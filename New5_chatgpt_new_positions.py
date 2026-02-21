"""
New pipeline (5/5): ChatGPT analysis for new position candidates (A+/A from prepared data).
Reads prepared_new_positions.json, sends raw OHLCV to ChatGPT, writes report.
"""
import os
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple

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

if Path(DEFAULT_ENV_PATH).exists():
    load_dotenv(Path(DEFAULT_ENV_PATH))


def send_to_chatgpt(prompt: str, api_key: str, model: str, max_tokens: int) -> Tuple[Optional[str], Optional[Dict]]:
    last_error = None
    for attempt in range(OPENAI_CHATGPT_RETRY_ATTEMPTS):
        try:
            client = OpenAI(api_key=api_key, timeout=max(OPENAI_API_TIMEOUT, 120))
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a professional institutional technical analyst. Provide precise entry levels and clear recommendations (STRONG BUY / BUY ON PULLBACK / WAIT / PASS)."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_completion_tokens=max_tokens,
            )
            usage = None
            if getattr(response, "usage", None):
                u = response.usage
                usage = {"prompt_tokens": getattr(u, "prompt_tokens", None), "completion_tokens": getattr(u, "completion_tokens", None), "total_tokens": getattr(u, "total_tokens", None)}
            return response.choices[0].message.content, usage
        except Exception as e:
            last_error = e
            logger.warning("ChatGPT attempt %s failed: %s", attempt + 1, e)
            if attempt < OPENAI_CHATGPT_RETRY_ATTEMPTS - 1:
                time.sleep(OPENAI_CHATGPT_RETRY_BASE_SECONDS * (attempt + 1))
    return None, None


def main():
    parser = argparse.ArgumentParser(description="New5: ChatGPT new position suggestions (new pipeline)")
    parser.add_argument("--model", default=None, help=f"OpenAI model (default: {OPENAI_CHATGPT_MODEL})")
    parser.add_argument("--api-key", default=None, help="OpenAI API key (default: OPENAI_API_KEY env)")
    parser.add_argument("--limit", type=int, default=50, help="Max A+/A stocks to analyze (default 50)")
    args = parser.parse_args()

    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[ERROR] OPENAI_API_KEY not set. Set it in .env or use --api-key")
        return

    if not PREPARED_NEW.exists():
        print(f"[ERROR] Prepared data not found: {PREPARED_NEW}. Run New3 first.")
        return

    with open(PREPARED_NEW, "r", encoding="utf-8") as f:
        data = json.load(f)
    stocks = data.get("stocks", [])
    # Sort best to worst: A+ first, then A; within grade: meets_criteria first, then closer to buy (lower distance_to_buy_pct)
    def sort_key(s):
        grade_rank = 0 if s.get("grade") == "A+" else 1
        meets = 0 if s.get("meets_criteria") else 1
        dist = s.get("distance_to_buy_pct")
        if dist is None:
            dist = 999
        return (grade_rank, meets, dist)
    stocks = sorted(stocks, key=sort_key)[: args.limit]

    if not stocks:
        print("No A+/A stocks in prepared data (run New1 and New3; ensure scan produces A+ or A).")
        return

    model = args.model or OPENAI_CHATGPT_MODEL
    max_tokens = min(OPENAI_CHATGPT_MAX_COMPLETION_TOKENS, 8000)

    print(f"\n{'='*80}")
    print("NEW5: CHATGPT NEW POSITION SUGGESTIONS (A+/A)")
    print(f"{'='*80}")
    print(f"Stocks: {len(stocks)}  Model: {model}")
    print(f"{'='*80}\n")

    report_lines = ["=" * 80, "NEW5: CHATGPT NEW POSITION SUGGESTIONS (A+/A)", "=" * 80, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", f"Model: {model}", ""]

    # Ranking section: best to worst (same order as sorted stocks)
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
        content, usage = send_to_chatgpt(prompt_text, api_key, model, max_tokens)
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
