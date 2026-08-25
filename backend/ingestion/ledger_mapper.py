"""Ingestor for internal_ledger.csv -> CanonicalTransaction list."""

from __future__ import annotations

import csv
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .canonical import CanonicalTransaction, TxnType

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y")
_PAISE = Decimal("100")


def parse_date(raw: str):
    """Parse YYYY-MM-DD or DD/MM/YYYY; returns datetime.date or None."""
    value = (raw or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def to_paise(raw) -> Decimal | None:
    """Convert a rupee string like '1234.50' to integer paise Decimal (123450)."""
    value = str(raw or "").strip().replace(",", "").replace("₹", "")
    if not value:
        return None
    try:
        return (Decimal(value) * _PAISE).quantize(Decimal("1"))
    except InvalidOperation:
        return None


def infer_txn_type(status: str) -> TxnType:
    value = (status or "").strip().lower()
    if "refund" in value:
        return "refund"
    if "chargeback" in value or "reversal" in value:
        return "chargeback"
    return "payment"


def ingest_ledger(csv_path: str) -> list[CanonicalTransaction]:
    """Read the ledger CSV into canonical transactions.

    Rows missing order_id / amount / date are skipped with a warning rather than
    crashing the batch. Duplicate order_ids (the `duplicate_id` edge case) get a
    `#2`, `#3`, ... suffix on txn_id so IDs stay unique within the source while
    `reference` keeps the raw order_id for matching.
    """
    transactions: list[CanonicalTransaction] = []
    seen_ids: dict[str, int] = {}

    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"ledger CSV not found: {csv_path}")

    with open(path, newline="", encoding="utf-8") as handle:
        for line_no, row in enumerate(csv.DictReader(handle), start=2):
            order_id = (row.get("order_id") or "").strip()
            amount = to_paise(row.get("amount"))
            txn_date = parse_date(row.get("order_date", ""))

            if not order_id or amount is None or txn_date is None:
                print(
                    f"[ledger_mapper] skipping malformed row {line_no} in {path.name}",
                    file=sys.stderr,
                )
                continue

            count = seen_ids.get(order_id, 0) + 1
            seen_ids[order_id] = count
            txn_id = f"led_{order_id}" if count == 1 else f"led_{order_id}#{count}"

            transactions.append(
                CanonicalTransaction(
                    txn_id=txn_id,
                    source="ledger",
                    amount=amount,
                    currency=(row.get("currency") or "").strip() or "INR",
                    date=txn_date,
                    reference=order_id,
                    counterparty=(row.get("customer_name") or "").strip(),
                    txn_type=infer_txn_type(row.get("status")),
                    raw_record=dict(row),
                )
            )
    return transactions
