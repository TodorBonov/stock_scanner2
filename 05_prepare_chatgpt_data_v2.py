"""
Pipeline step 5 V2: Prepare ChatGPT data from V2 scan results.
Reads reports/scan_results_v2_latest.json (from 04_generate_full_report_v2.py).
Outputs reports/v2/prepared_existing_positions_v2.json and prepared_new_positions_v2.json.
A+/A from V2 grade (eligible + grade in A+, A). New positions payload includes V2 structured fields for LLM.
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv
from logger_config import setup_logging, get_logger
from config import DEFAULT_ENV_PATH
from currency_utils import get_eur_usd_rate_with_date
from ticker_utils import clean_ticker
from watchlist_loader import load_watchlist, TRADING212_SYMBOL, YAHOO_SYMBOL

from minervini_config_v2 import REPORTS_DIR_V2, SCAN_RESULTS_V2_LATEST
from config import PREPARED_FOR_MINERVINI

NEW_PIPELINE_DIR = Path("data")
NEW_PIPELINE_CACHE = NEW_PIPELINE_DIR / "cached_stock_data_new_pipeline.json"
NEW_PIPELINE_POSITIONS = NEW_PIPELINE_DIR / "positions_new_pipeline.json"
V2_REPORTS = REPORTS_DIR_V2 / "v2"
PREPARED_EXISTING_V2 = V2_REPORTS / "prepared_existing_positions_v2.json"
PREPARED_NEW_V2 = V2_REPORTS / "prepared_new_positions_v2.json"
MAX_OHLCV_DAYS_6MO = 126

setup_logging(log_level="INFO", log_to_file=True)
logger = get_logger(__name__)

if Path(DEFAULT_ENV_PATH).exists():
    load_dotenv(Path(DEFAULT_ENV_PATH))


def load_scan_results_v2() -> List[Dict]:
    """Load V2 scan results."""
    if not SCAN_RESULTS_V2_LATEST.exists():
        return []
    try:
        with open(SCAN_RESULTS_V2_LATEST, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("Could not load V2 scan results: %s", e)
        return []


def load_cache() -> dict:
    if not NEW_PIPELINE_CACHE.exists():
        return {"stocks": {}}
    try:
        with open(NEW_PIPELINE_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Could not load cache: %s", e)
        return {"stocks": {}}


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
        o, h, l_, c = rec.get("Open"), rec.get("High"), rec.get("Low"), rec.get("Close")
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


def derive_trend_and_volume_from_ohlcv(hist_dict: dict) -> Dict:
    """
    From cached historical_data (OHLCV), derive fields for the 08 prompt:
    current_price, sma_50, sma_150, sma_200, 52_week_high, 52_week_low,
    return_6m_pct, return_12m_pct, avg_daily_volume.
    Returns empty dict or partial dict if data insufficient.
    """
    out = {}
    if not hist_dict or "data" not in hist_dict:
        return out
    data = list(hist_dict["data"])
    if not data:
        return out
    n = len(data)
    try:
        closes = []
        opens = []
        highs = []
        lows = []
        vols = []
        for rec in data:
            c = rec.get("Close") or rec.get("close")
            o = rec.get("Open") or rec.get("open")
            h = rec.get("High") or rec.get("high")
            l_ = rec.get("Low") or rec.get("low")
            v = rec.get("Volume") or rec.get("volume") or 0
            if c is not None:
                closes.append(float(c))
                opens.append(float(o) if o is not None else float(c))
                highs.append(float(h)) if h is not None else highs.append(float(c))
                lows.append(float(l_)) if l_ is not None else lows.append(float(c))
                vols.append(float(v))
            else:
                closes.append(None)
                opens.append(None)
                highs.append(None)
                lows.append(None)
                vols.append(None)
        # drop None closes for SMA; use last valid
        valid_closes = [c for c in closes if c is not None]
        if not valid_closes:
            return out
        out["current_price"] = valid_closes[-1]
        # Breakout volume vs average: last 5d vol / 20d avg
        valid_vols = [v for v in vols if v is not None and v > 0]
        if len(valid_vols) >= 20:
            avg_20 = sum(valid_vols[-20:]) / 20
            last_5_vol = sum(valid_vols[-5:]) / 5 if len(valid_vols) >= 5 else avg_20
            if avg_20 > 0:
                out["breakout_volume_vs_avg"] = round(last_5_vol / avg_20, 2)
        # Accumulation days (last ~4 weeks = 20 trading days): up days (close > open)
        if len(closes) >= 20 and len(opens) >= 20:
            start = len(closes) - 20
            up_days = sum(1 for i in range(start, len(closes)) if closes[i] is not None and opens[i] is not None and closes[i] > opens[i])
            out["accumulation_days_4w"] = up_days
        # 52w high/low (last 252 or all)
        window_52 = min(252, n)
        recent_highs = [h for h in highs[-window_52:] if h is not None]
        recent_lows = [l for l in lows[-window_52:] if l is not None]
        if recent_highs:
            out["52_week_high"] = round(max(recent_highs), 2)
        if recent_lows:
            out["52_week_low"] = round(min(recent_lows), 2)
        # SMAs (last 50/150/200 closes)
        for period, key in [(50, "sma_50"), (150, "sma_150"), (200, "sma_200")]:
            if len(valid_closes) >= period:
                out[key] = round(sum(valid_closes[-period:]) / period, 2)
        # Returns
        if len(valid_closes) >= 126:  # 6M
            out["return_6m_pct"] = round((valid_closes[-1] / valid_closes[-126] - 1) * 100, 2)
        if len(valid_closes) >= 252:  # 12M
            out["return_12m_pct"] = round((valid_closes[-1] / valid_closes[-252] - 1) * 100, 2)
        # Avg daily volume (last 20)
        valid_vols = [v for v in vols if v is not None and v > 0]
        if valid_vols:
            out["avg_daily_volume"] = round(sum(valid_vols[-20:]) / min(20, len(valid_vols[-20:])), 0)
    except (TypeError, ValueError, IndexError) as e:
        logger.debug("derive_trend_and_volume failed: %s", e)
    return out


def resolve_cache_entry(ticker: str, stocks: Dict) -> Optional[Dict]:
    t = (ticker or "").strip().upper()
    if t in stocks:
        return stocks[t]
    cleaned = clean_ticker(t) or t
    if cleaned in stocks:
        return stocks[cleaned]
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
    print("\n" + "=" * 80)
    print("05 V2: PREPARE CHATGPT DATA (from V2 scan)")
    print("=" * 80)

    scan_results = load_scan_results_v2()
    if not scan_results:
        print("No V2 scan results. Run 04_generate_full_report_v2.py first.")
        return

    cached_data = load_cache()
    stocks = cached_data.get("stocks", {})
    positions = load_positions()
    eur_usd_rate, eur_usd_rate_date = get_eur_usd_rate_with_date()
    t212_to_yahoo = build_t212_to_yahoo_map("watchlist.csv")

    V2_REPORTS.mkdir(parents=True, exist_ok=True)

    # --- Existing positions (for 06 V2); resolve cache by Yahoo symbol when position uses T212 symbol (e.g. RWED -> RWE.DE) ---
    NO_OHLCV = "No OHLCV data available for this ticker."
    prepared_existing = []
    for pos in positions:
        ticker = pos.get("ticker") or pos.get("ticker_raw") or ""
        cache_key = t212_to_yahoo.get(ticker.upper()) or ticker
        cached = resolve_cache_entry(cache_key, stocks)
        hist = cached.get("historical_data", {}) if cached else {}
        to_eur = (pos.get("currency") or "USD").upper() == "EUR" and eur_usd_rate and eur_usd_rate > 0
        ohlcv_lines = ohlcv_to_csv_rows(hist, to_eur=to_eur, eur_rate=eur_usd_rate)
        ohlcv_csv = "Date, Open, High, Low, Close, Volume\n" + "\n".join(ohlcv_lines) if ohlcv_lines else NO_OHLCV
        prepared_existing.append({
            "ticker": ticker,
            "entry": float(pos.get("entry") or 0),
            "current": float(pos["current"]) if pos.get("current") is not None else None,
            "quantity": float(pos.get("quantity") or 0),
            "currency": (pos.get("currency") or "USD").upper(),
            "name": pos.get("name") or ticker,
            "ohlcv_csv": ohlcv_csv,
        })

    # --- New positions: A+/A from V2 scan, include full V2 structured row for LLM ---
    a_plus_a = [r for r in scan_results if r.get("eligible") and r.get("grade") in ("A+", "A") and "error" not in str(r)]
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
        # Derive trend/52w/returns/volume from OHLCV for 08 prompt (independent analysis)
        derived = derive_trend_and_volume_from_ohlcv(hist)
        # Include V2 fields so ChatGPT prompt can reference composite_score, base type, rs_percentile, etc.
        prepared_new.append({
            "ticker": ticker,
            "grade": r.get("grade"),
            "composite_score": r.get("composite_score"),
            "eligible": r.get("eligible"),
            "base": r.get("base"),
            "relative_strength": r.get("relative_strength"),
            "breakout": r.get("breakout"),
            "risk": r.get("risk"),
            "trend_score": r.get("trend_score"),
            "base_score": r.get("base_score"),
            "rs_score": r.get("rs_score"),
            "volume_score": r.get("volume_score"),
            "breakout_score": r.get("breakout_score"),
            "power_rank": r.get("power_rank"),
            "ohlcv_csv": "Date, Open, High, Low, Close, Volume\n" + "\n".join(ohlcv_lines),
            **derived,
        })

    data_timestamp_yahoo = None
    if PREPARED_FOR_MINERVINI.exists():
        try:
            with open(PREPARED_FOR_MINERVINI, "r", encoding="utf-8") as f:
                prep = json.load(f)
            data_timestamp_yahoo = (prep.get("metadata") or {}).get("data_timestamp_yahoo")
        except Exception:
            pass
    meta = {
        "prepared_at": datetime.now().isoformat(),
        "source": "scan_results_v2_latest.json",
        "data_timestamp_yahoo": data_timestamp_yahoo,
        "eur_usd_rate": eur_usd_rate,
        "eur_usd_rate_date": eur_usd_rate_date,
    }
    with open(PREPARED_EXISTING_V2, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "positions": prepared_existing}, f, indent=2, default=str)
    print(f"Wrote {PREPARED_EXISTING_V2} ({len(prepared_existing)} positions)")

    with open(PREPARED_NEW_V2, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "stocks": prepared_new}, f, indent=2, default=str)
    print(f"Wrote {PREPARED_NEW_V2} ({len(prepared_new)} A+/A stocks from V2)")

    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
