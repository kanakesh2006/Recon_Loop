from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.ingestion.canonical import CanonicalTransaction


def make_txn(**overrides):
    base = dict(
        txn_id="led_order_abc123def456",
        source="ledger",
        amount=Decimal("249900"),
        currency="INR",
        date=date(2026, 7, 14),
        reference="order_abc123def456",
        counterparty="Priya Sharma",
        txn_type="payment",
        raw_record={"order_id": "order_abc123def456"},
    )
    base.update(overrides)
    return CanonicalTransaction(**base)


def test_create_from_sample_data():
    txn = make_txn()
    assert txn.txn_id == "led_order_abc123def456"
    assert txn.source == "ledger"
    assert txn.amount == Decimal("249900")
    assert txn.currency == "INR"
    assert txn.date == date(2026, 7, 14)
    assert txn.txn_type == "payment"


def test_json_roundtrip():
    txn = make_txn()
    restored = CanonicalTransaction.model_validate_json(txn.model_dump_json())
    assert restored == txn
    assert restored.amount == Decimal("249900")
    assert restored.date == date(2026, 7, 14)


def test_negative_amount_rejected():
    with pytest.raises(ValidationError):
        make_txn(amount=Decimal("-100"))


def test_zero_amount_rejected():
    with pytest.raises(ValidationError):
        make_txn(amount=Decimal("0"))


def test_invalid_source_rejected():
    with pytest.raises(ValidationError):
        make_txn(source="paypal")


def test_invalid_txn_type_rejected():
    with pytest.raises(ValidationError):
        make_txn(txn_type="payout")
