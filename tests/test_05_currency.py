"""Tests for 05_chatgpt_validation_advanced currency handling (no double conversion)."""
import pytest
import sys
from pathlib import Path

# Import format_chart_data_for_advanced and the rate-selection logic
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from importlib.util import spec_from_file_location, module_from_spec
_spec = spec_from_file_location("validation_advanced", _root / "05_chatgpt_validation_advanced.py")
_mod = module_from_spec(_spec)
_spec.loader.exec_module(_mod)
format_chart_data_for_advanced = _mod.format_chart_data_for_advanced


def test_chart_data_without_rate_leaves_prices_unchanged():
    """When eur_to_usd_rate is None, prices in chart data are not converted (USD/cached case)."""
    scan = {
        "ticker": "AAPL",
        "stock_info": {"currency": "USD", "company_name": "Apple Inc."},
        "overall_grade": "A",
        "detailed_analysis": {"current_price": 150.0, "52_week_high": 180.0, "52_week_low": 120.0},
        "checklist": {},
        "buy_sell_prices": {},
    }
    text = format_chart_data_for_advanced(scan, eur_to_usd_rate=None)
    assert "150.00" in text
    assert "180.00" in text
    assert "120.00" in text
    assert "(All prices below converted" not in text


def test_chart_data_with_rate_converts_prices():
    """When eur_to_usd_rate is set (e.g. 1.08), prices are converted EUR->USD."""
    scan = {
        "ticker": "RWE",
        "stock_info": {"currency": "EUR", "company_name": "RWE AG"},
        "overall_grade": "A",
        "detailed_analysis": {"current_price": 100.0, "52_week_high": 110.0, "52_week_low": 90.0},
        "checklist": {},
        "buy_sell_prices": {},
    }
    text = format_chart_data_for_advanced(scan, eur_to_usd_rate=1.08)
    assert "108.00" in text  # 100 * 1.08
    assert "(All prices below converted" in text


def test_no_double_conversion_scan_usd_implies_no_rate():
    """When position is EUR but scan has currency USD (cached), we must pass rate=None to avoid double conversion.
    This test documents the intended behavior: callers should pass rate only when scan is in EUR."""
    scan_usd = {
        "ticker": "RWED",
        "stock_info": {"currency": "USD", "original_currency": "EUR", "company_name": "RWE"},
        "detailed_analysis": {"current_price": 51.94},
        "checklist": {},
        "buy_sell_prices": {},
    }
    # Simulate what 07 does: rate = only when scan_currency == "EUR"
    scan_currency = (scan_usd.get("stock_info") or {}).get("currency") or ""
    rate_should_be_none = scan_currency != "EUR"
    assert rate_should_be_none is True
    text = format_chart_data_for_advanced(scan_usd, eur_to_usd_rate=None)
    assert "51.94" in text
