"""
Pipeline step 1/5: Fetch and cache OHLCV from Yahoo for watchlist.
Run with watchlist_quick.txt for quick runs, or any watchlist path (e.g. watchlist.txt).
"""
import sys
import io
import argparse
import time
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from config import DEFAULT_ENV_PATH
from logger_config import setup_logging, get_logger

if Path(DEFAULT_ENV_PATH).exists():
    load_dotenv(Path(DEFAULT_ENV_PATH))

from watchlist_loader import load_watchlist, get_yahoo_symbols_for_fetch
from fetch_utils import fetch_stock_data_batch
from bot import TradingBot

# New pipeline: own cache file (do not overwrite main pipeline cache)
NEW_PIPELINE_DIR = Path("data")
NEW_PIPELINE_CACHE = NEW_PIPELINE_DIR / "cached_stock_data_new_pipeline.json"
FETCH_TIMEOUT_SEC = 300  # batch can take longer
BATCH_DELAY_AFTER_SEC = 1.0  # short delay after batch to be nice to Yahoo

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
    parser = argparse.ArgumentParser(description="01: Fetch Yahoo watchlist data (pipeline cache)")
    parser.add_argument("--watchlist", default="watchlist.csv", help="Watchlist CSV or legacy .txt (default: watchlist.csv)")
    parser.add_argument("--refresh", action="store_true", help="Force refresh (ignore cache)")
    parser.add_argument("--benchmark", default="^GDAXI", help="Benchmark for RS (default: ^GDAXI)")
    args = parser.parse_args()

    rows = load_watchlist(args.watchlist)
    tickers = get_yahoo_symbols_for_fetch(rows)
    if not tickers:
        print(f"No symbols in {args.watchlist}")
        return

    cached_data = load_new_pipeline_cache()
    cached_stocks = cached_data.get("stocks", {})
    bot = TradingBot(skip_trading212=True, benchmark=args.benchmark)

    total = len(tickers)
    fetched = 0
    skipped = 0
    errors = 0

    # Tickers we need to fetch (not in cache with data, or refresh)
    to_fetch = [
        t for t in tickers
        if args.refresh or t not in cached_stocks or not cached_stocks[t].get("data_available", False)
    ]
    skipped = sum(1 for t in tickers if t not in to_fetch)

    print(f"\n{'='*80}")
    print("01: FETCH YAHOO WATCHLIST")
    print(f"{'='*80}")
    print(f"Watchlist: {args.watchlist}")
    print(f"Tickers: {total}  (fetching: {len(to_fetch)}, using cache: {skipped})")
    print(f"Cache: {NEW_PIPELINE_CACHE}")
    print(f"{'='*80}\n")

    for i, ticker in enumerate(tickers, 1):
        if ticker not in to_fetch:
            print(f"[{i}/{total}] {ticker:12s} - Using cached")
            continue
        print(f"[{i}/{total}] {ticker:12s} - Queued for batch fetch")

    if to_fetch:
        print(f"\nBatch downloading {len(to_fetch)} tickers from Yahoo (threaded)...")
        try:
            batch_results = fetch_stock_data_batch(to_fetch, bot, stock_info_workers=6)
        except Exception as e:
            logger.exception("Batch fetch failed")
            batch_results = {t: {"ticker": t, "error": str(e), "data_available": False, "fetched_at": datetime.now().isoformat()} for t in to_fetch}
        for ticker in to_fetch:
            result = batch_results.get(ticker) or {
                "ticker": ticker,
                "error": "No result from batch",
                "data_available": False,
                "fetched_at": datetime.now().isoformat(),
            }
            cached_stocks[ticker] = result
            if result.get("data_available", False):
                fetched += 1
            else:
                errors += 1
        print(f"Batch done: {fetched} OK, {errors} errors.")
        time.sleep(BATCH_DELAY_AFTER_SEC)
    else:
        print("\nNothing to fetch (all cached).")

    cached_data["stocks"] = cached_stocks
    cached_data["metadata"] = {
        "last_updated": datetime.now().isoformat(),
        "total_stocks": len(cached_stocks),
        "stocks_with_data": sum(1 for s in cached_stocks.values() if s.get("data_available", False)),
        "benchmark": args.benchmark,
    }
    save_new_pipeline_cache(cached_data)

    print(f"\n{'='*80}")
    print("01 COMPLETE")
    print(f"Fetched: {fetched}  Skipped: {skipped}  Errors: {errors}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
