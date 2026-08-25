from types import SimpleNamespace

from backend.agents import llm
from backend.agents.explainer import DEGRADED_MESSAGE, ExceptionExplainer
from backend.agents.llm import RateLimiter
from backend.matching.match_record import build_match_record


class FakeAgent:
    def __init__(
        self,
        response="The ledger order has a chargeback settlement instead of a normal one.",
    ):
        self.response = response
        self.payloads = []

    def invoke(self, payload, config=None):
        self.payloads.append(payload)
        return {"messages": [SimpleNamespace(content=self.response)]}


class FailingAgent:
    def invoke(self, payload, config=None):
        raise RuntimeError("rate limit exceeded")


def _exception_record():
    record = build_match_record(
        txn_ids=["led_order_9"],
        match_stage="unmatched",
        confidence_score=0.0,
        rule_or_model="no_match_found",
        status="exception",
        details={"reason": "no settlement or bank counterpart resolved"},
    )
    record.status = "exception"
    return record


def test_degrades_without_api_key(monkeypatch):
    monkeypatch.setattr(llm, "groq_api_key", lambda: "")

    explainer = ExceptionExplainer()

    assert explainer.available is False
    assert explainer.explain_exception(_exception_record()) == DEGRADED_MESSAGE


def test_explain_exception_returns_llm_text(monkeypatch):
    monkeypatch.setattr(llm, "groq_api_key", lambda: "k")
    monkeypatch.setattr(RateLimiter, "wait", lambda self: None)
    fake_agent = FakeAgent()
    monkeypatch.setattr(ExceptionExplainer, "_build_agent", lambda self: fake_agent)

    explainer = ExceptionExplainer()
    explanation = explainer.explain_exception(_exception_record())

    assert explanation.startswith("The ledger order has a chargeback")
    assert len(fake_agent.payloads) == 1
    prompt = fake_agent.payloads[0]["messages"][0][1]
    assert "no_match_found" in prompt
    assert "led_order_9" in prompt


def test_explain_exception_degrades_on_persistent_failure(monkeypatch):
    monkeypatch.setattr(llm, "groq_api_key", lambda: "k")
    monkeypatch.setattr(RateLimiter, "wait", lambda self: None)
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(ExceptionExplainer, "_build_agent", lambda self: FailingAgent())

    explainer = ExceptionExplainer()

    assert explainer.explain_exception(_exception_record()) == DEGRADED_MESSAGE


def test_prompt_includes_matcher_details():
    prompt = ExceptionExplainer._build_prompt(_exception_record())

    assert "Rule fired: no_match_found" in prompt
    assert "Confidence: 0.00" in prompt
    assert "no settlement or bank counterpart resolved" in prompt


def test_rate_limiter_enforces_interval(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(llm.time, "monotonic", lambda: 100.0)

    limiter = llm.RateLimiter(min_interval_seconds=2.5)
    limiter.wait()
    assert sleeps == []

    limiter.wait()
    assert sleeps == [2.5]
