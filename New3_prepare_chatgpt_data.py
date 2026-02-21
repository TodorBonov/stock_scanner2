"""
New pipeline (3/5): Prepare data for New4 (existing positions) and New5 (new position suggestions).
Loads new pipeline cache + positions, runs Minervini scan on cache, converts to EUR for EUR positions,
outputs prepared JSON files for ChatGPT scripts.
"""
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

from dotenv import load_dotenv
from logger_config import setup_logging, get_logger
from config import DEFAULT_ENV_PATH
from currency_utils import get_eur_usd_rate_with_date, usd_to_eur
from ticker_utils import clean_ticker

# New pipeline paths (match New1, New2)
NEW_PIPELINE_DIR = Path("data")
NEW_PIPELINE_CACHE = NEW_PIPELINE_DIR / "cached_stock_data_new_pipeline.json"
NEW_PIPELINE_POSITIONS = NEW_PIPELINE_DIR / "positions_new_pipeline.json"
NEW_PIPELINE_REPORTS = Path("reports") / "new_pipeline"
PREPARED_EXISTING = NEW_PIPELINE_REPORTS / "prepared_existing_positions.json"
PREPARED_NEW = NEW_PIPELINE_REPORTS / "prepared_new_positions.json"

setup_logging(log_level="INFO", log_to_file=True)
logger = get_logger(__name__)

if Path(DEFAULT_ENV_PATH).exists():
    load_dotenv(Path(DEFAULT_ENV_PATH))


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


def run_scan(cached_data: dict, benchmark: str = "^GDAXI") -> List[Dict]:
    """Run Minervini scan on new pipeline cache (reuse 02 logic)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "report_module", Path(__file__).parent / "02_generate_full_report.py"
    )
    report_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report_module)
    results, _ = report_module.scan_all_stocks_from_cache(cached_data, benchmark=benchmark)
    return results


def ohlcv_to_csv_rows(hist_dict: dict, to_eur: bool = False, eur_rate: Optional[float] = None) -> List[str]:
    """Turn cache historical_data into 'Date, Open, High, Low, Close, Volume' lines (oldest first)."""
    if not hist_dict or "data" not in hist_dict:
        return []
    index = hist_dict.get("index") or []
    data = hist_dict["data"]
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
    # T212 often uses trailing D (e.g. RWED, PFED) for same as RWE, PFE
    if len(t) > 1 and t.endswith("D") and t[:-1] in stocks:
        return stocks[t[:-1]]
    for key in stocks:
        if key.upper() == t or (clean_ticker(key) or key) == cleaned:
            return stocks[key]
    return None


def main():
    parser = argparse.ArgumentParser(description="New3: Prepare ChatGPT data (new pipeline)")
    parser.add_argument("--benchmark", default="^GDAXI", help="Benchmark for scan (default: ^GDAXI)")
    args = parser.parse_args()

    print(f"\n{'='*80}")
    print("NEW3: PREPARE CHATGPT DATA")
    print(f"{'='*80}")

    cached_data = load_new_pipeline_cache()
    stocks = cached_data.get("stocks", {})
    if not stocks:
        print("No cache found. Run New1 (and optionally New2 --refresh) first.")
        return

    positions = load_positions()
    eur_usd_rate, _ = get_eur_usd_rate_with_date()
    if positions and any(p.get("currency") == "EUR" for p in positions) and (not eur_usd_rate or eur_usd_rate <= 0):
        logger.warning("EUR/USD rate unavailable; EUR positions will be left in USD in prepared data.")

    # Run scan for A+/A list
    print("Running Minervini scan on new pipeline cache...")
    scan_results = run_scan(cached_data, benchmark=args.benchmark)

    # --- Prepared for New4 (existing positions): include every position from Trading212 ---
    NO_OHLCV_PLACEHOLDER = "No OHLCV data available for this ticker (cache missing or ticker not in watchlist)."
    prepared_existing = []
    for pos in positions:
        ticker = pos.get("ticker") or pos.get("ticker_raw") or ""
        entry = float(pos.get("entry") or 0)
        current = pos.get("current")  # current price from Trading212 at fetch time
        if current is not None:
            current = float(current)
        quantity = float(pos.get("quantity") or 0)
        currency = (pos.get("currency") or "USD").upper()
        name = pos.get("name") or ticker
        cached = resolve_cache_entry(ticker, stocks)
        ohlcv_csv = NO_OHLCV_PLACEHOLDER
        if cached and cached.get("data_available"):
            hist = cached.get("historical_data", {})
            to_eur = currency == "EUR" and eur_usd_rate and eur_usd_rate > 0
            rate = eur_usd_rate if to_eur else None
            ohlcv_lines = ohlcv_to_csv_rows(hist, to_eur=to_eur, eur_rate=rate)
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

    # --- Prepared for New5 (A+/A only) ---
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
        ohlcv_lines = ohlcv_to_csv_rows(hist, to_eur=False)
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
    meta = {"prepared_at": datetime.now().isoformat(), "eur_usd_rate": eur_usd_rate}

    with open(PREPARED_EXISTING, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "positions": prepared_existing}, f, indent=2, default=str)
    print(f"Wrote {PREPARED_EXISTING} ({len(prepared_existing)} positions)")

    with open(PREPARED_NEW, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "stocks": prepared_new}, f, indent=2, default=str)
    print(f"Wrote {PREPARED_NEW} ({len(prepared_new)} A+/A stocks)")

    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
