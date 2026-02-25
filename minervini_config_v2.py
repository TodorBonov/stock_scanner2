"""
Minervini SEPA Scanner V2 – Configuration
Used only by minervini_scanner_v2 and report/report_v2.
All thresholds are config-driven; no hardcoding in scanner logic.
"""
from pathlib import Path

# ----------------------------------------------------------------------------
# STRUCTURAL ELIGIBILITY (V2)
# ----------------------------------------------------------------------------
# Liquidity: minimum avg dollar volume (20d) to be eligible
MIN_AVG_DOLLAR_VOLUME_20D = 1_000_000.0  # $1M minimum

# Price: minimum share price to be eligible
MIN_PRICE_THRESHOLD = 5.0  # Avoid penny stocks

# ----------------------------------------------------------------------------
# PRIOR RUN (V2) – base must follow meaningful advance (also structural gate)
# ----------------------------------------------------------------------------
MIN_PRIOR_RUN_PCT = 25.0  # prior_run_pct = (base_high - lowest_3m_before_base) / lowest_3m_before_base * 100
PRIOR_RUN_LOOKBACK_TRADING_DAYS = 63   # ~3 months before base
PRIOR_RUN_REQUIRED_FOR_ELIGIBILITY = True  # If True, prior_run < MIN_PRIOR_RUN_PCT → REJECT

# ----------------------------------------------------------------------------
# RS PERCENTILE (V2) – computed across universe after scan
# ----------------------------------------------------------------------------
RS_3M_LOOKBACK_DAYS = 63   # ~3 months for 3M return
RS_6M_LOOKBACK_DAYS = 126  # Optional 6M return

# ----------------------------------------------------------------------------
# BASE TYPE CLASSIFICATION (V2)
# ----------------------------------------------------------------------------
BASE_TYPE_FLAT_MAX_DEPTH_PCT = 15.0       # depth ≤ 15% → flat_base
BASE_TYPE_HIGH_TIGHT_PRIOR_RUN_PCT = 100.0  # prior_run ≥ 100%
BASE_TYPE_HIGH_TIGHT_MAX_DEPTH_PCT = 25.0   # depth ≤ 25%
BASE_TYPE_HIGH_TIGHT_MAX_WEEKS = 5.0        # base ≤ 5 weeks
# "cup" = U-shape (simplified: depth > 15% and not high_tight → could be cup or standard)
# standard_base = fallback

# ----------------------------------------------------------------------------
# PIVOT BY BASE TYPE (V2) – Minervini: pivot = resistance from base structure
# ----------------------------------------------------------------------------
# Flat base: pivot = max(High) of base, with optional spike filter
# Cup-with-handle: pivot = max(High) of handle (last N days)
# High tight flag: pivot = max(High) of flag (base is the flag)
PIVOT_SPIKE_FILTER_ENABLED = True   # Exclude outlier highs from pivot (mean + K*std)
PIVOT_SPIKE_STD_MULTIPLIER = 2.0    # Ignore bar if High > mean(High) + this * std(High)
PIVOT_IGNORE_SPIKE_WITHIN_LAST_N_DAYS = 5  # Don't filter spikes in last N days (near breakout)
PIVOT_HANDLE_DAYS = 7               # For cup: handle = last N trading days; pivot = max(handle High)

# ----------------------------------------------------------------------------
# TREND SCORE – graded by % above 200 SMA (not binary)
# ----------------------------------------------------------------------------
# Price % above 200 SMA → trend score component (0–100)
TREND_PCT_ABOVE_200_TIER1 = 30.0   # ≥30% above 200 SMA → 100
TREND_PCT_ABOVE_200_TIER2 = 15.0   # 15–30% → 70
TREND_PCT_ABOVE_200_TIER3 = 5.0    # 5–15% → 40
TREND_PCT_ABOVE_200_TIER4 = 0.0    # 0–5% → 15; below 0 → 0

# ----------------------------------------------------------------------------
# BASE QUALITY BONUSES – elite base traits
# ----------------------------------------------------------------------------
BASE_BONUS_RANGE_CONTRACTION_LAST_2W = 10   # +10 if price range in last 2 weeks of base is tight vs full base
BASE_BONUS_WEEKLY_CLOSES_UPPER_40 = 10      # +10 if last 2 weekly closes in upper 40% of base range
BASE_RANGE_CONTRACTION_RATIO_MAX = 0.5      # last_2w_range / base_range < this → contraction bonus

# ----------------------------------------------------------------------------
# POWER RANK – 0.5 * rs_percentile + 0.5 * prior_run_scaled (prior_run capped at 100)
# ----------------------------------------------------------------------------
POWER_RANK_PRIOR_RUN_CAP = 100.0   # prior_run_pct scaled as min(prior_run_pct, this)

# ----------------------------------------------------------------------------
# COMPOSITE SCORING WEIGHTS (V2) – each component 0–100
# ----------------------------------------------------------------------------
WEIGHT_TREND_STRUCTURE = 0.20   # 20%
WEIGHT_BASE_QUALITY = 0.25      # 25%
WEIGHT_RELATIVE_STRENGTH = 0.25 # 25%
WEIGHT_VOLUME_SIGNATURE = 0.15  # 15%
WEIGHT_BREAKOUT_QUALITY = 0.15  # 15%

# ----------------------------------------------------------------------------
# COMPOSITE GRADE BANDS (V2) – replace failure-count grading
# ----------------------------------------------------------------------------
GRADE_A_PLUS_MIN_SCORE = 85.0   # ≥85 → A+
GRADE_A_MIN_SCORE = 75.0        # 75–84 → A
GRADE_B_MIN_SCORE = 65.0        # 65–74 → B
GRADE_C_MIN_SCORE = 55.0        # 55–64 → C
# <55 → REJECT
# Min RS percentile for top grades (downgrade if below)
MIN_RS_PERCENTILE_FOR_A_PLUS = 80.0   # rs_percentile < this → cap at A
MIN_RS_PERCENTILE_FOR_A = 70.0       # rs_percentile < this → cap at B

# ----------------------------------------------------------------------------
# ATR STOP (V2) – when True, stop = max(pivot - ATR*mult, lowest_low_breakout_week)
# ----------------------------------------------------------------------------
USE_ATR_STOP_V2 = True   # Volatility-adjusted stop for growth / HTF names
ATR_PERIOD_V2 = 14
ATR_STOP_MULTIPLIER_V2 = 1.5
ATR_STOP_LOWEST_LOW_DAYS = 5   # Days for "breakout week" lowest low (floor under ATR stop)

# ----------------------------------------------------------------------------
# EXTENDED / DISTANCE TO PIVOT – single source for scanner, report, ChatGPT step
# ----------------------------------------------------------------------------
# Above pivot: distance_to_pivot_pct > EXTENDED_DISTANCE_PCT → "Extended" status, breakout score 30
EXTENDED_DISTANCE_PCT = 8.0    # Was 5; 8–10 = fewer names flagged extended
# Risk warning in report: "Extended: ticker (>X% above pivot)"
EXTENDED_RISK_WARNING_PCT = 15.0

# ----------------------------------------------------------------------------
# BREAKOUT SCORE BANDS (V2) – distance_to_pivot_pct → 0–100 component score
# ----------------------------------------------------------------------------
# Pre-breakout: tight band → 80, near band → 60, extended → 30, else 50
BREAKOUT_SCORE_TIGHT_LOW_PCT = -3   # -3% to 0% → 80
BREAKOUT_SCORE_TIGHT_HIGH_PCT = 0
BREAKOUT_SCORE_NEAR_LOW_PCT = -5    # -5% to -3% → 60
BREAKOUT_SCORE_NEAR_HIGH_PCT = -3
# Above EXTENDED_DISTANCE_PCT → 30 (see above)

# ----------------------------------------------------------------------------
# BASE QUALITY SCORE BANDS (optional – used in _component_score_base)
# ----------------------------------------------------------------------------
BASE_SCORE_DEPTH_ELITE_PCT = 15   # depth ≤ this → +10
BASE_SCORE_DEPTH_GOOD_PCT = 20    # depth ≤ this → +5
BASE_SCORE_PRIOR_RUN_BONUS = 10   # prior_run ≥ MIN_PRIOR_RUN_PCT → +this
BASE_SCORE_PRIOR_RUN_PENALTY = -20  # prior_run < MIN_PRIOR_RUN_PCT → this
# Base length in composite: ideal 5–8 weeks bonus, short (<4 weeks) penalty
BASE_SCORE_LENGTH_IDEAL_MIN_WEEKS = 5.0
BASE_SCORE_LENGTH_IDEAL_MAX_WEEKS = 8.0
BASE_SCORE_LENGTH_SHORT_PENALTY_WEEKS = 4.0   # length < this → penalty
BASE_SCORE_LENGTH_IDEAL_BONUS = 5
BASE_SCORE_LENGTH_SHORT_PENALTY = -5

# ----------------------------------------------------------------------------
# VOLUME SCORE BANDS (optional – volume_contraction vs score)
# ----------------------------------------------------------------------------
VOLUME_SCORE_STRONG_CONTRACTION = 0.8   # contraction < this → 70
VOLUME_SCORE_MODERATE_CONTRACTION = 0.95  # contraction < this → 50; else 0

# ----------------------------------------------------------------------------
# BASE RECENCY – "last 2 weeks" for range contraction bonus
# ----------------------------------------------------------------------------
BASE_LAST_N_DAYS_RANGE_CONTRACTION = 10   # Trading days (~2 weeks)

# ----------------------------------------------------------------------------
# EARLY CANDIDATES (report section only – same scan, different filter/sort)
# ----------------------------------------------------------------------------
# "Early" = not yet extended, building RS, near pivot. Used only in report.
EARLY_TREND_SCORE_MIN = 40.0   # trend_score >= this (not weak)
EARLY_TREND_SCORE_MAX = 70.0   # trend_score <= this (not extended; 100 = extended)
EARLY_RS_PERCENTILE_MIN = 50.0 # rs_percentile >= this (building)
EARLY_RS_PERCENTILE_MAX = 80.0 # rs_percentile <= this (not already top)
EARLY_DIST_TO_PIVOT_MIN_PCT = -5.0  # distance_to_pivot_pct >= -5%
EARLY_DIST_TO_PIVOT_MAX_PCT = 0.0   # distance_to_pivot_pct <= 0%
EARLY_MAX_ROWS = 40   # max rows in Early candidates table

# ----------------------------------------------------------------------------
# OUTPUT PATHS (V2 pipeline – does not overwrite main pipeline)
# ----------------------------------------------------------------------------
REPORTS_DIR_V2 = Path("reports")
SCAN_RESULTS_V2_LATEST = REPORTS_DIR_V2 / "scan_results_v2_latest.json"
USER_REPORT_SUBDIR_V2 = "v2"
SEPA_USER_REPORT_PREFIX = "sepa_scan_user_report_"
SEPA_CSV_PREFIX = "sepa_scan_summary_"
