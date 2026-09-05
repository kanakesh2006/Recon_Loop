# ReconLoop

### Multi-Source Reconciliation Agent with Explainable, Conversational Exception Resolution

**Razorpay AI Buildathon | Track 04: AI Finance Controller**

ReconLoop closes a complete finance operations loop end to end. It ingests order, settlement, and bank data across distinct formats, auto-matches them using a tiered rules and fuzzy matching engine, and goes beyond traditional reconciliation tools by providing RAG-grounded AI explanations for why exceptions occur. Finance teams can investigate breaks conversationally via voice or text, while every decision is backed by an immutable audit trail.

![ReconLoop System Architecture](architecture.png)

---

## The Problem

Reconciliation remains a manual bottleneck for modern finance teams. Financial data is fragmented across three primary systems:

| Source | Primary Function | Sample Format |
|---|---|---|
| Internal Ledger | Order IDs, gross amounts, customer records | `order_a1b2..., 2499.00` |
| Gateway Settlement | Settlement IDs, deductions, fees, UTRs | `setl_k9m8..., net 2436.48` |
| Bank Statement | Raw banking entries with embedded UTR strings | `NEFT/HDFCN.../RZPPAYOUT` |

The core challenge in automated finance operations is **verification capacity**: trusting and auditing output at scale. A single cherry-picked demo does not prove real-world reliability.

## What ReconLoop Does

1. **Dynamic Ingestion & Auto-Detection**: Drag-and-drop CSV upload supporting Internal Ledgers, Payment Gateways, and Bank Statements. Includes column-pair heuristics for automatic schema recognition with manual category overrides. All currency amounts are normalized to integer paise.
2. **Tiered Reconciliation Engine**: Runs exact key matching (order ID to transaction reference, UTR extraction) followed by fuzzy matching (amount tolerance bands, sliding date windows, RapidFuzz string matching, and one-to-many bundled payout resolution).
3. **Confidence-Based Routing**: Categorizes transactions into auto-matched, needs review, or exception buckets. Every result is persisted to an immutable Supabase audit log.
4. **Root-Cause Exception Explainer**: Powered by a LangGraph ReAct agent that cross-references breaks against policy documents (fee schedules, chargebacks, settlement delays). Generates cited explanations alongside an **AI Confidence Score** for risk-aware decision making.
5. **Conversational Copilot (Voice & Text)**: Interactive assistant for querying settlement data ("Why is order #4521 short?"). Integrated with the Web Speech API for hands-free voice dictation.
6. **Resilient Streaming Architecture**: Real-time progress updates via Server-Sent Events (SSE) featuring automatic exponential backoff and rate-limit fallbacks.

## Measured Results (Held-out 86-event labeled batch, seed 42)

| Metric | Result |
|---|---|
| Auto-match rate | **94.2%** (81/86 events, event-level) |
| Routing accuracy | **100%** (all events correctly categorized into expected buckets) |
| Honest exceptions | **2** chargeback events (flagged, cited, and explained without hiding edge cases) |
| Throughput | **~10,000 events/sec** (86 events in ~8.5 ms) |
| Edge cases handled | Bundled payouts, partial refunds, rounding drift (₹0.01 to ₹2), duplicate IDs, 3-5 day settlement delays, reference typos, pending orders, chargebacks |

Ground truth datasets were generated before running the evaluation pipeline. Per-category accuracy and unresolved exception lists are fully empirical. See [`eval_report.md`](eval_report.md) for full metrics and methodology.

## Tech Stack

| Layer | Tool |
|---|---|
| Backend API | FastAPI + Uvicorn |
| Frontend | React 19 + TypeScript + Vite + Tailwind CSS v4 |
| Matching Engine | Python, pandas, rapidfuzz (Decimal paise arithmetic) |
| Audit Trail & DB | Supabase (PostgreSQL) |
| RAG Vector Store | Pinecone Serverless (768-d, dual-embedding namespaces) |
| Embeddings | Hugging Face Inference API (`BAAI/bge-base-en-v1.5`, fallback `all-MiniLM-L6-v2`) |
| Agent Framework | LangChain + LangGraph (ReAct), Groq `openai/gpt-oss-120b` (fallback `openai/gpt-oss-20b`) |
| Observability | LangSmith tracing |
| Synthetic Data | Python + Faker with a hand-authored edge-case injector |

## Run It Locally

### Prerequisites

- Python 3.12+, Node 22+
- A `.env` at the project root (copy `.env.example` and fill in):

```
SUPABASE_URL=...
SUPABASE_KEY=...
PINECONE_API_KEY=...
GROQ_API_KEY=...
HUGGING_FACE_API_KEY=...
```

### Option A: Docker (One Command)

```bash
docker compose up --build
```

Backend on `:8000`, dashboard on `:5173`.

### Option B: Native (Two Processes)

```bash
# 1. Python dependencies
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt        # Windows
# .venv/bin/pip install -r requirements.txt          # macOS/Linux

# 2. Frontend dependencies
cd frontend && npm install && cd ..

# 3. Seed the RAG knowledge base (once)
.venv\Scripts\python backend\agents\vector_store.py data\policies

# 4. Run full evaluation (generates data, matches, explains, uploads audit trail)
.venv\Scripts\python backend\eval\run_eval.py

# 5. Start backend and dashboard together
.venv\Scripts\python run_dev.py
```

Open **http://localhost:5173** (API docs at **http://localhost:8000/docs**).

### Verification & Tests

```bash
.venv\Scripts\python -m pytest tests/                # 121 tests
.venv\Scripts\python data\validate_ground_truth.py   # ground-truth sanity check
```

`backend/eval/run_eval.py` regenerates the labeled batch (seeded, deterministic), reruns the pipeline, recomputes metrics against ground truth, and updates `eval_report.md`.

## Repository Layout

```
reconloop/
├── data/
│   ├── generate_synthetic.py     # labeled held-out batch generator (8 edge-case types)
│   ├── validate_ground_truth.py  # ground-truth sanity checks
│   ├── policies/                 # RAG knowledge base documents
│   └── samples/                  # generated raw CSVs + ground_truth.csv
├── backend/
│   ├── ingestion/                # canonical schema + 3 source mappers
│   ├── matching/                 # exact -> fuzzy -> confidence routing pipeline
│   ├── agents/                   # Pinecone RAG, LangGraph explainer + copilot
│   ├── audit/                    # Supabase audit logger (graceful offline mode)
│   ├── eval/                     # metrics harness, markdown report, CLI runner
│   └── api/                      # FastAPI endpoints for the dashboard
├── frontend/                     # React + Tailwind dashboard & chat UI
├── docs/                         # schemas, demo script, architecture
├── eval_report.md                # generated: full measured evaluation
└── run_dev.py                    # starts backend + frontend together
```

## Design Principles

- **Integer Paise Precision**: All currency operations use integer paise to eliminate floating-point matching errors.
- **Typed Direction**: Transaction directions are explicitly typed (`payment`, `chargeback`, `refund`) rather than sign-encoded.
- **Settlement Bridge**: Settlement records bridge the gap between internal ledgers and bank statements.
- **Graceful Degradation**: System agents handle API rate limits and missing keys cleanly without crashing.
- **Free-Tier Discipline**: Enforces strict rate limiting, exponential backoff, and dual-model fallbacks throughout the agent layer.
