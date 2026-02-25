"""
Minervini SEPA V2 – User-friendly report and CSV export.
Consumes final scan JSON only; no scoring or metric computation.
Pure Python, deterministic, no LLM.
"""
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from minervini_config_v2 import (
    REPORTS_DIR_V2,
    USER_REPORT_SUBDIR_V2,
    SEPA_USER_REPORT_PREFIX,
    SEPA_CSV_PREFIX,
    EXTENDED_DISTANCE_PCT,
    EXTENDED_RISK_WARNING_PCT,
    EARLY_TREND_SCORE_MIN,
    EARLY_TREND_SCORE_MAX,
    EARLY_RS_PERCENTILE_MIN,
    EARLY_RS_PERCENTILE_MAX,
    EARLY_DIST_TO_PIVOT_MIN_PCT,
    EARLY_DIST_TO_PIVOT_MAX_PCT,
    EARLY_MAX_ROWS,
    # For PART 3 – Score breakdown & config thresholds
    MIN_AVG_DOLLAR_VOLUME_20D,
    MIN_PRICE_THRESHOLD,
    MIN_PRIOR_RUN_PCT,
    PRIOR_RUN_LOOKBACK_TRADING_DAYS,
    TREND_PCT_ABOVE_200_TIER1,
    TREND_PCT_ABOVE_200_TIER2,
    TREND_PCT_ABOVE_200_TIER3,
    TREND_PCT_ABOVE_200_TIER4,
    WEIGHT_TREND_STRUCTURE,
    WEIGHT_BASE_QUALITY,
    WEIGHT_RELATIVE_STRENGTH,
    WEIGHT_VOLUME_SIGNATURE,
    WEIGHT_BREAKOUT_QUALITY,
    GRADE_A_PLUS_MIN_SCORE,
    GRADE_A_MIN_SCORE,
    GRADE_B_MIN_SCORE,
    GRADE_C_MIN_SCORE,
    MIN_RS_PERCENTILE_FOR_A_PLUS,
    MIN_RS_PERCENTILE_FOR_A,
    BASE_SCORE_DEPTH_ELITE_PCT,
    BASE_SCORE_DEPTH_GOOD_PCT,
    BASE_SCORE_PRIOR_RUN_BONUS,
    BASE_SCORE_PRIOR_RUN_PENALTY,
    BASE_SCORE_LENGTH_IDEAL_MIN_WEEKS,
    BASE_SCORE_LENGTH_IDEAL_MAX_WEEKS,
    BASE_SCORE_LENGTH_SHORT_PENALTY_WEEKS,
    BASE_SCORE_LENGTH_IDEAL_BONUS,
    BASE_SCORE_LENGTH_SHORT_PENALTY,
    BREAKOUT_SCORE_TIGHT_LOW_PCT,
    BREAKOUT_SCORE_TIGHT_HIGH_PCT,
    BREAKOUT_SCORE_NEAR_LOW_PCT,
    BREAKOUT_SCORE_NEAR_HIGH_PCT,
    VOLUME_SCORE_STRONG_CONTRACTION,
    VOLUME_SCORE_MODERATE_CONTRACTION,
)


def _safe_float(x, default: float = 0.0, round_to: Optional[int] = None) -> float:
    if x is None:
        return default
    try:
        v = float(x)
        return round(v, round_to) if round_to is not None else v
    except (TypeError, ValueError):
        return default


# Late-stage base: depth above this is flagged as important note (same as Risk Warnings)
LATE_STAGE_BASE_DEPTH_PCT = 20.0
# Low RS threshold for important note
LOW_RS_PERCENTILE_THRESHOLD = 70.0


def _status_line(r: Dict) -> str:
    """Status: Ready | Triggered | Extended | Developing."""
    grade = r.get("grade") or ""
    dist = _safe_float(r.get("breakout", {}).get("distance_to_pivot_pct"), default=0, round_to=2)
    in_breakout = r.get("breakout", {}).get("in_breakout", False)
    if -3 <= dist <= 0 and grade in ("A+", "A"):
        return "Ready - Tight base, strong RS, not extended."
    if in_breakout:
        return "Triggered"
    if dist > EXTENDED_DISTANCE_PCT:
        return "Extended"
    if grade == "B":
        return "Developing"
    return "Watch"


def _important_notes(r: Dict) -> List[str]:
    """Risk/info remarks for this stock: Extended, Late-stage base, Low RS, In breakout."""
    notes = []
    dist = _safe_float((r.get("breakout") or {}).get("distance_to_pivot_pct"))
    if dist > EXTENDED_RISK_WARNING_PCT:
        notes.append(f"Extended (>{EXTENDED_RISK_WARNING_PCT}% above pivot)")
    depth = _safe_float((r.get("base") or {}).get("depth_pct"))
    if depth > LATE_STAGE_BASE_DEPTH_PCT:
        notes.append(f"Late-stage base (>{LATE_STAGE_BASE_DEPTH_PCT:.0f}% depth)")
    rs_pct = (r.get("relative_strength") or {}).get("rs_percentile")
    if rs_pct is not None and _safe_float(rs_pct) < LOW_RS_PERCENTILE_THRESHOLD:
        notes.append(f"Low RS percentile (<{LOW_RS_PERCENTILE_THRESHOLD:.0f})")
    if r.get("breakout", {}).get("in_breakout", False):
        notes.append("In breakout (already triggered)")
    return notes


def _important_note_short(r: Dict) -> str:
    """Short note string for ranked tables: Ext, Late, LowRS, BO or —."""
    notes = _important_notes(r)
    if not notes:
        return "—"
    abbr = []
    for n in notes:
        if "Extended" in n:
            abbr.append("Ext")
        elif "Late-stage" in n:
            abbr.append("Late")
        elif "Low RS" in n:
            abbr.append("LowRS")
        elif "In breakout" in n:
            abbr.append("BO")
    return ",".join(abbr) if abbr else "—"


def _short_summary_block(r: Dict) -> List[str]:
    """Short summary for one stock (2–4 lines)."""
    ticker = r.get("ticker", "?")
    grade = r.get("grade", "?")
    score = _safe_float(r.get("composite_score"), round_to=1)
    base = r.get("base") or {}
    base_type = base.get("type", "—")
    depth = _safe_float(base.get("depth_pct"), round_to=1)
    br = r.get("breakout") or {}
    pivot = _safe_float(br.get("pivot_price"), round_to=2) if br.get("pivot_price") is not None else None
    pivot_src = br.get("pivot_source") or ""
    dist = _safe_float(br.get("distance_to_pivot_pct"), round_to=1)
    risk = r.get("risk") or {}
    stop = _safe_float(risk.get("stop_price"), round_to=2) if risk.get("stop_price") is not None else None
    rr = risk.get("reward_to_risk")
    rr_str = f"{_safe_float(rr, round_to=1)}" if rr is not None else "—"
    status = _status_line(r)
    lines = [f"  {ticker}  [{grade}] Score {score}  |  Base: {base_type} ({depth}% deep)"]
    pivot_line = f"    Pivot: {pivot}" + (f" ({pivot_src})" if pivot_src else "") + f"  Dist: {dist}%  |  Stop: {stop}  R/R: {rr_str}  |  {status}"
    lines.append(pivot_line)
    return lines


def _detailed_block(r: Dict) -> List[str]:
    """Detailed info block for one stock: grade, composite, score calculation with component brackets, then full metrics."""
    ticker = r.get("ticker", "?")
    composite = _safe_float(r.get("composite_score"), round_to=1)
    t = _safe_float(r.get("trend_score"), round_to=1)
    b = _safe_float(r.get("base_score"), round_to=1)
    rs = _safe_float(r.get("rs_score"), round_to=1)
    v = _safe_float(r.get("volume_score"), round_to=1)
    br = _safe_float(r.get("breakout_score"), round_to=1)
    dist = _safe_float((r.get("breakout") or {}).get("distance_to_pivot_pct"))
    rs_pct = (r.get("relative_strength") or {}).get("rs_percentile")

    lines = [
        f"----- {ticker} -----",
        f"Grade: {r.get('grade', '?')}",
    ]
    important = _important_notes(r)
    if important:
        lines.append(f"Important note: {'; '.join(important)}")
    lines.append(f"Composite Score: {composite}")
    lines.extend([
        f"  Score calculation: {WEIGHT_TREND_STRUCTURE}*{t} + {WEIGHT_BASE_QUALITY}*{b} + {WEIGHT_RELATIVE_STRENGTH}*{rs} + {WEIGHT_VOLUME_SIGNATURE}*{v} + {WEIGHT_BREAKOUT_QUALITY}*{br} = {composite}",
        f"  Trend: {t}   ({_trend_band_description(t)})",
        f"  Base: {b}    ({_base_band_description(r)})",
        f"  RS: {rs}     (rs_percentile 0-100; this stock {_safe_float(rs_pct, round_to=1) if rs_pct is not None else '—'})",
        f"  Volume: {v}  ({_volume_band_description(v)})",
        f"  Breakout: {br} ({_breakout_band_description(br, dist)})",
    ])
    base = r.get("base") or {}
    lines.append(f"Base: {base.get('type', '?')} ({_safe_float(base.get('length_weeks'), round_to=1)} weeks, {_safe_float(base.get('depth_pct'), round_to=1)}% deep)")
    prior = base.get("prior_run_pct")
    lines.append(f"Prior Run: {f'+{_safe_float(prior, round_to=0)}%' if prior is not None else '—'}")
    rs_block = r.get("relative_strength") or {}
    pct = rs_block.get("rs_percentile")
    lines.append(f"RS Percentile: {_safe_float(pct, round_to=0) if pct is not None else '—'}")
    lines.append(f"RSI: {_safe_float(rs_block.get('rsi_14'), round_to=0) if rs_block.get('rsi_14') is not None else '—'}")
    br_block = r.get("breakout") or {}
    pivot_val = br_block.get("pivot_price")
    pivot_src = br_block.get("pivot_source") or ""
    pivot_str = f"{_safe_float(pivot_val, round_to=2)}" + (f"  (source: {pivot_src})" if pivot_src else "") if pivot_val is not None else "—"
    lines.append(f"Pivot: {pivot_str}")
    lines.append(f"Distance to Pivot: {_safe_float(br_block.get('distance_to_pivot_pct'), round_to=1)}%")
    risk = r.get("risk") or {}
    stop_val = risk.get("stop_price")
    stop_str = f"{_safe_float(stop_val, round_to=2)} ({risk.get('stop_method', 'fixed')} method)" if stop_val is not None else "—"
    lines.append(f"Stop: {stop_str}")
    rr = risk.get("reward_to_risk")
    lines.append(f"Reward/Risk: {_safe_float(rr, round_to=1) if rr is not None else '—'}")
    pr = r.get("power_rank")
    if pr is not None:
        lines.append(f"Power Rank: {_safe_float(pr, round_to=1)}")
    lines.append(f"Status: {_status_line(r)}")
    return lines


def _config_thresholds_lines() -> List[str]:
    """Config thresholds summary for PART 3 (from minervini_config_v2)."""
    return [
        "Eligibility:",
        f"  MIN_AVG_DOLLAR_VOLUME_20D = {MIN_AVG_DOLLAR_VOLUME_20D:,.0f}  MIN_PRICE_THRESHOLD = {MIN_PRICE_THRESHOLD}",
        f"  MIN_PRIOR_RUN_PCT = {MIN_PRIOR_RUN_PCT}%  PRIOR_RUN_LOOKBACK_TRADING_DAYS = {PRIOR_RUN_LOOKBACK_TRADING_DAYS}",
        "",
        "Trend score (0–100 by % above 200 SMA):",
        f"  ≥{TREND_PCT_ABOVE_200_TIER1}% → 100  {TREND_PCT_ABOVE_200_TIER2}–{TREND_PCT_ABOVE_200_TIER1}% → 70  "
        f"{TREND_PCT_ABOVE_200_TIER3}–{TREND_PCT_ABOVE_200_TIER2}% → 40  {TREND_PCT_ABOVE_200_TIER4}–{TREND_PCT_ABOVE_200_TIER3}% → 15  <{TREND_PCT_ABOVE_200_TIER4}% → 0",
        "",
        "Composite weights:",
        f"  WEIGHT_TREND_STRUCTURE = {WEIGHT_TREND_STRUCTURE}  WEIGHT_BASE_QUALITY = {WEIGHT_BASE_QUALITY}  "
        f"WEIGHT_RELATIVE_STRENGTH = {WEIGHT_RELATIVE_STRENGTH}  WEIGHT_VOLUME_SIGNATURE = {WEIGHT_VOLUME_SIGNATURE}  WEIGHT_BREAKOUT_QUALITY = {WEIGHT_BREAKOUT_QUALITY}",
        "",
        "Grade bands (composite score):",
        f"  ≥{GRADE_A_PLUS_MIN_SCORE} → A+  ≥{GRADE_A_MIN_SCORE} → A  ≥{GRADE_B_MIN_SCORE} → B  ≥{GRADE_C_MIN_SCORE} → C  <{GRADE_C_MIN_SCORE} → REJECT",
        f"  MIN_RS_PERCENTILE_FOR_A_PLUS = {MIN_RS_PERCENTILE_FOR_A_PLUS}  MIN_RS_PERCENTILE_FOR_A = {MIN_RS_PERCENTILE_FOR_A} (downgrade if below)",
        "",
        "Base score (additions/penalties):",
        f"  depth ≤{BASE_SCORE_DEPTH_ELITE_PCT}% → +10  ≤{BASE_SCORE_DEPTH_GOOD_PCT}% → +5  prior_run ≥{MIN_PRIOR_RUN_PCT}% → +{BASE_SCORE_PRIOR_RUN_BONUS}  else → {BASE_SCORE_PRIOR_RUN_PENALTY}",
        f"  length {BASE_SCORE_LENGTH_IDEAL_MIN_WEEKS}–{BASE_SCORE_LENGTH_IDEAL_MAX_WEEKS} wks → +{BASE_SCORE_LENGTH_IDEAL_BONUS}  <{BASE_SCORE_LENGTH_SHORT_PENALTY_WEEKS} wks → {BASE_SCORE_LENGTH_SHORT_PENALTY}",
        "",
        "Breakout score (pre-breakout by distance to pivot):",
        f"  dist [{BREAKOUT_SCORE_TIGHT_LOW_PCT}%, {BREAKOUT_SCORE_TIGHT_HIGH_PCT}%] → 80  "
        f"[{BREAKOUT_SCORE_NEAR_LOW_PCT}%, {BREAKOUT_SCORE_NEAR_HIGH_PCT}%) → 60  >{EXTENDED_DISTANCE_PCT}% → 30  else 50  (in breakout → 100)",
        "",
        "Volume score (base contraction):",
        f"  contraction <{VOLUME_SCORE_STRONG_CONTRACTION} → 100  <{VOLUME_SCORE_MODERATE_CONTRACTION} → 70  else 50 (when passed); failed → 0/50/70 by band",
        "",
    ]


def _trend_band_description(score: float) -> str:
    if score >= 100:
        return f">={TREND_PCT_ABOVE_200_TIER1}% above 200 SMA"
    if score >= 70:
        return f"{TREND_PCT_ABOVE_200_TIER2}-{TREND_PCT_ABOVE_200_TIER1}% above 200 SMA"
    if score >= 40:
        return f"{TREND_PCT_ABOVE_200_TIER3}-{TREND_PCT_ABOVE_200_TIER2}% above 200 SMA"
    if score >= 15:
        return f"{TREND_PCT_ABOVE_200_TIER4}-{TREND_PCT_ABOVE_200_TIER3}% above 200 SMA"
    return "below 200 SMA"


def _breakout_band_description(score: float, dist: Optional[float]) -> str:
    if score >= 100:
        return "in breakout (passed)"
    if score >= 80:
        return f"dist {dist}% in [{BREAKOUT_SCORE_TIGHT_LOW_PCT}%, {BREAKOUT_SCORE_TIGHT_HIGH_PCT}%] -> 80"
    if score >= 60:
        return f"dist {dist}% in [{BREAKOUT_SCORE_NEAR_LOW_PCT}%, {BREAKOUT_SCORE_NEAR_HIGH_PCT}%) -> 60"
    if score <= 30:
        return f"dist {dist}% > {EXTENDED_DISTANCE_PCT}% (extended) -> 30"
    return f"dist {dist}% -> 50"


def _volume_band_description(score: float) -> str:
    if score >= 100:
        return f"contraction <{VOLUME_SCORE_STRONG_CONTRACTION} -> 100"
    if score >= 70:
        return f"contraction <{VOLUME_SCORE_MODERATE_CONTRACTION} -> 70"
    if score >= 50:
        return f"contraction >={VOLUME_SCORE_MODERATE_CONTRACTION} or other -> 50"
    return "failed / 0"


def _base_band_description(r: Dict) -> str:
    """One-line explanation of how base score was derived (depth/prior/length rules → score)."""
    base = r.get("base") or {}
    depth = base.get("depth_pct")
    prior = base.get("prior_run_pct")
    length_w = base.get("length_weeks")
    b = _safe_float(r.get("base_score"), round_to=0)
    parts = []
    if depth is not None:
        parts.append(f"depth {_safe_float(depth, round_to=1)}% (<={BASE_SCORE_DEPTH_ELITE_PCT} +10, <={BASE_SCORE_DEPTH_GOOD_PCT} +5)")
    if prior is not None:
        parts.append(f"prior {_safe_float(prior, round_to=0)}% (>={MIN_PRIOR_RUN_PCT} +{BASE_SCORE_PRIOR_RUN_BONUS} else {BASE_SCORE_PRIOR_RUN_PENALTY})")
    if length_w is not None:
        parts.append(f"length {length_w} wks ({BASE_SCORE_LENGTH_IDEAL_MIN_WEEKS}-{BASE_SCORE_LENGTH_IDEAL_MAX_WEEKS} +{BASE_SCORE_LENGTH_IDEAL_BONUS}, <{BASE_SCORE_LENGTH_SHORT_PENALTY_WEEKS} {BASE_SCORE_LENGTH_SHORT_PENALTY})")
    parts.append(f"80+bonuses = {b}")
    return "; ".join(parts)


def _score_breakdown_block(r: Dict) -> List[str]:
    """Per-stock score derivation for PART 3: formula + component bands."""
    ticker = r.get("ticker", "?")
    grade = r.get("grade", "?")
    t = _safe_float(r.get("trend_score"), round_to=1)
    b = _safe_float(r.get("base_score"), round_to=1)
    rs = _safe_float(r.get("rs_score"), round_to=1)
    v = _safe_float(r.get("volume_score"), round_to=1)
    br = _safe_float(r.get("breakout_score"), round_to=1)
    composite = _safe_float(r.get("composite_score"), round_to=1)
    base = r.get("base") or {}
    depth = _safe_float(base.get("depth_pct"))
    prior = base.get("prior_run_pct")
    length_w = base.get("length_weeks")
    dist = _safe_float((r.get("breakout") or {}).get("distance_to_pivot_pct"))
    rs_pct = (r.get("relative_strength") or {}).get("rs_percentile")
    prior_str = f"{prior}%" if prior is not None else "—"
    length_str = f"{length_w}" if length_w is not None else "—"
    lines = [
        f"--- {ticker} ({grade}) ---",
        f"  Composite = {WEIGHT_TREND_STRUCTURE}*{t} + {WEIGHT_BASE_QUALITY}*{b} + {WEIGHT_RELATIVE_STRENGTH}*{rs} + {WEIGHT_VOLUME_SIGNATURE}*{v} + {WEIGHT_BREAKOUT_QUALITY}*{br} = {composite}",
        f"  Trend: {t}  ({_trend_band_description(t)})",
        f"  Base: {b}  (depth {depth}%, prior_run {prior_str}, length {length_str} wks; depth ≤{BASE_SCORE_DEPTH_ELITE_PCT} +10, ≤{BASE_SCORE_DEPTH_GOOD_PCT} +5, prior ≥{MIN_PRIOR_RUN_PCT} +{BASE_SCORE_PRIOR_RUN_BONUS}, length {BASE_SCORE_LENGTH_IDEAL_MIN_WEEKS}-{BASE_SCORE_LENGTH_IDEAL_MAX_WEEKS} +{BASE_SCORE_LENGTH_IDEAL_BONUS})",
        f"  RS: {rs}  (rs_percentile = {rs_pct})",
        f"  Volume: {v}  ({_volume_band_description(v)})",
        f"  Breakout: {br}  ({_breakout_band_description(br, dist)})",
    ]
    return lines


def generate_user_friendly_report(
    scan_results: List[Dict],
    data_timestamp: Optional[str] = None,
    report_run_timestamp: Optional[str] = None,
) -> str:
    """
    PART 8 — User-friendly final report in three parts.
    Part 1: Rank table + combined summary per stock (short + detailed in one block).
    Part 3: Score breakdown with config thresholds (how composite was reached).
    Consumes final JSON only; no metric computation.
    data_timestamp: when data was taken from Yahoo (e.g. from prepared metadata).
    report_run_timestamp: when this report was generated (default: now).
    """
    if report_run_timestamp is None:
        report_run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Sort by composite_score descending (eligible first, then by score)
    sorted_results = sorted(
        [r for r in scan_results if isinstance(r, dict)],
        key=lambda x: (not x.get("eligible", True), -_safe_float(x.get("composite_score"), default=0)),
    )
    eligible = [r for r in sorted_results if r.get("eligible", False)]
    actionable = [r for r in eligible if r.get("grade") in ("A+", "A")]
    watchlist = [r for r in eligible if r.get("grade") == "B"]

    rs_percentiles = [
        _safe_float(r.get("relative_strength", {}).get("rs_percentile"))
        for r in eligible
        if r.get("relative_strength", {}).get("rs_percentile") is not None
    ]
    avg_rs_pct = sum(rs_percentiles) / len(rs_percentiles) if rs_percentiles else 0
    in_breakout_count = sum(1 for r in eligible if r.get("breakout", {}).get("in_breakout"))

    lines = []
    lines.append(f"Report run: {report_run_timestamp}")
    if data_timestamp:
        lines.append(f"Data as of (Yahoo): {data_timestamp}")
    lines.append("")

    # ========== PART 1: Rank table + detailed per stock ==========
    lines.append("=" * 60)
    lines.append("PART 1 — RANK TABLE & DETAILED (PER STOCK)")
    lines.append("=" * 60)
    lines.append("")
    lines.append("----- Executive Summary -----")
    lines.append(f"Universe: {len(scan_results)} stocks")
    lines.append(f"Eligible Stage 2: {len(eligible)}")
    lines.append(f"A+/A candidates: {len(actionable)}")
    lines.append(f"B candidates: {len(watchlist)}")
    lines.append(f"In Breakout Now: {in_breakout_count}")
    lines.append(f"Average RS Percentile (eligible): {round(avg_rs_pct, 0)}")
    lines.append("")

    lines.append("----- Ranked Table -----")
    header = "| Rank | Ticker | Grade | Score | Base Type | Depth % | RS %ile | Dist to Pivot | R/R | Stop | Note |"
    lines.append(header)
    lines.append("|" + "---|" * 11)
    for i, r in enumerate(sorted_results[:80], 1):
        ticker = r.get("ticker", "?")
        grade = r.get("grade", "?")
        score = _safe_float(r.get("composite_score"), round_to=1)
        base_type = (r.get("base") or {}).get("type", "—")
        depth = _safe_float((r.get("base") or {}).get("depth_pct"), round_to=1)
        rs_pct = (r.get("relative_strength") or {}).get("rs_percentile")
        rs_str = f"{_safe_float(rs_pct, round_to=1)}" if rs_pct is not None else "—"
        dist = _safe_float((r.get("breakout") or {}).get("distance_to_pivot_pct"), round_to=1)
        rr = (r.get("risk") or {}).get("reward_to_risk")
        rr_str = f"{_safe_float(rr, round_to=1)}" if rr is not None else "—"
        stop = (r.get("risk") or {}).get("stop_price")
        stop_str = f"{_safe_float(stop, round_to=2)}" if stop is not None else "—"
        note_str = _important_note_short(r)
        lines.append(f"| {i} | {ticker} | {grade} | {score} | {base_type} | {depth} | {rs_str} | {dist} | {rr_str} | {stop_str} | {note_str} |")
    lines.append("")

    lines.append("----- Detailed (per stock) -----")
    for r in sorted_results[:80]:
        lines.extend(_detailed_block(r))
        lines.append("")
    lines.append("")

    # ========== Early candidates (before extension) ==========
    # Same scan results; filter by thresholds, sort by grade (A+ then A then B) then composite score
    def _grade_sort_key(g: str) -> int:
        if g == "A+": return 0
        if g == "A": return 1
        if g == "B": return 2
        return 3

    early = []
    for r in eligible:
        if r.get("grade") not in ("A+", "A", "B"):
            continue
        trend_s = _safe_float(r.get("trend_score"), default=0)
        rs_pct = _safe_float((r.get("relative_strength") or {}).get("rs_percentile"), default=0)
        dist = _safe_float((r.get("breakout") or {}).get("distance_to_pivot_pct"), default=-999)
        if not (EARLY_TREND_SCORE_MIN <= trend_s <= EARLY_TREND_SCORE_MAX):
            continue
        if not (EARLY_RS_PERCENTILE_MIN <= rs_pct <= EARLY_RS_PERCENTILE_MAX):
            continue
        if not (EARLY_DIST_TO_PIVOT_MIN_PCT <= dist <= EARLY_DIST_TO_PIVOT_MAX_PCT):
            continue
        early.append(r)
    early_sorted = sorted(
        early,
        key=lambda x: (
            _grade_sort_key(x.get("grade") or ""),
            -_safe_float(x.get("composite_score"), default=0),
            -_safe_float((x.get("breakout") or {}).get("distance_to_pivot_pct")),
            x.get("ticker") or "",
        ),
    )
    lines.append("=" * 60)
    lines.append("EARLY CANDIDATES (before extension)")
    lines.append("=" * 60)
    lines.append("")
    lines.append("Stocks that are not yet extended (trend 40-70), building RS (50-80 %ile),")
    lines.append("and near pivot (-5% to 0%). Sorted by grade (A+ then A then B), then composite score.")
    lines.append("")
    lines.append("----- Early candidates table -----")
    header_early = "| Rank | Ticker | Grade | Score | Trend | RS %ile | Dist to Pivot | Base Type | Note |"
    lines.append(header_early)
    lines.append("|" + "---|" * 9)
    for i, r in enumerate(early_sorted[:EARLY_MAX_ROWS], 1):
        ticker = r.get("ticker", "?")
        grade = r.get("grade", "?")
        score = _safe_float(r.get("composite_score"), round_to=1)
        trend_s = _safe_float(r.get("trend_score"), round_to=0)
        rs_pct_val = (r.get("relative_strength") or {}).get("rs_percentile")
        rs_str = f"{_safe_float(rs_pct_val, round_to=1)}" if rs_pct_val is not None else "—"
        dist = _safe_float((r.get("breakout") or {}).get("distance_to_pivot_pct"), round_to=1)
        base_type = (r.get("base") or {}).get("type", "—")
        note_str = _important_note_short(r)
        lines.append(f"| {i} | {ticker} | {grade} | {score} | {trend_s} | {rs_str} | {dist} | {base_type} | {note_str} |")
    lines.append("")
    if not early_sorted:
        lines.append("  (none match the early thresholds this run)")
    else:
        lines.append("----- Early candidates detailed (per stock) -----")
        for r in early_sorted[:EARLY_MAX_ROWS]:
            lines.extend(_detailed_block(r))
            lines.append("")
    lines.append("")

    # Risk Warnings (summary; each stock also has Important note in its block)
    lines.append("----- Risk Warnings (summary) -----")
    extended = [r for r in eligible if _safe_float((r.get("breakout") or {}).get("distance_to_pivot_pct")) > EXTENDED_RISK_WARNING_PCT]
    late_base = [r for r in eligible if _safe_float((r.get("base") or {}).get("depth_pct")) > LATE_STAGE_BASE_DEPTH_PCT]
    low_rs = [r for r in eligible if (r.get("relative_strength") or {}).get("rs_percentile") is not None and _safe_float((r.get("relative_strength") or {}).get("rs_percentile")) < LOW_RS_PERCENTILE_THRESHOLD]
    for r in extended:
        lines.append(f"  Extended: {r.get('ticker')} (>{EXTENDED_RISK_WARNING_PCT}% above pivot)")
    for r in late_base:
        lines.append(f"  Late-stage base: {r.get('ticker')} (>{LATE_STAGE_BASE_DEPTH_PCT:.0f}% depth)")
    for r in low_rs:
        pct = (r.get("relative_strength") or {}).get("rs_percentile")
        lines.append(f"  Low RS percentile: {r.get('ticker')} ({pct})")
    if not (extended or late_base or low_rs):
        lines.append("  None")
    lines.append("")

    # ========== PART 3: Score breakdown & config thresholds ==========
    lines.append("=" * 60)
    lines.append("PART 3 — SCORE BREAKDOWN & CONFIG THRESHOLDS")
    lines.append("=" * 60)
    lines.append("")
    lines.append("How the composite score is computed: composite = "
                 f"{WEIGHT_TREND_STRUCTURE}*Trend + {WEIGHT_BASE_QUALITY}*Base + {WEIGHT_RELATIVE_STRENGTH}*RS + "
                 f"{WEIGHT_VOLUME_SIGNATURE}*Vol + {WEIGHT_BREAKOUT_QUALITY}*Breakout (each component 0–100).")
    lines.append("")
    lines.append("----- Config thresholds (minervini_config_v2) -----")
    lines.extend(_config_thresholds_lines())
    lines.append("----- Per-stock score derivation (top 80) -----")
    for r in sorted_results[:80]:
        lines.extend(_score_breakdown_block(r))
        lines.append("")
    lines.append("===== END SEPA SCAN =====")

    return "\n".join(lines)


def export_scan_summary_to_csv(scan_results: List[Dict], filepath: Optional[Path] = None) -> str:
    """
    PART 9 — CSV export.
    Columns: ticker, grade, composite_score, base_type, depth_pct, rs_percentile,
    distance_to_pivot_pct, reward_to_risk, stop_price
    """
    if filepath is None:
        filepath = REPORTS_DIR_V2 / "v2" / f"{SEPA_CSV_PREFIX}{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for r in scan_results:
        if not isinstance(r, dict):
            continue
        base = r.get("base") or {}
        br = r.get("breakout") or {}
        risk = r.get("risk") or {}
        rs = r.get("relative_strength") or {}
        pr = r.get("power_rank")
        rows.append({
            "ticker": r.get("ticker", ""),
            "grade": r.get("grade", ""),
            "composite_score": _safe_float(r.get("composite_score"), round_to=2),
            "base_type": base.get("type", ""),
            "depth_pct": _safe_float(base.get("depth_pct"), round_to=2),
            "pivot_source": (r.get("breakout") or {}).get("pivot_source", ""),
            "rs_percentile": _safe_float(rs.get("rs_percentile"), round_to=2) if rs.get("rs_percentile") is not None else "",
            "power_rank": _safe_float(pr, round_to=2) if pr is not None else "",
            "distance_to_pivot_pct": _safe_float(br.get("distance_to_pivot_pct"), round_to=2),
            "reward_to_risk": _safe_float(risk.get("reward_to_risk"), round_to=2) if risk.get("reward_to_risk") is not None else "",
            "stop_price": _safe_float(risk.get("stop_price"), round_to=2) if risk.get("stop_price") is not None else "",
        })

    import csv
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        if not rows:
            f.write("ticker,grade,composite_score,base_type,depth_pct,pivot_source,rs_percentile,power_rank,distance_to_pivot_pct,reward_to_risk,stop_price\n")
        else:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    return str(filepath)
