"""Stage 1 — exact matchers.

Ledger <-> Settlement joins on `reference` (order_id = txn_ref). Amounts are
NOT compared here: ledger amounts are gross, settlement amounts are net of
fees, so a difference is expected. Settlement <-> Bank joins on UTR (extracted
from the bank reference string); amounts must be equal for a 1:1 match.
"""

from __future__ import annotations

from collections import defaultdict

from backend.ingestion.canonical import CanonicalTransaction

from .match_record import MatchRecord, build_match_record
from .utils import extract_utr

LS_EXACT_RULE = "exact_ledger_settlement_ref"
SB_EXACT_RULE = "exact_settlement_bank_utr"
MAX_EXACT_LAG_DAYS = 2


def settlement_utr(settlement: CanonicalTransaction) -> str:
    return str(settlement.raw_record.get("utr_number", "") or "").strip()


def sb_types_compatible(
    settlement: CanonicalTransaction, bank: CanonicalTransaction
) -> bool:
    """Bank credits (payment) settle payments and (net-of-refund) refunds.
    Bank debits pair with chargeback reversals."""
    if bank.txn_type == "payment":
        return settlement.txn_type in ("payment", "refund")
    if bank.txn_type == "chargeback":
        return settlement.txn_type == "chargeback"
    if bank.txn_type == "refund":
        return settlement.txn_type == "refund"
    return False


def exact_match_ledger_settlement(
    ledger: list[CanonicalTransaction],
    settlements: list[CanonicalTransaction],
) -> tuple[list[MatchRecord], list[CanonicalTransaction], list[CanonicalTransaction]]:
    """Match ledger rows to settlements on exact reference + type + date window.

    The first ledger row for a reference consumes the settlement (duplicate
    entries stay unmatched and are flagged downstream). Pending orders and
    chargeback reversals legitimately find no partner here.
    """
    by_ref: dict[str, list[CanonicalTransaction]] = defaultdict(list)
    for settlement in settlements:
        by_ref[settlement.reference].append(settlement)

    matches: list[MatchRecord] = []
    matched_settlement_ids: set[str] = set()
    unmatched_ledger: list[CanonicalTransaction] = []

    for led in ledger:
        found: CanonicalTransaction | None = None
        for settlement in by_ref.get(led.reference, []):
            if settlement.txn_id in matched_settlement_ids:
                continue
            lag_days = (settlement.date - led.date).days
            if (
                led.txn_type == settlement.txn_type
                and 0 <= lag_days <= MAX_EXACT_LAG_DAYS
            ):
                found = settlement
                break
        if found is not None:
            matched_settlement_ids.add(found.txn_id)
            matches.append(
                build_match_record(
                    txn_ids=[led.txn_id, found.txn_id],
                    match_stage="exact",
                    confidence_score=1.0,
                    rule_or_model=LS_EXACT_RULE,
                )
            )
        else:
            unmatched_ledger.append(led)

    unmatched_settlements = [
        s for s in settlements if s.txn_id not in matched_settlement_ids
    ]
    return matches, unmatched_ledger, unmatched_settlements


def exact_match_settlement_bank(
    settlements: list[CanonicalTransaction],
    bank_txns: list[CanonicalTransaction],
) -> tuple[list[MatchRecord], list[CanonicalTransaction], list[CanonicalTransaction]]:
    """Match settlements to bank rows on exact UTR + equal amount + type.

    Bundled payouts (N settlements sharing one UTR, one summed bank credit)
    fail the 1:1 amount check and stay unconsumed for the bundled matcher.
    """
    bank_by_utr: dict[str, CanonicalTransaction] = {}
    for bank in bank_txns:
        utr = extract_utr(bank.reference)
        if utr:
            bank_by_utr[utr] = bank

    matches: list[MatchRecord] = []
    matched_bank_ids: set[str] = set()
    unmatched_settlements: list[CanonicalTransaction] = []

    for settlement in settlements:
        utr = settlement_utr(settlement)
        bank = bank_by_utr.get(utr) if utr else None
        if (
            bank is not None
            and bank.txn_id not in matched_bank_ids
            and settlement.amount == bank.amount
            and sb_types_compatible(settlement, bank)
        ):
            matched_bank_ids.add(bank.txn_id)
            matches.append(
                build_match_record(
                    txn_ids=[settlement.txn_id, bank.txn_id],
                    match_stage="exact",
                    confidence_score=1.0,
                    rule_or_model=SB_EXACT_RULE,
                )
            )
        else:
            unmatched_settlements.append(settlement)

    unmatched_bank = [b for b in bank_txns if b.txn_id not in matched_bank_ids]
    return matches, unmatched_settlements, unmatched_bank
