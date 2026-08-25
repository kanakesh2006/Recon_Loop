"""Supabase audit client.

Writes every pipeline run and MatchRecord to the recon_runs / audit_log tables
(docs/schema.sql). Graceful offline mode: missing credentials, client
initialization failures, or insert failures log a warning and no-op — the
audit logger must never crash the pipeline.
"""

from __future__ import annotations

import json
import logging
import os

from dotenv import load_dotenv
from supabase import Client, create_client

from backend.matching.match_record import MatchRecord

logger = logging.getLogger(__name__)


class AuditLogger:
    def __init__(self, url: str | None = None, key: str | None = None):
        load_dotenv()
        resolved_url = (url or os.getenv("SUPABASE_URL", "") or "").strip()
        resolved_key = (key or os.getenv("SUPABASE_KEY", "") or "").strip()
        self.client: Client | None = None
        if not resolved_url or not resolved_key:
            logger.warning(
                "SUPABASE_URL/SUPABASE_KEY not configured - audit log running in offline mode"
            )
            return
        try:
            self.client = create_client(resolved_url, resolved_key)
        except Exception as exc:
            logger.warning(
                "Supabase client initialization failed (%s) - audit log offline", exc
            )
            self.client = None

    @property
    def is_connected(self) -> bool:
        return self.client is not None

    def create_run(self, stats: dict, seed: int | None = None) -> str | None:
        """Insert a recon_runs row; returns the generated run_id or None."""
        if not self.client:
            return None
        row = {
            "seed": seed,
            "total_events": int(stats.get("total_events", 0) or 0),
            "auto_matched_count": int(stats.get("auto_matched_count", 0) or 0),
            "review_count": int(stats.get("review_count", 0) or 0),
            "exception_count": int(stats.get("exception_count", 0) or 0),
            "match_rate": float(stats.get("match_rate", 0.0) or 0.0),
            "processing_time_ms": float(stats.get("processing_time_ms", 0.0) or 0.0),
        }
        try:
            response = self.client.table("recon_runs").insert(row).execute()
            data = getattr(response, "data", None)
            if isinstance(data, list) and data:
                return data[0].get("run_id")
            return None
        except Exception as exc:
            logger.warning("Failed to insert recon_runs row: %s", exc)
            return None

    def write_batch(self, records: list[MatchRecord], run_id: str | None = None) -> int:
        """Bulk-insert MatchRecords into audit_log; returns count written (0 on failure)."""
        if not self.client or not records:
            return 0
        rows = [self._to_row(record, run_id) for record in records]
        try:
            self.client.table("audit_log").insert(rows).execute()
            return len(rows)
        except Exception as exc:
            logger.warning("Failed to insert audit_log batch: %s", exc)
            return 0

    @staticmethod
    def _to_row(record: MatchRecord, run_id: str | None) -> dict:
        return {
            "match_id": record.match_id,
            "run_id": run_id,
            "txn_ids": list(record.txn_ids),
            "match_stage": record.match_stage,
            "confidence_score": float(record.confidence_score),
            "status": record.status,
            "rule_or_model": record.rule_or_model,
            "matched_at": record.timestamp.isoformat(),
            "explanation": record.explanation,
            "details": json.dumps(record.details, default=str),
        }
