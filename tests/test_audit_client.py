import json
from types import SimpleNamespace

from backend.audit import supabase_client
from backend.audit.supabase_client import AuditLogger
from backend.matching.match_record import build_match_record

FAKE_RUN_ID = "11111111-2222-3333-4444-555555555555"


class FakeQuery:
    def __init__(self, store, result):
        self._store = store
        self._result = result
        self.inserted = None

    def insert(self, rows):
        self.inserted = rows
        return self

    def execute(self):
        self._store.extend(self.inserted or [])
        return SimpleNamespace(data=self._result)


class FakeClient:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        self.tables.setdefault(name, [])
        result = [{"run_id": FAKE_RUN_ID}] if name == "recon_runs" else None
        return FakeQuery(self.tables[name], result)


def _sample_record():
    return build_match_record(
        txn_ids=["led_order_1", "stl_setl_1"],
        match_stage="fuzzy",
        confidence_score=0.91,
        rule_or_model="fuzzy_utr_amount_date",
        details={"amount_diff_paise": 12},
    )


def test_offline_when_env_missing(monkeypatch):
    monkeypatch.setattr(supabase_client, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    logger = AuditLogger()

    assert logger.is_connected is False
    assert logger.write_batch([_sample_record()]) == 0
    assert logger.create_run({"total_events": 86}) is None


def test_connects_with_explicit_credentials(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(supabase_client, "create_client", lambda url, key: fake)

    logger = AuditLogger(url="https://example.supabase.co", key="secret")

    assert logger.is_connected is True
    assert logger.client is fake


def test_connects_from_env(monkeypatch):
    monkeypatch.setattr(supabase_client, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "secret")
    fake = FakeClient()
    monkeypatch.setattr(supabase_client, "create_client", lambda url, key: fake)

    logger = AuditLogger()

    assert logger.is_connected is True


def test_client_init_failure_falls_back_offline(monkeypatch):
    def boom(url, key):
        raise RuntimeError("no network")

    monkeypatch.setattr(supabase_client, "create_client", boom)

    logger = AuditLogger(url="u", key="k")

    assert logger.is_connected is False
    assert logger.write_batch([_sample_record()]) == 0


def test_write_batch_payload_shape(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(supabase_client, "create_client", lambda url, key: fake)
    logger = AuditLogger(url="u", key="k")
    record = _sample_record()

    written = logger.write_batch([record], run_id="run-123")

    assert written == 1
    row = fake.tables["audit_log"][0]
    assert row["match_id"] == record.match_id
    assert row["run_id"] == "run-123"
    assert row["txn_ids"] == ["led_order_1", "stl_setl_1"]
    assert row["match_stage"] == "fuzzy"
    assert row["confidence_score"] == 0.91
    assert row["status"] == "auto_matched"
    assert row["rule_or_model"] == "fuzzy_utr_amount_date"
    assert row["matched_at"] == record.timestamp.isoformat()
    assert row["explanation"] == ""
    assert json.loads(row["details"]) == {"amount_diff_paise": 12}


def test_write_batch_insert_failure_returns_zero(monkeypatch):
    fake = FakeClient()

    def broken_execute(self):
        raise RuntimeError("db down")

    monkeypatch.setattr(supabase_client, "create_client", lambda url, key: fake)
    monkeypatch.setattr(FakeQuery, "execute", broken_execute)
    logger = AuditLogger(url="u", key="k")

    assert logger.write_batch([_sample_record()]) == 0


def test_create_run_payload_and_returned_id(monkeypatch):
    fake = FakeClient()
    captured = {}
    original_insert = FakeQuery.insert

    def spying_insert(self, rows):
        captured.update(rows)
        return original_insert(self, rows)

    monkeypatch.setattr(supabase_client, "create_client", lambda url, key: fake)
    monkeypatch.setattr(FakeQuery, "insert", spying_insert)
    logger = AuditLogger(url="u", key="k")

    run_id = logger.create_run(
        {
            "total_events": 86,
            "auto_matched_count": 77,
            "review_count": 7,
            "exception_count": 2,
            "match_rate": 0.8953,
            "processing_time_ms": 10.5,
        },
        seed=42,
    )

    assert run_id == FAKE_RUN_ID
    assert captured["seed"] == 42
    assert captured["total_events"] == 86
    assert captured["auto_matched_count"] == 77
    assert captured["review_count"] == 7
    assert captured["exception_count"] == 2
    assert captured["match_rate"] == 0.8953
    assert captured["processing_time_ms"] == 10.5
