# Trading-perspective review — findings to dig into

Assessment of the scanner as a *trading system* implementing Minervini SEPA / Trend Template.
Not financial advice — a methodology critique. Ordered by trading impact.

## P1 — Highest impact

- [ ] **No market-regime filter.** `REQUIRE_MARKET_ABOVE_200SMA = False` (config.py) — it's off, and
  `get_market_regime()` isn't used. Minervini's first rule is to trade in sync with the general market.
  Result: A/A+ breakouts get surfaced even in market downtrends (highest failure rate).
  - **DECISION: mark/flag, do NOT gate.** Compute regime per benchmark index (index close vs its own
    200-day SMA), once per unique benchmark in the scan, and **clearly label** each stock when its
    market is risk-off (e.g. a `market: risk-off` tag + regime line at the top of the report).
    Grades stay unchanged; the user judges. (Optionally a soft-downgrade switch later.)
  - Which index per stock: the stock's assigned `benchmark_index` (watchlist column, else inferred
    from exchange suffix via benchmark_mapping). Same index used for RS.

- [ ] **No segment/sector-relative marking.** Beyond the broad market, the watchlist has a `Sector`
  (and `Region`) column that isn't used to assess whether a stock's *segment* is leading or lagging.
  - **DECISION: also clearly mark when a stock's sector/segment is currently underperforming.**
    Approach: rank sectors by recent relative performance (e.g. median 3M return of the stocks in
    each sector vs the market, or a sector index), and tag stocks in lagging sectors
    (e.g. `sector: lagging`). Flag only — no grade change.

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

- [ ] **Breakout volume confirmation loosened.** `VOLUME_EXPANSION_MIN = 1.2` over a 2-day window
  vs Minervini's ~+40–50% on the breakout day. Admits low-conviction breakouts.
  - Action: treat weak-volume breakouts as a score downgrade rather than a pass.

## P3 — Minor / polish

- [ ] **Within 15% of 52w high** (`PRICE_FROM_52W_HIGH_MAX_PCT = 15`) is stricter than Minervini's 25%
  — trims early-stage names. Intentional? Document or relax.
- [ ] **No earnings-date guard.** Nothing prevents a "buy" signal landing days before an earnings report
  (event risk). Add an earnings-date flag to candidate output.
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

- [ ] Fix clear benchmark errors: **GS71.DE → `^GDAXI`**, **LUN.TO → `^GSPTSE`**.
- [ ] Verify **CNP** / **BPER** resolve to the intended (European?) company — a wrong *symbol* means
  the whole row's price data is the wrong instrument, far worse than a wrong benchmark. Add proper
  suffixes (`CNP.PA`, `BPER.MI`) if European. Cross-check fetched currency once the cache is built.
