"""Matching pipeline orchestrator.

Sequence: ingest -> LS exact -> SB exact (all settlements) -> bundled ->
SB fuzzy -> LS fuzzy -> assemble -> route -> stats. Assembly runs once after
all settlement-side matching so each event chain becomes exactly one record
(no double-counting of bundled/fuzzy events as separate 2-way records).
"""

from __future__ import annotations

from time import perf_counter

from pydantic import BaseModel, Field

from backend.ingestion.bank_mapper import ingest_bank
from backend.ingestion.ledger_mapper import ingest_ledger
from backend.ingestion.settlement_mapper import ingest_settlement

from .confidence import route_matches
from .exact_matcher import exact_match_ledger_settlement, exact_match_settlement_bank
from .fuzzy_matcher import (
    fuzzy_match_ledger_settlement,
    fuzzy_match_residuals,
    match_bundled_payouts,
)
from .match_record import MatchRecord
from .three_way import assemble_three_way_matches


class MatchingResult(BaseModel):
    auto_matched: list[MatchRecord] = Field(default_factory=list)
    needs_review: list[MatchRecord] = Field(default_factory=list)
    exceptions: list[MatchRecord] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)


def run_matching_pipeline(
    ledger_path: str,
    settlement_path: str,
    bank_path: str,
) -> MatchingResult:
    started = perf_counter()

    ledger = ingest_ledger(ledger_path)
    settlements = ingest_settlement(settlement_path)
    bank_txns = ingest_bank(bank_path)

    ls_matches, unmatched_ledger, ls_unmatched_settlements = (
        exact_match_ledger_settlement(ledger, settlements)
    )
    sb_matches, sb_unmatched_settlements, unmatched_bank = exact_match_settlement_bank(
        settlements, bank_txns
    )
    bundled_matches, bundle_residual_settlements, unmatched_bank = (
        match_bundled_payouts(sb_unmatched_settlements, unmatched_bank)
    )
    fuzzy_matches, fuzzy_residual_settlements, unmatched_bank = fuzzy_match_residuals(
        bundle_residual_settlements, unmatched_bank
    )
    ls_fuzzy_matches, unmatched_ledger, ls_residual_settlements = (
        fuzzy_match_ledger_settlement(unmatched_ledger, ls_unmatched_settlements)
    )

    sb_stage_matches = sb_matches + bundled_matches + fuzzy_matches
    assembled = assemble_three_way_matches(
        ls_matches + ls_fuzzy_matches, sb_stage_matches
    )

    claimed_txn_ids = {txn_id for record in assembled for txn_id in record.txn_ids}
    residual_settlements = [s for s in settlements if s.txn_id not in claimed_txn_ids]
    residual_bank = [b for b in bank_txns if b.txn_id not in claimed_txn_ids]

    auto_matched, needs_review, exceptions = route_matches(
        assembled, unmatched_ledger, residual_settlements, residual_bank
    )

    elapsed_ms = (perf_counter() - started) * 1000
    total_events = len({t.reference for t in ledger})
    stats = {
        "total_records": len(auto_matched) + len(needs_review) + len(exceptions),
        "auto_matched_count": len(auto_matched),
        "review_count": len(needs_review),
        "exception_count": len(exceptions),
        "total_events": total_events,
        "match_rate": (
            round(len(auto_matched) / total_events, 4) if total_events else 0.0
        ),
        "processing_time_ms": round(elapsed_ms, 2),
    }

    return MatchingResult(
        auto_matched=auto_matched,
        needs_review=needs_review,
        exceptions=exceptions,
        stats=stats,
    )
