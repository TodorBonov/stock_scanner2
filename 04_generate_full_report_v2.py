"""
Pipeline step 4 V2: Run Minervini SEPA V2 scan (eligibility + composite scoring + RS percentile).
Reads from data/prepared_for_minervini.json (same as step 04). Does NOT overwrite scan_results_latest.json.
Writes: reportsV2/scan_results_v2_latest.json (LLM/engine output), reportsV2/sepa_scan_user_report_<ts>.txt,
        and optional CSV. Existing pipeline (04→05→06→07) is unchanged.
"""
import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd

from bot import TradingBot
from minervini_scanner_v2 import MinerviniScannerV2
from minervini_report_v2 import generate_user_friendly_report, export_scan_summary_to_csv
from logger_config import setup_logging, get_logger
from config import (
    PREPARED_FOR_MINERVINI,
    REPORTS_DIR_V2,
    SCAN_RESULTS_V2_LATEST,
    USER_REPORT_SUBDIR_V2,
    SEPA_USER_REPORT_PREFIX,
)
from cache_utils import load_cached_data

setup_logging(log_level="INFO", log_to_file=True)
logger = get_logger(__name__)


def convert_cached_data_to_dataframe(cached_stock: Dict) -> Optional[pd.DataFrame]:
    """Convert cached historical data to DataFrame (same logic as 04, for V2 use)."""
    try:
        hist_dict = cached_stock.get("historical_data", {})
        if not hist_dict or "data" not in hist_dict:
            return None
        data = hist_dict["data"]
        df = pd.DataFrame(data)
        if "index" in hist_dict and hist_dict["index"]:
            df.index = pd.to_datetime(hist_dict["index"], utc=True)
        elif "Date" in df.columns:
            df.index = pd.to_datetime(df["Date"])
            df = df.drop("Date", axis=1)
        else:
            for col in df.columns:
                if "date" in col.lower() or "time" in col.lower():
                    df.index = pd.to_datetime(df[col], utc=True)
                    df = df.drop(col, axis=1)
                    break
        df.columns = [col.capitalize() if col.lower() in ["open", "high", "low", "close", "volume"] else col for col in df.columns]
        col_mapping = {
            "Open": ["Open", "open", "OPEN"],
            "High": ["High", "high", "HIGH"],
            "Low": ["Low", "low", "LOW"],
            "Close": ["Close", "close", "CLOSE", "Adj Close", "adj close"],
            "Volume": ["Volume", "volume", "VOLUME", "Vol", "vol"],
        }
        for target_col, variations in col_mapping.items():
            for var in variations:
                if var in df.columns and target_col not in df.columns:
                    df = df.rename(columns={var: target_col})
        required_cols = ["Open", "High", "Low", "Close", "Volume"]
        if any(c not in df.columns for c in required_cols):
            return None
        return df[required_cols]
    except Exception as e:
        logger.debug("Convert cached to DataFrame failed: %s", e)
        return None


class CachedDataProviderV2:
    """Data provider that uses cached data (V2)."""

    def __init__(self, cached_stocks: Dict, original_provider):
        self.cached_stocks = cached_stocks
        self.original_provider = original_provider

    def get_historical_data(self, ticker: str, period: str = "1y", interval: str = "1d"):
        if ticker in self.cached_stocks and self.cached_stocks[ticker].get("data_available", False):
            hist = convert_cached_data_to_dataframe(self.cached_stocks[ticker])
            if hist is not None and not hist.empty:
                return hist
        return self.original_provider.get_historical_data(ticker, period, interval)

    def get_stock_info(self, ticker: str):
        if ticker in self.cached_stocks and self.cached_stocks[ticker].get("stock_info"):
            return self.cached_stocks[ticker]["stock_info"]
        return self.original_provider.get_stock_info(ticker)

    def calculate_relative_strength(self, ticker: str, benchmark: str, period: int = 252):
        return self.original_provider.calculate_relative_strength(ticker, benchmark, period)


def sanitize_for_json(obj):
    """Convert numpy/datetime to JSON-serializable."""
    import numpy as np
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    if isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    return str(obj)


def main():
    parser = argparse.ArgumentParser(description="Minervini SEPA V2 scan: eligibility + composite score + user report")
    parser.add_argument("--ticker", type=str, help="Single ticker only")
    parser.add_argument("--tickers", type=str, help="Comma-separated tickers")
    parser.add_argument("--benchmark", default="^GDAXI", type=str, help="Default benchmark for RS")
    parser.add_argument("--csv", action="store_true", help="Also export CSV summary")
    args = parser.parse_args()

    # Load data: prefer prepared, else legacy cache
    cached_data = None
    if PREPARED_FOR_MINERVINI.exists():
        try:
            with open(PREPARED_FOR_MINERVINI, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
        except Exception as e:
            logger.warning("Could not load prepared data: %s", e)
    if cached_data is None:
        cached_data = load_cached_data()
    if not cached_data or not cached_data.get("stocks"):
        logger.error("No cache. Run 01 and 03 first.")
        sys.exit(1)

    data_timestamp = (cached_data.get("metadata") or {}).get("data_timestamp_yahoo") or (cached_data.get("metadata") or {}).get("generated_at")
    stocks = cached_data["stocks"]
    if args.tickers:
        allowed = {t.strip().upper() for t in args.tickers.split(",") if t.strip()}
        stocks = {k: v for k, v in stocks.items() if k.upper() in allowed}
    elif args.ticker:
        if args.ticker not in stocks:
            logger.error("Ticker %s not in cache", args.ticker)
            sys.exit(1)
        stocks = {args.ticker: stocks[args.ticker]}

    tickers = [t for t in stocks if stocks[t].get("data_available", False)]
    if not tickers:
        logger.error("No tickers with data_available in cache")
        sys.exit(1)

    benchmark_overrides = {t: stocks[t].get("benchmark_index") for t in tickers if stocks[t].get("benchmark_index")}
    bot = TradingBot(skip_trading212=True, benchmark=args.benchmark)
    provider = CachedDataProviderV2(stocks, bot.data_provider)
    scanner = MinerviniScannerV2(provider, benchmark=args.benchmark)

    print(f"SEPA V2 Scan: {len(tickers)} tickers")
    results = scanner.scan_universe(tickers, benchmark_overrides or None)
    print(f"Scan complete: {len(results)} results")

    # Write LLM/engine JSON (single source of truth)
    REPORTS_DIR_V2.mkdir(parents=True, exist_ok=True)
    with open(SCAN_RESULTS_V2_LATEST, "w", encoding="utf-8") as f:
        json.dump(sanitize_for_json(results), f, indent=2, ensure_ascii=False)
    logger.info("Wrote %s", SCAN_RESULTS_V2_LATEST)

    # User-friendly report (report_run_timestamp = when this report is generated)
    report_run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_txt = generate_user_friendly_report(
        results,
        data_timestamp=data_timestamp,
        report_run_timestamp=report_run_ts,
    )
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = REPORTS_DIR_V2 / USER_REPORT_SUBDIR_V2 if USER_REPORT_SUBDIR_V2 else REPORTS_DIR_V2
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / f"{SEPA_USER_REPORT_PREFIX}{ts}.txt"
    report_file.write_text(report_txt, encoding="utf-8")
    # Avoid printing full report to console (contains Unicode e.g. ≥) which can fail on Windows cp1252
    print(f"\nUser report saved: {report_file} ({len(report_txt)} chars)")

    if args.csv:
        csv_path = report_dir / f"sepa_scan_summary_{ts}.csv"
        export_scan_summary_to_csv(results, csv_path)
        print(f"CSV saved: {csv_path}")

    print("\nV2 scan complete. Use scan_results_v2_latest.json for LLM/ChatGPT pipeline.")


if __name__ == "__main__":
    main()
