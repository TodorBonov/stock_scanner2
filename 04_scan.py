"""
Pipeline step 4: Run SEPA scan (eligibility + composite scoring + RS percentile).
Reads from data/prepared_for_minervini.json (output of step 03).
Writes: reports/scan/latest.json (machine output), reports/scan/scan_<ts>.txt (human report),
        and optional reports/scan/scan_summary_<ts>.csv.
"""
import json
import os
import sys
import time
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
    NEW_PIPELINE_CACHE,
    EARNINGS_GUARD_DAYS,
    EARNINGS_GUARD_GRADES,
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
        # Volume is often NaN for index benchmarks (^FTMIB, etc.); don't let that wipe the
        # series — fill it with 0 and only require OHLC to be present.
        df["Volume"] = df["Volume"].fillna(0)
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        if len(df) < 200:
            return None
        # Ensure chronological order (oldest first) so iloc[-1] = latest and SMAs are correct
        df = df.sort_index(ascending=True)
        return df
    except Exception as e:
        logger.debug("Convert cached to DataFrame failed: %s", e)
        return None


class CachedDataProviderV2:
    """
    Cache-ONLY data provider for the scan. It never makes live Yahoo calls: step 01 is
    responsible for fetching, and during a 1,700-name scan a per-ticker live fallback means
    60/180s rate-limit backoffs that can turn a seconds-long scan into an hour. If a ticker's
    cached data is missing/short, we return empty and let the scanner mark it insufficient.
    `original_provider` is accepted for API compatibility but intentionally not used here.
    """

    def __init__(self, cached_stocks: Dict, original_provider=None):
        self.cached_stocks = cached_stocks
        self.original_provider = original_provider

    def get_historical_data(self, ticker: str, period: str = "1y", interval: str = "1d"):
        if ticker in self.cached_stocks and self.cached_stocks[ticker].get("data_available", False):
            hist = convert_cached_data_to_dataframe(self.cached_stocks[ticker])
            if hist is not None and not hist.empty:
                return hist
        return pd.DataFrame()  # cache miss -> empty (NO live fetch during scan)

    def get_stock_info(self, ticker: str):
        if ticker in self.cached_stocks and self.cached_stocks[ticker].get("stock_info"):
            return self.cached_stocks[ticker]["stock_info"]
        return {}

    def calculate_relative_strength(self, ticker: str, benchmark: str, period: int = 252):
        """
        Relative strength vs benchmark, computed purely from the cached snapshot — no live
        calls. Returns {} if either series is missing from cache (caller handles the fallback).
        """
        try:
            stock_hist = self.get_historical_data(ticker, period="1y")
            benchmark_hist = self.get_historical_data(benchmark, period="1y")
            if stock_hist.empty or benchmark_hist.empty:
                return {}

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


def compute_sector_strength(results):
    """
    Marker 2 (FLAG ONLY): tag each result with how its sector is performing vs the universe.
    Uses each result's 3-month return (relative_strength.rs_3m). Sectors are ranked by their
    MEDIAN 3M return; the bottom third are 'lagging', the top third 'leading', the rest 'inline'.
    Stocks with no sector or no return get 'unknown'. Attaches r['sector_strength'] and returns
    (sector_median dict, market_3m) for the report summary.
    """
    from statistics import median
    sector_returns = {}
    all_returns = []
    for r in results:
        rs3 = (r.get("relative_strength") or {}).get("rs_3m")
        if rs3 is None:
            continue
        all_returns.append(rs3)
        sec = (r.get("sector") or "").strip()
        if sec:
            sector_returns.setdefault(sec, []).append(rs3)
    market_3m = round(median(all_returns), 2) if all_returns else 0.0
    sector_median = {s: median(v) for s, v in sector_returns.items() if v}
    ranked = sorted(sector_median, key=lambda s: sector_median[s])  # ascending
    lagging, leading = set(), set()
    if len(ranked) >= 3:
        cut = max(1, len(ranked) // 3)
        lagging = set(ranked[:cut])
        leading = set(ranked[-cut:])
    for r in results:
        sec = (r.get("sector") or "").strip()
        if sec and sec in sector_median:
            status = "lagging" if sec in lagging else "leading" if sec in leading else "inline"
            r["sector_strength"] = {"sector": sec, "sector_3m": round(sector_median[sec], 2),
                                    "market_3m": market_3m, "status": status}
        else:
            r["sector_strength"] = {"sector": sec or None, "sector_3m": None,
                                    "market_3m": market_3m, "status": "unknown"}
    return {s: round(v, 2) for s, v in sector_median.items()}, market_3m


def earnings_days_until(next_date, today):
    """Days from `today` to `next_date` (a datetime.date), or None. Negative if in the past."""
    if next_date is None or today is None:
        return None
    try:
        return (next_date - today).days
    except Exception:
        return None


def _yf_session():
    """curl_cffi Chrome session under DISABLE_SSL_VERIFY (corporate proxy), else default."""
    if os.environ.get("DISABLE_SSL_VERIFY", "").strip().lower() in ("1", "true", "yes"):
        try:
            from curl_cffi import requests as cr
            s = cr.Session(impersonate="chrome"); s.verify = False
            return s
        except ImportError:
            return None
    return None


def fetch_next_earnings_date(ticker, session=None):
    """Next FUTURE earnings date via Yahoo .calendar (the endpoint that isn't throttled here)."""
    import yfinance as yf
    from datetime import date
    try:
        tk = yf.Ticker(ticker, session=session) if session else yf.Ticker(ticker)
        cal = tk.calendar
        dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if not dates:
            return None
        today = date.today()
        future = sorted(d for d in dates if hasattr(d, "year") and d >= today)
        return future[0] if future else None
    except Exception:
        return None


def apply_earnings_guard(results, window_days=EARNINGS_GUARD_DAYS, grades=EARNINGS_GUARD_GRADES):
    """
    Flag actionable candidates (grade in `grades`) that report earnings within `window_days`.
    Live .calendar fetch per candidate (scoped small). Attaches r['earnings']; flag only.
    Returns the count flagged as reporting soon.
    """
    from datetime import date
    session = _yf_session()
    today = date.today()
    soon = 0
    for r in results:
        if r.get("grade") not in grades:
            continue
        nd = fetch_next_earnings_date(r.get("ticker"), session)
        days = earnings_days_until(nd, today)
        is_soon = days is not None and 0 <= days <= window_days
        r["earnings"] = {
            "next_date": nd.isoformat() if nd else None,
            "days_until": days,
            "soon": is_soon,
        }
        if is_soon:
            soon += 1
        time.sleep(0.2)  # gentle pacing for the scoped live calls
    return soon


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

    # The prepared file excludes index rows, but RS needs benchmark OHLCV (^GSPC, ^GDAXI, ...).
    # Merge the raw step-01 cache (which has the indices) into the provider's data so RS is
    # served from cache instead of a live Yahoo fetch per stock. Scan list (`tickers`) is unchanged.
    provider_stocks = dict(stocks)
    try:
        if NEW_PIPELINE_CACHE.exists():
            with open(NEW_PIPELINE_CACHE, "r", encoding="utf-8") as f:
                raw_stocks = (json.load(f) or {}).get("stocks", {})
            added = 0
            for sym, entry in raw_stocks.items():
                if sym not in provider_stocks and entry.get("data_available", False):
                    provider_stocks[sym] = entry
                    added += 1
            logger.info("Merged %d cached entries (incl. benchmark indices) into the scan provider", added)
    except Exception as e:
        logger.warning("Could not merge raw cache for benchmarks: %s", e)

    provider = CachedDataProviderV2(provider_stocks, StockDataProvider(alpha_vantage_api_key=os.getenv("ALPHA_VANTAGE_API_KEY"), prefer_yfinance=True))
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

    # Marker 1 — market regime (FLAG ONLY, no grade change). Minervini's #1 rule: trade with
    # the market. For each stock's benchmark index, compare its latest close to its own 200-day
    # SMA (computed once per benchmark from cached index data; no live calls).
    benchmarks_used = {(benchmark_overrides.get(t) or args.benchmark) for t in tickers}
    regime_by_bench = {}
    for b in benchmarks_used:
        if b:
            regime_by_bench[b] = scanner.get_market_regime(b)
    risk_off_count = 0
    for r in results:
        b = benchmark_overrides.get(r.get("ticker")) or args.benchmark
        above = (regime_by_bench.get(b) or {}).get("above_200sma")
        status = "uptrend" if above is True else ("risk-off" if above is False else "unknown")
        if status == "risk-off":
            risk_off_count += 1
        r["market_regime"] = {"benchmark": b, "above_200sma": above, "status": status}
    # Marker 2 — sector strength (FLAG ONLY, no grade change)
    sector_medians, market_3m = compute_sector_strength(results)
    lagging_count = sum(1 for r in results if (r.get("sector_strength") or {}).get("status") == "lagging")

    # Earnings-date guard (FLAG ONLY) — scoped to actionable candidates (A+/A); live .calendar.
    n_to_check = sum(1 for r in results if r.get("grade") in EARNINGS_GUARD_GRADES)
    print(f"Earnings guard: checking {n_to_check} {'/'.join(EARNINGS_GUARD_GRADES)} candidates...")
    earnings_soon_count = apply_earnings_guard(results)

    print(f"Scan complete: {len(results)} results")
    print(f"Market regime: {sum(1 for v in regime_by_bench.values() if v.get('above_200sma') is True)}/"
          f"{len(regime_by_bench)} benchmarks in uptrend; {risk_off_count} candidates in risk-off markets")
    print(f"Sector strength: {len(sector_medians)} sectors ranked; {lagging_count} candidates in lagging sectors")
    print(f"Earnings guard: {earnings_soon_count} candidate(s) report within {EARNINGS_GUARD_DAYS} days")

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
                "market_regime": (r.get("market_regime") or {}).get("status"),
                "sector_strength": (r.get("sector_strength") or {}).get("status"),
                "earnings_date": (r.get("earnings") or {}).get("next_date"),
                "earnings_soon": (r.get("earnings") or {}).get("soon"),
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
    # Marker 1 — prepend a market-regime summary (flag only; does not change grades)
    regime_lines = [
        "=" * 80,
        "MARKET REGIME (benchmark index vs its 200-day SMA) — flag only, grades unchanged",
        "=" * 80,
    ]
    for b in sorted(regime_by_bench):
        above = regime_by_bench[b].get("above_200sma")
        label = ("UPTREND  (above 200 SMA)" if above is True
                 else "RISK-OFF (below 200 SMA)" if above is False else "unknown (no data)")
        regime_lines.append(f"  {b:8}  {label}")
    regime_lines.append(f"  => {risk_off_count} candidate(s) currently in a risk-off market")
    regime_lines.append("")
    # Marker 2 — sector strength summary (flag only)
    regime_lines.append("=" * 80)
    regime_lines.append("SECTOR STRENGTH (median 3M return per sector vs universe) — flag only")
    regime_lines.append("=" * 80)
    for sec in sorted(sector_medians, key=lambda s: sector_medians[s], reverse=True):
        med = sector_medians[sec]
        status = next((r["sector_strength"]["status"] for r in results
                       if (r.get("sector_strength") or {}).get("sector") == sec), "")
        regime_lines.append(f"  {sec:26}  3M median {med:+6.1f}%   {status.upper()}")
    regime_lines.append(f"  (market 3M median {market_3m:+.1f}%; {lagging_count} candidate(s) in lagging sectors)")
    regime_lines.append("")
    # Earnings-date guard summary (flag only) — A+/A candidates reporting within the window
    regime_lines.append("=" * 80)
    regime_lines.append(f"EARNINGS WATCH ({'/'.join(EARNINGS_GUARD_GRADES)} candidates reporting within {EARNINGS_GUARD_DAYS} days) — flag only")
    regime_lines.append("=" * 80)
    soon = sorted(
        (r for r in results if (r.get("earnings") or {}).get("soon")),
        key=lambda r: (r.get("earnings") or {}).get("days_until", 99),
    )
    if soon:
        for r in soon:
            e = r["earnings"]
            regime_lines.append(f"  {r.get('ticker',''):10} {r.get('grade',''):3}  earnings {e['next_date']} (in {e['days_until']}d) — avoid fresh entry")
    else:
        regime_lines.append("  none")
    regime_lines.append("")
    report_txt = "\n".join(regime_lines) + "\n" + report_txt
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
