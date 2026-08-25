"""Evaluation harness — measures the pipeline against the labeled ground truth.

Event-level semantics: every ground-truth event (order_id) is mapped to the
best pipeline status across all MatchRecords covering it (auto_matched >
needs_review > exception). Events with no covering record count as exception.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from backend.matching.match_record import MatchRecord
from backend.matching.pipeline import MatchingResult

STATUS_PRIORITY = {"auto_matched": 0, "needs_review": 1, "exception": 2}
LEDGER_PREFIX = "led_"


@dataclass
class CategoryResult:
    label: str
    total: int
    auto_matched: int
    needs_review: int
    exception: int
    expected_status: str
    correctly_routed: int
    accuracy: float


@dataclass
class EvalMetrics:
    total_events: int
    auto_matched_count: int
    review_count: int
    exception_count: int
    match_rate: float
    review_rate: float
    exception_rate: float
    processing_time_ms: float
    records_per_second: float
    per_category: dict[str, CategoryResult]
    correctly_routed: int
    correctly_routed_rate: float
    honest_exceptions: list[dict] = field(default_factory=list)


def _order_id_from_txn_id(txn_id: str) -> str | None:
    if not txn_id.startswith(LEDGER_PREFIX):
        return None
    return txn_id[len(LEDGER_PREFIX) :].split("#")[0]


def best_status_by_order(records: list[MatchRecord]) -> dict[str, str]:
    best: dict[str, str] = {}
    for record in records:
        for txn_id in record.txn_ids:
            order_id = _order_id_from_txn_id(txn_id)
            if order_id is None:
                continue
            current = best.get(order_id)
            if (
                current is None
                or STATUS_PRIORITY[record.status] < STATUS_PRIORITY[current]
            ):
                best[order_id] = record.status
    return best


def _is_correctly_routed(
    expected_status: str, label: str, pipeline_status: str
) -> bool:
    expected = str(expected_status).strip().lower()
    if expected == "matched":
        if label == "duplicate_id":
            return pipeline_status in ("auto_matched", "needs_review")
        return pipeline_status == "auto_matched"
    if expected == "pending":
        return pipeline_status == "needs_review"
    if expected in ("chargeback", "exception"):
        return pipeline_status in ("exception", "needs_review")
    return False


def evaluate_pipeline(
    matching_result: MatchingResult,
    ground_truth_path: str,
) -> EvalMetrics:
    ground_truth = pd.read_csv(ground_truth_path)
    all_records = (
        matching_result.auto_matched
        + matching_result.needs_review
        + matching_result.exceptions
    )
    best_status = best_status_by_order(all_records)

    rows = []
    for _, gt_row in ground_truth.iterrows():
        order_id = str(gt_row["order_id"])
        expected_status = str(gt_row["expected_match_status"])
        label = str(gt_row["edge_case_label"])
        pipeline_status = best_status.get(order_id, "exception")
        rows.append(
            {
                "order_id": order_id,
                "expected_status": expected_status,
                "label": label,
                "pipeline_status": pipeline_status,
                "correct": _is_correctly_routed(
                    expected_status, label, pipeline_status
                ),
            }
        )
    events = pd.DataFrame(rows)

    total_events = len(events)
    status_counts = events["pipeline_status"].value_counts()
    auto_matched = int(status_counts.get("auto_matched", 0))
    review = int(status_counts.get("needs_review", 0))
    exception = int(status_counts.get("exception", 0))
    correctly_routed = int(events["correct"].sum())

    per_category: dict[str, CategoryResult] = {}
    for label, group in events.groupby("label"):
        label_status_counts = group["pipeline_status"].value_counts()
        label_correct = int(group["correct"].sum())
        label_total = len(group)
        per_category[str(label)] = CategoryResult(
            label=str(label),
            total=label_total,
            auto_matched=int(label_status_counts.get("auto_matched", 0)),
            needs_review=int(label_status_counts.get("needs_review", 0)),
            exception=int(label_status_counts.get("exception", 0)),
            expected_status=str(group["expected_status"].iloc[0]),
            correctly_routed=label_correct,
            accuracy=round(label_correct / label_total, 4) if label_total else 0.0,
        )

    processing_time_ms = float(
        matching_result.stats.get("processing_time_ms", 0.0) or 0.0
    )
    records_per_second = (
        total_events / (processing_time_ms / 1000) if processing_time_ms > 0 else 0.0
    )

    honest_exceptions = [
        {
            "txn_ids": list(record.txn_ids),
            "rule_or_model": record.rule_or_model,
            "details": dict(record.details),
            "explanation": record.explanation,
        }
        for record in matching_result.exceptions
    ]

    def _rate(count: int) -> float:
        return round(count / total_events, 4) if total_events else 0.0

    return EvalMetrics(
        total_events=total_events,
        auto_matched_count=auto_matched,
        review_count=review,
        exception_count=exception,
        match_rate=_rate(auto_matched),
        review_rate=_rate(review),
        exception_rate=_rate(exception),
        processing_time_ms=processing_time_ms,
        records_per_second=round(records_per_second, 2),
        per_category=per_category,
        correctly_routed=correctly_routed,
        correctly_routed_rate=_rate(correctly_routed),
        honest_exceptions=honest_exceptions,
    )
