"""
Pipeline step 7 (V2): ChatGPT analysis for new position candidates using V2 scan output.
Reads reportsV2/prepared_new_positions_v2.json (from 05_prepare_chatgpt_data_v2.py).
Uses the structured V2 fields (composite_score, base type, rs_percentile, pivot, stop_method) in the prompt.
Writes reportsV2/chatgpt_new_positions_v2_<ts>.txt
"""
import json
import re
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict

from dotenv import load_dotenv
from logger_config import setup_logging, get_logger
from openai_utils import require_openai_api_key, send_to_chatgpt as openai_send
from config import (
    DEFAULT_ENV_PATH,
    OPENAI_CHATGPT_MODEL,
    OPENAI_CHATGPT_MAX_COMPLETION_TOKENS,
    REPORTS_DIR_V2,
    EXTENDED_DISTANCE_PCT,
    BREAKOUT_SCORE_TIGHT_LOW_PCT,
    BREAKOUT_SCORE_TIGHT_HIGH_PCT,
)

if Path(DEFAULT_ENV_PATH).exists():
    load_dotenv(Path(DEFAULT_ENV_PATH))

V2_REPORTS = REPORTS_DIR_V2  # reportsV2
PREPARED_NEW_V2 = V2_REPORTS / "prepared_new_positions_v2.json"

setup_logging(log_level="INFO", log_to_file=True)
logger = get_logger(__name__)

ORDER_PROMPT_V2 = """You are a technical analyst. Below are candidate stocks from a Minervini SEPA V2 scan (composite score, base type, RS percentile, distance to pivot).

Rank them in the order you recommend for considering new entries: best opportunity first. One ticker per line. Reply with nothing else than the list of tickers.

STOCKS:
{stocks_list}
"""


def _fmt(x, round_to=None):
    """Format value for prompt; use — if None or missing."""
    if x is None or x == "":
        return "—"
    try:
        v = float(x)
        return str(round(v, round_to)) if round_to is not None else str(v)
    except (TypeError, ValueError):
        return str(x)


def _infer_exchange(ticker: str) -> str:
    """Infer market/exchange from ticker suffix when available from prior data."""
    t = (ticker or "").strip().upper()
    if t.endswith(".DE") or t.endswith(".F") or t.endswith(".ETR"):
        return "XETRA / Frankfurt"
    if t.endswith(".L"):
        return "LSE"
    if t.endswith(".PA"):
        return "Euronext Paris"
    if t.endswith(".AS"):
        return "Euronext Amsterdam"
    if t.endswith(".SW") or t.endswith(".SRX"):
        return "SIX"
    if "." in t:
        return "—"
    return "US"


def _build_stock_data_section(s: Dict) -> str:
    """Build STOCK DATA section from payload; use — when not available from prior scripts."""
    ticker = s.get("ticker") or "—"
    base = s.get("base") or {}
    rs = s.get("relative_strength") or {}
    br = s.get("breakout") or {}
    # Current price: from derived or from pivot + distance
    current = s.get("current_price")
    if current is None and br.get("pivot_price") is not None and br.get("distance_to_pivot_pct") is not None:
        try:
            p = float(br["pivot_price"])
            d = float(br["distance_to_pivot_pct"]) / 100
            current = round(p * (1 + d), 2)
        except (TypeError, ValueError):
            pass
    lines = [
        "========================\nSTOCK DATA\n========================\n",
        f"Ticker: {ticker}",
        f"Market: {_infer_exchange(ticker)}",
        "Timeframe: Daily\n",
        "Trend:",
        f"- Current Price: {_fmt(current, 2)}",
        f"- 50 MA: {_fmt(s.get('sma_50'), 2)}",
        f"- 150 MA: {_fmt(s.get('sma_150'), 2)}",
        f"- 200 MA: {_fmt(s.get('sma_200'), 2)}",
        f"- 52w High: {_fmt(s.get('52_week_high'), 2)}",
        f"- 52w Low: {_fmt(s.get('52_week_low'), 2)}",
        f"- Prior Run % (last major advance): {(_fmt(base.get('prior_run_pct'), 1) + '%') if base.get('prior_run_pct') is not None else '—'}\n",
        "Base:",
        f"- Base Type: {base.get('type') or '—'}",
        f"- Base Length (weeks): {_fmt(base.get('length_weeks'), 1)}",
        f"- Base Depth %: {_fmt(base.get('depth_pct'), 1)}",
        f"- Pivot Price: {_fmt(br.get('pivot_price'), 2)}",
        f"- Distance to Pivot %: {(_fmt(br.get('distance_to_pivot_pct'), 2) + '%') if br.get('distance_to_pivot_pct') is not None else '—'}\n",
        "Momentum:",
        f"- RSI (14): {_fmt(rs.get('rsi_14'), 1)}",
        f"- 3M Return %: {(_fmt(rs.get('rs_3m'), 2) + '%') if rs.get('rs_3m') is not None else '—'}",
        f"- 6M Return %: {(_fmt(s.get('return_6m_pct'), 2) + '%') if s.get('return_6m_pct') is not None else '—'}",
        f"- 12M Return %: {(_fmt(s.get('return_12m_pct'), 2) + '%') if s.get('return_12m_pct') is not None else '—'}",
        f"- RS Percentile (vs universe): {_fmt(rs.get('rs_percentile'), 1)}\n",
        "Volume:",
        f"- Avg Daily Volume: {_fmt(s.get('avg_daily_volume'), 0)}",
        f"- Accumulation/Distribution Days (last 4 weeks): {_fmt(s.get('accumulation_days_4w'), 0) if s.get('accumulation_days_4w') is not None else '—'}",
        f"- Breakout volume vs average (last 5d/20d avg): {_fmt(s.get('breakout_volume_vs_avg'), 2) if s.get('breakout_volume_vs_avg') is not None else '—'}\n",
        "Market Context:",
        "- Index Trend (e.g., S&P 500 / DAX): —",
        "- Sector Trend: —",
        "- Stock vs Sector performance: —",
    ]
    return "\n".join(lines)


INDEPENDENT_ANALYSIS_PROMPT = """You are an independent institutional momentum trader using a strict Minervini-style SEPA framework.

IMPORTANT:
- Ignore any prior grading or model output until the very end.
- Do NOT anchor to my internal score.
- Perform a fully independent evaluation based only on the data provided.
- Be critical. If the structure is flawed, say so clearly.

{stock_data_section}

========================
INDEPENDENT ANALYSIS REQUIRED
========================

Answer the following:

1. Is the stock in a valid Stage 2 uptrend?
2. Is the current base constructive, extended, or damaged?
3. Is relative strength indicating institutional accumulation?
4. What are the three biggest technical strengths?
5. What are the three biggest technical weaknesses?
6. Would you classify this as A / B / C / D quality?
7. Is it buyable now? If not, what must improve?
8. What would invalidate the setup?
9. How would this likely behave in:
   A) Strong market continuation
   B) Market correction

Be decisive and specific. Avoid vague language.

========================
MODEL OUTPUT (FOR COMPARISON ONLY — DO NOT ANCHOR)
========================

My internal model graded this as:

Composite Score: {composite_score}
Grade: {grade}
Status: {status}

Now compare your independent evaluation to the model grade.
If your conclusion differs by more than one grade, explain precisely why.
"""


def _status_for_prompt(s: Dict) -> str:
    """Short status label for MODEL OUTPUT section."""
    grade = s.get("grade") or ""
    br = s.get("breakout") or {}
    dist = br.get("distance_to_pivot_pct")
    in_breakout = br.get("in_breakout", False)
    try:
        d = float(dist) if dist is not None else 0
    except (TypeError, ValueError):
        d = 0
    if in_breakout:
        return "Triggered (in breakout)"
    if BREAKOUT_SCORE_TIGHT_LOW_PCT <= d <= BREAKOUT_SCORE_TIGHT_HIGH_PCT and grade in ("A+", "A"):
        return "Ready"
    if d > EXTENDED_DISTANCE_PCT:
        return "Extended"
    if grade == "B":
        return "Developing"
    return "Watch"


def _parse_ticker_order(text: str, valid: set) -> List[str]:
    ordered = []
    seen = set()
    for line in text.strip().splitlines():
        line = re.sub(r"^\s*\d+[.)]\s*", "", line.strip())
        line = re.sub(r"^\s*[-*]\s*", "", line)
        for part in line.replace(",", " ").split():
            t = part.upper().strip(".:)")
            if 1 <= len(t) <= 12 and t not in seen and t in valid:
                ordered.append(t)
                seen.add(t)
    return ordered


def _reorder(stocks: List[Dict], ordered: List[str]) -> List[Dict]:
    by_ticker = {}
    for s in stocks:
        t = str(s.get("ticker", "")).strip().upper()
        by_ticker[t] = s
    result = []
    for t in ordered:
        t = t.upper().strip()
        if t in by_ticker:
            result.append(by_ticker[t])
    for s in stocks:
        if s not in result:
            result.append(s)
    return result


def _parse_chatgpt_grade_from_response(content: str) -> str:
    """
    Extract ChatGPT's quality grade from the response (e.g. Comparison section).
    Looks for patterns like "My independent conclusion is **B**", "**B+**", "I would rate **A**".
    Returns empty string if not found.
    """
    if not content or not content.strip():
        return ""
    # Normalize: look for ## Comparison or similar, then nearby **X** or **X+**
    comp_idx = content.find("Comparison to your model grade")
    if comp_idx == -1:
        comp_idx = content.find("Comparison vs your model grade")
    if comp_idx == -1:
        comp_idx = 0
    # Search in the 800 chars after the comparison header
    block = content[comp_idx : comp_idx + 800]
    # Common patterns: "**B**", "**A+**", "**B+**", "My conclusion is **B**", "grade: **A**"
    # Prefer "My ... conclusion ... **Grade**" or "I would ... **Grade**" or "**Grade** /"
    for pattern in [
        r"My independent conclusion is\s*\*\*([A-D][+]?)\*\*",
        r"Mine:\s*\*\*([A-D][+]?)\*\*",
        r"\*\*([A-D][+]?)\*\*\s*/\s*",
        r"Quality (?:grade|classification).*?\*\*([A-D][+]?)\*\*",
        r"([A-D][+]?)\s*/\s*Not (?:buyable|ready)",
        r"would you classify.*?\*\*([A-D][+]?)\*\*",
        r"\*\*([A-D][+]?)\*\*",
    ]:
        m = re.search(pattern, block, re.IGNORECASE | re.DOTALL)
        if m:
            g = (m.group(1) or "").strip().upper().replace("*", "")
            if g and g[0] in ("A", "B", "C", "D") and (len(g) == 1 or g[1:] == "+"):
                return g
    return ""


def main():
    parser = argparse.ArgumentParser(description="08 V2: ChatGPT new position suggestions (uses V2 scan output)")
    parser.add_argument("--model", default=None, help="OpenAI model")
    parser.add_argument("--api-key", default=None, help="OpenAI API key")
    parser.add_argument("--limit", type=int, default=50, help="Max stocks to load for ranking")
    parser.add_argument("--max-rank", type=int, default=50, help="Run detailed ChatGPT analysis only for stocks up to this rank (default 50)")
    args = parser.parse_args()

    api_key = require_openai_api_key(args.api_key)
    if not PREPARED_NEW_V2.exists():
        print(f"[ERROR] {PREPARED_NEW_V2} not found. Run 04_generate_full_report_v2.py then 05_prepare_chatgpt_data_v2.py.")
        return

    with open(PREPARED_NEW_V2, "r", encoding="utf-8") as f:
        data = json.load(f)
    stocks = data.get("stocks", [])[: args.limit]
    if not stocks:
        print("No A+/A stocks in V2 prepared data.")
        return

    meta = data.get("meta") or {}
    data_timestamp_yahoo = meta.get("data_timestamp_yahoo")

    model = args.model or OPENAI_CHATGPT_MODEL
    valid_tickers = {str(s.get("ticker", "")).strip().upper() for s in stocks}
    stocks_list = "\n".join(
        f"  {s.get('ticker')}  score={s.get('composite_score')}  base={(s.get('base') or {}).get('type')}  rs_pct={(s.get('relative_strength') or {}).get('rs_percentile')}  dist_pivot={(s.get('breakout') or {}).get('distance_to_pivot_pct')}"
        for s in stocks
    )
    order_prompt = ORDER_PROMPT_V2.format(stocks_list=stocks_list)
    print("Asking ChatGPT for recommended order...")
    order_resp, _ = openai_send(order_prompt, api_key, model=model, max_tokens=500)
    chatgpt_order = []
    if order_resp:
        ordered = _parse_ticker_order(order_resp, valid_tickers)
        if ordered:
            chatgpt_order = ordered
            stocks = _reorder(stocks, ordered)
            print(f"Order: {' -> '.join(ordered[:15])}{' ...' if len(ordered) > 15 else ''}")

    # Ranking by my composite score (for first table)
    ranking_by_my_score = sorted(stocks, key=lambda s: (-(float(s.get("composite_score") or 0)), s.get("ticker") or ""))

    print(f"\n{'='*80}\n08 V2: CHATGPT NEW POSITIONS (V2 scan data)\n{'='*80}\n")
    report_run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_lines = [
        "=" * 80, "08 V2: CHATGPT NEW POSITION SUGGESTIONS", "=" * 80,
        f"Report run: {report_run_ts}",
        f"Data as of (Yahoo): {data_timestamp_yahoo or '—'}",
        f"Model: {model}", "Source: V2 scan (composite score, base type, RS percentile)", ""
    ]
    report_lines.append("RANKING (by my composite score)")
    report_lines.append("-" * 80)
    for rank, s in enumerate(ranking_by_my_score, 1):
        report_lines.append(f"  {rank}. {s.get('ticker')} ({s.get('grade')}) composite={s.get('composite_score')}")
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("DETAILED ANALYSIS (ranks 1–{})".format(min(args.max_rank, len(stocks))))
    report_lines.append("=" * 80)
    report_lines.append("")

    stocks_to_analyze = stocks[: args.max_rank]
    comparison_rows = []  # (ticker, my_grade, my_score, chatgpt_grade)
    for i, s in enumerate(stocks_to_analyze, 1):
        ticker = s.get("ticker", "?")
        stock_data_section = _build_stock_data_section(s)
        prompt_text = INDEPENDENT_ANALYSIS_PROMPT.format(
            stock_data_section=stock_data_section,
            composite_score=s.get("composite_score") if s.get("composite_score") is not None else "—",
            grade=s.get("grade", "—"),
            status=_status_for_prompt(s),
        )
        print(f"[{i}/{len(stocks_to_analyze)}] {ticker} ... ", end="", flush=True)
        content, _ = openai_send(prompt_text, api_key, model=model, max_tokens=min(OPENAI_CHATGPT_MAX_COMPLETION_TOKENS, 8000))
        if not content:
            print("FAILED")
            report_lines.append(f"### {ticker}\n(ChatGPT request failed.)\n")
            comparison_rows.append((ticker, s.get("grade"), s.get("composite_score"), ""))
            continue
        print("OK")
        cg_grade = _parse_chatgpt_grade_from_response(content)
        comparison_rows.append((ticker, s.get("grade"), s.get("composite_score"), cg_grade))
        report_lines.append(f"### {ticker} [{s.get('grade')}] composite={s.get('composite_score')}")
        report_lines.append("")
        report_lines.append(content.strip())
        report_lines.append("")
        report_lines.append("-" * 80)
        report_lines.append("")

    # Table: My score vs ChatGPT score (ordered by my composite score)
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("MY SCORE VS CHATGPT SCORE (ordered by my composite score)")
    report_lines.append("=" * 80)
    report_lines.append("")
    comparison_rows.sort(key=lambda x: (-(float(x[2]) if x[2] is not None else 0), x[0] or ""))
    report_lines.append("| Rank | Ticker | My Grade | My Score | ChatGPT Grade |")
    report_lines.append("|" + "---|" * 5)
    for r, (ticker, my_grade, my_score, cg_grade) in enumerate(comparison_rows, 1):
        report_lines.append(f"| {r} | {ticker} | {my_grade or '—'} | {my_score or '—'} | {cg_grade or '—'} |")
    report_lines.append("")

    V2_REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = V2_REPORTS / f"chatgpt_new_positions_v2_{ts}.txt"
    out_file.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Report saved: {out_file}\n")


if __name__ == "__main__":
    main()
