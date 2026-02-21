"""
New pipeline (4/5): ChatGPT analysis for existing positions (from prepared data).
Reads prepared_existing_positions.json, sends raw OHLCV + position info to ChatGPT, writes report.
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
PREPARED_EXISTING = NEW_PIPELINE_REPORTS / "prepared_existing_positions.json"

PROMPT_TEMPLATE = """Act as a professional institutional technical analyst using Mark Minervini, Stan Weinstein, and quantitative price/volume analysis.

Use quantitative analysis on the OHLCV data to compute moving averages, trend structure, and breakout probabilities.

TIMEFRAME: swing
RISK PROFILE: moderate

I will provide raw daily OHLCV data from Yahoo Finance for a stock I currently hold.

Analyze the position and provide a complete institutional-grade review: whether to hold, add, trim, or exit, with exact levels.

STOCK INFO:
Ticker: {ticker}
My entry price: {entry_price}
Current price (from broker at fetch time): {current_price}
My position size: {position_size}
Currency: {currency}

DATA:
{ohlcv_csv}

ANALYSIS REQUIREMENTS:

1. Trend Analysis
- Calculate and analyze 50, 150, and 200 day moving averages
- Identify Weinstein stage (Stage 1–4)
- Determine short, medium, and long-term trend direction
- Assess whether the trend still supports holding this position

2. Key Levels
- Identify exact support levels (where I should hold or add)
- Identify exact resistance levels (targets or trim zones)
- Identify Minervini pivot and relevance to my entry
- Identify breakdown levels that would invalidate the position

3. Position Review (focus: my existing position)
- Score my entry quality (1–10) and whether it still makes sense to hold
- Evaluate current position strength (strong hold / hold / consider trim / consider exit)
- Calculate proper stop loss level (sell below)
- Calculate optimal add levels (if trend and structure support adding)
- Recommend: HOLD, ADD, TRIM, or EXIT with brief rationale

4. Volume Analysis
- Detect accumulation or distribution since my entry
- Identify institutional activity (supportive or concerning for holding)
- Confirm or question breakout quality if near/at breakout

5. Risk / Reward for This Position
- Probability of position working (upside to next targets) (%)
- Probability of breakdown (downside to stop) (%)
- Expected upside targets from current price
- Expected downside to stop

6. Scenario Forecast (for my position)
- Bullish: price targets and what to do (hold/add)
- Neutral: range and action (hold or trim)
- Bearish: breakdown level and action (trim or exit)

7. Institutional Rating
- Rate overall position quality now (1–10)
- Confirm or revise whether this still qualifies as a valid Stage 2 hold

8. Exact Action Plan (for my existing position)
Provide precise levels:
- Hold above:
- Sell below (stop):
- Add above (if applicable):
- Trim / reduce above (if applicable):

Use precise numeric levels derived from the OHLCV data.
Avoid generic advice. Prioritize price structure, moving averages, and volume behavior in the context of managing my current position.
"""

PROMPT_NO_OHLCV = """Act as a professional institutional technical analyst.

I hold this position but no OHLCV history was available for the prompt.

STOCK INFO:
Ticker: {ticker}
My entry price: {entry_price}
Current price (from broker at fetch time): {current_price}
Position size: {position_size}
Currency: {currency}

Provide a brief institutional-grade review: HOLD / ADD / TRIM / EXIT with rationale, and suggest a stop level and add level if applicable. Use general Minervini/Weinstein principles.
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
                    {"role": "system", "content": "You are a professional institutional technical analyst. Provide precise price levels and clear action plans (HOLD/ADD/TRIM/EXIT)."},
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
    parser = argparse.ArgumentParser(description="New4: ChatGPT existing position suggestions (new pipeline)")
    parser.add_argument("--model", default=None, help=f"OpenAI model (default: {OPENAI_CHATGPT_MODEL})")
    parser.add_argument("--api-key", default=None, help="OpenAI API key (default: OPENAI_API_KEY env)")
    args = parser.parse_args()

    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[ERROR] OPENAI_API_KEY not set. Set it in .env or use --api-key")
        return

    if not PREPARED_EXISTING.exists():
        print(f"[ERROR] Prepared data not found: {PREPARED_EXISTING}. Run New3 first.")
        return

    with open(PREPARED_EXISTING, "r", encoding="utf-8") as f:
        data = json.load(f)
    positions = data.get("positions", [])
    if not positions:
        print("No positions in prepared data (run New2 to fetch positions, then New3).")
        return

    model = args.model or OPENAI_CHATGPT_MODEL
    max_tokens = min(OPENAI_CHATGPT_MAX_COMPLETION_TOKENS, 8000)

    print(f"\n{'='*80}")
    print("NEW4: CHATGPT EXISTING POSITIONS")
    print(f"{'='*80}")
    print(f"Positions: {len(positions)}  Model: {model}")
    print(f"{'='*80}\n")

    report_lines = ["=" * 80, "NEW4: CHATGPT EXISTING POSITION SUGGESTIONS", "=" * 80, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", f"Model: {model}", ""]
    total_tokens = 0

    NO_OHLCV_PLACEHOLDER = "No OHLCV data available for this ticker (cache missing or ticker not in watchlist)."
    for i, pos in enumerate(positions, 1):
        ticker = pos.get("ticker", "?")
        entry = pos.get("entry", 0)
        current = pos.get("current")
        current_str = f"{current:.2f}" if current is not None else "N/A"
        quantity = pos.get("quantity", 0)
        currency = pos.get("currency", "USD")
        name = pos.get("name", ticker)
        ohlcv = pos.get("ohlcv_csv", "")
        position_size = f"{quantity} shares" if quantity else "N/A"
        if not ohlcv or ohlcv.strip() == NO_OHLCV_PLACEHOLDER:
            prompt_text = PROMPT_NO_OHLCV.format(
                ticker=ticker,
                entry_price=entry,
                current_price=current_str,
                position_size=position_size,
                currency=currency,
            )
        else:
            prompt_text = PROMPT_TEMPLATE.format(
                ticker=ticker,
                entry_price=entry,
                current_price=current_str,
                position_size=position_size,
                currency=currency,
                ohlcv_csv=ohlcv,
            )
        print(f"[{i}/{len(positions)}] {ticker} ... ", end="", flush=True)
        content, usage = send_to_chatgpt(prompt_text, api_key, model, max_tokens)
        if usage and usage.get("total_tokens"):
            total_tokens += usage["total_tokens"]
        if not content:
            print("FAILED")
            report_lines.append(f"### {ticker} ({name})")
            report_lines.append("(ChatGPT request failed.)")
            report_lines.append("")
            continue
        print("OK")
        report_lines.append(f"### {ticker} ({name})")
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
    out_file = NEW_PIPELINE_REPORTS / f"chatgpt_existing_positions_{ts}.txt"
    out_file.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Report saved: {out_file}\n")


if __name__ == "__main__":
    main()
