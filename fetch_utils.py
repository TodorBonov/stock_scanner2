"""
Shared fetch logic for stock data from watchlist.
Used by 01_fetch_yahoo_watchlist_V2.py (pipeline cache).
"""
import time
from datetime import datetime
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from bot import TradingBot
from logger_config import get_logger
from config import FAILED_FETCH_LIST, TICKER_MAPPING_ERRORS_FILE
from currency_utils import get_eur_usd_rate

logger = get_logger(__name__)


def fetch_stock_data(ticker: str, bot: TradingBot) -> Dict:
    """Fetch historical data for a single stock. Returns dict with data_available, historical_data, stock_info, or error."""
    try:
        logger.info("Fetching data for %s...", ticker)
        hist = bot.data_provider.get_historical_data(ticker, period="1y", interval="1d")
        if hist.empty or len(hist) < 200:
            logger.warning("Insufficient data for %s: %d rows", ticker, len(hist))
            return {
                "ticker": ticker,
                "error": f"Insufficient historical data ({len(hist)} rows, need ≥200)",
                "data_available": False,
                "fetched_at": datetime.now().isoformat(),
            }
        stock_info = bot.data_provider.get_stock_info(ticker)
        hist_dict = {
            "index": [str(idx) for idx in hist.index],
            "data": hist.to_dict("records"),
        }
        if (stock_info or {}).get("currency") == "EUR":
            rate = get_eur_usd_rate()
            if rate and rate > 0:
                for row in hist_dict["data"]:
                    for key in ("Open", "High", "Low", "Close"):
                        if key in row and row[key] is not None:
                            row[key] = round(float(row[key]) * rate, 4)
                if stock_info:
                    for key in ("current_price", "52_week_high", "52_week_low"):
                        if stock_info.get(key) is not None:
                            stock_info[key] = round(float(stock_info[key]) * rate, 4)
                    stock_info["currency"] = "USD"
                    stock_info["original_currency"] = "EUR"
                logger.debug("Converted %s from EUR to USD (rate %.4f)", ticker, rate)
            else:
                if stock_info:
                    stock_info["original_currency"] = "EUR"
                    stock_info["rate_unavailable"] = True
                logger.warning(
                    "EUR/USD rate unavailable for %s; cached data left in EUR (downstream may assume USD).",
                    ticker,
                )
        return {
            "ticker": ticker,
            "data_available": True,
            "historical_data": hist_dict,
            "stock_info": stock_info or {},
            "data_points": len(hist),
            "date_range": {"start": str(hist.index[0]), "end": str(hist.index[-1])},
            "fetched_at": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error fetching data for %s: %s", ticker, e)
        return {
            "ticker": ticker,
            "error": str(e),
            "data_available": False,
            "fetched_at": datetime.now().isoformat(),
        }


def fetch_stock_data_with_retry(ticker: str, bot: TradingBot, max_retries: int = 2) -> Dict:
    """Fetch stock data with retry logic."""
    last_error = None
    for attempt in range(max_retries + 1):
        if attempt > 0:
            wait_time = min(2 ** attempt, 10)
            logger.info("Retry attempt %d for %s after %ds...", attempt, ticker, wait_time)
            time.sleep(wait_time)
        result = fetch_stock_data(ticker, bot)
        if result.get("data_available", False):
            return result
        last_error = result.get("error", "Unknown error")
    return {
        "ticker": ticker,
        "error": f"{last_error} (after {max_retries + 1} attempts)",
        "data_available": False,
        "fetched_at": datetime.now().isoformat(),
    }


def _build_result_from_hist(
    ticker: str,
    hist,
    stock_info: Dict,
    eur_usd_rate: float,
) -> Dict:
    """Build cache result dict from hist DataFrame and stock_info (same shape as fetch_stock_data)."""
    hist_dict = {
        "index": [str(idx) for idx in hist.index],
        "data": hist.to_dict("records"),
    }
    if (stock_info or {}).get("currency") == "EUR" and eur_usd_rate and eur_usd_rate > 0:
        for row in hist_dict["data"]:
            for key in ("Open", "High", "Low", "Close"):
                if key in row and row[key] is not None:
                    row[key] = round(float(row[key]) * eur_usd_rate, 4)
        if stock_info:
            for key in ("current_price", "52_week_high", "52_week_low"):
                if stock_info.get(key) is not None:
                    stock_info[key] = round(float(stock_info[key]) * eur_usd_rate, 4)
            stock_info["currency"] = "USD"
            stock_info["original_currency"] = "EUR"
    elif (stock_info or {}).get("currency") == "EUR":
        if stock_info:
            stock_info["original_currency"] = "EUR"
            stock_info["rate_unavailable"] = True
    return {
        "ticker": ticker,
        "data_available": True,
        "historical_data": hist_dict,
        "stock_info": stock_info or {},
        "data_points": len(hist),
        "date_range": {"start": str(hist.index[0]), "end": str(hist.index[-1])},
        "fetched_at": datetime.now().isoformat(),
    }


def fetch_stock_data_batch(tickers: List[str], bot: TradingBot, stock_info_workers: int = 4) -> Dict[str, Dict]:
    """
    Fetch historical data for many tickers in one batch (yf.download), then fetch stock_info
    in parallel. Returns dict mapping ticker -> same result shape as fetch_stock_data.
    Tickers with insufficient data get an error result.
    """
    if not tickers:
        return {}
    logger.info("Batch fetching historical data for %d tickers...", len(tickers))
    hist_by_ticker = bot.data_provider.get_historical_data_batch(tickers, period="1y", interval="1d")
    min_rows = 200
    ok_tickers = [t for t in tickers if t in hist_by_ticker and len(hist_by_ticker[t]) >= min_rows]
    results: Dict[str, Dict] = {}
    for t in tickers:
        if t not in hist_by_ticker or len(hist_by_ticker[t]) < min_rows:
            results[t] = {
                "ticker": t,
                "error": "Insufficient historical data ({} rows, need ≥{})".format(
                    len(hist_by_ticker.get(t, [])) if t in hist_by_ticker else 0, min_rows
                ),
                "data_available": False,
                "fetched_at": datetime.now().isoformat(),
            }
    if not ok_tickers:
        return results
    eur_usd_rate = get_eur_usd_rate()
    rate = eur_usd_rate if eur_usd_rate and eur_usd_rate > 0 else None
    # Fetch stock_info in parallel
    def get_info(t: str):
        return t, bot.data_provider.get_stock_info(t)
    info_by_ticker: Dict[str, Dict] = {}
    with ThreadPoolExecutor(max_workers=min(stock_info_workers, len(ok_tickers))) as ex:
        futures = {ex.submit(get_info, t): t for t in ok_tickers}
        for future in as_completed(futures):
            try:
                t, info = future.result()
                info_by_ticker[t] = info or {}
            except Exception as e:
                t = futures[future]
                logger.warning("Stock info failed for %s: %s", t, e)
                info_by_ticker[t] = {}
    for t in ok_tickers:
        results[t] = _build_result_from_hist(
            t,
            hist_by_ticker[t],
            info_by_ticker.get(t, {}),
            rate or 0.0,
        )
    return results
