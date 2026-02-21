"""
New pipeline (2/5): Fetch open positions from Trading212 and optionally refresh OHLCV for them.
Writes positions to new pipeline data dir; merges OHLCV into the same cache used by New1.
"""
import os
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

from dotenv import load_dotenv
from logger_config import setup_logging, get_logger
from config import DEFAULT_ENV_PATH
from ticker_utils import clean_ticker
from trading212_client import Trading212Client
from currency_utils import get_eur_usd_rate

# New pipeline paths (must match New1)
NEW_PIPELINE_DIR = Path("data")
NEW_PIPELINE_CACHE = NEW_PIPELINE_DIR / "cached_stock_data_new_pipeline.json"
NEW_PIPELINE_POSITIONS = NEW_PIPELINE_DIR / "positions_new_pipeline.json"

setup_logging(log_level="INFO", log_to_file=True)
logger = get_logger(__name__)

if Path(DEFAULT_ENV_PATH).exists():
    load_dotenv(Path(DEFAULT_ENV_PATH))


def _get_ticker_from_position(position: Dict) -> str:
    ticker = position.get("ticker")
    if ticker:
        return ticker
    instrument = position.get("instrument") or {}
    return instrument.get("ticker") or instrument.get("symbol") or ""


def _get_currency_from_position(position: Dict) -> str:
    instrument = position.get("instrument") or {}
    currency = instrument.get("currency") or ""
    if currency:
        return currency
    impact = position.get("walletImpact") or position.get("wallet_impact")
    if isinstance(impact, dict):
        return impact.get("currency") or ""
    return ""


def _get_entry_price(position: Dict) -> float:
    return float(position.get("averagePricePaid") or position.get("averagePrice") or 0)


def _get_current_price(position: Dict) -> float:
    return float(position.get("currentPrice") or position.get("current_price") or 0)


def _get_quantity(position: Dict) -> float:
    return float(position.get("quantity") or 0)


def fetch_positions() -> List[Dict[str, Any]]:
    """Fetch positions from Trading212 API. Returns list of dicts with ticker, entry, quantity, currency, etc."""
    api_key = os.getenv("TRADING212_API_KEY")
    api_secret = os.getenv("TRADING212_API_SECRET")
    if not api_key or not api_secret:
        logger.warning("TRADING212_API_KEY/SECRET not set; no positions")
        return []
    try:
        client = Trading212Client(api_key, api_secret)
        raw = client.get_positions()
    except Exception as e:
        logger.warning("Could not fetch positions: %s", e)
        return []
    out = []
    for pos in raw or []:
        qty = _get_quantity(pos)
        if qty <= 0:
            continue
        ticker_raw = _get_ticker_from_position(pos)
        if not ticker_raw:
            continue
        ticker_clean = clean_ticker(ticker_raw) or ticker_raw
        entry = _get_entry_price(pos)
        current = _get_current_price(pos)
        currency = _get_currency_from_position(pos)
        name = (pos.get("instrument") or {}).get("name") or ""
        out.append({
            "ticker_raw": ticker_raw,
            "ticker": ticker_clean,
            "entry": entry,
            "current": current,
            "quantity": qty,
            "currency": currency,
            "name": name,
        })
    return out


def load_new_pipeline_cache() -> dict:
    if not NEW_PIPELINE_CACHE.exists():
        return {"stocks": {}, "metadata": {}}
    try:
        with open(NEW_PIPELINE_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Could not load new pipeline cache: %s", e)
        return {"stocks": {}, "metadata": {}}


def save_new_pipeline_cache(data: dict) -> None:
    NEW_PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
    with open(NEW_PIPELINE_CACHE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def refresh_ohlcv_for_tickers(tickers: List[str]) -> None:
    """Fetch OHLCV for given tickers and merge into new pipeline cache (same structure as 01)."""
    if not tickers:
        return
    from bot import TradingBot
    bot = TradingBot(skip_trading212=True)
    cached_data = load_new_pipeline_cache()
    stocks = cached_data.get("stocks", {})
    for ticker in tickers:
        logger.info("Refreshing OHLCV for %s", ticker)
        try:
            hist = bot.data_provider.get_historical_data(ticker, period="1y", interval="1d")
            if hist.empty or len(hist) < 200:
                stocks[ticker] = {
                    "ticker": ticker,
                    "error": f"Insufficient data ({len(hist)} rows)",
                    "data_available": False,
                    "fetched_at": datetime.now().isoformat(),
                }
                continue
            stock_info = bot.data_provider.get_stock_info(ticker) or {}
            hist_dict = {"index": [str(idx) for idx in hist.index], "data": hist.to_dict("records")}
            if stock_info.get("currency") == "EUR":
                rate = get_eur_usd_rate()
                if rate and rate > 0:
                    for row in hist_dict["data"]:
                        for key in ("Open", "High", "Low", "Close"):
                            if key in row and row[key] is not None:
                                row[key] = round(float(row[key]) * rate, 4)
                    for key in ("current_price", "52_week_high", "52_week_low"):
                        if stock_info.get(key) is not None:
                            stock_info[key] = round(float(stock_info[key]) * rate, 4)
                    stock_info["currency"] = "USD"
                    stock_info["original_currency"] = "EUR"
            stocks[ticker] = {
                "ticker": ticker,
                "data_available": True,
                "historical_data": hist_dict,
                "stock_info": stock_info,
                "data_points": len(hist),
                "date_range": {"start": str(hist.index[0]), "end": str(hist.index[-1])},
                "fetched_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.warning("Fetch failed for %s: %s", ticker, e)
            stocks[ticker] = {"ticker": ticker, "error": str(e), "data_available": False, "fetched_at": datetime.now().isoformat()}
    cached_data["stocks"] = stocks
    save_new_pipeline_cache(cached_data)
    print(f"  Cache updated for {len(tickers)} position ticker(s).")


def main():
    parser = argparse.ArgumentParser(description="New2: Fetch Trading212 positions (new pipeline)")
    parser.add_argument("--refresh", action="store_true", help="Fetch OHLCV for position tickers into new pipeline cache")
    args = parser.parse_args()

    print(f"\n{'='*80}")
    print("NEW2: FETCH POSITIONS (Trading212)")
    print(f"{'='*80}")

    positions = fetch_positions()
    has_eur = any(p.get("currency") == "EUR" for p in positions)
    if has_eur:
        eur_rate, eur_rate_date = get_eur_usd_rate_with_date()
        warn_if_eur_rate_unavailable(True, eur_rate)
        if eur_rate and eur_rate > 0:
            logger.info("EUR/USD rate (Yahoo): %.4f (date: %s)", eur_rate, eur_rate_date or "N/A")
    if not positions:
        print("No open positions (or API not configured).")
        NEW_PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
        with open(NEW_PIPELINE_POSITIONS, "w", encoding="utf-8") as f:
            json.dump({"positions": [], "updated": datetime.now().isoformat()}, f, indent=2)
        print(f"Wrote {NEW_PIPELINE_POSITIONS}")
        print(f"{'='*80}\n")
        return

    print(f"Positions: {len(positions)}")
    for p in positions:
        print(f"  {p['ticker']}: entry={p['entry']:.2f} {p['currency'] or 'USD'}  qty={p['quantity']}")

    if args.refresh:
        tickers = list(dict.fromkeys([p["ticker"] for p in positions]))
        refresh_ohlcv_for_tickers(tickers)

    NEW_PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"positions": positions, "updated": datetime.now().isoformat()}
    with open(NEW_PIPELINE_POSITIONS, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"Wrote {NEW_PIPELINE_POSITIONS}")

    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
