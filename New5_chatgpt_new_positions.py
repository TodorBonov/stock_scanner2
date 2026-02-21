"""
New pipeline (5/5): ChatGPT analysis for new position candidates (A+/A from prepared data).
Reads prepared_new_positions.json, sends raw OHLCV to ChatGPT, writes report.
"""
import os
import json
import time
import argparse
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple, List

from dotenv import load_dotenv
from openai import OpenAI
from logger_config import setup_logging, get_logger
from config import (
    DEFAULT_ENV_PATH,
    OPENAI_API_TIMEOUT,
    OPENAI_CHATGPT_MODEL,
    OPENAI_CHATGPT_MAX_COMPLETION_TOKENS,
    OPENAI_CHATGPT_RETRY_ATTEMPTS,
    OPENAI_CHATGPT_RETRY_BASE_SECONDS,
)

NEW_PIPELINE_REPORTS = Path("reports") / "new_pipeline"
PREPARED_NEW = NEW_PIPELINE_REPORTS / "prepared_new_positions.json"


def _parse_ticker_order_from_response(text: str, valid_tickers: set) -> List[str]:
    """Extract tickers from ChatGPT response in order. Expects one ticker per line or numbered list."""
    ordered: List[str] = []
    seen: set = set()
    for line in text.strip().splitlines():
        line = line.strip()
        line = re.sub(r"^\s*\d+[.)]\s*", "", line)
        line = re.sub(r"^\s*[-*]\s*", "", line)
        for part in line.replace(",", " ").split():
            t = part.upper().strip(".:)")
            if 1 <= len(t) <= 12 and t not in seen and t in valid_tickers:
                ordered.append(t)
                seen.add(t)
    return ordered


def _reorder_stocks_by_chatgpt(stocks: List[Dict], ordered_tickers: List[str]) -> List[Dict]:
    """Reorder stocks to match ordered_tickers; any not in list stay at end in original order."""
    by_ticker: Dict[str, Dict] = {}
    for s in stocks:
        t = str(s.get("ticker", "")).strip().upper()
        by_ticker[t] = s
        if t.endswith("D") and len(t) > 1:
            by_ticker[t[:-1]] = s
    result = []
    seen_ids = set(id(s) for s in stocks)
    for t in ordered_tickers:
        t = t.upper().strip()
        s = by_ticker.get(t)
        if s and id(s) in seen_ids:
            result.append(s)
            seen_ids.discard(id(s))
    for s in stocks:
        if id(s) in seen_ids:
            result.append(s)
    return result


ORDER_PROMPT_STOCKS = """You are a technical analyst. Below are candidate stocks for new positions (ticker, grade, meets Minervini criteria, distance to buy %).

Rank them in the order you recommend for considering new entries: best opportunity first. One ticker per line, first line = best. Reply with nothing else than the list of tickers, one per line.

STOCKS:
{stocks_list}
"""


PROMPT_TEMPLATE = """Act as a professional institutional technical analyst using Mark Minervini, Stan Weinstein, and quantitative price/volume analysis.

Use quantitative analysis on the OHLCV data to compute moving averages, trend structure, and breakout probabilities.

TIMEFRAME: swing
RISK PROFILE: moderate

I will provide raw daily OHLCV data from Yahoo Finance. This stock is a candidate for a new position (I do not hold it yet).

Analyze the stock and provide a complete institutional-grade evaluation for potential buy: setup quality, entry levels, and risk/reward.

STOCK INFO:
Ticker: {ticker}
Current price (reference): {current_price}
Position size: N/A (candidate for new position)
Grade from scanner: {grade}

DATA:
{ohlcv_csv}

ANALYSIS REQUIREMENTS:

1. Trend Analysis
- Calculate and analyze 50, 150, and 200 day moving averages
- Identify Weinstein stage (Stage 1–4)
- Determine short, medium, and long-term trend direction
- Assess whether the trend supports a new long entry

2. Key Levels
- Identify exact support levels
- Identify exact resistance levels
- Identify Minervini pivot point (breakout level)
- Identify breakout level and failure level (below = no buy / exit if held later)

3. Entry Evaluation (focus: new position candidate)
- Score setup quality for a new buy (1–10)
- Rate current location: ideal entry zone, extended (wait for pullback), or not yet (wait for breakout)
- Calculate proper stop loss level (if I buy)
- Calculate optimal buy / add levels (first entry and add-on zones)
- Recommend: STRONG BUY, BUY ON PULLBACK, WAIT FOR BREAKOUT, or WATCH / PASS with brief rationale

4. Volume Analysis
- Detect accumulation or distribution
- Identify institutional activity
- Confirm breakout quality (if at or near breakout)

5. Probability Assessment (for a new entry)
- Probability of breakout success (%)
- Probability of breakdown (%)
- Expected upside targets from suggested entry
- Expected downside to stop

6. Scenario Forecast (for potential new position)
- Bullish scenario with price targets and suggested entry
- Neutral scenario (wait or conditional buy)
- Bearish scenario (avoid or wait for structure repair)

7. Institutional Rating
- Rate overall setup quality (1–10)
- Confirm if stock qualifies as Stage 2 breakout candidate for a new position

8. Exact Action Plan (for potential new buy)
Provide precise levels:
- Strong buy above (breakout):
- Buy on pullback to (support/add zone):
- Do not buy below (failure level):
- Stop loss if bought (sell below):

Use precise numeric levels derived from the OHLCV data.
Avoid generic advice. Prioritize price structure, moving averages, and volume behavior for evaluating a new position candidate.
"""

setup_logging(log_level="INFO", log_to_file=True)
logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(description="New5: ChatGPT new position suggestions (new pipeline)")
    parser.add_argument("--model", default=None, help=f"OpenAI model (default: {OPENAI_CHATGPT_MODEL})")
    parser.add_argument("--api-key", default=None, help="OpenAI API key (default: OPENAI_API_KEY env)")
    parser.add_argument("--use-6mo", dest="use_6mo", action="store_true", help="Use 6-month OHLCV prepared data (prepared_new_positions_6mo.json)")
    parser.add_argument("--limit", type=int, default=50, help="Max A+/A stocks to analyze (default 50)")
    args = parser.parse_args()

    api_key = require_openai_api_key(args.api_key)
    prepared_path = _prepared_path(args.use_6mo)
    if not prepared_path.exists():
        print(f"[ERROR] Prepared data not found: {prepared_path}. Run New3 (with --use-6mo if needed) first.")
        return

    with open(prepared_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    stocks = data.get("stocks", [])[: args.limit]

    if not stocks:
        print("No A+/A stocks in prepared data (run New1 and New3; ensure scan produces A+ or A).")
        return

    model = args.model or OPENAI_CHATGPT_MODEL
    max_tokens = min(OPENAI_CHATGPT_MAX_COMPLETION_TOKENS, 8000)

    # Ask ChatGPT for recommended order (best opportunity first)
    valid_tickers = set()
    for s in stocks:
        t = str(s.get("ticker", "")).strip().upper()
        valid_tickers.add(t)
        if t.endswith("D") and len(t) > 1:
            valid_tickers.add(t[:-1])
    stocks_list = "\n".join(
        f"  {s.get('ticker', '?')}  grade={s.get('grade')}  meets_criteria={s.get('meets_criteria')}  distance_to_buy_pct={s.get('distance_to_buy_pct')}"
        for s in stocks
    )
    order_prompt = ORDER_PROMPT_STOCKS.format(stocks_list=stocks_list)
    print("Asking ChatGPT for recommended order (best first)...")
    order_resp, _ = openai_send(order_prompt, api_key, model=model, max_tokens=500)
    if order_resp:
        ordered_tickers = _parse_ticker_order_from_response(order_resp, valid_tickers)
        if ordered_tickers:
            stocks = _reorder_stocks_by_chatgpt(stocks, ordered_tickers)
            print(f"Using ChatGPT order: {' → '.join(ordered_tickers[:15])}{' ...' if len(ordered_tickers) > 15 else ''}")
        else:
            print("Could not parse order from ChatGPT; using original order.")
    else:
        print("ChatGPT order request failed; using original order.")

    print(f"\n{'='*80}")
    print("NEW5: CHATGPT NEW POSITION SUGGESTIONS (A+/A)")
    print(f"{'='*80}")
    print(f"Stocks: {len(stocks)}  Model: {model}")
    print(f"{'='*80}\n")

    report_lines = ["=" * 80, "NEW5: CHATGPT NEW POSITION SUGGESTIONS (A+/A)", "=" * 80, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", f"Model: {model}", "Order: ChatGPT recommended (best opportunity first)", ""]

    # Ranking section: same order as ChatGPT (best first)
    report_lines.append("RANKING (BEST TO WORST)")
    report_lines.append("-" * 80)
    for rank, s in enumerate(stocks, 1):
        ticker = s.get("ticker", "?")
        grade = s.get("grade", "?")
        name = (s.get("name") or ticker)[:50]
        report_lines.append(f"  {rank}. {ticker} ({grade}) — {name}")
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("DETAILED ANALYSIS")
    report_lines.append("=" * 80)
    report_lines.append("")

    total_tokens = 0

    for i, s in enumerate(stocks, 1):
        ticker = s.get("ticker", "?")
        grade = s.get("grade", "?")
        current = s.get("current_price")
        current_str = f"{current:.2f}" if current is not None else "from data"
        name = s.get("name", ticker)
        ohlcv = s.get("ohlcv_csv", "")
        prompt_text = PROMPT_TEMPLATE.format(
            ticker=ticker,
            current_price=current_str,
            grade=grade,
            ohlcv_csv=ohlcv,
        )
        print(f"[{i}/{len(stocks)}] {ticker} ({grade}) ... ", end="", flush=True)
        content, usage = openai_send(prompt_text, api_key, model=model, max_tokens=max_tokens)
        if usage and usage.get("total_tokens"):
            total_tokens += usage["total_tokens"]
        if not content:
            print("FAILED")
            report_lines.append(f"### {ticker} ({name}) [{grade}]")
            report_lines.append("(ChatGPT request failed.)")
            report_lines.append("")
            continue
        print("OK")
        report_lines.append(f"### {ticker} ({name}) [{grade}]")
        report_lines.append("")
        report_lines.append(content.strip())
        report_lines.append("")
        report_lines.append("-" * 80)
        report_lines.append("")

    if total_tokens:
        report_lines.insert(5, f"Tokens used: {total_tokens:,}")
        report_lines.insert(6, "")

    NEW_PIPELINE_REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = NEW_PIPELINE_REPORTS / f"chatgpt_new_positions_{ts}.txt"
    out_file.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Report saved: {out_file}\n")


if __name__ == "__main__":
    main()
