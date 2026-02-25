# Pipeline

**main** has only **Pipeline V2**. Run: `python run_pipeline_v2.py`. See **PIPELINE_V2.md**.

The **original pipeline** (01 → 04 → 05 → 06 → 07) is on branch **pipeline-v1**; its scripts are not on main. See **PIPELINE_ARCHIVE.md**.

---

## Original pipeline (on branch pipeline-v1 only)

Script order: **01 → 02 → 03 → 04 → 05 → 06 → 07**. Optional 6-month OHLCV: use `--use-6mo` on 05, 06, 07. Checkout branch **pipeline-v1** to run it.

---

## Scripts (execution order)

| Step | Script | Purpose |
|------|--------|--------|
| 1 | `01_fetch_yahoo_watchlist.py` | Fetch OHLCV from Yahoo for watchlist (CSV or legacy .txt) → `data/cached_stock_data_new_pipeline.json` |
| 2 | `02_fetch_positions_trading212.py` | Fetch open positions from Trading212 → `data/positions_new_pipeline.json` |
| 3 | `03_prepare_for_minervini.py` | Load cache + positions + watchlist; build `data/prepared_for_minervini.json` (tickers with benchmark_index); write `reports/problems_with_tickers.txt` |
| 4 | `04_generate_full_report.py` | Run Minervini scan (reads prepared file or legacy cache); per-stock benchmark when available; writes summary/detailed reports and `reports/scan_results_latest.json` |
| 5 | `05_prepare_chatgpt_data.py` | Load scan results from 04 + cache + positions; output `reports/new_pipeline/prepared_existing_positions.json`, `prepared_new_positions.json` (A+/A only). Does not run scan. |
| 5b | `05_prepare_chatgpt_data.py --use-6mo` | Same as 05 but OHLCV limited to last 126 days → `*_6mo.json`. |
| 6 | `06_chatgpt_existing_positions.py` | ChatGPT analysis for **existing positions** → `reports/new_pipeline/chatgpt_existing_positions_<ts>.txt` |
| 7 | `07_chatgpt_new_positions.py` | ChatGPT analysis for **new position candidates** (A+/A) → `reports/new_pipeline/chatgpt_new_positions_<ts>.txt` (default `--limit 50`) |

## Watchlist

- **CSV** (recommended): `watchlist.csv` with header `type,yahoo_symbol,trading212_symbol,benchmark_index`.
  - `type`: `ticker` or `index`. Only tickers are scanned; indexes are fetched from Yahoo and used as benchmarks for relative strength.
  - `yahoo_symbol`: Symbol for Yahoo (e.g. `AAPL`, `RWE.DE`, `^GSPC`).
  - `trading212_symbol`: Symbol used by Trading212 (e.g. `AAPL`, `RWED`). Optional for indexes.
  - `benchmark_index`: Benchmark for RS for that ticker (e.g. `^GSPC`, `^GDAXI`).
- **Legacy**: `watchlist.txt` — one symbol per line (Yahoo symbol). Treated as tickers; benchmark from `benchmark_mapping.get_benchmark(symbol)`.

01 uses `watchlist_loader.load_watchlist(path)` and fetches all symbols from the watchlist (tickers + indexes). Default watchlist: `watchlist.csv` (fallback to legacy if CSV not used).

## Data paths

- Cache: `data/cached_stock_data_new_pipeline.json`
- Positions: `data/positions_new_pipeline.json`
- Prepared for Minervini: `data/prepared_for_minervini.json` (written by 03, read by 04)
- Problems report: `reports/problems_with_tickers.txt` (written by 03)
- Scan results: `reports/scan_results_latest.json` (written by 04, read by 05)
- Prepared for ChatGPT: `reports/new_pipeline/prepared_existing_positions.json`, `prepared_new_positions.json` (and `*_6mo.json` if using 6mo)
- Reports: `reports/new_pipeline/chatgpt_*.txt`

## Run order

1. `python 01_fetch_yahoo_watchlist.py`   (optional: `--watchlist watchlist.csv`)
2. `python 02_fetch_positions_trading212.py`   (optional if you only want new-position suggestions)
3. `python 03_prepare_for_minervini.py`
4. `python 04_generate_full_report.py`
5. `python 05_prepare_chatgpt_data.py`   (optional: `--use-6mo`)
6. `python 06_chatgpt_existing_positions.py`   (optional: `--use-6mo`)
7. `python 07_chatgpt_new_positions.py`   (optional: `--use-6mo`)

Token usage and 6mo vs full OHLCV: see `reports/new_pipeline/TOKEN_COMPARISON_ORIGINAL_VS_6MO.md` and `TOKEN_RECORD_AND_IMPROVEMENTS.md` (if present).

## Supporting scripts

- **watchlist_loader.py** – Load CSV or legacy watchlist; `get_yahoo_symbols_for_fetch(rows)`, `get_ticker_rows(rows)`.
- **fetch_utils.py** – Shared fetch logic (fetch_stock_data_with_retry, etc.). Used by 01. `generate_full_report.py --refresh` uses fetch_utils to fill legacy cache.
- **04_generate_full_report.py** / **generate_full_report.py** – Minervini scan. Prefers `data/prepared_for_minervini.json` if present; else legacy `data/cached_stock_data.json`. Use `--refresh` to fetch into legacy cache. Writes `reports/scan_results_latest.json` for step 05.
