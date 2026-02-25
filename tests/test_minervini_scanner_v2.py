"""Tests for MinerviniScannerV2 (eligibility, reject result, grade bands)."""
import pandas as pd
import pytest
from unittest.mock import MagicMock

from minervini_scanner_v2 import MinerviniScannerV2


def test_scan_stock_insufficient_data_returns_reject():
    """When historical data is empty or too short, scan_stock returns eligible=False, grade REJECT."""
    provider = MagicMock()
    provider.get_historical_data.return_value = pd.DataFrame()
    provider.get_stock_info.return_value = {}
    scanner = MinerviniScannerV2(provider, benchmark="^GDAXI")
    result = scanner.scan_stock("FAKE")
    assert result["ticker"] == "FAKE"
    assert result["eligible"] is False
    assert result["grade"] == "REJECT"
    assert "reject_reason" in result
    assert "Insufficient" in result["reject_reason"]


def test_scan_stock_short_series_returns_reject():
    """When historical data has fewer than MIN_DATA_DAYS rows, scan_stock returns REJECT."""
    provider = MagicMock()
    provider.get_historical_data.return_value = pd.DataFrame({"Close": [100.0] * 100})
    provider.get_stock_info.return_value = {}
    scanner = MinerviniScannerV2(provider, benchmark="^GDAXI")
    result = scanner.scan_stock("FAKE")
    assert result["eligible"] is False
    assert result["grade"] == "REJECT"
    assert result.get("reject_reason") == "Insufficient historical data"


def test_reject_result_has_expected_shape():
    """_reject_result returns dict with all expected keys for downstream (05, 06, 07)."""
    provider = MagicMock()
    scanner = MinerviniScannerV2(provider, benchmark="^GDAXI")
    out = scanner._reject_result("TICK", "some reason")
    assert out["ticker"] == "TICK"
    assert out["eligible"] is False
    assert out["grade"] == "REJECT"
    assert out["reject_reason"] == "some reason"
    assert "composite_score" in out
    assert "base" in out and "type" in out["base"]
    assert "relative_strength" in out
    assert "breakout" in out
    assert "risk" in out


def test_grade_from_composite_bands():
    """_grade_from_composite returns A+, A, B, C, REJECT for score bands."""
    provider = MagicMock()
    scanner = MinerviniScannerV2(provider, benchmark="^GDAXI")
    assert scanner._grade_from_composite(85.0) == "A+"
    assert scanner._grade_from_composite(90.0) == "A+"
    assert scanner._grade_from_composite(80.0) == "A"
    assert scanner._grade_from_composite(75.0) == "A"
    assert scanner._grade_from_composite(70.0) == "B"
    assert scanner._grade_from_composite(65.0) == "B"
    assert scanner._grade_from_composite(60.0) == "C"
    assert scanner._grade_from_composite(55.0) == "C"
    assert scanner._grade_from_composite(54.9) == "REJECT"
    assert scanner._grade_from_composite(0.0) == "REJECT"
