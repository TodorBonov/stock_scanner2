"""
ChatGPT Validation Script
Sends A and B grade stocks to ChatGPT for Minervini SEPA analysis validation
"""
import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from logger_config import get_logger
from config import (
    DEFAULT_ENV_PATH,
    OPENAI_API_TIMEOUT,
    OPENAI_CHATGPT_MODEL,
    OPENAI_CHATGPT_MAX_COMPLETION_TOKENS,
    OPENAI_CHATGPT_MAX_A_GRADE_STOCKS,
    OPENAI_CHATGPT_MAX_PRE_BREAKOUT_STOCKS,
    OPENAI_CHATGPT_INCLUDE_FULL_SCAN_DATA,
    OPENAI_CHATGPT_RETRY_ATTEMPTS,
    OPENAI_CHATGPT_RETRY_BASE_SECONDS,
)

logger = get_logger(__name__)

# Load environment variables
env_file = Path(DEFAULT_ENV_PATH)
if env_file.exists():
    load_dotenv(env_file)

from config import REPORTS_DIR, SCAN_RESULTS_LATEST
from cache_utils import load_cached_data
from pre_breakout_utils import get_pre_breakout_stocks

REPORTS_DIR.mkdir(exist_ok=True)


def get_scan_date_from_latest_report() -> Optional[str]:
    """
    Get scan date (data as of) from the latest summary report filename.
    Format: summary_report_YYYYMMDD_HHMMSS.txt -> returns YYYY-MM-DD.
    Returns None if no matching report found.
    """
    import re
    pattern = re.compile(r"summary_report_(\d{4})(\d{2})(\d{2})_\d{6}\.txt")
    latest_date = None
    latest_ts = None
    for path in REPORTS_DIR.glob("summary_report_*.txt"):
        m = pattern.match(path.name)
        if m:
            y, mo, d = m.group(1), m.group(2), m.group(3)
            ts = (y, mo, d)
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts
                latest_date = f"{y}-{mo}-{d}"
    return latest_date


def format_stock_data_for_chatgpt(stock_result: Dict, is_pre_breakout: bool = False) -> str:
    """
    Format stock analysis data for ChatGPT prompt.
    When is_pre_breakout=True, prepends a PRE-BREAKOUT WATCHLIST tag and distance to pivot.
    """
    ticker = stock_result.get("ticker", "UNKNOWN")
    company_name = stock_result.get("stock_info", {}).get("company_name", "N/A")
    grade = stock_result.get("overall_grade", "F")
    meets_criteria = stock_result.get("meets_criteria", False)
    position_size = stock_result.get("position_size", "None")
    
    detailed = stock_result.get("detailed_analysis", {})
    checklist = stock_result.get("checklist", {})
    buy_sell = stock_result.get("buy_sell_prices", {})
    stock_info = stock_result.get("stock_info", {})
    
    # Build formatted text
    lines = []
    if is_pre_breakout:
        dist = buy_sell.get("distance_to_buy_pct")
        dist_str = f"{dist:.1f}%" if dist is not None else "N/A"
        lines.append("*** PRE-BREAKOUT WATCHLIST — Not yet broken out; watch for breakout above pivot. ***")
        lines.append(f"*** Distance to pivot: {dist_str} (negative = below pivot) ***")
        lines.append("")
    lines.append(f"STOCK: {ticker} ({company_name})")
    lines.append(f"Grade: {grade} | Meets Criteria: {meets_criteria} | Position Size: {position_size}")
    if stock_result.get("benchmark_used"):
        lines.append(f"Benchmark used for RS: {stock_result.get('benchmark_used')}")
    lines.append("")
    
    # For A stocks (not A+), highlight that we need to know why it's not A+
    if grade == "A":
        lines.append("*** NOTE: This stock is A grade (not A+). Please explain what criteria failures prevent it from being A+. ***")
    elif grade == "A+":
        lines.append("*** NOTE: This stock is A+ grade. Please confirm all criteria are met. ***")
    
    lines.append("")
    
    # Company/Fundamental Information
    lines.append("COMPANY INFO:")
    lines.append(f"  Sector: {stock_info.get('sector', 'N/A')}")
    lines.append(f"  Industry: {stock_info.get('industry', 'N/A')}")
    market_cap = stock_info.get('market_cap', 0)
    if market_cap:
        if market_cap >= 1e12:
            mc_str = f"${market_cap/1e12:.2f}T"
        elif market_cap >= 1e9:
            mc_str = f"${market_cap/1e9:.2f}B"
        elif market_cap >= 1e6:
            mc_str = f"${market_cap/1e6:.2f}M"
        else:
            mc_str = f"${market_cap:,.0f}"
        lines.append(f"  Market Cap: {mc_str}")
    lines.append(f"  Beta: {stock_info.get('beta', 'N/A')}")
    lines.append("")
    
    # Fundamental Metrics
    lines.append("FUNDAMENTAL METRICS:")
    earnings_growth = stock_info.get('earnings_growth')
    if earnings_growth is not None:
        lines.append(f"  Earnings Growth: {earnings_growth:.1f}%")
    revenue_growth = stock_info.get('revenue_growth')
    if revenue_growth is not None:
        lines.append(f"  Revenue Growth: {revenue_growth:.1f}%")
    profit_margins = stock_info.get('profit_margins')
    if profit_margins is not None:
        lines.append(f"  Profit Margins: {profit_margins:.1f}%")
    roe = stock_info.get('return_on_equity')
    if roe is not None:
        lines.append(f"  Return on Equity (ROE): {roe:.1f}%")
    de = stock_info.get('debt_to_equity')
    if de is not None:
        lines.append(f"  Debt to Equity: {de:.1f}")
    lines.append("")
    
    # Valuation Metrics
    lines.append("VALUATION METRICS:")
    trailing_pe = stock_info.get('trailing_pe')
    if trailing_pe is not None:
        lines.append(f"  Trailing P/E: {trailing_pe:.1f}")
    forward_pe = stock_info.get('forward_pe')
    if forward_pe is not None:
        lines.append(f"  Forward P/E: {forward_pe:.1f}")
    div_yield = stock_info.get('dividend_yield')
    if div_yield is not None:
        lines.append(f"  Dividend Yield: {div_yield:.2f}%")
    lines.append("")
    
    # Price Information
    lines.append("PRICE INFORMATION:")
    lines.append(f"  Current Price: ${detailed.get('current_price', 0):.2f}")
    lines.append(f"  52-Week High: ${detailed.get('52_week_high', 0):.2f}")
    lines.append(f"  52-Week Low: ${detailed.get('52_week_low', 0):.2f}")
    lines.append(f"  From 52W High: {detailed.get('price_from_52w_high_pct', 0):.1f}%")
    lines.append(f"  From 52W Low: {detailed.get('price_from_52w_low_pct', 0):.1f}%")
    lines.append("")
    
    # Buy/Sell Prices
    if buy_sell:
        lines.append("ENTRY/EXIT PRICES:")
        if buy_sell.get("pivot_price"):
            lines.append(f"  Pivot Price (Base High): ${buy_sell.get('pivot_price', 0):.2f}")
        lines.append(f"  Buy Price: ${buy_sell.get('buy_price', 0):.2f}")
        stop_pct = buy_sell.get("stop_loss_pct", 5.0)
        lines.append(f"  Tight Stop Loss ({stop_pct:.1f}%): ${buy_sell.get('stop_loss', 0):.2f} ({buy_sell.get('stop_loss_pct', 0):.1f}%)")
        if buy_sell.get("stop_loss_atr") is not None:
            lines.append(f"  Stop Loss (ATR): ${buy_sell.get('stop_loss_atr', 0):.2f}")
        if buy_sell.get("days_since_base_end") is not None:
            lines.append(f"  Days Since Base End: {buy_sell.get('days_since_base_end')}")
        lines.append(f"  Profit Target 1: ${buy_sell.get('profit_target_1', 0):.2f} ({buy_sell.get('profit_target_1_pct', 0):.1f}%)")
        lines.append(f"  Profit Target 2: ${buy_sell.get('profit_target_2', 0):.2f} ({buy_sell.get('profit_target_2_pct', 0):.1f}%)")
        if buy_sell.get("risk_reward_ratio"):
            lines.append(f"  Risk/Reward Ratio: {buy_sell.get('risk_reward_ratio', 0):.2f}")
        lines.append("")
    
    # KEY SUPPORT LEVELS (for stop loss reference)
    lines.append("KEY SUPPORT LEVELS:")
    trend = checklist.get("trend_structure", {})
    base = checklist.get("base_quality", {})
    if trend.get("details"):
        sma_200 = trend["details"].get("sma_200", 0)
        sma_150 = trend["details"].get("sma_150", 0)
        sma_50 = trend["details"].get("sma_50", 0)
        lines.append(f"  SMA 50 (short-term support): ${sma_50:.2f}")
        lines.append(f"  SMA 150 (intermediate support): ${sma_150:.2f}")
        lines.append(f"  SMA 200 (major support): ${sma_200:.2f}")
    if base.get("details"):
        base_low = base["details"].get("base_low", 0)
        base_high = base["details"].get("base_high", 0)
        lines.append(f"  Current Base Low: ${base_low:.2f} (swing trade stop level)")
        lines.append(f"  Current Base High (Pivot): ${base_high:.2f}")
    lines.append(f"  52-Week Low: ${detailed.get('52_week_low', 0):.2f} (disaster stop reference)")
    lines.append("")
    
    # PART 1: Trend & Structure
    trend = checklist.get("trend_structure", {})
    lines.append("PART 1: TREND & STRUCTURE")
    lines.append(f"  Passed: {trend.get('passed', False)}")
    if trend.get("details"):
        d = trend["details"]
        lines.append(f"  Current Price: ${d.get('current_price', 0):.2f}")
        lines.append(f"  SMA 50: ${d.get('sma_50', 0):.2f} | Above: {'✓' if d.get('above_50') else '✗'}")
        lines.append(f"  SMA 150: ${d.get('sma_150', 0):.2f} | Above: {'✓' if d.get('above_150') else '✗'}")
        lines.append(f"  SMA 200: ${d.get('sma_200', 0):.2f} | Above: {'✓' if d.get('above_200') else '✗'}")
        lines.append(f"  SMA Order (50>150>200): {'✓' if d.get('sma_order_correct') else '✗'}")
        lines.append(f"  Price from 52W Low: {d.get('price_from_52w_low_pct', 0):.1f}% (need ≥30%)")
        lines.append(f"  Price from 52W High: {d.get('price_from_52w_high_pct', 0):.1f}% (need ≤15%)")
    if trend.get("failures"):
        lines.append(f"  Failures: {', '.join(trend['failures'])}")
    lines.append("")
    
    # PART 2: Base Quality
    base = checklist.get("base_quality", {})
    lines.append("PART 2: BASE QUALITY")
    lines.append(f"  Passed: {base.get('passed', False)}")
    if base.get("details"):
        d = base["details"]
        lines.append(f"  Base Length: {d.get('base_length_weeks', 0):.1f} weeks (need 3-8 weeks)")
        lines.append(f"  Base Depth: {d.get('base_depth_pct', 0):.1f}% (need ≤25%, ≤15% is elite)")
        lines.append(f"  Base High: ${d.get('base_high', 0):.2f}")
        lines.append(f"  Base Low: ${d.get('base_low', 0):.2f}")
        lines.append(f"  Avg Close Position: {d.get('avg_close_position_pct', 0):.1f}% (need ≥50%)")
        lines.append(f"  Volume Contraction: {d.get('volume_contraction', 0):.2f}x (need <0.95x)")
    if base.get("failures"):
        lines.append(f"  Failures: {', '.join(base['failures'])}")
    lines.append("")
    
    # PART 3: Relative Strength
    rs = checklist.get("relative_strength", {})
    lines.append("PART 3: RELATIVE STRENGTH")
    lines.append(f"  Passed: {rs.get('passed', False)}")
    if rs.get("details"):
        d = rs["details"]
        lines.append(f"  RSI(14): {d.get('rsi_14', 0):.1f} (need >60)")
        lines.append(f"  Relative Strength: {d.get('relative_strength', 0):.4f} (need >0)")
        lines.append(f"  RS Rating: {d.get('rs_rating', 0):.1f}")
        lines.append(f"  Stock Return: {d.get('stock_return', 0):.2%}")
        lines.append(f"  Benchmark Return: {d.get('benchmark_return', 0):.2%}")
        lines.append(f"  Outperforming: {'✓' if d.get('outperforming') else '✗'}")
    if rs.get("failures"):
        lines.append(f"  Failures: {', '.join(rs['failures'])}")
    lines.append("")
    
    # PART 4: Volume Signature
    volume = checklist.get("volume_signature", {})
    lines.append("PART 4: VOLUME SIGNATURE")
    lines.append(f"  Passed: {volume.get('passed', False)}")
    if volume.get("details"):
        d = volume["details"]
        lines.append(f"  Base Avg Volume: {d.get('base_avg_volume', 0):,.0f}")
        lines.append(f"  Pre-Base Volume: {d.get('pre_base_volume', 0):,.0f}")
        lines.append(f"  Volume Contraction: {d.get('volume_contraction', 0):.2f}x (need <0.9x)")
        lines.append(f"  Recent Volume: {d.get('recent_volume', 0):,.0f}")
        lines.append(f"  Avg Volume (20d): {d.get('avg_volume_20d', 0):,.0f}")
        lines.append(f"  Volume Increase: {d.get('volume_increase', 0):.2f}x (need ≥1.4x for breakout)")
        lines.append(f"  In Breakout: {'✓' if d.get('in_breakout') else '✗'}")
    if volume.get("failures"):
        lines.append(f"  Failures: {', '.join(volume['failures'])}")
    lines.append("")
    
    # PART 5: Breakout Rules
    breakout = checklist.get("breakout_rules", {})
    lines.append("PART 5: BREAKOUT RULES")
    lines.append(f"  Passed: {breakout.get('passed', False)}")
    if breakout.get("details"):
        d = breakout["details"]
        lines.append(f"  Pivot Price (Base High): ${d.get('pivot_price', 0):.2f}")
        lines.append(f"  Current Price: ${d.get('current_price', 0):.2f}")
        lines.append(f"  Clears Pivot (≥2% above): {'✓' if d.get('clears_pivot') else '✗'}")
        lines.append(f"  Close Position on Breakout: {d.get('close_position_pct', 0):.1f}% (need ≥70%)")
        lines.append(f"  Volume Ratio: {d.get('volume_ratio', 0):.2f}x (need ≥1.2x)")
        lines.append(f"  In Breakout: {'✓' if d.get('in_breakout') else '✗'}")
        if d.get("last_above_pivot_date") is not None:
            lines.append(f"  Last Close Above Pivot: {d.get('last_above_pivot_date')}")
        if d.get("days_since_breakout") is not None:
            lines.append(f"  Days Since Breakout: {d.get('days_since_breakout')}")
    if breakout.get("failures"):
        lines.append(f"  Failures: {', '.join(breakout['failures'])}")
    lines.append("")
    
    return "\n".join(lines)


def create_chatgpt_prompt(
    stocks_data: List[str],
    pre_breakout_data: Optional[List[str]] = None,
) -> str:
    """
    Create the prompt for ChatGPT analysis.
    stocks_data: formatted A+ and A grade stocks.
    pre_breakout_data: optional list of formatted pre-breakout (setup ready, not yet broken out) stocks.
    """
    has_pre_breakout = bool(pre_breakout_data)
    prompt = """You are an expert stock analyst specializing in Mark Minervini's SEPA (Stock Exchange Price Action) methodology.

Analyze the following stocks that have been graded A+ or A by an automated Minervini scanner.
"""
    if has_pre_breakout:
        prompt += """
You will also receive a separate "PRE-BREAKOUT SETUPS" list: stocks with a valid base and near the pivot that have NOT yet broken out. For these, provide a focused "PRE-BREAKOUT WATCHLIST" section (see below).
"""
    prompt += """
## FIRST: TOP 20 PICKS - DETAILED SUMMARY
Start with a comprehensive "TOP 20 PICKS" section that highlights your top 20 stock recommendations from the A+ / A list, ranked by quality. For each pick, provide:

| Rank | Ticker | Company | Why It's a Top Pick | Entry Price | Stop Loss (Tight) | Stop Loss (Base Low) | Target 1 | Risk/Reward |
|------|--------|---------|---------------------|-------------|-------------------|----------------------|----------|-------------|

For each of your TOP 20 picks, also provide a brief narrative (3-4 sentences) explaining:
- The quality of the current base pattern and its characteristics
- The last strong support level (previous base low or key moving average) that could serve as an alternative stop loss
- Why this stock stands out from the others
- Any upcoming catalysts or concerns to watch

### STOP LOSS STRATEGIES FOR TOP 20:
For each top pick, suggest TWO stop loss levels:
1. **Tight Stop**: 5% below pivot price (for aggressive traders)
2. **Base Low Stop**: At or slightly below the base low (for swing traders who want more room)

Also identify the **Last Strong Base** support level - this is the low of the previous consolidation before the current base, which can serve as a disaster stop.
"""
    if has_pre_breakout:
        prompt += """
## PRE-BREAKOUT WATCHLIST (if pre-breakout setups were provided)
After your TOP 20 PICKS, add a "PRE-BREAKOUT WATCHLIST" section. List the top 20 stocks from the PRE-BREAKOUT SETUPS list that are best positioned to break out soon. For each, give: Ticker, Company, Pivot price, Distance to pivot (%), Why the setup is strong (base depth, volume, RS), and what to watch for (e.g. volume on breakout, close above pivot). These are candidates to watch for a breakout entry; they have not yet cleared the pivot by 2%.

"""
    prompt += """
## THEN: For each stock in the full A+ / A list, provide detailed analysis:

1. **Overall Assessment**: Do you agree with the grade? Why or why not?
2. **A+ vs A Analysis**: 
   - If the stock is graded A (not A+), explain SPECIFICALLY why it is not A+. What criteria are missing or what failures prevent it from being A+?
   - If the stock is graded A+, confirm that all criteria are met and explain why it deserves the A+ grade.
3. **Trend & Structure Analysis**: Is the stock in a proper Stage 2 uptrend?
4. **Base Quality Assessment**: Is the base pattern valid (3-8 weeks, ≤25% depth)?
5. **Relative Strength Evaluation**: Is the stock showing strong relative strength?
6. **Volume Analysis**: Is volume contracting in base and expanding on breakout?
7. **Breakout Validation**: Is the stock breaking out properly?
8. **Risk Assessment**: What are the key risks for this stock?
9. **Recommendation**: Would you take a position? If yes, what size (Full/Half/None)?
10. **Entry/Exit Levels**:
    - Pivot Price (base high)
    - Buy Price (entry zone)
    - Tight Stop Loss (5% below entry)
    - Base Low Stop Loss (below base low)
    - Last Strong Base / Support Level (for disaster stop reference)
    - Profit Target 1 (10% gain)
    - Profit Target 2 (45% gain)

IMPORTANT: For stocks graded A (not A+), you MUST clearly explain what specific criteria failures or issues prevent them from being A+ grade. Reference the detailed checklist data provided for each stock.

Provide your analysis in a clear, structured format for each stock.

STOCKS TO ANALYZE (A+ / A grade):
"""
    prompt += "\n" + "="*80 + "\n"
    prompt += "\n".join(stocks_data)
    prompt += "\n" + "="*80 + "\n"
    if has_pre_breakout:
        prompt += "\n\nPRE-BREAKOUT SETUPS (watchlist - not yet broken out; watch for breakout above pivot):\n"
        prompt += "="*80 + "\n"
        prompt += "\n".join(pre_breakout_data)
        prompt += "\n" + "="*80 + "\n"
    prompt += "\nPlease provide your detailed analysis as described above.\n"
    
    return prompt


def send_to_chatgpt(
    prompt: str,
    api_key: str,
    model: Optional[str] = None,
    timeout: Optional[int] = None,
    max_completion_tokens: Optional[int] = None,
) -> tuple[Optional[str], Optional[dict]]:
    """
    Send prompt to ChatGPT and get response. Retries on rate limit / transient errors with backoff.
    Returns (content, usage_dict). usage_dict has prompt_tokens, completion_tokens, total_tokens if available.
    """
    model = model or OPENAI_CHATGPT_MODEL
    request_timeout = timeout or OPENAI_API_TIMEOUT
    if len(prompt) > 50000:
        request_timeout = max(request_timeout, 300)
    max_tokens = max_completion_tokens if max_completion_tokens is not None else OPENAI_CHATGPT_MAX_COMPLETION_TOKENS
    last_error = None
    for attempt in range(OPENAI_CHATGPT_RETRY_ATTEMPTS):
        try:
            client = OpenAI(api_key=api_key, timeout=request_timeout)
            logger.info(f"Sending request to ChatGPT (model: {model}, attempt {attempt + 1}/{OPENAI_CHATGPT_RETRY_ATTEMPTS})...")
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert stock analyst specializing in Mark Minervini's SEPA methodology. Provide detailed, accurate analysis of stocks based on technical analysis principles."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_completion_tokens=max_tokens,
            )
            usage = None
            if getattr(response, "usage", None) is not None:
                u = response.usage
                usage = {
                    "prompt_tokens": getattr(u, "prompt_tokens", None),
                    "completion_tokens": getattr(u, "completion_tokens", None),
                    "total_tokens": getattr(u, "total_tokens", None),
                }
            return response.choices[0].message.content, usage
        except Exception as e:
            last_error = e
            logger.warning(f"ChatGPT API attempt {attempt + 1} failed: {e}")
            if "rate_limit" in str(e).lower() or "429" in str(e):
                wait = OPENAI_CHATGPT_RETRY_BASE_SECONDS * (attempt + 1)
                if attempt < OPENAI_CHATGPT_RETRY_ATTEMPTS - 1:
                    logger.info(f"Rate limited. Waiting {wait}s before retry...")
                    import time
                    time.sleep(wait)
            elif "insufficient_quota" in str(e).lower():
                logger.error("Insufficient API quota. Please check your OpenAI account.")
                return None, None
            elif attempt < OPENAI_CHATGPT_RETRY_ATTEMPTS - 1:
                wait = OPENAI_CHATGPT_RETRY_BASE_SECONDS * (attempt + 1)
                logger.info(f"Transient error. Waiting {wait}s before retry...")
                import time
                time.sleep(wait)
    logger.error(f"ChatGPT API failed after {OPENAI_CHATGPT_RETRY_ATTEMPTS} attempts: {last_error}")
    return None, None


def load_scan_results_from_file() -> Optional[List[Dict]]:
    """
    Load scan results from the latest saved file (written by 02_generate_full_report.py).
    Returns None if file is missing or invalid.
    """
    if not SCAN_RESULTS_LATEST.exists():
        return None
    try:
        with open(SCAN_RESULTS_LATEST, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) > 0:
            return data
        return None
    except Exception as e:
        logger.warning(f"Could not load scan results from {SCAN_RESULTS_LATEST}: {e}")
        return None


def get_scan_results(benchmark: str = "^GDAXI") -> List[Dict]:
    """
    Get scan results - load from latest report file if available, otherwise run full scan.
    benchmark: used when falling back to full scan (e.g. ^GDAXI, ^GSPC).
    """
    results = load_scan_results_from_file()
    if results is not None:
        logger.info(f"Loaded {len(results)} scan results from {SCAN_RESULTS_LATEST}")
        print(f"[INFO] Loaded {len(results)} results from report (no re-scan).")
        return results

    # Fallback: run full Minervini scan
    cached_data = load_cached_data()
    if not cached_data:
        logger.error("No cached data available. Please run 01_fetch_stock_data.py first.")
        return []

    import importlib.util
    report_module_path = Path("02_generate_full_report.py")
    spec = importlib.util.spec_from_file_location("generate_full_report", report_module_path)
    report_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report_module)

    logger.info(f"Running Minervini scan on all stocks (benchmark={benchmark})...")
    results, _ = report_module.scan_all_stocks_from_cache(cached_data, benchmark=benchmark)
    return results


def main():
    """Main function"""
    import argparse
    parser = argparse.ArgumentParser(description="Send A-grade and pre-breakout stocks to ChatGPT for Minervini SEPA validation")
    parser.add_argument("--model", type=str, default=None, help=f"OpenAI model (default: {OPENAI_CHATGPT_MODEL})")
    parser.add_argument("--max-a-stocks", type=int, default=None, help=f"Max A+ and A stocks in prompt (default: {OPENAI_CHATGPT_MAX_A_GRADE_STOCKS})")
    parser.add_argument("--max-pre-breakout", type=int, default=None, help=f"Max pre-breakout setups in prompt (default: {OPENAI_CHATGPT_MAX_PRE_BREAKOUT_STOCKS})")
    parser.add_argument("--benchmark", type=str, default="^GDAXI", help="Benchmark for RS when re-scanning (default: ^GDAXI)")
    parser.add_argument("--include-full-scan-data", action="store_true", help="Include full ORIGINAL SCAN DATA block in report (default: from config)")
    parser.add_argument("--no-include-full-scan-data", action="store_true", help="Omit full ORIGINAL SCAN DATA block (smaller file)")
    parser.add_argument("--api-key", type=str, default=None, help="OpenAI API key (default: OPENAI_API_KEY env)")
    args = parser.parse_args()

    max_a = args.max_a_stocks if args.max_a_stocks is not None else OPENAI_CHATGPT_MAX_A_GRADE_STOCKS
    max_pre = args.max_pre_breakout if args.max_pre_breakout is not None else OPENAI_CHATGPT_MAX_PRE_BREAKOUT_STOCKS
    include_full_scan = OPENAI_CHATGPT_INCLUDE_FULL_SCAN_DATA
    if args.include_full_scan_data:
        include_full_scan = True
    if args.no_include_full_scan_data:
        include_full_scan = False

    print("="*80)
    print("CHATGPT VALIDATION - MINERVINI SEPA ANALYSIS")
    print("="*80)

    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n[ERROR] OPENAI_API_KEY not found. Set it in .env or use --api-key")
        print("   Get your API key from: https://platform.openai.com/api-keys")
        return

    print("\n[INFO] Loading scan results...")
    all_results = get_scan_results(benchmark=args.benchmark)

    if not all_results:
        print("[ERROR] No scan results available")
        return

    a_plus_stocks = [r for r in all_results if r.get("overall_grade") == "A+" and "error" not in r]
    a_stocks = [r for r in all_results if r.get("overall_grade") == "A" and "error" not in r]
    all_a_stocks_full = a_plus_stocks + a_stocks
    all_a_stocks = all_a_stocks_full[:max_a]
    a_stocks_capped = len(all_a_stocks_full) - len(all_a_stocks)

    if not all_a_stocks:
        print("[ERROR] No A+ or A grade stocks found")
        return

    pre_breakout_stocks_full = get_pre_breakout_stocks(all_results)
    pre_breakout_stocks = pre_breakout_stocks_full[:max_pre]
    pre_breakout_capped = len(pre_breakout_stocks_full) - len(pre_breakout_stocks)

    formatted_pre_breakout = []
    if pre_breakout_stocks:
        for stock in pre_breakout_stocks:
            formatted_pre_breakout.append(format_stock_data_for_chatgpt(stock, is_pre_breakout=True))

    print(f"[OK] Stocks to send to ChatGPT (capped):")
    print(f"   A+ / A: {len(all_a_stocks)} (of {len(all_a_stocks_full)} total)" + (f" — {a_stocks_capped} omitted (limit {max_a})" if a_stocks_capped else ""))
    if pre_breakout_stocks:
        print(f"   Pre-breakout: {len(pre_breakout_stocks)} (of {len(pre_breakout_stocks_full)} total)" + (f" — {pre_breakout_capped} omitted (limit {max_pre})" if pre_breakout_capped else ""))

    print("\n[INFO] Formatting stock data...")
    formatted_stocks = [format_stock_data_for_chatgpt(stock) for stock in all_a_stocks]

    print("[INFO] Creating ChatGPT prompt...")
    prompt = create_chatgpt_prompt(formatted_stocks, formatted_pre_breakout if formatted_pre_breakout else None)

    prompt_length = len(prompt)
    estimated_tokens = prompt_length / 4
    print(f"\n[STATS] Prompt Statistics:")
    print(f"   Prompt length: {prompt_length:,} characters")
    print(f"   Estimated tokens: ~{estimated_tokens:,.0f}")
    print(f"   A+ / A stocks: {len(all_a_stocks)}")
    if pre_breakout_stocks:
        print(f"   Pre-breakout setups: {len(pre_breakout_stocks)}")

    if estimated_tokens > 100000:
        print(f"\n[WARNING] Prompt is very long ({estimated_tokens:,.0f} tokens)")
        print("   Proceeding (use --max-a and --max-prebreakout to reduce size if needed).")

    model = args.model or OPENAI_CHATGPT_MODEL
    print(f"\n[INFO] Sending to ChatGPT (model: {model})...")
    if estimated_tokens > 10000:
        print(f"   (Large request: ~{estimated_tokens:,.0f} tokens - may take several minutes...)")
    analysis, usage = send_to_chatgpt(prompt, api_key, model=model)

    if not analysis:
        print("[ERROR] Failed to get analysis from ChatGPT. Check API key and quota.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = REPORTS_DIR / "summary_Chat_GPT.txt"
    timestamped_file = REPORTS_DIR / f"summary_Chat_GPT_{timestamp}.txt"

    report_lines = []
    report_lines.append("="*100)
    report_lines.append("CHATGPT VALIDATION - MINERVINI SEPA ANALYSIS")
    report_lines.append("="*100)
    report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"Model: {model}")
    if usage and (usage.get("total_tokens") is not None or usage.get("prompt_tokens") is not None):
        pt, ct, tot = usage.get("prompt_tokens"), usage.get("completion_tokens"), usage.get("total_tokens")
        if tot is not None:
            report_lines.append(f"Tokens used: {tot:,} total (prompt: {pt or 0:,}, completion: {ct or 0:,})")
        else:
            report_lines.append(f"Tokens used: prompt {pt or 0:,}, completion {ct or 0:,}")
    scan_date = get_scan_date_from_latest_report()
    if scan_date:
        report_lines.append(f"Scan date (data as of): {scan_date}")
    report_lines.append(f"Total A+ / A Stocks Analyzed: {len(all_a_stocks)}")
    report_lines.append(f"  A+ Grade: {len(a_plus_stocks)}")
    report_lines.append(f"  A Grade: {len(a_stocks)}")
    if pre_breakout_stocks:
        report_lines.append(f"  Pre-breakout setups (watchlist): {len(pre_breakout_stocks)}")
    report_lines.append("")
    report_lines.append("="*100)
    report_lines.append("CHATGPT ANALYSIS")
    report_lines.append("="*100)
    report_lines.append("")
    report_lines.append(analysis)
    report_lines.append("")

    if include_full_scan:
        report_lines.append("="*100)
        report_lines.append("ORIGINAL SCAN DATA (for reference)")
        report_lines.append("="*100)
        report_lines.append("")
        report_lines.append("A+ / A grade stocks:")
        report_lines.append("")
        for stock in all_a_stocks:
            report_lines.append(format_stock_data_for_chatgpt(stock))
            report_lines.append("")
            report_lines.append("-"*100)
            report_lines.append("")
        if pre_breakout_stocks:
            report_lines.append("PRE-BREAKOUT SETUPS (reference):")
            report_lines.append("")
            for stock in pre_breakout_stocks:
                report_lines.append(format_stock_data_for_chatgpt(stock, is_pre_breakout=True))
                report_lines.append("")
                report_lines.append("-"*100)
                report_lines.append("")

    report_content = "\n".join(report_lines)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report_content)
    with open(timestamped_file, 'w', encoding='utf-8') as f:
        f.write(report_content)

    print(f"\n[SUCCESS] Analysis complete!")
    print(f"   Report saved to: {output_file}")
    print(f"   Backup saved to: {timestamped_file}")
    print(f"   File size: {output_file.stat().st_size / 1024:.2f} KB")


if __name__ == "__main__":
    main()
