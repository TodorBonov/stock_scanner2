# Technical Reference

---

## 1. Architecture

### Scanner engine

`sepa_scorer.py` — `MinerviniScannerV2`
- Structural eligibility gating, composite scoring, RS percentile ranking,
  base-type classification, ATR stop, power rank.
- This is the engine used by the pipeline (`04_scan.py`).
- Produces a single deterministic JSON object per ticker (schema in section 2).

### Data flow

```
watchlist.csv
    │
    ▼ step 01 — fetch_utils + StockDataProvider (Yahoo Finance)
data/cached_stock_data_new_pipeline.json
    │
    ▼ step 02 — Trading212 API
data/positions_new_pipeline.json
    │
    ▼ step 03 — merge + resolve ticker mappings
data/prepared_for_minervini.json
    │
    ▼ step 04 — MinerviniScannerV2 + CachedDataProviderV2
reports/scan/latest.json          ← machine output (overwritten each run)
reports/scan/scan_<ts>.txt        ← human report
docs/index.html                   ← HTML rank table
    │
    ▼ step 05 — extract holdings + A+/A candidates
reports/data/ai_holdings_input.json
reports/data/ai_candidates_input.json
    │
    ├─▶ step 06 — ChatGPT → reports/ai/holdings_<ts>.txt
    └─▶ step 07 — ChatGPT → reports/ai/candidates_<ts>.txt
```

---

## 2. V2 scan result JSON schema

Each object in `reports/scan/latest.json`:

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
    "rs_3m": 14.59,
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
    "atr_14": 1.48,
    "stop_method": "ATR"
  },
  "trend_details": {
    "current_price": 51.70,
    "sma_50": 50.10,
    "sma_150": 47.30,
    "sma_200": 45.20,
    "52_week_high": 57.40,
    "52_week_low": 35.10
  },
  "region": "EU",
  "sector": "Utilities",
  "market_cap": "Large Cap"
}
```

Ineligible tickers:
```json
{
  "ticker": "XYZ",
  "eligible": false,
  "grade": "REJECT",
  "composite_score": 0.0,
  ...all score fields 0...
}
```

**Note:** `grade` (not `overall_grade`). `breakout.pivot_price` and `risk.stop_price` (not `buy_sell_prices`).

---

## 3. Eligibility gates

A ticker must pass **all** of the following or it is immediately rejected (grade = REJECT, no scoring):

| Gate | Condition |
|------|-----------|
| Stage 2 trend | Price > SMA 50, 150, 200; SMA 50 > 150 > 200; all slopes up; price ≥ 30% above 52W low; price within 15% of 52W high |
| Valid base | Base identified (2–12 weeks, depth ≤ 35%) |
| Prior run | `(base_high − lowest_low_63d_before_base) / lowest_low * 100 ≥ 25%` (when `PRIOR_RUN_REQUIRED_FOR_ELIGIBILITY = True`) |
| Liquidity | Avg 20-day (Close × Volume) ≥ $1,000,000 |
| Min price | Current price ≥ $5.00 |

---

## 4. Composite scoring

### Weights

| Component | Weight | Config constant |
|-----------|--------|----------------|
| Trend structure | 20% | `WEIGHT_TREND_STRUCTURE` |
| Base quality | 25% | `WEIGHT_BASE_QUALITY` |
| Relative strength | 25% | `WEIGHT_RELATIVE_STRENGTH` |
| Volume signature | 15% | `WEIGHT_VOLUME_SIGNATURE` |
| Breakout quality | 15% | `WEIGHT_BREAKOUT_QUALITY` |

`composite_score = Σ(weight × component_score)`, each component scored 0–100.

### Component scores

**Trend score** (graded by % above 200 SMA):

| `pct_above_200` | Score |
|----------------|-------|
| ≥ 30% | 100 |
| 15–30% | 70 |
| 5–15% | 40 |
| 0–5% | 15 |
| < 0% (below 200 SMA) | 0 |

**Base score:** Start 80; +10 if depth ≤ 15%; +5 if depth ≤ 20%; +10 if prior run ≥ 25%, else −20; +10 if range contraction (last 2-week range / base range ≤ 0.5); +10 if last 2 weekly closes in upper 40% of base range. Clamped [0, 100].

**RS score:** Equal to `rs_percentile` (0–100, position in universe by 3M return).

**Volume score:** 100 if volume signature passed; 70 if contraction ratio < 0.80; 50 if < 0.95; else 0.

**Breakout score:** 100 if in breakout; 80 if −3% ≤ distance_to_pivot ≤ 0%; 60 if −5% ≤ distance < −3%; 30 if distance > 5% (extended); else 50.

### Grade bands

| Composite score | Grade |
|----------------|-------|
| ≥ 85 | A+ |
| 75–84 | A |
| 65–74 | B |
| 55–64 | C |
| < 55 | REJECT |

A+ also requires `rs_percentile ≥ 80`; A requires `rs_percentile ≥ 70` (configured via `MIN_RS_PERCENTILE_FOR_A_PLUS` / `MIN_RS_PERCENTILE_FOR_A`).

---

## 5. Base types and pivot selection

| Base type | Condition | Pivot |
|-----------|-----------|-------|
| `flat_base` | depth ≤ 15% | `max(High)` of base, spike-filtered |
| `high_tight_flag` | prior run ≥ 100%, depth ≤ 25%, length ≤ 5 weeks | `max(High)` of flag |
| `cup` | 15% < depth ≤ 25% (not HTF) | `max(High)` of last 7 days (handle) |
| `standard_base` | fallback | `max(High)` of base, spike-filtered |

**Spike filter** (flat/standard only): bars with `High > mean(High) + 2×std(High)` are excluded, except the last 5 days of the base are never filtered.

---

## 6. Relative strength metrics

**rs_3m** — Total return % of the stock over last 63 trading days.
`(Close[-1] / Close[-63] − 1) × 100`

**rs_percentile** — Where this stock's 3M return ranks in the scan universe.
`count(tickers with 3M return < this stock's) / n × 100`
0 = worst, 100 = best. Used as the RS component score.

**rsi_14** — Standard RSI(14) on closing prices. Reported for context only; does not affect composite score.

**RS vs benchmark** — Used internally by the checklist (`_check_relative_strength`) for pass/fail and RS line checks. Not exposed in the V2 composite; that uses `rs_percentile` instead.

---

## 7. Stop and risk

**ATR stop** (default, `USE_ATR_STOP_V2 = True`):
```
atr_stop   = pivot_price − ATR(14) × 1.5
lowest_low = min(Low) of last 5 days
stop_price = max(atr_stop, lowest_low)
```

**Fixed stop** (fallback):
```
stop_price = pivot_price × (1 − STOP_LOSS_PCT / 100)
```
`STOP_LOSS_PCT = 5` → 5% below pivot.

**Power rank:**
```
power_rank = 0.5 × rs_percentile + 0.5 × min(prior_run_pct, 100)
```
Used as a secondary sort for candidates with high RS and strong prior advances.

---

## 8. Key config constants (`config.py`)

### Structural eligibility
| Constant | Value |
|----------|-------|
| `MIN_AVG_DOLLAR_VOLUME_20D` | 1,000,000 |
| `MIN_PRICE_THRESHOLD` | 5.0 |
| `MIN_PRIOR_RUN_PCT` | 25.0 |
| `PRIOR_RUN_LOOKBACK_TRADING_DAYS` | 63 |
| `PRIOR_RUN_REQUIRED_FOR_ELIGIBILITY` | True |

### Scoring weights
| Constant | Value |
|----------|-------|
| `WEIGHT_TREND_STRUCTURE` | 0.20 |
| `WEIGHT_BASE_QUALITY` | 0.25 |
| `WEIGHT_RELATIVE_STRENGTH` | 0.25 |
| `WEIGHT_VOLUME_SIGNATURE` | 0.15 |
| `WEIGHT_BREAKOUT_QUALITY` | 0.15 |

### Grade bands
| Constant | Value |
|----------|-------|
| `GRADE_A_PLUS_MIN_SCORE` | 85.0 |
| `GRADE_A_MIN_SCORE` | 75.0 |
| `GRADE_B_MIN_SCORE` | 65.0 |
| `GRADE_C_MIN_SCORE` | 55.0 |
| `MIN_RS_PERCENTILE_FOR_A_PLUS` | 80.0 |
| `MIN_RS_PERCENTILE_FOR_A` | 70.0 |

### ATR stop
| Constant | Value |
|----------|-------|
| `USE_ATR_STOP_V2` | True |
| `ATR_PERIOD_V2` | 14 |
| `ATR_STOP_MULTIPLIER_V2` | 1.5 |
| `ATR_STOP_LOWEST_LOW_DAYS` | 5 |

### Trend tiers
| Constant | Value |
|----------|-------|
| `TREND_PCT_ABOVE_200_TIER1` | 30.0 |
| `TREND_PCT_ABOVE_200_TIER2` | 15.0 |
| `TREND_PCT_ABOVE_200_TIER3` | 5.0 |

### Base types
| Constant | Value |
|----------|-------|
| `BASE_TYPE_FLAT_MAX_DEPTH_PCT` | 15.0 |
| `BASE_TYPE_HIGH_TIGHT_PRIOR_RUN_PCT` | 100.0 |
| `BASE_TYPE_HIGH_TIGHT_MAX_DEPTH_PCT` | 25.0 |
| `BASE_TYPE_HIGH_TIGHT_MAX_WEEKS` | 5.0 |

### Pivot / breakout
| Constant | Value |
|----------|-------|
| `PIVOT_SPIKE_FILTER_ENABLED` | True |
| `PIVOT_SPIKE_STD_MULTIPLIER` | 2.0 |
| `PIVOT_IGNORE_SPIKE_WITHIN_LAST_N_DAYS` | 5 |
| `PIVOT_HANDLE_DAYS` | 7 |
| `EXTENDED_DISTANCE_PCT` | 8.0 |

### OpenAI
| Constant | Value |
|----------|-------|
| `OPENAI_CHATGPT_MODEL` | `gpt-5.2` |
| `OPENAI_CHATGPT_MAX_COMPLETION_TOKENS` | 64000 |
| `OPENAI_CHATGPT_RETRY_ATTEMPTS` | 3 |

---

## 9. File paths (from `config.py`)

| Constant | Path |
|----------|------|
| `SCAN_RESULTS_V2_LATEST` | `reports/scan/latest.json` |
| `SCAN_HISTORY_FILE` | `reports/scan/history.jsonl` |
| `PREPARED_FOR_MINERVINI` | `data/prepared_for_minervini.json` |
| `PREPARED_EXISTING_V2` | `reports/data/ai_holdings_input.json` |
| `PREPARED_NEW_V2` | `reports/data/ai_candidates_input.json` |
| `CACHE_FILE` | `data/cached_stock_data.json` (legacy fallback) |
| `REPORTS_DIR_V2` | `reports` |
| `SEPA_USER_REPORT_PREFIX` | `scan_` |

