"""
List all tickers that failed to fetch (from cache).
Writes data/failed_fetch.txt and prints the list.
Run after 01_fetch_stock_data.py to regenerate the list without re-fetching.
"""
import sys
from pathlib import Path

# Add project root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cache_utils import load_cached_data
from config import CACHE_FILE, FAILED_FETCH_LIST


def main():
    cached = load_cached_data()
    if not cached or not cached.get("stocks"):
        print("No cache found. Run 01_fetch_stock_data.py first.")
        return 1

    stocks = cached.get("stocks", {})
    failed = [t for t, s in stocks.items() if not s.get("data_available", False)]
    failed.sort()

    if not failed:
        FAILED_FETCH_LIST.parent.mkdir(parents=True, exist_ok=True)
        FAILED_FETCH_LIST.write_text("", encoding="utf-8")
        print("No failed tickers in cache.")
        print(f"Cleared {FAILED_FETCH_LIST}")
        return 0

    FAILED_FETCH_LIST.parent.mkdir(parents=True, exist_ok=True)
    FAILED_FETCH_LIST.write_text("\n".join(failed) + "\n", encoding="utf-8")
    print(f"Failed tickers: {len(failed)}")
    print(f"Written to: {FAILED_FETCH_LIST}")
    print()
    for t in failed:
        err = stocks[t].get("error", "Unknown")
        snippet = (err[:70] + "...") if len(err) > 70 else err
        # Avoid Unicode that breaks Windows console (e.g. ≥)
        safe = snippet.replace("\u2265", ">=").encode("ascii", errors="replace").decode("ascii")
        print(f"  {t}: {safe}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
