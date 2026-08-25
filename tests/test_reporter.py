from backend.eval.harness import CategoryResult, EvalMetrics
from backend.eval.reporter import generate_markdown_report


def _metrics(honest_exceptions=None):
    per_category = {
        "bundled_match": CategoryResult("bundled_match", 6, 6, 0, 0, "matched", 6, 1.0),
        "chargeback": CategoryResult("chargeback", 2, 0, 0, 2, "exception", 2, 1.0),
        "clean_match": CategoryResult("clean_match", 60, 60, 0, 0, "matched", 60, 1.0),
    }
    return EvalMetrics(
        total_events=68,
        auto_matched_count=66,
        review_count=0,
        exception_count=2,
        match_rate=0.9706,
        review_rate=0.0,
        exception_rate=0.0294,
        processing_time_ms=12.5,
        records_per_second=5440.0,
        per_category=per_category,
        correctly_routed=68,
        correctly_routed_rate=1.0,
        honest_exceptions=(
            honest_exceptions
            if honest_exceptions is not None
            else [
                {
                    "txn_ids": ["led_order_a"],
                    "rule_or_model": "no_match_found",
                    "details": {"reason": "no settlement or bank counterpart resolved"},
                }
            ]
        ),
    )


def test_contains_all_eight_sections():
    report = generate_markdown_report(_metrics(), seed=42)

    assert report.startswith("# ReconLoop — Evaluation Report")
    for section in (
        "## 1. Executive Summary",
        "## 2. Throughput",
        "## 3. Match Rate Breakdown",
        "## 4. Edge-Case Performance",
        "## 5. Routing Accuracy",
        "## 6. Honest Exception List",
        "## 7. Methodology",
    ):
        assert section in report
    assert "Seed:** 42" in report


def test_summary_numbers_present():
    report = generate_markdown_report(_metrics())

    assert "97.1%" in report
    assert "5,440" in report
    assert "12.5 ms" in report


def test_edge_case_table_sorted_with_total_row():
    report = generate_markdown_report(_metrics())
    lines = report.splitlines()

    table_lines = [line for line in lines if line.startswith("|")]
    assert any("|---|" in line for line in table_lines)
    labels = [line.split("|")[1].strip() for line in table_lines]
    assert (
        labels.index("bundled_match")
        < labels.index("chargeback")
        < labels.index("clean_match")
    )
    assert "| **Total** | **68** | **66** | **0** | **2** |" in report
    assert "| clean_match | 60 | 60 | 0 | 0 | matched | 100.0% |" in report


def test_honest_exception_list_shows_entries():
    report = generate_markdown_report(_metrics())

    assert "`led_order_a`" in report
    assert "`no_match_found`" in report
    assert "no settlement or bank counterpart resolved" in report


def test_honest_exception_list_present_even_when_empty():
    report = generate_markdown_report(_metrics(honest_exceptions=[]))

    assert "## 6. Honest Exception List" in report
    assert "No unresolved exceptions." in report


def test_methodology_mentions_held_out_batch():
    report = generate_markdown_report(_metrics())

    assert "held-out labeled batch" in report
    assert "ground truth" in report
