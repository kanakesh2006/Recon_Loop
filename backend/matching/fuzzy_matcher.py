"""Stage 2 — fuzzy matching on unmatched residuals.

Three passes live here:
- fuzzy_match_residuals: settlement <-> bank via rapidfuzz UTR similarity with
  amount-tolerance and date-window bands (catches rounding_diff, date drift
  on the bank side, ref_typo).
- match_bundled_payouts: N settlements sharing one UTR vs one summed bank
  credit (one-to-many).
- fuzzy_match_ledger_settlement: ledger <-> settlement residuals where the
  reference key matched exactly but the exact window/type rules failed
  (settlement date drift beyond the exact window, partial-refund type
  mismatch). Chargeback reversals are never paired here.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from rapidfuzz import fuzz

from backend.ingestion.canonical import CanonicalTransaction

from .exact_matcher import sb_types_compatible, settlement_utr
from .match_record import MatchRecord, build_match_record
from .utils import amount_diff_paise, date_diff_days, extract_utr

FUZZY_SB_RULE = "fuzzy_utr_amount_date"
BUNDLED_RULE = "bundled_payout_utr"
LS_DATE_WINDOW_RULE = "fuzzy_ls_ref_date_window"
LS_PARTIAL_REFUND_RULE = "fuzzy_ls_ref_partial_refund"

DEFAULT_AMOUNT_TOLERANCE_PAISE = 200
DEFAULT_DATE_TOLERANCE_DAYS = 5
DEFAULT_REF_SIMILARITY_THRESHOLD = 80.0
DEFAULT_BUNDLE_TOLERANCE_PAISE = 100
DEFAULT_LS_DATE_WINDOW_DAYS = 30
BUNDLE_CONFIDENCE = 0.95
LS_DATE_WINDOW_CONFIDENCE = 0.9
LS_PARTIAL_REFUND_CONFIDENCE = 0.88
BUNDLE_FUZZY_THRESHOLD = 90.0


def fuzzy_match_residuals(
    unmatched_settlements: list[CanonicalTransaction],
    unmatched_bank: list[CanonicalTransaction],
    amount_tolerance_paise: int = DEFAULT_AMOUNT_TOLERANCE_PAISE,
    date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
    ref_similarity_threshold: float = DEFAULT_REF_SIMILARITY_THRESHOLD,
) -> tuple[list[MatchRecord], list[CanonicalTransaction], list[CanonicalTransaction]]:
    matches: list[MatchRecord] = []
    available = list(unmatched_bank)
    remaining_settlements: list[CanonicalTransaction] = []

    for settlement in unmatched_settlements:
        settlement_utr_value = settlement_utr(settlement)
        best_bank: CanonicalTransaction | None = None
        best_confidence = -1.0
        best_details: dict | None = None

        for bank in available:
            bank_utr = extract_utr(bank.reference)
            if not settlement_utr_value or not bank_utr:
                continue
            similarity = fuzz.ratio(settlement_utr_value, bank_utr)
            if similarity < ref_similarity_threshold:
                continue
            if not sb_types_compatible(settlement, bank):
                continue
            amount_diff = amount_diff_paise(settlement.amount, bank.amount)
            if amount_diff > amount_tolerance_paise:
                continue
            days_diff = date_diff_days(settlement.date, bank.date)
            if days_diff > date_tolerance_days:
                continue

            ref_score = similarity / 100.0
            amt_score = max(0.0, 1.0 - float(amount_diff) / amount_tolerance_paise)
            date_score = max(0.0, 1.0 - days_diff / date_tolerance_days)
            confidence = 0.5 * ref_score + 0.3 * amt_score + 0.2 * date_score
            if confidence > best_confidence:
                best_confidence = confidence
                best_bank = bank
                best_details = {
                    "utr_similarity": round(similarity, 2),
                    "amount_diff_paise": int(amount_diff),
                    "date_diff_days": days_diff,
                }

        if best_bank is not None:
            available.remove(best_bank)
            matches.append(
                build_match_record(
                    txn_ids=[settlement.txn_id, best_bank.txn_id],
                    match_stage="fuzzy",
                    confidence_score=round(best_confidence, 4),
                    rule_or_model=FUZZY_SB_RULE,
                    details=best_details,
                )
            )
        else:
            remaining_settlements.append(settlement)

    return matches, remaining_settlements, available


def match_bundled_payouts(
    unmatched_settlements: list[CanonicalTransaction],
    unmatched_bank: list[CanonicalTransaction],
    amount_tolerance_paise: int = DEFAULT_BUNDLE_TOLERANCE_PAISE,
) -> tuple[list[MatchRecord], list[CanonicalTransaction], list[CanonicalTransaction]]:
    by_utr: dict[str, list[CanonicalTransaction]] = defaultdict(list)
    for settlement in unmatched_settlements:
        utr = settlement_utr(settlement)
        if utr:
            by_utr[utr].append(settlement)

    available = list(unmatched_bank)
    matches: list[MatchRecord] = []
    consumed_settlement_ids: set[str] = set()

    for utr, group in by_utr.items():
        if len(group) < 2:
            continue
        total = sum((s.amount for s in group), Decimal("0"))
        bank = next((b for b in available if extract_utr(b.reference) == utr), None)
        if bank is None:
            best_score = -1.0
            for candidate in available:
                score = fuzz.ratio(utr, extract_utr(candidate.reference) or "")
                if score >= BUNDLE_FUZZY_THRESHOLD and score > best_score:
                    best_score = score
                    bank = candidate
        diff = amount_diff_paise(total, bank.amount) if bank is not None else None
        if (
            bank is None
            or diff > amount_tolerance_paise
            or not sb_types_compatible(group[0], bank)
        ):
            continue

        consumed_settlement_ids.update(s.txn_id for s in group)
        available.remove(bank)
        matches.append(
            build_match_record(
                txn_ids=[s.txn_id for s in group] + [bank.txn_id],
                match_stage="fuzzy",
                confidence_score=BUNDLE_CONFIDENCE,
                rule_or_model=BUNDLED_RULE,
                details={
                    "utr": utr,
                    "settlement_count": len(group),
                    "summed_net_paise": int(total),
                    "amount_diff_paise": int(diff),
                },
            )
        )

    remaining_settlements = [
        s for s in unmatched_settlements if s.txn_id not in consumed_settlement_ids
    ]
    return matches, remaining_settlements, available


def fuzzy_match_ledger_settlement(
    unmatched_ledger: list[CanonicalTransaction],
    unmatched_settlements: list[CanonicalTransaction],
    date_window_days: int = DEFAULT_LS_DATE_WINDOW_DAYS,
) -> tuple[list[MatchRecord], list[CanonicalTransaction], list[CanonicalTransaction]]:
    by_ref: dict[str, list[CanonicalTransaction]] = defaultdict(list)
    for settlement in unmatched_settlements:
        by_ref[settlement.reference].append(settlement)

    matches: list[MatchRecord] = []
    consumed_settlement_ids: set[str] = set()
    remaining_ledger: list[CanonicalTransaction] = []

    for led in unmatched_ledger:
        found: CanonicalTransaction | None = None
        details: dict | None = None
        rule = ""
        confidence = 0.0
        for settlement in by_ref.get(led.reference, []):
            if settlement.txn_id in consumed_settlement_ids:
                continue
            lag_days = (settlement.date - led.date).days
            if settlement.txn_type == "chargeback" or lag_days < 0:
                continue
            if led.txn_type == "payment" and settlement.txn_type == "refund":
                found = settlement
                rule = LS_PARTIAL_REFUND_RULE
                confidence = LS_PARTIAL_REFUND_CONFIDENCE
                details = {
                    "type_mismatch": "ledger_payment_vs_settlement_refund",
                    "date_diff_days": lag_days,
                }
                break
            if (
                led.txn_type == settlement.txn_type
                and 0 <= lag_days <= date_window_days
            ):
                found = settlement
                rule = LS_DATE_WINDOW_RULE
                confidence = LS_DATE_WINDOW_CONFIDENCE
                details = {"date_diff_days": lag_days}
                break
        if found is not None:
            consumed_settlement_ids.add(found.txn_id)
            matches.append(
                build_match_record(
                    txn_ids=[led.txn_id, found.txn_id],
                    match_stage="fuzzy",
                    confidence_score=confidence,
                    rule_or_model=rule,
                    details=details,
                )
            )
        else:
            remaining_ledger.append(led)

    remaining_settlements = [
        s for s in unmatched_settlements if s.txn_id not in consumed_settlement_ids
    ]
    return matches, remaining_ledger, remaining_settlements
