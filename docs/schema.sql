-- ReconLoop — Supabase (Postgres) schema
-- Paste into the Supabase SQL editor. Idempotent: safe to re-run.

-- One row per pipeline execution.
CREATE TABLE IF NOT EXISTS recon_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    seed INTEGER,
    total_events INTEGER NOT NULL,
    auto_matched_count INTEGER NOT NULL,
    review_count INTEGER NOT NULL,
    exception_count INTEGER NOT NULL,
    match_rate NUMERIC(5,4) NOT NULL,
    processing_time_ms NUMERIC(10,2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per MatchRecord (every match/no-match decision).
CREATE TABLE IF NOT EXISTS audit_log (
    match_id UUID PRIMARY KEY,
    run_id UUID REFERENCES recon_runs(run_id),
    txn_ids TEXT[] NOT NULL,
    match_stage TEXT NOT NULL CHECK (match_stage IN ('exact', 'fuzzy', 'unmatched')),
    confidence_score NUMERIC(4,3) NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('auto_matched', 'needs_review', 'exception')),
    rule_or_model TEXT NOT NULL,
    matched_at TIMESTAMPTZ NOT NULL,
    explanation TEXT DEFAULT '',
    details JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_run_id ON audit_log (run_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_status ON audit_log (status);
CREATE INDEX IF NOT EXISTS idx_audit_log_txn_ids ON audit_log USING GIN (txn_ids);
