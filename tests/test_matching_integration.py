import csv
import importlib.util
from pathlib import Path

from backend.matching.pipeline import run_matching_pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = PROJECT_ROOT / "data" / "generate_synthetic.py"

_spec = importlib.util.spec_from_file_location("generate_synthetic", GENERATOR_PATH)
generate_synthetic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(generate_synthetic)

STATUS_PRIORITY = {"auto_matched": 0, "needs_review": 1, "exception": 2}


def test_full_matching_pipeline_on_generated_batch(tmp_path):
    out_dir = tmp_path / "samples"
    rc = generate_synthetic.main(
        ["--count", "60", "--output", str(out_dir), "--seed", "42"]
    )
    assert rc == 0

    result = run_matching_pipeline(
        str(out_dir / "internal_ledger.csv"),
        str(out_dir / "gateway_settlement.csv"),
        str(out_dir / "bank_statement.csv"),
    )

    stats = result.stats
    for key in (
        "total_records",
        "auto_matched_count",
        "review_count",
        "exception_count",
        "match_rate",
        "processing_time_ms",
    ):
        assert key in stats
    assert stats["processing_time_ms"] > 0
    assert 0.0 < stats["match_rate"] < 1.0
    assert stats["match_rate"] >= 0.5

    all_records = result.auto_matched + result.needs_review + result.exceptions
    for record in all_records:
        assert record.match_id
        assert record.txn_ids
        assert record.status in ("auto_matched", "needs_review", "exception")
        assert record.match_stage in ("exact", "fuzzy", "unmatched")
        assert 0.0 <= record.confidence_score <= 1.0
        assert record.rule_or_model
        assert record.timestamp

    with open(out_dir / "ground_truth.csv", newline="", encoding="utf-8") as handle:
        ground_truth = list(csv.DictReader(handle))

    records_by_ledger_ref: dict[str, list] = {}
    for record in all_records:
        for txn_id in record.txn_ids:
            if txn_id.startswith("led_"):
                ref = txn_id[4:].split("#")[0]
                records_by_ledger_ref.setdefault(ref, []).append(record)

    label_outcomes: dict[str, dict[str, int]] = {}
    for row in ground_truth:
        order_id = row["order_id"]
        linked = records_by_ledger_ref.get(order_id, [])
        assert linked, f"no MatchRecord covers ground-truth event {order_id}"
        event_status = min((r.status for r in linked), key=lambda s: STATUS_PRIORITY[s])
        label = row["edge_case_label"]
        counts = label_outcomes.setdefault(
            label, {"auto_matched": 0, "needs_review": 0, "exception": 0}
        )
        counts[event_status] += 1

    print("\n=== Matching pipeline summary (86-event batch, seed 42) ===")
    print(
        f"match_rate={stats['match_rate']:.4f}  "
        f"auto={stats['auto_matched_count']}  review={stats['review_count']}  "
        f"exceptions={stats['exception_count']}  time={stats['processing_time_ms']}ms"
    )
    print(f"{'edge case':<16}{'auto':>6}{'review':>8}{'exception':>11}")
    for label in sorted(label_outcomes):
        counts = label_outcomes[label]
        print(
            f"{label:<16}{counts['auto_matched']:>6}{counts['needs_review']:>8}"
            f"{counts['exception']:>11}"
        )
