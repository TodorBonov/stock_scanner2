"""
New pipeline (1/5): Fetch and cache OHLCV from Yahoo for watchlist.
Uses a dedicated cache so the new pipeline is separate from 01/02/03.
Run with watchlist_quick.txt for quick runs, or any watchlist path.
"""
import sys
import io
import argparse
import time
import json
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from dotenv import load_dotenv
from config import DEFAULT_ENV_PATH
from logger_config import setup_logging, get_logger

if Path(DEFAULT_ENV_PATH).exists():
    load_dotenv(Path(DEFAULT_ENV_PATH))

# Use 01's fetch logic but write to new pipeline cache
import importlib.util
_spec = importlib.util.spec_from_file_location("fetch_stock_data", Path(__file__).parent / "01_fetch_stock_data.py")
_fetch_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fetch_module)
load_watchlist = _fetch_module.load_watchlist
fetch_stock_data = _fetch_module.fetch_stock_data
fetch_stock_data_with_retry = _fetch_module.fetch_stock_data_with_retry

from bot import TradingBot

# New pipeline: own cache file (do not overwrite main pipeline cache)
NEW_PIPELINE_DIR = Path("data")
NEW_PIPELINE_CACHE = NEW_PIPELINE_DIR / "cached_stock_data_new_pipeline.json"
DELAY_BETWEEN_FETCHES_SEC = 1.0
FETCH_TIMEOUT_SEC = 60

if sys.platform == "win32" and "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

setup_logging(log_level="INFO", log_to_file=True)
logger = get_logger(__name__)


def load_new_pipeline_cache() -> dict:
    """Load new pipeline cache (stocks + metadata)."""
    if not NEW_PIPELINE_CACHE.exists():
        return {"stocks": {}, "metadata": {}}
    try:
        with open(NEW_PIPELINE_CACHE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {"stocks": {}, "metadata": {}}
    except Exception as e:
        logger.warning("Could not load new pipeline cache: %s", e)
        return {"stocks": {}, "metadata": {}}


def save_new_pipeline_cache(data: dict) -> None:
    """Save new pipeline cache."""
    NEW_PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
    with open(NEW_PIPELINE_CACHE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def main():
    parser = argparse.ArgumentParser(description="New1: Fetch Yahoo watchlist data (new pipeline cache)")
    parser.add_argument("--watchlist", default="watchlist_quick.txt", help="Watchlist file (default: watchlist_quick.txt)")
    parser.add_argument("--refresh", action="store_true", help="Force refresh (ignore cache)")
    parser.add_argument("--benchmark", default="^GDAXI", help="Benchmark for RS (default: ^GDAXI)")
    args = parser.parse_args()

    tickers = load_watchlist(args.watchlist)
    if not tickers:
        print(f"No tickers in {args.watchlist}")
        return

    cached_data = load_new_pipeline_cache()
    cached_stocks = cached_data.get("stocks", {})
    bot = TradingBot(skip_trading212=True, benchmark=args.benchmark)

    total = len(tickers)
    fetched = 0
    skipped = 0
    errors = 0

    print(f"\n{'='*80}")
    print("NEW1: FETCH YAHOO WATCHLIST (new pipeline)")
    print(f"{'='*80}")
    print(f"Watchlist: {args.watchlist}")
    print(f"Tickers: {total}")
    print(f"Cache: {NEW_PIPELINE_CACHE}")
    print(f"{'='*80}\n")

    for i, ticker in enumerate(tickers, 1):
        if not args.refresh and ticker in cached_stocks and cached_stocks[ticker].get("data_available", False):
            print(f"[{i}/{total}] {ticker:12s} - Using cached")
            skipped += 1
            continue
        if not args.refresh and ticker in cached_stocks and cached_stocks[ticker].get("error"):
            print(f"[{i}/{total}] {ticker:12s} - Retrying...")
        print(f"[{i}/{total}] {ticker:12s} - Fetching...", end=" ", flush=True)
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(fetch_stock_data_with_retry, ticker, bot)
                result = future.result(timeout=FETCH_TIMEOUT_SEC)
        except FuturesTimeoutError:
            result = {"ticker": ticker, "error": "Timeout", "data_available": False, "fetched_at": datetime.now().isoformat()}

        cached_stocks[ticker] = result
        if result.get("data_available", False):
            fetched += 1
            print(f"OK ({result.get('data_points', 0)} points)")
        else:
            errors += 1
            print(f"Error: {result.get('error', 'Unknown')[:50]}")
        time.sleep(DELAY_BETWEEN_FETCHES_SEC)

    cached_data["stocks"] = cached_stocks
    cached_data["metadata"] = {
        "last_updated": datetime.now().isoformat(),
        "total_stocks": len(cached_stocks),
        "stocks_with_data": sum(1 for s in cached_stocks.values() if s.get("data_available", False)),
        "benchmark": args.benchmark,
    }
    save_new_pipeline_cache(cached_data)

    print(f"\n{'='*80}")
    print("NEW1 COMPLETE")
    print(f"Fetched: {fetched}  Skipped: {skipped}  Errors: {errors}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
