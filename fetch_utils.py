"""
Shared fetch logic for stock data from watchlist.
Used by New1_fetch_yahoo_watchlist.py (new pipeline cache) and 02_generate_full_report.py (--refresh to legacy cache).
"""
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from bot import TradingBot
from logger_config import get_logger
from cache_utils import load_cached_data, save_cached_data
from config import CACHE_FILE, FAILED_FETCH_LIST, TICKER_MAPPING_ERRORS_FILE
from currency_utils import get_eur_usd_rate

DELAY_BETWEEN_FETCHES_SEC = 1.0
FETCH_TIMEOUT_SEC = 60

logger = get_logger(__name__)


def load_watchlist(file_path: str = "watchlist.txt") -> List[str]:
    """Load tickers from watchlist file."""
    tickers = []
    watchlist_path = Path(file_path)
    if not watchlist_path.exists():
        logger.error("Watchlist file not found: %s", file_path)
        return []
    with open(watchlist_path, "r", encoding="utf-8") as f:
        for line in f:
            ticker = line.strip()
            if ticker and not ticker.startswith("#"):
                tickers.append(ticker)
    logger.info("Loaded %d tickers from %s", len(tickers), file_path)
    return tickers


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


def fetch_all_data(
    force_refresh: bool = False,
    benchmark: str = "^GDAXI",
    watchlist_path: str = "watchlist.txt",
) -> None:
    """
    Fetch data for all stocks in watchlist and save to legacy cache (CACHE_FILE).
    Used by 02_generate_full_report.py --refresh.
    """
    tickers = load_watchlist(watchlist_path)
    if not tickers:
        print("No tickers found in watchlist")
        return
    cached_data = load_cached_data() or {"stocks": {}, "metadata": {}}
    cached_stocks = cached_data.get("stocks", {})
    bot = TradingBot(skip_trading212=True, benchmark=benchmark)
    total = len(tickers)
    fetched = skipped = errors = 0
    print(f"\n{'='*80}\nFETCHING STOCK DATA\n{'='*80}")
    print(f"Total tickers: {total}\nCache file: {CACHE_FILE}\n{'='*80}\n")
    for i, ticker in enumerate(tickers, 1):
        if not force_refresh and ticker in cached_stocks and cached_stocks[ticker].get("data_available", False):
            print(f"[{i}/{total}] {ticker:12s} - Using cached data")
            skipped += 1
            continue
        if not force_refresh and ticker in cached_stocks and cached_stocks[ticker].get("error"):
            print(f"[{i}/{total}] {ticker:12s} - Retrying...")
        print(f"[{i}/{total}] {ticker:12s} - Fetching...", end=" ", flush=True)
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(fetch_stock_data_with_retry, ticker, bot)
                result = future.result(timeout=FETCH_TIMEOUT_SEC)
        except FuturesTimeoutError:
            result = {
                "ticker": ticker,
                "error": f"Timeout after {FETCH_TIMEOUT_SEC}s (skipped)",
                "data_available": False,
                "fetched_at": datetime.now().isoformat(),
            }
        cached_stocks[ticker] = result
        if result.get("data_available", False):
            fetched += 1
            print(f"OK ({result.get('data_points', 0)} points)")
        else:
            errors += 1
            print(f"Error: {(result.get('error') or 'Unknown')[:50]}")
        time.sleep(DELAY_BETWEEN_FETCHES_SEC)
    cached_data["stocks"] = cached_stocks
    cached_data["metadata"] = {
        "last_updated": datetime.now().isoformat(),
        "total_stocks": len(cached_stocks),
        "stocks_with_data": sum(1 for s in cached_stocks.values() if s.get("data_available", False)),
        "benchmark": benchmark,
    }
    save_cached_data(cached_data)
    failed = [t for t, s in cached_stocks.items() if not s.get("data_available", False)]
    failed.sort()
    if failed:
        FAILED_FETCH_LIST.parent.mkdir(parents=True, exist_ok=True)
        FAILED_FETCH_LIST.write_text("\n".join(failed) + "\n", encoding="utf-8")
    elif FAILED_FETCH_LIST.exists():
        FAILED_FETCH_LIST.write_text("", encoding="utf-8")
    TICKER_MAPPING_ERRORS_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Tickers that failed to fetch (possible mapping issues).",
        "# Generated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "",
    ]
    if failed:
        lines.extend(failed)
    else:
        lines.append("(none)")
    TICKER_MAPPING_ERRORS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n{'='*80}\nFetched: {fetched}  Skipped: {skipped}  Errors: {errors}\n{'='*80}\n")
