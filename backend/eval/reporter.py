"""Markdown report generator — the buildathon proof-of-work artifact.

Section order and content follow the build doc's "What to report" (Section 6)
and the evaluation bar, including the mandatory honest exception list.
"""

from __future__ import annotations

from datetime import datetime

from backend.eval.harness import EvalMetrics


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def generate_markdown_report(metrics: EvalMetrics, seed: int = 42) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []

    lines.append("# ReconLoop — Evaluation Report")
    lines.append("")
    lines.append(
        f"**Generated:** {generated_at} &nbsp;|&nbsp; **Seed:** {seed} "
        f"&nbsp;|&nbsp; **Batch:** {metrics.total_events} labeled events"
    )
    lines.append("")
    lines.append("## 1. Executive Summary")
    lines.append("")
    lines.append(
        "ReconLoop closed one full finance-ops reconciliation loop on a held-out "
        "labeled batch: ingestion of three heterogeneous sources, tiered matching, "
        "and honest exception reporting — with every decision written to an "
        "immutable audit trail."
    )
    lines.append("")
    lines.append(f"**Overall auto-match rate: {_pct(metrics.match_rate)}**")
    lines.append("")
    lines.append("## 2. Throughput")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Batch size | {metrics.total_events} events |")
    lines.append(f"| Processing time | {metrics.processing_time_ms:.1f} ms |")
    lines.append(f"| Throughput | {metrics.records_per_second:,.0f} events/sec |")
    lines.append("")
    lines.append("## 3. Match Rate Breakdown")
    lines.append("")
    lines.append("| Bucket | Events | % of batch |")
    lines.append("|---|---|---|")
    lines.append(
        f"| Auto-matched | {metrics.auto_matched_count} | {_pct(metrics.match_rate)} |"
    )
    lines.append(
        f"| Needs review | {metrics.review_count} | {_pct(metrics.review_rate)} |"
    )
    lines.append(
        f"| Exception | {metrics.exception_count} | {_pct(metrics.exception_rate)} |"
    )
    lines.append("")
    lines.append("## 4. Edge-Case Performance")
    lines.append("")
    lines.append(
        "| Category | Total | Auto | Review | Exception | Expected | Accuracy |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    totals = {"total": 0, "auto": 0, "review": 0, "exception": 0, "correct": 0}
    for label in sorted(metrics.per_category):
        category = metrics.per_category[label]
        totals["total"] += category.total
        totals["auto"] += category.auto_matched
        totals["review"] += category.needs_review
        totals["exception"] += category.exception
        totals["correct"] += category.correctly_routed
        lines.append(
            f"| {label} | {category.total} | {category.auto_matched} | "
            f"{category.needs_review} | {category.exception} | "
            f"{category.expected_status} | {_pct(category.accuracy)} |"
        )
    overall_accuracy = totals["correct"] / totals["total"] if totals["total"] else 0.0
    lines.append(
        f"| **Total** | **{totals['total']}** | **{totals['auto']}** | "
        f"**{totals['review']}** | **{totals['exception']}** | — | "
        f"**{_pct(overall_accuracy)}** |"
    )
    lines.append("")
    lines.append("## 5. Routing Accuracy")
    lines.append("")
    lines.append(
        f"**{_pct(metrics.correctly_routed_rate)}** of events "
        f"({metrics.correctly_routed}/{metrics.total_events}) landed in the "
        "pipeline bucket expected by the ground truth."
    )
    lines.append("")
    lines.append("## 6. Honest Exception List")
    lines.append("")
    lines.append(
        "Every record the system could not resolve, with the rule that fired and "
        "the stated reason. Shown, not hidden."
    )
    lines.append("")
    if metrics.honest_exceptions:
        for index, exc in enumerate(metrics.honest_exceptions, start=1):
            reason = exc.get("details", {}).get("reason", "no reason recorded")
            txn_ids = ", ".join(exc.get("txn_ids", []))
            lines.append(
                f"{index}. `{txn_ids}` — rule `{exc.get('rule_or_model', 'unknown')}` — reason: {reason}"
            )
            explanation = (exc.get("explanation") or "").strip()
            if explanation:
                lines.append(f"   Explanation: {explanation}")
    else:
        lines.append("No unresolved exceptions.")
    lines.append("")
    lines.append("## 7. Methodology")
    lines.append("")
    lines.append(
        "Metrics are computed against a held-out labeled batch generated with "
        "known ground truth (seeded, deliberately injected edge cases) — not "
        "self-reported. Ground truth was fixed before the pipeline ever ran; "
        "per-category accuracy and the exception list above are measured, not claimed."
    )
    lines.append("")
    return "\n".join(lines)
