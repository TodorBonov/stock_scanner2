# Minervini V2 Script – Trading Perspective Review

Thorough review of the Minervini SEPA Scanner V2 from a **trading perspective**: what works well, suggested improvements, and parameters that belong in config.

---

## 1. What Works Well (Trading Perspective)

### 1.1 Structural gate before scoring
- **Eligibility** requires: Stage 2 trend + valid base + liquidity (20d avg dollar volume ≥ $1M) + min price ($5). Fail any → REJECT, no scoring.
- **Why it helps:** Avoids wasting attention on illiquid or downtrending names; keeps the universe tradeable and Stage 2–only.

### 1.2 Prior run requirement
- Base must follow a **≥25% advance** (configurable) from the lowest low in the prior ~3 months.
- **Why it helps:** Aligns with Minervini’s “advance before base”; filters out bases that formed after weak or no prior run.

### 1.3 RS percentile across universe
- RS component uses **3M return percentile** across the scanned universe (0–100), not just vs one benchmark.
- **Why it helps:** Ranks relative strength among your actual watchlist; better for stock selection than a single-index comparison.

### 1.4 Base-type-aware pivot
- Pivot by base type: **flat** (max High, optional spike filter), **cup** (handle high), **high-tight flag** (flag high).
- **Why it helps:** Defines resistance correctly per pattern; improves entry and stop levels.

### 1.5 ATR stop with floor
- When ATR stop is on: stop = `max(pivot - ATR×mult, lowest_low of last 5 days)`.
- **Why it helps:** Volatility-adjusted risk while avoiding a stop tighter than recent price action (reduces noise exits).

### 1.6 Composite scoring and grades
- Weighted composite (trend, base, RS, volume, breakout) with **configurable weights** and grade bands (A+/A/B/C/REJECT).
- **Why it helps:** Single, auditable score; easy to tune aggressiveness (e.g. raise/lower grade thresholds).

### 1.7 Power rank
- `0.5 × rs_percentile + 0.5 × min(prior_run_pct, 100)`.
- **Why it helps:** Surfaces names that are both strong (RS) and had a big prior run (momentum).

### 1.8 Deterministic JSON output
- One structured JSON per ticker; no LLM in the engine.
- **Why it helps:** Reproducible scans; easy to backtest, log, and integrate with other tools.

---

## 2. Suggested Improvements (Trading)

### 2.1 Centralize “extended” thresholds (high impact)
- **Issue:** “Extended” is defined in three places with different numbers:
  - Scanner: `distance_to_pivot_pct > 5` → breakout score 30.
  - Report status: `dist > 5` → “Extended”.
  - Report risk warnings: `> 10` → “Extended: ticker (>10% above pivot)”.
- **Suggestion:** Add to `minervini_config_v2.py`:
  - `EXTENDED_DISTANCE_PCT` (e.g. 8 or 10) for **scoring and status** (“Extended”).
  - `EXTENDED_RISK_WARNING_PCT` (e.g. 15) for **risk warnings** (“>X% above pivot”).
- **Why:** Fewer good names flagged as extended; one place to tune “how far above pivot” is too far.

### 2.2 Clarify R/R and entry price
- **Current:** `reward_to_risk` = (profit_target_1 − pivot) / (pivot − stop). So R/R is **at pivot entry**.
- **Issue:** If the report says “Triggered” and the user buys at **current** price, actual risk = current − stop (often larger), so actual R/R is lower.
- **Suggestion:** In the user report, add one line when `in_breakout`: e.g. “R/R at pivot: X.XX; at current price: Y.YY” (using current price for risk). Optional: add `reward_to_risk_at_current` in the JSON for triggered names.

### 2.3 Prior-run penalty
- **Current:** If prior_run_pct < 25%, base score gets **−20** (and base quality is failed). That’s a large drop.
- **Suggestion:** Make the penalty configurable (e.g. `BASE_SCORE_PRIOR_RUN_PENALTY = -20`). Consider −10 if you want to allow marginal prior runs without killing the score.

### 2.4 Base lookback consistency
- **Current:** V2 uses `lookback = min(60, len(hist))` for base identification; main config has `BASE_LOOKBACK_DAYS = 60`.
- **Suggestion:** Import and use `BASE_LOOKBACK_DAYS` from `config` in V2 (or add `BASE_LOOKBACK_DAYS_V2` in `minervini_config_v2.py`) so one constant drives both pipelines.

### 2.5 Optional minimum R/R filter
- **Current:** No eligibility filter on reward-to-risk.
- **Suggestion:** Optional `MIN_REWARD_TO_RISK` (e.g. 1.5). If set and R/R < threshold, either exclude from “actionable” or add a warning in the report. Keeps poor R/R setups from being treated as full candidates.

### 2.6 Optional minimum RS percentile
- **Current:** Structural eligibility does not require a minimum RS percentile.
- **Suggestion:** Optional `MIN_RS_PERCENTILE_ELIGIBILITY` (e.g. 40). When set, treat rs_percentile < value as ineligible (or “watch only”). Helps avoid the weakest RS names in the list.

### 2.7 “Breakout week” for ATR stop floor
- **Current:** “Lowest low of last 5 days” is hardcoded.
- **Suggestion:** Add `ATR_STOP_LOWEST_LOW_DAYS = 5` (or 4–5) in config so you can align with your definition of “breakout week” without code changes.

---

## 3. Parameters That Should Be in Config

These are either **hardcoded in the V2 scanner/report** or **duplicated across scanner/report/ChatGPT step**. Moving them to `minervini_config_v2.py` gives one place to tune behaviour.

### 3.1 Extended / breakout distance (recommended)
| Parameter | Suggested default | Used in |
|-----------|-------------------|--------|
| `EXTENDED_DISTANCE_PCT` | 8.0 or 10.0 | Scanner (`_component_score_breakout`), report status, 08_chatgpt_new_positions_v2 |
| `EXTENDED_RISK_WARNING_PCT` | 15.0 | Report “Risk Warnings” |

### 3.2 Breakout score bands (recommended)
| Parameter | Suggested default | Meaning |
|-----------|-------------------|--------|
| `BREAKOUT_SCORE_TIGHT_LOW_PCT` | -3 | Lower bound of “tight” band (score 80) |
| `BREAKOUT_SCORE_TIGHT_HIGH_PCT` | 0 | Upper bound of “tight” band |
| `BREAKOUT_SCORE_NEAR_LOW_PCT` | -5 | Lower bound of “near” band (score 60) |
| `BREAKOUT_SCORE_NEAR_HIGH_PCT` | -3 | Upper bound of “near” band |
| (extended uses `EXTENDED_DISTANCE_PCT`) | — | Above this → score 30 |

### 3.3 Base quality score (optional)
| Parameter | Suggested default | Meaning |
|-----------|-------------------|--------|
| `BASE_SCORE_DEPTH_ELITE_PCT` | 15 | depth ≤ this → +10 |
| `BASE_SCORE_DEPTH_GOOD_PCT` | 20 | depth ≤ this → +5 |
| `BASE_SCORE_PRIOR_RUN_BONUS` | 10 | prior_run ≥ MIN_PRIOR_RUN_PCT → +10 |
| `BASE_SCORE_PRIOR_RUN_PENALTY` | -20 | prior_run < MIN_PRIOR_RUN_PCT → this |

### 3.4 Volume score (optional)
| Parameter | Suggested default | Meaning |
|-----------|-------------------|--------|
| `VOLUME_SCORE_STRONG_CONTRACTION` | 0.8 | contraction < this → 70 |
| `VOLUME_SCORE_MODERATE_CONTRACTION` | 0.95 | contraction < this → 50 |

### 3.5 Base / ATR helper periods (optional)
| Parameter | Suggested default | Meaning |
|-----------|-------------------|--------|
| `BASE_LAST_N_DAYS_RANGE_CONTRACTION` | 10 | “Last 2 weeks” for range contraction bonus |
| `ATR_STOP_LOWEST_LOW_DAYS` | 5 | Days for “lowest low” floor under ATR stop |

### 3.6 Eligibility / filters (optional)
| Parameter | Suggested default | Meaning |
|-----------|-------------------|--------|
| `MIN_REWARD_TO_RISK` | 0 (off) | If > 0, flag or exclude when R/R < value |
| `MIN_RS_PERCENTILE_ELIGIBILITY` | 0 (off) | If > 0, treat rs_percentile < value as ineligible or watch-only |

### 3.7 Base lookback
- Use `config.BASE_LOOKBACK_DAYS` in V2’s `scan_stock` for base identification, or add `BASE_LOOKBACK_DAYS_V2` in V2 config and use that. Avoids magic number `60`.

---

## 4. Summary

- **Strengths:** Structural gate, prior run, RS percentile, base-type pivot, ATR stop with floor, composite scoring, power rank, and deterministic output all support real trading and ranking.
- **High-value improvements:** Centralize extended thresholds (`EXTENDED_DISTANCE_PCT`, `EXTENDED_RISK_WARNING_PCT`), optionally clarify R/R at current price, and move breakout/base/volume score bands and key periods into config.
- **Config:** Add the parameters in §3 to `minervini_config_v2.py` (at least extended + breakout bands), and use them in `minervini_scanner_v2.py`, `minervini_report_v2.py`, and `08_chatgpt_new_positions_v2.py` so one config file drives scanner, report, and ChatGPT step.
