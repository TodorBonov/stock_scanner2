# Minervini Logic – How Your Scanner Works

This document explains the **Minervini SEPA (Stock Exchange Price Action)** logic implemented in your scanner: what it checks, why, and how it turns that into grades and entry/exit levels.

---

## What Is SEPA?

Your scanner follows **Mark Minervini’s SEPA methodology**: a five-part checklist to find stocks in a **Stage 2 uptrend** that are building a high-quality **consolidation base** and are ready (or about) to **break out** with volume. The idea is to buy strength (breakouts) with defined risk, not to buy dips or value.

The five parts are:

1. **Trend & Structure** – Uptrend confirmed (price above rising SMAs, near 52-week high).
2. **Base Quality** – A valid 3–8 week consolidation with tight price action and dry volume.
3. **Relative Strength** – Stock outperforming the benchmark; RSI and RS line show strength.
4. **Volume Signature** – Volume dries up in the base; expands on breakout.
5. **Breakout Rules** – Price clears the pivot by ≥2%; strong close and volume on breakout.

**Trend & Structure is non-negotiable.** If it fails, the stock gets an **F** and you walk away. The other four parts are scored; the number of failures drives the grade (A+, A, B, C) and position size (Full / Half / None).

---

## Part 1: Trend & Structure (Non-Negotiable)

**Goal:** Confirm the stock is in a **Stage 2 uptrend**, not in a base (Stage 1) or decline (Stage 3).

### How each parameter is calculated

| Parameter | Formula | Pass condition |
|-----------|---------|----------------|
| **SMA 50 / 150 / 200** | `SMA(n) = average(Close over last n days)` | `current_price > SMA_50` and `> SMA_150` and `> SMA_200` |
| **SMA order** | Compare latest values | `SMA_50 > SMA_150 > SMA_200` |
| **SMA slope** | Compare current SMA to value N days ago (N = 20, or 10 if insufficient data) | `SMA_now > SMA_{N_days_ago}` for all three |
| **Price from 52W low %** | `(current_price - 52W_low) / 52W_low × 100` | ≥ 30% |
| **Price from 52W high %** | `(52W_high - current_price) / 52W_high × 100` | ≤ 15% (fail if above); warning if < 10% (late-stage) |

52-week high/low use the last 252 trading days (or all available if fewer).

### Example (Trend & Structure)

- **Current close** = 51.80  
- **52W high** = 54.76, **52W low** = 27.05  
- **SMA 50** = 49.20, **SMA 150** = 45.10, **SMA 200** = 42.80  

Then:

- **Price from 52W low** = (51.80 − 27.05) / 27.05 × 100 = **91.5%** → pass (≥ 30%).
- **Price from 52W high** = (54.76 − 51.80) / 54.76 × 100 = **5.4%** → pass (≤ 15%); 5.4% < 10% → *warning* (very close to high).
- Price > all three SMAs and 50 > 150 > 200 → structure passes (slope check would compare to 20 days ago).

**Where it lives:** `minervini_scanner.py` → `_check_trend_structure()`. Thresholds in `config.py` (e.g. `PRICE_FROM_52W_LOW_MIN_PCT`, `PRICE_FROM_52W_HIGH_MAX_PCT`).

**If this part fails:** Grade is **F**, `meets_criteria` is False, position size is None. No other part can save it.

---

## Part 2: Base Quality

**Goal:** Ensure there is a **real consolidation base** (3–8 weeks, not too deep, tight candles, closes near highs, volume contracting).

### How each parameter is calculated

| Parameter | Formula | Pass condition |
|-----------|---------|----------------|
| **Base length (weeks)** | `trading_days_in_base / 5` | 3 ≤ weeks ≤ 8 |
| **Base depth %** | `(base_high - base_low) / base_high × 100` | ≤ 25% (elite ≤ 15%); warning if > 20% |
| **Base volatility** | `std(daily % change of Close)` over base period | — |
| **Avg volatility** | Same formula over last 252 days of full history | Base vol ≤ 1.5 × avg vol |
| **Close position %** (per day) | `(Close - Low) / (High - Low) × 100`; then **average** over base days | ≥ 50% |
| **Volume contraction** | `base_avg_volume / pre_base_volume` (pre-base = 20 days before base window) | < 0.95 for no warning (base drier than pre-base) |

**Base identification (how the “base” is found):**  
`_identify_base()` uses:

- **Low-volatility method:** Rolling 10-day std of daily % change; if ≥ 55% of the last 15+ days have volatility < 85% of average volatility, that recent window (e.g. 20 days) is the base. Then `base_depth_pct = (base_high - base_low) / base_high × 100`, `length_weeks = days / 5`.
- **Range method (fallback):** `range_30d = (High.max - Low.min) / Close.mean × 100` over last 30 days (and similarly 60 days). If range_30d ≤ 15% or range_60d ≤ 25%, that period is the base; depth and length computed as above.

Identification accepts 2–12 weeks and depth ≤ 35%; quality check then requires 3–8 weeks and depth ≤ 25%.

### Example (Base Quality)

- **Base:** high = 115.85, low = 100.33, 22 trading days.  
- **Base depth** = (115.85 − 100.33) / 115.85 × 100 = **13.4%** → pass (≤ 25%, and elite ≤ 15%).  
- **Base length** = 22 / 5 = **4.4 weeks** → pass (3–8).  
- **Close position:** suppose average of `(Close - Low) / (High - Low) × 100` over base = 62% → pass (≥ 50%).  
- **Volume:** base avg volume = 1.2M, pre-base avg = 1.5M → contraction = 1.2/1.5 = **0.80** → pass (base drier; no 95% warning).

**Where it lives:** `minervini_scanner.py` → `_check_base_quality()`, `_identify_base()`. Config: `config.py` (BASE_* and base-identification constants).

---

## Part 3: Relative Strength

**Goal:** Stock is **outperforming the benchmark** and has **strong momentum** (RSI, RS line).

### How each parameter is calculated

| Parameter | Formula | Pass condition |
|-----------|---------|----------------|
| **RSI(14)** | Standard RSI: `delta = Close.diff()`; `gain = mean(positive delta, 14d)`; `loss = mean(negative delta, 14d)`; `RS = gain/loss`; `RSI = 100 - 100/(1+RS)` | > 60 (at base start if base exists, else current) |
| **Relative strength** | Over 60 days (aligned dates): `stock_return = (1 + stock_returns).prod() - 1`, `bench_return` same; `relative_strength = stock_return - bench_return` | > 0 (outperforming) |
| **RS rating** | `min(100, max(0, 50 + relative_strength × 100))` | Higher = stronger (for display/sort) |
| **RS line** | `rs_line = stock_Close / benchmark_Close` (aligned); normalize to start at 100: `(rs_line / rs_line[0]) × 100` | — |
| **RS line from high %** | `(rs_high - current_rs) / rs_high × 100` over last 60 days | Fail if > 10% and not trending up; warning if > 5% (unless relax) |
| **RS trending up** | `current_rs > rs_line[20 days ago]` | Used with RS line decline (fail only if decline > 10% and not trending up, unless relax) |

**Relax option:** If `RS_RELAX_LINE_DECLINE_IF_STRONG` is True and stock outperforms and RSI ≥ 60, RS line decline does not cause failure.

### Example (Relative Strength)

- **RSI at base start** = 51.9 → **fail** (need > 60).  
- **Stock return (60d)** = +8%, **benchmark return** = +3% → **relative_strength** = 0.08 − 0.03 = **0.05** → pass (outperforming).  
- **RS line** normalized: recent high = 108, current = 100 → **RS from high** = (108 − 100) / 108 × 100 = **7.4%** → warning (> 5%); if not trending up and > 10% would fail; with relax + RSI ≥ 60 + outperforming, no failure.  
- **RS rating** = 50 + 5 = 55 (example).

**Where it lives:** `minervini_scanner.py` → `_check_relative_strength()`. Config: `config.py` (RSI_*, RS_*, RS_RELAX_*).

---

## Part 4: Volume Signature

**Goal:** Volume **contracts in the base** and **expands on breakout**.

### How each parameter is calculated

| Parameter | Formula | Pass condition |
|-----------|---------|----------------|
| **Pre-base volume** | `mean(Volume)` over 20 days immediately **before** the base window | — |
| **Base avg volume** | `mean(Volume)` over base days | — |
| **Volume contraction** | `base_avg_volume / pre_base_volume` | < 0.90 (failure if ≥ 0.90; base should be drier) |
| **Recent volume** (breakout check) | `mean(Volume)` over last 5 days | — |
| **Avg volume (20d)** | `mean(Volume)` over last 20 days | — |
| **Volume increase** (when in breakout) | `recent_volume / avg_volume_20d` | ≥ 1.4 when `current_price > base_high × 1.02` |
| **Heavy sell volume** (when not in breakout) | On down days (Close < Open): `mean(Volume)` of those days | Fail if > base_avg_volume × 1.5 |

“In breakout” here means `current_price > base_high × (1 + BUY_PRICE_BUFFER_PCT/100)` (e.g. > 2% above base high).

### Example (Volume Signature)

- **Pre-base volume** = 1.5M, **base avg volume** = 1.1M → **contraction** = 1.1/1.5 = **0.73** → pass (< 0.90).  
- **Current price** = 119, **base high** = 115.85 → 119 > 115.85×1.02 ≈ 118.17 → in breakout. **Recent 5d volume** = 2.1M, **20d avg** = 1.4M → **volume increase** = 2.1/1.4 = **1.5** → pass (≥ 1.4).  
- If not in breakout and down-day volume = 2.0M, base avg = 1.1M → 2.0 > 1.1×1.5 = 1.65 → **heavy sell volume** → failure.

**Where it lives:** `minervini_scanner.py` → `_check_volume_signature()`. Config: `config.py` (VOLUME_*, BREAKOUT_VOLUME_MULTIPLIER, etc.).

---

## Part 5: Breakout Rules

**Goal:** Confirm that price has **cleared the pivot decisively** and that the **breakout day** (or nearby) has a **strong close** and **volume expansion**.

### How each parameter is calculated

| Parameter | Formula | Pass condition |
|-----------|---------|----------------|
| **Pivot (clearance level)** | `base_high × (1 + PIVOT_CLEARANCE_PCT/100)` = base_high × 1.02 | — |
| **Cleared pivot?** | Any day in last 5 days with `Close ≥ pivot_clearance` | At least one such day |
| **Breakout day** | First day (from oldest to newest in that 5-day window) where close ≥ pivot | — |
| **Close position %** (breakout day) | `(Close - Low) / (High - Low) × 100` on that day | ≥ 70% (close in top 30% of range) |
| **Volume ratio** (breakout day) | `breakout_day_Volume / avg_Volume_20d` | ≥ 1.2 on breakout day **or** on one of the next 2 days if multi-day confirmation is on |

If no day in the last 5 clears the pivot, breakout rules **fail** and close position % is not computed (reported as 0).

### Example (Breakout Rules)

- **Base high** = 115.85 → **pivot clearance** = 115.85 × 1.02 = **118.17**.  
- **Last 5 days closes:** 117, 118.5, 119, 118, 120 → day with close 118.5 is first to clear 118.17 → **breakout day** found.  
- **Breakout day:** Low = 114, High = 120, Close = 118.5 → **close position** = (118.5 − 114) / (120 − 114) × 100 = **75%** → pass (≥ 70%).  
- **Breakout day volume** = 1.3M, **20d avg** = 1.0M → **volume ratio** = 1.3 → pass (≥ 1.2). If that day had 1.0M but the next day had 1.25M, with multi-day confirmation the 1.25M day would still satisfy the 1.2× rule.

**Where it lives:** `minervini_scanner.py` → `_check_breakout_rules()`. Config: `config.py` (PIVOT_CLEARANCE_PCT, BREAKOUT_LOOKBACK_DAYS, CLOSE_POSITION_MIN_PCT_BREAKOUT, VOLUME_EXPANSION_MIN, USE_MULTI_DAY_VOLUME_CONFIRMATION, VOLUME_CONFIRMATION_DAYS_AFTER_BREAKOUT).

---

## Grading and Position Sizing

**Grade is derived from the checklist:**

| Grade | Rule | meets_criteria | Position |
|-------|------|----------------|----------|
| **F** | Any failure in Trend & Structure (count = critical_failures) | False | None |
| **A+** | critical_failures = 0 and total_failures (other 4 parts) = 0 | True | Full |
| **A** | critical_failures = 0 and total_failures ≤ 2 | True | Half |
| **B** | critical_failures = 0 and total_failures ≤ 4 | False | Half |
| **C** | critical_failures = 0 and total_failures > 4 | False | None |

**Counts:** Each failure message in a part counts as 1; Trend & Structure failures are critical and force F; all other parts sum to `total_failures`.

### Example (Grading)

- Trend & Structure: 1 failure (“Price below 200 SMA”) → **F**, position None.  
- Trend passes; Base Quality 1 failure (depth warning); Relative Strength 0; Volume 0; Breakout 1 failure (volume) → **total_failures = 2** → **A**, half position, meets_criteria True.  
- Trend passes; 3 failures across base/RS/volume/breakout → **B**; 5 failures → **C**.

Config: `MAX_FAILURES_FOR_A` (2), `MAX_FAILURES_FOR_B` (4), `CRITICAL_FAILURE_GRADE` ("F") in `config.py`.

**Where it lives:** `minervini_scanner.py` → `_calculate_grade()`.

---

## Buy/Sell Prices and Pivot

**Pivot (entry level):** The **base high** from the identified base. That’s Minervini’s buy level: you buy when price **clears the pivot by ≥ 2%** (e.g. close ≥ pivot × 1.02).

### How each parameter is calculated

| Parameter | Formula | Notes |
|-----------|---------|-------|
| **Pivot price** | `base_high` from base_info (max High in base) | Entry level |
| **Buy price** | Always = pivot (whether pre-breakout or already above pivot) | — |
| **Stop loss** | `buy_price × (1 - STOP_LOSS_PCT/100)` | Default 5% below |
| **Profit target 1** | `buy_price × (1 + PROFIT_TARGET_1_PCT/100)` | Default 10% above |
| **Profit target 2** | `buy_price × (1 + PROFIT_TARGET_2_PCT/100)` | Default 45% above |
| **Distance to buy %** | `(current_price - buy_price) / buy_price × 100` | Negative = below pivot; positive = above |
| **Risk/reward ratio** | `(profit_target_1 - buy_price) / (buy_price - stop_loss)` | e.g. 10% / 5% = 2 |
| **In breakout?** | `current_price ≥ buy_price × (1 + BUY_PRICE_BUFFER_PCT/100)` | Typically 2% above pivot |

Optional: **ATR stop** = `buy_price - ATR(14) × ATR_STOP_MULTIPLIER` when `USE_ATR_STOP` is True.

### Example (Buy/Sell)

- **Pivot** = 115.85, **current price** = 112.88.  
- **Buy price** = 115.85. **Distance to buy** = (112.88 − 115.85) / 115.85 × 100 = **−2.56%** (pre-breakout).  
- **Stop loss** = 115.85 × 0.95 = **110.06**. **Profit target 1** = 115.85 × 1.10 = **127.44**; **Profit target 2** = 115.85 × 1.45 = **167.98**.  
- **Risk per share** = 115.85 − 110.06 = 5.79; **Reward to target 1** = 127.44 − 115.85 = 11.59 → **R/R** = 11.59 / 5.79 = **2.0**.

**Where it lives:** `minervini_scanner.py` → `_calculate_buy_sell_prices()`. Config: `config.py` (STOP_LOSS_PCT, PROFIT_TARGET_1_PCT, PROFIT_TARGET_2_PCT, BUY_PRICE_BUFFER_PCT, USE_ATR_STOP, ATR_*).

---

## Pre-Breakout View

Besides “already in breakout” names, the report can show **pre-breakout setups**: stocks that **pass the checklist well enough** (e.g. grade ≥ B) and have **not yet** cleared the pivot by 2%, but are **within a few % below the pivot** (e.g. within 5%). These are “ready to watch” for a breakout.

### How filtering and sort work

| Check | Meaning |
|-------|--------|
| No `error` in result | Scan completed successfully |
| Grade ≥ PRE_BREAKOUT_MIN_GRADE | e.g. B or better (B, A, A+) using order A+ > A > B > C > F |
| Has pivot | `buy_sell_prices.pivot_price` or `base_quality.details.base_high` present |
| Breakout not passed | `breakout_rules.passed` is False (no close ≥ 2% above base high in last 5 days) |
| Distance to buy | `distance_to_buy_pct` in **[−PRE_BREAKOUT_MAX_DISTANCE_PCT, 0]** (e.g. −5% to 0%) |
| Require base | If PRE_BREAKOUT_REQUIRE_BASE: `base_quality.details` exists with `base_high` |

**Sort key (best first):**  
`(base_depth_pct, volume_contraction, abs(distance_to_buy_pct), −rs_rating)`  
— Tighter base (lower depth), drier volume (lower contraction), closer to pivot (lower distance), higher RS (higher rating).

### Example (Pre-Breakout)

- Grade **A**, pivot **115.85**, current **112.88** → **distance_to_buy_pct** = −2.56%.  
- Breakout rules **not** passed (no close ≥ 118.17 in last 5 days).  
- −2.56% is in [−5%, 0%] → **included** in pre-breakout list.  
- Sort: base depth 13%, volume_contraction 0.80, |−2.56| = 2.56, rs_rating 70 → key (13, 0.80, 2.56, −70). A stock with depth 10%, contraction 0.70, distance −1.5%, rs_rating 80 would sort earlier (better).

**Where it lives:** `pre_breakout_utils.py` → `get_pre_breakout_stocks()`, sort key; config in `pre_breakout_config.py` only (PRE_BREAKOUT_*). Used in `04_generate_full_report.py` for the pre-breakout section.

---

## Data and Pipeline

- **Input to the scan:** Either `data/prepared_for_minervini.json` (from step 03: watchlist + cache + positions, with optional per-ticker benchmark) or legacy `data/cached_stock_data.json`.
- **Step 04** runs the Minervini scan (one `MinerviniScanner` per run; benchmark can be overridden per ticker from the prepared file), then writes summary report, detailed report, and `reports/scan_results_latest.json`.

So: **your Minervini logic** = Trend & Structure (non-negotiable) + Base Quality + Relative Strength + Volume Signature + Breakout Rules → grade and position size; pivot = base high; buy/sell/stop/targets from config; pre-breakout list = good grades, no breakout yet, within a few % below pivot. All thresholds and options are in `config.py` (and `pre_breakout_config.py` for the pre-breakout view). For exact formulas and config names, see **CALCULATIONS_REFERENCE.md**.
