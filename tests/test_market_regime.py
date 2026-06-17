"""Tests for the market-regime check (Marker 1): index close vs its own 200-day SMA."""
import pandas as pd
from sepa_checklist import MinerviniScanner


class _FakeProvider:
    def __init__(self, df):
        self.df = df

    def get_historical_data(self, *a, **k):
        return self.df


def _series(values):
    idx = pd.date_range("2025-01-01", periods=len(values), freq="D")
    return pd.DataFrame(
        {"Open": values, "High": values, "Low": values, "Close": values, "Volume": [1] * len(values)},
        index=idx,
    )


def test_regime_uptrend_above_200sma():
    df = _series([100 + i for i in range(250)])  # steadily rising -> last close > 200 SMA
    r = MinerviniScanner(_FakeProvider(df)).get_market_regime("^X")
    assert r["above_200sma"] is True
    assert r["benchmark"] == "^X"


def test_regime_riskoff_below_200sma():
    df = _series([350 - i for i in range(250)])  # steadily falling -> last close < 200 SMA
    r = MinerviniScanner(_FakeProvider(df)).get_market_regime("^X")
    assert r["above_200sma"] is False


def test_regime_unknown_when_insufficient_data():
    df = _series([100 + i for i in range(50)])  # < 200 rows
    r = MinerviniScanner(_FakeProvider(df)).get_market_regime("^X")
    assert r["above_200sma"] is None


def test_regime_unknown_when_empty():
    r = MinerviniScanner(_FakeProvider(pd.DataFrame())).get_market_regime("^X")
    assert r["above_200sma"] is None
