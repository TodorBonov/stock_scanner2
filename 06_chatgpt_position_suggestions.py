"""
ChatGPT position suggestions script.
Runs after 03_position_suggestions.py. Reads the latest position_suggestions_*.txt,
sends it to ChatGPT, and writes AI suggestions to position_suggestions_Chat_GPT_*.txt.
Uses stored scan results (50/200 DMA, base highs/lows, volume) for SEPA-style pivot/add and must-hold levels.
Requires OPENAI_API_KEY in .env.
"""
import os
import re
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
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

logger = get_logger(__name__)

env_file = Path(DEFAULT_ENV_PATH)
if env_file.exists():
    load_dotenv(env_file)

REPORTS_DIR.mkdir(exist_ok=True)

# Scan results path (same as 03_position_suggestions)
SCAN_RESULTS_PATH = REPORTS_DIR / "scan_results_latest.json"


def get_latest_position_suggestions_file() -> Optional[Path]:
    """Return the path to the most recently modified position_suggestions_*.txt (excl. Chat_GPT)."""
    candidates = [
        p for p in REPORTS_DIR.glob("position_suggestions_*.txt")
        if "Chat_GPT" not in p.name
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


# Words that are not tickers (avoid matching from report lines)
NOT_TICKERS = frozenset({"HOLD", "EXIT", "ADD", "REDUCE", "POSITION", "POSITIONS", "RULES", "GENERATED", "TRADING"})


def extract_tickers_from_position_report(content: str) -> list[str]:
    """Parse ticker symbols from position suggestions report (blocks separated by ---)."""
    tickers = []
    for block in re.split(r"\n-{2,}\n", content):
        for line in block.splitlines():
            s = line.strip()
            if not s or "=" in s or s in NOT_TICKERS:
                continue
            if s.startswith(("Grade", "Suggestion", "Reason", "Entry", "Your", "Current vs", "Rules:", "Generated:", "Positions:")):
                break
            if 1 <= len(s) <= 12 and s.isupper() and s.isalpha():
                tickers.append(s)
                break
    return tickers


def load_chart_data_from_scan_results(tickers: list[str]) -> str:
    """
    Load 50/200 DMA, base highs/lows, and volume trend from scan_results_latest.json
    for the given tickers. Returns a text block to append to the ChatGPT prompt.
    """
    if not SCAN_RESULTS_PATH.exists():
        logger.info("No scan results at %s; skipping chart/level data", SCAN_RESULTS_PATH)
        return ""

    try:
        with open(SCAN_RESULTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("Could not load scan results: %s", e)
        return ""

    if not isinstance(data, list):
        return ""

    # Map ticker (any case) -> scan result row
    by_ticker = {}
    for item in data:
        t = (item.get("ticker") or "").strip().upper()
        if t:
            by_ticker[t] = item
            # Also allow without suffix (e.g. AAPL from AAPL_US_EQ)
        if "_" in t:
            base = t.split("_")[0]
            if base not in by_ticker:
                by_ticker[base] = item

    lines = []
    for ticker in tickers:
        t = ticker.upper()
        row = (
            by_ticker.get(t)
            or by_ticker.get(t.split("_")[0] if "_" in t else t)
            or (by_ticker.get(t[:-1]) if t.endswith("D") and len(t) > 1 else None)  # RWED->RWE, PFED->PFE
        )
        if not row:
            continue
        checklist = row.get("checklist") or {}
        trend = (checklist.get("trend_structure") or {}).get("details") or {}
        base = (checklist.get("base_quality") or {}).get("details") or {}
        volume = (checklist.get("volume_signature") or {}).get("details") or {}
        breakout = (checklist.get("breakout_rules") or {}).get("details") or {}

        parts = [f"[{ticker}]"]
        if trend:
            parts.append(
                f"50 DMA: ${trend.get('sma_50', 0):.2f} (above: {'Y' if trend.get('above_50') else 'N'}) | "
                f"200 DMA: ${trend.get('sma_200', 0):.2f} (above: {'Y' if trend.get('above_200') else 'N'})"
            )
        if base:
            parts.append(f"Base high (pivot): ${base.get('base_high', 0):.2f} | Base low: ${base.get('base_low', 0):.2f}")
        if volume:
            parts.append(
                f"Volume: contraction {volume.get('volume_contraction', 0):.2f}x, "
                f"ratio {volume.get('volume_ratio', 0):.2f}x, "
                f"recent vs 20d avg: {volume.get('volume_increase', 0):.2f}x"
            )
        if breakout:
            parts.append(f"Breakout volume ratio: {breakout.get('volume_ratio', 0):.2f}x")
        if len(parts) > 1:
            lines.append(" ".join(parts))

    if not lines:
        return ""
    return "Chart/level data from scan (use for SEPA pivot/add and must-hold levels):\n\n" + "\n".join(lines)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Send position suggestions to ChatGPT for AI recommendations")
    parser.add_argument("--model", type=str, default=None, help=f"OpenAI model (default: {OPENAI_CHATGPT_MODEL})")
    parser.add_argument("--api-key", type=str, default=None, help="OpenAI API key (default: OPENAI_API_KEY env)")
    parser.add_argument(
        "--extra",
        type=str,
        default=None,
        metavar="FILE",
        help="Optional extra file with additional chart/level notes (appended to auto-loaded scan data)",
    )
    args = parser.parse_args()

    api_key = require_openai_api_key(args.api_key)

    latest = get_latest_position_suggestions_file()
    if not latest or not latest.exists():
        print("\n[ERROR] No position_suggestions_*.txt found. Run 03_position_suggestions.py first.")
        return

    content = latest.read_text(encoding="utf-8")
    if not content.strip():
        print("\n[WARN] Position suggestions file is empty. Nothing to send to ChatGPT.")
        return

    print("=" * 80)
    print("CHATGPT POSITION SUGGESTIONS")
    print("=" * 80)
    print(f"\n[INFO] Using: {latest.name}")
    print("[INFO] Sending to ChatGPT...")

    prompt = (
        "Below is my current position suggestions report (rule-based: stop loss, profit targets, scan grades). "
        "For each position, give your suggested action (EXIT / REDUCE / HOLD / ADD), whether you agree or "
        "disagree with the rule-based suggestion, short reasoning, and what to watch. "
        "For each position, also give two stop loss suggestions: (1) Stop loss per my guidelines (the rule-based "
        "stop in the report). (2) Stop loss outside my guidelines — e.g. SEPA/chart-based (base low, key MA, "
        "must-hold level), regardless of the fixed-percent rule.\n\n"
        "---\n\n"
    ) + content

    # Auto-include chart/level data from stored scan results (50/200 DMA, base highs/lows, volume)
    tickers = extract_tickers_from_position_report(content)
    chart_block = load_chart_data_from_scan_results(tickers)
    if chart_block:
        prompt += "\n\n---\n\n" + chart_block
        print("[INFO] Included chart/level data from scan_results_latest.json for SEPA pivot/add and must-hold levels.")

    if args.extra:
        extra_path = Path(args.extra)
        if not extra_path.is_absolute():
            extra_path = Path.cwd() / extra_path
        if extra_path.exists():
            extra_content = extra_path.read_text(encoding="utf-8").strip()
            if extra_content:
                prompt += (
                    "\n\n---\n\nAdditional notes (chart/level):\n\n"
                    + extra_content
                )
                print(f"[INFO] Included extra context from: {extra_path.name}")
        else:
            print(f"[WARN] Extra file not found: {args.extra}")

    model = args.model or OPENAI_CHATGPT_MODEL
    analysis, usage = openai_send(
        prompt, api_key, model=model,
        system_content=(
            "You are an expert stock trader and risk manager. You use Mark Minervini-style "
            "SEPA principles (trend, base, volume, breakout). Given a list of open positions "
            "with rule-based suggestions (HOLD, ADD, REDUCE, EXIT), give your own clear "
            "recommendation for each position: agree or disagree with the rule, your reasoning, "
            "and what to watch (e.g. key levels, volume, or catalysts). Be concise but actionable. "
            "When the user provides chart/level data (e.g. 50/200 DMA location, base highs/lows, "
            "volume trend), use it to give SEPA-style pivot/add points and 'must-hold' levels "
            "for each position; otherwise you may note what data would allow that."
        ),
    )
    if not analysis:
        print("[ERROR] Failed to get response from ChatGPT. Check API key and quota.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_latest = REPORTS_DIR / "position_suggestions_Chat_GPT.txt"
    out_ts = REPORTS_DIR / f"position_suggestions_Chat_GPT_{timestamp}.txt"

    header = [
        "=" * 80,
        "CHATGPT POSITION SUGGESTIONS",
        "=" * 80,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Model: {model}",
        f"Input: {latest.name}",
    ]
    if usage and (usage.get("total_tokens") is not None or usage.get("prompt_tokens") is not None):
        pt, ct, tot = usage.get("prompt_tokens"), usage.get("completion_tokens"), usage.get("total_tokens")
        if tot is not None:
            header.append(f"Tokens used: {tot:,} total (prompt: {pt or 0:,}, completion: {ct or 0:,})")
        else:
            header.append(f"Tokens used: prompt {pt or 0:,}, completion {ct or 0:,}")
    header.extend([
        "",
        "=" * 80,
        "CHATGPT RECOMMENDATIONS",
        "=" * 80,
        "",
    ])
    body = "\n".join(header) + analysis.strip() + "\n"

    for path in (out_latest, out_ts):
        try:
            path.write_text(body, encoding="utf-8")
            print(f"Report saved: {path}")
        except Exception as e:
            logger.warning("Could not save %s: %s", path, e)

    print("\n[OK] Done.")


if __name__ == "__main__":
    main()
