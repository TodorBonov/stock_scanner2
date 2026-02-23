"""
Pre-breakout view: filter and sort scan results for "setup ready, not yet broken out".
Used by 02_generate_full_report.py (PRE-BREAKOUT SETUPS section).
Config: pre_breakout_config.py only (no changes to config.py).
"""
from typing import Dict, List

from pre_breakout_config import (
    PRE_BREAKOUT_MAX_DISTANCE_PCT,
    PRE_BREAKOUT_MIN_GRADE,
    PRE_BREAKOUT_NEAR_PIVOT_PCT,
    PRE_BREAKOUT_REQUIRE_BASE,
    PRE_BREAKOUT_REQUIRE_NOT_BROKEN_OUT,
    _PRE_BREAKOUT_GRADE_ORDER,
)


def _grade_rank(grade: str) -> int:
    """Lower rank = better grade. Used to compare >= MIN_GRADE."""
    try:
        return _PRE_BREAKOUT_GRADE_ORDER.index(grade)
    except ValueError:
        return 999


def actionability_sort_key(r: Dict) -> tuple:
    """
    Sort key for best setups and pre-breakout list: tighter base, drier volume, closer to pivot, higher RS.
    Lower key = better setup. Shared by 02_generate_full_report (BEST SETUPS) and pre-breakout section.
    """
    bq = r.get("checklist", {}).get("base_quality", {}).get("details") or {}
    buy_sell = r.get("buy_sell_prices") or {}
    rs_details = r.get("checklist", {}).get("relative_strength", {}).get("details") or {}

    base_depth = bq.get("base_depth_pct", 99.0)
    vol_contract = bq.get("volume_contraction", 2.0)
    dist_buy = buy_sell.get("distance_to_buy_pct")
    dist_buy = abs(dist_buy) if dist_buy is not None else 999.0
    rs_rating = rs_details.get("rs_rating", 0)

    return (base_depth, vol_contract, dist_buy, -rs_rating)


# Alias for backward compatibility and clarity in pre-breakout context
pre_breakout_sort_key = actionability_sort_key


def get_pre_breakout_stocks(results: List[Dict]) -> List[Dict]:
    """
    Filter scan results to stocks that have a valid setup but have NOT yet broken out.
    Returns list sorted by setup quality (best first).

    Criteria (all must hold):
    - No "error" in result.
    - Grade >= PRE_BREAKOUT_MIN_GRADE (e.g. B or better).
    - Has pivot (buy_sell_prices.pivot_price or base_quality.details.base_high).
    - Breakout rules NOT passed (has not closed >= 2% above base high in last 5 days).
    - Distance to buy (below pivot) within PRE_BREAKOUT_MAX_DISTANCE_PCT (e.g. within 5% below pivot).
    - Optionally: require base_quality.details (PRE_BREAKOUT_REQUIRE_BASE).
    """
    min_rank = _grade_rank(PRE_BREAKOUT_MIN_GRADE)
    out = []
    for r in results:
        if "error" in r:
            continue
        grade = r.get("overall_grade", "F")
        if _grade_rank(grade) > min_rank:
            continue
        checklist = r.get("checklist", {})
        buy_sell = r.get("buy_sell_prices") or {}
        breakout = checklist.get("breakout_rules", {})
        base_quality = checklist.get("base_quality", {})

        if PRE_BREAKOUT_REQUIRE_BASE:
            details = base_quality.get("details") or {}
            if not details or details.get("base_high") is None:
                continue
        pivot = buy_sell.get("pivot_price") or (base_quality.get("details") or {}).get("base_high")
        if pivot is None:
            continue
        if PRE_BREAKOUT_REQUIRE_NOT_BROKEN_OUT and breakout.get("passed", False):
            continue
        dist = buy_sell.get("distance_to_buy_pct")
        if dist is None:
            continue
        # Pre-breakout: we want price below pivot, so distance_to_buy_pct < 0.
        # Include only if within MAX_DISTANCE below pivot (e.g. -5% to 0%).
        if dist > 0 or dist < -PRE_BREAKOUT_MAX_DISTANCE_PCT:
            continue
        # Optional: exclude bases older than N days (config.BASE_MAX_DAYS_OLD)
        try:
            from config import BASE_MAX_DAYS_OLD
            if BASE_MAX_DAYS_OLD > 0 and buy_sell.get("days_since_base_end") is not None:
                if buy_sell.get("days_since_base_end") > BASE_MAX_DAYS_OLD:
                    continue
        except ImportError:
            pass
        out.append(r)

    out.sort(key=pre_breakout_sort_key)
    return out
