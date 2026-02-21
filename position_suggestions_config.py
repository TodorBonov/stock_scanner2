"""
Position suggestions configuration
Dedicated config for 03_position_suggestions.py – rules for suggesting actions on open positions.
All thresholds and behaviour are defined here; change only this file to adjust suggestions.
"""
from pathlib import Path

# =============================================================================
# PATHS
# =============================================================================

# Directory for position suggestion reports
POSITION_REPORTS_DIR = Path("reports")
# Optional: path to latest scan results (A/B grades); if set, used for grade-based suggestions
SCAN_RESULTS_PATH = Path("reports/scan_results_latest.json")

# =============================================================================
# STOP LOSS & PROFIT TARGETS (vs average entry price)
# =============================================================================

# Stop loss: suggest EXIT if position is down this much from average entry
STOP_LOSS_PCT = 5.0
# Purpose: 5% max loss (R/R 2:1 with 10% target)
# Used by: Suggestion logic for EXIT (cut loss)

# First profit target: suggest REDUCE (take partial) when position is up this much
PROFIT_TARGET_1_PCT = 10.0
# Purpose: 10% targeted win (2:1 R/R vs 5% stop)
# Used by: Suggestion logic for REDUCE (take partial profits)

# Second profit target: suggest REDUCE more when position is up this much
PROFIT_TARGET_2_PCT = 45.0
# Purpose: Let winners run until here, then consider reducing
# Used by: Suggestion logic for REDUCE (let winners run then trim)

# Buffer: don't suggest REDUCE until price is at least this far above entry (avoids noise)
PROFIT_SUGGEST_MIN_PCT = 5.0

# =============================================================================
# GRADE-BASED RULES (if scan results are available)
# =============================================================================

# Grades that are considered "strong" – suggest HOLD or ADD if position is in profit
STRONG_GRADES = ("A+", "A")

# Grades that are considered "weak" – suggest EXIT or REDUCE if other triggers (e.g. stop loss)
WEAK_GRADES = ("C", "F")

# If position is in loss and grade is in WEAK_GRADES, suggest EXIT (cut loss)
EXIT_ON_WEAK_GRADE_IF_LOSS = True

# If position is in profit and grade is in STRONG_GRADES, allow ADD suggestion when below target 1
ALLOW_ADD_ON_STRONG_GRADE = True

# When grade is B and position is in profit, suggest REDUCE (trim) instead of only EXIT on weak+loss
REDUCE_ON_GRADE_B_IN_PROFIT = True

# When suggesting ADD, require current price >= scan pivot; if below pivot, suggest HOLD (avoid adding in pullbacks)
DO_NOT_ADD_BELOW_PIVOT = True

# =============================================================================
# SUGGESTION PRIORITY
# =============================================================================

# When multiple conditions apply, order of precedence:
# 1. Stop loss hit -> EXIT (cut loss)
# 2. At or past profit target 2 -> REDUCE (take more profit)
# 3. At or past profit target 1 -> REDUCE (take partial)
# 4. Grade weak + in loss -> EXIT (if EXIT_ON_WEAK_GRADE_IF_LOSS)
# 5. Grade B + in profit -> REDUCE (if REDUCE_ON_GRADE_B_IN_PROFIT)
# 6. Grade strong + below target 1 -> ADD or HOLD (if ALLOW_ADD_ON_STRONG_GRADE; HOLD if below pivot and DO_NOT_ADD_BELOW_PIVOT)
# 7. Else -> HOLD

# =============================================================================
# OUTPUT
# =============================================================================

# Include scan grade in report when available
INCLUDE_GRADE_IN_REPORT = True

# Include entry, current price, PnL %, and suggested stop/targets in report
INCLUDE_PRICE_DETAILS = True
