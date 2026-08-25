"""Ingestor for bank_statement.csv -> CanonicalTransaction list.

Credits become positive-amount payments; debits become positive-amount rows
whose txn_type is inferred from keywords in the description (refund /
chargeback, else adjustment). Exactly one canonical row per bank row — a
bundled payout credit ingests as a single row with the summed amount.
"""

from __future__ import annotations

import csv
import sys
from decimal import Decimal
from pathlib import Path

from .canonical import CanonicalTransaction, TxnType
from .ledger_mapper import parse_date, to_paise

_ZERO = Decimal("0")


def infer_debit_type(description: str) -> TxnType:
    value = (description or "").lower()
    if "chargeback" in value or "reversal" in value:
        return "chargeback"
    if "refund" in value:
        return "refund"
    return "adjustment"


def ingest_bank(csv_path: str) -> list[CanonicalTransaction]:
    """Read the bank statement CSV into canonical transactions.

    Rows with no parseable amount (debit and credit both zero/empty) are skipped
    with a warning. Duplicate reference_no within the same direction gets a
    `#2`, `#3`, ... suffix so txn_id stays unique within the source.
    """
    transactions: list[CanonicalTransaction] = []
    seen_ids: dict[str, int] = {}

    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"bank CSV not found: {csv_path}")

    with open(path, newline="", encoding="utf-8") as handle:
        for line_no, row in enumerate(csv.DictReader(handle), start=2):
            txn_date = parse_date(row.get("date", ""))
            credit = to_paise(row.get("credit")) or _ZERO
            debit = to_paise(row.get("debit")) or _ZERO
            reference_no = (row.get("reference_no") or "").strip()
            description = (row.get("description") or "").strip()

            if txn_date is None or not reference_no:
                print(
                    f"[bank_mapper] skipping malformed row {line_no} in {path.name}",
                    file=sys.stderr,
                )
                continue

            if credit > 0 and debit > 0:
                print(
                    f"[bank_mapper] skipping row {line_no}: both debit and credit set",
                    file=sys.stderr,
                )
                continue

            if credit > 0:
                direction, amount, txn_type = "cr", credit, "payment"
            elif debit > 0:
                direction, amount, txn_type = "dr", debit, infer_debit_type(description)
            else:
                print(
                    f"[bank_mapper] skipping row {line_no}: no amount",
                    file=sys.stderr,
                )
                continue

            base_id = f"bnk_{direction}_{reference_no}"
            count = seen_ids.get(base_id, 0) + 1
            seen_ids[base_id] = count
            txn_id = base_id if count == 1 else f"{base_id}#{count}"

            transactions.append(
                CanonicalTransaction(
                    txn_id=txn_id,
                    source="bank",
                    amount=amount,
                    currency="INR",
                    date=txn_date,
                    reference=reference_no,
                    counterparty=description,
                    txn_type=txn_type,
                    raw_record=dict(row),
                )
            )
    return transactions
