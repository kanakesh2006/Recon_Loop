"""Stage 3 — confidence-based routing.

Re-routes every assembled match by confidence threshold, then converts all
residual transactions into unmatched MatchRecords. Pending orders and
duplicate ledger entries land in needs_review (they are not breaks); anything
else unresolved is an honest exception.
"""

from __future__ import annotations

from backend.ingestion.canonical import CanonicalTransaction

from .match_record import MatchRecord, build_match_record

DEFAULT_AUTO_THRESHOLD = 0.85
DEFAULT_REVIEW_THRESHOLD = 0.50


def route_matches(
    matches: list[MatchRecord],
    unmatched_ledger: list[CanonicalTransaction],
    unmatched_settlements: list[CanonicalTransaction],
    unmatched_bank: list[CanonicalTransaction],
    auto_threshold: float = DEFAULT_AUTO_THRESHOLD,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> tuple[list[MatchRecord], list[MatchRecord], list[MatchRecord]]:
    auto_matched: list[MatchRecord] = []
    needs_review: list[MatchRecord] = []
    exceptions: list[MatchRecord] = []

    for record in matches:
        if record.confidence_score >= auto_threshold:
            record.status = "auto_matched"
            auto_matched.append(record)
        elif record.confidence_score >= review_threshold:
            record.status = "needs_review"
            needs_review.append(record)
        else:
            record.status = "exception"
            exceptions.append(record)

    for led in unmatched_ledger:
        raw_status = str(led.raw_record.get("status", "") or "").strip().lower()
        if led.txn_type == "payment" and raw_status == "pending":
            needs_review.append(
                build_match_record(
                    txn_ids=[led.txn_id],
                    match_stage="unmatched",
                    confidence_score=0.0,
                    rule_or_model="pending_order",
                    status="needs_review",
                    details={"reason": "order not settled yet"},
                )
            )
        elif "#" in led.txn_id:
            needs_review.append(
                build_match_record(
                    txn_ids=[led.txn_id],
                    match_stage="unmatched",
                    confidence_score=0.0,
                    rule_or_model="possible_duplicate",
                    status="needs_review",
                    details={"reason": "possible duplicate ledger entry"},
                )
            )
        else:
            exceptions.append(
                build_match_record(
                    txn_ids=[led.txn_id],
                    match_stage="unmatched",
                    confidence_score=0.0,
                    rule_or_model="no_match_found",
                    status="exception",
                    details={"reason": "no settlement or bank counterpart resolved"},
                )
            )

    for settlement in unmatched_settlements:
        exceptions.append(
            build_match_record(
                txn_ids=[settlement.txn_id],
                match_stage="unmatched",
                confidence_score=0.0,
                rule_or_model="no_match_found",
                status="exception",
                details={"reason": "settlement with no ledger/bank counterpart"},
            )
        )

    for bank in unmatched_bank:
        exceptions.append(
            build_match_record(
                txn_ids=[bank.txn_id],
                match_stage="unmatched",
                confidence_score=0.0,
                rule_or_model="no_match_found",
                status="exception",
                details={"reason": "bank row with no settlement counterpart"},
            )
        )

    return auto_matched, needs_review, exceptions
