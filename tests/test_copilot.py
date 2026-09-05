from types import SimpleNamespace

from backend.agents import llm
from backend.agents.copilot import COPILOT_UNAVAILABLE_MESSAGE, CopilotSession
from backend.agents.llm import RateLimiter


class FakeAgent:
    def __init__(self):
        self.calls = []

    def invoke(self, payload, config=None):
        self.calls.append((payload, config))
        return {
            "messages": [SimpleNamespace(content="Order order_1 settled net of fees.")]
        }


def test_copilot_degrades_without_api_key(monkeypatch):
    monkeypatch.setattr(llm, "groq_api_key", lambda: "")

    session = CopilotSession()

    assert session.available is False
    assert session.ask("why is order_1 short?") == COPILOT_UNAVAILABLE_MESSAGE


def test_copilot_ask_returns_response_with_thread_memory(monkeypatch):
    monkeypatch.setattr(llm, "groq_api_key", lambda: "k")
    monkeypatch.setattr(RateLimiter, "wait", lambda self: None)
    fake_agent = FakeAgent()
    monkeypatch.setattr(
        CopilotSession, "_build_agent", lambda self, transactions=None: fake_agent
    )

    session = CopilotSession()
    answer = session.ask("How many exceptions this week are fee-related?")

    assert answer.startswith("Order order_1 settled")
    assert len(fake_agent.calls) == 1
    _, config = fake_agent.calls[0]
    assert config["configurable"]["thread_id"] == session.thread_id


def test_copilot_blank_question_short_circuits(monkeypatch):
    monkeypatch.setattr(llm, "groq_api_key", lambda: "k")
    monkeypatch.setattr(RateLimiter, "wait", lambda self: None)
    fake_agent = FakeAgent()
    monkeypatch.setattr(
        CopilotSession, "_build_agent", lambda self, transactions=None: fake_agent
    )

    session = CopilotSession()

    assert "Please ask a question" in session.ask("   ")
    assert fake_agent.calls == []


def test_copilot_error_degrades_gracefully(monkeypatch):
    class ExplodingAgent:
        def invoke(self, payload, config=None):
            raise RuntimeError("quota exhausted")

    monkeypatch.setattr(llm, "groq_api_key", lambda: "k")
    monkeypatch.setattr(RateLimiter, "wait", lambda self: None)
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        CopilotSession, "_build_agent", lambda self, transactions=None: ExplodingAgent()
    )

    session = CopilotSession()
    answer = session.ask("hello")

    assert answer.startswith("Automated explanation unavailable")
