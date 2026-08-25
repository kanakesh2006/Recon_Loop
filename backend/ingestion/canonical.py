"""Canonical transaction schema — the single normalized shape every source maps into.

Money is stored in **paise** (integer-valued Decimal, rupees x 100) to eliminate
floating-point matching errors, and is always positive; direction/type lives in
`txn_type` (see docs/raw_schemas.md and the per-source mappers).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SourceType = Literal["ledger", "settlement", "bank"]
TxnType = Literal["payment", "refund", "fee", "chargeback", "adjustment"]


class CanonicalTransaction(BaseModel):
    txn_id: str
    source: SourceType
    amount: Decimal
    currency: str = "INR"
    date: date
    reference: str
    counterparty: str
    txn_type: TxnType
    raw_record: dict = Field(default_factory=dict)

    @field_validator("amount")
    @classmethod
    def _amount_must_be_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError(f"amount must be positive (paise), got {value}")
        return value
