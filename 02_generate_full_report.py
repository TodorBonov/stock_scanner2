"""
Generate full Minervini SEPA analysis report from cached data
Produces: Summary report + Detailed list of all stocks
"""
import importlib.util
import json
import sys
import io
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Optional
from bot import TradingBot
from minervini_scanner import MinerviniScanner
from data_provider import StockDataProvider
from logger_config import setup_logging, get_logger
import pandas as pd

# Fix Windows console encoding (skip when running under pytest to avoid breaking capture)
if sys.platform == 'win32' and 'pytest' not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Set up logging
setup_logging(log_level="INFO", log_to_file=True)
logger = get_logger(__name__)

from config import CACHE_FILE, REPORTS_DIR, SCAN_RESULTS_LATEST, REQUIRE_MARKET_ABOVE_200SMA, USE_ATR_STOP
from cache_utils import load_cached_data
from pre_breakout_utils import get_pre_breakout_stocks, actionability_sort_key
from pre_breakout_config import PRE_BREAKOUT_MAX_DISTANCE_PCT, PRE_BREAKOUT_MIN_GRADE, PRE_BREAKOUT_NEAR_PIVOT_PCT
from benchmark_mapping import get_benchmark


def sanitize_for_json(obj):
    """Convert numpy/datetime types to JSON-serializable types."""
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
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    if hasattr(obj, "isoformat"):  # datetime, pd.Timestamp
        return obj.isoformat() if hasattr(obj, "isoformat") else str(obj)
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    return str(obj)


def convert_cached_data_to_dataframe(cached_stock: Dict) -> Optional[pd.DataFrame]:
    """Convert cached historical data back to DataFrame"""
    try:
        hist_dict = cached_stock.get("historical_data", {})
        if not hist_dict or "data" not in hist_dict:
            return None
        
        # Reconstruct DataFrame
        data = hist_dict["data"]
        df = pd.DataFrame(data)
        
        # Convert index back to datetime
        if "index" in hist_dict and hist_dict["index"]:
            df.index = pd.to_datetime(hist_dict["index"], utc=True)
        elif "Date" in df.columns:
            df.index = pd.to_datetime(df["Date"])
            df = df.drop("Date", axis=1)
        else:
            # Try to find date column
            for col in df.columns:
                if 'date' in col.lower() or 'time' in col.lower():
                    df.index = pd.to_datetime(df[col], utc=True)
                    df = df.drop(col, axis=1)
                    break
        
        # Ensure proper column names (case-insensitive)
        df.columns = [col.capitalize() if col.lower() in ['open', 'high', 'low', 'close', 'volume'] else col 
                     for col in df.columns]
        
        # Map common column name variations
        col_mapping = {
            'Open': ['Open', 'open', 'OPEN'],
            'High': ['High', 'high', 'HIGH'],
            'Low': ['Low', 'low', 'LOW'],
            'Close': ['Close', 'close', 'CLOSE', 'Adj Close', 'adj close'],
            'Volume': ['Volume', 'volume', 'VOLUME', 'Vol', 'vol']
        }
        
        # Find and rename columns
        for target_col, variations in col_mapping.items():
            for var in variations:
                if var in df.columns and target_col not in df.columns:
                    df = df.rename(columns={var: target_col})
        
        # Ensure required columns exist
        required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            logger.warning(f"Missing columns: {missing_cols}. Available: {list(df.columns)}")
            return None
        
        # Return only required columns in correct order
        return df[required_cols]
    except Exception as e:
        logger.error(f"Error converting cached data to DataFrame: {e}", exc_info=True)
        return None


class CachedDataProvider:
    """Data provider that uses cached data"""
    def __init__(self, cached_stocks: Dict, original_provider):
        self.cached_stocks = cached_stocks
        self.original_provider = original_provider
    
    def get_historical_data(self, ticker: str, period: str = "1y", interval: str = "1d"):
        """Get historical data from cache or fallback to original"""
        if ticker in self.cached_stocks:
            cached = self.cached_stocks[ticker]
            if cached.get("data_available", False):
                hist = convert_cached_data_to_dataframe(cached)
                if hist is not None and not hist.empty:
                    return hist
        # Fallback to original provider if not in cache
        return self.original_provider.get_historical_data(ticker, period, interval)
    
    def get_stock_info(self, ticker: str):
        """Get stock info from cache or fallback to original"""
        if ticker in self.cached_stocks:
            cached = self.cached_stocks[ticker]
            stock_info = cached.get("stock_info", {})
            if stock_info:
                return stock_info
        return self.original_provider.get_stock_info(ticker)
    
    def calculate_relative_strength(self, ticker: str, benchmark: str, period: int = 252):
        """Use original provider for relative strength (needs benchmark data)"""
        return self.original_provider.calculate_relative_strength(ticker, benchmark, period)


def scan_all_stocks_from_cache(cached_data: Dict, benchmark: str = "^GDAXI", single_ticker: Optional[str] = None):
    """Scan all stocks using cached data"""
    stocks = cached_data.get("stocks", {})
    
    # Initialize bot
    bot = TradingBot(skip_trading212=True, benchmark=benchmark)
    
    # Create cached data provider
    cached_provider = CachedDataProvider(stocks, bot.data_provider)
    
    # Create scanner with cached provider
    scanner = MinerviniScanner(cached_provider, benchmark=benchmark)
    
    results = []
    
    # Filter to single ticker if specified
    if single_ticker:
        if single_ticker in stocks:
            stocks = {single_ticker: stocks[single_ticker]}
        else:
            logger.error(f"Ticker {single_ticker} not found in cache")
            return [], scanner
    
    total = len(stocks)
    print(f"\n{'='*80}")
    print(f"RUNNING MINERVINI SEPA ANALYSIS")
    print(f"{'='*80}")
    print(f"Total stocks: {total}")
    if single_ticker:
        print(f"Single stock mode: {single_ticker}")
    print(f"{'='*80}\n")
    
    # Scan each stock
    for i, (ticker, cached_stock) in enumerate(stocks.items(), 1):
        if not cached_stock.get("data_available", False):
            # Skip stocks without data
            error_msg = cached_stock.get("error", "No data available")
            print(f"[{i}/{total}] {ticker:12s} - ✗ {error_msg}")
            results.append({
                "ticker": ticker,
                "error": error_msg,
                "meets_criteria": False,
                "overall_grade": "F"
            })
            continue
        
        print(f"[{i}/{total}] Scanning {ticker:12s}...", end=" ", flush=True)
        
        # Scan using cached data (per-ticker benchmark when mapping available)
        try:
            benchmark_override = get_benchmark(ticker, benchmark)
            result = scanner.scan_stock(ticker, benchmark_override=benchmark_override)
            # Add company name from cached stock_info if available
            cached_stock_info = cached_stock.get("stock_info", {})
            company_name = cached_stock_info.get("company_name", "")
            if company_name and "stock_info" in result:
                result["stock_info"]["company_name"] = company_name
            elif company_name:
                if "stock_info" not in result:
                    result["stock_info"] = {}
                result["stock_info"]["company_name"] = company_name
            
            # Add data timestamp from cached data
            result["data_timestamp"] = cached_stock.get("fetched_at")
            result["data_date_range"] = cached_stock.get("date_range", {})
            
            grade = result.get("overall_grade", "F")
            meets = "✓" if result.get("meets_criteria", False) else "✗"
            print(f"{meets} Grade: {grade}")
            results.append(result)
        except Exception as e:
            print(f"✗ Error: {e}")
            logger.error(f"Error scanning {ticker}: {e}", exc_info=True)
            results.append({
                "ticker": ticker,
                "error": str(e),
                "meets_criteria": False,
                "overall_grade": "F"
            })
    
    return results, scanner


def get_company_name(result: Dict) -> str:
    """Extract company name from result"""
    stock_info = result.get("stock_info", {})
    company_name = stock_info.get("company_name", "")
    return company_name if company_name else "N/A"


def generate_summary_report(results: List[Dict], output_file: Optional[Path] = None, market_regime: Optional[Dict] = None):
    """Generate summary report with grade distribution. market_regime: from scanner.get_market_regime() when REQUIRE_MARKET_ABOVE_200SMA."""
    total = len(results)
    grade_counts = defaultdict(int)
    meets_criteria = sum(1 for r in results if r.get('meets_criteria', False))
    position_sizes = defaultdict(int)
    criteria_pass = defaultdict(int)
    
    for result in results:
        if "error" not in result:
            grade = result.get("overall_grade", "F")
            grade_counts[grade] += 1
            position = result.get("position_size", "None")
            position_sizes[position] += 1
            
            checklist = result.get("checklist", {})
            if checklist.get("trend_structure", {}).get("passed", False):
                criteria_pass["Trend & Structure"] += 1
            if checklist.get("base_quality", {}).get("passed", False):
                criteria_pass["Base Quality"] += 1
            if checklist.get("relative_strength", {}).get("passed", False):
                criteria_pass["Relative Strength"] += 1
            if checklist.get("volume_signature", {}).get("passed", False):
                criteria_pass["Volume Signature"] += 1
            if checklist.get("breakout_rules", {}).get("passed", False):
                criteria_pass["Breakout Rules"] += 1
    
    # Generate report
    lines = []
    lines.append("=" * 100)
    lines.append("MINERVINI SEPA SCAN - SUMMARY REPORT")
    lines.append("=" * 100)
    lines.append(f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # Data Freshness Information
    data_timestamps = [r.get("data_timestamp") for r in results if r.get("data_timestamp")]
    if data_timestamps:
        # Find oldest and newest data timestamps
        try:
            from datetime import datetime as dt
            parsed_times = []
            for ts in data_timestamps:
                try:
                    if 'T' in ts:
                        dt_str = ts.split('T')[0] + ' ' + ts.split('T')[1].split('.')[0].split('+')[0]
                        parsed_times.append(dt.strptime(dt_str[:19], '%Y-%m-%d %H:%M:%S'))
                except Exception as e:
                    logger.debug("Could not parse data timestamp %s: %s", ts, e)
                    pass
            
            if parsed_times:
                oldest_data = min(parsed_times)
                newest_data = max(parsed_times)
                lines.append("📅 DATA FRESHNESS")
                lines.append("-" * 100)
                lines.append(f"  Oldest Data: {oldest_data.strftime('%Y-%m-%d %H:%M:%S')}")
                lines.append(f"  Newest Data: {newest_data.strftime('%Y-%m-%d %H:%M:%S')}")
                if (datetime.now() - newest_data.replace(tzinfo=None)).days > 1:
                    days_old = (datetime.now() - newest_data.replace(tzinfo=None)).days
                    lines.append(f"  ⚠️  Warning: Data is {days_old} day(s) old - consider refreshing")
                lines.append("")
        except Exception as e:
            logger.debug("Data freshness section failed: %s", e)
            pass
    
    # Market regime (optional)
    if REQUIRE_MARKET_ABOVE_200SMA and market_regime and market_regime.get("error") is None:
        above = market_regime.get("above_200sma")
        bench = market_regime.get("benchmark", "")
        if above is True:
            lines.append("🌐 MARKET REGIME")
            lines.append("-" * 100)
            lines.append(f"  {bench}: Above 200 SMA ✓ (favorable for new breakouts)")
            lines.append("")
        elif above is False:
            lines.append("🌐 MARKET REGIME")
            lines.append("-" * 100)
            lines.append(f"  {bench}: Below 200 SMA ⚠ (consider reducing size or skipping new breakouts)")
            lines.append("")
    
    # Overall Statistics
    lines.append("📊 OVERALL STATISTICS")
    lines.append("-" * 100)
    lines.append(f"Total Stocks Scanned: {total}")
    lines.append(f"Stocks Meeting Criteria: {meets_criteria} ({meets_criteria/total*100:.1f}%)")
    lines.append(f"Stocks NOT Meeting Criteria: {total - meets_criteria} ({(total-meets_criteria)/total*100:.1f}%)")
    lines.append("")
    
    # Grade Distribution
    lines.append("🎯 GRADE DISTRIBUTION")
    lines.append("-" * 100)
    grade_order = ["A+", "A", "B", "C", "F"]
    
    for grade in grade_order:
        count = grade_counts.get(grade, 0)
        percentage = (count / total * 100) if total > 0 else 0
        bar_length = int(percentage / 2)
        bar = "█" * bar_length
        
        if grade == "A+":
            position = "Full Position"
        elif grade == "A":
            position = "Half Position"
        elif grade == "B":
            position = "Half Position (Watch)"
        elif grade == "C":
            position = "Avoid"
        else:
            position = "Avoid"
        
        lines.append(f"{grade:3s}: {count:4d} stocks ({percentage:5.1f}%) {bar} {position}")
    
    lines.append("")
    
    # Position Size Distribution
    lines.append("💰 POSITION SIZE RECOMMENDATIONS")
    lines.append("-" * 100)
    for position in ["Full", "Half", "None"]:
        count = position_sizes.get(position, 0)
        percentage = (count / total * 100) if total > 0 else 0
        lines.append(f"{position:6s}: {count:4d} stocks ({percentage:5.1f}%)")
    lines.append("")
    
    # Criteria Pass Rates
    lines.append("✅ CRITERIA PASS RATES")
    lines.append("-" * 100)
    criteria_names = [
        "Trend & Structure",
        "Base Quality",
        "Relative Strength",
        "Volume Signature",
        "Breakout Rules"
    ]
    
    for criterion in criteria_names:
        count = criteria_pass.get(criterion, 0)
        percentage = (count / total * 100) if total > 0 else 0
        bar_length = int(percentage / 2)
        bar = "█" * bar_length
        lines.append(f"{criterion:25s}: {count:4d} stocks ({percentage:5.1f}%) {bar}")
    
    lines.append("")
    
    # Top Stocks by Grade
    lines.append("📈 TOP STOCKS BY GRADE")
    lines.append("-" * 100)
    grade_order_list = ["A+", "A", "B", "C"]
    for grade in grade_order_list:
        stocks = [r for r in results if "error" not in r and r.get("overall_grade") == grade]
        if not stocks:
            continue
        
        # Sort by price from 52W high (closest to high is better)
        stocks_sorted = sorted(
            stocks,
            key=lambda x: x.get("detailed_analysis", {}).get("price_from_52w_high_pct", 100)
        )
        
        lines.append(f"\n{grade} Grade ({len(stocks_sorted)} stocks):")
        # Show all stocks for A+ and A grades, top 10 for others
        max_stocks = len(stocks_sorted) if grade in ["A+", "A"] else 10
        for i, stock in enumerate(stocks_sorted[:max_stocks], 1):
            ticker = stock.get("ticker", "UNKNOWN")
            company_name = get_company_name(stock)
            price_pct = stock.get("detailed_analysis", {}).get("price_from_52w_high_pct", 0)
            buy_sell = stock.get("buy_sell_prices", {})
            data_timestamp = stock.get("data_timestamp")
            
            # Format company name
            if company_name and company_name != "N/A":
                name_part = f"{ticker:12s} ({company_name[:40]})"
            else:
                name_part = f"{ticker:12s}"
            
            # Add price info
            price_info = f"{price_pct:.1f}% from 52W high"
            
            # Format timestamp if available
            timestamp_str = ""
            if data_timestamp:
                try:
                    # Handle ISO format timestamp
                    if 'T' in data_timestamp:
                        dt_str = data_timestamp.split('T')[0] + ' ' + data_timestamp.split('T')[1].split('.')[0].split('+')[0]
                        timestamp_str = f" | Data: {dt_str[:16]}"  # YYYY-MM-DD HH:MM
                    else:
                        timestamp_str = f" | Data: {data_timestamp[:16]}" if len(data_timestamp) > 16 else f" | Data: {data_timestamp}"
                except Exception as e:
                    logger.debug("Timestamp format failed for %s: %s", data_timestamp, e)
                    timestamp_str = f" | Data: {data_timestamp[:16]}" if data_timestamp and len(str(data_timestamp)) > 16 else f" | Data: {data_timestamp}"
            
            # Add buy/sell prices if available
            if buy_sell and buy_sell.get("pivot_price") is not None:
                buy_price = buy_sell.get("buy_price", 0)
                stop_loss = buy_sell.get("stop_loss", 0)
                profit_target_1 = buy_sell.get("profit_target_1", 0)
                lines.append(f"  {i:2d}. {name_part} - {price_info}{timestamp_str}")
                stop_line = f"      Buy: ${buy_price:.2f} | Stop: ${stop_loss:.2f} | Target 1: ${profit_target_1:.2f}"
                if USE_ATR_STOP and buy_sell.get("stop_loss_atr") is not None:
                    stop_line += f" | Stop(ATR): ${buy_sell.get('stop_loss_atr', 0):.2f}"
                lines.append(stop_line)
                if buy_sell.get("days_since_base_end") is not None:
                    lines.append(f"      Days since base end: {buy_sell.get('days_since_base_end')}")
            else:
                lines.append(f"  {i:2d}. {name_part} - {price_info}{timestamp_str}")
    
    # Best setups (A-grade): same A+ and A stocks, ranked by setup quality
    best_setup_grades = ["A+", "A"]
    best_setup_stocks = [
        r for r in results
        if "error" not in r and r.get("overall_grade") in best_setup_grades
    ]
    if best_setup_stocks:
        best_setup_sorted = sorted(best_setup_stocks, key=actionability_sort_key)
        lines.append("")
        lines.append("📐 BEST SETUPS (A-grade by setup quality)")
        lines.append("-" * 100)
        lines.append("  Ranked by: base depth (tighter) → volume contraction (drier) → distance to pivot (closer) → RS rating (higher)")
        lines.append("")
        for i, stock in enumerate(best_setup_sorted, 1):
            ticker = stock.get("ticker", "UNKNOWN")
            company_name = get_company_name(stock)
            buy_sell = stock.get("buy_sell_prices", {})
            bq = stock.get("checklist", {}).get("base_quality", {}).get("details") or {}
            rs_details = stock.get("checklist", {}).get("relative_strength", {}).get("details") or {}
            if company_name and company_name != "N/A":
                name_part = f"{ticker:12s} ({company_name[:40]})"
            else:
                name_part = f"{ticker:12s}"
            # Setup metrics line
            base_depth = bq.get("base_depth_pct")
            vol_contract = bq.get("volume_contraction")
            dist_buy = buy_sell.get("distance_to_buy_pct")
            rs_rating = rs_details.get("rs_rating")
            metrics = []
            if base_depth is not None:
                metrics.append(f"base {base_depth:.1f}%")
            if vol_contract is not None:
                metrics.append(f"vol {vol_contract:.2f}x")
            if dist_buy is not None:
                metrics.append(f"dist {dist_buy:.1f}%")
            if rs_rating is not None:
                metrics.append(f"RS {rs_rating:.0f}")
            metrics_str = " | ".join(metrics) if metrics else ""
            lines.append(f"  {i:2d}. {name_part}  [{metrics_str}]")
            if buy_sell and buy_sell.get("pivot_price") is not None:
                buy_price = buy_sell.get("buy_price", 0)
                stop_loss = buy_sell.get("stop_loss", 0)
                profit_target_1 = buy_sell.get("profit_target_1", 0)
                line = f"      Buy: ${buy_price:.2f} | Stop: ${stop_loss:.2f} | Target 1: ${profit_target_1:.2f}"
                if USE_ATR_STOP and buy_sell.get("stop_loss_atr") is not None:
                    line += f" | Stop(ATR): ${buy_sell.get('stop_loss_atr', 0):.2f}"
                lines.append(line)
                if buy_sell.get("days_since_base_end") is not None:
                    lines.append(f"      Days since base end: {buy_sell.get('days_since_base_end')}")
    
    # Pre-breakout setups (setup ready, not yet broken out) - additive view only
    pre_breakout_stocks = get_pre_breakout_stocks(results)
    if pre_breakout_stocks:
        lines.append("")
        lines.append("📐 PRE-BREAKOUT SETUPS (setup ready, not yet broken out)")
        lines.append("-" * 100)
        lines.append(f"  Stocks with valid base, grade ≥ {PRE_BREAKOUT_MIN_GRADE}, within {PRE_BREAKOUT_MAX_DISTANCE_PCT:.0f}% below pivot, breakout not yet triggered.")
        lines.append("  Ranked by: base depth (tighter) → volume contraction (drier) → distance to pivot (closer) → RS rating (higher)")
        lines.append("")
        for i, stock in enumerate(pre_breakout_stocks, 1):
            ticker = stock.get("ticker", "UNKNOWN")
            company_name = get_company_name(stock)
            buy_sell = stock.get("buy_sell_prices", {})
            bq = stock.get("checklist", {}).get("base_quality", {}).get("details") or {}
            rs_details = stock.get("checklist", {}).get("relative_strength", {}).get("details") or {}
            if company_name and company_name != "N/A":
                name_part = f"{ticker:12s} ({company_name[:40]})"
            else:
                name_part = f"{ticker:12s}"
            base_depth = bq.get("base_depth_pct")
            vol_contract = bq.get("volume_contraction")
            dist_buy = buy_sell.get("distance_to_buy_pct")
            rs_rating = rs_details.get("rs_rating")
            metrics = []
            if base_depth is not None:
                metrics.append(f"base {base_depth:.1f}%")
            if vol_contract is not None:
                metrics.append(f"vol {vol_contract:.2f}x")
            if dist_buy is not None:
                metrics.append(f"dist {dist_buy:.1f}%")
            if rs_rating is not None:
                metrics.append(f"RS {rs_rating:.0f}")
            metrics_str = " | ".join(metrics) if metrics else ""
            grade = stock.get("overall_grade", "?")
            near_pivot = (dist_buy is not None and 0 >= dist_buy >= -PRE_BREAKOUT_NEAR_PIVOT_PCT)
            suffix = "  [near pivot]" if near_pivot else ""
            lines.append(f"  {i:2d}. {name_part}  [{metrics_str}]  Grade: {grade}{suffix}")
            if buy_sell and buy_sell.get("pivot_price") is not None:
                buy_price = buy_sell.get("buy_price", 0)
                stop_loss = buy_sell.get("stop_loss", 0)
                profit_target_1 = buy_sell.get("profit_target_1", 0)
                line = f"      Pivot: ${buy_price:.2f} | Stop: ${stop_loss:.2f} | Target 1: ${profit_target_1:.2f}"
                if USE_ATR_STOP and buy_sell.get("stop_loss_atr") is not None:
                    line += f" | Stop(ATR): ${buy_sell.get('stop_loss_atr', 0):.2f}"
                lines.append(line)
                if buy_sell.get("days_since_base_end") is not None:
                    lines.append(f"      Days since base end: {buy_sell.get('days_since_base_end')}")
            br_details = stock.get("checklist", {}).get("breakout_rules", {}).get("details", {})
            if br_details.get("last_above_pivot_date") is not None or br_details.get("days_since_breakout") is not None:
                last_date = br_details.get("last_above_pivot_date")
                days_since = br_details.get("days_since_breakout")
                if last_date is not None:
                    lines.append(f"      Last close above pivot: {last_date}" + (f" ({days_since} days ago)" if days_since is not None else ""))
                elif days_since is not None:
                    lines.append(f"      Days since breakout: {days_since}")
    
    lines.append("")
    lines.append("=" * 100)
    
    # Print to console
    report_text = "\n".join(lines)
    print(report_text)
    
    # Save to file
    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report_text)
        print(f"\nSummary report saved to: {output_file}")
    
    return report_text


def format_stock_header(result: Dict) -> str:
    """Format stock header with ticker and company name"""
    ticker = result.get("ticker", "UNKNOWN")
    company_name = get_company_name(result)
    grade = result.get("overall_grade", "F")
    meets = result.get("meets_criteria", False)
    position = result.get("position_size", "None")
    
    if company_name and company_name != "N/A":
        return f"STOCK: {ticker} ({company_name}) | Grade: {grade} | Meets Criteria: {meets} | Position Size: {position}"
    else:
        return f"STOCK: {ticker} | Grade: {grade} | Meets Criteria: {meets} | Position Size: {position}"


def generate_detailed_report(results: List[Dict], output_file: Optional[Path] = None):
    """Generate detailed report with complete explanations for each stock"""
    # Sort by grade (A+ first, F last)
    grade_order = {"A+": 0, "A": 1, "B": 2, "C": 3, "F": 4}
    results_sorted = sorted(
        [r for r in results if "error" not in r],
        key=lambda x: (grade_order.get(x.get("overall_grade", "F"), 4), 
                       -x.get("detailed_analysis", {}).get("price_from_52w_high_pct", 100))
    )
    
    # Group by grade
    by_grade = defaultdict(list)
    for result in results_sorted:
        grade = result.get("overall_grade", "F")
        by_grade[grade].append(result)
    
    # Generate report
    lines = []
    lines.append("=" * 100)
    lines.append("MINERVINI SEPA SCAN - DETAILED ANALYSIS")
    lines.append("=" * 100)
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Total Stocks: {len(results_sorted)}")
    lines.append("")
    
    # Print by grade
    grade_order_list = ["A+", "A", "B", "C", "F"]
    for grade in grade_order_list:
        stocks = by_grade.get(grade, [])
        if not stocks:
            continue
        
        lines.append("#" * 100)
        lines.append(f"# GRADE {grade} ({len(stocks)} stocks)")
        lines.append("#" * 100)
        lines.append("")
        
        for stock in stocks:
            # Stock header with company name
            lines.append("=" * 100)
            lines.append(format_stock_header(stock))
            lines.append("=" * 100)
            lines.append("")
            
            # Data timestamp
            data_timestamp = stock.get("data_timestamp")
            data_date_range = stock.get("data_date_range", {})
            if data_timestamp:
                try:
                    # Handle ISO format timestamp
                    if 'T' in data_timestamp:
                        dt_str = data_timestamp.split('T')[0] + ' ' + data_timestamp.split('T')[1].split('.')[0].split('+')[0]
                        timestamp_str = dt_str[:19]  # YYYY-MM-DD HH:MM:SS
                    else:
                        timestamp_str = data_timestamp
                except Exception as e:
                    logger.debug("Data timestamp format failed: %s", e)
                    timestamp_str = data_timestamp
                
                lines.append("[DATA TIMESTAMP]")
                lines.append(f"  Data Fetched: {timestamp_str}")
                if data_date_range:
                    start_date = data_date_range.get('start', 'N/A')
                    end_date = data_date_range.get('end', 'N/A')
                    # Format dates (remove timezone info if present)
                    if start_date != 'N/A' and 'T' in str(start_date):
                        start_date = str(start_date).split('T')[0]
                    if end_date != 'N/A' and 'T' in str(end_date):
                        end_date = str(end_date).split('T')[0]
                    lines.append(f"  Data Range: {start_date} to {end_date}")
                lines.append("")
            
            # Price info
            detailed = stock.get("detailed_analysis", {})
            if detailed:
                # Get last trading date from data range
                last_trade_date = "N/A"
                if data_date_range and data_date_range.get('end'):
                    end_date = data_date_range.get('end')
                    if 'T' in str(end_date):
                        last_trade_date = str(end_date).split('T')[0]
                    else:
                        last_trade_date = str(end_date).split()[0] if ' ' in str(end_date) else str(end_date)
                
                lines.append("[PRICE INFO]")
                if last_trade_date != "N/A":
                    lines.append(f"  Last Close Price (as of {last_trade_date}): ${detailed.get('current_price', 0):.2f}")
                else:
                    lines.append(f"  Last Close Price: ${detailed.get('current_price', 0):.2f}")
                lines.append(f"  52-Week High: ${detailed.get('52_week_high', 0):.2f}")
                lines.append(f"  52-Week Low: ${detailed.get('52_week_low', 0):.2f}")
                lines.append(f"  From 52W High: {detailed.get('price_from_52w_high_pct', 0):.1f}%")
                lines.append(f"  From 52W Low: {detailed.get('price_from_52w_low_pct', 0):.1f}%")
                lines.append("")
            
            # Buy/Sell Prices (Entry/Exit Points)
            buy_sell = stock.get("buy_sell_prices", {})
            if buy_sell and buy_sell.get("pivot_price") is not None:
                lines.append("[ENTRY/EXIT PRICES]")
                lines.append(f"  Pivot Point (Base High): ${buy_sell.get('pivot_price', 0):.2f}")
                lines.append(f"  Buy Price (Entry): ${buy_sell.get('buy_price', 0):.2f}")
                if buy_sell.get('distance_to_buy_pct', 0) != 0:
                    lines.append(f"  Distance to Buy: {buy_sell.get('distance_to_buy_pct', 0):.1f}%")
                lines.append("")
                lines.append(f"  Stop Loss: ${buy_sell.get('stop_loss', 0):.2f} ({buy_sell.get('stop_loss_pct', 0):.1f}% below entry)")
                if USE_ATR_STOP and buy_sell.get("stop_loss_atr") is not None:
                    lines.append(f"  Stop Loss (ATR): ${buy_sell.get('stop_loss_atr', 0):.2f}")
                if buy_sell.get("days_since_base_end") is not None:
                    lines.append(f"  Days Since Base End: {buy_sell.get('days_since_base_end')}")
                lines.append(f"  Profit Target 1: ${buy_sell.get('profit_target_1', 0):.2f} ({buy_sell.get('profit_target_1_pct', 0):.1f}% above entry) - Take Partial Profits")
                lines.append(f"  Profit Target 2: ${buy_sell.get('profit_target_2', 0):.2f} ({buy_sell.get('profit_target_2_pct', 0):.1f}% above entry) - Let Winners Run")
                if buy_sell.get('risk_reward_ratio'):
                    lines.append(f"  Risk/Reward Ratio: {buy_sell.get('risk_reward_ratio', 0):.2f}:1")
                lines.append("")
                lines.append(f"  Risk per Share: ${buy_sell.get('risk_per_share', 0):.2f}")
                lines.append(f"  Potential Profit (Target 1): ${buy_sell.get('potential_profit_1', 0):.2f}")
                lines.append(f"  Potential Profit (Target 2): ${buy_sell.get('potential_profit_2', 0):.2f}")
                lines.append("")
            
            # Checklist summary
            checklist = stock.get("checklist", {})
            criteria_names = [
                ("trend_structure", "Trend & Structure"),
                ("base_quality", "Base Quality"),
                ("relative_strength", "Relative Strength"),
                ("volume_signature", "Volume Signature"),
                ("breakout_rules", "Breakout Rules")
            ]
            
            for key, name in criteria_names:
                if key in checklist:
                    criterion = checklist[key]
                    passed = criterion.get("passed", False)
                    status = "[PASS]" if passed else "[FAIL]"
                    lines.append("=" * 100)
                    lines.append(f"{status} PART {criteria_names.index((key, name)) + 1}: {name}")
                    lines.append("=" * 100)
                    
                    # Show KPI values from details
                    details = criterion.get("details", {})
                    if details:
                        lines.append("[KPIs]")
                        
                        if key == "trend_structure":
                            # Trend & Structure KPIs
                            # Get last trading date for context
                            last_trade_date = ""
                            if data_date_range and data_date_range.get('end'):
                                end_date = data_date_range.get('end')
                                if 'T' in str(end_date):
                                    last_trade_date = f" (as of {str(end_date).split('T')[0]})"
                            lines.append(f"  Last Close Price{last_trade_date}: ${details.get('current_price', 0):.2f}")
                            lines.append(f"  SMA 50: ${details.get('sma_50', 0):.2f} | Above: {'✓' if details.get('above_50') else '✗'}")
                            lines.append(f"  SMA 150: ${details.get('sma_150', 0):.2f} | Above: {'✓' if details.get('above_150') else '✗'}")
                            lines.append(f"  SMA 200: ${details.get('sma_200', 0):.2f} | Above: {'✓' if details.get('above_200') else '✗'}")
                            lines.append(f"  SMA Order (50>150>200): {'✓' if details.get('sma_order_correct') else '✗'}")
                            lines.append(f"  52W High: ${details.get('52_week_high', 0):.2f}")
                            lines.append(f"  52W Low: ${details.get('52_week_low', 0):.2f}")
                            lines.append(f"  Price from 52W Low: {details.get('price_from_52w_low_pct', 0):.1f}% (need ≥30%)")
                            lines.append(f"  Price from 52W High: {details.get('price_from_52w_high_pct', 0):.1f}% (need ≤15%)")
                            
                        elif key == "base_quality":
                            # Base Quality KPIs
                            lines.append(f"  Base Length: {details.get('base_length_weeks', 0):.1f} weeks (need 3-8 weeks)")
                            lines.append(f"  Base Depth: {details.get('base_depth_pct', 0):.1f}% (need ≤25%, ≤15% is elite)")
                            lines.append(f"  Base High: ${details.get('base_high', 0):.2f}")
                            lines.append(f"  Base Low: ${details.get('base_low', 0):.2f}")
                            lines.append(f"  Base Volatility: {details.get('base_volatility', 0):.4f}")
                            lines.append(f"  Avg Volatility: {details.get('avg_volatility', 0):.4f}")
                            lines.append(f"  Avg Close Position: {details.get('avg_close_position_pct', 0):.1f}% (need ≥50%)")
                            lines.append(f"  Volume Contraction: {details.get('volume_contraction', 0):.2f}x (need <0.95x)")
                            
                        elif key == "relative_strength":
                            # Relative Strength KPIs
                            lines.append(f"  RSI(14): {details.get('rsi_14', 0):.1f} (need >60)")
                            lines.append(f"  Relative Strength: {details.get('relative_strength', 0):.4f} (need >0)")
                            lines.append(f"  RS Rating: {details.get('rs_rating', 0):.1f}")
                            lines.append(f"  Stock Return: {details.get('stock_return', 0):.2%}")
                            lines.append(f"  Benchmark Return: {details.get('benchmark_return', 0):.2%}")
                            lines.append(f"  Outperforming: {'✓' if details.get('outperforming') else '✗'}")
                            
                        elif key == "volume_signature":
                            # Volume Signature KPIs
                            lines.append(f"  Base Avg Volume: {details.get('base_avg_volume', 0):,.0f}")
                            lines.append(f"  Pre-Base Volume: {details.get('pre_base_volume', 0):,.0f}")
                            lines.append(f"  Volume Contraction: {details.get('volume_contraction', 0):.2f}x (need <0.9x)")
                            lines.append(f"  Recent Volume: {details.get('recent_volume', 0):,.0f}")
                            lines.append(f"  Avg Volume (20d): {details.get('avg_volume_20d', 0):,.0f}")
                            lines.append(f"  Volume Increase: {details.get('volume_increase', 0):.2f}x (need ≥1.4x for breakout)")
                            lines.append(f"  In Breakout: {'✓' if details.get('in_breakout') else '✗'}")
                            
                        elif key == "breakout_rules":
                            # Breakout Rules KPIs
                            lines.append(f"  Pivot Price (Base High): ${details.get('pivot_price', 0):.2f}")
                            # Get last trading date for context
                            last_trade_date = ""
                            if data_date_range and data_date_range.get('end'):
                                end_date = data_date_range.get('end')
                                if 'T' in str(end_date):
                                    last_trade_date = f" (as of {str(end_date).split('T')[0]})"
                            lines.append(f"  Last Close Price{last_trade_date}: ${details.get('current_price', 0):.2f}")
                            if details.get('breakout_day_price'):
                                lines.append(f"  Breakout Day Price: ${details.get('breakout_day_price', 0):.2f}")
                            lines.append(f"  Clears Pivot (≥2% above): {'✓' if details.get('clears_pivot') else '✗'}")
                            lines.append(f"  Close Position on Breakout: {details.get('close_position_pct', 0):.1f}% (need ≥70%)")
                            lines.append(f"  Volume Ratio: {details.get('volume_ratio', 0):.2f}x (need ≥1.2x)")
                            lines.append(f"  In Breakout: {'✓' if details.get('in_breakout') else '✗'}")
                            if details.get('last_above_pivot_date') is not None:
                                lines.append(f"  Last Close Above Pivot: {details.get('last_above_pivot_date')}")
                            if details.get('days_since_breakout') is not None:
                                lines.append(f"  Days Since Breakout: {details.get('days_since_breakout')}")
                        
                        lines.append("")
                    
                    # Show failures/warnings
                    failures = criterion.get("failures", [])
                    if failures:
                        lines.append("  Failures/Warnings:")
                        for failure in failures:
                            lines.append(f"    - {failure}")
                        lines.append("")
                    else:
                        lines.append("  ✓ All criteria met")
                        lines.append("")
            
            lines.append("")
    
    # Print to console (truncated for very long reports)
    report_text = "\n".join(lines)
    if len(report_text) > 50000:  # If very long, only show first part
        print(report_text[:50000])
        print("\n... (report truncated in console, full version saved to file)")
    else:
        print(report_text)
    
    # Save to file
    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report_text)
        print(f"\nDetailed report saved to: {output_file}")
    
    return report_text


def main():
    parser = argparse.ArgumentParser(
        description="Generate full Minervini SEPA analysis report from cached data"
    )
    parser.add_argument(
        "--ticker",
        type=str,
        help="Analyze single stock only (optional)"
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh data before analysis (runs fetch_stock_data.py)"
    )
    parser.add_argument(
        "--benchmark",
        default="^GDAXI",
        type=str,
        help="Benchmark index for RS (default: ^GDAXI). Examples: ^GDAXI, ^GSPC, ^FCHI, ^AEX, ^SSMI, ^GSPTSE. Per-ticker mapping in benchmark_mapping.py when scanning mixed watchlists."
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Generate only summary report (skip detailed)"
    )
    parser.add_argument(
        "--detailed-only",
        action="store_true",
        help="Generate only detailed report (skip summary)"
    )
    
    args = parser.parse_args()
    
    # Refresh data if requested (load 01_fetch_stock_data via importlib - module name can't start with number)
    if args.refresh:
        print("Refreshing stock data...")
        _fetch_spec = importlib.util.spec_from_file_location(
            "fetch_stock_data", Path(__file__).parent / "01_fetch_stock_data.py"
        )
        _fetch_module = importlib.util.module_from_spec(_fetch_spec)
        _fetch_spec.loader.exec_module(_fetch_module)
        _fetch_module.fetch_all_data(force_refresh=True, benchmark=args.benchmark)
        print()
    
    # Load cached data (shared cache_utils)
    cached_data = load_cached_data()
    if cached_data is None:
        logger.error("Cache file not found or invalid. Run 01_fetch_stock_data.py first.")
        print("Error: Could not load cached data")
        print("Please run: python 01_fetch_stock_data.py")
        sys.exit(1)
    logger.info(f"Loaded {len(cached_data.get('stocks', {}))} stocks from cache")
    
    # Scan all stocks
    results, scanner = scan_all_stocks_from_cache(
        cached_data, 
        benchmark=args.benchmark,
        single_ticker=args.ticker
    )
    
    if not results:
        print("No results to report")
        return
    
    # Save scan results for ChatGPT script (03) to load without re-scanning
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        payload = sanitize_for_json(results)
        with open(SCAN_RESULTS_LATEST, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=0, ensure_ascii=False)
        logger.info(f"Scan results saved to {SCAN_RESULTS_LATEST}")
    except Exception as e:
        logger.warning(f"Could not save scan results for ChatGPT: {e}")
    
    # Generate timestamp for filenames
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Generate reports
    if not args.detailed_only:
        summary_file = REPORTS_DIR / f"summary_report_{timestamp}.txt"
        market_regime = scanner.get_market_regime(args.benchmark) if REQUIRE_MARKET_ABOVE_200SMA else None
        generate_summary_report(results, summary_file, market_regime=market_regime)
        print()
    
    if not args.summary_only:
        detailed_file = REPORTS_DIR / f"detailed_report_{timestamp}.txt"
        generate_detailed_report(results, detailed_file)
    
    print(f"\n{'='*80}")
    print("ANALYSIS COMPLETE")
    print(f"{'='*80}")
    print(f"Reports saved to: {REPORTS_DIR}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()

