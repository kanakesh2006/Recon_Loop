"""LangChain tools for ReconLoop agents: transaction lookup, policy search, fee schedule."""

from __future__ import annotations

import logging

from langchain_core.tools import tool

from backend.ingestion.canonical import CanonicalTransaction

logger = logging.getLogger(__name__)

_FEE_SCHEDULE_SUMMARY = (
    "Razorpay standard fee schedule (as modeled in ReconLoop):\n"
    "- Transaction fee: 2% of gross amount + Rs 3 flat per transaction\n"
    "- GST: 18% on the fee (not on the transaction amount)\n"
    "- Net settlement = gross - fee - tax_on_fee (bank receives the net amount)\n"
    "- Example: Rs 2,499.00 order -> fee Rs 52.98, GST Rs 9.54, net Rs 2,436.48\n"
    "- Ledger-vs-settlement differences of ~2% + Rs 3 + GST are expected, not exceptions;\n"
    "  rounding differences of Rs 0.01-Rs 2.00 are tolerated by fuzzy matching."
)

_TRANSACTION_INDEX: dict[str, CanonicalTransaction] = {}
_VECTOR_STORE = None


def set_transaction_index(transactions: list[CanonicalTransaction]) -> int:
    """Index transactions for get_transaction lookups (by txn_id and reference)."""
    _TRANSACTION_INDEX.clear()
    for txn in transactions:
        keys = {txn.txn_id, txn.reference, txn.txn_id.split("#")[0]}
        for key in keys:
            _TRANSACTION_INDEX.setdefault(key, txn)
    return len(_TRANSACTION_INDEX)


def set_vector_store(store) -> None:
    global _VECTOR_STORE
    _VECTOR_STORE = store


def get_vector_store():
    global _VECTOR_STORE
    if _VECTOR_STORE is None:
        from backend.agents.vector_store import VectorStore

        _VECTOR_STORE = VectorStore()
    return _VECTOR_STORE


def _format_transaction(txn: CanonicalTransaction) -> str:
    lines = [
        f"txn_id: {txn.txn_id}",
        f"source: {txn.source}",
        f"type: {txn.txn_type}",
        f"amount: Rs {txn.amount / 100:,.2f}",
        f"date: {txn.date.isoformat()}",
        f"reference: {txn.reference}",
        f"counterparty: {txn.counterparty}",
        f"raw status: {txn.raw_record.get('status', '')}",
    ]
    utr = txn.raw_record.get("utr_number")
    if utr:
        lines.append(f"utr: {utr}")
    notes = txn.raw_record.get("notes")
    if notes:
        lines.append(f"notes: {notes}")
    return "\n".join(lines)


@tool
def get_transaction(txn_id: str) -> str:
    """Look up a transaction by txn_id (led_/stl_/bnk_ prefixed), order_id, or reference."""
    key = txn_id.strip()
    txn = _TRANSACTION_INDEX.get(key)
    if txn is None:
        case_insensitive = {k.lower(): v for k, v in _TRANSACTION_INDEX.items()}
        txn = case_insensitive.get(key.lower())
    if txn is None:
        substring_matches = {
            id for id in _TRANSACTION_INDEX if key.lower() in id.lower()
        }
        if len(substring_matches) == 1:
            txn = _TRANSACTION_INDEX[substring_matches.pop()]
        elif len(substring_matches) > 1:
            listed = ", ".join(sorted(substring_matches)[:10])
            return (
                f"Multiple transactions match '{txn_id}'. Candidates: {listed}. "
                "Please specify the full txn_id."
            )
    if txn is None:
        return (
            f"Transaction '{txn_id}' not found. Try the order_id (e.g. order_abc123), "
            "a txn_id (led_/stl_/bnk_ prefixed), or the raw reference."
        )
    return _format_transaction(txn)


@tool
def get_fee_schedule() -> str:
    """Return Razorpay's standard fee schedule (2% + Rs 3 + 18% GST on fee)."""
    return _FEE_SCHEDULE_SUMMARY


@tool
def search_policy_docs(query: str) -> str:
    """Search the reconciliation policy knowledge base (fees, chargebacks, settlement delays)."""
    try:
        store = get_vector_store()
        results = store.search(query, top_k=4)
    except Exception as exc:
        return f"Policy search unavailable: {exc}"
    if not results:
        return "No policy documents found for that query."
    formatted = [
        f"[{result['source']} | relevance {result['score']:.2f}]\n{result['text']}"
        for result in results
    ]
    return "\n\n---\n\n".join(formatted)


AGENT_TOOLS = [get_transaction, search_policy_docs, get_fee_schedule]
