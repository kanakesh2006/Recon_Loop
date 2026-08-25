import csv
import importlib.util
from pathlib import Path

from backend.eval.harness import evaluate_pipeline
from backend.eval.reporter import generate_markdown_report
from backend.matching.pipeline import run_matching_pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = PROJECT_ROOT / "data" / "generate_synthetic.py"

_spec = importlib.util.spec_from_file_location("generate_synthetic", GENERATOR_PATH)
generate_synthetic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(generate_synthetic)


def test_full_eval_pipeline_on_generated_batch(tmp_path):
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
    metrics = evaluate_pipeline(result, str(out_dir / "ground_truth.csv"))

    assert metrics.total_events == 86
    assert metrics.match_rate >= 0.80
    assert metrics.correctly_routed_rate >= 0.90

    with open(out_dir / "ground_truth.csv", newline="", encoding="utf-8") as handle:
        gt_labels = {row["edge_case_label"] for row in csv.DictReader(handle)}
    assert gt_labels == set(metrics.per_category)

    assert isinstance(metrics.honest_exceptions, list)
    assert metrics.records_per_second > 0
    assert metrics.processing_time_ms > 0

    for category in metrics.per_category.values():
        assert 0.0 <= category.accuracy <= 1.0
        assert category.total == (
            category.auto_matched + category.needs_review + category.exception
        )

    report = generate_markdown_report(metrics, seed=42)
    assert isinstance(report, str)
    assert len(report) > 0
    assert "# ReconLoop" in report
    assert "Honest Exception List" in report

    print("\n=== Per-category accuracy (86-event batch, seed 42) ===")
    print(
        f"match_rate={metrics.match_rate:.4f}  correctly_routed={metrics.correctly_routed_rate:.4f}"
    )
    print(
        f"{'category':<16}{'total':>6}{'auto':>6}{'review':>8}{'exc':>5}{'accuracy':>10}"
    )
    for label in sorted(metrics.per_category):
        category = metrics.per_category[label]
        print(
            f"{label:<16}{category.total:>6}{category.auto_matched:>6}"
            f"{category.needs_review:>8}{category.exception:>5}{category.accuracy:>10.1%}"
        )
