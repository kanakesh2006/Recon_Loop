"""MatchRecord — the audit-log-ready record of every matching decision."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

MatchStage = Literal["exact", "fuzzy", "unmatched"]
MatchStatus = Literal["auto_matched", "needs_review", "exception"]


class MatchRecord(BaseModel):
    match_id: str
    txn_ids: list[str]
    match_stage: MatchStage
    confidence_score: float
    status: MatchStatus
    rule_or_model: str
    timestamp: datetime
    explanation: str = ""
    details: dict = Field(default_factory=dict)


def build_match_record(
    txn_ids: list[str],
    match_stage: MatchStage,
    confidence_score: float,
    rule_or_model: str,
    status: MatchStatus = "auto_matched",
    details: dict | None = None,
) -> MatchRecord:
    return MatchRecord(
        match_id=str(uuid4()),
        txn_ids=list(txn_ids),
        match_stage=match_stage,
        confidence_score=float(confidence_score),
        status=status,
        rule_or_model=rule_or_model,
        timestamp=datetime.now(timezone.utc),
        details=details or {},
    )
