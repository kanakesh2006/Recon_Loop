from factories import bank_txn, ledger_txn, settlement_txn

from backend.matching.exact_matcher import (
    exact_match_ledger_settlement,
    exact_match_settlement_bank,
)
from backend.matching.match_record import build_match_record
from backend.matching.three_way import assemble_three_way_matches


def _ls(led, stl):
    return exact_match_ledger_settlement([led], [stl])[0][0]


def _sb(stl, bnk):
    return exact_match_settlement_bank([stl], [bnk])[0][0]


def test_full_three_way_merge():
    led = ledger_txn(reference="order_1", day=1)
    stl = settlement_txn(reference="order_1", day=2)
    bnk = bank_txn(day=2)
    records = assemble_three_way_matches([_ls(led, stl)], [_sb(stl, bnk)])

    assert len(records) == 1
    record = records[0]
    assert record.txn_ids == [led.txn_id, stl.txn_id, bnk.txn_id]
    assert record.match_stage == "exact"
    assert record.confidence_score == 1.0
    assert record.status == "auto_matched"
    assert (
        record.rule_or_model == "exact_ledger_settlement_ref+exact_settlement_bank_utr"
    )


def test_ls_only_becomes_two_way_needs_review():
    led = ledger_txn(reference="order_1", day=1)
    stl = settlement_txn(reference="order_1", day=2)
    records = assemble_three_way_matches([_ls(led, stl)], [])

    assert len(records) == 1
    record = records[0]
    assert record.txn_ids == [led.txn_id, stl.txn_id]
    assert record.confidence_score == 0.8
    assert record.status == "needs_review"


def test_sb_only_becomes_two_way_needs_review():
    stl = settlement_txn(txn_type="chargeback", status="chargeback")
    bnk = bank_txn(direction="dr", txn_type="chargeback")
    records = assemble_three_way_matches([], [_sb(stl, bnk)])

    assert len(records) == 1
    record = records[0]
    assert record.txn_ids == [stl.txn_id, bnk.txn_id]
    assert record.confidence_score == 0.8
    assert record.status == "needs_review"


def test_merged_confidence_is_weakest_link():
    led = ledger_txn(reference="order_1", day=1)
    stl = settlement_txn(reference="order_1", day=2)
    bnk = bank_txn(day=2)
    ls_match = build_match_record(
        [led.txn_id, stl.txn_id], "fuzzy", 0.9, "fuzzy_ls_ref_date_window"
    )
    records = assemble_three_way_matches([ls_match], [_sb(stl, bnk)])

    assert len(records) == 1
    record = records[0]
    assert record.confidence_score == 0.9
    assert record.match_stage == "fuzzy"


def test_bundled_merge_single_record():
    leds = [ledger_txn(reference=f"order_{i}", day=1) for i in (1, 2, 3)]
    stls = [
        settlement_txn(
            reference=f"order_{i}", utr="UTRB1", amount_paise=49000, sid=str(i)
        )
        for i in (1, 2, 3)
    ]
    bnk = bank_txn(reference="NEFT/UTRB1/RZPPAYOUT", amount_paise=147000, day=3)

    ls_matches = []
    for led, stl in zip(leds, stls):
        ls_matches.append(_ls(led, stl))
    bundled = build_match_record(
        [s.txn_id for s in stls] + [bnk.txn_id],
        "fuzzy",
        0.95,
        "bundled_payout_utr",
        details={"settlement_count": 3},
    )
    records = assemble_three_way_matches(ls_matches, [bundled])

    assert len(records) == 1
    record = records[0]
    assert record.txn_ids == [
        leds[0].txn_id,
        leds[1].txn_id,
        leds[2].txn_id,
        stls[0].txn_id,
        stls[1].txn_id,
        stls[2].txn_id,
        bnk.txn_id,
    ]
    assert record.confidence_score == 0.95
    assert record.match_stage == "fuzzy"
    assert record.details["settlement_count"] == 3
