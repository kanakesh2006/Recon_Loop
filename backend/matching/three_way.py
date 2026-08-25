"""Three-way match assembler.

Merges ledger<->settlement matches with settlement-side matches (exact SB,
bundled, or fuzzy SB) that share a settlement txn_id. Fully linked chains
become one record; chains missing one side become 2-way records routed to
needs_review. Works for any SB-stage records, so the pipeline can assemble
once after all settlement-side matching has run.
"""

from __future__ import annotations

from backend.matching.match_record import MatchRecord, build_match_record

TWO_WAY_CONFIDENCE = 0.8


def _ordered_txn_ids(txn_ids: list[str]) -> list[str]:
    ordered: list[str] = []
    for prefix in ("led_", "stl_", "bnk_"):
        for txn_id in txn_ids:
            if txn_id.startswith(prefix) and txn_id not in ordered:
                ordered.append(txn_id)
    return ordered + [t for t in txn_ids if t not in ordered]


def assemble_three_way_matches(
    ls_matches: list[MatchRecord],
    sb_matches: list[MatchRecord],
) -> list[MatchRecord]:
    sb_by_settlement: dict[str, MatchRecord] = {}
    for sb in sb_matches:
        for txn_id in sb.txn_ids:
            if txn_id.startswith("stl_"):
                sb_by_settlement[txn_id] = sb

    grouped: dict[str, list[MatchRecord]] = {}
    unpaired_ls: list[MatchRecord] = []
    for ls in ls_matches:
        settlement_ids = [t for t in ls.txn_ids if t.startswith("stl_")]
        sb = sb_by_settlement.get(settlement_ids[0]) if settlement_ids else None
        if sb is not None:
            grouped.setdefault(sb.match_id, []).append(ls)
        else:
            unpaired_ls.append(ls)

    records: list[MatchRecord] = []
    for sb in sb_matches:
        group = grouped.get(sb.match_id, [])
        if not group:
            records.append(
                build_match_record(
                    txn_ids=_ordered_txn_ids(sb.txn_ids),
                    match_stage=sb.match_stage,
                    confidence_score=TWO_WAY_CONFIDENCE,
                    rule_or_model=sb.rule_or_model,
                    status="needs_review",
                    details=dict(sb.details),
                )
            )
            continue

        components = [*group, sb]
        txn_ids: list[str] = []
        for record in components:
            txn_ids.extend(record.txn_ids)
        confidence = min(record.confidence_score for record in components)
        stage = (
            "fuzzy" if any(r.match_stage == "fuzzy" for r in components) else "exact"
        )
        rule = "+".join(dict.fromkeys(r.rule_or_model for r in components))
        details: dict = {}
        for record in components:
            for key, value in record.details.items():
                details.setdefault(key, value)
        records.append(
            build_match_record(
                txn_ids=_ordered_txn_ids(txn_ids),
                match_stage=stage,
                confidence_score=confidence,
                rule_or_model=rule,
                details=details,
            )
        )

    for ls in unpaired_ls:
        records.append(
            build_match_record(
                txn_ids=_ordered_txn_ids(ls.txn_ids),
                match_stage=ls.match_stage,
                confidence_score=TWO_WAY_CONFIDENCE,
                rule_or_model=ls.rule_or_model,
                status="needs_review",
                details=dict(ls.details),
            )
        )
    return records
