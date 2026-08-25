# ReconLoop — 3-Minute Demo Script

> Deterministic demo: seed 42 means every order ID below is stable across runs.
> Total runtime: ~3 minutes. Rehearse once before recording/presenting.

## Pre-flight checklist (before the demo)

- [ ] `.env` present with `GROQ_API_KEY`, `HUGGING_FACE_API_KEY`, `PINECONE_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`
- [ ] One fresh eval run completed: `.venv\Scripts\python backend\eval\run_eval.py` (writes `eval_report.md`, uploads the audit trail to Supabase)
- [ ] Knowledge base seeded (once ever): `.venv\Scripts\python backend\agents\vector_store.py data\policies`
- [ ] Terminal open at project root, venv activated
- [ ] Browser tab ready at `http://localhost:5173` (after starting `run_dev.py`)
- [ ] Fallback if Wi-Fi flakes: the eval run + report work fully offline; only the copilot chat needs the LLM (it degrades to a clean "unavailable" message, which is itself a talking point)

---

## Beat 1 — The Problem (0:00–0:30)

**Show:** the three raw CSVs side by side.

```
data/samples/internal_ledger.csv      (what the merchant's books say)
data/samples/gateway_settlement.csv   (what the gateway settled)
data/samples/bank_statement.csv       (what actually hit the bank)
```

**Say:**
- "Three systems, three different schemas, three different truths. Ledger has order IDs and gross amounts. The gateway has settlement IDs, fees, and UTRs. The bank has reference strings with UTRs buried inside them."
- "86 transactions in this batch — and we deliberately injected 26 broken ones: bundled payouts, partial refunds, typos, duplicates, delayed settlements, chargebacks. This is what finance teams actually face."

## Beat 2 — The Engine (0:30–1:15)

**Run:** `.venv\Scripts\python backend\eval\run_eval.py`

**Say (while it runs, ~5 seconds):**
- "One command closes the loop: normalize three sources into one canonical schema, tiered matching — exact keys first, then fuzzy with amount/date/reference tolerance — then every decision routed by confidence and written to an immutable Supabase audit trail."
- Point at the output: **94.2% auto-match rate, 100% routing accuracy, 2 honest exceptions, ~10,000 events/sec.**
- "Ground truth was labeled before the pipeline ever ran — these numbers are measured, not claimed."

## Beat 3 — The Dashboard (1:15–1:50)

**Run:** `.venv\Scripts\python run_dev.py` → open `http://localhost:5173`

**Say:**
- "The stats panel reads straight from the Supabase audit trail — the same numbers, nothing hand-typed."
- "94.2% of events auto-matched across three sources. The industry benchmark for rules-only matching is 40–60%."

## Beat 4 — Honest Exceptions (1:50–2:30)

**Show:** the Exception Queue cards.

**Say:**
- "Here's the part most demos hide: what the system could NOT resolve."
- "Two chargeback events. The ledger order has no normal settlement — it has a reversal. The engine correctly refuses to auto-pair it, and the Exception Explainer agent explains WHY with citations: it looked up the transaction with a tool call, retrieved our chargeback policy from the vector store, and produced this plain-English explanation with a suggested resolution."
- "This is the difference between detection and explanation — and we prove both on a held-out batch, including our own failure cases."

## Beat 5 — The Copilot (2:30–3:00)

**Type into the chat panel:**

```
What is the total fee for order led_order_ad3wrdhw9re2q6 and how is it calculated?
```

(Any order works — try `order_nhj7xvg0fn9xuy` for a clean one, or ask
"how many exceptions this week are chargeback related?")

**Say:**
- "The copilot answers with tool calls against the live transaction index and the policy knowledge base — grounded and cited, not hallucinated."
- Close: "Detect, explain, resolve, audit — one loop, closed end to end. That's ReconLoop."

---

## If something breaks live

| Symptom | Fallback |
|---|---|
| Copilot reply is an error message | Say: "free-tier API hiccup — the retry layer usually absorbs it; notice it degrades gracefully instead of crashing" and ask a second question |
| Stats panel shows an error | The audit trail needs one prior `run_eval.py` run — run it, click Refresh |
| `run_dev.py` port conflict | Backend on :8000, frontend on :5173 — free the ports or use `docker compose up` |
| Everything fails | `eval_report.md` at the repo root contains the full measured evaluation, including the honest exception list — walk the judges through it |
