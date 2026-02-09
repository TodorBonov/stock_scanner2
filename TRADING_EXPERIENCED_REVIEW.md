# Complete Review — Experienced Trader Perspective

A full, critical review of the Minervini SEPA scanner and pipeline as if evaluating it for real-money use. Covers pipeline, data, methodology, risk, reporting, and what to fix or add before going live.

---

## 1. Pipeline Overview (What Actually Runs)

| Step | Script | What it does | Trader view |
|------|--------|---------------|--------------|
| 01 | `01_fetch_stock_data.py` | Loads `watchlist.txt`, fetches 1y daily OHLCV per ticker (yfinance primary, Alpha Vantage fallback), writes `data/cached_stock_data.json`. Optional `--refresh` to refetch all; `--benchmark` only affects downstream if you pass it to 02. | **Data is the foundation.** Stale or partial cache = wrong pivots and grades. |
| 02 | `02_generate_full_report.py` | Loads cache, runs Minervini scan per ticker (per-ticker benchmark via `benchmark_mapping`), writes `reports/scan_results_latest.json`, summary report, and detailed report. | **Single source of truth for grades and pivots.** Everything else (03, 05) reads from here. |
| 03 | `03_chatgpt_validation.py` | Reads `scan_results_latest.json`, sends A-grade + pre-breakout subset to OpenAI, writes `summary_Chat_GPT_*.txt`. | **Advisory only.** Good for prioritization and narrative; not for execution. |
| 04 | `04_retry_failed_stocks.py` | Retries tickers that have `error` in cache. | **Operational.** Use when fetch had transient failures. |
| 05 | `05_position_suggestions.py` | Calls Trading 212 API for open positions, merges with scan grades from `scan_results_latest.json`, suggests EXIT/REDUCE/HOLD/ADD per position. Optional `--refresh-tickers` to refetch and rescan only position tickers. | **Hold management.** Aligns with 5%/10%/45% and grade; no order routing. |

**Critical path:** Watchlist → 01 (fetch) → 02 (scan + reports) → 03 (optional ChatGPT) → 05 (optional, needs T212 API). If 01 is skipped and cache is old, 02 is still correct *for that cached date* but your “current” pivot/grade may be wrong for today’s bar.

---

## 2. Data Layer — Where It Can Bite You

### 2.1 Sources and Fallback

- **Primary:** Yahoo Finance (yfinance). Free, no key; good US coverage; EU/international can be delayed or missing.
- **Fallback:** Alpha Vantage (needs key; 25 req/day free). Used when yfinance fails or for fundamentals.
- **Trading 212:** Used only in 05 for *positions* (read-only). Not used for price history.

**Trader take:** For EU names, expect occasional bad or delayed data from Yahoo. Alpha Vantage’s 25/day is too low for a 1700+ watchlist refresh; use it for retries or a small subset. If you trade EU only, consider a dedicated EU data source for critical names.

### 2.2 Caching and Staleness

- **Cache:** One JSON file; no per-ticker TTL. “Fresh” only after you run 01 (full or with retries).
- **Report:** Shows “Oldest Data” / “Newest Data” and warns if newest is >1 day old. No automatic refresh.
- **RS:** When scanning from cache, *price* comes from cache; *relative strength* uses the **live** data provider for the benchmark (CachedDataProvider delegates `calculate_relative_strength` to the original provider). So on a day-old cache you have: stock = yesterday (or older), benchmark = today. RS can be slightly off; usually acceptable for screening.

**Trader take:** Run 01 at least once before the session (e.g. pre-market or at open). For “am I in breakout *right now*?” use live or near-live data at entry time; the scan is for *setup* identification.

### 2.3 Fetch Robustness

- **Rate limiting:** 1s delay between fetches in 01; yfinance rate-limit handling with backoff in data_provider.
- **Timeout:** 60s per ticker (ThreadPoolExecutor); one stuck ticker doesn’t block the whole run.
- **Retries:** 01 uses `fetch_stock_data_with_retry` (2 retries); 04 retries failed cache entries.

**Trader take:** Solid. For 1700+ tickers, a full refresh will take time; expect some failures and run 04 after.

### 2.4 Ticker Formats and Benchmark Mapping

- **Ticker cleaning:** `ticker_utils.clean_ticker` normalizes; data_provider tries multiple formats (e.g. `.L` vs `LON:SYMB`).
- **Benchmark mapping:** `benchmark_mapping.get_benchmark(ticker, default)` maps by suffix (e.g. `.MC` → ^IBEX, `.L` → ^FTSE, no suffix → ^GSPC if default is US). **Gaps:** `.WA` (Warsaw), `.VI` (Vienna), `.PRG` (Prague) etc. fall back to run default (e.g. ^GDAXI). So Polish/CEE names get a non-local benchmark unless you add mappings.

**Trader take:** For mixed US/EU/CEE watchlists, add `BENCHMARK_BY_SUFFIX` entries for every exchange you care about (e.g. `.WA` → `^WIG20`). Otherwise RS for those names is vs wrong index.

---

## 3. Methodology — Fidelity and Edge Cases

### 3.1 Minervini Fidelity

The five-part checklist and thresholds match Minervini’s published rules:

- Trend: price above 50/150/200 SMA, proper order and slope, 30%+ above 52W low, within 15% of 52W high.
- Base: 3–8 weeks, depth ≤25%, tight closes, volume contraction.
- RS: RSI > 60, outperforming benchmark, RS line not sharply declining (with optional relax when strong).
- Volume: dry in base; breakout volume 1.4x (Volume Signature) and 1.2x in breakout rules with multi-day confirmation.
- Breakout: pivot clearance ≥2%, close in top 30% of range, volume expansion in window.

**Trader take:** Methodology is sound and config-driven. The “relax” options (multi-day volume, RS when strong) are documented and optional; you can tighten by config.

### 3.2 Base Identification — The Weak Link

Bases are found in `_identify_base()` with:

1. **Low-volatility method:** Rolling vol < 85% of average; 55% of last 20 days “low vol”; then validated for length/depth.
2. **Range method:** Last 30d or 60d range ≤15% or ≤25%; validated for length/depth.

**Problems an experienced trader would flag:**

- **Single “base” per run:** The code returns one base (most recent qualifying window). In choppy action you can get a 20–30d window that’s not the “real” chart base. So pivot and base depth can be wrong.
- **No VCP / multi-base logic:** Minervini often talks about later-stage bases (e.g. third base). Here there’s no notion of “first base off low” vs “third base”; it’s just “last N days that look like a base.”
- **Advance-before-base:** There is a check that price isn’t >10% below 40 days ago (reject clear downtrends), but it doesn’t force “advance then base” explicitly; it only skips one failure path.

**Trader take:** Base identification is the part most likely to mislabel. Always compare scanner pivot/base to the chart. If you see “pivot 115, base 6w 12%” but the chart shows a 10-week messy range, treat the scanner as a filter and confirm structure visually.

### 3.3 Grading and Failure Count

- **Trend failure:** Automatic F; no trade.
- **Other categories:** Each *failure reason* counts (e.g. “RSI &lt; 60” + “RS line declining” = 2). So one category can contribute more than one to `total_failures`.
- **A:** total_failures ≤ 2 (non-trend). **A+:** 0 failures. **B:** ≤ 4. **C:** 5+.

**Trader take:** Correct. A stock with two small flaws (e.g. volume not dry + breakout not confirmed) still gets A and half position; that’s consistent with Minervini.

### 3.4 Breakout Rules — Why 0% Pass

In practice, Breakout Rules pass rate is 0% because you need, in the last 5 days:

- At least one close ≥2% above base high.
- That day: close in top 30% of range.
- Volume ≥1.2x on that day or in the next 2 (multi-day).

Many names are *near* pivot but haven’t closed that far above yet, or had a weak close or volume. So the scanner correctly surfaces “best setups” (A = 1–2 failures) and pre-breakout list; **you** trigger on the actual breakout bar. No change needed unless you want a “recent breakout” view (e.g. 10-day lookback) for different use.

---

## 4. Risk and Position Management

### 4.1 Position Sizing

- **Scanner:** Recommends “Full” (A+) or “Half” (A) by grade; no dollar amount.
- **position_sizing.py:** Risk-based: `shares = (account × risk_pct) / (buy - stop)`. Default 1% risk per trade. Can pull buy/stop from `--from-scan` (latest scan) or `--buy`/`--stop` manually.

**Trader take:** Correct. Always size by risk (e.g. 0.5–1% per trade), not by “full/half” alone. Run `position_sizing.py --account X --risk-pct 1 --from-scan` before adding.

### 4.2 Stops and Targets

- **Fixed:** Stop 5% below pivot; target 1 = +10%, target 2 = +45%.
- **Optional:** ATR stop in report when `USE_ATR_STOP = True` (stop = buy − ATR × multiplier). Not used in 05; for reference only.

**Trader take:** 5% is tight; one gap through stop can hurt. For volatile names, use ATR or base-low as reference and consider a wider initial stop or smaller size. 05 doesn’t suggest “exit below base low”; that’s a manual check (compare current price to scan’s base_low).

### 4.3 Position Suggestions (05)

Logic is clear and priority-ordered: EXIT at −5%; REDUCE at +45% then +10%; EXIT if weak grade and in loss; ADD if strong grade and below target 1; else HOLD. Uses average entry and current price from Trading 212.

**Gaps:**

- **No trailing stop:** After target 2, “trail” is not coded; you trail manually or in broker.
- **No break-of-base exit:** If price &lt; base_low from scan, 05 doesn’t suggest EXIT. You have base levels in scan results; check manually or add a rule.
- **Grade from last scan:** If you don’t re-run 02 (or --refresh-tickers in 05), grades are from the last full scan. Stale grade can suggest HOLD/ADD when the setup has already broken.

**Trader take:** Use 05 for stop and profit targets and for grade overlay. For “structure broken” (below base low or key MA), add your own rule or a future code change.

---

## 5. Reporting — What’s Useful and What’s Not

### 5.1 Summary Report

- Data freshness, grade distribution, criteria pass rates, top stocks by grade, best setups (A-grade sorted by base/volume/distance/RS), pre-breakout list. All good.
- **Best setups** sort key: base depth (tighter), volume contraction (drier), distance to pivot (closer), RS (higher). Matches what a trader wants for “next breakout” list.

### 5.2 Detailed Report

- One block per ticker with full checklist and numbers. Useful for deep dives and for feeding 03. Too large for daily skim; use for selected tickers or debugging.

### 5.3 ChatGPT Report

- Takes A-grade + pre-breakout, sends formatted text, gets back Top 20 + pre-breakout table + narratives. Good for prioritization and “why this one” / “what’s the risk.” Model set in config: `OPENAI_CHATGPT_MODEL` (e.g. `gpt-4o`); if you see `gpt-5.2` in the file it may be invalid — fix in `config.py`.
- **Caveat:** ChatGPT can hallucinate levels; always verify pivot, stop, target from scan (or chart), not from the narrative text.

### 5.4 Scan Results JSON

- `scan_results_latest.json` is the machine-readable source for 03 and 05. Contains full result per ticker (grades, checklist, buy_sell_prices, etc.). Keep this; 05 and position sizing depend on it.

---

## 6. Pre-Breakout and Best Setups

- **Pre-breakout:** Grade ≥ B, has pivot, *not* broken out (no close ≥2% above pivot in last 5 days), within 5% below pivot; optional base recency filter (`BASE_MAX_DAYS_OLD`). Sorted by same actionability key as best setups.
- **Best setups:** A+ and A, same sort. So you get “best names that meet criteria” and “best names that are setup-ready but not yet broken out.” Overlap is possible (an A name can be in both if it hasn’t broken out).

**Trader take:** Pre-breakout is one of the most useful features: a focused watchlist with trigger (close above pivot +2% with volume). Use it daily.

---

## 7. Configuration and Maintainability

- **config.py:** All Minervini thresholds, API timeouts, paths, grading, ATR, market regime. One place to tune.
- **position_suggestions_config.py:** Stops, targets, grade rules for 05.
- **pre_breakout_config.py:** Pre-breakout distance, min grade, “near pivot” band.
- **benchmark_mapping.py:** Per-ticker benchmark; add suffixes for your exchanges.

**Trader take:** Well organized. Change behaviour via config, not code. Document any non-default values (e.g. relaxed RS or multi-day volume) so you don’t forget why they’re on.

---

## 8. What an Experienced Trader Would Demand Before Live

| Check | Status | Action |
|-------|--------|--------|
| Data fresh at decision time | ⚠️ | Run 01 before session; confirm breakout on live/near-live data. |
| Position size by risk % | ✅ | Use position_sizing.py; never size by “full/half” only. |
| Stop and targets defined | ✅ | 5% / 10% / 45%; optionally ATR or base low for wide volatility. |
| Exit on break of structure | ⚠️ | Not in 05; add manual check vs base_low or code it. |
| Trailing after big win | ⚠️ | Not in code; trail manually or in broker. |
| Benchmark correct per name | ⚠️ | Add benchmark_mapping for all exchanges you use. |
| Base/pivot sanity check | ⚠️ | Compare scanner pivot to chart; don’t trust base blindly. |
| ChatGPT model valid | ⚠️ | Set OPENAI_CHATGPT_MODEL to a real model (e.g. gpt-4o). |
| No auto-execution | ✅ | All execution is manual; no accidental orders. |

---

## 9. Prioritized Improvements (Experienced Trader View)

**High (before real money):**

1. **Data freshness discipline:** Always run 01 (or 05 --refresh-tickers for positions) before relying on grades/pivots; document “scan as of” in your process.
2. **Benchmark mapping:** Add every exchange you trade (e.g. .WA, .VI) to `benchmark_mapping.py`.
3. **Fix ChatGPT model name:** Ensure `OPENAI_CHATGPT_MODEL` in config is a valid model (e.g. `gpt-4o`).

**Medium (next iteration):**

4. **Break-of-base exit in 05:** If current price &lt; base_low from scan for that ticker, suggest EXIT (structure broken).
5. **Optional trailing suggestion:** After target 2, suggest a trailing level (e.g. X% below 10-day high or below 10 SMA) in position suggestions report only.
6. **Base identification:** Consider “advance-before-base” more explicitly and/or longest valid base in lookback instead of “first valid” to reduce wrong pivots in choppy markets.

**Lower (nice to have):**

7. **Backtest module:** Run scanner logic on historical dates to see pass rates and, if desired, hypothetical performance (out of scope of current pipeline).
8. **Sector/position cap:** No built-in limit on names or sector concentration; enforce manually or add a simple cap in 05.

---

## 10. Bottom Line

- **Methodology:** Minervini SEPA is implemented correctly and is configurable; base identification is the main source of potential error.
- **Data:** Yahoo + optional Alpha Vantage; cache is fine for screening but must be refreshed before use; RS uses live benchmark.
- **Risk:** Position sizing by risk % and clear 5%/10%/45% rules are in place; trailing and break-of-base exit are not.
- **Reporting:** Summary and pre-breakout are strong; ChatGPT is a useful overlay if you verify numbers from the scan.
- **Execution:** Fully manual; no order routing.

**Verdict:** The stack is **production-ready for a discretionary swing trader** who uses it as a **screening and risk-sizing tool**, confirms pivots and breakouts on the chart (and, at entry, on fresh data), and manages trailing and structure breaks manually or in the broker. Treat the scanner as a filter and the reports as a focused watchlist and hold checklist, not as a black box that replaces judgment.

---

*Review reflects the codebase and docs as of the date of this document. For formulas and config details see CALCULATIONS_REFERENCE.md and config.py; for trading rationale see TRADING_IMPROVEMENTS_RATIONALE.md and TRADING_REVIEW.md.*
