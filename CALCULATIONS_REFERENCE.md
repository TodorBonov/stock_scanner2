# Minervini SEPA Scanner – Calculations Reference

This document describes how all scanner calculations are made, with formulas and examples. It covers the **current pipeline** (five-part checklist, grading, buy/sell) and the **pre-breakout view** (additive only). Config for the current logic is in `config.py`; config for the pre-breakout view is in `pre_breakout_config.py` only.

---

## 1. Part 1: Trend & Structure

**Purpose:** Ensure the stock is in a Stage 2 uptrend (price above rising moving averages, within range of 52W high).

**Code:** `minervini_scanner.py` → `_check_trend_structure()`

| Metric | Formula / Rule | Config | Pass condition |
|--------|----------------|--------|-----------------|
| SMA 50/150/200 | Simple moving average of `Close` over 50, 150, 200 days | `SMA_50_PERIOD`, `SMA_150_PERIOD`, `SMA_200_PERIOD` (config.py) | Price > SMA 50, 150, 200 |
| SMA order | 50 > 150 > 200 | — | All three must be rising (slope check) |
| Price from 52W low | `(current - 52W_low) / 52W_low * 100` | `PRICE_FROM_52W_LOW_MIN_PCT` (30%) | ≥ 30% |
| Price from 52W high | `(52W_high - current) / 52W_high * 100` (or equivalent) | `PRICE_FROM_52W_HIGH_MAX_PCT` (15%) | ≤ 15% (Minervini: within 15% of 52W high; warning if very close to high) |

**Example:** Close = 51.80, 52W high = 54.76, 52W low = 27.05  
→ From 52W high = (54.76 − 51.80) / 54.76 × 100 ≈ **5.4%** (within 15%; warning if &lt; ~10%).

---

## 2. Part 2: Base Quality

**Purpose:** Valid consolidation base (3–8 weeks, depth ≤ 25%, tight closes, volume contracting).

**Code:** `minervini_scanner.py` → `_check_base_quality()`, `_identify_base()`

| Metric | Formula / Rule | Config | Pass condition |
|--------|----------------|--------|-----------------|
| Base length | Identified base length in weeks (e.g. trading_days / 5) | `BASE_LENGTH_MIN_WEEKS` (3), `BASE_LENGTH_MAX_WEEKS` (8) | 3–8 weeks |
| Base depth % | `(base_high - base_low) / base_high * 100` | `BASE_DEPTH_MAX_PCT` (25), `BASE_DEPTH_ELITE_PCT` (15) | ≤ 25% (elite ≤ 15%) |
| Base volatility | Std dev of daily returns in base vs full-period avg | `BASE_VOLATILITY_MULTIPLIER` (1.5) | Base vol ≤ 1.5× avg |
| Avg close position | Per day: `(Close - Low) / (High - Low) * 100`; then average over base | `CLOSE_POSITION_MIN_PCT` (50) | ≥ 50% |
| Volume contraction | `base_avg_volume / pre_base_volume` | `VOLUME_CONTRACTION_WARNING_BASE` (0.95) | &lt; 0.95 warning |

**Example:** Base high = 115.85, base low = 100.33  
→ Base depth = (115.85 − 100.33) / 115.85 × 100 ≈ **13.4%** (pass; elite if &lt; 15%).

---

## 3. Part 3: Relative Strength

**Purpose:** Stock outperforming benchmark; RSI &gt; 60; RS line not declining sharply (or relaxed when stock is strong).

**Code:** `minervini_scanner.py` → `_check_relative_strength()`

**Benchmark:** Set per run via script args (e.g. `02_generate_full_report.py --benchmark ^GDAXI` or `^GSPC`). Not stored in config; default in bot is `^GDAXI`. (Script numbers match execution order.)

| Metric | Formula / Rule | Config | Pass condition |
|--------|----------------|--------|-----------------|
| RSI(14) | Standard RSI on 14-day close | `RSI_MIN_THRESHOLD` (60) | &gt; 60 |
| RS line | Stock return vs benchmark return over lookback | `RS_LOOKBACK_DAYS` (60), `RS_LINE_DECLINE_WARNING_PCT` (5), `RS_LINE_DECLINE_FAIL_PCT` (10) | Outperforming; RS line not &gt; 10% below recent high (or see relax below) |
| RS rating | Normalized relative strength (e.g. 0–100) | — | Higher = stronger |
| **Relax when strong** | When outperforming **and** RSI ≥ 60, RS line decline is not counted as failure | `RS_RELAX_LINE_DECLINE_IF_STRONG` (True) | If True: no failure for “RS line X% below high” when stock outperforms and RSI ≥ 60 |

**Example:** RSI = 51.9 → **Fail** (need &gt; 60). RS rating 100 with outperforming = pass on RS line. With relax enabled, a US name vs DAX that outperforms and has RSI 65 may still pass even if RS line is 8% below high.

---

## 4. Part 4: Volume Signature

**Purpose:** Volume contracts in base; can check expansion on breakout.

**Code:** `minervini_scanner.py` → `_check_volume_signature()`

| Metric | Formula / Rule | Config | Pass condition |
|--------|----------------|--------|-----------------|
| Volume contraction | Base avg volume / pre-base volume | `VOLUME_CONTRACTION_WARNING` (0.9) | &lt; 0.9 ideal |
| Volume increase (breakout) | Recent volume / 20d avg volume | `BREAKOUT_VOLUME_MULTIPLIER` (1.4) | ≥ 1.4x for breakout |

**Volume thresholds (two roles):** Volume Signature uses **1.4x** when the scanner detects price already &gt; 2% above base high (ongoing breakout confirmation). Breakout Rules use **1.2x** with the multi-day confirmation window for the specific breakout day. They serve different roles; see MINERVINI_LOGIC_IMPROVEMENTS.md.

---

## 5. Part 5: Breakout Rules

**Purpose:** Price has cleared pivot by ≥ 2% in last 5 days; breakout day close in top 30% of range; volume expansion (on breakout day or within configurable days after).

**Code:** `minervini_scanner.py` → `_check_breakout_rules()`

| Metric | Formula / Rule | Config | Pass condition |
|--------|----------------|--------|-----------------|
| Pivot clearance | Any close in last N days ≥ `base_high * (1 + PIVOT_CLEARANCE_PCT/100)` | `PIVOT_CLEARANCE_PCT` (2), `BREAKOUT_LOOKBACK_DAYS` (5) | At least one day closes ≥ 2% above base high |
| Close position on breakout | On that day: `(Close - Low) / (High - Low) * 100` | `CLOSE_POSITION_MIN_PCT_BREAKOUT` (70) | ≥ 70% (close in top 30% of range) |
| Volume ratio | Breakout day volume / 20d avg volume, or **any day from breakout day through next N days** | `VOLUME_EXPANSION_MIN` (1.2), `USE_MULTI_DAY_VOLUME_CONFIRMATION` (True), `VOLUME_CONFIRMATION_DAYS_AFTER_BREAKOUT` (2) | ≥ 1.2x on breakout day, or on one of the next 2 days when multi-day is enabled |

**Multi-day volume confirmation (trading improvement):** When `USE_MULTI_DAY_VOLUME_CONFIRMATION` is True and `VOLUME_CONFIRMATION_DAYS_AFTER_BREAKOUT` > 0, volume is allowed to confirm on the **breakout day** or on any of the **next N calendar days** (within the same lookback window). So if day 1 clears pivot with a strong close but volume is only 1.0x, and day 2 or 3 has volume ≥ 1.2x, the breakout passes. Set `VOLUME_CONFIRMATION_DAYS_AFTER_BREAKOUT = 0` for strict same-day-only behaviour.

**Example (no breakout yet):** Base high = 115.85 → pivot clearance = 115.85 × 1.02 = 118.17. If no close in last 5 days ≥ 118.17, `clears_pivot` = False and **Close Position on Breakout** is shown as **0.0%** (placeholder: not computed because no breakout day was found).

**Example (with breakout day):** Breakout day Low = 114, High = 120, Close = 118.5  
→ Close position = (118.5 − 114) / (120 − 114) × 100 = **75%** (pass ≥ 70%). Volume can pass on that day or on the next 1–2 days if multi-day confirmation is enabled.

---

## 6. Grading and “Meets Criteria”

**Code:** `minervini_scanner.py` → `_calculate_grade()`

| Grade | Rule | meets_criteria |
|-------|------|----------------|
| F | Trend & Structure failed (critical) | False |
| A+ | Zero failures in other four parts | True |
| A | 1–2 failures (non–trend) | True |
| B | 3–4 failures | False |
| C | 5+ failures | False |

**Config:** `MAX_FAILURES_FOR_A` (2), `MAX_FAILURES_FOR_B` (4), `CRITICAL_FAILURE_GRADE` ("F") in `config.py`.

---

## 7. Buy/Sell Prices and Distance to Pivot

**Code:** `minervini_scanner.py` → `_calculate_buy_sell_prices()`

| Metric | Formula | Config |
|--------|---------|--------|
| Pivot (buy price) | Base high from base_info | — |
| Stop loss | `pivot * (1 - STOP_LOSS_PCT/100)` | `STOP_LOSS_PCT` (5) |
| Profit target 1 | `pivot * (1 + PROFIT_TARGET_1_PCT/100)` | `PROFIT_TARGET_1_PCT` (10) |
| Profit target 2 | `pivot * (1 + PROFIT_TARGET_2_PCT/100)` | `PROFIT_TARGET_2_PCT` (45) |
| Distance to buy % | `(current_price - buy_price) / buy_price * 100` | — |

**Example:** Pivot = 115.85, current = 112.88  
→ Distance to buy = (112.88 − 115.85) / 115.85 × 100 ≈ **−2.6%** (below pivot; pre-breakout).

---

## 8. Pre-Breakout View (Additive Only)

**Purpose:** List stocks that have a valid setup but have **not yet** broken out (conditions that predict the breakout).

**Config:** All in `pre_breakout_config.py` (not `config.py`).

| Parameter | Meaning | Default |
|-----------|--------|--------|
| `PRE_BREAKOUT_MAX_DISTANCE_PCT` | Max % below pivot to include (e.g. 5 = within 5% below) | 5.0 |
| `PRE_BREAKOUT_MIN_GRADE` | Minimum grade (e.g. "B" = B, A, A+) | "B" |
| `PRE_BREAKOUT_REQUIRE_BASE` | Require base_quality.details (base_high/base_low) | True |
| `PRE_BREAKOUT_REQUIRE_NOT_BROKEN_OUT` | Require breakout_rules.passed == False | True |

**Filter (all must hold):**

1. No `"error"` in result.
2. `overall_grade` ≥ `PRE_BREAKOUT_MIN_GRADE` (e.g. B or better).
3. Has pivot (from `buy_sell_prices.pivot_price` or `base_quality.details.base_high`).
4. `breakout_rules.passed` is False (no close ≥ 2% above base high in last 5 days).
5. `distance_to_buy_pct` in **[−PRE_BREAKOUT_MAX_DISTANCE_PCT, 0]** (below pivot but within 5%).
6. If `PRE_BREAKOUT_REQUIRE_BASE`: `base_quality.details` exists with `base_high`.

**Sort key (best first):**  
`(base_depth_pct, volume_contraction, abs(distance_to_buy_pct), -rs_rating)`  
— Tighter base, drier volume, closer to pivot, higher RS.

**Code:** `pre_breakout_utils.py` → `get_pre_breakout_stocks()`, `pre_breakout_sort_key()`.

**Example:** Stock with grade A, pivot 115.85, current 112.88 → distance −2.6%. Within 5% below pivot and breakout not triggered → included in pre-breakout list.

---

## 9. Code Reference Summary

| Item | File | Function / Section |
|------|------|--------------------|
| Trend & Structure | minervini_scanner.py | _check_trend_structure() |
| Base Quality | minervini_scanner.py | _check_base_quality(), _identify_base() |
| Relative Strength | minervini_scanner.py | _check_relative_strength() |
| Volume Signature | minervini_scanner.py | _check_volume_signature() |
| Breakout Rules | minervini_scanner.py | _check_breakout_rules() |
| Grading | minervini_scanner.py | _calculate_grade() |
| Buy/Sell, distance_to_buy_pct | minervini_scanner.py | _calculate_buy_sell_prices() |
| Current pipeline config | config.py | All constants for above |
| Pre-breakout config | pre_breakout_config.py | PRE_BREAKOUT_* only |
| Pre-breakout filter/sort | pre_breakout_utils.py | get_pre_breakout_stocks(), pre_breakout_sort_key() |
| Summary report (BEST SETUPS, PRE-BREAKOUT) | 02_generate_full_report.py | generate_summary_report(), pre-breakout section |
| ChatGPT (A-grade + pre-breakout) | 04_chatgpt_validation.py | create_chatgpt_prompt(..., pre_breakout_data), main() |

---

## 10. Trading Improvements (Configurable)

The following options in `config.py` tune behaviour for real-world trading without changing core Minervini logic:

| Config | Section | Effect |
|--------|---------|--------|
| `USE_MULTI_DAY_VOLUME_CONFIRMATION` | Breakout | When True, volume confirmation can occur on breakout day or in the next N days. |
| `VOLUME_CONFIRMATION_DAYS_AFTER_BREAKOUT` | Breakout | Number of days after breakout day to look for volume ≥ `VOLUME_EXPANSION_MIN` (0 = same day only). |
| `RS_RELAX_LINE_DECLINE_IF_STRONG` | Relative Strength | When True, if stock outperforms benchmark and RSI ≥ 60, RS line decline from high does not cause failure. |
| `BREAKOUT_LOOKBACK_DAYS_FOR_REPORT` | Breakout | Days to scan for "last close above pivot" (reporting only; default 21). |
| `USE_ATR_STOP` | Buy/Sell | When True, report also shows ATR-based stop (stop_loss_atr). |
| `ATR_PERIOD`, `ATR_STOP_MULTIPLIER` | Buy/Sell | ATR(14) and stop = buy_price − ATR × multiplier. |
| `REQUIRE_MARKET_ABOVE_200SMA` | Market | When True, report shows market regime (benchmark above/below 200 SMA). |
| `BASE_MAX_DAYS_OLD` | Pre-breakout | When &gt;0, exclude bases older than N days from pre-breakout list (0 = off). |

Benchmark is set per run (e.g. `--benchmark ^GSPC` for US). **Per-ticker benchmark:** `benchmark_mapping.get_benchmark(ticker, default)` is used by the report script so mixed US/EU watchlists get the right benchmark per symbol. **Position sizing:** `position_sizing.py` suggests $ and shares from account size and risk % per trade. See **TRADING_IMPROVEMENTS_RATIONALE.md** for why these options exist.

---

*This document describes the logic as implemented. For Minervini methodology background, see README and MINERVINI_LOGIC_IMPROVEMENTS.md.*
