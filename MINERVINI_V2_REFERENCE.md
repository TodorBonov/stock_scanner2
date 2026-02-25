# Minervini SEPA Scanner V2 – Reference

This document describes the V2 engine: variables (with current values), **calculations for every metric** (eligibility, prior run, base type, pivot, component scores, composite, grade, stop, R/R, power rank), how relative strength is derived, and a **full RWE.DE example** with both **LLM (JSON) and user report** outputs.

---

## 1. What V2 Changes

| Aspect | Original | V2 |
|--------|----------|-----|
| Eligibility | Implicit in checklist | **Structural gate**: trend + valid base + liquidity + min price. If not passed → REJECT, no scoring. |
| Grading | Failure count (0–2 = A, etc.) | **Weighted composite score** 0–100; grade from score bands. |
| Prior run | Not required | **Required**: base must follow ≥25% advance (configurable). |
| RS | Binary pass/fail vs benchmark | **RS percentile** across universe (0–100) + 3M return. |
| Base | Single “base” window | **Base type**: flat_base, cup, high_tight_flag, standard_base. |
| Pivot | `max(High)` of base | **Base-type-aware**: flat (with optional spike filter), cup = handle high, HTF = flag high. |
| Trend score | Binary (0 or 100) | **Graded** by % above 200 SMA: ≥30%→100, 15–30%→70, 5–15%→40, 0–5%→15. |
| Base score | Depth + prior run | **+Elite bonuses**: +10 range contraction (last 2w), +10 last 2 weekly closes in upper 40% of base. |
| Stop | Fixed % or optional ATR | **ATR stop default on**: max(pivot − ATR×mult, lowest low of breakout week). |
| Ranking | Composite only | **Power rank**: 0.5×rs_percentile + 0.5×min(prior_run_pct, 100). |
| Output | Checklist + buy_sell | **Single JSON** per ticker (eligible, grade, composite_score, power_rank, base, relative_strength, breakout, risk). |

---

## 2. Variables and Current Values

All V2-specific parameters live in **`minervini_config_v2.py`**. Values below are as of the last update.

### 2.1 Structural eligibility

| Variable | Current value | Meaning |
|----------|----------------|---------|
| `MIN_AVG_DOLLAR_VOLUME_20D` | 1,000,000 | Min 20-day avg (Price × Volume) to be eligible ($). |
| `MIN_PRICE_THRESHOLD` | 5.0 | Min share price ($); below → ineligible. |

### 2.2 Prior run

| Variable | Current value | Meaning |
|----------|----------------|---------|
| `MIN_PRIOR_RUN_PCT` | 25.0 | Min prior run %; `(base_high - lowest_3m_before_base) / lowest_3m_before_base * 100`. |
| `PRIOR_RUN_LOOKBACK_TRADING_DAYS` | 63 | Lookback (trading days) before base start for “lowest low”. |

### 2.3 RS percentile

| Variable | Current value | Meaning |
|----------|----------------|---------|
| `RS_3M_LOOKBACK_DAYS` | 63 | Days for 3M return used in percentile. |
| `RS_6M_LOOKBACK_DAYS` | 126 | Optional 6M return (for future use). |

### 2.4 Base type classification

| Variable | Current value | Meaning |
|----------|----------------|---------|
| `BASE_TYPE_FLAT_MAX_DEPTH_PCT` | 15.0 | Depth ≤ 15% → **flat_base**. |
| `BASE_TYPE_HIGH_TIGHT_PRIOR_RUN_PCT` | 100.0 | Prior run ≥ 100% (for high_tight_flag). |
| `BASE_TYPE_HIGH_TIGHT_MAX_DEPTH_PCT` | 25.0 | Depth ≤ 25% for high_tight_flag. |
| `BASE_TYPE_HIGH_TIGHT_MAX_WEEKS` | 5.0 | Base length ≤ 5 weeks for high_tight_flag. |
| (cup) | — | Depth > 15% and ≤ 25%, not HTF → **cup**. |
| (standard_base) | — | Fallback when none of the above. |

### 2.5 Pivot by base type

| Variable | Current value | Meaning |
|----------|----------------|---------|
| `PIVOT_SPIKE_FILTER_ENABLED` | True | For flat/standard: drop bars with High > mean + K×std before taking max. |
| `PIVOT_SPIKE_STD_MULTIPLIER` | 2.0 | K in “mean + K×std”. |
| `PIVOT_IGNORE_SPIKE_WITHIN_LAST_N_DAYS` | 5 | Last N days of base never filtered (near breakout). |
| `PIVOT_HANDLE_DAYS` | 7 | For **cup**: handle = last N trading days; pivot = max(High) of handle. |

### 2.6 Composite scoring weights

| Variable | Current value | Meaning |
|----------|----------------|---------|
| `WEIGHT_TREND_STRUCTURE` | 0.20 | 20% of composite. |
| `WEIGHT_BASE_QUALITY` | 0.25 | 25%. |
| `WEIGHT_RELATIVE_STRENGTH` | 0.25 | 25%. |
| `WEIGHT_VOLUME_SIGNATURE` | 0.15 | 15%. |
| `WEIGHT_BREAKOUT_QUALITY` | 0.15 | 15%. |

Each component is scored 0–100; composite = sum(weight × score).

### 2.7 Trend score (graded)

| Variable | Current value | Meaning |
|----------|----------------|---------|
| `TREND_PCT_ABOVE_200_TIER1` | 30.0 | Price ≥30% above 200 SMA → trend score **100**. |
| `TREND_PCT_ABOVE_200_TIER2` | 15.0 | 15–30% above → **70**. |
| `TREND_PCT_ABOVE_200_TIER3` | 5.0 | 5–15% above → **40**. |
| `TREND_PCT_ABOVE_200_TIER4` | 0.0 | 0–5% above → **15**; below 0 → **0**. |

### 2.8 Base quality bonuses

| Variable | Current value | Meaning |
|----------|----------------|---------|
| `BASE_BONUS_RANGE_CONTRACTION_LAST_2W` | 10 | +10 if last 2 weeks of base have tight range vs full base. |
| `BASE_BONUS_WEEKLY_CLOSES_UPPER_40` | 10 | +10 if last 2 weekly closes are in upper 40% of base range. |
| `BASE_RANGE_CONTRACTION_RATIO_MAX` | 0.5 | last_2w_range / base_range < this → contraction bonus. |

### 2.9 Power rank

| Variable | Current value | Meaning |
|----------|----------------|---------|
| `POWER_RANK_PRIOR_RUN_CAP` | 100.0 | prior_run_pct scaled as min(prior_run_pct, cap). |
| Formula | — | `power_rank = 0.5 × rs_percentile + 0.5 × prior_run_scaled`. |

### 2.10 Grade bands

| Variable | Current value | Grade |
|----------|----------------|--------|
| `GRADE_A_PLUS_MIN_SCORE` | 85.0 | composite ≥ 85 → **A+** |
| `GRADE_A_MIN_SCORE` | 75.0 | 75 ≤ composite < 85 → **A** |
| `GRADE_B_MIN_SCORE` | 65.0 | 65 ≤ composite < 75 → **B** |
| `GRADE_C_MIN_SCORE` | 55.0 | 55 ≤ composite < 65 → **C** |
| — | — | composite < 55 → **REJECT** |

### 2.11 ATR stop

| Variable | Current value | Meaning |
|----------|----------------|---------|
| `USE_ATR_STOP_V2` | **True** | Stop = max(pivot − ATR×mult, lowest low of breakout week). |
| `ATR_PERIOD_V2` | 14 | ATR period. |
| `ATR_STOP_MULTIPLIER_V2` | 1.5 | Multiplier on ATR. |

### 2.12 Output paths

| Variable | Current value |
|----------|----------------|
| `REPORTS_DIR_V2` | `reports` |
| `SCAN_RESULTS_V2_LATEST` | `reports/scan_results_v2_latest.json` |
| `USER_REPORT_SUBDIR_V2` | `v2` |
| `SEPA_USER_REPORT_PREFIX` | `sepa_scan_user_report_` |
| `SEPA_CSV_PREFIX` | `sepa_scan_summary_` |

---

## 3. How relative strength is calculated

V2 output shows three RS-related numbers: **rs_3m**, **rs_percentile**, and **rsi_14**. They come from different calculations.

### 3.1 RS vs benchmark (under the hood)

The scanner still uses the **original** relative-strength-vs-benchmark logic (for checklist pass/fail and RS line). It lives in `data_provider.calculate_relative_strength()` and `minervini_scanner._check_relative_strength()`:

- **Period:** Last `period` trading days (default 252 in data provider; 60 days in scanner’s manual fallback, from `config.RS_LOOKBACK_DAYS`).
- **Aligned returns:** Stock and benchmark daily returns are aligned by date; only common dates in the last `period` days are used.
- **Cumulative returns:**
  - `stock_cumulative = (1 + stock_period).prod() - 1`
  - `benchmark_cumulative = (1 + benchmark_period).prod() - 1`
- **Relative strength (raw):**  
  `relative_strength = stock_cumulative - benchmark_cumulative`  
  (e.g. +0.05 = stock up 5% more than benchmark over the period.)
- **RS rating (0–100):**  
  `rs_rating = min(100, max(0, 50 + relative_strength * 100))`  
  So 50 = in line with benchmark; >50 = outperforming; <50 = underperforming.

This is used for the checklist (e.g. “Stock not outperforming benchmark”) and for the RS line / slope checks. V2 does **not** use this number in the composite; it uses **rs_percentile** and **rs_3m** instead.

### 3.2 RS 3M return (V2: `rs_3m`)

Used only in V2, for **universe comparison**:

- **Lookback:** Last **63** trading days (`minervini_config_v2.RS_3M_LOOKBACK_DAYS`).
- **Formula:**  
  `start_price = Close[−63]`  
  `end_price = Close[−1]`  
  `rs_3m = (end_price / start_price − 1) × 100`  
  So it’s the **total return %** over that window (no benchmark).

**Where it’s used:** In `scan_universe()`, Phase 1: for every ticker we compute this 3M return, then we rank them to get **rs_percentile**.

### 3.3 RS percentile (V2: `rs_percentile`)

- **Input:** The 3M return of the stock and the list of 3M returns of **all** tickers in the scan.
- **Formula (strict percentile rank):**  
  `rs_percentile = (count of tickers with 3M return **strictly less** than this stock’s) / n × 100`  
  So 0 = worst in universe, 100 = best; 50 = half did worse.
- **Code:** `_percentile_rank(value, universe_values)` in `minervini_scanner_v2.py`.

**Use in V2:** This 0–100 value is the **RS component score** in the composite (when `rs_percentile` is provided from the universe pass). So relative strength in the grade is “where this stock ranks in 3M return vs the rest of the scan list,” not vs a single index.

### 3.4 RSI(14) (`rsi_14`)

Standard **Relative Strength Index** on closing prices:

- **Period:** 14 days (`config.RSI_PERIOD`).
- **Formula:**  
  - `delta = Close.diff()`  
  - `gain = mean of positive deltas over 14 days`  
  - `loss = mean of absolute negative deltas over 14 days`  
  - `RS = gain / loss` (if loss is 0, RSI is 100)  
  - `RSI = 100 − 100 / (1 + RS)`

So RSI is 0–100: >70 often “overbought,” <30 “oversold.” Minervini uses it as “RSI > 60 before breakout” (checked at base start or current in the original checklist). V2 just reports the **current** RSI as `rsi_14` in the JSON/report; it does not change the composite (that uses `rs_percentile`).

---

## 4. Calculations for all metrics

Formulas and logic for every value in the V2 output. Thresholds come from `config.py` (trend, base, volume, breakout, stop) and `minervini_config_v2.py` (eligibility, prior run, base type, pivot, weights, grades).

### 4.1 Structural eligibility

- **stage_2:** Parent `_check_trend_structure(hist)`: price > SMA 50, 150, 200; SMA 50 > 150 > 200; SMAs sloping up; price ≥ 30% above 52W low; price within 15% of 52W high. All must pass.
- **has_valid_base:** `base_info` exists and has `length_weeks` (base identified by low-vol or range method, 2–12 weeks, depth ≤ 35%).
- **liquidity_ok:** `avg_dollar_volume_20d = mean(Close × Volume)` over last 20 days; pass if ≥ `MIN_AVG_DOLLAR_VOLUME_20D` (1,000,000).
- **price_threshold_ok:** `current_price = Close[-1]`; pass if ≥ `MIN_PRICE_THRESHOLD` (5.0).
- **eligible:** `stage_2 and has_valid_base and liquidity_ok and price_threshold_ok`. If not eligible, output is REJECT with composite 0; no further scoring.

### 4.2 Prior run

- **Lookback:** Last `PRIOR_RUN_LOOKBACK_TRADING_DAYS` (63) trading days **before** base start date.
- **lowest_low_3m_before_base:** `min(Low)` over that window.
- **prior_run_pct:** `(base_high - lowest_low_3m_before_base) / lowest_low_3m_before_base * 100`.
- **Base quality:** If `prior_run_pct < MIN_PRIOR_RUN_PCT` (25), base quality fails and base component score is penalised (e.g. −20).

### 4.3 Base type

- **depth_pct:** `(base_high - base_low) / base_high * 100` over identified base.
- **length_weeks:** `trading_days_in_base / 5`.
- **flat_base:** `depth_pct ≤ 15`.
- **high_tight_flag:** `prior_run_pct ≥ 100 and depth_pct ≤ 25 and length_weeks ≤ 5`.
- **cup:** `15 < depth_pct ≤ 25` and not high_tight_flag.
- **standard_base:** fallback.

### 4.4 Pivot by base type

- **flat_base / standard_base:** Take base `High` series; if spike filter on, drop bars with `High > mean(High) + PIVOT_SPIKE_STD_MULTIPLIER * std(High)` except in last `PIVOT_IGNORE_SPIKE_WITHIN_LAST_N_DAYS` (5). Pivot = `max(High)` of remaining (or whole base if filter off). Source: `flat_max` or `flat_max_spike_filtered`.
- **cup:** Handle = last `PIVOT_HANDLE_DAYS` (7) trading days of base. Pivot = `max(High)` of handle. Source: `cup_handle`.
- **high_tight_flag:** Pivot = `max(High)` of base (flag). Source: `htf_flag`.

### 4.5 Component scores (0–100 each)

- **trend_score:** If trend_structure not passed → 0. Else graded by % above 200 SMA: `pct_above_200 = (current_price - sma_200) / sma_200 * 100`. ≥30% → 100; 15–30% → 70; 5–15% → 40; 0–5% → 15; &lt;0 → 0.
- **base_score:** If base_quality failed, 0. Else start at 80; +10 if depth ≤ 15, +5 if depth ≤ 20; +10 if prior_run_pct ≥ 25, else −20; +10 if range contraction (last 2w range / base range ≤ 0.5); +10 if last 2 weekly closes in upper 40% of base range; then clamp to [0, 100].
- **rs_score:** Equals `rs_percentile` when provided from universe; else RS details `rs_rating` or 50.
- **volume_score:** 100 if volume_signature passed; else 70 if contraction < 0.8, 50 if < 0.95, else 0.
- **breakout_score:** 100 if breakout_rules passed; else 80 if −3 ≤ distance_to_pivot_pct ≤ 0; 60 if −5 ≤ distance < −3; 30 if distance > 5; else 50.

### 4.6 Composite and grade

- **composite_score:** `0.20*trend + 0.25*base + 0.25*rs + 0.15*volume + 0.15*breakout`, rounded to 1 decimal.
- **grade:** composite ≥ 85 → A+; ≥ 75 → A; ≥ 65 → B; ≥ 55 → C; < 55 → REJECT.

### 4.7 Breakout and risk

- **distance_to_pivot_pct:** `(current_price - pivot_price) / pivot_price * 100`. Negative = below pivot.
- **in_breakout:** `current_price >= pivot_price * (1 + BUY_PRICE_BUFFER_PCT/100)` (e.g. ≥ 2% above pivot).
- **stop_price (fixed):** `pivot_price * (1 - STOP_LOSS_PCT/100)` with `STOP_LOSS_PCT = 5` → 5% below pivot.
- **stop_price (ATR):** If `USE_ATR_STOP_V2` True: `max(pivot_price - ATR_14 * ATR_STOP_MULTIPLIER, lowest_low_of_last_5_days)`.
- **risk_per_share:** `pivot_price - stop_price`.
- **reward_to_risk:** `(profit_target_1 - pivot_price) / risk_per_share` where `profit_target_1 = pivot_price * (1 + PROFIT_TARGET_1_PCT/100)` (e.g. 10%). With ATR stop, risk is smaller so R/R is often &gt; 2.
- **power_rank:** `0.5 × rs_percentile + 0.5 × min(prior_run_pct, 100)`. Used for ranking elite RS + prior-run combos.

---

## 5. Worked example: RWE.DE

Example from a live V2 run (RWE.DE in a small universe). Illustrates **graded trend**, **ATR stop**, and **power_rank**.

- **Eligible:** Yes (trend, base, liquidity, price all pass).
- **Base:** flat_base, 6 weeks, 12.7% deep. Prior run 39.1% (≥ 25%).
- **Pivot:** flat_max_spike_filtered → **54.76** (example run; varies with data).
- **Trend score:** Price in 15–30% band above 200 SMA → **70** (not 100).
- **Component scores:** Trend 70, Base 100, RS 50, Volume 100, Breakout 50.  
  **Composite** = 0.20×70 + 0.25×100 + 0.25×50 + 0.15×100 + 0.15×50 = **74.0** → **B** (65 ≤ 74 &lt; 75).
- **Stop:** ATR method → stop **52.54**, risk_per_share **2.22**, **R/R 2.47**.
- **Power rank:** 0.5×50 + 0.5×39.1 = **44.6**.

---

## 6. Full example: RWE.DE — LLM output and user report

**LLM/engine output** (single ticker object in `reports/scan_results_v2_latest.json`):

```json
{
  "ticker": "RWE.DE",
  "eligible": true,
  "grade": "B",
  "composite_score": 74.0,
  "trend_score": 70.0,
  "base_score": 100.0,
  "rs_score": 50.0,
  "volume_score": 100.0,
  "breakout_score": 50.0,
  "power_rank": 44.6,
  "base": {
    "type": "flat_base",
    "length_weeks": 6.0,
    "depth_pct": 12.7,
    "prior_run_pct": 39.1
  },
  "relative_strength": {
    "rs_3m": 14.5898,
    "rs_percentile": 50.0,
    "rsi_14": 39.0
  },
  "breakout": {
    "pivot_price": 54.76,
    "pivot_source": "flat_max_spike_filtered",
    "distance_to_pivot_pct": -5.62,
    "in_breakout": false
  },
  "risk": {
    "stop_price": 52.54,
    "risk_per_share": 2.22,
    "reward_to_risk": 2.47,
    "atr_14": 1.4786,
    "stop_method": "ATR"
  }
}
```

**User report** (Part 1 row + Part 2 block for RWE.DE):

```
| Rank | Ticker | Grade | Score | Base Type | Depth % | RS %ile | Dist to Pivot | R/R | Stop |
| 1 | RWE.DE | B | 74.0 | flat_base | 12.7 | 50.0 | -5.6 | 2.47 | 52.54 |

  RWE.DE  [B] Score 74.0  |  Base: flat_base (12.7% deep)
    Pivot: 54.76 (flat_max_spike_filtered)  Dist: -5.6%  |  Stop: 52.54  R/R: 2.47  |  Watch

----- RWE.DE -----
Grade: B
Composite Score: 74.0
Base: flat_base (6.0 weeks, 12.7% deep)
Prior Run: +39.0%
RS Percentile: 50.0
RSI: 39.0
Pivot: 54.76  (source: flat_max_spike_filtered)
Distance to Pivot: -5.6%
Stop: 52.54 (ATR method)
Reward/Risk: 2.47
Power Rank: 44.6
Status: Watch
  Scores: Trend 70.0  Base 100.0  RS 50.0  Vol 100.0  Breakout 50.0
```

The full user report is written by `04_generate_full_report_v2.py` to `reports/v2/sepa_scan_user_report_<timestamp>.txt`. CSV (including `pivot_source` and `power_rank`) goes to `reports/v2/sepa_scan_summary_<timestamp>.csv`.

---

## Suggestion: Making stocks less overextended

To have **fewer** names flagged as extended / overextended, you can change the following (no code change is applied by default; these are suggestions):

| Where | What | Current | Suggested |
|-------|------|---------|-----------|
| **minervini_scanner_v2.py** | Breakout score: threshold above which distance-to-pivot gets score 30 | `if distance_to_pivot_pct > 5` | Raise to **8 or 10** so only stocks >8–10% above pivot are penalized. |
| **minervini_report_v2.py** | Status "Extended" | `if dist > 5` | Use same value as scanner (e.g. **10**). |
| **minervini_report_v2.py** | Risk Warnings "Extended" | `> 10` | Raise to **15** so only >15% above pivot are listed. |
| **08_chatgpt_new_positions_v2.py** | Status for prompt | `if d > 5` | Use same as report (e.g. **10**). |
| **config.py** | Late-stage warning (within X% of 52W high) | `PRICE_TOO_CLOSE_TO_HIGH_PCT = 10` | Raise to **15** so fewer get the "late stage" warning. |

Optional: add two constants in `minervini_config_v2.py` (e.g. `EXTENDED_DISTANCE_PCT`, `EXTENDED_RISK_WARNING_PCT`) and use them in the three files above so a single place controls the thresholds.
