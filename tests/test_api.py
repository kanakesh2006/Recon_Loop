from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.api import main as api_module

RUN_ROW = {
    "run_id": "11111111-2222-3333-4444-555555555555",
    "started_at": "2026-08-24T22:00:00+00:00",
    "seed": 42,
    "total_events": 86,
    "auto_matched_count": 81,
    "review_count": 3,
    "exception_count": 2,
    "match_rate": 0.9419,
    "processing_time_ms": 8.5,
}

EXCEPTION_ROWS = [
    {
        "match_id": "aaa11111-2222-3333-4444-555555555555",
        "txn_ids": ["led_order_ad3wrdhw9re2q6"],
        "match_stage": "unmatched",
        "confidence_score": 0.0,
        "status": "exception",
        "rule_or_model": "no_match_found",
        "explanation": "The ledger order has a chargeback settlement instead of a normal one.",
        "details": {"reason": "no settlement or bank counterpart resolved"},
    }
]

AUTO_MATCHED_ROW = {
    "match_id": "bbb11111-2222-3333-4444-555555555555",
    "run_id": RUN_ROW["run_id"],
    "txn_ids": [f"led_order_{index:02d}" for index in range(81)],
    "status": "auto_matched",
}


class FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self._filters: list[tuple[str, object]] = []

    def select(self, *columns):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def in_(self, column, values):
        self._filters.append((column, values))
        return self

    def order(self, column, desc=False):
        return self

    def limit(self, count):
        return self

    def execute(self):
        def matches_filter(row, c, v):
            return row.get(c) in v if isinstance(v, (list, set, tuple)) else row.get(c) == v
            
        data = [
            row for row in self._rows if all(matches_filter(row, c, v) for c, v in self._filters)
        ]
        return SimpleNamespace(data=data)


class FakeSupabase:
    def __init__(self, rows_by_table):
        self.rows_by_table = rows_by_table
        self.queries = []

    def table(self, name):
        self.queries.append(name)
        return FakeQuery(self.rows_by_table.get(name, []))


@pytest.fixture
def client():
    return TestClient(api_module.app)


@pytest.fixture
def fake_supabase():
    fake = FakeSupabase(
        {
            "recon_runs": [RUN_ROW],
            "audit_log": [AUTO_MATCHED_ROW, *EXCEPTION_ROWS],
        }
    )
    api_module._SUPABASE_CLIENT = fake
    yield fake
    api_module._SUPABASE_CLIENT = None


def test_stats_returns_latest_run(client, fake_supabase):
    response = client.get("/api/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == RUN_ROW["run_id"]
    assert body["total_events"] == 86
    assert "recon_runs" in fake_supabase.queries
    assert "audit_log" in fake_supabase.queries
    assert body["match_rate"] == pytest.approx(81 / 86)


def test_stats_503_when_supabase_unconfigured(client, monkeypatch):
    monkeypatch.setattr(api_module, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    api_module._SUPABASE_CLIENT = None

    response = client.get("/api/stats")

    assert response.status_code == 503
    assert "Supabase not configured" in response.json()["detail"]
    api_module._SUPABASE_CLIENT = None


def test_stats_404_when_no_runs(client):
    api_module._SUPABASE_CLIENT = FakeSupabase({"recon_runs": []})

    response = client.get("/api/stats")

    assert response.status_code == 404
    assert "run_eval" in response.json()["detail"]
    api_module._SUPABASE_CLIENT = None


def test_exceptions_returns_explanations(client, fake_supabase):
    response = client.get("/api/exceptions")

    assert response.status_code == 200
    body = response.json()
    assert len(body["exceptions"]) == 1
    exception = body["exceptions"][0]
    assert exception["txn_ids"] == ["led_order_ad3wrdhw9re2q6"]
    assert exception["rule_or_model"] == "no_match_found"
    assert "chargeback settlement" in exception["explanation"]
    assert (
        exception["details"]["reason"] == "no settlement or bank counterpart resolved"
    )


def test_chat_returns_copilot_reply(client, monkeypatch):
    monkeypatch.setattr(
        api_module, "_COPILOT", SimpleNamespace(ask=lambda m: f"echo: {m}")
    )

    response = client.post(
        "/api/chat", json={"message": "What fees does Razorpay charge?"}
    )

    assert response.status_code == 200
    assert response.json() == {"reply": "echo: What fees does Razorpay charge?"}
    api_module._COPILOT = None


def test_chat_rejects_blank_message(client, monkeypatch):
    monkeypatch.setattr(api_module, "_COPILOT", SimpleNamespace(ask=lambda m: m))

    response = client.post("/api/chat", json={"message": "   "})

    assert response.status_code == 422
    api_module._COPILOT = None
