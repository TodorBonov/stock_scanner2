"""
Pipeline step 6/7: ChatGPT analysis for existing positions (from prepared data).
Reads prepared_existing_positions.json from step 05 (or _6mo with --use-6mo), sends OHLCV + position info to ChatGPT, writes report.
"""
import json
import argparse
from pathlib import Path
from datetime import datetime
import re
from typing import Optional, Dict, Tuple, List

from dotenv import load_dotenv
from logger_config import setup_logging, get_logger
from config import DEFAULT_ENV_PATH, OPENAI_CHATGPT_MODEL, OPENAI_CHATGPT_MAX_COMPLETION_TOKENS
from openai_utils import require_openai_api_key, send_to_chatgpt as openai_send

if Path(DEFAULT_ENV_PATH).exists():
    load_dotenv(Path(DEFAULT_ENV_PATH))

NEW_PIPELINE_REPORTS = Path("reports") / "new_pipeline"


def _prepared_path(use_6mo: bool) -> Path:
    return NEW_PIPELINE_REPORTS / ("prepared_existing_positions_6mo.json" if use_6mo else "prepared_existing_positions.json")


def _parse_entry_quality_score(text: str) -> Optional[int]:
    """Parse entry quality / position quality score (1-10) from ChatGPT response. Returns None if not found."""
    if not text or not text.strip():
        return None
    # Try explicit "entry quality" or "position quality" patterns first
    for pattern in [
        r"[Ee]ntry\s+quality\s*[:\-]?\s*(\d+)",
        r"[Pp]osition\s+quality\s*[:\-]?\s*(\d+)",
        r"[Rr]ate\s+(?:overall\s+)?(?:position\s+)?quality\s*[:\-]?\s*(\d+)",
        r"quality\s*(?:now|score)?\s*[:\-]?\s*(\d+)\s*/\s*10",
        r"score\s*[:\-]?\s*(\d+)\s*[/\-]?\s*10",
        r"(\d+)\s*/\s*10\s*(?:for\s+entry|for\s+position|entry\s+quality)",
        r"(\d+)\s*/\s*10\s*$",  # line ending in "X/10"
    ]:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if m:
            v = int(m.group(1))
            if 1 <= v <= 10:
                return v
    # Fallback: first "X/10" or "X out of 10" in the text
    m = re.search(r"\b(\d+)\s*/\s*10\b", text)
    if m:
        v = int(m.group(1))
        if 1 <= v <= 10:
            return v
    m = re.search(r"\b(\d+)\s+out\s+of\s+10\b", text, re.IGNORECASE)
    if m:
        v = int(m.group(1))
        if 1 <= v <= 10:
            return v
    return None


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


def main():
    parser = argparse.ArgumentParser(description="04: ChatGPT existing position suggestions (pipeline)")
    parser.add_argument("--model", default=None, help=f"OpenAI model (default: {OPENAI_CHATGPT_MODEL})")
    parser.add_argument("--api-key", default=None, help="OpenAI API key (default: OPENAI_API_KEY env)")
    parser.add_argument("--use-6mo", dest="use_6mo", action="store_true", help="Use 6-month OHLCV prepared data (prepared_existing_positions_6mo.json)")
    args = parser.parse_args()

    api_key = require_openai_api_key(args.api_key)
    prepared_path = _prepared_path(args.use_6mo)
    if not prepared_path.exists():
        print(f"[ERROR] Prepared data not found: {prepared_path}. Run 03 (with --use-6mo if needed) first.")
        return

    with open(prepared_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    positions = data.get("positions", [])
    if not positions:
        print("No positions in prepared data (run 02 to fetch positions, then 03).")
        return

    model = args.model or OPENAI_CHATGPT_MODEL
    max_tokens = min(OPENAI_CHATGPT_MAX_COMPLETION_TOKENS, 8000)

    print(f"\n{'='*80}")
    print("04: CHATGPT EXISTING POSITIONS")
    print(f"{'='*80}")
    print(f"Positions: {len(positions)}  Model: {model}")
    print(f"{'='*80}\n")

    NO_OHLCV_PLACEHOLDER = "No OHLCV data available for this ticker (cache missing or ticker not in watchlist)."
    results: List[Tuple[Dict, Optional[str], Optional[Dict], Optional[int]]] = []  # (pos, content, usage, score)

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
        content, usage = openai_send(prompt_text, api_key, model=model, max_tokens=max_tokens)
        score = _parse_entry_quality_score(content) if content else None
        if not content:
            print("FAILED")
            results.append((pos, None, usage, None))
            continue
        print("OK" + (f" (score {score})" if score is not None else ""))
        results.append((pos, content, usage, score))

    # Sort by entry quality score high to low (no score last)
    results.sort(key=lambda x: (x[3] if x[3] is not None else -1), reverse=True)

    total_tokens = sum((u.get("total_tokens") or 0) for _, _, u, _ in results if u)
    report_lines = ["=" * 80, "04: CHATGPT EXISTING POSITION SUGGESTIONS", "=" * 80, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", f"Model: {model}", "Order: by entry quality score (high to low)", ""]
    if total_tokens:
        report_lines.append(f"Tokens used: {total_tokens:,}")
        report_lines.append("")

    report_lines.append("RANKING BY ENTRY QUALITY (high to low)")
    report_lines.append("-" * 80)
    for rank, (pos, content, _, score) in enumerate(results, 1):
        ticker = pos.get("ticker", "?")
        name = (pos.get("name") or ticker)[:50]
        score_str = f"Score: {score}" if score is not None else "Score: —"
        report_lines.append(f"  {rank}. {ticker} ({name}) — {score_str}")
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("DETAILED ANALYSIS (same order)")
    report_lines.append("=" * 80)
    report_lines.append("")

    for pos, content, usage, _ in results:
        ticker = pos.get("ticker", "?")
        name = pos.get("name", ticker)
        report_lines.append(f"### {ticker} ({name})")
        report_lines.append("")
        if content:
            report_lines.append(content.strip())
        else:
            report_lines.append("(ChatGPT request failed.)")
        report_lines.append("")
        report_lines.append("-" * 80)
        report_lines.append("")

    NEW_PIPELINE_REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = NEW_PIPELINE_REPORTS / f"chatgpt_existing_positions_{ts}.txt"
    out_file.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Report saved: {out_file}\n")


if __name__ == "__main__":
    main()
