const API_BASE: string = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

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

export interface JobStatus {
  job_id: string;
  status: string;
  progress: number;
  message: string;
  result?: Record<string, unknown>;
  error?: string;
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

export async function uploadFiles(files: Record<string, File>): Promise<{ job_id: string }> {
  const formData = new FormData();
  
  Object.entries(files).forEach(([key, file]) => {
    formData.append(`${key}_file`, file);
  });
  
  const res = await fetch(`${API_BASE}/api/process/start`, {
    method: "POST",
    body: formData,
  });
  
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function pollJobStatus(jobId: string): Promise<{ 
  job_id: string;
  status: string;
  progress: number;
  message: string;
  result?: Record<string, unknown>;
  error?: string;
}> {
  const res = await fetch(`${API_BASE}/api/jobs/${jobId}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function streamJobProgress(
  jobId: string,
  onProgress: (data: { progress: number; message: string; status: string }) => void,
  onComplete: (data: { progress: number; message: string; status: string }) => void,
  onError: (error: Error) => void
): Promise<() => void> {
  const eventSource = new EventSource(`${API_BASE}/api/jobs/${jobId}/stream`);
  
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.error) {
        onError(new Error(data.error));
        eventSource.close();
        return;
      }
      
      onProgress(data);
      
      if (data.status === "completed" || data.status === "failed") {
        onComplete(data);
        eventSource.close();
      }
    } catch (err) {
      onError(err instanceof Error ? err : new Error("Failed to parse SSE data"));
      eventSource.close();
    }
  };
  
  eventSource.onerror = () => {
    eventSource.close();
    onError(new Error("SSE connection lost"));
  };
  
  return () => eventSource.close();
}

export async function checkHealth(): Promise<{ status: string; version: string; timestamp: string }> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export function formatMatchRate(rate: number | null): string {
  if (rate === null) return "—";
  return `${(rate * 100).toFixed(1)}%`;
}