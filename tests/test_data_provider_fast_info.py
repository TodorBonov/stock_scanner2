"""Tests for the lightweight fast_info path in StockDataProvider.get_stock_info(fast=True)."""
from unittest.mock import MagicMock, patch

import data_provider
from data_provider import StockDataProvider


class _FakeFastInfo:
    """Mimics yfinance FastInfo: supports both attribute and item access."""
    def __init__(self, d):
        self._d = d

    def __getitem__(self, k):
        return self._d[k]  # raises KeyError when missing

    def __getattr__(self, k):
        try:
            return self.__dict__["_d"][k]
        except KeyError:
            raise AttributeError(k)


def _provider_with_fast_info(fast_info_dict):
    tk = MagicMock()
    tk.fast_info = _FakeFastInfo(fast_info_dict)
    # Accessing .info should fail the test if the fast path touches it.
    type(tk).info = property(lambda self: (_ for _ in ()).throw(AssertionError("heavy .info was called on the fast path")))
    p = StockDataProvider(prefer_yfinance=True)
    return p, tk


def test_fast_path_uses_fast_info_only():
    p, tk = _provider_with_fast_info({
        "currency": "USD", "last_price": 150.0, "market_cap": 2.0e12,
        "year_high": 200.0, "year_low": 100.0,
    })
    with patch.object(data_provider, "yf") as yfmock:
        yfmock.Ticker.return_value = tk
        info = p.get_stock_info("AAPL", fast=True)
    assert info["source"] == "yfinance_fast"
    assert info["currency"] == "USD"
    assert info["current_price"] == 150.0
    assert info["52_week_high"] == 200.0
    assert info["52_week_low"] == 100.0


def test_fast_path_handles_eur_currency():
    p, tk = _provider_with_fast_info({"currency": "EUR", "last_price": 50.0})
    with patch.object(data_provider, "yf") as yfmock:
        yfmock.Ticker.return_value = tk
        info = p.get_stock_info("RWE.DE", fast=True)
    assert info["currency"] == "EUR"
    assert info["source"] == "yfinance_fast"


def test_fast_path_falls_back_when_no_currency():
    # fast_info without currency -> fast path returns {}, get_stock_info falls through.
    tk_fast = MagicMock()
    tk_fast.fast_info = _FakeFastInfo({"last_price": 10.0})  # no currency
    p = StockDataProvider(prefer_yfinance=True)
    with patch.object(data_provider, "yf") as yfmock:
        yfmock.Ticker.return_value = tk_fast
        # Heavy .info also returns nothing usable -> overall error dict (no crash).
        tk_fast.info = {}
        info = p.get_stock_info("ZZZ", fast=True)
    assert "error" in info or info.get("source") != "yfinance_fast"
