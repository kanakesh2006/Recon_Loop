"""Small matching utilities: UTR extraction and amount/date diff helpers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal


def extract_utr(bank_reference: str) -> str | None:
    """Extract the UTR from a bank reference like 'NEFT/{utr}/RZPPAYOUT'.

    Splits on '/' and takes the second segment; returns the whole string when
    no '/' is present; returns None for empty input.
    """
    value = (bank_reference or "").strip()
    if not value:
        return None
    parts = value.split("/")
    return parts[1] if len(parts) > 1 and parts[1] else value


def amount_diff_paise(a: Decimal, b: Decimal) -> Decimal:
    return abs(a - b)


def date_diff_days(d1: date, d2: date) -> int:
    return abs((d1 - d2).days)
