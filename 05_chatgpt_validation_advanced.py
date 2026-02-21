"""
ChatGPT Validation Advanced
Sends your open positions first, then all A+ and A grade stocks to ChatGPT for
institutional-style technical analysis (Minervini, Weinstein, key levels, scenarios).
Uses structured daily chart/level data (no image). Requires OPENAI_API_KEY.
Run after 02_generate_full_report.py (and optionally 03_position_suggestions.py for positions).
"""
import os
import re
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dotenv import load_dotenv
from openai import OpenAI

from logger_config import get_logger
from config import (
    DEFAULT_ENV_PATH,
    REPORTS_DIR,
    OPENAI_API_TIMEOUT,
    OPENAI_CHATGPT_MODEL,
    OPENAI_CHATGPT_MAX_COMPLETION_TOKENS,
    OPENAI_CHATGPT_RETRY_ATTEMPTS,
    OPENAI_CHATGPT_RETRY_BASE_SECONDS,
)
from ticker_utils import clean_ticker
from currency_utils import get_eur_usd_rate_with_date, warn_if_eur_rate_unavailable

logger = get_logger(__name__)

env_file = Path(DEFAULT_ENV_PATH)
if env_file.exists():
    load_dotenv(env_file)

REPORTS_DIR.mkdir(exist_ok=True)

# Scan results (same as 03)
SCAN_RESULTS_LATEST = REPORTS_DIR / "scan_results_latest.json"

# Prompt template (user-provided); [INSERT PRICE] and [INSERT NAME] are replaced per stock
ADVANCED_PROMPT_TEMPLATE = """Act as a professional institutional technical analyst using Mark Minervini, Stan Weinstein, and classical price/volume analysis.

I am providing structured data derived from Yahoo Finance (no images, no raw OHLC paste). The data below includes: current close, 52-week high/low, 50/150/200 MA values, base high/low (pivot), volume metrics, relative strength, breakout rules, and buy/sell levels. Use this as your chart proxy.

Analyze the data and provide:

1. Trend Analysis
- Short term, medium term, long term trend
- Moving average analysis (50, 150, 200 MA)
- Trend stage (Weinstein Stage 1–4)

2. Key Levels
- Exact resistance levels
- Exact support levels
- Exact breakout pivot price (Minervini pivot)
- Exact strong buy level
- Exact strong sell level

3. Position Analysis
- Evaluate my entry quality (score 1–10)
- Risk/reward assessment
- Whether I should hold, sell, or add
- Proper stop loss level based on structure

4. Breakout Analysis
- Whether breakout is confirmed or not
- Volume confirmation assessment
- Probability of breakout success (percentage)

5. Scenario Forecast
Provide 3 scenarios:
- Bullish scenario with price targets
- Neutral scenario
- Bearish scenario with downside targets

6. Institutional Quality Rating
- Rate setup quality from 1–10
- Whether stock qualifies as Minervini Stage 2 breakout candidate

7. Exact Action Plan
Provide clear levels:
- Hold above:
- Sell below:
- Add above:
- Strong buy above:

Use precise price levels, probabilities, and professional reasoning.
Avoid generic advice.

My entry price is: {entry_price}

Chart timeframe: Daily
Stock name: {stock_name}

---
STRUCTURED DAILY CHART DATA (levels and metrics):
---
{chart_data}
"""


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def format_chart_data_for_advanced(stock_result: Dict, eur_to_usd_rate: Optional[float] = None) -> str:
    """Build chart/level data string from scan result for the advanced prompt.
    Includes: price, trend (DMAs + pass/fail), base, relative strength, volume, breakout rules, buy/sell levels.
    When eur_to_usd_rate is set (e.g. for EUR positions), all prices are converted to USD so they match the
    entry price we send (which is also in USD for EUR positions). Yahoo RWE.DE etc. return prices in EUR.
    """
    detailed = stock_result.get("detailed_analysis", {})
    checklist = stock_result.get("checklist", {})
    buy_sell = stock_result.get("buy_sell_prices", {})
    stock_info = stock_result.get("stock_info", {})

    def _p(val: float) -> float:
        """Convert price to USD when rate given (chart data from Yahoo EUR listing)."""
        if eur_to_usd_rate and eur_to_usd_rate > 0 and val is not None:
            return val * eur_to_usd_rate
        return val

    lines = []
    lines.append(f"Ticker: {stock_result.get('ticker', 'N/A')}")
    lines.append(f"Company: {stock_info.get('company_name', 'N/A')}")
    lines.append(f"Grade: {stock_result.get('overall_grade', 'N/A')}")
    if eur_to_usd_rate:
        lines.append("(All prices below converted to USD for consistency with entry price.)")
    lines.append("")

    # Price
    cur = _safe_float(detailed.get("current_price"))
    high52 = _safe_float(detailed.get("52_week_high"))
    low52 = _safe_float(detailed.get("52_week_low"))
    lines.append("PRICE:")
    lines.append(f"  Current: ${_p(cur):.2f} | 52W High: ${_p(high52):.2f} | 52W Low: ${_p(low52):.2f}")
    lines.append(f"  From 52W High: {_safe_float(detailed.get('price_from_52w_high_pct')):.1f}% | From 52W Low: {_safe_float(detailed.get('price_from_52w_low_pct')):.1f}%")
    lines.append("")

    # Trend (DMAs) + pass/fail
    trend = checklist.get("trend_structure", {})
    trend_d = trend.get("details") or {}
    if trend_d:
        lines.append("TREND / MOVING AVERAGES:")
        lines.append(f"  Passed: {trend.get('passed', False)}")
        lines.append(f"  SMA 50: ${_p(_safe_float(trend_d.get('sma_50'))):.2f} (above: {trend_d.get('above_50', False)})")
        lines.append(f"  SMA 150: ${_p(_safe_float(trend_d.get('sma_150'))):.2f} (above: {trend_d.get('above_150', False)})")
        lines.append(f"  SMA 200: ${_p(_safe_float(trend_d.get('sma_200'))):.2f} (above: {trend_d.get('above_200', False)})")
        lines.append(f"  SMA order correct (50>150>200): {trend_d.get('sma_order_correct', False)}")
        lines.append(f"  Price from 52W low: {_safe_float(trend_d.get('price_from_52w_low_pct')):.1f}% (need ≥30%) | from 52W high: {_safe_float(trend_d.get('price_from_52w_high_pct')):.1f}% (need ≤15%)")
        if trend.get("failures"):
            lines.append(f"  Failures: {', '.join(trend['failures'])}")
        lines.append("")

    # Base / pivot + pass/fail
    base = checklist.get("base_quality", {})
    base_d = base.get("details") or {}
    if base_d:
        lines.append("BASE / PIVOT:")
        lines.append(f"  Passed: {base.get('passed', False)}")
        lines.append(f"  Base high (pivot): ${_p(_safe_float(base_d.get('base_high'))):.2f}")
        lines.append(f"  Base low: ${_p(_safe_float(base_d.get('base_low'))):.2f}")
        lines.append(f"  Base depth: {_safe_float(base_d.get('base_depth_pct')):.1f}% | Length: {_safe_float(base_d.get('base_length_weeks')):.1f} weeks")
        lines.append(f"  Avg close position: {_safe_float(base_d.get('avg_close_position_pct')):.1f}% (need ≥50%) | Volume contraction: {_safe_float(base_d.get('volume_contraction')):.2f}x (need <0.95x)")
        if base.get("failures"):
            lines.append(f"  Failures: {', '.join(base['failures'])}")
        lines.append("")

    # Relative Strength (was missing)
    rs = checklist.get("relative_strength", {})
    rs_d = rs.get("details") or {}
    if rs_d:
        lines.append("RELATIVE STRENGTH:")
        lines.append(f"  Passed: {rs.get('passed', False)}")
        lines.append(f"  RSI(14): {_safe_float(rs_d.get('rsi_14')):.1f} (need >60)")
        lines.append(f"  RS Rating: {_safe_float(rs_d.get('rs_rating')):.1f}")
        lines.append(f"  Relative strength: {_safe_float(rs_d.get('relative_strength')):.4f} | Outperforming: {rs_d.get('outperforming', False)}")
        lines.append(f"  Stock return: {_safe_float(rs_d.get('stock_return')):.2%} | Benchmark return: {_safe_float(rs_d.get('benchmark_return')):.2%}")
        if rs.get("failures"):
            lines.append(f"  Failures: {', '.join(rs['failures'])}")
        lines.append("")

    # Volume (full details)
    vol = checklist.get("volume_signature", {})
    vol_d = vol.get("details") or {}
    if vol_d:
        lines.append("VOLUME:")
        lines.append(f"  Passed: {vol.get('passed', False)}")
        lines.append(f"  Volume contraction: {_safe_float(vol_d.get('volume_contraction')):.2f}x (need <0.9x)")
        lines.append(f"  Recent volume: {_safe_float(vol_d.get('recent_volume')):,.0f} | Avg 20d: {_safe_float(vol_d.get('avg_volume_20d')):,.0f}")
        lines.append(f"  Volume increase (recent vs avg): {_safe_float(vol_d.get('volume_increase')):.2f}x (need ≥1.4x for breakout)")
        lines.append(f"  In breakout: {vol_d.get('in_breakout', False)}")
        if vol.get("failures"):
            lines.append(f"  Failures: {', '.join(vol['failures'])}")
        lines.append("")

    # Breakout rules (was missing)
    br = checklist.get("breakout_rules", {})
    br_d = br.get("details") or {}
    if br_d:
        lines.append("BREAKOUT RULES:")
        lines.append(f"  Passed: {br.get('passed', False)}")
        lines.append(f"  Pivot: ${_p(_safe_float(br_d.get('pivot_price'))):.2f} | Current: ${_p(_safe_float(br_d.get('current_price'))):.2f}")
        lines.append(f"  Clears pivot (≥2% above): {br_d.get('clears_pivot', False)}")
        lines.append(f"  Volume ratio: {_safe_float(br_d.get('volume_ratio')):.2f}x (need ≥1.2x)")
        lines.append(f"  Close position on breakout day: {_safe_float(br_d.get('close_position_pct')):.1f}% (need ≥70%)")
        lines.append(f"  In breakout: {br_d.get('in_breakout', False)}")
        if br_d.get("days_since_breakout") is not None:
            lines.append(f"  Days since breakout: {br_d.get('days_since_breakout')}")
        if br_d.get("last_above_pivot_date"):
            lines.append(f"  Last close above pivot: {br_d.get('last_above_pivot_date')}")
        if br.get("failures"):
            lines.append(f"  Failures: {', '.join(br['failures'])}")
        lines.append("")

    if buy_sell:
        lines.append("BUY/SELL LEVELS:")
        lines.append(f"  Pivot: ${_p(_safe_float(buy_sell.get('pivot_price'))):.2f} | Buy: ${_p(_safe_float(buy_sell.get('buy_price'))):.2f}")
        lines.append(f"  Stop loss: ${_p(_safe_float(buy_sell.get('stop_loss'))):.2f} ({_safe_float(buy_sell.get('stop_loss_pct')):.1f}%)")
        lines.append(f"  Target 1: ${_p(_safe_float(buy_sell.get('profit_target_1'))):.2f} | Target 2: ${_p(_safe_float(buy_sell.get('profit_target_2'))):.2f}")
        lines.append(f"  Distance to buy: {_safe_float(buy_sell.get('distance_to_buy_pct')):.1f}%")
        if buy_sell.get("days_since_base_end") is not None:
            lines.append(f"  Days since base end: {buy_sell.get('days_since_base_end')}")
        lines.append("")

    return "\n".join(lines).strip()


def load_positions_from_api() -> List[Dict]:
    """Load open positions from Trading212 API. Returns list of {ticker, entry, current, name?}."""
    api_key = os.getenv("TRADING212_API_KEY")
    api_secret = os.getenv("TRADING212_API_SECRET")
    if not api_key or not api_secret:
        return []
    try:
        from trading212_client import Trading212Client
        client = Trading212Client(api_key, api_secret)
        positions = client.get_positions()
    except Exception as e:
        logger.warning("Could not fetch positions from API: %s", e)
        return []
    if not positions:
        return []
    out = []
    for pos in positions:
        ticker = pos.get("ticker") or (pos.get("instrument") or {}).get("ticker") or (pos.get("instrument") or {}).get("symbol") or ""
        if not ticker:
            continue
        qty = float(pos.get("quantity") or 0)
        if qty <= 0:
            continue
        entry = float(pos.get("averagePricePaid") or pos.get("averagePrice") or 0)
        current = float(pos.get("currentPrice") or pos.get("current_price") or 0)
        name = (pos.get("instrument") or {}).get("name") or ""
        currency = (pos.get("instrument") or {}).get("currency") or (pos.get("walletImpact") or {}).get("currency") or ""
        out.append({"ticker_raw": ticker, "ticker": clean_ticker(ticker) or ticker.upper(), "entry": entry, "current": current, "name": name, "currency": currency})
    return out


def load_positions_from_report() -> List[Dict]:
    """Parse latest position_suggestions_*.txt for ticker and entry (no API)."""
    candidates = [p for p in REPORTS_DIR.glob("position_suggestions_*.txt") if "Chat_GPT" not in p.name]
    if not candidates:
        return []
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    text = latest.read_text(encoding="utf-8")
    out = []
    for block in re.split(r"\n-{2,}\n", text):
        ticker = None
        entry = None
        current = None
        currency = ""
        for line in block.splitlines():
            s = line.strip()
            if s.startswith("Currency:"):
                currency = s.replace("Currency:", "").strip()
            elif s.startswith("Entry:") and "Current:" in s:
                # "  Entry: 78.65  Current: 74.89  PnL: -4.8%"
                m = re.search(r"Entry:\s*([\d.]+)\s+Current:\s*([\d.]+)", s)
                if m:
                    entry = float(m.group(1))
                    current = float(m.group(2))
                break
            elif re.match(r"^[A-Z0-9._]{1,12}$", s) and len(s) >= 2 and s not in ("Grade", "Suggestion", "Reason", "Entry", "Rules", "Positions", "Generated"):
                ticker = clean_ticker(s) or s.upper()
        if ticker and entry is not None:
            out.append({"ticker_raw": ticker, "ticker": ticker, "entry": entry, "current": current or entry, "name": ticker, "currency": currency})
    return out


def load_scan_results() -> List[Dict]:
    """Load scan results from scan_results_latest.json."""
    if not SCAN_RESULTS_LATEST.exists():
        return []
    try:
        with open(SCAN_RESULTS_LATEST, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception as e:
        logger.warning("Could not load scan results: %s", e)
    return []


def match_scan_to_ticker(ticker: str, scan_results: List[Dict]) -> Optional[Dict]:
    """Find scan result for a ticker (exact or base symbol match).
    Matches RWED->RWE, PFED->PFE (T212 position tickers with trailing D to scan symbol).
    """
    ticker_upper = (ticker or "").strip().upper()
    cleaned = clean_ticker(ticker_upper) or ticker_upper
    for r in scan_results:
        t = (r.get("ticker") or "").strip().upper()
        if not t:
            continue
        if t == ticker_upper or t == cleaned:
            return r
        if "_" in t and t.split("_")[0] == ticker_upper:
            return r
        if "_" in ticker_upper and t == ticker_upper.split("_")[0]:
            return r
        # T212 often uses trailing D for some listings (e.g. RWED, PFED) -> scan has RWE, PFE
        if ticker_upper.endswith("D") and ticker_upper[:-1] == t:
            return r
        if t.endswith("D") and t[:-1] == ticker_upper:
            return r
    return None


def send_to_chatgpt(prompt: str, api_key: str, model: str, max_tokens: int) -> Tuple[Optional[str], Optional[Dict]]:
    """Call OpenAI; returns (content, usage_dict)."""
    last_error = None
    for attempt in range(OPENAI_CHATGPT_RETRY_ATTEMPTS):
        try:
            client = OpenAI(api_key=api_key, timeout=max(OPENAI_API_TIMEOUT, 120))
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional institutional technical analyst. Provide precise price levels, probabilities, and clear action plans. Use the structured data provided as your chart proxy."
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_completion_tokens=max_tokens,
            )
            usage = None
            if getattr(response, "usage", None):
                u = response.usage
                usage = {
                    "prompt_tokens": getattr(u, "prompt_tokens", None),
                    "completion_tokens": getattr(u, "completion_tokens", None),
                    "total_tokens": getattr(u, "total_tokens", None),
                }
            return response.choices[0].message.content, usage
        except Exception as e:
            last_error = e
            logger.warning("ChatGPT attempt %s failed: %s", attempt + 1, e)
            if attempt < OPENAI_CHATGPT_RETRY_ATTEMPTS - 1:
                import time
                time.sleep(OPENAI_CHATGPT_RETRY_BASE_SECONDS * (attempt + 1))
    return None, None


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="ChatGPT Validation Advanced: positions first, then A+/A stocks with institutional analysis")
    parser.add_argument("--model", type=str, default=None, help=f"OpenAI model (default: {OPENAI_CHATGPT_MODEL})")
    parser.add_argument("--limit", type=int, default=20, help="Max number of stocks to analyze (positions + A+/A). Default 20.")
    parser.add_argument("--api-key", type=str, default=None, help="OpenAI API key (default: OPENAI_API_KEY env)")
    parser.add_argument("--positions-only", action="store_true", help="Analyze only your open positions")
    parser.add_argument("--no-positions", action="store_true", help="Skip positions; analyze only A+/A stocks")
    args = parser.parse_args()

    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n[ERROR] OPENAI_API_KEY not set. Set it in .env or use --api-key")
        return

    model = args.model or OPENAI_CHATGPT_MODEL
    limit = max(1, args.limit)

    print("=" * 80)
    print("CHATGPT VALIDATION ADVANCED")
    print("=" * 80)

    # Load positions
    positions = load_positions_from_api()
    if not positions:
        positions = load_positions_from_report()
    if not args.no_positions and positions:
        print(f"[INFO] Loaded {len(positions)} position(s)")
    elif args.no_positions:
        positions = []
    else:
        print("[INFO] No positions loaded (API not configured or no position report)")

    # Load scan results
    scan_results = load_scan_results()
    if not scan_results:
        print("[ERROR] No scan results. Run 02_generate_full_report.py first.")
        return

    a_plus = [r for r in scan_results if r.get("overall_grade") == "A+" and "error" not in str(r)]
    a_grade = [r for r in scan_results if r.get("overall_grade") == "A" and "error" not in str(r)]
    # Order A+ then A; within grade by e.g. meets_criteria then by pivot distance
    def sort_key(r):
        grade = 0 if r.get("overall_grade") == "A+" else 1
        meets = 0 if r.get("meets_criteria") else 1
        dist = abs(_safe_float((r.get("buy_sell_prices") or {}).get("distance_to_buy_pct"), 999))
        return (grade, meets, dist)
    a_plus_sorted = sorted(a_plus, key=sort_key)
    a_grade_sorted = sorted(a_grade, key=sort_key)
    other_a = a_plus_sorted + a_grade_sorted

    # EUR/USD rate and date for converting ChatGPT (USD) output to EUR for EUR positions
    has_eur = any(p.get("currency") == "EUR" for p in positions)
    eur_usd_rate, eur_usd_rate_date = get_eur_usd_rate_with_date() if has_eur else (None, None)
    warn_if_eur_rate_unavailable(has_eur, eur_usd_rate)

    # Build list: (label, entry_price, stock_name, chart_data, ticker, scan, position_eur_info?)
    items = []
    seen_tickers = set()

    for pos in positions:
        if len(items) >= limit:
            break
        ticker = pos["ticker"]
        if ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)
        entry = _safe_float(pos.get("entry"))
        current = _safe_float(pos.get("current")) or entry
        currency = pos.get("currency") or ""
        scan = match_scan_to_ticker(ticker, scan_results)
        if scan:
            # For EUR positions we send entry in USD. Only convert chart prices when scan is in EUR;
            # if scan came from cache (01 converted EUR->USD), stock_info.currency is "USD" — do not double-convert.
            scan_currency = (scan.get("stock_info") or {}).get("currency") or ""
            rate = eur_usd_rate if (currency == "EUR" and eur_usd_rate and eur_usd_rate > 0 and scan_currency == "EUR") else None
            chart_data = format_chart_data_for_advanced(scan, eur_to_usd_rate=rate)
            name = (scan.get("stock_info") or {}).get("company_name") or pos.get("name") or ticker
        else:
            chart_data = f"Ticker: {ticker}\nNo scan data for this ticker. Use entry and general market context."
            name = pos.get("name") or ticker
        if currency == "EUR" and eur_usd_rate and eur_usd_rate > 0:
            entry_for_prompt = entry * eur_usd_rate  # EUR -> USD for ChatGPT
            position_eur_info = {"currency": "EUR", "entry_eur": entry, "current_eur": current}
        else:
            entry_for_prompt = entry
            position_eur_info = None
        items.append(("POSITION", entry_for_prompt, name, chart_data, ticker, scan, position_eur_info))

    if not args.positions_only:
        for scan in other_a:
            if len(items) >= limit:
                break
            ticker = (scan.get("ticker") or "").strip().upper()
            if not ticker or ticker in seen_tickers:
                continue
            seen_tickers.add(ticker)
            name = (scan.get("stock_info") or {}).get("company_name") or ticker
            ref_price = _safe_float((scan.get("buy_sell_prices") or {}).get("buy_price")) or _safe_float((scan.get("detailed_analysis") or {}).get("current_price"))
            chart_data = format_chart_data_for_advanced(scan)
            items.append(("A+/A", ref_price, name, chart_data, ticker, scan, None))

    if not items:
        print("[ERROR] No positions and no A+/A stocks to analyze.")
        return

    print(f"[INFO] Analyzing {len(items)} item(s) (limit={limit})")
    print(f"[INFO] Model: {model}")
    print()

    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("CHATGPT VALIDATION ADVANCED")
    report_lines.append("=" * 80)
    report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"Model: {model}")
    if eur_usd_rate is not None:
        report_lines.append(f"EUR/USD rate (Yahoo): {eur_usd_rate:.4f} (used to convert USD to EUR for EUR positions)" + (f"  Rate date: {eur_usd_rate_date}" if eur_usd_rate_date else ""))
    report_lines.append("")
    total_tokens = 0

    last_section = None
    for i, item in enumerate(items, 1):
        label, entry_price, stock_name, chart_data, ticker, scan, position_eur_info = (
            item[0], item[1], item[2], item[3], item[4], item[5], item[6] if len(item) > 6 else None
        )
        section = "MY POSITIONS" if label == "POSITION" else "A+ / A STOCKS (by quality)"
        if section != last_section:
            last_section = section
            report_lines.append("")
            report_lines.append("=" * 80)
            report_lines.append(section)
            report_lines.append("=" * 80)
            report_lines.append("")

        prompt_text = ADVANCED_PROMPT_TEMPLATE.format(
            entry_price=entry_price,
            stock_name=stock_name,
            chart_data=chart_data,
        )
        print(f"[{i}/{len(items)}] {ticker} ({stock_name[:40]}...) ... ", end="", flush=True)
        content, usage = send_to_chatgpt(prompt_text, api_key, model, min(OPENAI_CHATGPT_MAX_COMPLETION_TOKENS, 8000))
        if usage and usage.get("total_tokens"):
            total_tokens += usage["total_tokens"]
        if not content:
            print("FAILED")
            report_lines.append(f"### {ticker} ({stock_name})")
            report_lines.append("[ERROR] No response from ChatGPT.")
            report_lines.append("")
            continue
        print("OK")
        report_lines.append(f"### {ticker} ({stock_name})")
        if usage and (usage.get("total_tokens") or usage.get("prompt_tokens") is not None):
            pt, ct, tot = usage.get("prompt_tokens"), usage.get("completion_tokens"), usage.get("total_tokens")
            if tot is not None:
                report_lines.append(f"Tokens used: {tot:,} total (prompt: {pt or 0:,}, completion: {ct or 0:,})")
            else:
                report_lines.append(f"Tokens used: prompt {pt or 0:,}, completion {ct or 0:,}")
        report_lines.append("")
        report_lines.append(content.strip())
        # For EUR positions: append conversion note (ChatGPT analysis is in USD)
        if position_eur_info and eur_usd_rate and eur_usd_rate > 0:
            e = position_eur_info.get("entry_eur")
            c = position_eur_info.get("current_eur")
            report_lines.append("")
            report_lines.append("--- Converted to EUR (1 EUR = {:.4f} USD) ---".format(eur_usd_rate))
            if e is not None:
                report_lines.append("Entry: {:.2f} EUR".format(e))
            if c is not None:
                report_lines.append("Current: {:.2f} EUR".format(c))
            report_lines.append("(Analysis above uses USD; key levels in EUR above.)")
        report_lines.append("")
        report_lines.append("-" * 80)
        report_lines.append("")

    if total_tokens:
        report_lines.insert(5, f"Tokens used (total this run): {total_tokens:,}")
        report_lines.insert(6, "")

    out_file = REPORTS_DIR / "summary_Chat_GPT_advanced.txt"
    ts_file = REPORTS_DIR / f"summary_Chat_GPT_advanced_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    body = "\n".join(report_lines)
    for path in (out_file, ts_file):
        try:
            path.write_text(body, encoding="utf-8")
            print(f"Report saved: {path}")
        except Exception as e:
            logger.warning("Could not save %s: %s", path, e)

    print("\n[OK] Done.")


if __name__ == "__main__":
    main()
