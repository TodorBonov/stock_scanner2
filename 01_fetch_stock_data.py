"""
Fetch and cache stock data from watchlist
Stores historical data for all stocks to avoid repeated API calls
"""
import sys
import io
import argparse
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from datetime import datetime
from typing import Dict, List

# Delay between Yahoo Finance requests (seconds) to reduce rate limiting
DELAY_BETWEEN_FETCHES_SEC = 1.0
# Max seconds per ticker so one stuck request (e.g. Yahoo hang) doesn't block the whole run
FETCH_TIMEOUT_SEC = 60
from bot import TradingBot
from logger_config import setup_logging, get_logger
from cache_utils import load_cached_data, save_cached_data
from config import CACHE_FILE, FAILED_FETCH_LIST, TICKER_MAPPING_ERRORS_FILE
from currency_utils import get_eur_usd_rate

# Fix Windows console encoding (skip when running under pytest to avoid breaking capture)
if sys.platform == 'win32' and 'pytest' not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Set up logging
setup_logging(log_level="INFO", log_to_file=True)
logger = get_logger(__name__)


def load_watchlist(file_path: str = "watchlist.txt") -> List[str]:
    """Load tickers from watchlist file"""
    tickers = []
    watchlist_path = Path(file_path)
    
    if not watchlist_path.exists():
        logger.error(f"Watchlist file not found: {file_path}")
        return []
    
    with open(watchlist_path, 'r', encoding='utf-8') as f:
        for line in f:
            ticker = line.strip()
            # Skip empty lines and comments
            if ticker and not ticker.startswith('#'):
                tickers.append(ticker)
    
    logger.info(f"Loaded {len(tickers)} tickers from {file_path}")
    return tickers


def fetch_stock_data(ticker: str, bot: TradingBot) -> Dict:
    """Fetch historical data for a single stock"""
    try:
        logger.info(f"Fetching data for {ticker}...")
        
        # Get historical data (need at least 1 year for 52-week calculations)
        hist = bot.data_provider.get_historical_data(ticker, period="1y", interval="1d")
        
        if hist.empty or len(hist) < 200:
            logger.warning(f"Insufficient data for {ticker}: {len(hist)} rows")
            return {
                "ticker": ticker,
                "error": f"Insufficient historical data ({len(hist)} rows, need ≥200)",
                "data_available": False,
                "fetched_at": datetime.now().isoformat()  # Track when we tried
            }
        
        # Get stock info
        stock_info = bot.data_provider.get_stock_info(ticker)
        
        # Convert DataFrame to dict for JSON serialization
        hist_dict = {
            "index": [str(idx) for idx in hist.index],
            "data": hist.to_dict('records')
        }
        
        # Normalize to USD: scripts after Yahoo use only USD; convert back to EUR only in reports
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
                logger.debug(f"Converted {ticker} from EUR to USD (rate {rate:.4f})")
            else:
                if stock_info:
                    stock_info["original_currency"] = "EUR"
                    stock_info["rate_unavailable"] = True
                logger.warning("EUR/USD rate unavailable for %s; cached data left in EUR (downstream may assume USD).", ticker)
        
        return {
            "ticker": ticker,
            "data_available": True,
            "historical_data": hist_dict,
            "stock_info": stock_info or {},
            "data_points": len(hist),
            "date_range": {
                "start": str(hist.index[0]),
                "end": str(hist.index[-1])
            },
            "fetched_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error fetching data for {ticker}: {e}")
        return {
            "ticker": ticker,
            "error": str(e),
            "data_available": False,
            "fetched_at": datetime.now().isoformat()  # Track when we tried
        }


def fetch_stock_data_with_retry(ticker: str, bot: TradingBot, max_retries: int = 2) -> Dict:
    """
    Fetch stock data with retry logic
    
    Args:
        ticker: Stock ticker symbol
        bot: TradingBot instance
        max_retries: Maximum number of retry attempts
        
    Returns:
        Dictionary with fetch results
    """
    import time
    from logger_config import get_logger
    retry_logger = get_logger(__name__)
    
    last_error = None
    
    for attempt in range(max_retries + 1):
        if attempt > 0:
            # Wait a bit before retry (exponential backoff)
            wait_time = min(2 ** attempt, 10)  # Max 10 seconds
            retry_logger.info(f"Retry attempt {attempt} for {ticker} after {wait_time}s...")
            time.sleep(wait_time)
        
        result = fetch_stock_data(ticker, bot)
        
        if result.get("data_available", False):
            return result
        
        last_error = result.get("error", "Unknown error")
    
    # All retries failed
    return {
        "ticker": ticker,
        "error": f"{last_error} (after {max_retries + 1} attempts)",
        "data_available": False,
        "fetched_at": datetime.now().isoformat()
    }


def fetch_all_data(force_refresh: bool = False, benchmark: str = "^GDAXI", watchlist_path: str = "watchlist.txt"):
    """Fetch data for all stocks in watchlist"""
    # Load watchlist
    tickers = load_watchlist(watchlist_path)
    if not tickers:
        print("No tickers found in watchlist.txt")
        return
    
    # Load existing cache (shared cache_utils returns None if missing)
    cached_data = load_cached_data() or {"stocks": {}, "metadata": {}}
    if not force_refresh and cached_data.get("stocks"):
        logger.info(f"Loaded {len(cached_data['stocks'])} stocks from cache")
    cached_stocks = cached_data.get("stocks", {})
    
    # Initialize bot
    bot = TradingBot(skip_trading212=True, benchmark=benchmark)
    
    # Track progress
    total = len(tickers)
    fetched = 0
    skipped = 0
    errors = 0
    
    print(f"\n{'='*80}")
    print(f"FETCHING STOCK DATA")
    print(f"{'='*80}")
    print(f"Total tickers: {total}")
    print(f"Force refresh: {force_refresh}")
    print(f"Cache file: {CACHE_FILE}")
    print(f"{'='*80}\n")
    
    # Fetch data for each ticker
    for i, ticker in enumerate(tickers, 1):
        # Check if already cached and not forcing refresh
        if not force_refresh and ticker in cached_stocks:
            cached_entry = cached_stocks[ticker]
            if cached_entry.get("data_available", False):
                print(f"[{i}/{total}] {ticker:12s} - Using cached data")
                skipped += 1
                continue
            # If cached entry exists but has error, retry it (might be temporary issue)
            elif cached_entry.get("error"):
                print(f"[{i}/{total}] {ticker:12s} - Retrying (previous error: {cached_entry.get('error', 'Unknown')[:30]}...)")
        # When forcing refresh, also retry stocks that previously failed
        elif force_refresh and ticker in cached_stocks:
            cached_entry = cached_stocks[ticker]
            if cached_entry.get("error") and not cached_entry.get("data_available", False):
                print(f"[{i}/{total}] {ticker:12s} - Force refresh (was failed: {cached_entry.get('error', 'Unknown')[:30]}...)")
        
        # Fetch new data (with retry logic), with timeout so one stuck ticker doesn't hang the run
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

        if result.get("data_available", False):
            cached_stocks[ticker] = result
            fetched += 1
            print(f"✓ ({result.get('data_points', 0)} data points)")
        else:
            cached_stocks[ticker] = result
            errors += 1
            error_msg = result.get("error", "Unknown error")
            print(f"✗ Error: {error_msg}")

        # Throttle requests to avoid Yahoo Finance rate limiting
        time.sleep(DELAY_BETWEEN_FETCHES_SEC)
    
    # Update metadata
    cached_data["metadata"] = {
        "last_updated": datetime.now().isoformat(),
        "total_stocks": len(cached_stocks),
        "stocks_with_data": sum(1 for s in cached_stocks.values() if s.get("data_available", False)),
        "stocks_with_errors": sum(1 for s in cached_stocks.values() if "error" in s),
        "benchmark": benchmark
    }
    cached_data["stocks"] = cached_stocks
    
    # Save cache (shared cache_utils)
    save_cached_data(cached_data)
    logger.info(f"Saved {len(cached_data.get('stocks', {}))} stocks to cache: {CACHE_FILE}")

    # Write list of failed tickers
    failed = [t for t, s in cached_stocks.items() if not s.get("data_available", False)]
    failed.sort()
    if failed:
        FAILED_FETCH_LIST.parent.mkdir(parents=True, exist_ok=True)
        FAILED_FETCH_LIST.write_text("\n".join(failed) + "\n", encoding="utf-8")
        logger.info(f"Wrote {len(failed)} failed tickers to {FAILED_FETCH_LIST}")
    elif FAILED_FETCH_LIST.exists():
        FAILED_FETCH_LIST.write_text("", encoding="utf-8")
        logger.info(f"Cleared {FAILED_FETCH_LIST} (no failures)")

    # Write ticker mapping errors (for manual resolution in data/ticker_mapping.json)
    TICKER_MAPPING_ERRORS_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Tickers that failed to fetch (possible T212/Yahoo mapping issues).",
        "# Add mappings to data/ticker_mapping.json and re-run. Format: \"T212_SYMBOL\": \"Yahoo_SYMBOL\"",
        "# Generated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "",
    ]
    if failed:
        lines.extend(failed)
        logger.info(f"Wrote {len(failed)} ticker mapping errors to {TICKER_MAPPING_ERRORS_FILE}")
    else:
        lines.append("(none)")
    TICKER_MAPPING_ERRORS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Print summary
    print(f"\n{'='*80}")
    print(f"FETCHING COMPLETE")
    print(f"{'='*80}")
    print(f"Total tickers: {total}")
    print(f"Fetched: {fetched}")
    print(f"Skipped (cached): {skipped}")
    print(f"Errors: {errors}")
    print(f"Cache saved to: {CACHE_FILE}")
    if failed:
        print(f"Failed tickers list: {FAILED_FETCH_LIST}")
    print(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch and cache stock data from watchlist"
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force refresh all data (ignore cache)"
    )
    parser.add_argument(
        "--benchmark",
        default="^GDAXI",
        choices=["^GDAXI", "^FCHI", "^AEX", "^SSMI", "^OMX"],
        help="Benchmark index for relative strength (default: ^GDAXI)"
    )
    parser.add_argument(
        "--watchlist",
        default="watchlist.txt",
        help="Path to watchlist file (default: watchlist.txt)"
    )
    
    args = parser.parse_args()
    
    fetch_all_data(force_refresh=args.refresh, benchmark=args.benchmark, watchlist_path=args.watchlist)


if __name__ == "__main__":
    main()

