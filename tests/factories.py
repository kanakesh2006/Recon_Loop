from datetime import date
from decimal import Decimal

from backend.ingestion.canonical import CanonicalTransaction


def ledger_txn(
    reference="order_1",
    amount_paise=100000,
    day=1,
    month=7,
    txn_type="payment",
    status="completed",
    suffix="",
):
    return CanonicalTransaction(
        txn_id=f"led_{reference}{suffix}",
        source="ledger",
        amount=Decimal(amount_paise),
        date=date(2026, month, day),
        reference=reference,
        counterparty="Test Customer",
        txn_type=txn_type,
        raw_record={"order_id": reference, "status": status},
    )


def settlement_txn(
    reference="order_1",
    utr="HDFCN202607020000000001",
    amount_paise=98000,
    day=2,
    month=7,
    txn_type="payment",
    status="processed",
    sid="1",
):
    return CanonicalTransaction(
        txn_id=f"stl_setl_{sid}",
        source="settlement",
        amount=Decimal(amount_paise),
        date=date(2026, month, day),
        reference=reference,
        counterparty="mer_test",
        txn_type=txn_type,
        raw_record={
            "settlement_id": f"setl_{sid}",
            "txn_ref": reference,
            "utr_number": utr,
            "status": status,
        },
    )


def bank_txn(
    reference="NEFT/HDFCN202607020000000001/RZPPAYOUT",
    amount_paise=98000,
    day=2,
    direction="cr",
    txn_type="payment",
    bid="1",
):
    return CanonicalTransaction(
        txn_id=f"bnk_{direction}_{reference}_{bid}",
        source="bank",
        amount=Decimal(amount_paise),
        date=date(2026, 7, day),
        reference=reference,
        counterparty="RAZORPAY PAYOUT",
        txn_type=txn_type,
        raw_record={"reference_no": reference},
    )
