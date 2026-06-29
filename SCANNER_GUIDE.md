# How the Minervini SEPA Scanner Works

A practical, end-to-end explanation of what this project does, how each piece fits together,
and where it could be improved. For *commands*, see [COMMANDS.md](COMMANDS.md); for the
trading-methodology critique and open items, see [TRADING_REVIEW.md](TRADING_REVIEW.md).

---

## 1. What it is (in one paragraph)

It screens a watchlist (~1,700 US + European stocks) for **Mark Minervini–style SEPA / Trend-Template
setups**: stocks in a Stage-2 uptrend that have built a tight consolidation base and are positioned to
break out. It fetches price data, runs a **deterministic, pure-Python scoring engine** (no AI), grades
each stock, and flags context (market regime, sector strength, earnings risk, entry-readiness). An
optional ChatGPT layer can review holdings and rank candidates, but the core screen is 100% rule-based
and reproducible.

---

## 2. The pipeline (run by `run_pipeline.py`)

Seven steps; each reads the previous step's output. The orchestrator runs them in order and supports
`--watchlist`, `--refresh`, `--no-ai`, `--csv`, `--exclude-06/07`.

| Step | Script | Does | Output |
|------|--------|------|--------|
| 01 | `01_fetch_prices.py` | Fetch ~1y daily OHLCV for the watchlist from Yahoo (batched) | `data/cached_stock_data_new_pipeline.json` |
| 02 | `02_fetch_positions.py` | Pull open positions from Trading 212 (`--refresh` also refetches their OHLCV) | `data/positions_new_pipeline.json` |
| 03 | `03_prepare_data.py` | Merge cache + positions + watchlist, map symbols, **report data/benchmark problems** | `data/prepared_for_minervini.json`, `reports/problems_with_tickers.txt` |
| 04 | `04_scan.py` | **The scan**: eligibility + composite scoring + markers/guards | `reports/scan/latest.json`, `scan_<ts>.txt`, `history.jsonl`, `docs/index.html` |
| 05 | `05_prep_ai_data.py` | Build LLM inputs for holdings (06) and A+/A candidates (07) | `reports/data/ai_*_input.json` |
| 06 | `06_analyze_holdings.py` | *(optional, GPT)* review existing positions | `reports/ai/holdings_<ts>.txt` |
| 07 | `07_rank_candidates.py` | *(optional, GPT)* independent ranking of candidates | `reports/ai/candidates_<ts>.txt` |

`--no-ai` skips 06/07 → a pure math run with **zero token cost**. Steps 01–05 never call an LLM.

---

## 3. The data layer

**Source:** Yahoo Finance via `yfinance`, fetched in **batches** (`get_historical_data_batch`,
chunks of `YF_BATCH_CHUNK_SIZE`) with an **adaptive delay** — a short pause between clean chunks and a
long back-off only when a chunk looks rate-limited.

**Corporate SSL:** if `DISABLE_SSL_VERIFY=1` (set in `.env`), all Yahoo traffic uses a **curl_cffi
Chrome-impersonating session** (a plain `requests` session is blocked by SSL-inspection proxies).

**Currency → USD:** every ticker's currency is inferred from its **exchange suffix** (`currency_for_symbol`:
`.L`→GBp pence, `.DE/.PA`→EUR, `.SW`→CHF, no-suffix→USD, …) — *no per-ticker network call*, because the
`.info` quote endpoint is the main thing Yahoo rate-limits. OHLCV and prices are converted to USD at
fetch time (FX rates cached per currency, so ~10 lookups for the whole universe), incl. the London
**pence→USD** 100× fix.

**Validation:** `yf.download` aligns all tickers to a shared date index and **NaN-fills failures**, so a
failed ticker can still have ≥200 *rows*. The fetch counts **non-NaN OHLC rows** and does one gentle
batch-retry; genuinely-failed names are marked unavailable (and surface in `problems_with_tickers.txt`).

**Caching / incremental:** step 01 only fetches tickers not already cached unless `--refresh` is passed.
A full `--refresh` of ~1,700 names takes ~2–3 minutes.

---

## 4. The watchlist (`watchlist.csv`)

One row per symbol. Schema:
`type, yahoo_symbol, trading212_symbol, benchmark_index, currency, sector, sub_industry, region, size, source, enabled`

- `type` = `ticker` (scanned) or `index` (benchmark, fetched for RS/regime, not scanned).
- `benchmark_index` drives both **relative strength** and the **market-regime** marker (US→`^GSPC`,
  Germany→`^GDAXI`, …; inferred from suffix when blank via `benchmark_mapping.py`).
- `sector` is real **GICS** (from S&P 500/400/600 + STOXX 600 + TSX lists; ~95% filled), used by the
  sector-strength marker.
- `currency` is normally blank (inferred); fill only to override an oddball.

---

## 5. The scoring engine (`sepa_scorer.MinerviniScannerV2`)

Extends the original 5-part checklist (`sepa_checklist.MinerviniScanner`). For each stock:

### (a) Structural eligibility — must pass all, else `REJECT`
- **Stage-2 trend** (Trend Template): price > 50/150/200-day SMA, `50 > 150 > 200`, SMAs rising, ≥30%
  above the 52-week low, within 15% of the 52-week high.
- **Valid base** identified (a consolidation following an advance).
- **Prior run** ≥ `MIN_PRIOR_RUN_PCT` (25%) — the base must follow a real advance.
- **Liquidity** ≥ `MIN_AVG_DOLLAR_VOLUME_20D` ($1M/day) and **price** ≥ `MIN_PRICE_THRESHOLD` ($5).

### (b) Base analysis
Identifies the base, classifies its **type** (flat / cup / high-tight-flag / standard) and computes the
**pivot** (buy trigger) from the base structure, with a spike filter.

### (c) Five weighted component scores (0–100 each) → composite
| Component | Weight | Driven by |
|---|---|---|
| Trend & structure | 20% | % above the 200-day SMA (tiered) |
| Base quality | 25% | pass + depth + prior run + length + tightness bonuses |
| Relative strength | 25% | RS percentile across the scanned universe |
| Volume signature | 15% | volume dry-up in base / contraction |
| Breakout quality | 15% | distance-to-pivot bands; **volume-scaled once broken out** |

`composite = Σ weightᵢ × scoreᵢ` → **grade**: A+ ≥85, A ≥75, B ≥65, C ≥55, else REJECT.
A grade is then **capped by RS percentile** (A+ needs ≥80, A needs ≥70) — *skipped for tiny universes*
so a single-ticker scan isn't unfairly downgraded.

### (d) Risk block
Stop (ATR-based or fixed %), risk-per-share, and reward-to-risk vs the first profit target.

### Performance note
During the scan the data provider is **cache-only** — it never makes live Yahoo calls (benchmark index
data is merged in from the step-01 cache). This keeps a 1,700-name scan at ~40 seconds.

---

## 6. Context markers & guards (all flag-only unless noted)

These add decision context **without changing the deterministic grade** (except the weak-volume rule):

- **Market regime (Marker 1):** is each stock's benchmark index above its own 200-day SMA? Tags
  `uptrend` / `risk-off` / `unknown`. (Minervini's #1 rule: trade with the market.)
- **Sector strength (Marker 2):** ranks sectors by median 3-month return; tags `leading` / `inline` /
  `lagging` so you can avoid strong stocks in weak groups.
- **Earnings guard:** for A+/A candidates, fetches the next earnings date (Yahoo `.calendar`) and flags
  any reporting within `EARNINGS_GUARD_DAYS` (7) — don't initiate into an earnings gap.
- **Entry-actionability `status`:** `Ready` (coiled just under the pivot) / `In-breakout` / `Extended`
  (already ran — avoid chasing) / `Near` / `Watch`. The report's **ACTIONABLE NOW** block lists the
  A+/A names "Ready at the pivot" so you can use a buy-stop-at-pivot workflow and catch them *as* they
  trigger rather than after.
- **Weak-volume breakout downgrade (affects grade):** once a breakout clears the pivot, its score scales
  by volume (≥1.4×→100, 1.2–1.4×→80, <1.2×→65) instead of always 100. Pre-breakout names are unaffected.

---

## 7. Outputs

- `reports/scan/latest.json` — machine-readable results (the single source of truth for 05–07).
- `reports/scan/scan_<ts>.txt` — human report; starts with MARKET REGIME, SECTOR STRENGTH, EARNINGS
  WATCH, and ACTIONABLE NOW summary blocks, then the ranked detail.
- `reports/scan/history.jsonl` — one flat row per ticker per run (for tracking over time).
- `reports/problems_with_tickers.txt` — unmapped/failed tickers **and** failed benchmark indices.
- `docs/index.html` — published rank table.

---

## 8. Configuration

Everything tunable lives in `config.py` with inline rationale — SMA periods, base thresholds, RS
lookbacks, composite weights, grade bands, ATR stop settings, the markers' thresholds
(`EARNINGS_GUARD_DAYS`, `MIN_UNIVERSE_FOR_RS_PERCENTILE`, breakout volume tiers, etc.).

---

## 9. Known limitations & suggested improvements

**Faithful to the *technical* half of SEPA; the *fundamental* half is missing.**

1. **No fundamental leg (highest-value gap).** SEPA = fundamentals **and** technicals (EPS/sales
   acceleration, margins, ROE — "leading stocks in leading groups"). The engine fetches some of these
   fields but doesn't use them in scoring, so a chart-perfect base on a company with collapsing earnings
   scores like a true leader. *Improvement:* add a fundamental gate/score. **Data catch:** Yahoo `.info`
   is rate-limited to zero here — use **SEC EDGAR** (free, not throttled) or a paid fundamentals API.
2. **Relative strength isn't a market-wide rank.** It's a percentile across *the watchlist*, not the
   whole market, and the legacy `rs_rating` is a homemade scaling. *Improvement:* compute a true
   **IBD-style RS Rating (1–99)** against a broad reference universe; optionally add Mansfield RS.
3. **Base detection isn't a true VCP.** It uses low-volatility windows / price-range rather than counting
   progressive volatility contractions with volume dry-up. *Improvement:* detect 2–4 ever-tighter
   contractions explicitly.
4. **Profit-taking is two fixed targets (10% / 45%).** *Improvement:* tiered/trailing exits.
5. **`within 15% of 52w high`** is stricter than Minervini's 25% — intentional but worth documenting.
6. **Daily EOD lag.** The scan can't catch the intraday breakout instant; the intended workflow is to
   use the **ACTIONABLE NOW "Ready"** list to place buy-stops at the pivot.
7. **Data gaps to watch:** `^WIG20` (Polish index) has no reliable Yahoo symbol (1 ticker affected,
   flagged); ~5% of sectors are blank (recent IPOs / Asian ADRs); a few tickers fail to fetch each run
   (now honestly reported rather than silently NaN).

**Operationally solid:** currency-correct, fast (~2–3 min full refresh), reproducible, with the failure
modes surfaced in `problems_with_tickers.txt` rather than hidden.

---

*Disclaimer: educational tool implementing a published methodology — not financial advice.*
