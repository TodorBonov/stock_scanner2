# Comparison: Before vs After Latest Implementation

Same cache (no new fetch). **Before** = last run before the latest implementation (report 2026-02-08 23:39:27). **After** = run with the new logic (stricter 52W high, hard failures for RS line and breakout close, per-ticker benchmark, etc.).

---

## Before (summary_report_20260208_233927.txt)

| Metric | Value |
|--------|--------|
| Total stocks | 1752 |
| Meeting criteria | 117 (6.7%) |
| **Grade A+** | 0 |
| **Grade A** | 117 |
| Grade B | 364 |
| Grade C | 174 |
| Grade F | 1054 |
| **Trend & Structure** | 655 (37.4%) |
| **Base Quality** | 455 (26.0%) |
| **Relative Strength** | 28 (1.6%) |
| **Volume Signature** | 965 (55.1%) |
| **Breakout Rules** | 0 (0.0%) |

---

## After (summary_report_20260209_093303.txt — current code, same cache)

| Metric | Value |
|--------|--------|
| Total stocks | 1752 |
| Meeting criteria | 117 (6.7%) |
| **Grade A+** | 0 |
| **Grade A** | 117 |
| Grade B | 363 |
| Grade C | 160 |
| Grade F | 1069 |
| **Trend & Structure** | 640 (36.5%) |
| **Base Quality** | 455 (26.0%) |
| **Relative Strength** | 38 (2.2%) |
| **Volume Signature** | 965 (55.1%) |
| **Breakout Rules** | 0 (0.0%) |

---

## Why the changes in the output occur

The following code and config changes directly affect the reported numbers and grades.

### 1. **PRICE_FROM_52W_HIGH_MAX_PCT: 25% → 15%**

- **What changed:** The rule “price must be within X% of 52-week high” was tightened from 25% to **15%** (Minervini’s typical rule).
- **Effect on output:** Any stock that was **between 15% and 25% below** its 52-week high used to **pass** Trend & Structure; it now **fails**.
- **Result:** **Trend & Structure** pass count **decreases**. More stocks get an F (Trend failure), so **Grade F** count **increases** and **Meeting criteria** and **Grade A** counts can **decrease**. The exact size of the shift depends on how many names in the cache sit in that 15–25% band.

### 2. **RS line decline now sets Relative Strength to “failed”**

- **What changed:** Previously, “RS line X% below recent high” only added a failure message; the Relative Strength step could still be `passed = True`, so that failure was **not** counted in the grade. Now, when the RS line is more than the warning threshold below its high (and the “relax when strong” option does not apply), we set **`passed = False`** for Relative Strength.
- **Effect on output:** Stocks that had RS line decline as a *soft* failure now **fail** the Relative Strength criterion. The failure is counted in the total failure count used for grading.
- **Result:** **Relative Strength** pass count can **decrease**. Some stocks that were A (1–2 failures) or B (3–4 failures) get one more *counted* failure and can move to a **lower grade** (e.g. A→B, B→C). **Meeting criteria** and **Grade A** counts can **decrease**; **Grade B/C** and **Grade F** can **increase** depending on how many had only RS line decline as the extra failure.

### 3. **Breakout day close position now sets Breakout Rules to “failed”**

- **What changed:** If on the breakout day the close was below 70% of the day’s range (or the day had zero range), we only appended a failure message before; we now set **`passed = False`** for Breakout Rules.
- **Effect on output:** Any stock that had cleared the pivot with volume but had a weak close (or zero range) on that day now **fails** Breakout Rules and the failure is counted.
- **Result:** **Breakout Rules** pass count can **decrease** (it was already 0 in the “Before” run; it may stay 0 or drop further if any edge case appeared). Fewer stocks will have “all five parts passed,” so **Grade A+** (if any) could disappear; **Grade A** could **decrease** if some of those stocks had only this as an extra failure.

### 4. **Per-ticker benchmark (benchmark_override)**

- **What changed:** The report script now uses **per-ticker** benchmarks (e.g. US → ^GSPC, .DE → ^GDAXI, .PA → ^FCHI) via `benchmark_mapping.get_benchmark(ticker, default)` instead of a single benchmark for all.
- **Effect on output:** Relative Strength is computed against a **different index** for some tickers (e.g. US names vs S&P 500 instead of DAX). Some stocks may **pass** RS that previously failed (better comparison), others may **fail** that previously passed (stricter or different index).
- **Result:** **Relative Strength** pass count can **increase or decrease** depending on the mix of tickers and index performance. Grade distribution can shift accordingly.

### 5. **Other additions (no or minimal impact on counts)**

- **Last above pivot / days since breakout:** Only added to the report text and breakout details; they do not change pass/fail or grading.
- **Days since base end:** Only reported; optional filter `BASE_MAX_DAYS_OLD` can reduce pre-breakout list size but not the main criteria pass rates or grade counts.
- **ATR stop, market regime, pre-breakout “[near pivot]”:** Report-only; no effect on grade or criteria pass counts.

---

## Summary: Before vs After

| Metric | Before (233927) | After (093303) | Change | Main driver |
|--------|------------------|----------------|--------|-------------|
| Meeting criteria | 117 (6.7%) | 117 (6.7%) | — | — |
| Grade A+ | 0 | 0 | — | — |
| Grade A | 117 | 117 | — | — |
| Grade B | 364 | 363 | −1 | 52W 15%, RS/breakout hard fail |
| Grade C | 174 | 160 | −14 | Same |
| Grade F | 1054 | 1069 | +15 | 52W 15% (more Trend failures) |
| Trend & Structure (pass) | 655 (37.4%) | 640 (36.5%) | −15 | 52W 15% (stricter) |
| Relative Strength (pass) | 28 (1.6%) | 38 (2.2%) | +10 | Per-ticker benchmark (e.g. US→^GSPC) |
| Breakout Rules (pass) | 0 (0.0%) | 0 (0.0%) | — | — |

---

## How to re-run and update this comparison

1. **Run report without fetching new data:**
   ```powershell
   python 02_generate_full_report.py --summary-only
   ```
2. Open the **newest** `reports/summary_report_YYYYMMDD_HHMMSS.txt`.
3. Copy the **OVERALL STATISTICS**, **GRADE DISTRIBUTION**, and **CRITERIA PASS RATES** into the “After” table and the “Summary table” above.
4. Optionally set **Before** to the previous run’s file for a consistent before/after pair.

---

## Pipeline status

- **Report (02):** Run when needed → `summary_report_*.txt`
- **Position suggestions (03):** Optional after report
- **ChatGPT validation (04):** Optional after report

To re-run without fetching new data:
```powershell
.\run_latest_data_pipeline.ps1
```
Or step by step: `python 02_generate_full_report.py`, then `python 03_position_suggestions.py`, then `python 04_chatgpt_validation.py`.
