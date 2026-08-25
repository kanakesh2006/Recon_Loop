"""CLI runner: generate -> match -> evaluate -> report -> (best-effort) audit upload.

Works fully offline. Supabase upload only happens when SUPABASE_URL/KEY are
configured; otherwise it is skipped with a notice and exit code stays 0.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.agents.explainer import DEGRADED_MESSAGE, ExceptionExplainer
from backend.audit.supabase_client import AuditLogger
from backend.eval.harness import evaluate_pipeline
from backend.eval.reporter import generate_markdown_report
from backend.matching.pipeline import run_matching_pipeline


def _load_generator():
    generator_path = PROJECT_ROOT / "data" / "generate_synthetic.py"
    spec = importlib.util.spec_from_file_location("generate_synthetic", generator_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="Run the ReconLoop evaluation end-to-end."
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--output-dir", default="data/samples")
    args = parser.parse_args(argv)

    generator = _load_generator()
    out_dir = Path(args.output_dir)
    generator.main(
        ["--count", str(args.count), "--output", str(out_dir), "--seed", str(args.seed)]
    )

    result = run_matching_pipeline(
        str(out_dir / "internal_ledger.csv"),
        str(out_dir / "gateway_settlement.csv"),
        str(out_dir / "bank_statement.csv"),
    )

    if result.exceptions:
        explainer = ExceptionExplainer()
        if explainer.available:
            print(
                f"Explaining {len(result.exceptions)} exception(s) via LLM "
                f"(rate-limited, {len(result.exceptions)}+ LLM calls)..."
            )
            for record in result.exceptions:
                record.explanation = explainer.explain_exception(record)
                preview = record.explanation.replace("\n", " ")[:100]
                print(f"  - {record.txn_ids[0]}: {preview}")
        else:
            print(
                f"LLM explainer unavailable - explanations set to '{DEGRADED_MESSAGE}'"
            )

    metrics = evaluate_pipeline(result, str(out_dir / "ground_truth.csv"))
    report = generate_markdown_report(metrics, seed=args.seed)
    report_path = PROJECT_ROOT / "eval_report.md"
    report_path.write_text(report, encoding="utf-8")

    print("=== ReconLoop eval summary ===")
    print(f"match rate:        {metrics.match_rate:.2%}")
    print(f"correctly routed:  {metrics.correctly_routed_rate:.2%}")
    print(f"exceptions:        {metrics.exception_count}")
    print(f"throughput:        {metrics.records_per_second:,.0f} events/sec")
    print(f"report written to: {report_path}")

    audit_logger = AuditLogger()
    if not audit_logger.is_connected:
        print("⚠ Supabase not configured — audit log skipped")
    else:
        run_id = audit_logger.create_run(result.stats, seed=args.seed)
        all_records = result.auto_matched + result.needs_review + result.exceptions
        written = audit_logger.write_batch(all_records, run_id=run_id)
        print(f"audit log: {written} records uploaded (run_id={run_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
