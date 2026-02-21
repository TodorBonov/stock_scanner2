"""
New pipeline (3/5) 6MO: Same as New3 but OHLCV limited to last 6 months (126 days) only.
Reuses existing prepared_*.json from New3; rewrites OHLCV with last 126 days. Run New3 first.
"""
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv
from logger_config import setup_logging, get_logger
from config import DEFAULT_ENV_PATH
from currency_utils import get_eur_usd_rate_with_date
from ticker_utils import clean_ticker

MAX_OHLCV_DAYS = 126  # 6 months

NEW_PIPELINE_DIR = Path("data")
NEW_PIPELINE_CACHE = NEW_PIPELINE_DIR / "cached_stock_data_new_pipeline.json"
NEW_PIPELINE_REPORTS = Path("reports") / "new_pipeline"
PREPARED_EXISTING = NEW_PIPELINE_REPORTS / "prepared_existing_positions_6mo.json"
PREPARED_NEW = NEW_PIPELINE_REPORTS / "prepared_new_positions_6mo.json"

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
        logger.warning("Could not load cache: %s", e)
        return {"stocks": {}, "metadata": {}}


def load_prepared_existing() -> List[Dict]:
    path = NEW_PIPELINE_REPORTS / "prepared_existing_positions.json"
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("positions", [])
    except Exception as e:
        logger.warning("Could not load prepared existing: %s", e)
        return []


def load_prepared_new() -> List[Dict]:
    path = NEW_PIPELINE_REPORTS / "prepared_new_positions.json"
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("stocks", [])
    except Exception as e:
        logger.warning("Could not load prepared new: %s", e)
        return []


def ohlcv_to_csv_rows(hist_dict: dict, to_eur: bool = False, eur_rate: Optional[float] = None, max_days: Optional[int] = None) -> List[str]:
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


def main():
    parser = argparse.ArgumentParser(description="New3 6MO: Prepare data with last 6 months OHLCV only. Run New3 first.")
    parser.parse_args()

    print(f"\n{'='*80}")
    print("NEW3 6MO: PREPARE CHATGPT DATA (last 6 months OHLCV only)")
    print(f"{'='*80}")
    print(f"MAX_OHLCV_DAYS: {MAX_OHLCV_DAYS}")
    print(f"{'='*80}")

    cached_data = load_new_pipeline_cache()
    stocks = cached_data.get("stocks", {})
    if not stocks:
        print("No cache found. Run New1 first.")
        return

    eur_usd_rate, _ = get_eur_usd_rate_with_date()
    NO_OHLCV = "No OHLCV data available for this ticker (cache missing or ticker not in watchlist)."

    existing_list = load_prepared_existing()
    if not existing_list:
        print("No prepared_existing_positions.json. Run New3 first.")
        return
    prepared_existing = []
    for pos in existing_list:
        ticker = pos.get("ticker") or ""
        ohlcv_csv = pos.get("ohlcv_csv") or NO_OHLCV
        if ohlcv_csv != NO_OHLCV:
            cached = resolve_cache_entry(ticker, stocks)
            if cached and cached.get("data_available"):
                hist = cached.get("historical_data", {})
                currency = (pos.get("currency") or "USD").upper()
                to_eur = currency == "EUR" and eur_usd_rate and eur_usd_rate > 0
                rate = eur_usd_rate if to_eur else None
                lines = ohlcv_to_csv_rows(hist, to_eur=to_eur, eur_rate=rate, max_days=MAX_OHLCV_DAYS)
                if lines:
                    ohlcv_csv = "Date, Open, High, Low, Close, Volume\n" + "\n".join(lines)
        prepared_existing.append({**pos, "ohlcv_csv": ohlcv_csv})

    new_list = load_prepared_new()
    if not new_list:
        print("No prepared_new_positions.json. Run New3 first.")
        return
    prepared_new = []
    for s in new_list:
        ticker = s.get("ticker") or ""
        cached = resolve_cache_entry(ticker, stocks)
        if not cached or not cached.get("data_available"):
            prepared_new.append(s)
            continue
        hist = cached.get("historical_data", {})
        lines = ohlcv_to_csv_rows(hist, to_eur=False, max_days=MAX_OHLCV_DAYS)
        if lines:
            prepared_new.append({**s, "ohlcv_csv": "Date, Open, High, Low, Close, Volume\n" + "\n".join(lines)})
        else:
            prepared_new.append(s)

    NEW_PIPELINE_REPORTS.mkdir(parents=True, exist_ok=True)
    meta = {"prepared_at": datetime.now().isoformat(), "eur_usd_rate": eur_usd_rate, "max_ohlcv_days": MAX_OHLCV_DAYS}

    with open(PREPARED_EXISTING, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "positions": prepared_existing}, f, indent=2, default=str)
    print(f"Wrote {PREPARED_EXISTING} ({len(prepared_existing)} positions)")

    with open(PREPARED_NEW, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "stocks": prepared_new}, f, indent=2, default=str)
    print(f"Wrote {PREPARED_NEW} ({len(prepared_new)} A+/A stocks)")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
