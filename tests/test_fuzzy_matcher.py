from factories import bank_txn, ledger_txn, settlement_txn

from backend.matching.fuzzy_matcher import (
    BUNDLED_RULE,
    FUZZY_SB_RULE,
    LS_DATE_WINDOW_RULE,
    LS_PARTIAL_REFUND_RULE,
    fuzzy_match_ledger_settlement,
    fuzzy_match_residuals,
    match_bundled_payouts,
)


def test_rounding_diff_fuzzy_match():
    stl = settlement_txn(utr="HDFCN202607020000000001", amount_paise=98000, day=2)
    bnk = bank_txn(
        reference="NEFT/HDFCN202607020000000001/RZPPAYOUT", amount_paise=98100, day=2
    )
    matches, rem_settlements, rem_bank = fuzzy_match_residuals([stl], [bnk])

    assert len(matches) == 1
    record = matches[0]
    assert record.match_stage == "fuzzy"
    assert record.rule_or_model == FUZZY_SB_RULE
    assert 0.0 < record.confidence_score <= 1.0
    assert record.details["utr_similarity"] == 100.0
    assert record.details["amount_diff_paise"] == 100
    assert record.details["date_diff_days"] == 0
    assert rem_settlements == []
    assert rem_bank == []


def test_ref_typo_fuzzy_match():
    stl = settlement_txn(utr="HDFCN202607020000000001", amount_paise=98000, day=2)
    bnk = bank_txn(
        reference="NEFT/HDFCN2026070200000000m1/RZPPAYOUT", amount_paise=98000, day=2
    )
    matches, rem_settlements, rem_bank = fuzzy_match_residuals([stl], [bnk])

    assert len(matches) == 1
    assert matches[0].details["utr_similarity"] >= 80.0
    assert rem_settlements == []
    assert rem_bank == []


def test_bank_side_date_drift_within_tolerance():
    stl = settlement_txn(utr="HDFCN202607020000000001", amount_paise=98000, day=2)
    bnk = bank_txn(
        reference="NEFT/HDFCN202607020000000001/RZPPAYOUT", amount_paise=98000, day=5
    )
    matches, rem_settlements, _ = fuzzy_match_residuals([stl], [bnk])

    assert len(matches) == 1
    assert matches[0].details["date_diff_days"] == 3
    assert rem_settlements == []


def test_dissimilar_ref_fails():
    stl = settlement_txn(utr="HDFCN202607020000000001", amount_paise=98000)
    bnk = bank_txn(reference="NEFT/ICIC000000000000999/RZPPAYOUT", amount_paise=98000)
    matches, rem_settlements, rem_bank = fuzzy_match_residuals([stl], [bnk])

    assert matches == []
    assert rem_settlements == [stl]
    assert rem_bank == [bnk]


def test_amount_beyond_tolerance_fails():
    stl = settlement_txn(utr="HDFCN202607020000000001", amount_paise=98000)
    bnk = bank_txn(
        reference="NEFT/HDFCN202607020000000001/RZPPAYOUT", amount_paise=98999
    )
    matches, rem_settlements, rem_bank = fuzzy_match_residuals([stl], [bnk])

    assert matches == []
    assert rem_settlements == [stl]
    assert rem_bank == [bnk]


def test_date_beyond_tolerance_fails():
    stl = settlement_txn(utr="HDFCN202607020000000001", amount_paise=98000, day=2)
    bnk = bank_txn(
        reference="NEFT/HDFCN202607020000000001/RZPPAYOUT", amount_paise=98000, day=20
    )
    matches, rem_settlements, rem_bank = fuzzy_match_residuals([stl], [bnk])

    assert matches == []
    assert rem_settlements == [stl]
    assert rem_bank == [bnk]


def test_best_candidate_wins_and_consumption():
    stl = settlement_txn(utr="HDFCN202607020000000001", amount_paise=98000, day=2)
    good = bank_txn(
        reference="NEFT/HDFCN202607020000000001/RZPPAYOUT",
        amount_paise=98000,
        day=2,
        bid="good",
    )
    worse = bank_txn(
        reference="NEFT/HDFCN202607020000000001/RZPPAYOUT",
        amount_paise=98150,
        day=4,
        bid="worse",
    )
    matches, rem_settlements, rem_bank = fuzzy_match_residuals([stl], [worse, good])

    assert len(matches) == 1
    assert matches[0].txn_ids == [stl.txn_id, good.txn_id]
    assert rem_bank == [worse]
    assert rem_settlements == []

    matches2, rem2, rem_bank2 = fuzzy_match_residuals([], rem_bank)
    assert matches2 == []
    assert rem_bank2 == [worse]


def test_bundled_payout_match():
    stl1 = settlement_txn(
        reference="order_1", utr="UTRBUNDLE1", amount_paise=49000, sid="1", day=2
    )
    stl2 = settlement_txn(
        reference="order_2", utr="UTRBUNDLE1", amount_paise=49000, sid="2", day=2
    )
    stl3 = settlement_txn(
        reference="order_3", utr="UTRBUNDLE1", amount_paise=49000, sid="3", day=2
    )
    bnk = bank_txn(reference="NEFT/UTRBUNDLE1/RZPPAYOUT", amount_paise=147000, day=3)
    matches, rem_settlements, rem_bank = match_bundled_payouts(
        [stl1, stl2, stl3], [bnk]
    )

    assert len(matches) == 1
    record = matches[0]
    assert record.rule_or_model == BUNDLED_RULE
    assert record.confidence_score == 0.95
    assert record.txn_ids == [stl1.txn_id, stl2.txn_id, stl3.txn_id, bnk.txn_id]
    assert record.details["settlement_count"] == 3
    assert rem_settlements == []
    assert rem_bank == []


def test_bundled_amount_mismatch_no_match():
    stl1 = settlement_txn(
        reference="order_1", utr="UTRBUNDLE1", amount_paise=49000, sid="1"
    )
    stl2 = settlement_txn(
        reference="order_2", utr="UTRBUNDLE1", amount_paise=49000, sid="2"
    )
    bnk = bank_txn(reference="NEFT/UTRBUNDLE1/RZPPAYOUT", amount_paise=99999)
    matches, rem_settlements, rem_bank = match_bundled_payouts([stl1, stl2], [bnk])

    assert matches == []
    assert rem_settlements == [stl1, stl2]
    assert rem_bank == [bnk]


def test_single_settlement_utr_not_treated_as_bundle():
    stl = settlement_txn(reference="order_1", utr="UTRSOLO", amount_paise=98000)
    bnk = bank_txn(reference="NEFT/UTRSOLO/RZPPAYOUT", amount_paise=98000)
    matches, rem_settlements, rem_bank = match_bundled_payouts([stl], [bnk])

    assert matches == []
    assert rem_settlements == [stl]
    assert rem_bank == [bnk]


def test_ls_fuzzy_date_window():
    led = ledger_txn(reference="order_1", day=1)
    stl = settlement_txn(reference="order_1", day=5)
    matches, rem_ledger, rem_settlements = fuzzy_match_ledger_settlement([led], [stl])

    assert len(matches) == 1
    assert matches[0].rule_or_model == LS_DATE_WINDOW_RULE
    assert matches[0].confidence_score == 0.9
    assert matches[0].details["date_diff_days"] == 4
    assert rem_ledger == []
    assert rem_settlements == []


def test_ls_fuzzy_partial_refund_type_mismatch():
    led = ledger_txn(
        reference="order_1", amount_paise=100000, day=1, txn_type="payment"
    )
    stl = settlement_txn(
        reference="order_1",
        amount_paise=78000,
        day=2,
        txn_type="refund",
        status="refund",
    )
    matches, rem_ledger, rem_settlements = fuzzy_match_ledger_settlement([led], [stl])

    assert len(matches) == 1
    assert matches[0].rule_or_model == LS_PARTIAL_REFUND_RULE
    assert matches[0].confidence_score == 0.88
    assert rem_ledger == []
    assert rem_settlements == []


def test_ls_fuzzy_never_pairs_chargebacks():
    led = ledger_txn(reference="order_1", day=1, txn_type="payment")
    stl = settlement_txn(
        reference="order_1", day=8, txn_type="chargeback", status="chargeback"
    )
    matches, rem_ledger, rem_settlements = fuzzy_match_ledger_settlement([led], [stl])

    assert matches == []
    assert rem_ledger == [led]
    assert rem_settlements == [stl]


def test_ls_fuzzy_date_window_beyond_window_fails():
    led = ledger_txn(reference="order_1", day=1)
    stl = settlement_txn(reference="order_1", day=2, month=8)
    matches, rem_ledger, rem_settlements = fuzzy_match_ledger_settlement([led], [stl])

    assert matches == []
    assert rem_ledger == [led]
    assert rem_settlements == [stl]
