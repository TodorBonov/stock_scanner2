# Action Plan – Implementation Summary

This document summarizes the implementation of the trading improvements and weakness fixes from the review. All items are implemented and configurable.

---

## ✅ Priority 1: Grading / Failures (Hard Failures)

- **RS line decline:** When RS line is >5% below recent high and `RS_RELAX_LINE_DECLINE_IF_STRONG` is not applied, the Relative Strength category now sets `passed = False`, so the failure is counted in the grade.
- **Breakout close position:** When close on breakout day is below 70% of range (or zero daily range), Breakout Rules now set `passed = False`.

**Code:** `minervini_scanner.py` – `_check_relative_strength`, `_check_breakout_rules`.

---

## ✅ Priority 2: Breakout Lookback and Reporting

- **Config:** `BREAKOUT_LOOKBACK_DAYS` remains 5 for the breakout check; `BREAKOUT_LOOKBACK_DAYS_FOR_REPORT = 21` added for reporting.
- **Breakout details:** Each result’s breakout_rules details now include `last_above_pivot_date` and `days_since_breakout` (from scanning the last 21 days).
- **Report:** Summary and detailed reports show “Last close above pivot” and “Days since breakout” where relevant.

**Code:** `config.py`, `minervini_scanner.py` (`_check_breakout_rules`), `02_generate_full_report.py`.

---

## ✅ Priority 3: 52-Week High and PRICE_FROM_52W_HIGH_MAX_PCT

- **Value:** `PRICE_FROM_52W_HIGH_MAX_PCT` set to **15%** (Minervini: within 15% of 52-week high).
- **Docs:** `CALCULATIONS_REFERENCE.md` updated.

**Code:** `config.py`, `CALCULATIONS_REFERENCE.md`.

---

## ✅ Priority 4: ATR-Based Stop (Optional)

- **Config:** `USE_ATR_STOP`, `ATR_PERIOD`, `ATR_STOP_MULTIPLIER` in `config.py`.
- **Scanner:** `_calculate_atr()` added; `_calculate_buy_sell_prices()` returns `stop_loss_atr` and `atr_value` when `USE_ATR_STOP` is True.
- **Report:** Summary and detailed reports show “Stop(ATR)” when enabled.

**Code:** `config.py`, `minervini_scanner.py`, `02_generate_full_report.py`.

---

## ✅ Priority 5: Market Regime (Optional)

- **Config:** `REQUIRE_MARKET_ABOVE_200SMA` in `config.py`.
- **Scanner:** `get_market_regime(benchmark)` returns `above_200sma`, `benchmark`, `error`.
- **Report:** When `REQUIRE_MARKET_ABOVE_200SMA` is True, summary report includes a “Market regime” section (above/below 200 SMA).

**Code:** `config.py`, `minervini_scanner.py`, `02_generate_full_report.py`.

---

## ✅ Priority 6: Multi-Benchmark by Region

- **Module:** `benchmark_mapping.py` with `get_benchmark(ticker, default_benchmark)` (suffix → ^GSPC, ^GDAXI, ^FCHI, etc.).
- **Scanner:** `scan_stock(ticker, benchmark_override=None)`; when provided, RS uses the override.
- **Report:** Each scan uses the mapped benchmark per ticker; result includes `benchmark_used`.

**Code:** `benchmark_mapping.py`, `minervini_scanner.py`, `02_generate_full_report.py`.

---

## ✅ Priority 7: Base Recency

- **Scanner:** `_calculate_buy_sell_prices()` returns `days_since_base_end` from base end_date.
- **Report:** Summary and detailed reports show “Days since base end” when available.
- **Optional filter:** `BASE_MAX_DAYS_OLD` in config; when >0, pre-breakout list excludes bases older than N days (`pre_breakout_utils.py`).

**Code:** `config.py`, `minervini_scanner.py`, `pre_breakout_utils.py`, `02_generate_full_report.py`.

---

## ✅ Priority 8: Position Sizing Script

- **Script:** `position_sizing.py` – `--account`, `--risk-pct`, `--from-scan` (and optional `--ticker`), or manual `--buy` / `--stop`.
- **Output:** Suggested shares and position value so risk per trade = account × risk%.

**Code:** `position_sizing.py`.

---

## ✅ Priority 9: Volume Thresholds Documentation

- **Doc:** `CALCULATIONS_REFERENCE.md` – note added that Volume Signature uses 1.4x (ongoing breakout) and Breakout Rules use 1.2x (multi-day window); different roles explained.

**Code:** `CALCULATIONS_REFERENCE.md`.

---

## ✅ Priority 10: Pre-Breakout Near-Pivot

- **Config:** `PRE_BREAKOUT_NEAR_PIVOT_PCT = 2.0` in `pre_breakout_config.py`.
- **Report:** Pre-breakout section labels stocks within 2% below pivot with “[near pivot]”.

**Code:** `pre_breakout_config.py`, `pre_breakout_utils.py` (import), `02_generate_full_report.py`.

---

## API Change for Callers of `scan_all_stocks_from_cache`

`scan_all_stocks_from_cache()` now returns `(results, scanner)`. Callers that only need results should unpack:

- `results, _ = scan_all_stocks_from_cache(...)`  
- Updated: `03_chatgpt_validation.py`, `05_position_suggestions.py`.

---

## Config Summary

| Config | Default | Purpose |
|--------|---------|--------|
| `PRICE_FROM_52W_HIGH_MAX_PCT` | 15 | Max % below 52W high (Minervini 15%) |
| `BREAKOUT_LOOKBACK_DAYS_FOR_REPORT` | 21 | Days to find last close above pivot |
| `USE_ATR_STOP` | False | Report ATR-based stop |
| `ATR_PERIOD` | 14 | ATR period |
| `ATR_STOP_MULTIPLIER` | 1.5 | Stop = buy − ATR × this |
| `REQUIRE_MARKET_ABOVE_200SMA` | False | Show market regime in report |
| `BASE_MAX_DAYS_OLD` | 0 | Exclude bases older than N days from pre-breakout (0 = off) |
| `PRE_BREAKOUT_NEAR_PIVOT_PCT` | 2.0 | “Near pivot” band for report label |

See `config.py` and `CALCULATIONS_REFERENCE.md` for full references.
