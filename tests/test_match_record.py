from backend.matching.match_record import MatchRecord, build_match_record


def test_create_with_factory_defaults():
    record = build_match_record(
        txn_ids=["led_order_1", "stl_setl_1"],
        match_stage="exact",
        confidence_score=1.0,
        rule_or_model="exact_ledger_settlement_ref",
    )
    assert record.match_id
    assert record.txn_ids == ["led_order_1", "stl_setl_1"]
    assert record.match_stage == "exact"
    assert record.confidence_score == 1.0
    assert record.status == "auto_matched"
    assert record.explanation == ""
    assert record.details == {}
    assert record.timestamp is not None


def test_json_roundtrip():
    record = build_match_record(
        txn_ids=["stl_setl_1", "bnk_cr_X"],
        match_stage="fuzzy",
        confidence_score=0.91,
        rule_or_model="fuzzy_utr_amount_date",
        details={"utr_similarity": 97.7, "amount_diff_paise": 12},
    )
    restored = MatchRecord.model_validate_json(record.model_dump_json())
    assert restored == record
    assert restored.details["utr_similarity"] == 97.7


def test_confidence_must_be_numeric():
    record = build_match_record(
        [], "unmatched", 0.0, "no_match_found", status="exception"
    )
    assert record.confidence_score == 0.0
    assert record.status == "exception"
    assert record.match_stage == "unmatched"
