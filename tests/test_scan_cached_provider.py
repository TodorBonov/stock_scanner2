"""
Tests for CachedDataProviderV2.calculate_relative_strength (step 04).

Verifies RS is computed from the cached snapshot (no live Yahoo calls) and that
the live provider is only used as a fallback when a series is missing from cache.

The step module's name starts with a digit, so it is loaded via importlib.
"""
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

SCAN_PATH = Path(__file__).resolve().parent.parent / "04_scan.py"


def _load_scan_module():
    spec = importlib.util.spec_from_file_location("scan04", SCAN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scan04 = _load_scan_module()
CachedDataProviderV2 = scan04.CachedDataProviderV2


def _cached_entry(daily_growth: float, n: int = 250, start: float = 100.0):
    """Build a cache entry (>=200 rows) with closes growing at a fixed daily rate."""
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    data = []
    price = start
    for _ in range(n):
        data.append({
            "Open": round(price, 4),
            "High": round(price * 1.01, 4),
            "Low": round(price * 0.99, 4),
            "Close": round(price, 4),
            "Volume": 1_000_000,
        })
        price *= (1 + daily_growth)
    return {
        "data_available": True,
        "historical_data": {
            "index": [str(d) for d in dates],
            "data": data,
        },
        "stock_info": {"currency": "USD"},
    }


class TestCachedRelativeStrength:
    def test_uses_cache_and_does_not_call_live_provider(self):
        cached = {
            "AAA": _cached_entry(0.0020),   # outperformer
            "^BENCH": _cached_entry(0.0005),
        }
        live = MagicMock()
        provider = CachedDataProviderV2(cached, live)

        rs = provider.calculate_relative_strength("AAA", "^BENCH", period=252)

        assert rs and "error" not in rs
        assert rs["relative_strength"] > 0          # AAA grew faster than benchmark
        assert rs["stock_return"] > rs["benchmark_return"]
        assert 0 <= rs["rs_rating"] <= 100
        # Crucially: no live network calls were made.
        live.get_historical_data.assert_not_called()
        live.calculate_relative_strength.assert_not_called()

    def test_underperformer_has_negative_rs(self):
        cached = {
            "BBB": _cached_entry(0.0002),   # slower than benchmark
            "^BENCH": _cached_entry(0.0010),
        }
        provider = CachedDataProviderV2(cached, MagicMock())
        rs = provider.calculate_relative_strength("BBB", "^BENCH", period=252)
        assert rs["relative_strength"] < 0

    def test_cache_only_no_live_when_ticker_missing(self):
        # The scan provider is cache-only: a cache miss must NOT trigger any live Yahoo call
        # (that's what turned a 40s scan into 60+ min). It returns empty/{} instead.
        cached = {"^BENCH": _cached_entry(0.0005)}
        live = MagicMock()
        provider = CachedDataProviderV2(cached, live)

        rs = provider.calculate_relative_strength("ZZZ", "^BENCH", period=252)
        assert rs == {}
        assert provider.get_historical_data("ZZZ").empty
        assert provider.get_stock_info("ZZZ") == {}
        # No live calls of any kind.
        live.calculate_relative_strength.assert_not_called()
        live.get_historical_data.assert_not_called()
        live.get_stock_info.assert_not_called()
