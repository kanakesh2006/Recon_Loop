import { useCallback, useEffect, useState } from "react";
import {
  fetchExceptions,
  fetchStats,
  type ExceptionRecord,
  type RunStats,
} from "../api";

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
      className="animate-fade-up rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur-xl transition duration-300 hover:border-white/25 hover:bg-white/10"
      style={{ animationDelay: `${delay}ms` }}
    >
      <p className="text-xs font-semibold tracking-widest text-slate-400 uppercase">
        {label}
      </p>
      <p className={`mt-2 text-4xl font-black tracking-tight ${accent}`}>
        {value}
      </p>
      <p className="mt-1 text-xs text-slate-500">{sub}</p>
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
      <div className="animate-fade-up rounded-2xl border border-rose-500/30 bg-rose-500/10 p-5 text-sm text-rose-200 backdrop-blur-xl">
        <p className="font-semibold">Could not load run stats</p>
        <p className="mt-1 text-rose-300/80">{error}</p>
        <button
          onClick={load}
          className="mt-3 rounded-lg border border-rose-400/40 px-3 py-1.5 text-xs font-semibold text-rose-100 transition hover:bg-rose-500/20"
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
          <div
            key={i}
            className="h-28 animate-pulse rounded-2xl border border-white/5 bg-white/5"
          />
        ))}
      </div>
    );
  }

  const matchPct =
    stats.match_rate !== null ? `${(stats.match_rate * 100).toFixed(1)}%` : "—";

  return (
    <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
      <StatCard
        label="Auto-Match Rate"
        value={matchPct}
        sub={`${stats.auto_matched_count ?? "—"} of ${stats.total_events ?? "—"} events (seed ${stats.seed ?? "—"})`}
        accent="bg-gradient-to-r from-emerald-300 to-cyan-300 bg-clip-text text-transparent"
        delay={0}
      />
      <StatCard
        label="Needs Review"
        value={String(stats.review_count ?? "—")}
        sub="flagged for a human"
        accent="text-amber-300"
        delay={70}
      />
      <StatCard
        label="Exceptions"
        value={String(stats.exception_count ?? "—")}
        sub="honest unresolved breaks"
        accent="text-rose-300"
        delay={140}
      />
      <StatCard
        label="Throughput"
        value={throughput(stats)}
        sub={`${stats.processing_time_ms ?? "—"} ms for ${stats.total_events ?? "—"} events`}
        accent="text-indigo-300"
        delay={210}
      />
    </div>
  );
}

function reasonOf(record: ExceptionRecord): string {
  const reason = record.details?.reason;
  return typeof reason === "string" ? reason : "No reason recorded";
}

function ExceptionCard({
  record,
  index,
}: {
  record: ExceptionRecord;
  index: number;
}) {
  return (
    <div
      className="animate-fade-up rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur-xl transition duration-300 hover:border-rose-400/30 hover:bg-white/10"
      style={{ animationDelay: `${index * 80}ms` }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-md bg-rose-500/15 px-2 py-0.5 text-[11px] font-bold tracking-wider text-rose-300 uppercase">
          Exception
        </span>
        <span className="rounded-md bg-slate-500/15 px-2 py-0.5 font-mono text-[11px] text-slate-300">
          {record.rule_or_model}
        </span>
        <span className="ml-auto text-[11px] text-slate-500">
          confidence {record.confidence_score.toFixed(2)} · {record.match_stage}
        </span>
      </div>
      <p className="mt-3 font-mono text-sm break-all text-slate-200">
        {record.txn_ids.join(", ")}
      </p>
      <p className="mt-2 text-xs text-slate-400">{reasonOf(record)}</p>
      {record.explanation ? (
        <div className="mt-3 rounded-xl border border-indigo-400/20 bg-indigo-500/10 p-3">
          <p className="text-[11px] font-bold tracking-widest text-indigo-300 uppercase">
            Copilot explanation
          </p>
          <p className="mt-1 text-sm leading-relaxed text-indigo-100/90">
            {record.explanation}
          </p>
        </div>
      ) : (
        <p className="mt-3 text-xs text-slate-500 italic">
          Explanation pending — rerun run_eval.py with the LLM explainer
          enabled.
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
        <h2 className="text-lg font-bold text-slate-100">Exception Queue</h2>
        <button
          onClick={load}
          className="rounded-lg border border-white/10 px-3 py-1.5 text-xs font-semibold text-slate-300 transition hover:border-white/25 hover:bg-white/10"
        >
          Refresh
        </button>
      </div>

      {error ? (
        <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-5 text-sm text-rose-200">
          <p className="font-semibold">Could not load exceptions</p>
          <p className="mt-1 text-rose-300/80">{error}</p>
        </div>
      ) : records === null ? (
        <div className="space-y-3">
          {[0, 1].map((i) => (
            <div
              key={i}
              className="h-36 animate-pulse rounded-2xl border border-white/5 bg-white/5"
            />
          ))}
        </div>
      ) : records.length === 0 ? (
        <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-5 text-sm text-emerald-200">
          No unresolved exceptions in the latest run.
        </div>
      ) : (
        <div className="space-y-3">
          {records.map((record, index) => (
            <ExceptionCard
              key={record.match_id}
              record={record}
              index={index}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export default function Dashboard() {
  return (
    <div className="space-y-6">
      <StatsPanel />
      <ExceptionsQueue />
    </div>
  );
}
