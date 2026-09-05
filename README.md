# ReconLoop

### Multi-Source Reconciliation Agent with Explainable, Conversational Exception Resolution

**Razorpay AI Buildathon | Track 04: AI Finance Controller**

ReconLoop closes a full finance-ops loop end to end. It ingests order, settlement, and bank data across three different CSV formats, auto-matches them through a tiered rules and fuzzy matching engine, and uses a RAG-grounded agent to explain why each exception occurred. Finance users can investigate discrepancies conversationally over text or voice, with every decision written to an immutable audit log.

![ReconLoop System Architecture](reconloop_architecture_detailed.svg)

---

## The Problem

Reconciliation remains a manual bottleneck for finance teams. Transaction data is spread across three isolated systems:

| Source | Role & Details | Example Record |
|---|---|---|
| Internal Ledger | Order IDs, gross amounts, customer names | `order_a1b2..., 2499.00` |
| Gateway Settlement | Settlement IDs, net payouts, fees, UTRs | `setl_k9m8..., net 2436.48` |
| Bank Statement | Raw reference strings with embedded UTRs | `NEFT/HDFCN.../RZPPAYOUT` |

The primary challenge in finance operations is verification capacity: validating output at high volume rather than relying on cherry-picked examples.

## Key Features

1. **Dynamic Ingestion & Auto-Detection**: Drag-and-drop CSV upload for Internal Ledgers, Payment Gateways, and Bank Statements. Includes column-pair heuristics for automatic schema detection with manual override controls. Amounts are normalized to integer paise.
2. **Tiered Matching Engine**: Matches exact keys first (order ID to transaction reference and UTR extraction), followed by fuzzy passes (amount tolerance bands, sliding date windows, RapidFuzz string matching, and bundled payout resolution).
3. **Confidence Routing**: Categorizes transactions into Auto-Matched, Needs Review, or Exception, persisting all audit records directly to Supabase.
4. **AI Exception Explainer & Confidence Score**: A LangGraph agent grounds breaks using transaction evidence and policy documents. It generates plain-English explanations with an AI Confidence Score to support risk-aware decisions.
5. **Conversational Copilot (Voice & Text)**: Interactive Q&A interface powered by Web Speech API voice dictation. Answers questions like *"Why is order #4521 short?"* with cited policy references.
6. **Resilient SSE Streaming**: Server-Sent Events stream pipeline progress in real time with built-in API rate-limit backoff handling.

## Evaluation & Measured Results (86-Event Labeled Batch, Seed 42)

| Metric | Measured Result |
|---|---|
| Auto-Match Rate | **94.2%** (81 out of 86 events) |
| Routing Accuracy | **100%** (All events correctly categorized) |
| Honest Exceptions | **2** chargeback breaks (Flagged and explained with citations) |
| Pipeline Throughput | **~10,000 events/sec** (86 events processed in ~8.5 ms) |
| Handled Edge Cases | Bundled payouts, partial refunds, rounding drift (₹0.01 to ₹2), duplicate IDs, 3-5 day settlement lag, reference typos, pending orders, chargebacks |

Ground truth labels were established prior to running the matching pipeline. Full evaluation methodology and per-category breakdowns are documented in [`eval_report.md`](eval_report.md).

## Tech Stack

| Layer | Component |
|---|---|
| Backend API | FastAPI + Uvicorn |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS v4 |
| Matching Engine | Python, pandas, RapidFuzz (Integer paise arithmetic) |
| Database & Audit Trail | Supabase (PostgreSQL) |
| Vector Store (RAG) | Pinecone Serverless (768-d `bge-vectors` namespace) |
| Embeddings | Hugging Face Inference API (`BAAI/bge-base-en-v1.5`, fallback `all-MiniLM-L6-v2`) |
| AI Agents | LangChain + LangGraph ReAct Agent (Groq `openai/gpt-oss-120b` with `20b` fallback) |
| Observability | LangSmith Tracing |
| Synthetic Data | Python + Faker with edge-case injector |

## Local Setup

### Prerequisites

- Python 3.12+
- Node.js 22+
- A `.env` file created at the project root (see `.env.example`):

```env
SUPABASE_URL=...
SUPABASE_KEY=...
PINECONE_API_KEY=...
GROQ_API_KEY=...
HUGGING_FACE_API_KEY=...
```

### Option 1: Docker (Single Command)

```bash
docker compose up --build
```

Access the dashboard at `http://localhost:5173` and backend API docs at `http://localhost:8000/docs`.

### Option 2: Native Setup

```bash
# 1. Install Python dependencies
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt        # Windows
# .venv/bin/pip install -r requirements.txt          # macOS/Linux

# 2. Install Frontend dependencies
cd frontend && npm install && cd ..

# 3. Seed RAG knowledge base
.venv\Scripts\python backend\agents\vector_store.py data\policies

# 4. Run evaluation pipeline
.venv\Scripts\python backend\eval\run_eval.py

# 5. Start development servers
.venv\Scripts\python run_dev.py
```

### Verification & Testing

```bash
# Run unit test suite (121 tests)
.venv\Scripts\python -m pytest tests/

# Validate ground-truth dataset integrity
.venv\Scripts\python data\validate_ground_truth.py
```

Running `backend/eval/run_eval.py` regenerates the deterministic test batch, executes matching and LLM explanation steps, and writes updated results to `eval_report.md`.

## Repository Structure

```
reconloop/
├── README.md                            # Project overview and setup instructions
├── reconloop_architecture_detailed.svg  # System architecture diagram
├── data/
│   ├── generate_synthetic.py            # Synthetic batch generator (8 edge-case types)
│   ├── validate_ground_truth.py         # Ground-truth validator script
│   ├── policies/                        # Policy documents for RAG agent
│   └── samples/                         # Generated CSV samples and ground_truth.csv
├── backend/
│   ├── ingestion/                       # Schema mappers for ledger, settlement, and bank feeds
│   ├── matching/                        # Multi-stage matching and confidence routing logic
│   ├── agents/                          # Pinecone vector store, LangGraph explainer, and copilot
│   ├── audit/                           # Supabase audit log client
│   ├── eval/                            # Evaluation harness and report generator
│   └── api/                             # FastAPI endpoints and SSE worker
├── frontend/                            # React dashboard and voice copilot interface
├── docs/                                # Schemas and demo scripts
├── eval_report.md                       # Full evaluation metrics report
└── run_dev.py                           # Concurrent backend and frontend launcher
```

## Core Design Principles

- **Integer Paise Arithmetic**: Currency values are converted to integer paise to eliminate floating-point precision issues.
- **Typed Direction**: Transaction types are explicitly categorized (e.g., chargebacks are positive amounts marked as `txn_type="chargeback"`).
- **Settlement Bridge**: Gateway settlement records serve as the join bridge between internal ledger entries and bank statements.
- **Graceful Agent Fallback**: Missing API keys or model rate limits trigger clean fallback responses without application crashes.
- **Rate-Limit Resilience**: Includes exponential backoff, rate limiting, and dual-model fallbacks for all LLM calls.
