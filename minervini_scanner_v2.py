"""
Minervini SEPA Scanner V2 – Deterministic quant engine.
Separates structural eligibility from quality scoring; weighted composite score;
prior-run requirement; RS percentile; base-type classification; ATR stop option.
Produces structured JSON only. No LLM; all calculations pure Python.
Does NOT modify the original MinerviniScanner.
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from data_provider import StockDataProvider
from logger_config import get_logger
from minervini_scanner import MinerviniScanner
from config import (
    SMA_200_PERIOD, MIN_DATA_DAYS,
    BASE_LENGTH_MIN_WEEKS, BASE_LENGTH_MAX_WEEKS, BASE_DEPTH_MAX_PCT,
    RSI_PERIOD, BUY_PRICE_BUFFER_PCT, PIVOT_CLEARANCE_PCT,
    STOP_LOSS_PCT, USE_ATR_STOP, ATR_PERIOD, ATR_STOP_MULTIPLIER,
    BASE_LOOKBACK_DAYS,
    MIN_AVG_DOLLAR_VOLUME_20D, MIN_PRICE_THRESHOLD,
    MIN_PRIOR_RUN_PCT, PRIOR_RUN_LOOKBACK_TRADING_DAYS,
    PRIOR_RUN_REQUIRED_FOR_ELIGIBILITY,
    RS_3M_LOOKBACK_DAYS,
    BASE_TYPE_FLAT_MAX_DEPTH_PCT, BASE_TYPE_HIGH_TIGHT_PRIOR_RUN_PCT,
    BASE_TYPE_HIGH_TIGHT_MAX_DEPTH_PCT, BASE_TYPE_HIGH_TIGHT_MAX_WEEKS,
    PIVOT_SPIKE_FILTER_ENABLED, PIVOT_SPIKE_STD_MULTIPLIER,
    PIVOT_IGNORE_SPIKE_WITHIN_LAST_N_DAYS, PIVOT_HANDLE_DAYS,
    TREND_PCT_ABOVE_200_TIER1, TREND_PCT_ABOVE_200_TIER2,
    TREND_PCT_ABOVE_200_TIER3, TREND_PCT_ABOVE_200_TIER4,
    BASE_BONUS_RANGE_CONTRACTION_LAST_2W, BASE_BONUS_WEEKLY_CLOSES_UPPER_40,
    BASE_RANGE_CONTRACTION_RATIO_MAX, POWER_RANK_PRIOR_RUN_CAP,
    WEIGHT_TREND_STRUCTURE, WEIGHT_BASE_QUALITY, WEIGHT_RELATIVE_STRENGTH,
    WEIGHT_VOLUME_SIGNATURE, WEIGHT_BREAKOUT_QUALITY,
    GRADE_A_PLUS_MIN_SCORE, GRADE_A_MIN_SCORE, GRADE_B_MIN_SCORE, GRADE_C_MIN_SCORE,
    MIN_RS_PERCENTILE_FOR_A_PLUS, MIN_RS_PERCENTILE_FOR_A,
    BASE_SCORE_LENGTH_IDEAL_MIN_WEEKS, BASE_SCORE_LENGTH_IDEAL_MAX_WEEKS,
    BASE_SCORE_LENGTH_SHORT_PENALTY_WEEKS,
    BASE_SCORE_LENGTH_IDEAL_BONUS, BASE_SCORE_LENGTH_SHORT_PENALTY,
    USE_ATR_STOP_V2, ATR_PERIOD_V2, ATR_STOP_MULTIPLIER_V2,
    ATR_STOP_LOWEST_LOW_DAYS,
    EXTENDED_DISTANCE_PCT,
    BREAKOUT_SCORE_TIGHT_LOW_PCT, BREAKOUT_SCORE_TIGHT_HIGH_PCT,
    BREAKOUT_SCORE_NEAR_LOW_PCT, BREAKOUT_SCORE_NEAR_HIGH_PCT,
    BASE_SCORE_DEPTH_ELITE_PCT, BASE_SCORE_DEPTH_GOOD_PCT,
    BASE_SCORE_PRIOR_RUN_BONUS, BASE_SCORE_PRIOR_RUN_PENALTY,
    VOLUME_SCORE_STRONG_CONTRACTION, VOLUME_SCORE_MODERATE_CONTRACTION,
    BASE_LAST_N_DAYS_RANGE_CONTRACTION,
)

logger = get_logger(__name__)


def _percentile_rank(value: float, universe_values: List[float]) -> float:
    """Compute percentile rank of value in universe (0-100). Strict: (count strictly less) / n * 100."""
    if not universe_values or len(universe_values) == 0:
        return 50.0
    arr = np.asarray(universe_values, dtype=float)
    n = len(arr)
    count_below = np.sum(arr < value)
    return float(count_below) / n * 100.0


def _base_quality_extras(base_info: Optional[Dict]) -> Tuple[bool, bool]:
    """
    Elite base bonuses: (range_contraction_ok, weekly_closes_upper_40_ok).
    +10 each in base score if True.
    """
    if not base_info or "data" not in base_info:
        return False, False
    base_data = base_info["data"]
    if base_data.empty or len(base_data) < 5:
        return False, False
    base_high = float(base_data["High"].max())
    base_low = float(base_data["Low"].min())
    base_range = base_high - base_low
    if base_range <= 0:
        return False, False

    # Last N trading days of base (e.g. ~2 weeks): range contraction
    last_2w = base_data.tail(BASE_LAST_N_DAYS_RANGE_CONTRACTION)
    last_2w_range = float(last_2w["High"].max() - last_2w["Low"].min())
    range_contraction_ok = (last_2w_range / base_range) <= BASE_RANGE_CONTRACTION_RATIO_MAX

    # Last 2 weekly closes in upper 40% of base range (close >= base_low + 0.6 * base_range)
    upper_40_bound = base_low + 0.6 * base_range
    try:
        if isinstance(base_data.index, pd.DatetimeIndex):
            weekly = base_data["Close"].resample("W").last().dropna()
            last_2_weeks = weekly.tail(2)
        else:
            # No datetime index: use last 10 days, treat 5th-from-end and last as "2 weeks"
            closes = base_data["Close"]
            if len(closes) >= 5:
                last_2_weeks = closes.iloc[[-5, -1]]
            else:
                last_2_weeks = pd.Series(dtype=float)
    except Exception:
        last_2_weeks = pd.Series(dtype=float)
    if len(last_2_weeks) < 2:
        weekly_closes_upper_ok = False
    else:
        weekly_closes_upper_ok = bool(
            (last_2_weeks >= upper_40_bound).all()
        )
    return range_contraction_ok, weekly_closes_upper_ok


def _compute_prior_run(hist: pd.DataFrame, base_info: Optional[Dict]) -> Tuple[Optional[float], Optional[float]]:
    """
    prior_run_pct = (base_high - lowest_low_3m_before_base) / lowest_low_3m_before_base * 100.
    Returns (prior_run_pct, lowest_low_3m_before_base).
    """
    if not base_info or "data" not in base_info or "start_date" not in base_info:
        return None, None
    base_high = float(base_info["data"]["High"].max())
    base_start = base_info["start_date"]
    try:
        mask = hist.index < base_start
        before_base = hist.loc[mask].tail(PRIOR_RUN_LOOKBACK_TRADING_DAYS)
    except Exception:
        before_base = pd.DataFrame()
    if before_base.empty or len(before_base) < 5:
        return None, None
    lowest = float(before_base["Low"].min())
    if lowest <= 0:
        return None, None
    prior_run_pct = (base_high - lowest) / lowest * 100.0
    return prior_run_pct, lowest


class MinerviniScannerV2(MinerviniScanner):
    """
    V2 Scanner: structural eligibility, composite scoring, prior run, RS percentile,
    base type, ATR stop. Outputs deterministic JSON only.
    """

    def _check_structural_eligibility(self, hist: pd.DataFrame, base_info: Optional[Dict]) -> Dict:
        """
        PART 1 — Structural eligibility (must pass all).
        Returns: { "eligible": bool, "reasons": [], "details": { stage_2, has_valid_base, liquidity_ok, price_threshold_ok, prior_run_ok } }
        """
        reasons = []
        details = {"stage_2": False, "has_valid_base": False, "liquidity_ok": False, "price_threshold_ok": False, "prior_run_ok": True}

        # Trend & Structure (reuse parent; stock_info not required for pass/fail)
        trend = self._check_trend_structure(hist, {})
        details["stage_2"] = trend.get("passed", False)
        if not details["stage_2"]:
            reasons.extend(trend.get("failures", [])[:3])

        # Valid base
        details["has_valid_base"] = base_info is not None and base_info.get("length_weeks") is not None
        if not details["has_valid_base"]:
            reasons.append("No valid base identified")

        # Prior run (structural gate when PRIOR_RUN_REQUIRED_FOR_ELIGIBILITY)
        prior_run_pct, _ = _compute_prior_run(hist, base_info)
        if PRIOR_RUN_REQUIRED_FOR_ELIGIBILITY and prior_run_pct is not None and prior_run_pct < MIN_PRIOR_RUN_PCT:
            details["prior_run_ok"] = False
            reasons.append(f"Prior run {prior_run_pct:.1f}% < {MIN_PRIOR_RUN_PCT}%")
        else:
            details["prior_run_ok"] = True

        # Liquidity: avg dollar volume (20d) > threshold
        if len(hist) >= 20:
            last_20 = hist.tail(20)
            avg_dollar_vol = (last_20["Close"] * last_20["Volume"]).mean()
            details["liquidity_ok"] = float(avg_dollar_vol) >= MIN_AVG_DOLLAR_VOLUME_20D
            if not details["liquidity_ok"]:
                reasons.append(f"Avg 20d dollar volume ${avg_dollar_vol:,.0f} < ${MIN_AVG_DOLLAR_VOLUME_20D:,.0f}")
        else:
            reasons.append("Insufficient data for liquidity")

        # Price threshold
        current_price = float(hist["Close"].iloc[-1])
        details["price_threshold_ok"] = current_price >= MIN_PRICE_THRESHOLD
        if not details["price_threshold_ok"]:
            reasons.append(f"Price ${current_price:.2f} < ${MIN_PRICE_THRESHOLD}")

        eligible = all([details["stage_2"], details["has_valid_base"], details["liquidity_ok"], details["price_threshold_ok"], details["prior_run_ok"]])
        return {"eligible": eligible, "reasons": reasons, "details": details}

    def _identify_base_best(self, hist: pd.DataFrame) -> Optional[Dict]:
        """
        Try multiple lookback windows; return the base with highest prior run (advance-before-base).
        Uses full hist so prior_run is computed correctly.
        """
        lookback = min(BASE_LOOKBACK_DAYS, len(hist))
        if lookback < 20:
            return MinerviniScanner._identify_base(self, hist.tail(lookback))
        best_base = None
        best_prior: float = -1.0
        for w in range(20, min(61, lookback + 1), 5):
            tail = hist.tail(w)
            base_info = MinerviniScanner._identify_base(self, tail)
            if not base_info:
                continue
            prior_run_pct, _ = _compute_prior_run(hist, base_info)
            pct = float(prior_run_pct) if prior_run_pct is not None else -1.0
            if pct > best_prior:
                best_prior = pct
                best_base = base_info
        if best_base is not None:
            return best_base
        return MinerviniScanner._identify_base(self, hist.tail(lookback))

    def _classify_base(self, base_info: Dict, prior_run_pct: Optional[float]) -> str:
        """
        PART 4 — Base type: flat_base | cup | high_tight_flag | standard_base
        """
        if not base_info:
            return "standard_base"
        depth = base_info.get("depth_pct") or 0
        length_weeks = base_info.get("length_weeks") or 0
        prior = prior_run_pct if prior_run_pct is not None else 0

        if depth <= BASE_TYPE_FLAT_MAX_DEPTH_PCT:
            return "flat_base"
        if (
            prior >= BASE_TYPE_HIGH_TIGHT_PRIOR_RUN_PCT
            and depth <= BASE_TYPE_HIGH_TIGHT_MAX_DEPTH_PCT
            and length_weeks <= BASE_TYPE_HIGH_TIGHT_MAX_WEEKS
        ):
            return "high_tight_flag"
        if depth > BASE_TYPE_FLAT_MAX_DEPTH_PCT and depth <= BASE_DEPTH_MAX_PCT:
            return "cup"
        return "standard_base"

    def _get_pivot_by_base_type(self, base_info: Optional[Dict], base_type: str) -> Tuple[Optional[float], str]:
        """
        Institutional pivot: resistance from base structure by type.
        Flat base: max(High), optional spike filter. Cup: max(handle High). HTF: max(flag High).
        Returns (pivot_price, pivot_source_description).
        """
        if not base_info or "data" not in base_info:
            return None, "no_base"
        base_data = base_info["data"]
        if base_data.empty or "High" not in base_data.columns:
            return None, "no_data"
        highs = base_data["High"]
        n = len(highs)

        def _apply_spike_filter(series: pd.Series) -> pd.Series:
            """Exclude bars where High > mean + K*std, except in last PIVOT_IGNORE_SPIKE_WITHIN_LAST_N_DAYS."""
            if not PIVOT_SPIKE_FILTER_ENABLED or len(series) < 3:
                return series
            mean_h = series.mean()
            std_h = series.std()
            if std_h <= 0 or pd.isna(std_h):
                return series
            threshold = mean_h + PIVOT_SPIKE_STD_MULTIPLIER * std_h
            exclude_last = min(PIVOT_IGNORE_SPIKE_WITHIN_LAST_N_DAYS, len(series) - 1)
            keep = series <= threshold
            if exclude_last > 0:
                keep.iloc[-exclude_last:] = True
            return series[keep]

        if base_type == "flat_base" or base_type == "standard_base":
            filtered = _apply_spike_filter(highs)
            pivot = float(filtered.max()) if not filtered.empty else float(highs.max())
            source = "flat_max" if not PIVOT_SPIKE_FILTER_ENABLED else "flat_max_spike_filtered"
            return pivot, source
        if base_type == "cup":
            handle_days = min(PIVOT_HANDLE_DAYS, n)
            if handle_days < 2:
                pivot = float(highs.max())
                return pivot, "cup_whole"
            handle_highs = highs.tail(handle_days)
            pivot = float(handle_highs.max())
            return pivot, "cup_handle"
        if base_type == "high_tight_flag":
            # Flag is the base; pivot = high of flag
            pivot = float(highs.max())
            return pivot, "htf_flag"
        pivot = float(highs.max())
        return pivot, "default"

    def _component_score_trend(self, checklist: Dict) -> float:
        """
        Trend & Structure: graded 0–100 by % price above 200 SMA.
        ≥30% → 100, 15–30% → 70, 5–15% → 40, 0–5% → 15, below 0 → 0.
        If trend_structure not passed, returns 0.
        """
        trend = checklist.get("trend_structure", {})
        if not trend.get("passed", False):
            return 0.0
        details = trend.get("details", {})
        current_price = details.get("current_price")
        sma_200 = details.get("sma_200")
        if current_price is None or sma_200 is None or sma_200 <= 0:
            return 15.0  # passed but no detail → minimal score
        pct_above_200 = (float(current_price) - float(sma_200)) / float(sma_200) * 100.0
        if pct_above_200 >= TREND_PCT_ABOVE_200_TIER1:
            return 100.0
        if pct_above_200 >= TREND_PCT_ABOVE_200_TIER2:
            return 70.0
        if pct_above_200 >= TREND_PCT_ABOVE_200_TIER3:
            return 40.0
        if pct_above_200 >= TREND_PCT_ABOVE_200_TIER4:
            return 15.0
        return 0.0

    def _component_score_base(
        self,
        checklist: Dict,
        prior_run_pct: Optional[float],
        base_quality_extras: Optional[Tuple[bool, bool]] = None,
    ) -> float:
        """
        Base Quality: 0-100 from pass + depth + prior run + length + elite bonuses.
        base_quality_extras = (range_contraction_ok, weekly_closes_upper_40_ok) → +10 each.
        """
        bq = checklist.get("base_quality", {})
        if not bq.get("passed", False):
            return 0.0
        details = bq.get("details", {})
        score = 80.0  # base pass
        depth = details.get("base_depth_pct") or 25
        if depth <= BASE_SCORE_DEPTH_ELITE_PCT:
            score += 10
        elif depth <= BASE_SCORE_DEPTH_GOOD_PCT:
            score += 5
        if prior_run_pct is not None:
            if prior_run_pct >= MIN_PRIOR_RUN_PCT:
                score += BASE_SCORE_PRIOR_RUN_BONUS
            else:
                score += BASE_SCORE_PRIOR_RUN_PENALTY  # penalize
        # Base length: ideal 5-8 weeks bonus, short <4 weeks penalty
        length_weeks = details.get("base_length_weeks")
        if length_weeks is not None:
            try:
                lw = float(length_weeks)
                if BASE_SCORE_LENGTH_IDEAL_MIN_WEEKS <= lw <= BASE_SCORE_LENGTH_IDEAL_MAX_WEEKS:
                    score += BASE_SCORE_LENGTH_IDEAL_BONUS
                elif lw < BASE_SCORE_LENGTH_SHORT_PENALTY_WEEKS:
                    score += BASE_SCORE_LENGTH_SHORT_PENALTY
            except (TypeError, ValueError):
                pass
        if base_quality_extras:
            range_ok, weekly_ok = base_quality_extras
            if range_ok:
                score += BASE_BONUS_RANGE_CONTRACTION_LAST_2W
            if weekly_ok:
                score += BASE_BONUS_WEEKLY_CLOSES_UPPER_40
        return min(100.0, max(0.0, score))

    def _component_score_rs(self, rs_percentile: Optional[float], checklist: Dict) -> float:
        """Relative Strength: use rs_percentile (0-100) if provided, else from RS details."""
        if rs_percentile is not None:
            return float(rs_percentile)
        details = checklist.get("relative_strength", {}).get("details", {})
        rs_rating = details.get("rs_rating")
        if rs_rating is not None:
            return min(100.0, max(0.0, float(rs_rating)))
        return 50.0

    def _component_score_volume(self, checklist: Dict) -> float:
        """Volume Signature: 0-100. When passed, still penalize weak contraction (pre-breakout)."""
        vol = checklist.get("volume_signature", {})
        details = vol.get("details", {})
        contraction = details.get("volume_contraction", 1.0)
        try:
            contraction = float(contraction)
        except (TypeError, ValueError):
            contraction = 1.0
        if vol.get("passed", False):
            # Don't give 100 for passed if base volume was not dry
            if contraction >= VOLUME_SCORE_MODERATE_CONTRACTION:
                return 50.0
            if contraction >= VOLUME_SCORE_STRONG_CONTRACTION:
                return 70.0
            return 100.0
        if contraction < VOLUME_SCORE_STRONG_CONTRACTION:
            return 70.0
        if contraction < VOLUME_SCORE_MODERATE_CONTRACTION:
            return 50.0
        return 0.0

    def _component_score_breakout(self, checklist: Dict, distance_to_pivot_pct: float) -> float:
        """Breakout Quality: 0-100 from pass + distance to pivot."""
        br = checklist.get("breakout_rules", {})
        if br.get("passed", False):
            return 100.0
        # Pre-breakout: closer to pivot = higher score
        if BREAKOUT_SCORE_TIGHT_LOW_PCT <= distance_to_pivot_pct <= BREAKOUT_SCORE_TIGHT_HIGH_PCT:
            return 80.0
        if BREAKOUT_SCORE_NEAR_LOW_PCT <= distance_to_pivot_pct < BREAKOUT_SCORE_NEAR_HIGH_PCT:
            return 60.0
        if distance_to_pivot_pct > EXTENDED_DISTANCE_PCT:
            return 30.0  # extended
        return 50.0

    def _calculate_composite_score(self, metrics: Dict) -> float:
        """
        PART 5 — Weighted composite: sum(weight_i * component_score_i).
        """
        t = metrics.get("trend_score", 0) or 0
        b = metrics.get("base_score", 0) or 0
        r = metrics.get("rs_score", 0) or 0
        v = metrics.get("volume_score", 0) or 0
        br = metrics.get("breakout_score", 0) or 0
        return (
            WEIGHT_TREND_STRUCTURE * t
            + WEIGHT_BASE_QUALITY * b
            + WEIGHT_RELATIVE_STRENGTH * r
            + WEIGHT_VOLUME_SIGNATURE * v
            + WEIGHT_BREAKOUT_QUALITY * br
        )

    def _grade_from_composite(self, composite_score: float) -> str:
        """≥85 A+, 75-84 A, 65-74 B, 55-64 C, <55 REJECT."""
        if composite_score >= GRADE_A_PLUS_MIN_SCORE:
            return "A+"
        if composite_score >= GRADE_A_MIN_SCORE:
            return "A"
        if composite_score >= GRADE_B_MIN_SCORE:
            return "B"
        if composite_score >= GRADE_C_MIN_SCORE:
            return "C"
        return "REJECT"

    def _build_risk_section(
        self,
        hist: pd.DataFrame,
        pivot_price: Optional[float],
        buy_sell: Dict,
        in_breakout: bool,
    ) -> Dict:
        """Stop (ATR or fixed), risk_per_share, reward_to_risk, atr_14, stop_method."""
        out = {
            "stop_price": None,
            "risk_per_share": None,
            "reward_to_risk": None,
            "atr_14": None,
            "stop_method": "fixed",
        }
        if pivot_price is None or pivot_price <= 0:
            return out
        atr = self._calculate_atr(hist, period=ATR_PERIOD_V2)
        out["atr_14"] = round(float(atr), 4) if atr is not None else None

        if USE_ATR_STOP_V2 and atr is not None:
            atr_stop = pivot_price - atr * ATR_STOP_MULTIPLIER_V2
            # lowest_low of breakout week (last N days)
            last_n = hist.tail(ATR_STOP_LOWEST_LOW_DAYS)
            lowest_week = float(last_n["Low"].min()) if not last_n.empty else atr_stop
            stop_price = max(atr_stop, lowest_week)
            out["stop_price"] = round(stop_price, 2)
            out["stop_method"] = "ATR"
        else:
            stop_price = pivot_price * (1 - STOP_LOSS_PCT / 100)
            out["stop_price"] = round(stop_price, 2)
            out["stop_method"] = "fixed"

        risk = pivot_price - out["stop_price"]
        out["risk_per_share"] = round(risk, 2)
        profit_target_1 = buy_sell.get("profit_target_1")
        if profit_target_1 and risk > 0:
            out["reward_to_risk"] = round((float(profit_target_1) - pivot_price) / risk, 2)
        return out

    def scan_stock(
        self,
        ticker: str,
        benchmark_override: Optional[str] = None,
        rs_percentile: Optional[float] = None,
        rs_3m_return: Optional[float] = None,
        rs_6m_return: Optional[float] = None,
    ) -> Dict:
        """
        Scan one stock; returns deterministic JSON (single source of truth).
        If rs_percentile/rs_3m_return are provided (from universe pass), they are used; otherwise RS from checklist only.
        """
        try:
            benchmark = benchmark_override or self.benchmark
            hist = self.data_provider.get_historical_data(ticker, period="1y", interval="1d")
            if hist.empty or len(hist) < MIN_DATA_DAYS:
                return self._reject_result(ticker, "Insufficient historical data")

            lookback = min(BASE_LOOKBACK_DAYS, len(hist))
            base_info = self._identify_base_best(hist)

            # Structural eligibility first
            eligibility = self._check_structural_eligibility(hist, base_info)
            if not eligibility["eligible"]:
                return self._reject_result(ticker, "; ".join(eligibility["reasons"][:5]))

            # Run full checklist (reuse parent logic)
            stock_info = self.data_provider.get_stock_info(ticker)
            trend_results = self._check_trend_structure(hist, stock_info)
            base_results = self._check_base_quality(hist, base_info)
            rs_results = self._check_relative_strength(ticker, hist, base_info, benchmark=benchmark)
            volume_results = self._check_volume_signature(hist, base_info)

            # Prior run and base-type-aware pivot (before breakout / buy_sell)
            prior_run_pct, _ = _compute_prior_run(hist, base_info)
            if prior_run_pct is not None and prior_run_pct < MIN_PRIOR_RUN_PCT:
                base_results["passed"] = False
                base_results["failures"].append(f"Prior run {prior_run_pct:.1f}% < {MIN_PRIOR_RUN_PCT}%")
            base_type = self._classify_base(base_info or {}, prior_run_pct)
            pivot_price, pivot_source = self._get_pivot_by_base_type(base_info, base_type)
            orig_base_data = None
            if pivot_price is not None and base_info and "data" in base_info:
                orig_base_data = base_info["data"]
                copy = orig_base_data.copy()
                copy["High"] = copy["High"].clip(upper=float(pivot_price))
                copy.loc[copy.index[0], "High"] = float(pivot_price)
                base_info["data"] = copy
            breakout_results = self._check_breakout_rules(hist, base_info)
            checklist = {
                "trend_structure": trend_results,
                "base_quality": base_results,
                "relative_strength": rs_results,
                "volume_signature": volume_results,
                "breakout_rules": breakout_results,
            }
            buy_sell = self._calculate_buy_sell_prices(hist, base_info, checklist)
            if orig_base_data is not None:
                base_info["data"] = orig_base_data

            pivot_price = buy_sell.get("pivot_price")
            current_price = float(hist["Close"].iloc[-1])
            distance_to_pivot_pct = ((current_price - pivot_price) / pivot_price * 100) if pivot_price and pivot_price > 0 else 0.0
            in_breakout = buy_sell.get("in_breakout", False)

            # Base quality extras (range contraction, weekly closes upper 40%)
            base_extras = _base_quality_extras(base_info)

            # Component scores (0-100 each)
            trend_score = self._component_score_trend(checklist)
            base_score = self._component_score_base(checklist, prior_run_pct, base_extras)
            rs_score = self._component_score_rs(rs_percentile, checklist)
            volume_score = self._component_score_volume(checklist)
            breakout_score = self._component_score_breakout(checklist, distance_to_pivot_pct)

            composite_score = self._calculate_composite_score({
                "trend_score": trend_score,
                "base_score": base_score,
                "rs_score": rs_score,
                "volume_score": volume_score,
                "breakout_score": breakout_score,
            })
            grade = self._grade_from_composite(composite_score)
            # Cap grade by RS percentile: A+ requires min RS, A requires min RS
            rs_pct = rs_percentile if rs_percentile is not None else 0
            if grade == "A+" and rs_pct < MIN_RS_PERCENTILE_FOR_A_PLUS:
                grade = "A"
            elif grade == "A" and rs_pct < MIN_RS_PERCENTILE_FOR_A:
                grade = "B"

            # Base block
            base_type = self._classify_base(base_info or {}, prior_run_pct)
            base_block = {
                "type": base_type,
                "length_weeks": round(float(base_info["length_weeks"]), 1) if base_info else 0,
                "depth_pct": round(float(base_info["depth_pct"]), 1) if base_info else 0,
                "prior_run_pct": round(prior_run_pct, 1) if prior_run_pct is not None else None,
            }

            # RS block (use passed-in or compute from checklist)
            rsi = self._calculate_rsi(hist["Close"], period=RSI_PERIOD)
            rsi_14 = float(rsi.iloc[-1]) if rsi is not None and not rsi.empty else None
            rs_block = {
                "rs_3m": round(rs_3m_return, 4) if rs_3m_return is not None else None,
                "rs_percentile": round(rs_percentile, 1) if rs_percentile is not None else None,
                "rsi_14": round(rsi_14, 1) if rsi_14 is not None else None,
            }

            # Breakout block (pivot_source from base-type-aware logic)
            breakout_block = {
                "pivot_price": round(pivot_price, 2) if pivot_price else None,
                "pivot_source": pivot_source if pivot_price else None,
                "distance_to_pivot_pct": round(distance_to_pivot_pct, 2),
                "in_breakout": in_breakout,
            }

            # Risk block (ATR or fixed)
            risk_block = self._build_risk_section(hist, pivot_price, buy_sell, in_breakout)

            # Power rank: 0.5 * rs_percentile + 0.5 * prior_run_scaled (prior_run capped at 100)
            prior_scaled = min(
                float(prior_run_pct or 0),
                POWER_RANK_PRIOR_RUN_CAP,
            )
            power_rank = 0.5 * (rs_percentile or 0) + 0.5 * prior_scaled

            return {
                "ticker": ticker,
                "eligible": True,
                "grade": grade,
                "composite_score": round(composite_score, 1),
                "trend_score": round(trend_score, 1),
                "base_score": round(base_score, 1),
                "rs_score": round(rs_score, 1),
                "volume_score": round(volume_score, 1),
                "breakout_score": round(breakout_score, 1),
                "power_rank": round(power_rank, 1),
                "base": base_block,
                "relative_strength": rs_block,
                "breakout": breakout_block,
                "risk": risk_block,
            }
        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}", exc_info=True)
            return self._reject_result(ticker, str(e))

    def _reject_result(self, ticker: str, reason: str = "") -> Dict:
        """Standardized REJECT JSON."""
        return {
            "ticker": ticker,
            "eligible": False,
            "grade": "REJECT",
            "composite_score": 0.0,
            "trend_score": 0.0,
            "base_score": 0.0,
            "rs_score": 0.0,
            "volume_score": 0.0,
            "breakout_score": 0.0,
            "power_rank": None,
            "base": {"type": "standard_base", "length_weeks": 0, "depth_pct": 0, "prior_run_pct": None},
            "relative_strength": {"rs_3m": None, "rs_percentile": None, "rsi_14": None},
            "breakout": {"pivot_price": None, "pivot_source": None, "distance_to_pivot_pct": 0, "in_breakout": False},
            "risk": {"stop_price": None, "risk_per_share": None, "reward_to_risk": None, "atr_14": None, "stop_method": "fixed"},
            "reject_reason": reason,
        }

    def scan_universe(
        self,
        tickers: List[str],
        benchmark_overrides: Optional[Dict[str, str]] = None,
    ) -> List[Dict]:
        """
        Two-phase: (1) collect 3M returns for all tickers, compute percentile; (2) scan each stock with rs_percentile.
        benchmark_overrides: optional dict ticker -> benchmark
        """
        # Phase 1: 3M returns for universe
        returns_3m: Dict[str, float] = {}
        for t in tickers:
            try:
                hist = self.data_provider.get_historical_data(t, period="1y", interval="1d")
                if hist is None or len(hist) < RS_3M_LOOKBACK_DAYS:
                    continue
                start_price = hist["Close"].iloc[-RS_3M_LOOKBACK_DAYS]
                end_price = hist["Close"].iloc[-1]
                if start_price and start_price > 0:
                    returns_3m[t] = (end_price / float(start_price) - 1.0) * 100.0
            except Exception as e:
                logger.debug(f"Could not get 3M return for {t}: {e}")
        values = list(returns_3m.values())
        percentiles: Dict[str, float] = {}
        for t, r in returns_3m.items():
            percentiles[t] = _percentile_rank(r, values)

        # Phase 2: scan each with rs_percentile and rs_3m
        results = []
        for t in tickers:
            bench = (benchmark_overrides or {}).get(t) or self.benchmark
            r3 = returns_3m.get(t)
            pct = percentiles.get(t)
            result = self.scan_stock(t, benchmark_override=bench, rs_percentile=pct, rs_3m_return=r3, rs_6m_return=None)
            results.append(result)
        return results
