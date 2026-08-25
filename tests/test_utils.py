from datetime import date
from decimal import Decimal

from backend.matching.utils import amount_diff_paise, date_diff_days, extract_utr


def test_extract_utr_standard_neft():
    assert (
        extract_utr("NEFT/HDFCN20260705692749116/RZPPAYOUT") == "HDFCN20260705692749116"
    )


def test_extract_utr_reversal_format():
    assert (
        extract_utr("REV/HDFCN20260705692749116/CHARGEBACK") == "HDFCN20260705692749116"
    )


def test_extract_utr_no_slash_fallback():
    assert extract_utr("HDFCN20260705692749116") == "HDFCN20260705692749116"


def test_extract_utr_empty_returns_none():
    assert extract_utr("") is None
    assert extract_utr("   ") is None


def test_amount_diff_paise():
    assert amount_diff_paise(Decimal("98000"), Decimal("98150")) == Decimal(150)
    assert amount_diff_paise(Decimal("98150"), Decimal("98000")) == Decimal(150)
    assert amount_diff_paise(Decimal("100"), Decimal("100")) == Decimal(0)


def test_date_diff_days():
    assert date_diff_days(date(2026, 7, 5), date(2026, 7, 2)) == 3
    assert date_diff_days(date(2026, 7, 2), date(2026, 7, 5)) == 3
    assert date_diff_days(date(2026, 7, 2), date(2026, 7, 2)) == 0
