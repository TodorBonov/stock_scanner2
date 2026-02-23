# Pipeline

This repo has a single pipeline: **New1 → New2 → New3 → New4 → New5**. Optional 6-month OHLCV variants: New3_6mo, New4_6mo, New5_6mo.

---

## Scripts

| Step | Script | Purpose |
|------|--------|--------|
| 1 | `New1_fetch_yahoo_watchlist.py` | Fetch OHLCV from Yahoo for watchlist → `data/cached_stock_data_new_pipeline.json` |
| 2 | `New2_fetch_positions_trading212.py` | Fetch open positions from Trading212 → `data/positions_new_pipeline.json` |
| 3 | `New3_prepare_chatgpt_data.py` | Load cache + positions, run Minervini scan (via 02), output prepared JSON for ChatGPT: `reports/new_pipeline/prepared_existing_positions.json`, `prepared_new_positions.json` (A+/A only) |
| 3b | `New3_prepare_chatgpt_data_6mo.py` | Optional. Same as New3 but OHLCV limited to last 126 days → `*_6mo.json`. Run **after** New3. |
| 4 | `New4_chatgpt_existing_positions.py` | ChatGPT analysis for **existing positions** → `reports/new_pipeline/chatgpt_existing_positions_<ts>.txt` |
| 4b | `New4_chatgpt_existing_positions_6mo.py` | Same as New4 using 6mo prepared data → `chatgpt_existing_positions_6mo_<ts>.txt` |
| 5 | `New5_chatgpt_new_positions.py` | ChatGPT analysis for **new position candidates** (A+/A) → `reports/new_pipeline/chatgpt_new_positions_<ts>.txt` (default `--limit 50`) |
| 5b | `New5_chatgpt_new_positions_6mo.py` | Same as New5 using 6mo prepared data → `chatgpt_new_positions_6mo_<ts>.txt` |

## Data paths

- Cache: `data/cached_stock_data_new_pipeline.json`
- Positions: `data/positions_new_pipeline.json`
- Prepared: `reports/new_pipeline/prepared_existing_positions.json`, `prepared_new_positions.json` (and `*_6mo.json` if using 6mo)
- Reports: `reports/new_pipeline/chatgpt_*.txt`

## Run order

1. `python New1_fetch_yahoo_watchlist.py`
2. `python New2_fetch_positions_trading212.py`   (optional if you only want new-position suggestions)
3. `python New3_prepare_chatgpt_data.py`
4. Optionally: `python New3_prepare_chatgpt_data_6mo.py`
5. `python New4_chatgpt_existing_positions.py`  (and/or `New4_chatgpt_existing_positions_6mo.py`)
6. `python New5_chatgpt_new_positions.py`       (and/or `New5_chatgpt_new_positions_6mo.py`)

Token usage and 6mo vs full OHLCV comparison: see `reports/new_pipeline/TOKEN_COMPARISON_ORIGINAL_VS_6MO.md` and `TOKEN_RECORD_AND_IMPROVEMENTS.md` (if present).

## Supporting scripts

- **fetch_utils.py** – Shared fetch logic (load_watchlist, fetch_stock_data, fetch_stock_data_with_retry, fetch_all_data). Used by New1 and by 02 when run with `--refresh`.
- **02_generate_full_report.py** – Minervini scan used by New3; can be run standalone for a full report. Use `--refresh` to fetch into the legacy cache first.
