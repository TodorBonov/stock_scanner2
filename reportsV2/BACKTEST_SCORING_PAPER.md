# Backtesting the Minervini V2 Scoring System — Design Paper

**Question:** How can I do backtesting for the scoring system I have?

This document outlines the problem, required ingredients, design options, and trade-offs so you can review the approach before any implementation.

---

## 1. What You Have (Scoring System)

Your **Minervini SEPA V2** pipeline:

- **Eligibility:** Structural pass/fail (trend & structure, valid base, prior run, liquidity, price).
- **Scoring:** Five component scores (trend, base quality, relative strength, volume, breakout) combined into a **composite score** and a **grade** (A+, A, B, C, REJECT).
- **Data used today:** For each ticker the scanner calls `get_historical_data(ticker, period="1y")` — i.e. the last year of OHLCV up to “today” — and (in `scan_universe`) 3‑month returns across the universe to compute RS percentile.

So the score is a **point-in-time** signal: “as of date T, this stock had composite score X and grade Y.”

---

## 2. What Backtesting Should Answer

Backtesting the scoring system means answering:

- **Predictive power:** Do higher composite scores (or better grades) predict better forward returns?
- **Grade usefulness:** Do A+ names outperform A, and A outperform B/C?
- **Stability:** Are results stable across different periods and universes?
- **Tuning:** Should weights or grade bands be changed?

To answer these you need:

1. **Scores as of many past dates** — run the same scoring logic as if the “current” date were T (no look-ahead).
2. **Forward returns** — for each (ticker, date T) where the stock was eligible and scored, measure return from T to T+Δ (e.g. 1 month, 3 months).
3. **Aggregation** — by grade, by score quintile, or by component: average return, win rate, (optionally) Sharpe, drawdown.

---

## 3. Core Constraint: Point-in-Time Data

The scanner today uses “all data up to now.” For backtesting you must simulate **only information available at T**:

- **Price/volume:** Only bars with date ≤ T.
- **RS percentile:** 3‑month returns and percentile computed from data up to T (universe returns and ranks as of T).
- **Base/trend/breakout:** All logic must use history that ends at T.

So for each backtest date T you need:

- OHLCV (and benchmark) **ending at T** (e.g. last 252 trading days ending on T).
- No use of prices or volumes after T when computing the score.

---

## 4. Data Requirements

| Need | Purpose |
|------|--------|
| **Ticker universe** | Same or similar to your live watchlist (e.g. from `prepared_for_minervini.json` or a fixed list). |
| **Historical OHLCV** | At least **1y + forward window** per ticker (e.g. 1y + 3 months) so that (a) you have a full year of data as of T and (b) you have future bars to compute 1m/3m forward returns. Prefer 2y to cover many T’s. |
| **Benchmark history** | Same date range as tickers, for RS and RS percentile as of T. |
| **Sequence of backtest dates** | e.g. every 2 or 4 weeks from “start” to “end” (end must be far enough in the past that you have forward data for all T). |

Practical options:

- **Live API (e.g. Yahoo):** Fetch 2y once per ticker; in code, **slice** each series to “as of T” for the scan and “T to T+63” for forward returns. No change to the data provider’s public API is strictly necessary if you have a wrapper that serves sliced data.
- **Cache:** If your pipeline caches OHLCV (e.g. `cached_stock_data_new_pipeline.json`), you could use that as the source of “full” history and slice by T in the backtester — subject to cache coverage and date range.
- **Stored time series:** For heavy backtesting, a dedicated store (e.g. daily bars per ticker in DB or Parquet) with an “as of date” query is ideal.

---

## 5. High-Level Design Options

### Option A: Sliced pre-fetched history (recommended for a first version)

1. **One-time:** Fetch 2y (or 1y + 3m) OHLCV for universe + benchmark (existing batch API).
2. **Backtest driver:** For each backtest date T:
   - Set “as of date” to T.
   - Use a **backtest data provider** that, for any `get_historical_data(ticker)`, returns only rows with date ≤ T (e.g. last 252 trading days ending at T). Same for benchmark when computing RS.
   - Run **existing** `MinerviniScannerV2.scan_universe(tickers)` (or equivalent) so that all internal logic sees only data up to T.
   - For each eligible result (ticker, grade, composite_score), compute forward return from T to T+21 and T+63 using the **same** pre-fetched series (future slice).
3. **Aggregation:** By grade and by composite_score quintile → avg return 1m/3m, win rate, count.

**Pros:** Reuses current scanner and scoring logic; no look-ahead; clear separation (data provider vs scanner).  
**Cons:** Need a small “as of date” data layer (wrapper that holds full series and returns slice by T).

### Option B: End-date in the live data provider

- Extend `StockDataProvider.get_historical_data(ticker, period=..., end_date=T)` so that the underlying source (e.g. Yahoo) is called with `end=T` (or equivalent).
- Backtest loop: for each T, set end_date=T, run scan, then fetch or derive forward prices (e.g. another call with start=T+1, end=T+63).

**Pros:** No separate backtest provider; works with live API.  
**Cons:** Many repeated API calls (one or two per T per ticker); rate limits and runtime; need to ensure Yahoo (or other) supports end date and you have enough history.

### Option C: Cached pipeline data

- Use your existing cache (e.g. from step 01/03) as the source of “full” history.
- Build a provider that, given an as-of date T, returns cached OHLCV truncated to T (and ensure cache has at least 1y before T and 3m after T for each ticker).
- Same backtest loop as in A: run scanner with truncated data, then forward returns from the same cache.

**Pros:** No extra fetch if cache is already 2y; fast.  
**Cons:** Depends on cache structure and how often it’s refreshed; may need a “backtest cache” with longer history.

---

## 6. What Must Run “As of T”

Everything that depends on time must see only data ≤ T:

- **Trend & structure:** SMA(200), etc., from bars ≤ T.
- **Base identification:** Lookback windows ending at T.
- **Prior run:** Computed from history before the base, with base and history all ≤ T.
- **RS:** Stock vs benchmark returns over a window ending at T.
- **RS percentile:** 3m returns of all tickers as of T, then percentile rank.
- **Volume / breakout:** All checks on bars ≤ T.
- **Composite score and grade:** Derived from the above.

Forward returns must use only bars **after** T (e.g. close at T+21 and T+63 trading days).

---

## 7. Metrics to Report

- **By grade (A+, A, B, C, REJECT):**
  - Count of (ticker, T) pairs.
  - Average 1m and 3m forward return (%).
  - Win rate (1m and 3m).
- **By composite score quintile (or decile):**
  - Same stats to see if higher score → better returns.
- **Optional:** Sharpe of “portfolio” that holds each eligible name for 1m or 3m; or max drawdown of a simple equal-weight strategy.

---

## 8. Pitfalls to Avoid

- **Look-ahead:** Using any price, volume, or derived series after T when computing the score.
- **Survivorship bias:** Using a current watchlist that only contains names that survived; backtest should use a universe that was known at each T (or accept the bias and document it).
- **Universe change:** If the list of tickers changes over time, “as of T” should use the universe that would have been used at T (e.g. from a saved watchlist or a rule).
- **Forward window:** Use trading days (e.g. 21, 63), not calendar days, for 1m/3m returns.

---

## 9. Summary

| Item | Recommendation |
|------|-----------------|
| **Core idea** | Run the existing V2 scanner at many past dates T with data truncated to T; compute 1m/3m forward returns; aggregate by grade and score. |
| **Data** | Pre-fetch 2y OHLCV for universe + benchmark; slice by T in a backtest data provider. |
| **No code change to scanner** | Scanner keeps calling `get_historical_data(ticker)`; the provider returns “as of T” data. |
| **Output** | Report (and optional JSON): by-grade and by-quintile stats (count, avg return, win rate). |

This paper is intended for review. Once you are happy with the approach, implementation can follow (e.g. a backtest data provider + a single backtest script that loops over T and writes the report).
