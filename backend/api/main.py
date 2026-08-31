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
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str


class UploadConfig(BaseModel):
    ledger: str | None = None
    settlement: str | None = None
    bank: str | None = None


class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str


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


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint for monitoring and load balancers."""
    from datetime import datetime, timezone
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


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


# --- Custom Document Upload & Processing ---

# In-memory job storage (in production, use Redis or database)
_jobs: dict[str, dict[str, Any]] = {}


def _detect_csv_type(headers: list[str]) -> str | None:
    """Auto-detect CSV type based on column headers."""
    headers_lower = [h.lower().strip() for h in headers]
    
    # Ledger indicators
    if "order_id" in headers_lower and "customer_name" in headers_lower:
        return "ledger"
    
    # Settlement indicators
    if "settlement_id" in headers_lower and "txn_ref" in headers_lower:
        return "settlement"
    
    # Bank statement indicators
    if "reference_no" in headers_lower and ("debit" in headers_lower or "credit" in headers_lower):
        return "bank"
    
    return None


def _parse_csv_preview(file_content: bytes) -> tuple[list[str], list[list[str]]]:
    """Parse CSV and return headers and first few rows."""
    import csv
    import io
    
    text = file_content.decode("utf-8")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return [], []
    headers = rows[0]
    preview_rows = rows[1:6]  # First 5 data rows
    return headers, preview_rows


@app.post("/api/upload/preview")
async def preview_upload(
    files: list[UploadFile] = File(...),
):
    """Preview uploaded files with auto-detected categories."""
    results = []
    for file in files:
        content = await file.read()
        headers, preview_rows = _parse_csv_preview(content)
        detected_type = _detect_csv_type(headers)
        
        results.append({
            "filename": file.filename,
            "detected_type": detected_type,
            "headers": headers,
            "preview_rows": preview_rows,
            "size": len(content),
        })
    
    return {"files": results}



@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get job status and progress."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "job_id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
        "result": job["result"],
        "error": job["error"],
    }


@app.get("/api/jobs/{job_id}/stream")
async def stream_job_progress(job_id: str):
    """Server-Sent Events stream for real-time job progress."""
    from asyncio import sleep
    import json
    
    async def event_generator():
        while True:
            job = _jobs.get(job_id)
            if not job:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                break
            
            yield f"data: {json.dumps({'progress': job['progress'], 'message': job['message'], 'status': job['status'], 'result': job.get('result')})}\n\n"
            
            if job["status"] in ("completed", "failed"):
                break
            
            await sleep(0.5)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


async def _process_job(job_id: str):
    """Background job processor."""
    import asyncio
    import os
    import tempfile
    import shutil
    from backend.matching.pipeline import run_matching_pipeline
    from backend.agents.explainer import ExceptionExplainer, DEGRADED_MESSAGE
    from backend.audit.supabase_client import AuditLogger
    
    job = _jobs.get(job_id)
    if not job:
        return
    
    job["status"] = "processing"
    job["progress"] = 10
    job["message"] = "Loading documents..."
    
    files_data = job.get("files", {})
    temp_dir = tempfile.mkdtemp()
    
    try:
        paths = {}
        for key in ["ledger", "settlement", "bank"]:
            if key in files_data:
                content = files_data[key]["content"]
                path = os.path.join(temp_dir, f"{key}.csv")
                with open(path, "wb") as f:
                    f.write(content)
                paths[key] = path
            else:
                raise ValueError(f"Missing required file: {key}")
                
        await asyncio.sleep(0.1)
        job["progress"] = 30
        job["message"] = "Normalizing and running reconciliation..."
        
        # Run matching pipeline
        result = run_matching_pipeline(paths["ledger"], paths["settlement"], paths["bank"])
        
        await asyncio.sleep(0.1)
        job["progress"] = 70
        job["message"] = "Generating explanations..."
        
        if result.exceptions:
            explainer = ExceptionExplainer()
            if explainer.available:
                for record in result.exceptions:
                    record.explanation = explainer.explain_exception(record)
            else:
                for record in result.exceptions:
                    record.explanation = DEGRADED_MESSAGE
                    
        await asyncio.sleep(0.1)
        job["progress"] = 90
        job["message"] = "Auditing results..."
        
        # Push to Supabase
        audit_logger = AuditLogger()
        if audit_logger.is_connected:
            run_id = audit_logger.create_run(result.stats)
            all_records = result.auto_matched + result.needs_review + result.exceptions
            audit_logger.write_batch(all_records, run_id=run_id)
            
        # Recompute event-level match rate to match the dashboard
        total_events = 0
        auto_events = 0
        all_recs = result.auto_matched + result.needs_review + result.exceptions
        for record in all_recs:
            ledger_count = sum(1 for tx in record.txn_ids if tx.startswith("led_order_"))
            total_events += ledger_count
            if record.status == "auto_matched":
                auto_events += ledger_count
                
        event_match_rate = auto_events / total_events if total_events > 0 else 0.0
            
        job["progress"] = 100
        job["status"] = "completed"
        job["message"] = "Processing complete!"
        job["result"] = {
            "match_rate": event_match_rate,
            "total_events": total_events,
            "auto_matched": auto_events,
            "needs_review": result.stats["review_count"],
            "exceptions": result.stats["exception_count"],
        }
    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        job["message"] = f"Processing failed: {exc}"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# Start background processing when job is created
@app.post("/api/process/start")
async def start_processing(
    ledger_file: UploadFile = File(None),
    settlement_file: UploadFile = File(None),
    bank_file: UploadFile = File(None),
    config: str = Form("{}"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    import uuid
    import json
    
    try:
        config_data = json.loads(config)
    except json.JSONDecodeError:
        config_data = {}
    
    job_id = str(uuid.uuid4())[:8]
    
    files_data = {}
    for field_name, file in [("ledger", ledger_file), ("settlement", settlement_file), ("bank", bank_file)]:
        if file and file.filename:
            content = await file.read()
            if content:
                files_data[field_name] = {
                    "filename": file.filename,
                    "content": content,
                }
    
    _jobs[job_id] = {
        "id": job_id,
        "status": "pending",
        "progress": 0,
        "message": "Initializing...",
        "files": files_data,
        "config": config_data,
        "result": None,
        "error": None,
    }
    
    # Start background processing
    if background_tasks:
        background_tasks.add_task(_process_job, job_id)
    
    return JobResponse(
        job_id=job_id,
        status="pending",
        message="Job queued for processing",
    )
