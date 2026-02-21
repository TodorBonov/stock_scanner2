"""Unit tests for currency_utils."""
import pytest
from unittest.mock import patch, MagicMock

from currency_utils import (
    usd_to_eur,
    get_eur_usd_rate,
    get_eur_usd_rate_with_date,
    warn_if_eur_rate_unavailable,
    format_eur_if_available,
)


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
