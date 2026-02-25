"""
Pipeline step 5/7: Prepare data for 06 (existing positions) and 07 (new position suggestions).
Loads scan results from step 04 (SCAN_RESULTS_LATEST), pipeline cache + positions; converts to EUR for EUR positions;
outputs prepared JSON for 06 and 07. Does not run Minervini scan (run 04 first).
"""
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

from dotenv import load_dotenv
from logger_config import setup_logging, get_logger
from config import DEFAULT_ENV_PATH, SCAN_RESULTS_LATEST
from currency_utils import get_eur_usd_rate_with_date
from ticker_utils import clean_ticker
from watchlist_loader import load_watchlist, TRADING212_SYMBOL, YAHOO_SYMBOL

# Pipeline paths (match 01, 02)
NEW_PIPELINE_DIR = Path("data")
NEW_PIPELINE_CACHE = NEW_PIPELINE_DIR / "cached_stock_data_new_pipeline.json"
NEW_PIPELINE_POSITIONS = NEW_PIPELINE_DIR / "positions_new_pipeline.json"
NEW_PIPELINE_REPORTS = Path("reports") / "new_pipeline"
PREPARED_EXISTING = NEW_PIPELINE_REPORTS / "prepared_existing_positions.json"
PREPARED_NEW = NEW_PIPELINE_REPORTS / "prepared_new_positions.json"
PREPARED_EXISTING_6MO = NEW_PIPELINE_REPORTS / "prepared_existing_positions_6mo.json"
PREPARED_NEW_6MO = NEW_PIPELINE_REPORTS / "prepared_new_positions_6mo.json"
MAX_OHLCV_DAYS_6MO = 126

setup_logging(log_level="INFO", log_to_file=True)
logger = get_logger(__name__)

if Path(DEFAULT_ENV_PATH).exists():
    load_dotenv(Path(DEFAULT_ENV_PATH))


def load_scan_results() -> List[Dict]:
    """Load scan results written by step 04. Exit if missing."""
    if not SCAN_RESULTS_LATEST.exists():
        return []
    try:
        with open(SCAN_RESULTS_LATEST, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("Could not load scan results: %s", e)
        return []


def load_new_pipeline_cache() -> dict:
    if not NEW_PIPELINE_CACHE.exists():
        return {"stocks": {}, "metadata": {}}
    try:
        with open(NEW_PIPELINE_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Could not load new pipeline cache: %s", e)
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


def ohlcv_to_csv_rows(hist_dict: dict, to_eur: bool = False, eur_rate: Optional[float] = None, max_days: Optional[int] = None) -> List[str]:
    """Turn cache historical_data into 'Date, Open, High, Low, Close, Volume' lines (oldest first). If max_days set, use only last max_days rows."""
    if not hist_dict or "data" not in hist_dict:
        return []
    index = list(hist_dict.get("index") or [])
    data = list(hist_dict["data"])
    if max_days and len(data) > max_days:
        data = data[-max_days:]
        index = index[-max_days:] if len(index) >= max_days else index[-len(data):]
    rows = []
    for i, rec in enumerate(data):
        date_str = index[i] if i < len(index) else ""
        if hasattr(rec.get("Date"), "strftime"):
            date_str = rec["Date"].strftime("%Y-%m-%d") if rec.get("Date") else date_str
        o = rec.get("Open")
        h = rec.get("High")
        l_ = rec.get("Low")
        c = rec.get("Close")
        v = rec.get("Volume", 0)
        if to_eur and eur_rate and eur_rate > 0:
            o = round(float(o) / eur_rate, 4) if o is not None else None
            h = round(float(h) / eur_rate, 4) if h is not None else None
            l_ = round(float(l_) / eur_rate, 4) if l_ is not None else None
            c = round(float(c) / eur_rate, 4) if c is not None else None
        else:
            o = round(float(o), 4) if o is not None else None
            h = round(float(h), 4) if h is not None else None
            l_ = round(float(l_), 4) if l_ is not None else None
            c = round(float(c), 4) if c is not None else None
        rows.append(f"{date_str}, {o}, {h}, {l_}, {c}, {v}")
    return rows


def resolve_cache_entry(ticker: str, stocks: Dict) -> Optional[Dict]:
    """Get cache entry for ticker (try exact, cleaned, T212-style without trailing D)."""
    t = (ticker or "").strip().upper()
    if t in stocks:
        return stocks[t]
    cleaned = clean_ticker(t) or t
    if cleaned in stocks:
        return stocks[cleaned]
    if len(t) > 1 and t.endswith("D") and t[:-1] in stocks:
        return stocks[t[:-1]]
    for key in stocks:
        if key.upper() == t or (clean_ticker(key) or key) == cleaned:
            return stocks[key]
    return None


def build_t212_to_yahoo_map(watchlist_path: str = "watchlist.csv") -> Dict[str, str]:
    """Build Trading212 symbol -> Yahoo symbol from watchlist (cache is keyed by Yahoo)."""
    rows = load_watchlist(watchlist_path)
    out: Dict[str, str] = {}
    for r in rows:
        t212 = (r.get(TRADING212_SYMBOL) or "").strip().upper()
        yahoo = (r.get(YAHOO_SYMBOL) or "").strip().upper()
        if t212 and yahoo:
            out[t212] = yahoo
    return out


def main():
    parser = argparse.ArgumentParser(description="05: Prepare ChatGPT data (reads scan results from step 04)")
    parser.add_argument("--benchmark", default="^GDAXI", help="Unused; kept for CLI compatibility")
    parser.add_argument("--watchlist", default="watchlist.csv", help="Watchlist CSV (for T212->Yahoo symbol mapping)")
    parser.add_argument("--use-6mo", dest="use_6mo", action="store_true", help="Limit OHLCV to last 6 months (126 days) and write *_6mo.json files")
    args = parser.parse_args()

    use_6mo = getattr(args, "use_6mo", False)
    max_days = MAX_OHLCV_DAYS_6MO if use_6mo else None
    out_existing = PREPARED_EXISTING_6MO if use_6mo else PREPARED_EXISTING
    out_new = PREPARED_NEW_6MO if use_6mo else PREPARED_NEW

    print(f"\n{'='*80}")
    print("05: PREPARE CHATGPT DATA" + (" (6-month OHLCV)" if use_6mo else ""))
    print(f"{'='*80}")

    scan_results = load_scan_results()
    if not scan_results:
        print("No scan results found (04 not run or empty). Will write existing positions only; prepared_new will be empty.")

    cached_data = load_new_pipeline_cache()
    stocks = cached_data.get("stocks", {})
    if not stocks:
        print("No cache found. Run 01 (and optionally 02 --refresh) first.")
        return

    # Map Trading212 ticker -> Yahoo symbol so we can find OHLCV (cache is keyed by Yahoo)
    t212_to_yahoo = build_t212_to_yahoo_map(getattr(args, "watchlist", "watchlist.csv"))

    positions = load_positions()
    eur_usd_rate, eur_usd_rate_date = get_eur_usd_rate_with_date()
    if positions and any(p.get("currency") == "EUR" for p in positions) and (not eur_usd_rate or eur_usd_rate <= 0):
        logger.warning("EUR/USD rate unavailable; EUR positions will be left in USD in prepared data.")

    # --- Prepared for 06 (existing positions): include every position from Trading212 ---
    NO_OHLCV_PLACEHOLDER = "No OHLCV data available for this ticker (cache missing or ticker not in watchlist)."
    prepared_existing = []
    for pos in positions:
        ticker = pos.get("ticker") or pos.get("ticker_raw") or ""
        entry = float(pos.get("entry") or 0)
        current = pos.get("current")
        if current is not None:
            current = float(current)
        quantity = float(pos.get("quantity") or 0)
        currency = (pos.get("currency") or "USD").upper()
        name = pos.get("name") or ticker
        # Resolve cache by Yahoo symbol when position uses Trading212 symbol (e.g. RWED -> RWE.DE)
        cache_key = t212_to_yahoo.get(ticker.upper()) or ticker
        cached = resolve_cache_entry(cache_key, stocks)
        ohlcv_csv = NO_OHLCV_PLACEHOLDER
        if cached and cached.get("data_available"):
            hist = cached.get("historical_data", {})
            to_eur = currency == "EUR" and eur_usd_rate and eur_usd_rate > 0
            rate = eur_usd_rate if to_eur else None
            ohlcv_lines = ohlcv_to_csv_rows(hist, to_eur=to_eur, eur_rate=rate, max_days=max_days)
            if ohlcv_lines:
                ohlcv_csv = "Date, Open, High, Low, Close, Volume\n" + "\n".join(ohlcv_lines)
            else:
                logger.warning("No OHLCV rows for position %s.", ticker)
        else:
            logger.warning("No OHLCV cache for position %s; including in report with placeholder.", ticker)
        prepared_existing.append({
            "ticker": ticker,
            "entry": entry,
            "current": current,
            "quantity": quantity,
            "currency": currency,
            "name": name,
            "ohlcv_csv": ohlcv_csv,
        })

    # --- Prepared for 07 (A+/A only) from scan results ---
    a_plus_a = [r for r in scan_results if r.get("overall_grade") in ("A+", "A") and "error" not in str(r)]
    prepared_new = []
    for r in a_plus_a:
        ticker = (r.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        cached = resolve_cache_entry(ticker, stocks)
        if not cached or not cached.get("data_available"):
            continue
        hist = cached.get("historical_data", {})
        ohlcv_lines = ohlcv_to_csv_rows(hist, to_eur=False, max_days=max_days)
        if not ohlcv_lines:
            continue
        detailed = r.get("detailed_analysis") or {}
        current = detailed.get("current_price")
        name = (r.get("stock_info") or {}).get("company_name") or ticker
        buy_sell = r.get("buy_sell_prices") or {}
        distance_to_buy = buy_sell.get("distance_to_buy_pct")
        if distance_to_buy is not None:
            distance_to_buy = float(distance_to_buy)
        prepared_new.append({
            "ticker": ticker,
            "grade": r.get("overall_grade"),
            "meets_criteria": r.get("meets_criteria", False),
            "distance_to_buy_pct": distance_to_buy,
            "current_price": current,
            "name": name,
            "ohlcv_csv": "Date, Open, High, Low, Close, Volume\n" + "\n".join(ohlcv_lines),
        })

    NEW_PIPELINE_REPORTS.mkdir(parents=True, exist_ok=True)
    meta = {"prepared_at": datetime.now().isoformat(), "eur_usd_rate": eur_usd_rate, "eur_usd_rate_date": eur_usd_rate_date}
    if use_6mo:
        meta["max_ohlcv_days"] = MAX_OHLCV_DAYS_6MO

    with open(out_existing, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "positions": prepared_existing}, f, indent=2, default=str)
    print(f"Wrote {out_existing} ({len(prepared_existing)} positions)")

    with open(out_new, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "stocks": prepared_new}, f, indent=2, default=str)
    print(f"Wrote {out_new} ({len(prepared_new)} A+/A stocks)")

    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
