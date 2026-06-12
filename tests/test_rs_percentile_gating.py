"""
Tests for the RS-percentile grade-cap gating (review item 4).

A single-ticker or tiny scan can't produce a meaningful universe percentile, so
scan_universe must pass rs_percentile=None for small universes — otherwise the
0th-percentile cap forces every A+/A down a grade. Large universes still rank.
"""
from unittest.mock import MagicMock

import pandas as pd

from sepa_scorer import MinerviniScannerV2
from config import MIN_UNIVERSE_FOR_RS_PERCENTILE


def _make_df(n: int = 120, growth: float = 0.001) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    close = [100.0 * (1 + growth) ** i for i in range(n)]
    return pd.DataFrame(
        {"Open": close, "High": close, "Low": close, "Close": close, "Volume": [1_000_000] * n},
        index=idx,
    )


class _FakeProvider:
    """Returns a per-ticker history; everything else is unused by scan_universe."""
    def __init__(self, per_ticker):
        self.per_ticker = per_ticker

    def get_historical_data(self, ticker, period="1y", interval="1d"):
        return self.per_ticker.get(ticker, _make_df())

    def get_stock_info(self, ticker):
        return {}

    def calculate_relative_strength(self, *a, **k):
        return {}


def _rs_percentiles_passed(n_tickers: int):
    """Run scan_universe over n synthetic tickers; return the rs_percentile passed to each scan_stock."""
    tickers = [f"T{i}" for i in range(n_tickers)]
    # Vary growth slightly per ticker so 3M returns differ.
    per_ticker = {t: _make_df(growth=0.0005 + 0.0001 * i) for i, t in enumerate(tickers)}
    scanner = MinerviniScannerV2(_FakeProvider(per_ticker), benchmark="^BENCH")
    scanner.scan_stock = MagicMock(side_effect=lambda t, **kw: {"ticker": t})
    scanner.scan_universe(tickers)
    return [kw.get("rs_percentile") for _, kw in scanner.scan_stock.call_args_list]


class TestRsPercentileGating:
    def test_single_ticker_gets_none(self):
        passed = _rs_percentiles_passed(1)
        assert passed == [None]

    def test_small_universe_all_none(self):
        n = MIN_UNIVERSE_FOR_RS_PERCENTILE - 1
        passed = _rs_percentiles_passed(n)
        assert len(passed) == n
        assert all(p is None for p in passed)

    def test_large_universe_gets_percentiles(self):
        n = MIN_UNIVERSE_FOR_RS_PERCENTILE
        passed = _rs_percentiles_passed(n)
        assert len(passed) == n
        assert all(p is not None for p in passed)
        # Percentiles span the 0..100 range (strictly-less ranking).
        assert min(passed) == 0.0
        assert max(passed) > 0.0
