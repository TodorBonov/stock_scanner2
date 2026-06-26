# Trading-perspective review — findings to dig into

Assessment of the scanner as a *trading system* implementing Minervini SEPA / Trend Template.
Not financial advice — a methodology critique. Ordered by trading impact.

## P1 — Highest impact

- [x] **No market-regime filter.** DONE (Marker 1, flag-only). Step 04 computes regime per
  benchmark index (close vs its own 200-day SMA, from cached index data — no live calls),
  attaches `market_regime` to each result + history.jsonl, and prepends a MARKET REGIME
  summary to the report. Grades unchanged. Indices with no data show "unknown".
  Original finding: `REQUIRE_MARKET_ABOVE_200SMA = False`; `get_market_regime()` was unused.
  - **DECISION: mark/flag, do NOT gate.** Compute regime per benchmark index (index close vs its own
    200-day SMA), once per unique benchmark in the scan, and **clearly label** each stock when its
    market is risk-off (e.g. a `market: risk-off` tag + regime line at the top of the report).
    Grades stay unchanged; the user judges. (Optionally a soft-downgrade switch later.)
  - Which index per stock: the stock's assigned `benchmark_index` (watchlist column, else inferred
    from exchange suffix via benchmark_mapping). Same index used for RS.

- [x] **No segment/sector-relative marking.** DONE (Marker 2, flag-only). `compute_sector_strength`
  in step 04 ranks sectors by MEDIAN 3M return of their constituents; bottom third = `lagging`,
  top third = `leading`, rest = `inline` (blank sector / no return = `unknown`). Attaches
  `sector_strength` to each result + history.jsonl and adds a SECTOR STRENGTH summary to the
  report. Grades unchanged. (Uses the 95%-filled GICS `sector` column from the watchlist remake.)

- [ ] **No fundamental leg (SEPA's "A" is missing).** `get_stock_info` fetches `earnings_growth`,
  `revenue_growth`, `profit_margins`, `return_on_equity` but **none are used** in eligibility or the
  composite score (weights are trend/base/RS/volume/breakout only). A chart-perfect base on a company
  with collapsing earnings scores the same as a fundamental leader.
  - Action: add a fundamental gate/score (EPS & sales acceleration, margins, ROE).

## P2

- [ ] **"Relative Strength" isn't a market RS rank.** `rs_rating = 50 + outperformance*100` (vs ONE
  index) is not a percentile; the V2 `rs_percentile` is a true rank but only across the ~1,700-name
  watchlist, not the market — so RS quality depends on what's in the watchlist.
  - Action: rank RS against a broad-market proxy; relabel `rs_rating` to avoid confusion with IBD RS.

- [ ] **Base detection isn't a true VCP.** `_identify_base` uses low-volatility windows / price-range
  thresholds, not progressive volatility contraction (2–4 ever-tighter pullbacks with volume drying up).
  Can pass loose consolidations that aren't VCPs.
  - Action: count contractions and require each tighter than the last; verify volume dry-up.

- [x] **Breakout volume confirmation loosened.** DONE (affects grade). Once a breakout clears the
  pivot, `_component_score_breakout` now scales the score by volume: ≥1.4× → 100, 1.2–1.4× → 80,
  <1.2× → 65. Only already-broken-out names are affected; pre-breakout proximity bands unchanged.
  - **Also added: entry-actionability `status`** (Ready / In-breakout / Extended / Near / Watch from
    distance-to-pivot) + an ACTIONABLE NOW report block listing A+/A "Ready at the pivot" names — so
    pre-breakout setups are surfaced *before* they run (buy-stop-at-pivot workflow), not chased.

## P3 — Minor / polish

- [ ] **Within 15% of 52w high** (`PRICE_FROM_52W_HIGH_MAX_PCT = 15`) is stricter than Minervini's 25%
  — trims early-stage names. Intentional? Document or relax.
- [x] **No earnings-date guard.** DONE (flag-only). Step 04 fetches the next earnings date (Yahoo
  `.calendar`, scoped to A+/A candidates only — `get_earnings_dates()` is throttled here) and flags
  any reporting within `EARNINGS_GUARD_DAYS` (7). Adds `earnings {next_date, days_until, soon}` to
  results + history.jsonl and an EARNINGS WATCH block to the report. Grades unchanged.
- [ ] **Profit-taking is two fixed targets** (10% / 45%). Minervini sells partial into strength and
  trails. Consider a tiered/trailing model.

## Quick wins (mechanical, low risk)
1. Market-regime + sector **markers** (flag-only) in reports/output. (P1)
2. Add earnings-date flag to candidate output. (P3)
3. Add a coarse fundamentals gate using already-fetched data. (P2)
4. Downgrade (don't pass) weak-volume breakouts. (P2)

## Watchlist data quality (audit of watchlist.csv)

Audit: 1,727 ticker rows, 1,721 match the suffix→benchmark rule, 0 blanks, all 15 referenced
index symbols have `type=index` rows (so RS + regime data is available for every benchmark). ✅
6 rows have an explicit benchmark that differs from the exchange-suffix rule:

| Ticker | Assigned | Suffix implies | Verdict |
|---|---|---|---|
| PHG | `^AEX` | `^GSPC` | OK — Philips is Dutch (US ADR); AEX better than S&P |
| STLA | `^FTMIB` | `^GSPC` | Defensible — Stellantis trades US but is a Euro automaker |
| GS71.DE | `^GSPC` | `^GDAXI` | ❌ Wrong — German listing vs S&P; should be DAX |
| LUN.TO | `^OMXC25` | `^GSPTSE` | ❌ Wrong — Toronto-listed vs Danish index; should be TSX |
| CNP | `^FCHI` | `^GSPC` | ⚠️ Symbol risk — bare `CNP` = CenterPoint (US); if CNP Assurances use `CNP.PA` |
| BPER | `^FTMIB` | `^GSPC` | ⚠️ Symbol risk — BPER Banca is Italian; bare symbol may need `BPER.MI` |

- [x] Fix clear benchmark errors: **GS71.DE → `^GDAXI`**, **LUN.TO → `^GSPTSE`** (done in watchlist remake).
- [x] **CNP** resolved: it's CenterPoint Energy (US, S&P 1000) → `^GSPC` + Utilities. **BPER** still
  fails to fetch (bare symbol; flagged in problems_with_tickers via the new benchmark/data checks) —
  needs `BPER.MI` if the Italian bank is intended. (Also fixed dead benchmarks: `^FTMIB → FTSEMIB.MI`;
  `^WIG20` has no reliable Yahoo symbol — flagged.)
