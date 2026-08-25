import csv
import importlib.util
from pathlib import Path

from backend.ingestion.bank_mapper import ingest_bank
from backend.ingestion.ledger_mapper import ingest_ledger
from backend.ingestion.settlement_mapper import ingest_settlement

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = PROJECT_ROOT / "data" / "generate_synthetic.py"

CLEAN_COUNT = 60

_spec = importlib.util.spec_from_file_location("generate_synthetic", GENERATOR_PATH)
generate_synthetic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(generate_synthetic)


def _csv_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_full_ingestion_pipeline(tmp_path):
    out_dir = tmp_path / "samples"
    rc = generate_synthetic.main(
        ["--count", str(CLEAN_COUNT), "--output", str(out_dir), "--seed", "42"]
    )
    assert rc == 0

    ledger_csv = _csv_rows(out_dir / "internal_ledger.csv")
    settlement_csv = _csv_rows(out_dir / "gateway_settlement.csv")
    bank_csv = _csv_rows(out_dir / "bank_statement.csv")
    ground_truth = _csv_rows(out_dir / "ground_truth.csv")

    ledger = ingest_ledger(str(out_dir / "internal_ledger.csv"))
    settlements = ingest_settlement(str(out_dir / "gateway_settlement.csv"))
    bank = ingest_bank(str(out_dir / "bank_statement.csv"))
    all_txns = ledger + settlements + bank

    assert len(ledger) == len(ledger_csv) == 88
    assert len(settlements) == len(settlement_csv) == 83
    assert len(bank) == len(bank_csv) == 79
    assert len(all_txns) == 250
    assert len(ground_truth) == 86

    for txn in all_txns:
        assert txn.source in ("ledger", "settlement", "bank")
        assert txn.txn_type in ("payment", "refund", "fee", "chargeback", "adjustment")
        assert txn.amount > 0
        assert txn.raw_record

    by_source = {"ledger": ledger, "settlement": settlements, "bank": bank}
    for source, txns in by_source.items():
        ids = [t.txn_id for t in txns]
        assert len(ids) == len(set(ids)), f"duplicate txn_id within {source}"

    pending_refs = {
        row["order_id"] for row in ground_truth if row["edge_case_label"] == "pending"
    }
    settlement_refs = {t.reference for t in settlements}
    assert not (
        pending_refs & settlement_refs
    ), "pending events must have no settlement row"

    chargeback_refs = {
        row["order_id"]
        for row in ground_truth
        if row["edge_case_label"] == "chargeback"
    }
    chargeback_txns = [t for t in settlements if t.reference in chargeback_refs]
    assert len(chargeback_txns) == 2
    assert all(t.txn_type == "chargeback" for t in chargeback_txns)

    bundle_refs = {
        row["bank_reference"]
        for row in ground_truth
        if row["edge_case_label"] == "bundled_match"
    }
    bundle_bank_txns = [t for t in bank if t.reference in bundle_refs]
    assert len(bundle_bank_txns) == 2
    assert all(t.txn_type == "payment" for t in bundle_bank_txns)
