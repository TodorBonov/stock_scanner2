# Minervini SEPA Scanner

Stock screening pipeline implementing Mark Minervini's SEPA (Stock Exchange Price Action) methodology. Fetches market data, runs a deterministic V2 composite scorer, and optionally uses ChatGPT to review holdings and rank candidates.

---

## Setup

```bash
pip install -r requirements.txt
```

Copy `config.example.env` to `.env` and fill in what you need:

```
ALPHA_VANTAGE_API_KEY=your_key   # optional — fallback data source
TRADING212_API_KEY=your_key      # optional — needed for step 02
TRADING212_API_SECRET=your_key   # optional — needed for step 02
OPENAI_API_KEY=your_key          # optional — needed for steps 06 and 07
```

---

## Running the pipeline

```bash
# Standard run (cached Yahoo data, all 7 steps)
python run_pipeline.py

# Fresh data from Yahoo
python run_pipeline.py --refresh

# Quick test with short watchlist
python run_pipeline.py --watchlist watchlist_test.csv --refresh

# Skip ChatGPT steps (no token cost)
python run_pipeline.py --exclude-06 --exclude-07

# Also export CSV from step 04
python run_pipeline.py --csv

# Fresh data, no GPT
python run_pipeline.py --refresh --exclude-06 --exclude-07
```

---

## Pipeline steps

| Step | Script | Input | Output |
|------|--------|-------|--------|
| 01 | `01_fetch_prices.py` | `watchlist.csv` | `data/cached_stock_data_new_pipeline.json` |
| 02 | `02_fetch_positions.py` | Trading212 API | `data/positions_new_pipeline.json` |
| 03 | `03_prepare_data.py` | cache + positions + watchlist | `data/prepared_for_minervini.json` |
| 04 | `04_scan.py` | prepared data | `reports/scan/latest.json`, `reports/scan/scan_<ts>.txt` |
| 05 | `05_prep_ai_data.py` | scan results + positions | `reports/data/ai_holdings_input.json`, `reports/data/ai_candidates_input.json` |
| 06 | `06_analyze_holdings.py` | ai_holdings_input.json | `reports/ai/holdings_<ts>.txt` |
| 07 | `07_rank_candidates.py` | ai_candidates_input.json | `reports/ai/candidates_<ts>.txt` |

Step 04 also writes `docs/index.html` (static HTML rank table) after each scan.

---

## Watchlist format

`watchlist.csv` — one row per ticker:

| Column | Required | Example | Notes |
|--------|----------|---------|-------|
| `type` | yes | `ticker` | `ticker` or `index` |
| `yahoo_symbol` | yes | `RWE.DE` | Symbol used for Yahoo Finance |
| `trading212_symbol` | no | `RWEd_EQ` | Only needed if different from Yahoo symbol |
| `benchmark_index` | no | `^GDAXI` | Per-ticker benchmark; defaults to `--benchmark` arg |
| `region` | no | `EU` | Attached to scan output |
| `sector` | no | `Utilities` | Attached to scan output |
| `market_cap` | no | `Large Cap` | Attached to scan output |

Benchmark index rows (`type=index`) are fetched for RS calculation but excluded from scanning.

---

## Project structure

```
run_pipeline.py             # Entry point — runs steps 01–07 in sequence

# Pipeline steps
01_fetch_prices.py
02_fetch_positions.py
03_prepare_data.py
04_scan.py
05_prep_ai_data.py
06_analyze_holdings.py
07_rank_candidates.py

# Scanner engine
sepa_checklist.py           # MinerviniScanner: 5-part checklist (base class for V2)
sepa_scorer.py              # MinerviniScannerV2: composite scorer, inherits from sepa_checklist
sepa_report.py              # Formats scan JSON into human-readable .txt and CSV
sepa_web_export.py          # Generates docs/index.html from latest.json

# Data layer
data_provider.py            # Yahoo Finance / Alpha Vantage / Trading212 data fetcher
trading212_client.py        # Trading212 REST API client
fetch_utils.py              # Batch fetch helpers (used by step 01)
watchlist_loader.py         # Parses watchlist.csv
cache_utils.py              # Legacy cache read/write (fallback for step 04)
benchmark_mapping.py        # Maps ticker suffixes to benchmark indices

# Utilities
config.py                   # All thresholds, file paths, API settings, scoring weights
currency_utils.py           # EUR/USD conversion via Yahoo EURUSD=X
ticker_utils.py             # Ticker normalisation and mapping
position_sizing.py          # Standalone position size calculator
openai_utils.py             # OpenAI API wrapper with retry logic
logger_config.py
validators.py

# Inputs
watchlist.csv               # Main watchlist
watchlist_test.csv          # Short list for quick test runs
data/ticker_mapping.json    # Manual symbol overrides (Yahoo ↔ Trading212)

# Outputs
data/                       # Cached OHLCV and positions (gitignored)
reports/scan/               # latest.json + scan_<ts>.txt per run
reports/ai/                 # holdings_<ts>.txt, candidates_<ts>.txt
reports/data/               # Intermediate JSON for steps 06/07 (gitignored)
reports/problems_with_tickers.txt
docs/index.html             # Live HTML rank table
```

---

## Troubleshooting

**Step 02 returns 401**
Trading212 Live API credentials are wrong or expired. Regenerate in Trading212 → Invest → Settings → API. Make sure `.env` is in the project root and loaded. To skip step 02 entirely, run steps 01 → 03 → 04 → 05; step 03 handles missing positions gracefully.

**Step 01 rate-limited by Yahoo**
Yahoo Finance aggressively rate-limits large batches. The pipeline retries automatically (60 s / 120 s / 180 s). For large watchlists run without `--refresh` to reuse cached data.

**A ticker is missing from the scan**
Check `reports/problems_with_tickers.txt` — step 03 logs every ticker it could not map or that lacked sufficient data (< 200 trading days required).

---

## Disclaimer

For educational purposes only. This implements Minervini's published methodology but is not financial advice. Trading involves risk of loss.
