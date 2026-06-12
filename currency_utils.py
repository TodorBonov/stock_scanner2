"""
Currency conversion for report display.
All data and calculations stay in USD; convert to EUR only at report time for positions bought in EUR.
Uses Yahoo Finance EURUSD=X (USD per 1 EUR) for the rate.
"""
import os
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# Yahoo ticker: EUR/USD rate = how many USD per 1 EUR
EURUSD_YAHOO_TICKER = "EURUSD=X"

# Minor-unit currencies (sub-units quoted instead of the major unit).
# Yahoo reports e.g. London shares in "GBp" (pence), not GBP (pounds).
# Map: quoted code -> (major ISO code, divisor to get 1 major unit).
# Case-sensitive on purpose: "GBp" (pence) differs from "GBP" (pounds).
MINOR_UNIT_CURRENCIES: Dict[str, Tuple[str, float]] = {
    "GBp": ("GBP", 100.0),   # London pence
    "GBX": ("GBP", 100.0),   # alt code for pence
    "ZAc": ("ZAR", 100.0),   # South African cents
    "ILA": ("ILS", 100.0),   # Israeli agorot
    "USX": ("USD", 100.0),   # US cents (rare)
}

# Process-lifetime cache of FX rates to USD, keyed by the quoted currency code.
_FX_TO_USD_CACHE: Dict[str, Optional[float]] = {}


def _fetch_yahoo_fx_with_date(pair_ticker: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Fetch latest close for a Yahoo FX pair ticker (e.g. "EURUSD=X", "GBPUSD=X").
    Returns (rate, date_iso) or (None, None) if unavailable.
    """
    try:
        import yfinance as yf
        session = None
        if os.environ.get("DISABLE_SSL_VERIFY", "").strip().lower() in ("1", "true", "yes"):
            import requests
            session = requests.Session()
            session.verify = False
        t = yf.Ticker(pair_ticker, session=session) if session else yf.Ticker(pair_ticker)
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


def get_eur_usd_rate_with_date() -> Tuple[Optional[float], Optional[str]]:
    """
    Get latest EUR/USD rate and its date from Yahoo Finance (USD per 1 EUR).
    Returns (rate, date_iso) or (None, None) if unavailable.
    date_iso is YYYY-MM-DD from the history index.
    """
    return _fetch_yahoo_fx_with_date(EURUSD_YAHOO_TICKER)


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


def _split_minor_unit(currency: str) -> Tuple[str, float]:
    """
    Resolve a quoted currency code to (major ISO code, divisor).
    e.g. "GBp" -> ("GBP", 100.0); "USD" -> ("USD", 1.0).
    """
    c = (currency or "").strip()
    if c in MINOR_UNIT_CURRENCIES:
        return MINOR_UNIT_CURRENCIES[c]
    return (c.upper(), 1.0)


def get_fx_rate_to_usd(currency: str) -> Optional[float]:
    """
    Return how many USD equal 1 unit of the *quoted* currency.

    Handles minor units (e.g. "GBp" pence -> USD per pence). Returns 1.0 for USD,
    None if the currency is unknown/empty or the rate can't be fetched.
    Rates are cached for the process lifetime (FX changes slowly relative to a run).
    """
    if not currency:
        return None
    if currency in _FX_TO_USD_CACHE:
        return _FX_TO_USD_CACHE[currency]

    major, divisor = _split_minor_unit(currency)
    if major == "USD" and divisor == 1.0:
        _FX_TO_USD_CACHE[currency] = 1.0
        return 1.0

    if major == "USD":
        # e.g. USX (US cents): no FX lookup needed, just the divisor.
        rate = 1.0 / divisor
        _FX_TO_USD_CACHE[currency] = rate
        return rate

    pair_rate, _ = _fetch_yahoo_fx_with_date(f"{major}USD=X")
    if pair_rate is None or pair_rate <= 0:
        _FX_TO_USD_CACHE[currency] = None
        return None
    rate = pair_rate / divisor
    _FX_TO_USD_CACHE[currency] = rate
    return rate


def convert_ohlcv_and_info_to_usd(hist_dict: Optional[dict], stock_info: Optional[dict]) -> bool:
    """
    Convert OHLCV rows (in hist_dict["data"]) and price fields in stock_info to USD,
    in place, based on stock_info["currency"]. No-op for USD or missing currency.

    On success sets stock_info["currency"]="USD" and stock_info["original_currency"]=<orig>.
    When a non-USD currency is detected but no rate is available, marks
    stock_info["rate_unavailable"]=True and leaves data unconverted.
    Returns True if a conversion was applied.
    """
    if not stock_info:
        return False
    currency = (stock_info.get("currency") or "").strip()
    if not currency or currency.upper() == "USD":
        return False

    rate = get_fx_rate_to_usd(currency)
    if rate is None:
        stock_info["original_currency"] = currency
        stock_info["rate_unavailable"] = True
        logger.warning(
            "FX rate to USD unavailable for currency %s; data left unconverted (downstream may assume USD).",
            currency,
        )
        return False

    if hist_dict and isinstance(hist_dict.get("data"), list):
        for row in hist_dict["data"]:
            for key in ("Open", "High", "Low", "Close"):
                if row.get(key) is not None:
                    row[key] = round(float(row[key]) * rate, 4)
    for key in ("current_price", "52_week_high", "52_week_low"):
        if stock_info.get(key) is not None:
            stock_info[key] = round(float(stock_info[key]) * rate, 4)
    stock_info["original_currency"] = currency
    stock_info["currency"] = "USD"
    return True
