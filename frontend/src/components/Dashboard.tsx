import { useCallback, useEffect, useState } from "react";
import { fetchExceptions, fetchStats, type ExceptionRecord, type RunStats } from "../api";
import CopilotChat from "./CopilotChat";

function throughput(stats: RunStats | null): string {
  if (!stats?.total_events || !stats?.processing_time_ms) return "—";
  const perSecond = stats.total_events / (stats.processing_time_ms / 1000);
  return `${Math.round(perSecond).toLocaleString()}/s`;
}

function StatCard({
  label,
  value,
  sub,
  accent,
  delay,
}: {
  label: string;
  value: string;
  sub: string;
  accent: string;
  delay: number;
}) {
  return (
    <div
      className="animate-fade-up card transition-all duration-300 hover:border-accent/50 hover:shadow-lg hover:shadow-accent/10"
      style={{ animationDelay: `${delay}ms` }}
    >
      <p className="text-xs font-semibold tracking-widest text-muted uppercase">{label}</p>
      <p className={`mt-2 text-4xl font-black tracking-tight ${accent}`}>{value}</p>
      <p className="mt-1 text-xs text-muted">{sub}</p>
    </div>
  );
}

function StatsPanel() {
  const [stats, setStats] = useState<RunStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    fetchStats()
      .then(setStats)
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(load, [load]);

  if (error) {
    return (
      <div className="animate-fade-up card border-rose-400/30 bg-rose-50/50 dark:bg-rose-950/20 p-5 text-sm text-rose-700 dark:text-rose-300">
        <p className="font-semibold">Could not load run stats</p>
        <p className="mt-1 text-rose-300/80 dark:text-rose-400">{error}</p>
        <button
          onClick={load}
          className="mt-3 rounded-lg border border-rose-400/40 px-3 py-1.5 text-xs font-semibold text-rose-100 transition hover:bg-rose-100/20 dark:hover:bg-rose-900/20"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-28 animate-pulse card" />
        ))}
      </div>
    );
  }

  const matchPct = stats.match_rate !== null ? `${(stats.match_rate * 100).toFixed(1)}%` : "—";

  return (
    <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
      <StatCard
        label="Auto-Match Rate"
        value={matchPct}
        sub={`${stats.auto_matched_count ?? "—"} of ${stats.total_events ?? "—"} events (seed ${stats.seed ?? "—"})`}
        accent="stat-value"
        delay={0}
      />
      <StatCard
        label="Needs Review"
        value={String(stats.review_count ?? "—")}
        sub="flagged for a human"
        accent="stat-value-amber"
        delay={70}
      />
      <StatCard
        label="Exceptions"
        value={String(stats.exception_count ?? "—")}
        sub="honest unresolved breaks"
        accent="stat-value-rose"
        delay={140}
      />
      <StatCard
        label="Throughput"
        value={throughput(stats)}
        sub={`${stats.processing_time_ms ?? "—"} ms for ${stats.total_events ?? "—"} events`}
        accent="stat-value-indigo"
        delay={210}
      />
    </div>
  );
}

function reasonOf(record: ExceptionRecord): string {
  const reason = record.details?.reason;
  return typeof reason === "string" ? reason : "No reason recorded";
}

function formatRule(rule: string): string {
  return rule.split("_").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}

function ExceptionCard({ record, index }: { record: ExceptionRecord; index: number }) {
  const isReview = record.status === "needs_review";
  const badgeClass = isReview ? "badge-review" : "badge-exception";
  const hoverClass = isReview 
    ? "hover:border-amber-400/30 hover:shadow-amber-500/10" 
    : "hover:border-rose-400/30 hover:shadow-rose-500/10";

  return (
    <div
      className={`animate-fade-up card transition-all duration-300 hover:shadow-lg ${hoverClass}`}
      style={{ animationDelay: `${index * 80}ms` }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className={`badge ${badgeClass}`}>
          {isReview ? "Needs Review" : "Exception"}
        </span>
        <span className="badge badge-info font-mono text-xs">
          {formatRule(record.rule_or_model)}
        </span>
        <span className="ml-auto text-[11px] text-muted font-medium uppercase tracking-wider">
          Stage: {record.match_stage}
        </span>
      </div>
      <p className="mt-3 font-mono text-sm break-all text-brown/80 dark:text-cream/80">
        {record.txn_ids.join(", ")}
      </p>
      <p className="mt-2 text-xs text-muted">{reasonOf(record)}</p>
      {record.explanation ? (
        <div className="mt-3 rounded-xl border border-brown/20 bg-brown/10 p-3">
          <div className="flex items-center justify-between mb-1">
            <p className="text-[11px] font-bold tracking-widest text-brown-lighter uppercase">
              Copilot explanation
            </p>
            {record.explanation_confidence !== undefined && record.explanation_confidence !== null && (
              <span className="text-[10px] font-bold tracking-wider text-amber-600 dark:text-amber-400">
                AI Confidence: {(record.explanation_confidence * 100).toFixed(0)}%
              </span>
            )}
          </div>
          <p className="text-sm leading-relaxed text-brown font-medium">{record.explanation}</p>
        </div>
      ) : (
        <p className="mt-3 text-xs text-muted italic">
          Explanation pending — rerun with the LLM explainer enabled.
        </p>
      )}
    </div>
  );
}

function ExceptionsQueue() {
  const [records, setRecords] = useState<ExceptionRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    fetchExceptions()
      .then(setRecords)
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(load, [load]);

  return (
    <section className="animate-fade-up" style={{ animationDelay: "260ms" }}>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-bold text-brown dark:text-cream">Exception & Review Queue</h2>
        <button
          onClick={load}
          className="btn-secondary"
        >
          Refresh
        </button>
      </div>

      {error ? (
        <div className="card border-rose-400/30 bg-rose-50/50 dark:bg-rose-950/20 p-5 text-sm text-rose-700 dark:text-rose-300">
          <p className="font-semibold">Could not load exceptions</p>
          <p className="mt-1 text-rose-300/80 dark:text-rose-400">{error}</p>
        </div>
      ) : records === null ? (
        <div className="space-y-3">
          {[0, 1].map((i) => (
            <div key={i} className="h-36 animate-pulse card" />
          ))}
        </div>
      ) : records.length === 0 ? (
        <div className="card border-emerald-400/30 bg-emerald-50/50 dark:bg-emerald-950/20 p-5 text-sm text-emerald-700 dark:text-emerald-300">
          No unresolved exceptions in the latest run.
        </div>
      ) : (
        <div className="space-y-3">
          {records.map((record, index) => (
            <ExceptionCard key={record.match_id} record={record} index={index} />
          ))}
        </div>
      )}
    </section>
  );
}

export default function Dashboard() {
  return (
    <div className="lg:grid lg:grid-cols-3 lg:gap-6 space-y-6 lg:space-y-0 items-start">
      <div className="lg:col-span-2 space-y-6">
        <StatsPanel />
        <ExceptionsQueue />
      </div>
      <div className="lg:col-span-1 sticky top-24 h-[calc(100vh-8rem)] min-h-[500px]">
        <CopilotChat />
      </div>
    </div>
  );
}