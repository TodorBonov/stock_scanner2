"""
Pipeline step 3/7: Prepare data for Minervini.
Loads Yahoo cache (01) + positions (02) + watchlist; applies mapping; writes data/prepared_for_minervini.json
and reportsV2/problems_with_tickers.txt. Data is stored for testing and for step 04.
"""
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

from dotenv import load_dotenv
from logger_config import setup_logging, get_logger
from config import (
    DEFAULT_ENV_PATH,
    PREPARED_FOR_MINERVINI,
    PROBLEMS_WITH_TICKERS,
    REPORTS_DIR,
    NEW_PIPELINE_CACHE,
    NEW_PIPELINE_POSITIONS,
)
from watchlist_loader import (
    load_watchlist,
    get_ticker_rows,
    TYPE,
    YAHOO_SYMBOL,
    TRADING212_SYMBOL,
    BENCHMARK_INDEX,
)
from ticker_utils import clean_ticker

setup_logging(log_level="INFO", log_to_file=True)
logger = get_logger(__name__)

if Path(DEFAULT_ENV_PATH).exists():
    load_dotenv(Path(DEFAULT_ENV_PATH))


def load_cache() -> Dict[str, Any]:
    if not NEW_PIPELINE_CACHE.exists():
        return {"stocks": {}, "metadata": {}}
    try:
        with open(NEW_PIPELINE_CACHE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {"stocks": {}, "metadata": {}}
    except Exception as e:
        logger.warning("Could not load cache: %s", e)
        return {"stocks": {}, "metadata": {}}


def load_positions() -> List[Dict]:
    if not NEW_PIPELINE_POSITIONS.exists():
        return []
    try:
        with open(NEW_PIPELINE_POSITIONS, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("positions", [])
    except Exception as e:
        logger.warning("Could not load positions: %s", e)
        return []


def resolve_cache_entry(symbol: str, stocks: Dict) -> Optional[Dict]:
    """Find cache entry by yahoo symbol or trading212 symbol (exact, cleaned, trailing D)."""
    s = (symbol or "").strip().upper()
    if s in stocks:
        return stocks[s]
    cleaned = clean_ticker(s) or s
    if cleaned in stocks:
        return stocks[cleaned]
    if len(s) > 1 and s.endswith("D") and s[:-1] in stocks:
        return stocks[s[:-1]]
    for key, val in stocks.items():
        if key.upper() == s or (clean_ticker(key) or key) == cleaned:
            return val
    return None


def main():
    parser = argparse.ArgumentParser(description="03: Prepare data for Minervini (stored for testing)")
    parser.add_argument("--watchlist", default="watchlist.csv", help="Watchlist CSV or .txt")
    args = parser.parse_args()

    print(f"\n{'='*80}")
    print("03: PREPARE FOR MINERVINI")
    print(f"{'='*80}")

    cache = load_cache()
    stocks = cache.get("stocks", {})
    positions = load_positions()
    rows = load_watchlist(args.watchlist)
    ticker_rows = get_ticker_rows(rows)

    if not ticker_rows:
        print("No ticker rows in watchlist. Add type=ticker rows to watchlist.")
        return

    # Build mapping: trading212_symbol -> watchlist row (for problem reporting)
    t212_to_row: Dict[str, Dict] = {}
    for r in ticker_rows:
        t212 = (r.get(TRADING212_SYMBOL) or "").strip().upper()
        if t212:
            t212_to_row[t212] = r

    prepared_stocks: Dict[str, Dict] = {}
    problems: List[str] = []

    for r in ticker_rows:
        yahoo = (r.get(YAHOO_SYMBOL) or "").strip().upper()
        t212 = (r.get(TRADING212_SYMBOL) or "").strip().upper()
        bench = (r.get(BENCHMARK_INDEX) or "").strip().upper() or "^GDAXI"

        entry = resolve_cache_entry(yahoo, stocks) or resolve_cache_entry(t212, stocks)
        if not entry:
            problems.append(f"No cache data: yahoo={yahoo}, trading212={t212 or '(none)'}")
            continue
        if not entry.get("data_available", False):
            problems.append(f"No data available: yahoo={yahoo}, trading212={t212 or '(none)'} ({entry.get('error', 'unknown')})")
            continue

        # Use yahoo as key so 04 can match
        rec = dict(entry)
        rec["benchmark_index"] = bench
        rec["yahoo_symbol"] = yahoo
        rec["trading212_symbol"] = t212
        prepared_stocks[yahoo] = rec

    # Positions not in watchlist (unmapped)
    pos_tickers = set()
    for p in positions:
        t = (p.get("ticker") or p.get("ticker_raw") or "").strip().upper()
        if t:
            pos_tickers.add(t)
    for pt in pos_tickers:
        if pt not in t212_to_row and not resolve_cache_entry(pt, stocks):
            problems.append(f"Position not in watchlist / no cache: trading212={pt}")

    # Latest Yahoo fetch time from cache (when data was taken from Yahoo)
    data_timestamp_yahoo = None
    for sym, entry in prepared_stocks.items():
        t = entry.get("fetched_at")
        if t and (data_timestamp_yahoo is None or (isinstance(t, str) and t > data_timestamp_yahoo)):
            data_timestamp_yahoo = t
    if not data_timestamp_yahoo:
        data_timestamp_yahoo = datetime.now().isoformat()

    PREPARED_FOR_MINERVINI.parent.mkdir(parents=True, exist_ok=True)
    prepared_data = {
        "stocks": prepared_stocks,
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "data_timestamp_yahoo": data_timestamp_yahoo,
            "total_tickers": len(ticker_rows),
            "with_data": len(prepared_stocks),
            "problems_count": len(problems),
        },
    }
    with open(PREPARED_FOR_MINERVINI, "w", encoding="utf-8") as f:
        json.dump(prepared_data, f, indent=2, default=str)
    print(f"Wrote {PREPARED_FOR_MINERVINI} ({len(prepared_stocks)} tickers with data)")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROBLEMS_WITH_TICKERS, "w", encoding="utf-8") as f:
        f.write("# Problems with tickers (generated by 03_prepare_for_minervini_V2.py)\n")
        f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        if problems:
            for line in problems:
                f.write(line + "\n")
            print(f"Wrote {PROBLEMS_WITH_TICKERS} ({len(problems)} problems)")
        else:
            f.write("(none)\n")
            print(f"Wrote {PROBLEMS_WITH_TICKERS} (no problems)")

    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
