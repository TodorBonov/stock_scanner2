"""
Position suggestions script
Fetches open positions from Trading 212 API and suggests an action for each (HOLD, ADD, REDUCE, EXIT)
based on rules in position_suggestions_config.py.
"""
import argparse
import os
import json
import importlib.util
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv
import requests

from trading212_client import Trading212Client
from ticker_utils import clean_ticker
from logger_config import get_logger
from config import DEFAULT_ENV_PATH
from position_suggestions_config import (
    POSITION_REPORTS_DIR,
    SCAN_RESULTS_PATH,
    STOP_LOSS_PCT,
    PROFIT_TARGET_1_PCT,
    PROFIT_TARGET_2_PCT,
    PROFIT_SUGGEST_MIN_PCT,
    STRONG_GRADES,
    WEAK_GRADES,
    EXIT_ON_WEAK_GRADE_IF_LOSS,
    ALLOW_ADD_ON_STRONG_GRADE,
    INCLUDE_GRADE_IN_REPORT,
    INCLUDE_PRICE_DETAILS,
)

logger = get_logger(__name__)

# Load env
_env_file = Path(DEFAULT_ENV_PATH)
if _env_file.exists():
    load_dotenv(_env_file)


def _get_ticker_from_position(position: Dict) -> str:
    """Extract ticker from Trading212 position (top-level or instrument)."""
    ticker = position.get("ticker")
    if ticker:
        return ticker
    instrument = position.get("instrument") or {}
    ticker = instrument.get("ticker") or instrument.get("symbol") or ""
    return ticker


def _get_entry_price(position: Dict) -> float:
    """Average price paid per share (Trading212: averagePricePaid)."""
    return float(position.get("averagePricePaid") or position.get("averagePrice") or 0)


def _get_current_price(position: Dict) -> float:
    """Current price per share (Trading212: currentPrice)."""
    return float(position.get("currentPrice") or position.get("current_price") or 0)


def _get_quantity(position: Dict) -> float:
    """Quantity held."""
    return float(position.get("quantity") or 0)


def _get_pnl_pct(position: Dict, entry: float, current: float) -> Optional[float]:
    """PnL % from position walletImpact or computed from entry/current."""
    impact = position.get("walletImpact") or position.get("wallet_impact")
    if isinstance(impact, dict) and impact.get("totalGain") is not None:
        # Prefer API PnL if available
        total_gain = float(impact.get("totalGain", 0))
        invested = entry * _get_quantity(position)
        if invested and invested > 0:
            return (total_gain / invested) * 100
    if entry and entry > 0 and current is not None:
        return ((current - entry) / entry) * 100
    return None


def load_scan_grades() -> Dict[str, str]:
    """Load ticker -> grade from latest scan results JSON. Returns {} if missing/invalid."""
    if not SCAN_RESULTS_PATH or not Path(SCAN_RESULTS_PATH).exists():
        return {}
    try:
        with open(SCAN_RESULTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("Could not load scan results: %s", e)
        return {}
    if not isinstance(data, list):
        return {}
    grades = {}
    for item in data:
        ticker = (item.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        grade = item.get("overall_grade") or "F"
        grades[ticker] = grade
        # Also map cleaned ticker (e.g. AAPL_US_EQ -> AAPL) so we can match API tickers
        cleaned = clean_ticker(ticker)
        if cleaned and cleaned not in grades:
            grades[cleaned] = grade
    return grades


def load_scan_base_levels() -> Dict[str, Optional[float]]:
    """Load ticker -> base_low from latest scan results (checklist.base_quality.details). Returns {} if missing/invalid."""
    if not SCAN_RESULTS_PATH or not Path(SCAN_RESULTS_PATH).exists():
        return {}
    try:
        with open(SCAN_RESULTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("Could not load scan results for base levels: %s", e)
        return {}
    if not isinstance(data, list):
        return {}
    base_levels: Dict[str, Optional[float]] = {}
    for item in data:
        ticker = (item.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        base_quality = (item.get("checklist") or {}).get("base_quality") or {}
        details = (base_quality.get("details") or {}) if isinstance(base_quality, dict) else {}
        base_low = details.get("base_low") if isinstance(details, dict) else None
        if base_low is not None:
            try:
                val = float(base_low)
            except (TypeError, ValueError):
                continue
            base_levels[ticker] = val
            cleaned = clean_ticker(ticker)
            if cleaned and cleaned not in base_levels:
                base_levels[cleaned] = val
    return base_levels


def refresh_data_for_tickers(tickers: List[str]) -> None:
    """Fetch fresh data and re-scan for the given tickers; update cache and scan_results_latest.json."""
    if not tickers:
        return
    cache_path = Path("data/cached_stock_data.json")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    # Load cache
    cached_data = {"stocks": {}, "metadata": {}}
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
        except Exception as e:
            logger.warning("Could not load cache: %s", e)
    stocks = cached_data.get("stocks", {})

    # Fetch fresh data for each ticker (same structure as 01_fetch_stock_data)
    from bot import TradingBot
    bot = TradingBot(skip_trading212=True)
    for ticker in tickers:
        print(f"  Refreshing data for {ticker}...")
        try:
            hist = bot.data_provider.get_historical_data(ticker, period="1y", interval="1d")
            if hist.empty or len(hist) < 200:
                stocks[ticker] = {
                    "ticker": ticker,
                    "error": f"Insufficient historical data ({len(hist)} rows, need ≥200)",
                    "data_available": False,
                    "fetched_at": datetime.now().isoformat(),
                }
            else:
                stock_info = bot.data_provider.get_stock_info(ticker)
                hist_dict = {"index": [str(idx) for idx in hist.index], "data": hist.to_dict("records")}
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
            stocks[ticker] = {
                "ticker": ticker,
                "error": str(e),
                "data_available": False,
                "fetched_at": datetime.now().isoformat(),
            }
    cached_data["stocks"] = stocks
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cached_data, f, indent=2, default=str)
        print(f"  Cache updated for {len(tickers)} ticker(s).")
    except Exception as e:
        logger.warning("Could not save cache: %s", e)
        return

    # Re-scan and merge into scan_results_latest.json
    spec = importlib.util.spec_from_file_location("report_module", Path("02_generate_full_report.py"))
    report_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report_module)
    all_results = []
    scan_path = Path(SCAN_RESULTS_PATH)
    if scan_path.exists():
        try:
            with open(scan_path, "r", encoding="utf-8") as f:
                all_results = json.load(f)
        except Exception:
            pass
    if not isinstance(all_results, list):
        all_results = []
    ticker_to_index = {str(r.get("ticker", "")).upper(): i for i, r in enumerate(all_results)}
    for ticker in tickers:
        print(f"  Scanning {ticker}...")
        try:
            results, _ = report_module.scan_all_stocks_from_cache(cached_data, benchmark="^GDAXI", single_ticker=ticker)
            if not results:
                continue
            one = results[0]
            t = str(one.get("ticker", "")).upper()
            if t in ticker_to_index:
                all_results[ticker_to_index[t]] = one
            else:
                all_results.append(one)
                ticker_to_index[t] = len(all_results) - 1
        except Exception as e:
            logger.warning("Scan failed for %s: %s", ticker, e)
    # Sanitize and save
    sanitized = report_module.sanitize_for_json(all_results)
    scan_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(scan_path, "w", encoding="utf-8") as f:
            json.dump(sanitized, f, indent=0, ensure_ascii=False)
        print(f"  Scan results updated for {len(tickers)} ticker(s).")
    except Exception as e:
        logger.warning("Could not save scan results: %s", e)


def suggest_action(
    entry: float,
    current: float,
    pnl_pct: Optional[float],
    grade: Optional[str],
) -> tuple[str, str]:
    """
    Return (action, reason) for a position.
    action: EXIT | REDUCE | HOLD | ADD
    """
    if not entry or entry <= 0:
        return "HOLD", "Unknown entry price; no suggestion."
    if current is None or current <= 0:
        return "HOLD", "Unknown current price; no suggestion."

    if pnl_pct is None:
        pnl_pct = ((current - entry) / entry) * 100

    # 1) Stop loss
    if pnl_pct <= -STOP_LOSS_PCT:
        return "EXIT", f"Cut loss: down {pnl_pct:.1f}% (stop {STOP_LOSS_PCT}%)"

    # 2) Profit target 2
    if pnl_pct >= PROFIT_TARGET_2_PCT:
        return "REDUCE", f"Take more profit: up {pnl_pct:.1f}% (target 2: {PROFIT_TARGET_2_PCT}%)"

    # 3) Profit target 1
    if pnl_pct >= PROFIT_TARGET_1_PCT:
        return "REDUCE", f"Take partial profit: up {pnl_pct:.1f}% (target 1: {PROFIT_TARGET_1_PCT}%)"

    # 4) Weak grade + in loss
    if EXIT_ON_WEAK_GRADE_IF_LOSS and grade in WEAK_GRADES and pnl_pct < 0:
        return "EXIT", f"Weak grade ({grade}) and in loss ({pnl_pct:.1f}%)"

    # 5) Strong grade + below target 1
    if ALLOW_ADD_ON_STRONG_GRADE and grade in STRONG_GRADES and pnl_pct < PROFIT_SUGGEST_MIN_PCT:
        return "ADD", f"Strong grade ({grade}); consider adding below target 1"

    if grade in STRONG_GRADES:
        return "HOLD", f"Strong grade ({grade}); hold toward targets"
    if grade in WEAK_GRADES:
        return "HOLD", f"Weak grade ({grade}); hold or trim on strength"
    return "HOLD", "No strong signal; hold"


def run() -> None:
    """Fetch positions, compute suggestions, print and save report."""
    parser = argparse.ArgumentParser(description="Position suggestions from Trading 212 (read-only)")
    parser.add_argument(
        "--refresh-tickers",
        action="store_true",
        help="Refresh cached data and scan grades for your current position tickers before suggesting",
    )
    args = parser.parse_args()

    api_key = os.getenv("TRADING212_API_KEY")
    api_secret = os.getenv("TRADING212_API_SECRET")
    if not api_key or not api_secret:
        print("ERROR: TRADING212_API_KEY and TRADING212_API_SECRET must be set (e.g. in .env)")
        return

    client = Trading212Client(api_key, api_secret)
    try:
        positions = client.get_positions()
    except requests.exceptions.HTTPError as e:
        logger.exception("Failed to fetch positions")
        print(f"ERROR: Failed to fetch positions: {e}")
        if e.response is not None and e.response.status_code == 401:
            print("\n  Unauthorized (401) usually means:")
            print("  - TRADING212_API_KEY or TRADING212_API_SECRET is wrong or expired")
            print("  - You are using DEMO keys with the LIVE API (this app uses live.trading212.com)")
            print("  - Regenerate API key/secret in Trading 212 (Invest → Settings → API)")
        return
    except Exception as e:
        logger.exception("Failed to fetch positions")
        print(f"ERROR: Failed to fetch positions: {e}")
        return

    if not positions:
        print("No open positions.")
        return

    if args.refresh_tickers:
        tickers = []
        for pos in positions:
            if _get_quantity(pos) <= 0:
                continue
            raw = _get_ticker_from_position(pos)
            cleaned = clean_ticker(raw) or raw
            if cleaned and cleaned not in tickers:
                tickers.append(cleaned)
        if tickers:
            print("Refreshing data for position tickers: " + ", ".join(tickers))
            refresh_data_for_tickers(tickers)
            print("")
        else:
            print("No position tickers to refresh.")

    grades = load_scan_grades()
    base_levels = load_scan_base_levels()
    POSITION_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("=" * 80)
    lines.append("POSITION SUGGESTIONS (Trading 212)")
    lines.append("=" * 80)
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Positions: {len(positions)}")
    lines.append("")
    lines.append("Rules: position_suggestions_config.py (stop loss, profit targets, grade-based)")
    lines.append("")

    for pos in positions:
        qty = _get_quantity(pos)
        if qty <= 0:
            continue
        ticker_raw = _get_ticker_from_position(pos)
        ticker_clean = clean_ticker(ticker_raw) or ticker_raw
        entry = _get_entry_price(pos)
        current = _get_current_price(pos)
        pnl_pct = _get_pnl_pct(pos, entry, current)
        grade = grades.get(ticker_clean) or grades.get(ticker_raw.upper())
        base_low = base_levels.get(ticker_clean) or base_levels.get(ticker_raw.upper())

        action, reason = suggest_action(entry, current, pnl_pct, grade)

        block = []
        block.append("-" * 80)
        block.append(f"  {ticker_clean or ticker_raw}")
        if INCLUDE_GRADE_IN_REPORT and grade:
            block.append(f"  Grade (scan): {grade}")
        block.append(f"  Suggestion: {action}")
        block.append(f"  Reason: {reason}")
        if INCLUDE_PRICE_DETAILS and entry and current:
            stop = entry * (1 - STOP_LOSS_PCT / 100)
            t1 = entry * (1 + PROFIT_TARGET_1_PCT / 100)
            t2 = entry * (1 + PROFIT_TARGET_2_PCT / 100)
            block.append(f"  Entry: {entry:.2f}  Current: {current:.2f}  PnL: {pnl_pct:.1f}%" if pnl_pct is not None else f"  Entry: {entry:.2f}  Current: {current:.2f}")
            block.append(f"  Your targets:  Stop loss: {stop:.2f}  Target 1: {t1:.2f}  Target 2: {t2:.2f}")
            # How current price relates to targets
            pct_above_stop = ((current - stop) / stop) * 100 if stop and stop > 0 else None
            pct_to_t1 = ((t1 - current) / current) * 100 if current and current > 0 else None
            pct_to_t2 = ((t2 - current) / current) * 100 if current and current > 0 else None
            rel = []
            if pct_above_stop is not None:
                rel.append(f"{pct_above_stop:.1f}% above stop")
            if pct_to_t1 is not None:
                rel.append(f"{abs(pct_to_t1):.1f}% {'to' if pct_to_t1 > 0 else 'past'} Target 1")
            if pct_to_t2 is not None:
                rel.append(f"{abs(pct_to_t2):.1f}% {'to' if pct_to_t2 > 0 else 'past'} Target 2")
            if rel:
                block.append(f"  Current vs targets:  {'  |  '.join(rel)}")
            # Base support: if scan identified a base whose low is above the % stop, suggest it as alternative exit
            if base_low is not None and stop and base_low > stop:
                block.append(f"  Base support: {base_low:.2f} – consider exit if price breaks below base.")
        block.append("")
        text = "\n".join(block)
        lines.append(text)
        print(text)

    lines.append("=" * 80)
    report_text = "\n".join(lines)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = POSITION_REPORTS_DIR / f"position_suggestions_{timestamp}.txt"
    try:
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_text)
        print(f"Report saved: {report_file}")
    except Exception as e:
        logger.warning("Could not save report: %s", e)


if __name__ == "__main__":
    run()
