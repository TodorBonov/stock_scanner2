"""
Pipeline step 4: Run SEPA scan (eligibility + composite scoring + RS percentile).
Reads from data/prepared_for_minervini.json (output of step 03).
Writes: reports/scan/latest.json (machine output), reports/scan/scan_<ts>.txt (human report),
        and optional reports/scan/scan_summary_<ts>.csv.
"""
import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd

from dotenv import load_dotenv
from data_provider import StockDataProvider
from sepa_scorer import MinerviniScannerV2
from sepa_report import generate_user_friendly_report, export_scan_summary_to_csv
from logger_config import setup_logging, get_logger
from config import (
    PREPARED_FOR_MINERVINI,
    REPORTS_DIR_V2,
    SCAN_RESULTS_V2_LATEST,
    SCAN_HISTORY_FILE,
    SEPA_USER_REPORT_PREFIX,
    SEPA_CSV_PREFIX,
    DEFAULT_ENV_PATH,
)
from cache_utils import load_cached_data

if Path(DEFAULT_ENV_PATH).exists():
    load_dotenv(Path(DEFAULT_ENV_PATH))

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
        df = df[required_cols].copy()
        # Drop rows with NaN in OHLCV (e.g. from Yahoo); otherwise rolling(SMA) and trend checks fail
        df = df.dropna(subset=required_cols)
        if len(df) < 200:
            return None
        # Ensure chronological order (oldest first) so iloc[-1] = latest and SMAs are correct
        df = df.sort_index(ascending=True)
        return df
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
        """
        Relative strength vs benchmark, computed from the cached snapshot.

        Uses this provider's cache-first get_historical_data for BOTH the ticker and the
        benchmark so RS comes from the same data vintage as every other metric in the scan
        (no live Yahoo calls, no mixed snapshots). Falls back to the live provider only if
        either series is missing from the cache.
        """
        try:
            stock_hist = self.get_historical_data(ticker, period="1y")
            benchmark_hist = self.get_historical_data(benchmark, period="1y")
            if stock_hist.empty or benchmark_hist.empty:
                return self.original_provider.calculate_relative_strength(ticker, benchmark, period)

            stock_returns = stock_hist["Close"].pct_change(fill_method=None).dropna()
            benchmark_returns = benchmark_hist["Close"].pct_change(fill_method=None).dropna()
            common_dates = stock_returns.index.intersection(benchmark_returns.index)
            if len(common_dates) < period:
                period = len(common_dates)
            if period <= 0:
                return {}

            stock_period = stock_returns.loc[common_dates[-period:]]
            benchmark_period = benchmark_returns.loc[common_dates[-period:]]
            stock_cumulative = (1 + stock_period).prod() - 1
            benchmark_cumulative = (1 + benchmark_period).prod() - 1
            relative_strength = stock_cumulative - benchmark_cumulative
            rs_rating = min(100, max(0, 50 + (relative_strength * 100)))
            return {
                "relative_strength": float(relative_strength),
                "rs_rating": float(rs_rating),
                "stock_return": float(stock_cumulative),
                "benchmark_return": float(benchmark_cumulative),
                "period_days": period,
            }
        except Exception as e:
            logger.debug("Cached RS calc failed for %s vs %s: %s", ticker, benchmark, e)
            return {"error": str(e)}


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
    provider = CachedDataProviderV2(stocks, StockDataProvider(alpha_vantage_api_key=os.getenv("ALPHA_VANTAGE_API_KEY"), prefer_yfinance=True))
    scanner = MinerviniScannerV2(provider, benchmark=args.benchmark)

    print(f"SEPA V2 Scan: {len(tickers)} tickers")
    results = scanner.scan_universe(tickers, benchmark_overrides or None)

    # Attach static watchlist metadata (Region, Sector, Market Cap) from prepared cache
    # so it flows into scan/latest.json and downstream HTML / text reports.
    for r in results:
        t = r.get("ticker")
        if not t:
            continue
        extra = stocks.get(t)
        if not isinstance(extra, dict):
            continue
        if extra.get("region") is not None:
            r["region"] = extra.get("region")
        if extra.get("sector") is not None:
            r["sector"] = extra.get("sector")
        if extra.get("market_cap") is not None:
            r["market_cap"] = extra.get("market_cap")
    print(f"Scan complete: {len(results)} results")

    # Write machine-readable JSON (single source of truth for downstream steps)
    scan_dir = REPORTS_DIR_V2 / "scan"
    scan_dir.mkdir(parents=True, exist_ok=True)
    with open(SCAN_RESULTS_V2_LATEST, "w", encoding="utf-8") as f:
        json.dump(sanitize_for_json(results), f, indent=2, ensure_ascii=False)
    logger.info("Wrote %s", SCAN_RESULTS_V2_LATEST)

    # Append flattened rows to history.jsonl (one line per ticker per run)
    scan_ts = datetime.now().isoformat()
    with open(SCAN_HISTORY_FILE, "a", encoding="utf-8") as hf:
        for r in results:
            base = r.get("base") or {}
            rs = r.get("relative_strength") or {}
            br = r.get("breakout") or {}
            risk = r.get("risk") or {}
            row = {
                "scan_date": scan_ts,
                "ticker": r.get("ticker"),
                "eligible": r.get("eligible"),
                "grade": r.get("grade"),
                "composite_score": r.get("composite_score"),
                "trend_score": r.get("trend_score"),
                "base_score": r.get("base_score"),
                "rs_score": r.get("rs_score"),
                "volume_score": r.get("volume_score"),
                "breakout_score": r.get("breakout_score"),
                "power_rank": r.get("power_rank"),
                "base_type": base.get("type"),
                "base_depth_pct": base.get("depth_pct"),
                "base_length_weeks": base.get("length_weeks"),
                "base_prior_run_pct": base.get("prior_run_pct"),
                "rs_percentile": rs.get("rs_percentile"),
                "rs_3m": rs.get("rs_3m"),
                "rsi_14": rs.get("rsi_14"),
                "pivot_price": br.get("pivot_price"),
                "distance_to_pivot_pct": br.get("distance_to_pivot_pct"),
                "in_breakout": br.get("in_breakout"),
                "stop_price": risk.get("stop_price"),
                "reward_to_risk": risk.get("reward_to_risk"),
                "stop_method": risk.get("stop_method"),
                "region": r.get("region"),
                "sector": r.get("sector"),
                "market_cap": r.get("market_cap"),
            }
            hf.write(json.dumps(row, default=str) + "\n")
    logger.info("Appended %d rows to %s", len(results), SCAN_HISTORY_FILE)

    # Human-readable report
    report_run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_txt = generate_user_friendly_report(
        results,
        data_timestamp=data_timestamp,
        report_run_timestamp=report_run_ts,
    )
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = scan_dir / f"{SEPA_USER_REPORT_PREFIX}{ts}.txt"
    report_file.write_text(report_txt, encoding="utf-8")
    # Avoid printing full report to console (contains Unicode e.g. ≥) which can fail on Windows cp1252
    print(f"\nUser report saved: {report_file} ({len(report_txt)} chars)")

    if args.csv:
        csv_path = scan_dir / f"{SEPA_CSV_PREFIX}{ts}.csv"
        export_scan_summary_to_csv(results, csv_path)
        print(f"CSV saved: {csv_path}")

    print("\nScan complete. reports/scan/latest.json ready for AI pipeline (steps 05–07).")


if __name__ == "__main__":
    main()
