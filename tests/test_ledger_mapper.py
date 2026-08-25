import csv
from datetime import date
from decimal import Decimal

from backend.ingestion.ledger_mapper import ingest_ledger


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


LEDGER_ROW = {
    "order_id": "order_a1111111111111",
    "customer_name": "Priya Sharma",
    "amount": "2499.00",
    "currency": "INR",
    "order_date": "2026-07-14",
    "payment_method": "UPI",
    "status": "completed",
    "notes": "regular sale",
}


def test_maps_fields_correctly(tmp_path):
    path = tmp_path / "ledger.csv"
    write_csv(path, [LEDGER_ROW])
    txns = ingest_ledger(str(path))

    assert len(txns) == 1
    txn = txns[0]
    assert txn.txn_id == "led_order_a1111111111111"
    assert txn.source == "ledger"
    assert txn.amount == Decimal("249900")
    assert txn.date == date(2026, 7, 14)
    assert txn.reference == "order_a1111111111111"
    assert txn.counterparty == "Priya Sharma"
    assert txn.txn_type == "payment"
    assert txn.currency == "INR"
    assert txn.raw_record["payment_method"] == "UPI"
    assert txn.raw_record["notes"] == "regular sale"


def test_date_formats_and_status_inference(tmp_path):
    path = tmp_path / "ledger.csv"
    write_csv(
        path,
        [
            {
                **LEDGER_ROW,
                "order_id": "order_b2222222222222",
                "order_date": "15/07/2026",
                "status": "refund",
            },
            {**LEDGER_ROW, "order_id": "order_c3333333333333", "status": "chargeback"},
            {**LEDGER_ROW, "order_id": "order_d4444444444444", "status": "pending"},
        ],
    )
    txns = ingest_ledger(str(path))

    assert len(txns) == 3
    assert txns[0].date == date(2026, 7, 15)
    assert txns[0].txn_type == "refund"
    assert txns[1].txn_type == "chargeback"
    assert txns[2].txn_type == "payment"


def test_missing_optional_fields_default_gracefully(tmp_path):
    path = tmp_path / "ledger.csv"
    write_csv(path, [{**LEDGER_ROW, "customer_name": "", "currency": "", "notes": ""}])
    txns = ingest_ledger(str(path))

    assert len(txns) == 1
    assert txns[0].counterparty == ""
    assert txns[0].currency == "INR"


def test_duplicate_order_ids_get_unique_txn_ids(tmp_path):
    path = tmp_path / "ledger.csv"
    write_csv(path, [LEDGER_ROW, LEDGER_ROW])
    txns = ingest_ledger(str(path))

    assert len(txns) == 2
    assert [t.txn_id for t in txns] == [
        "led_order_a1111111111111",
        "led_order_a1111111111111#2",
    ]
    assert all(t.reference == "order_a1111111111111" for t in txns)


def test_malformed_rows_skipped_with_warning(tmp_path, capsys):
    path = tmp_path / "ledger.csv"
    write_csv(
        path,
        [
            LEDGER_ROW,
            {**LEDGER_ROW, "order_id": "", "amount": "10.00"},
            {**LEDGER_ROW, "order_id": "order_x", "amount": ""},
            {**LEDGER_ROW, "order_id": "order_y", "order_date": "not-a-date"},
        ],
    )
    txns = ingest_ledger(str(path))

    assert len(txns) == 1
    assert "skipping malformed row" in capsys.readouterr().err


def test_missing_file_raises(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        ingest_ledger(str(tmp_path / "nope.csv"))
