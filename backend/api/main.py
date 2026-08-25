"""ReconLoop FastAPI backend.

Serves dashboard data from the Supabase audit trail (latest run stats +
exception queue with LLM explanations) and the Q&A Copilot. Graceful
degradation: unconfigured Supabase returns 503 with a clear message; the
copilot degrades internally when GROQ_API_KEY is missing.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(title="ReconLoop API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_SUPABASE_CLIENT = None
_COPILOT = None


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


class StatsResponse(BaseModel):
    run_id: str | None = None
    started_at: str | None = None
    seed: int | None = None
    total_events: int | None = None
    auto_matched_count: int | None = None
    review_count: int | None = None
    exception_count: int | None = None
    match_rate: float | None = None
    processing_time_ms: float | None = None


def get_supabase():
    global _SUPABASE_CLIENT
    if _SUPABASE_CLIENT is None:
        load_dotenv()
        url = (os.getenv("SUPABASE_URL") or "").strip()
        key = (os.getenv("SUPABASE_KEY") or "").strip()
        if not url or not key:
            raise HTTPException(
                status_code=503,
                detail="Supabase not configured: set SUPABASE_URL and SUPABASE_KEY in .env",
            )
        from supabase import create_client

        _SUPABASE_CLIENT = create_client(url, key)
    return _SUPABASE_CLIENT


def _load_sample_transactions():
    samples = Path(__file__).resolve().parents[2] / "data" / "samples"
    ledger = samples / "internal_ledger.csv"
    settlement = samples / "gateway_settlement.csv"
    bank = samples / "bank_statement.csv"
    if not (ledger.exists() and settlement.exists() and bank.exists()):
        return []
    try:
        from backend.ingestion.bank_mapper import ingest_bank
        from backend.ingestion.ledger_mapper import ingest_ledger
        from backend.ingestion.settlement_mapper import ingest_settlement

        return (
            ingest_ledger(str(ledger))
            + ingest_settlement(str(settlement))
            + ingest_bank(str(bank))
        )
    except Exception as exc:
        logger.warning("Failed to load sample transactions: %s", exc)
        return []


def get_copilot():
    global _COPILOT
    if _COPILOT is None:
        from backend.agents.copilot import CopilotSession
        from backend.agents.tools import set_transaction_index

        transactions = _load_sample_transactions()
        if transactions:
            set_transaction_index(transactions)
        _COPILOT = CopilotSession()
    return _COPILOT


@app.get("/api/stats", response_model=StatsResponse)
def read_stats():
    client = get_supabase()
    try:
        response = (
            client.table("recon_runs")
            .select("*")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Supabase query failed: {exc}")
    rows = getattr(response, "data", None) or []
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No reconciliation runs found. Run backend/eval/run_eval.py first.",
        )
    row = rows[0]

    # Recompute event-level match rate from audit_log (bundled payouts mean 1 record can = multiple events)
    try:
        run_id = row.get("run_id")
        al_res = (
            client.table("audit_log")
            .select("txn_ids")
            .eq("run_id", run_id)
            .eq("status", "auto_matched")
            .execute()
        )
        audit_data = getattr(al_res, "data", None) or []
        auto_matched_events = sum(
            sum(1 for tid in record.get("txn_ids", []) if tid.startswith("led_order_"))
            for record in audit_data
        )
        total_events = row.get("total_events", 1)
        match_rate = (
            auto_matched_events / total_events
            if total_events > 0
            else float(row.get("match_rate", 0))
        )
    except Exception as exc:
        logger.warning(f"Failed to recompute event match rate: {exc}")
        match_rate = (
            float(row["match_rate"]) if row.get("match_rate") is not None else None
        )

    return StatsResponse(
        run_id=row.get("run_id"),
        started_at=str(row.get("started_at")) if row.get("started_at") else None,
        seed=row.get("seed"),
        total_events=row.get("total_events"),
        auto_matched_count=row.get("auto_matched_count"),
        review_count=row.get("review_count"),
        exception_count=row.get("exception_count"),
        match_rate=match_rate,
        processing_time_ms=(
            float(row["processing_time_ms"])
            if row.get("processing_time_ms") is not None
            else None
        ),
    )


@app.get("/api/exceptions")
def read_exceptions():
    client = get_supabase()
    try:
        response = (
            client.table("audit_log")
            .select("*")
            .eq("status", "exception")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Supabase query failed: {exc}")
    return {"exceptions": getattr(response, "data", None) or []}


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="message must not be empty")
    copilot = get_copilot()
    return ChatResponse(reply=copilot.ask(message))
