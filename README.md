# Minervini SEPA Scanner

A professional-grade stock scanner implementing Mark Minervini's exact SEPA (Stock Exchange Price Action) methodology for European stocks. Evaluates stocks against the complete 5-part Minervini checklist, assigns a composite score (0–100), and grades each stock A+/A/B/C/REJECT.

## Features

1. **Complete Minervini SEPA Checklist** — all 5 parts
   - ✅ Trend & Structure (NON-NEGOTIABLE)
   - ✅ Base Quality (3–8 week bases, ≤25% depth)
   - ✅ Relative Strength (RS line, RSI > 60)
   - ✅ Volume Signature (dry volume in base, +40% on breakout)
   - ✅ Breakout Day Rules (pivot clearance, volume expansion)

2. **Automatic Grading** via composite score (0–100)
   - **A+ (≥85)**: Full position
   - **A (75–84)**: Half position
   - **B/C**: Watch / caution
   - **REJECT (<55)**: Walk away

3. **European Market Focus** — DAX, CAC 40, AEX, Swiss, Nordics and more. Per-ticker benchmarks via `benchmark_mapping.py`.

4. **Free Data Sources** — Yahoo Finance (primary), Alpha Vantage (fallback). No API key required for basic scanning.

5. **AI Analysis** — optional ChatGPT step ranks new candidates and reviews existing holdings.

---

## Setup

```bash
pip install -r requirements.txt
```

Copy `config.example.env` to `.env` and fill in the keys you need:

```
ALPHA_VANTAGE_API_KEY=your_key_here   # optional
TRADING212_API_KEY=your_key_here      # optional — needed for step 02
TRADING212_API_SECRET=your_secret_here
OPENAI_API_KEY=your_key_here          # optional — needed for steps 06 and 07
```

---

## Quick Start

```bash
python run_pipeline.py                                      # full watchlist, cached data
python run_pipeline.py --refresh                            # force fresh Yahoo data
python run_pipeline.py --watchlist watchlist_test.csv       # short watchlist (quick test)
python run_pipeline.py --csv                                # also export CSV from step 04
python run_pipeline.py --exclude-06 --exclude-07            # skip both GPT steps (no token cost)
```

---

## Pipeline Steps

| Step | Script | What it does | Output |
|------|--------|--------------|--------|
| 01 | `01_fetch_prices.py` | Fetch/cache Yahoo OHLCV for watchlist | `data/cached_stock_data_new_pipeline.json` |
| 02 | `02_fetch_positions.py` | Fetch open positions from Trading212 | `data/positions_new_pipeline.json` |
| 03 | `03_prepare_data.py` | Merge cache + positions + watchlist | `data/prepared_for_minervini.json` |
| 04 | `04_scan.py` | Run SEPA scorer → grades + scores | `reports/scan/scan_<ts>.txt`, `reports/scan/latest.json` |
| 05 | `05_prep_ai_data.py` | Prepare A+/A stocks + holdings for AI | `reports/data/ai_*.json` |
| 06 | `06_analyze_holdings.py` | ChatGPT review of existing holdings | `reports/ai/holdings_<ts>.txt` |
| 07 | `07_rank_candidates.py` | ChatGPT ranking of new candidates | `reports/ai/candidates_<ts>.txt` |

---

## Project Structure

```
run_pipeline.py             # Single entry point

# Pipeline steps
01_fetch_prices.py
02_fetch_positions.py
03_prepare_data.py
04_scan.py
05_prep_ai_data.py
06_analyze_holdings.py
07_rank_candidates.py

# Scanner engine
sepa_checklist.py           # 5-part Minervini checklist (pass/fail)
sepa_scorer.py              # Composite scoring → grade
sepa_report.py              # Report formatter
sepa_web_export.py          # HTML rank table → docs/index.html

# Data layer
trading_bot.py              # Orchestrates data + Trading212 client
data_provider.py            # Yahoo / Alpha Vantage / Trading212 fetcher
trading212_client.py        # Trading212 API client
fetch_utils.py              # Batch fetch logic
watchlist_loader.py         # Loads watchlist.csv
benchmark_mapping.py        # Per-ticker benchmark assignment

# Utilities
config.py                   # All thresholds, paths, API settings
cache_utils.py
currency_utils.py
ticker_utils.py
position_sizing.py
openai_utils.py
logger_config.py
validators.py

# Inputs
watchlist.csv               # type, yahoo_symbol, trading212_symbol, benchmark_index
watchlist_test.csv          # short list for quick runs

# Outputs
data/                       # cached OHLCV, positions (gitignored)
reports/scan/               # scan_<ts>.txt — one per run
reports/ai/                 # holdings_<ts>.txt, candidates_<ts>.txt
reports/data/               # intermediate JSON for steps 06/07 (gitignored)
docs/index.html             # live HTML rank table
```

---

## Minervini SEPA Criteria

### Part 1: Trend & Structure (NON-NEGOTIABLE)
All must pass or the stock is rejected immediately:
- Price above 50, 150, 200 SMA
- 50 SMA > 150 SMA > 200 SMA, all sloping up
- Price ≥30% above 52-week low
- Price within 15% of 52-week high

### Part 2: Base Quality
- Length: 3–8 weeks
- Depth: ≤25% (≤15% is elite)
- Volume contracts inside base
- Tight closes near highs

### Part 3: Relative Strength
- RS line near or at new highs
- Outperforms chosen benchmark (DAX, CAC, etc.)
- RSI(14) > 60 before breakout

### Part 4: Volume Signature
- Dry volume in base
- Breakout volume +40%+
- No heavy sell volume before breakout

### Part 5: Breakout Day Rules
- Clears pivot decisively (≥2% above base high)
- Closes in top 25–30% of range
- Volume expansion present

---

## Troubleshooting

### 401 on step 02

`02_fetch_positions.py` calls the Trading212 Live API. Common causes:
- Wrong or expired API key — regenerate in Trading212 → Invest → Settings → API
- Demo vs Live mismatch — this app uses the Live API
- `.env` not loaded — run from the project root

To skip Trading212: run `01 → 03 → 04 → 05` directly (step 03 handles missing positions gracefully).

---

## Disclaimer

For educational purposes only. Trading involves risk of loss. Always do your own research. This implements Minervini's methodology but is not financial advice.
