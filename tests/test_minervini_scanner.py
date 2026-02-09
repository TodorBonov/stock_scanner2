"""Minimal tests for minervini_scanner."""
import pandas as pd
import pytest
from unittest.mock import MagicMock

from minervini_scanner import MinerviniScanner


def test_scan_stock_insufficient_data_returns_f():
    """When historical data is empty or too short, scan_stock returns F grade and error."""
    provider = MagicMock()
    provider.get_historical_data.return_value = pd.DataFrame()
    scanner = MinerviniScanner(provider, benchmark="^GDAXI")
    result = scanner.scan_stock("FAKE")
    assert result["ticker"] == "FAKE"
    assert result["overall_grade"] == "F"
    assert result["meets_criteria"] is False
    assert "error" in result
    assert "Insufficient" in result["error"]


def test_scan_stock_insufficient_data_short_series():
    """When historical data has fewer than 200 rows, scan_stock returns F grade."""
    provider = MagicMock()
    # Fewer than 200 rows
    provider.get_historical_data.return_value = pd.DataFrame({"Close": [100.0] * 100})
    scanner = MinerviniScanner(provider, benchmark="^GDAXI")
    result = scanner.scan_stock("FAKE")
    assert result["overall_grade"] == "F"
    assert result.get("error") == "Insufficient historical data"
