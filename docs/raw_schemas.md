# Raw Source Schemas

These are the **pre-normalization** formats the synthetic data generator produces and the
ingestion layer consumes. They are intentionally different shapes/namings — normalizing them
into one canonical schema is the job of `backend/ingestion/`.

All money columns are **rupees with 2 decimal places** (e.g. `1234.50`). Ingestors convert to
**paise (integer-valued Decimal, ×100)** — see `backend/ingestion/canonical.py`.

---

## 1. Internal Ledger — `internal_ledger.csv`

What the merchant's own system thinks happened.

| Column | Type | Example | Notes |
|---|---|---|---|
| `order_id` | string | `order_a1b2c3d4e5f6a7` | Unique within ledger, `order_` + 14 alnum. May be **duplicated** by the `duplicate_id` edge case. |
| `customer_name` | string | `Priya Sharma` | Faker-generated |
| `amount` | decimal (rupees) | `2499.00` | Order value, always positive |
| `currency` | string | `INR` | Always `INR` in generated data |
| `order_date` | date | `2026-07-14` | `YYYY-MM-DD`; ingestor also accepts `DD/MM/YYYY` |
| `payment_method` | string | `UPI` | One of `UPI`, `card`, `netbanking`, `wallet` |
| `status` | string | `completed` | One of `completed`, `pending`, `refund`, `chargeback`. Drives `txn_type` inference. |
| `notes` | string | `regular sale` | Free text; edge cases annotate here |

## 2. Gateway Settlement — `gateway_settlement.csv`

Razorpay-style settlement record (what the gateway says it settled).

| Column | Type | Example | Notes |
|---|---|---|---|
| `settlement_id` | string | `setl_k9m8n7p6q5r4s3` | `setl_` + 14 alnum, unique |
| `txn_ref` | string | `order_a1b2c3d4e5f6a7` | **The cross-source link**: references the ledger `order_id` |
| `merchant_id` | string | `mer_x1y2z3a4b5c6d7` | Single merchant per generated batch |
| `gross_amount` | decimal (rupees) | `2499.00` | Equals ledger `amount` (negated for chargebacks) |
| `fee` | decimal (rupees) | `52.98` | Gateway fee: 2% of gross + ₹3 flat |
| `tax_on_fee` | decimal (rupees) | `9.54` | 18% GST on fee |
| `net_amount` | decimal (rupees) | `2436.48` | `gross - fee - tax_on_fee` (+ edge-case deltas). **This is the canonical amount.** Negative for chargebacks. |
| `settlement_date` | date | `2026-07-15` | Order date + 1–2 days normally; + 3–5 days for `date_drift` |
| `utr_number` | string | `HDFCN202607150012345678` | Bank-generated Unique Transaction Reference, 22 chars. Bundled settlements **share** the payout UTR. |
| `status` | string | `processed` | One of `processed`, `pending`, `refund`, `chargeback`. Drives `txn_type` inference. |

## 3. Bank Statement — `bank_statement.csv`

What actually hit the bank account.

| Column | Type | Example | Notes |
|---|---|---|---|
| `date` | date | `2026-07-15` | Settlement date (+0–1 day) |
| `description` | string | `RAZORPAY SOFTWARE PVT LTD PAYOUT` | Narrative text; debits carry keywords (`REFUND`, `CHARGEBACK`) used for `txn_type` inference |
| `reference_no` | string | `NEFT/HDFCN202607150012345678/RZPPAYOUT` | **Contains the `utr_number`** — the cross-source link. `ref_typo` edge case mutates the UTR chars here. |
| `debit` | decimal (rupees) | `0.00` | Money out (chargeback reversals); `0.00` for credits |
| `credit` | decimal (rupees) | `2436.48` | Money in; `0.00` for debits. Bundled payouts = **one credit row summing several settlements**. |
| `balance` | decimal (rupees) | `502436.48` | Running balance |

Exactly one of `debit`/`credit` is non-zero per row.

## 4. Ground Truth — `ground_truth.csv`

Produced by the generator, consumed by `data/validate_ground_truth.py` and the eval harness.
**One row per transaction event** (an event = one order's lifecycle across sources).

| Column | Type | Example | Notes |
|---|---|---|---|
| `order_id` | string | `order_a1b2c3d4e5f6a7` | Ledger key |
| `settlement_id` | string | `setl_k9m8n7p6q5r4s3` | Empty for `pending` events |
| `bank_reference` | string | `NEFT/HDFCN202607150012345678/RZPPAYOUT` | The **exact** `reference_no` of the linked bank row (so validation is exact-match). Empty for `pending`. |
| `expected_match_status` | string | `matched` | `matched` (should resolve via exact or fuzzy stages), `pending` (no settlement exists — must NOT be flagged as a break), `exception` (chargeback reversals — should be flagged, not silently matched) |
| `edge_case_label` | string | `clean_match` | One of: `clean_match`, `bundled_match`, `partial_refund`, `rounding_diff`, `duplicate_id`, `date_drift`, `ref_typo`, `pending`, `chargeback` |
| `notes` | string | `typo of true UTR HDFCN...` | Human-readable explanation of the injected edge case |

### Edge-case mix (injected by `--edge-cases`, on by default)

| # | Label | Count | Injected behavior | Expected pipeline outcome |
|---|---|---|---|---|
| 1 | `bundled_match` | 2 bundles (6 orders) | 3 settlements share one payout UTR; 1 bank credit = sum of nets | Matched via one-to-many handling |
| 2 | `partial_refund` | 3 | `net_amount` = expected − refund amount | Matched via amount tolerance / review |
| 3 | `rounding_diff` | 4 | `net_amount` off by ₹0.01–₹2.00 | Matched via fuzzy amount band |
| 4 | `duplicate_id` | 2 | Ledger `order_id` appears twice | Exactly one ledger↔settlement match; duplicate surfaced |
| 5 | `date_drift` | 3 | Settlement 3–5 days after order date | Matched via sliding date window |
| 6 | `ref_typo` | 3 | 1–2 char swap/drop in bank `reference_no` UTR | Matched via fuzzy reference matching |
| 7 | `pending` | 3 | No settlement or bank row | Not flagged as a break |
| 8 | `chargeback` | 2 | Negative settlement net + bank debit | Flagged as exception with explanation |

With default `--count 60`: 60 clean + 26 edge-case events = **86 ground-truth events**
(88 ledger rows, 83 settlement rows, 79 bank rows).
