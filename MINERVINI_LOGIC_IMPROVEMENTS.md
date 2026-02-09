# Minervini SEPA Logic – Improvements & Reference

This document is in two parts: **Part 1** describes the pure Minervini SEPA checklist logic and improvements in the scanner. **Part 2** describes how we search for and rank potential breakouts (pre-breakout view and report sections). All config is in `config.py` unless noted; formulas and config references are in **CALCULATIONS_REFERENCE.md**.

---

# Part 1: Pure Minervini Logic

## Overview

The scanner implements Mark Minervini’s five-part SEPA checklist. Trend & Structure is **non-negotiable** (one failure → grade F). The other four parts (Base Quality, Relative Strength, Volume Signature, Breakout Rules) are scored and combined into a grade (A+, A, B, C, F) and position size (Full, Half, None).

**Code:** `minervini_scanner.py` (with constants from `config.py`).

---

## 1.1 Trend & Structure

**Purpose:** Ensure the stock is in a Stage 2 uptrend.

**Checks:**
- Price above 50, 150, and 200 SMA.
- SMA order: 50 > 150 > 200, all sloping up.
- Price ≥ 30% above 52-week low.
- Price within 25% of 52-week high (warning if very close to high).

**Config:** `SMA_50_PERIOD`, `SMA_150_PERIOD`, `SMA_200_PERIOD`, `PRICE_FROM_52W_LOW_MIN_PCT`, `PRICE_FROM_52W_HIGH_MAX_PCT`, `PRICE_TOO_CLOSE_TO_HIGH_PCT`, `SMA_SLOPE_LOOKBACK_DAYS`.

**Improvements:** All thresholds are in `config.py`; no logic changes beyond centralisation.

---

## 1.2 Base Quality

**Purpose:** Valid consolidation base (3–8 weeks, depth ≤ 25%, tight closes, volume contracting).

**Checks:**
- Base length 3–8 weeks, depth ≤ 25% (≤ 15% elite).
- Base volatility ≤ 1.5× average volatility.
- Average close position in daily range ≥ 50%.
- Volume contraction in base (warning if base volume > 95% of pre-base).

**Base identification:** Done **once** per stock in `scan_stock()`, then the same `base_info` is passed to Base Quality, Volume Signature, and Breakout Rules. This avoids redundant work and keeps base definition consistent.

**Config:** `BASE_LENGTH_MIN_WEEKS`, `BASE_LENGTH_MAX_WEEKS`, `BASE_DEPTH_MAX_PCT`, `BASE_DEPTH_ELITE_PCT`, `BASE_VOLATILITY_MULTIPLIER`, `CLOSE_POSITION_MIN_PCT`, `VOLUME_CONTRACTION_WARNING_BASE`. Base identification uses the `*_IDENTIFY` and volatility/range constants in `config.py`.

**Improvements:** Percentage-based low-volatility check (e.g. 55% of days in window), advance-before-base check, and single base identification call are in place.

---

## 1.3 Relative Strength

**Purpose:** Stock outperforming benchmark; RSI > 60; RS line near new highs (or relaxed when stock is strong).

**Checks:**
- RSI(14) > 60 (checked at base start when base exists, else current).
- Stock outperforms benchmark over the lookback period.
- RS line not declining sharply from recent high (warning/fail thresholds in config).

**Benchmark:** Set per run (e.g. `02_generate_full_report.py --benchmark ^GDAXI` or `^GSPC`). Not in config; default in bot is `^GDAXI`.

**Config:** `RSI_PERIOD`, `RSI_MIN_THRESHOLD`, `RS_LINE_DECLINE_WARNING_PCT`, `RS_LINE_DECLINE_FAIL_PCT`, `RS_LOOKBACK_DAYS`, `RS_TREND_LOOKBACK_DAYS`, and **`RS_RELAX_LINE_DECLINE_IF_STRONG`** (trading improvement).

**Improvement – relax when strong:** When `RS_RELAX_LINE_DECLINE_IF_STRONG` is True and the stock **outperforms** the benchmark **and** RSI ≥ 60, a decline in the RS line from its recent high does **not** cause a failure. This avoids unfairly failing strong US names when the single benchmark is e.g. DAX. See **TRADING_IMPROVEMENTS_RATIONALE.md**.

---

## 1.4 Volume Signature

**Purpose:** Volume contracts in base; expansion on breakout when price is above base high.

**Checks:**
- Base volume vs pre-base (warning if not contracting).
- When price is in breakout zone (> 2% above base high), recent volume vs 20d average (≥ 1.4x in volume signature; breakout rules use 1.2x with optional multi-day window).

**Config:** `VOLUME_CONTRACTION_WARNING`, `BREAKOUT_VOLUME_MULTIPLIER`, `HEAVY_SELL_VOLUME_MULTIPLIER`, `RECENT_DAYS_FOR_VOLUME`, `AVG_VOLUME_LOOKBACK_DAYS`.

---

## 1.5 Breakout Rules

**Purpose:** Price has cleared pivot by ≥ 2% in the last N days; on that breakout day, close in top 30% of range; volume expansion on breakout day or within a short window after (configurable).

**Checks:**
- At least one close in last `BREAKOUT_LOOKBACK_DAYS` (5) ≥ `base_high * (1 + PIVOT_CLEARANCE_PCT/100)`.
- On **that** breakout day: close position in range ≥ 70%.
- Volume on breakout day ≥ `VOLUME_EXPANSION_MIN` (1.2x), **or** (when multi-day is enabled) on one of the next `VOLUME_CONFIRMATION_DAYS_AFTER_BREAKOUT` days.

**Config:** `PIVOT_CLEARANCE_PCT`, `BREAKOUT_LOOKBACK_DAYS`, `CLOSE_POSITION_MIN_PCT_BREAKOUT`, `VOLUME_EXPANSION_MIN`, **`USE_MULTI_DAY_VOLUME_CONFIRMATION`**, **`VOLUME_CONFIRMATION_DAYS_AFTER_BREAKOUT`**.

**Improvement – multi-day volume confirmation:** In practice, volume often spikes 1–2 days after pivot clearance. Requiring volume only on the same day gave a 0% breakout pass rate. With `USE_MULTI_DAY_VOLUME_CONFIRMATION = True` and `VOLUME_CONFIRMATION_DAYS_AFTER_BREAKOUT = 2`, volume can confirm on the breakout day or on either of the next two days (within the same lookback). Set `VOLUME_CONFIRMATION_DAYS_AFTER_BREAKOUT = 0` for strict same-day-only behaviour. See **TRADING_IMPROVEMENTS_RATIONALE.md**.

---

## 1.6 Grading and Position Size

**Logic:** Trend failure → F, position None. Otherwise count failures in the other four parts: 0 → A+, 1–2 → A, 3–4 → B, 5+ → C. A+ → Full position, A → Half, B/C → Half/None per config.

**Config:** `MAX_FAILURES_FOR_A`, `MAX_FAILURES_FOR_B`, `CRITICAL_FAILURE_GRADE`.

---

## 1.7 Buy/Sell Prices

Pivot = base high. Stop = pivot × (1 − `STOP_LOSS_PCT`/100). Targets = pivot × (1 + `PROFIT_TARGET_1_PCT`/100) and same for target 2. Distance to buy % = (current_price − buy_price) / buy_price × 100. Config: `STOP_LOSS_PCT`, `PROFIT_TARGET_1_PCT`, `PROFIT_TARGET_2_PCT`, `BUY_PRICE_BUFFER_PCT`.

---

# Part 2: Search for Potential Breakouts

## Overview

Besides the five-part checklist, the pipeline supports two **search** views that help find tradeable setups:

1. **BEST SETUPS** – A-grade stocks (A+ and A) ranked by setup quality (tighter base, drier volume, closer to pivot, higher RS).
2. **PRE-BREAKOUT SETUPS** – Stocks with a valid setup that have **not yet** broken out (within X% below pivot, grade ≥ B), ranked the same way.

Both use the same sort key (actionability) and rely on the scanner’s pivot and base info. Config for pre-breakout is separate so it doesn’t change core Minervini logic.

---

## 2.1 Pre-Breakout Filter

**Purpose:** List names that are “setup ready, not yet broken out” so you can watch for the breakout.

**Config:** All in **`pre_breakout_config.py`** (not `config.py`).

| Parameter | Meaning | Default |
|-----------|--------|--------|
| `PRE_BREAKOUT_MAX_DISTANCE_PCT` | Max % below pivot to include (e.g. 5 = within 5% below) | 5.0 |
| `PRE_BREAKOUT_MIN_GRADE` | Minimum grade (e.g. "B" = B, A, A+) | "B" |
| `PRE_BREAKOUT_REQUIRE_BASE` | Require base_quality.details (base_high/base_low) | True |
| `PRE_BREAKOUT_REQUIRE_NOT_BROKEN_OUT` | Require breakout_rules.passed == False | True |

**Filter (all must hold):**
- No `"error"` in result.
- `overall_grade` ≥ `PRE_BREAKOUT_MIN_GRADE`.
- Has pivot (`buy_sell_prices.pivot_price` or `base_quality.details.base_high`).
- `breakout_rules.passed` is False (no close ≥ 2% above base high in last 5 days).
- `distance_to_buy_pct` in [−`PRE_BREAKOUT_MAX_DISTANCE_PCT`, 0].
- If `PRE_BREAKOUT_REQUIRE_BASE`: `base_quality.details` exists with `base_high`.

**Code:** `pre_breakout_utils.py` → `get_pre_breakout_stocks()`.

---

## 2.2 Sort Key (Best Setups and Pre-Breakout)

Both BEST SETUPS and the pre-breakout list use the same **actionability** sort key so the best setups appear first:

- **Tuple:** `(base_depth_pct, volume_contraction, abs(distance_to_buy_pct), -rs_rating)`  
- **Meaning:** Tighter base (lower depth), drier volume (lower contraction), closer to pivot (smaller distance), higher RS (higher rating) = better.

**Code:** `pre_breakout_utils.py` → `actionability_sort_key()` (and alias `pre_breakout_sort_key`). Used by `02_generate_full_report.py` for both BEST SETUPS and PRE-BREAKOUT sections.

---

## 2.3 How This Ties to the Report

- **BEST SETUPS:** A and A+ stocks only, sorted by actionability. Shows names that already meet the checklist; some may have broken out (breakout rules passed), others not yet.
- **PRE-BREAKOUT:** Subset of scan results that pass the pre-breakout filter (grade ≥ B, has pivot, not broken out, within X% below pivot), sorted by actionability. Shown in the “PRE-BREAKOUT SETUPS” section of the summary report.

ChatGPT validation (03) can include both A-grade and pre-breakout data; see `03_chatgpt_validation.py` and the prompt construction.

---

## 2.4 Summary

| Item | Config | Code |
|------|--------|------|
| Pre-breakout filter | pre_breakout_config.py | pre_breakout_utils.get_pre_breakout_stocks() |
| Sort key (actionability) | — | pre_breakout_utils.actionability_sort_key() |
| Report sections | — | 02_generate_full_report.generate_summary_report() |

For formulas and every config key, see **CALCULATIONS_REFERENCE.md**. For why the trading-related options (multi-day volume, RS relax) exist, see **TRADING_IMPROVEMENTS_RATIONALE.md**.
