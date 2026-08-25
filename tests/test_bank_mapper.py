import csv
from datetime import date
from decimal import Decimal

from backend.ingestion.bank_mapper import ingest_bank


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


CREDIT_ROW = {
    "date": "2026-07-15",
    "description": "RAZORPAY SOFTWARE PVT LTD PAYOUT",
    "reference_no": "NEFT/HDFCN202607150012345678/RZPPAYOUT",
    "debit": "0.00",
    "credit": "2436.48",
    "balance": "502436.48",
}


def test_credit_becomes_payment(tmp_path):
    path = tmp_path / "bank.csv"
    write_csv(path, [CREDIT_ROW])
    txns = ingest_bank(str(path))

    assert len(txns) == 1
    txn = txns[0]
    assert txn.txn_id == "bnk_cr_NEFT/HDFCN202607150012345678/RZPPAYOUT"
    assert txn.source == "bank"
    assert txn.amount == Decimal("243648")
    assert txn.date == date(2026, 7, 15)
    assert txn.reference == "NEFT/HDFCN202607150012345678/RZPPAYOUT"
    assert txn.counterparty == "RAZORPAY SOFTWARE PVT LTD PAYOUT"
    assert txn.txn_type == "payment"


def test_debit_types_inferred_from_description(tmp_path):
    path = tmp_path / "bank.csv"
    write_csv(
        path,
        [
            {
                **CREDIT_ROW,
                "debit": "500.00",
                "credit": "0.00",
                "description": "REFUND UTR12345",
                "reference_no": "REF/UTR12345/REFUND",
            },
            {
                **CREDIT_ROW,
                "debit": "2499.00",
                "credit": "0.00",
                "description": "RAZORPAY CHARGEBACK REVERSAL",
                "reference_no": "REV/UTR67890/CHARGEBACK",
            },
            {
                **CREDIT_ROW,
                "debit": "100.00",
                "credit": "0.00",
                "description": "BANK CHARGES",
                "reference_no": "CHG/000111/FEES",
            },
        ],
    )
    txns = ingest_bank(str(path))

    assert [t.txn_type for t in txns] == ["refund", "chargeback", "adjustment"]
    assert all(t.amount > 0 for t in txns)
    assert [t.txn_id.split("_")[1] for t in txns] == ["dr", "dr", "dr"]
    assert txns[1].amount == Decimal("249900")


def test_bundled_credit_ingests_as_single_row(tmp_path):
    path = tmp_path / "bank.csv"
    write_csv(
        path,
        [
            {
                **CREDIT_ROW,
                "credit": "7309.44",
                "description": "RAZORPAY SOFTWARE PVT LTD BUNDLE PAYOUT",
                "reference_no": "NEFT/HDFCN202607160098765432/RZPPAYOUT",
            },
        ],
    )
    txns = ingest_bank(str(path))

    assert len(txns) == 1
    assert txns[0].amount == Decimal("730944")
    assert txns[0].txn_type == "payment"


def test_zero_amount_rows_skipped(tmp_path, capsys):
    path = tmp_path / "bank.csv"
    write_csv(
        path,
        [
            CREDIT_ROW,
            {
                **CREDIT_ROW,
                "debit": "0.00",
                "credit": "0.00",
                "reference_no": "EMPTY/ROW/1",
            },
        ],
    )
    txns = ingest_bank(str(path))

    assert len(txns) == 1
    assert "no amount" in capsys.readouterr().err


def test_duplicate_reference_gets_suffix(tmp_path):
    path = tmp_path / "bank.csv"
    write_csv(path, [CREDIT_ROW, {**CREDIT_ROW, "date": "2026-07-16"}])
    txns = ingest_bank(str(path))

    assert [t.txn_id for t in txns] == [
        "bnk_cr_NEFT/HDFCN202607150012345678/RZPPAYOUT",
        "bnk_cr_NEFT/HDFCN202607150012345678/RZPPAYOUT#2",
    ]
