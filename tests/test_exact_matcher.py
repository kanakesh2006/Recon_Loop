from decimal import Decimal

from factories import bank_txn, ledger_txn, settlement_txn

from backend.matching.exact_matcher import (
    LS_EXACT_RULE,
    SB_EXACT_RULE,
    exact_match_ledger_settlement,
    exact_match_settlement_bank,
)


def test_clean_exact_ls_match():
    led = ledger_txn(reference="order_1", amount_paise=100000, day=1)
    stl = settlement_txn(reference="order_1", amount_paise=98000, day=2)
    matches, unmatched_ledger, unmatched_settlements = exact_match_ledger_settlement(
        [led], [stl]
    )

    assert len(matches) == 1
    assert matches[0].match_stage == "exact"
    assert matches[0].confidence_score == 1.0
    assert matches[0].rule_or_model == LS_EXACT_RULE
    assert matches[0].txn_ids == [led.txn_id, stl.txn_id]
    assert unmatched_ledger == []
    assert unmatched_settlements == []


def test_ls_amounts_are_not_compared_gross_vs_net():
    led = ledger_txn(reference="order_1", amount_paise=100000, day=1)
    stl = settlement_txn(reference="order_1", amount_paise=1, day=2)
    matches, _, unmatched_settlements = exact_match_ledger_settlement([led], [stl])

    assert len(matches) == 1
    assert unmatched_settlements == []


def test_pending_order_stays_unmatched():
    led = ledger_txn(reference="order_1", status="pending")
    matches, unmatched_ledger, unmatched_settlements = exact_match_ledger_settlement(
        [led], []
    )

    assert matches == []
    assert unmatched_ledger == [led]
    assert unmatched_settlements == []


def test_duplicate_reference_first_wins():
    led1 = ledger_txn(reference="order_1", suffix="")
    led2 = ledger_txn(reference="order_1", suffix="#2")
    stl = settlement_txn(reference="order_1")
    matches, unmatched_ledger, unmatched_settlements = exact_match_ledger_settlement(
        [led1, led2], [stl]
    )

    assert len(matches) == 1
    assert matches[0].txn_ids == [led1.txn_id, stl.txn_id]
    assert unmatched_ledger == [led2]
    assert unmatched_settlements == []


def test_date_gap_beyond_exact_window_fails():
    led = ledger_txn(reference="order_1", day=1)
    stl = settlement_txn(reference="order_1", day=6)
    matches, unmatched_ledger, unmatched_settlements = exact_match_ledger_settlement(
        [led], [stl]
    )

    assert matches == []
    assert unmatched_ledger == [led]
    assert unmatched_settlements == [stl]


def test_chargeback_type_mismatch_fails_ls():
    led = ledger_txn(reference="order_1", txn_type="payment", status="completed")
    stl = settlement_txn(
        reference="order_1", txn_type="chargeback", status="chargeback"
    )
    matches, unmatched_ledger, unmatched_settlements = exact_match_ledger_settlement(
        [led], [stl]
    )

    assert matches == []
    assert unmatched_ledger == [led]
    assert unmatched_settlements == [stl]


def test_clean_exact_sb_match():
    stl = settlement_txn(amount_paise=98000, day=2)
    bnk = bank_txn(amount_paise=98000, day=2)
    matches, unmatched_settlements, unmatched_bank = exact_match_settlement_bank(
        [stl], [bnk]
    )

    assert len(matches) == 1
    assert matches[0].confidence_score == 1.0
    assert matches[0].rule_or_model == SB_EXACT_RULE
    assert matches[0].txn_ids == [stl.txn_id, bnk.txn_id]
    assert unmatched_settlements == []
    assert unmatched_bank == []


def test_sb_amount_mismatch_fails():
    stl = settlement_txn(amount_paise=98000)
    bnk = bank_txn(amount_paise=99000)
    matches, unmatched_settlements, unmatched_bank = exact_match_settlement_bank(
        [stl], [bnk]
    )

    assert matches == []
    assert unmatched_settlements == [stl]
    assert unmatched_bank == [bnk]


def test_chargeback_pair_matches_on_type_and_utr():
    utr = "HDFCN202607100000000009"
    stl = settlement_txn(
        reference="order_9",
        utr=utr,
        amount_paise=250000,
        txn_type="chargeback",
        status="chargeback",
    )
    bnk = bank_txn(
        reference=f"REV/{utr}/CHARGEBACK",
        amount_paise=250000,
        direction="dr",
        txn_type="chargeback",
    )
    matches, unmatched_settlements, unmatched_bank = exact_match_settlement_bank(
        [stl], [bnk]
    )

    assert len(matches) == 1
    assert unmatched_settlements == []
    assert unmatched_bank == []


def test_bundled_settlements_fail_1to1_and_stay_unconsumed():
    stl1 = settlement_txn(
        reference="order_1", utr="UTRBUNDLE1", amount_paise=49000, sid="1"
    )
    stl2 = settlement_txn(
        reference="order_2", utr="UTRBUNDLE1", amount_paise=49000, sid="2"
    )
    bnk = bank_txn(reference="NEFT/UTRBUNDLE1/RZPPAYOUT", amount_paise=98000)
    matches, unmatched_settlements, unmatched_bank = exact_match_settlement_bank(
        [stl1, stl2], [bnk]
    )

    assert matches == []
    assert unmatched_settlements == [stl1, stl2]
    assert unmatched_bank == [bnk]


def test_refund_settlement_matches_bank_credit():
    stl = settlement_txn(amount_paise=98000, txn_type="refund", status="refund")
    bnk = bank_txn(amount_paise=98000, txn_type="payment")
    matches, unmatched_settlements, unmatched_bank = exact_match_settlement_bank(
        [stl], [bnk]
    )

    assert len(matches) == 1
    assert unmatched_settlements == []
    assert unmatched_bank == []


def test_ref_typo_utr_fails_exact():
    stl = settlement_txn(utr="HDFCN202607020000000001", amount_paise=98000)
    bnk = bank_txn(
        reference="NEFT/HDFCN202607020000000002/RZPPAYOUT", amount_paise=98000
    )
    matches, unmatched_settlements, unmatched_bank = exact_match_settlement_bank(
        [stl], [bnk]
    )

    assert matches == []
    assert unmatched_settlements == [stl]
    assert unmatched_bank == [bnk]


def test_bank_row_consumed_after_match():
    stl1 = settlement_txn(
        reference="order_1", utr="UTRDUPE", amount_paise=1000, sid="1"
    )
    stl2 = settlement_txn(
        reference="order_2", utr="UTRDUPE", amount_paise=1000, sid="2"
    )
    bnk = bank_txn(reference="NEFT/UTRDUPE/RZPPAYOUT", amount_paise=1000)
    matches, unmatched_settlements, unmatched_bank = exact_match_settlement_bank(
        [stl1, stl2], [bnk]
    )

    assert len(matches) == 1
    assert matches[0].txn_ids == [stl1.txn_id, bnk.txn_id]
    assert unmatched_settlements == [stl2]
    assert unmatched_bank == []
