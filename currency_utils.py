"""
Currency conversion for report display.
All data and calculations stay in USD; convert to EUR only at report time for positions bought in EUR.
Uses Yahoo Finance EURUSD=X (USD per 1 EUR) for the rate.
"""
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# Yahoo ticker: EUR/USD rate = how many USD per 1 EUR
EURUSD_YAHOO_TICKER = "EURUSD=X"


def get_eur_usd_rate_with_date() -> Tuple[Optional[float], Optional[str]]:
    """
    Get latest EUR/USD rate and its date from Yahoo Finance (USD per 1 EUR).
    Returns (rate, date_iso) or (None, None) if unavailable.
    date_iso is YYYY-MM-DD from the history index.
    """
    try:
        import yfinance as yf
        t = yf.Ticker(EURUSD_YAHOO_TICKER)
        hist = t.history(period="5d", interval="1d")
        if hist is not None and not hist.empty and "Close" in hist.columns:
            rate = float(hist["Close"].iloc[-1])
            date_ts = hist.index[-1]
            date_iso = str(date_ts)[:10] if date_ts is not None else None
            return (rate, date_iso)
        info = getattr(t, "info", None) or {}
        if isinstance(info, dict) and info.get("regularMarketPrice"):
            return (float(info["regularMarketPrice"]), None)
        return (None, None)
    except Exception:
        return (None, None)


def get_eur_usd_rate() -> Optional[float]:
    """
    Get latest EUR/USD rate from Yahoo Finance (USD per 1 EUR).
    Returns None if unavailable.
    """
    rate, _ = get_eur_usd_rate_with_date()
    return rate


def warn_if_eur_rate_unavailable(has_eur_positions: bool, rate: Optional[float]) -> None:
    """Log a warning when there are EUR positions but the rate is unavailable."""
    if has_eur_positions and (rate is None or rate <= 0):
        logger.warning("EUR/USD rate unavailable; EUR positions may show without conversion or with stale data.")


def usd_to_eur(amount_usd: float, rate: Optional[float]) -> Optional[float]:
    """
    Convert USD amount to EUR using rate (USD per 1 EUR).
    If rate is None or <= 0, returns None.
    """
    if rate is None or rate <= 0 or amount_usd is None:
        return None
    return amount_usd / rate


def format_eur_if_available(amount_usd: float, rate: Optional[float], decimals: int = 2) -> str:
    """Format amount in EUR when rate is available, else return empty string (caller shows USD only)."""
    eur = usd_to_eur(amount_usd, rate)
    if eur is None:
        return ""
    return f"{eur:.{decimals}f} EUR"
