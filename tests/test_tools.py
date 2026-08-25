from types import SimpleNamespace

from factories import bank_txn, ledger_txn, settlement_txn

from backend.agents import tools
from backend.agents.tools import (
    get_fee_schedule,
    get_transaction,
    search_policy_docs,
    set_transaction_index,
)


def _sample_transactions():
    led = ledger_txn(reference="order_1", amount_paise=249900, day=1)
    stl = settlement_txn(reference="order_1", amount_paise=243648, day=2)
    bnk = bank_txn(amount_paise=243648, day=2)
    return [led, stl, bnk]


def test_get_transaction_by_txn_id():
    set_transaction_index(_sample_transactions())

    output = get_transaction.invoke({"txn_id": "led_order_1"})

    assert "txn_id: led_order_1" in output
    assert "amount: Rs 2,499.00" in output
    assert "source: ledger" in output
    assert "type: payment" in output


def test_get_transaction_by_order_reference():
    set_transaction_index(_sample_transactions())

    output = get_transaction.invoke({"txn_id": "order_1"})

    assert "reference: order_1" in output


def test_get_transaction_not_found():
    set_transaction_index(_sample_transactions())

    output = get_transaction.invoke({"txn_id": "order_does_not_exist"})

    assert "not found" in output


def test_get_transaction_duplicate_suffix_resolvable():
    led = ledger_txn(reference="order_dup", suffix="")
    led_dup = ledger_txn(reference="order_dup", suffix="#2")
    set_transaction_index([led, led_dup])

    output = get_transaction.invoke({"txn_id": "led_order_dup#2"})

    assert "txn_id: led_order_dup#2" in output


def test_get_fee_schedule_contents():
    output = get_fee_schedule.invoke({})

    assert "2%" in output
    assert "18%" in output
    assert "2,436.48" in output


def test_search_policy_docs_formats_results():
    tools.set_vector_store(
        SimpleNamespace(
            search=lambda query, top_k=4: [
                {
                    "text": "Fee is 2% plus Rs 3.",
                    "source": "fee_schedule.md",
                    "score": 0.91,
                },
            ]
        )
    )
    try:
        output = search_policy_docs.invoke({"query": "fee schedule"})
    finally:
        tools.set_vector_store(None)

    assert "fee_schedule.md" in output
    assert "0.91" in output
    assert "Fee is 2% plus Rs 3." in output


def test_search_policy_docs_empty_results():
    tools.set_vector_store(SimpleNamespace(search=lambda query, top_k=4: []))
    try:
        output = search_policy_docs.invoke({"query": "obscure topic"})
    finally:
        tools.set_vector_store(None)

    assert "No policy documents found" in output


def test_search_policy_docs_store_failure_degrades():
    def boom(query, top_k=4):
        raise RuntimeError("offline")

    tools.set_vector_store(SimpleNamespace(search=boom))
    try:
        output = search_policy_docs.invoke({"query": "anything"})
    finally:
        tools.set_vector_store(None)

    assert "Policy search unavailable" in output
