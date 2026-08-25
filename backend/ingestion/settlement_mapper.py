"""Ingestor for gateway_settlement.csv -> CanonicalTransaction list.

The canonical `amount` is `net_amount` (after fees); `fee` / `tax_on_fee` are
preserved in `raw_record`. Chargeback rows carry a negative net_amount in the
CSV; the canonical amount is stored positive with txn_type="chargeback" so the
direction is typed rather than sign-encoded.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from .canonical import CanonicalTransaction, TxnType
from .ledger_mapper import parse_date, to_paise


def infer_txn_type(status: str) -> TxnType:
    value = (status or "").strip().lower()
    if "chargeback" in value or "reversal" in value:
        return "chargeback"
    if "refund" in value:
        return "refund"
    return "payment"


def ingest_settlement(csv_path: str) -> list[CanonicalTransaction]:
    """Read the gateway settlement CSV into canonical transactions.

    Rows missing settlement_id / net_amount / settlement_date are skipped with a
    warning rather than crashing the batch.
    """
    transactions: list[CanonicalTransaction] = []

    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"settlement CSV not found: {csv_path}")

    with open(path, newline="", encoding="utf-8") as handle:
        for line_no, row in enumerate(csv.DictReader(handle), start=2):
            settlement_id = (row.get("settlement_id") or "").strip()
            net_raw = to_paise(row.get("net_amount"))
            txn_date = parse_date(row.get("settlement_date", ""))

            if not settlement_id or net_raw is None or txn_date is None:
                print(
                    f"[settlement_mapper] skipping malformed row {line_no} in {path.name}",
                    file=sys.stderr,
                )
                continue

            txn_type = infer_txn_type(row.get("status"))
            transactions.append(
                CanonicalTransaction(
                    txn_id=f"stl_{settlement_id}",
                    source="settlement",
                    amount=abs(net_raw),
                    currency="INR",
                    date=txn_date,
                    reference=(row.get("txn_ref") or "").strip(),
                    counterparty=(row.get("merchant_id") or "").strip(),
                    txn_type=txn_type,
                    raw_record=dict(row),
                )
            )
    return transactions
