"""
Pre-breakout view configuration (additive only).
Used ONLY by the pre-breakout report section and ChatGPT pre-breakout block.
NOT used by: fetch_utils, 02 main report logic, New4/New5 main lists.
All existing pipeline behavior is unchanged.
"""

# ----------------------------------------------------------------------------
# PRE-BREAKOUT FILTER
# ----------------------------------------------------------------------------
# Maximum distance below pivot to include (e.g. 5 = within 5% below pivot).
# distance_to_buy_pct is negative when price is below pivot.
PRE_BREAKOUT_MAX_DISTANCE_PCT = 5.0

# Minimum grade to include in pre-breakout list (B = include B, A, A+).
# Stocks must have at least this grade AND not yet cleared pivot.
PRE_BREAKOUT_MIN_GRADE = "B"
# Grade order for comparison (higher index = worse).
_PRE_BREAKOUT_GRADE_ORDER = ("A+", "A", "B", "C", "F")

# Require a valid base (base_quality has details with base_high/base_low).
# If True, only stocks with base_quality.details are included.
PRE_BREAKOUT_REQUIRE_BASE = True

# Require breakout_rules to have NOT passed (stock has not yet cleared pivot by 2%).
PRE_BREAKOUT_REQUIRE_NOT_BROKEN_OUT = True

# "Near pivot" band: within this % below pivot (e.g. 2 = within 2% below). Used for tagging/sorting; best setups already sorted by distance so nearest appear first.
PRE_BREAKOUT_NEAR_PIVOT_PCT = 2.0
