import csv
from datetime import date
from decimal import Decimal

from backend.ingestion.settlement_mapper import ingest_settlement


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


SETTLEMENT_ROW = {
    "settlement_id": "setl_a1111111111111",
    "txn_ref": "order_a1111111111111",
    "merchant_id": "mer_x1111111111111",
    "gross_amount": "2499.00",
    "fee": "52.98",
    "tax_on_fee": "9.54",
    "net_amount": "2436.48",
    "settlement_date": "2026-07-15",
    "utr_number": "HDFCN202607150012345678",
    "status": "processed",
}


def test_maps_fields_correctly(tmp_path):
    path = tmp_path / "settlement.csv"
    write_csv(path, [SETTLEMENT_ROW])
    txns = ingest_settlement(str(path))

    assert len(txns) == 1
    txn = txns[0]
    assert txn.txn_id == "stl_setl_a1111111111111"
    assert txn.source == "settlement"
    assert txn.amount == Decimal("243648")
    assert txn.date == date(2026, 7, 15)
    assert txn.reference == "order_a1111111111111"
    assert txn.counterparty == "mer_x1111111111111"
    assert txn.txn_type == "payment"
    assert txn.raw_record["fee"] == "52.98"
    assert txn.raw_record["tax_on_fee"] == "9.54"
    assert txn.raw_record["utr_number"] == "HDFCN202607150012345678"


def test_chargeback_negative_net_becomes_positive_chargeback(tmp_path):
    path = tmp_path / "settlement.csv"
    write_csv(
        path,
        [
            {
                **SETTLEMENT_ROW,
                "gross_amount": "-2499.00",
                "net_amount": "-2436.48",
                "status": "chargeback",
            }
        ],
    )
    txns = ingest_settlement(str(path))

    assert len(txns) == 1
    assert txns[0].amount == Decimal("243648")
    assert txns[0].txn_type == "chargeback"


def test_refund_status_inferred(tmp_path):
    path = tmp_path / "settlement.csv"
    write_csv(path, [{**SETTLEMENT_ROW, "status": "refund"}])
    txns = ingest_settlement(str(path))

    assert txns[0].txn_type == "refund"


def test_malformed_rows_skipped_with_warning(tmp_path, capsys):
    path = tmp_path / "settlement.csv"
    write_csv(
        path,
        [
            SETTLEMENT_ROW,
            {**SETTLEMENT_ROW, "settlement_id": ""},
            {**SETTLEMENT_ROW, "net_amount": ""},
            {**SETTLEMENT_ROW, "settlement_date": "31/31/2026"},
        ],
    )
    txns = ingest_settlement(str(path))

    assert len(txns) == 1
    assert "skipping malformed row" in capsys.readouterr().err
