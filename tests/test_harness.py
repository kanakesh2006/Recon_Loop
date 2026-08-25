from pathlib import Path

from backend.eval.harness import evaluate_pipeline
from backend.matching.match_record import build_match_record
from backend.matching.pipeline import MatchingResult

GROUND_TRUTH = """order_id,settlement_id,bank_reference,expected_match_status,edge_case_label,notes
order_1,setl_1,NEFT/U1/RZPPAYOUT,matched,clean_match,regular sale
order_2,,,pending,pending,no settlement yet
order_3,setl_3,REV/U3/CHARGEBACK,exception,chargeback,reversal entry
order_4,setl_4,NEFT/U4/RZPPAYOUT,matched,duplicate_id,entered twice
order_5,setl_5,NEFT/U5/RZPPAYOUT,matched,clean_match,regular sale
order_6,setl_6,REV/U6/CHARGEBACK,chargeback,chargeback,reversal entry
"""


def _record(txn_ids, status, rule="test_rule", details=None):
    record = build_match_record(
        txn_ids=txn_ids,
        match_stage="exact" if status == "auto_matched" else "unmatched",
        confidence_score=1.0 if status == "auto_matched" else 0.0,
        rule_or_model=rule,
        status=status,
        details=details or {},
    )
    record.status = status
    return record


def _matching_result():
    return MatchingResult(
        auto_matched=[
            _record(["led_order_1", "stl_setl_1", "bnk_cr_U1"], "auto_matched"),
            _record(["led_order_4", "stl_setl_4"], "auto_matched"),
        ],
        needs_review=[
            _record(["led_order_2"], "needs_review", rule="pending_order"),
            _record(["led_order_4#2"], "needs_review", rule="possible_duplicate"),
            _record(
                ["led_order_6", "stl_setl_6"],
                "needs_review",
                rule="exact_settlement_bank_utr",
            ),
        ],
        exceptions=[
            _record(
                ["led_order_3"],
                "exception",
                rule="no_match_found",
                details={"reason": "no settlement or bank counterpart resolved"},
            )
        ],
        stats={"total_events": 6, "processing_time_ms": 1000.0},
    )


def test_evaluate_pipeline_metrics(tmp_path: Path):
    gt_path = tmp_path / "ground_truth.csv"
    gt_path.write_text(GROUND_TRUTH, encoding="utf-8")

    metrics = evaluate_pipeline(_matching_result(), str(gt_path))

    assert metrics.total_events == 6
    assert metrics.auto_matched_count == 2
    assert metrics.review_count == 2
    assert metrics.exception_count == 2
    assert metrics.match_rate == round(2 / 6, 4)
    assert metrics.review_rate == round(2 / 6, 4)
    assert metrics.exception_rate == round(2 / 6, 4)
    assert metrics.processing_time_ms == 1000.0
    assert metrics.records_per_second == 6.0


def test_correctly_routed_including_dual_accept_buckets(tmp_path: Path):
    gt_path = tmp_path / "ground_truth.csv"
    gt_path.write_text(GROUND_TRUTH, encoding="utf-8")

    metrics = evaluate_pipeline(_matching_result(), str(gt_path))

    assert metrics.correctly_routed == 5
    assert metrics.correctly_routed_rate == round(5 / 6, 4)


def test_per_category_accuracy(tmp_path: Path):
    gt_path = tmp_path / "ground_truth.csv"
    gt_path.write_text(GROUND_TRUTH, encoding="utf-8")

    metrics = evaluate_pipeline(_matching_result(), str(gt_path))

    assert set(metrics.per_category) == {
        "clean_match",
        "pending",
        "chargeback",
        "duplicate_id",
    }
    clean = metrics.per_category["clean_match"]
    assert clean.total == 2
    assert clean.auto_matched == 1
    assert clean.exception == 1
    assert clean.accuracy == 0.5
    assert metrics.per_category["pending"].accuracy == 1.0
    assert metrics.per_category["pending"].expected_status == "pending"
    assert metrics.per_category["duplicate_id"].accuracy == 1.0
    chargeback = metrics.per_category["chargeback"]
    assert chargeback.total == 2
    assert chargeback.correctly_routed == 2
    assert chargeback.accuracy == 1.0


def test_missing_order_counts_as_exception(tmp_path: Path):
    gt_path = tmp_path / "ground_truth.csv"
    gt_path.write_text(GROUND_TRUTH, encoding="utf-8")

    metrics = evaluate_pipeline(_matching_result(), str(gt_path))

    clean = metrics.per_category["clean_match"]
    assert clean.exception == 1
    assert clean.correctly_routed == 1


def test_honest_exceptions_shape(tmp_path: Path):
    gt_path = tmp_path / "ground_truth.csv"
    gt_path.write_text(GROUND_TRUTH, encoding="utf-8")

    metrics = evaluate_pipeline(_matching_result(), str(gt_path))

    assert len(metrics.honest_exceptions) == 1
    entry = metrics.honest_exceptions[0]
    assert entry["txn_ids"] == ["led_order_3"]
    assert entry["rule_or_model"] == "no_match_found"
    assert entry["details"]["reason"] == "no settlement or bank counterpart resolved"


def test_duplicate_best_status_is_auto(tmp_path: Path):
    gt_path = tmp_path / "ground_truth.csv"
    gt_path.write_text(GROUND_TRUTH, encoding="utf-8")

    metrics = evaluate_pipeline(_matching_result(), str(gt_path))

    duplicate = metrics.per_category["duplicate_id"]
    assert duplicate.auto_matched == 1
    assert duplicate.needs_review == 0
