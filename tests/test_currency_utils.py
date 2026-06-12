"""Unit tests for currency_utils."""
import pytest
from unittest.mock import patch, MagicMock

import currency_utils
from currency_utils import (
    usd_to_eur,
    get_eur_usd_rate,
    get_eur_usd_rate_with_date,
    warn_if_eur_rate_unavailable,
    format_eur_if_available,
    _split_minor_unit,
    get_fx_rate_to_usd,
    convert_ohlcv_and_info_to_usd,
)


@pytest.fixture(autouse=True)
def _clear_fx_cache():
    """FX rates are cached for the process lifetime; clear between tests."""
    currency_utils._FX_TO_USD_CACHE.clear()
    yield
    currency_utils._FX_TO_USD_CACHE.clear()


class TestUsdToEur:
    def test_basic(self):
        # 108 USD / 1.08 = 100 EUR
        assert usd_to_eur(108.0, 1.08) == pytest.approx(100.0)

    def test_rate_none_returns_none(self):
        assert usd_to_eur(100.0, None) is None

    def test_rate_zero_returns_none(self):
        assert usd_to_eur(100.0, 0.0) is None

    def test_amount_none_returns_none(self):
        assert usd_to_eur(None, 1.08) is None


class TestGetEurUsdRate:
    def test_get_eur_usd_rate_returns_rate_from_with_date(self):
        with patch("currency_utils.get_eur_usd_rate_with_date", return_value=(1.09, "2026-02-20")):
            rate = get_eur_usd_rate()
            assert rate == 1.09

    def test_get_eur_usd_rate_with_date_return_shape(self):
        # With real yfinance we get (rate, date); with exception we get (None, None)
        rate, date = get_eur_usd_rate_with_date()
        assert (rate is None and date is None) or (isinstance(rate, (int, float)) and (date is None or isinstance(date, str)))


class TestFormatEurIfAvailable:
    def test_returns_formatted_eur_when_rate_ok(self):
        assert "100.00 EUR" in format_eur_if_available(108.0, 1.08)
        assert "50.00 EUR" in format_eur_if_available(54.0, 1.08)

    def test_returns_empty_when_rate_none(self):
        assert format_eur_if_available(108.0, None) == ""

    def test_decimals(self):
        assert "100.1 EUR" in format_eur_if_available(108.11, 1.08, decimals=1)


class TestWarnIfEurRateUnavailable:
    def test_no_warning_when_no_eur(self, caplog):
        warn_if_eur_rate_unavailable(False, None)
        assert "EUR" not in (caplog.text or "")

    def test_no_warning_when_rate_available(self, caplog):
        warn_if_eur_rate_unavailable(True, 1.08)
        assert "unavailable" not in (caplog.text or "").lower() or "rate" not in (caplog.text or "").lower()

    def test_warning_when_eur_and_rate_none(self, caplog):
        import logging
        caplog.set_level(logging.WARNING)
        warn_if_eur_rate_unavailable(True, None)
        assert "EUR" in caplog.text and "unavailable" in caplog.text.lower()


class TestSplitMinorUnit:
    def test_pence_maps_to_gbp_with_divisor_100(self):
        assert _split_minor_unit("GBp") == ("GBP", 100.0)

    def test_gbx_maps_to_gbp(self):
        assert _split_minor_unit("GBX") == ("GBP", 100.0)

    def test_plain_currency_uppercased_divisor_one(self):
        assert _split_minor_unit("chf") == ("CHF", 1.0)

    def test_usd_passthrough(self):
        assert _split_minor_unit("USD") == ("USD", 1.0)


class TestGetFxRateToUsd:
    def test_usd_is_one_without_network(self):
        assert get_fx_rate_to_usd("USD") == 1.0

    def test_empty_currency_returns_none(self):
        assert get_fx_rate_to_usd("") is None

    def test_gbp_uses_pair_rate(self):
        with patch("currency_utils._fetch_yahoo_fx_with_date", return_value=(1.25, "2026-06-11")):
            assert get_fx_rate_to_usd("GBP") == pytest.approx(1.25)

    def test_pence_divides_pair_rate_by_100(self):
        with patch("currency_utils._fetch_yahoo_fx_with_date", return_value=(1.25, "2026-06-11")):
            # 1 pence = 1/100 GBP = 0.0125 USD
            assert get_fx_rate_to_usd("GBp") == pytest.approx(0.0125)

    def test_rate_unavailable_returns_none(self):
        with patch("currency_utils._fetch_yahoo_fx_with_date", return_value=(None, None)):
            assert get_fx_rate_to_usd("SEK") is None

    def test_result_is_cached(self):
        with patch("currency_utils._fetch_yahoo_fx_with_date", return_value=(1.1, None)) as m:
            get_fx_rate_to_usd("CHF")
            get_fx_rate_to_usd("CHF")
            assert m.call_count == 1


class TestConvertOhlcvAndInfoToUsd:
    def _hist(self):
        return {
            "index": ["2026-06-10", "2026-06-11"],
            "data": [
                {"Open": 100.0, "High": 110.0, "Low": 90.0, "Close": 105.0, "Volume": 1000},
                {"Open": 105.0, "High": 115.0, "Low": 95.0, "Close": 110.0, "Volume": 2000},
            ],
        }

    def test_usd_is_noop(self):
        info = {"currency": "USD", "current_price": 105.0}
        hist = self._hist()
        assert convert_ohlcv_and_info_to_usd(hist, info) is False
        assert hist["data"][0]["Close"] == 105.0
        assert info["currency"] == "USD"
        assert "original_currency" not in info

    def test_pence_converts_by_dividing_100(self):
        # 1.25 USD per GBP -> 0.0125 USD per pence
        with patch("currency_utils._fetch_yahoo_fx_with_date", return_value=(1.25, None)):
            info = {"currency": "GBp", "current_price": 5000.0, "52_week_high": 6000.0}
            hist = self._hist()
            assert convert_ohlcv_and_info_to_usd(hist, info) is True
            assert hist["data"][0]["Close"] == pytest.approx(105.0 * 0.0125)
            assert info["current_price"] == pytest.approx(5000.0 * 0.0125)
            assert info["52_week_high"] == pytest.approx(6000.0 * 0.0125)
            assert info["currency"] == "USD"
            assert info["original_currency"] == "GBp"

    def test_eur_conversion(self):
        with patch("currency_utils._fetch_yahoo_fx_with_date", return_value=(1.08, None)):
            info = {"currency": "EUR", "current_price": 100.0}
            hist = self._hist()
            assert convert_ohlcv_and_info_to_usd(hist, info) is True
            assert hist["data"][1]["Open"] == pytest.approx(105.0 * 1.08)
            assert info["currency"] == "USD"
            assert info["original_currency"] == "EUR"

    def test_rate_unavailable_marks_flag_and_leaves_data(self):
        with patch("currency_utils._fetch_yahoo_fx_with_date", return_value=(None, None)):
            info = {"currency": "SEK", "current_price": 100.0}
            hist = self._hist()
            assert convert_ohlcv_and_info_to_usd(hist, info) is False
            assert hist["data"][0]["Close"] == 105.0  # unchanged
            assert info["currency"] == "SEK"          # unchanged
            assert info["original_currency"] == "SEK"
            assert info["rate_unavailable"] is True

    def test_missing_currency_is_noop(self):
        info = {"current_price": 100.0}
        assert convert_ohlcv_and_info_to_usd(self._hist(), info) is False
        assert info["current_price"] == 100.0
