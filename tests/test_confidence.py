from factories import bank_txn, ledger_txn, settlement_txn

from backend.matching.confidence import route_matches
from backend.matching.match_record import build_match_record


def _record(confidence):
    return build_match_record(
        txn_ids=["stl_x", "bnk_y"],
        match_stage="fuzzy",
        confidence_score=confidence,
        rule_or_model="test_rule",
    )


def test_threshold_routing():
    auto, review, exceptions = route_matches(
        [_record(1.0), _record(0.8), _record(0.3)], [], [], []
    )

    assert len(auto) == 1
    assert auto[0].status == "auto_matched"
    assert len(review) == 1
    assert review[0].status == "needs_review"
    assert len(exceptions) == 1
    assert exceptions[0].status == "exception"


def test_custom_thresholds():
    auto, review, exceptions = route_matches(
        [_record(0.82)], [], [], [], auto_threshold=0.8, review_threshold=0.4
    )
    assert len(auto) == 1


def test_pending_order_routes_to_needs_review():
    led = ledger_txn(reference="order_1", status="pending")
    auto, review, exceptions = route_matches([], [led], [], [])

    assert auto == []
    assert exceptions == []
    assert len(review) == 1
    assert review[0].rule_or_model == "pending_order"
    assert review[0].match_stage == "unmatched"
    assert review[0].confidence_score == 0.0
    assert review[0].txn_ids == [led.txn_id]


def test_duplicate_entry_routes_to_needs_review():
    led = ledger_txn(reference="order_1", suffix="#2")
    auto, review, exceptions = route_matches([], [led], [], [])

    assert len(review) == 1
    assert review[0].rule_or_model == "possible_duplicate"
    assert exceptions == []


def test_unresolved_ledger_routes_to_exception():
    led = ledger_txn(reference="order_1", status="completed")
    auto, review, exceptions = route_matches([], [led], [], [])

    assert review == []
    assert len(exceptions) == 1
    assert exceptions[0].rule_or_model == "no_match_found"


def test_unmatched_settlement_and_bank_route_to_exception():
    stl = settlement_txn()
    bnk = bank_txn()
    auto, review, exceptions = route_matches([], [], [stl], [bnk])

    assert len(exceptions) == 2
    assert exceptions[0].txn_ids == [stl.txn_id]
    assert exceptions[1].txn_ids == [bnk.txn_id]
