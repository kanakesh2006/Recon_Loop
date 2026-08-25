const API_BASE: string =
  import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export interface RunStats {
  run_id: string | null;
  started_at: string | null;
  seed: number | null;
  total_events: number | null;
  auto_matched_count: number | null;
  review_count: number | null;
  exception_count: number | null;
  match_rate: number | null;
  processing_time_ms: number | null;
}

export interface ExceptionRecord {
  match_id: string;
  txn_ids: string[];
  match_stage: string;
  confidence_score: number;
  status: string;
  rule_or_model: string;
  matched_at: string;
  explanation: string;
  details: Record<string, unknown>;
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (body && typeof body.detail === "string") return body.detail;
  } catch {
    /* fall through */
  }
  return `Request failed (HTTP ${res.status})`;
}

export async function fetchStats(): Promise<RunStats> {
  const res = await fetch(`${API_BASE}/api/stats`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchExceptions(): Promise<ExceptionRecord[]> {
  const res = await fetch(`${API_BASE}/api/exceptions`);
  if (!res.ok) throw new Error(await parseError(res));
  const body = await res.json();
  return body.exceptions as ExceptionRecord[];
}

export async function sendChatMessage(message: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const body = await res.json();
  return body.reply as string;
}
