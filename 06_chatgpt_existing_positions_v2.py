"""
Pipeline step 06 V2: ChatGPT analysis for existing (opened) positions from Trading212.
Reads reportsV2/prepared_existing_positions_v2.json (from 05_prepare_chatgpt_data_v2.py).
Uses full position data (entry, current, quantity, currency) + OHLCV; optionally enriches
with V2 scan data (composite_score, grade, base type, pivot) when the ticker was in the scan.
Output: institutional review and a clear suggestion per stock (HOLD / ADD / TRIM / EXIT).
Writes reportsV2/chatgpt_existing_positions_v2_<ts>.txt
"""
import json
import re
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from dotenv import load_dotenv
from logger_config import setup_logging, get_logger
from openai_utils import require_openai_api_key, send_to_chatgpt as openai_send
from config import (
    DEFAULT_ENV_PATH,
    OPENAI_CHATGPT_MODEL,
    OPENAI_CHATGPT_MAX_COMPLETION_TOKENS,
    REPORTS_DIR_V2,
    SCAN_RESULTS_V2_LATEST,
)

if Path(DEFAULT_ENV_PATH).exists():
    load_dotenv(Path(DEFAULT_ENV_PATH))

V2_REPORTS = REPORTS_DIR_V2  # reportsV2
PREPARED_EXISTING_V2 = V2_REPORTS / "prepared_existing_positions_v2.json"

setup_logging(log_level="INFO", log_to_file=True)
logger = get_logger(__name__)


def _fmt(x, round_to=None):
    if x is None or x == "":
        return "—"
    try:
        v = float(x)
        return str(round(v, round_to)) if round_to is not None else str(v)
    except (TypeError, ValueError):
        return str(x)


def load_v2_scan_by_ticker() -> Dict[str, Dict]:
    """Load V2 scan results and index by ticker (uppercase)."""
    if not SCAN_RESULTS_V2_LATEST.exists():
        return {}
    try:
        with open(SCAN_RESULTS_V2_LATEST, "r", encoding="utf-8") as f:
            data = json.load(f)
        rows = data if isinstance(data, list) else []
        return {(str(r.get("ticker") or "").strip().upper()): r for r in rows if r.get("ticker")}
    except Exception as e:
        logger.warning("Could not load V2 scan for enrichment: %s", e)
        return {}


def _build_v2_context_block(v2_row: Dict) -> str:
    """Build optional V2 scan context section for the prompt."""
    base = v2_row.get("base") or {}
    rs = v2_row.get("relative_strength") or {}
    br = v2_row.get("breakout") or {}
    risk = v2_row.get("risk") or {}
    lines = [
        "V2 SCAN CONTEXT (this ticker was in the latest V2 scan):",
        f"- Grade: {v2_row.get('grade') or '—'}",
        f"- Composite Score: {_fmt(v2_row.get('composite_score'), 1)}",
        f"- Base Type: {base.get('type') or '—'}",
        f"- Base Length (weeks): {_fmt(base.get('length_weeks'), 1)}",
        f"- Base Depth %: {_fmt(base.get('depth_pct'), 1)}",
        f"- Pivot Price: {_fmt(br.get('pivot_price'), 2)}",
        f"- Distance to Pivot %: {(_fmt(br.get('distance_to_pivot_pct'), 2) + '%') if br.get('distance_to_pivot_pct') is not None else '—'}",
        f"- RS Percentile: {_fmt(rs.get('rs_percentile'), 1)}",
        f"- Stop (V2): {_fmt(risk.get('stop_price'), 2)}",
    ]
    return "\n".join(lines)


PROMPT_TEMPLATE = """Act as a professional institutional technical analyst using Mark Minervini, Stan Weinstein, and quantitative price/volume analysis.

Use quantitative analysis on the OHLCV data to compute moving averages, trend structure, and key levels.

TIMEFRAME: swing
RISK PROFILE: moderate

I currently hold this position (from my broker). Analyze it and give me a clear action suggestion at the end.

========================
MY POSITION (from Trading)
========================
Ticker: {ticker}
Name: {name}
My entry price: {entry_price}
Current price (from broker at fetch time): {current_price}
Position size: {position_size}
Currency: {currency}

{v2_context}

========================
DAILY OHLCV DATA
========================
{ohlcv_csv}

========================
ANALYSIS REQUIREMENTS
========================

1. Trend: 50/150/200 MAs, Weinstein stage, whether trend still supports holding.
2. Key levels: support, resistance, Minervini pivot, breakdown level that would invalidate the position.
3. Position review: entry quality, current strength (strong hold / hold / consider trim / consider exit), stop level, add levels if applicable.
4. Volume: accumulation vs distribution since entry; institutional behavior.
5. Risk/reward: probability of working vs breakdown; upside targets and downside to stop.
6. Scenarios: bullish (hold/add), neutral (hold/trim), bearish (trim/exit).

========================
REQUIRED OUTPUT
========================

At the very end of your response you MUST include exactly one of these lines:

RECOMMENDATION: HOLD
RECOMMENDATION: ADD
RECOMMENDATION: TRIM
RECOMMENDATION: EXIT

Follow that line with one short sentence explaining why (e.g. "RECOMMENDATION: HOLD — Trend intact, above key support, no distribution.")

Also provide:
- Hold above: [level]
- Sell below (stop): [level]
- Add above (if applicable): [level]
- Trim above (if applicable): [level]

Use precise numeric levels from the OHLCV data. Be specific, not generic.
"""

PROMPT_NO_OHLCV = """Act as a professional institutional technical analyst.

I hold this position but no OHLCV history was available.

MY POSITION (from Trading):
Ticker: {ticker}
Name: {name}
My entry price: {entry_price}
Current price: {current_price}
Position size: {position_size}
Currency: {currency}

{v2_context}

Provide a brief review and a clear suggestion. End your response with exactly one of:
RECOMMENDATION: HOLD
RECOMMENDATION: ADD
RECOMMENDATION: TRIM
RECOMMENDATION: EXIT
Follow with one short sentence explaining why. Suggest stop and add levels if applicable.
"""

NO_OHLCV_PLACEHOLDER = "No OHLCV data available for this ticker."


def _parse_recommendation(content: str) -> Tuple[str, str]:
    """
    Parse RECOMMENDATION: HOLD|ADD|TRIM|EXIT and the following rationale line.
    Returns (action, rationale); action is one of HOLD, ADD, TRIM, EXIT or "".
    """
    if not content or not content.strip():
        return ("", "")
    # Find last occurrence of RECOMMENDATION: X (in case model repeats)
    pattern = re.compile(
        r"RECOMMENDATION\s*:\s*(HOLD|ADD|TRIM|EXIT)\s*[.—\-]*\s*(.*?)(?=\n|$)",
        re.IGNORECASE | re.DOTALL,
    )
    matches = list(pattern.finditer(content))
    if not matches:
        return ("", "")
    m = matches[-1]
    action = (m.group(1) or "").strip().upper()
    rationale = (m.group(2) or "").strip()
    # Take first sentence or first 200 chars
    if "\n" in rationale:
        rationale = rationale.split("\n")[0].strip()
    rationale = rationale[:250].strip()
    return (action, rationale)


def main():
    parser = argparse.ArgumentParser(
        description="06 V2: ChatGPT analysis for existing positions (Trading212 + OHLCV, optional V2 scan context)"
    )
    parser.add_argument("--model", default=None, help="OpenAI model")
    parser.add_argument("--api-key", default=None, help="OpenAI API key")
    parser.add_argument("--limit", type=int, default=100, help="Max positions to analyze (default 100)")
    args = parser.parse_args()

    api_key = require_openai_api_key(args.api_key)
    if not PREPARED_EXISTING_V2.exists():
        print(f"[ERROR] {PREPARED_EXISTING_V2} not found. Run 02_fetch_positions_trading212_V2.py then 05_prepare_chatgpt_data_v2.py.")
        return

    with open(PREPARED_EXISTING_V2, "r", encoding="utf-8") as f:
        data = json.load(f)
    positions = data.get("positions", [])[: args.limit]
    if not positions:
        print("No positions in prepared data. Run 02 (Trading212) then 05 V2.")
        return

    v2_by_ticker = load_v2_scan_by_ticker()
    model = args.model or OPENAI_CHATGPT_MODEL
    max_tokens = min(OPENAI_CHATGPT_MAX_COMPLETION_TOKENS, 8000)

    print(f"\n{'='*80}")
    print("06 V2: CHATGPT EXISTING POSITIONS (Trading212 + V2 context)")
    print(f"{'='*80}")
    print(f"Positions: {len(positions)}  Model: {model}")
    print(f"{'='*80}\n")

    results: List[Tuple[Dict, Optional[str], str, str]] = []  # (pos, content, action, rationale)

    for i, pos in enumerate(positions, 1):
        ticker = pos.get("ticker", "?")
        name = pos.get("name", ticker)
        entry = pos.get("entry", 0)
        current = pos.get("current")
        current_str = f"{current:.2f}" if current is not None else "N/A"
        quantity = pos.get("quantity", 0)
        currency = pos.get("currency", "USD")
        position_size = f"{quantity} shares" if quantity else "N/A"
        ohlcv = (pos.get("ohlcv_csv") or "").strip()

        v2_row = v2_by_ticker.get((ticker or "").strip().upper()) if ticker else None
        v2_context = _build_v2_context_block(v2_row) if v2_row else "V2 scan context: not available (ticker not in latest scan or scan not run)."

        if not ohlcv or ohlcv == NO_OHLCV_PLACEHOLDER:
            prompt_text = PROMPT_NO_OHLCV.format(
                ticker=ticker,
                name=name,
                entry_price=entry,
                current_price=current_str,
                position_size=position_size,
                currency=currency,
                v2_context=v2_context,
            )
        else:
            prompt_text = PROMPT_TEMPLATE.format(
                ticker=ticker,
                name=name,
                entry_price=entry,
                current_price=current_str,
                position_size=position_size,
                currency=currency,
                v2_context=v2_context,
                ohlcv_csv=ohlcv,
            )

        print(f"[{i}/{len(positions)}] {ticker} ... ", end="", flush=True)
        content, _ = openai_send(prompt_text, api_key, model=model, max_tokens=max_tokens)
        action, rationale = _parse_recommendation(content) if content else ("", "")
        if not content:
            print("FAILED")
            results.append((pos, None, "", ""))
            continue
        print(f"OK -> {action or '-'}")
        results.append((pos, content, action, rationale))

    # Report
    report_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_lines = [
        "=" * 80,
        "06 V2: CHATGPT EXISTING POSITION SUGGESTIONS",
        "=" * 80,
        f"Generated: {report_ts}",
        f"Model: {model}",
        f"Source: Trading212 positions + OHLCV (+ V2 scan when available)",
        "",
    ]

    # Summary: what to do with each stock
    report_lines.append("=" * 80)
    report_lines.append("SUGGESTIONS SUMMARY (what to do with each stock)")
    report_lines.append("=" * 80)
    report_lines.append("")
    report_lines.append("| Ticker | Suggestion | Rationale |")
    report_lines.append("|--------|------------|-----------|")
    for pos, _, action, rationale in results:
        ticker = pos.get("ticker", "?")
        action_display = action or "—"
        rationale_display = (rationale or "").replace("|", "\\|")[:120]
        report_lines.append(f"| {ticker} | {action_display} | {rationale_display} |")
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("DETAILED ANALYSIS")
    report_lines.append("=" * 80)
    report_lines.append("")

    for pos, content, action, _ in results:
        ticker = pos.get("ticker", "?")
        name = pos.get("name", ticker)
        report_lines.append(f"### {ticker} ({name}) — Suggestion: {action or '—'}")
        report_lines.append("")
        if content:
            report_lines.append(content.strip())
        else:
            report_lines.append("(ChatGPT request failed.)")
        report_lines.append("")
        report_lines.append("-" * 80)
        report_lines.append("")

    V2_REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = V2_REPORTS / f"chatgpt_existing_positions_v2_{ts}.txt"
    out_file.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Report saved: {out_file}\n")


if __name__ == "__main__":
    main()
