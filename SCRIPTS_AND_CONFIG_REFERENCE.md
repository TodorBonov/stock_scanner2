# Scripts & configs — quick reference

**You use Pipeline V2.** One command: `python run_pipeline_v2.py`

This file explains what each script and config is, so the names stop being confusing.

---

## What to run (Pipeline V2)

| You run | It runs these in order |
|--------|-------------------------|
| `python run_pipeline_v2.py` | 01 → 02 → 03 → **04 V2** → **05 V2** → **06 V2** → **07** |

So you never need to remember “04 vs 04_v2” or “07 vs 08” — the runner calls the right ones.

---

## Scripts: name → role

### Scripts on main (Pipeline V2 only)

| Script | Step | What it does |
|--------|------|--------------|
| `01_fetch_yahoo_watchlist_V2.py` | 01 | Fetch/cache Yahoo OHLCV for watchlist |
| `02_fetch_positions_trading212_V2.py` | 02 | Fetch open positions from Trading212 |
| `03_prepare_for_minervini_V2.py` | 03 | Build prepared data for the scanner |
| `04_generate_full_report_v2.py` | 04 V2 | V2 scan → `reportsV2/sepa_scan_user_report_*.txt`, `reportsV2/scan_results_v2_latest.json` |
| `05_prepare_chatgpt_data_v2.py` | 05 V2 | Prep existing + new from V2 scan → `reportsV2/prepared_*_v2.json` |
| `06_chatgpt_existing_positions_v2.py` | 06 V2 | ChatGPT for existing positions → `reportsV2/chatgpt_existing_positions_v2_*.txt` |
| `07_chatgpt_new_positions_v2.py` | 07 | ChatGPT for new candidates → `reportsV2/chatgpt_new_positions_v2_*.txt` |

### Not on main (only on branch pipeline-v1)

These scripts were removed from main; they exist only on branch **pipeline-v1** (original pipeline):

| Script | Role on pipeline-v1 |
|--------|------------|
| `04_generate_full_report.py` | Original Minervini scan (writes `scan_results_latest.json`). |
| `07_chatgpt_new_positions.py` | Original “new positions” ChatGPT. |
| `04_chatgpt_existing_positions.py` | Stub that delegates to 06. |
| `05_chatgpt_new_positions.py` | Stub that delegates to 07. |
| `generate_full_report.py` | Stub that delegates to 04. |
| `pre_breakout_config.py` | Config for pre-breakout view (used by original 04). |
| `pre_breakout_utils.py` | Pre-breakout logic (used by original 04). |

---

## Config files: which is which

| Config file | Used by | What it’s for |
|-------------|--------|----------------|
| **config.py** | Everything | Single config: API keys, paths, rate limits, OpenAI model, **original** scanner thresholds, **and** V2 settings (prior run %, grade bands, composite weights, ATR V2, `reportsV2/` paths). |
| **pre_breakout_config.py** | Only on branch pipeline-v1 | Pre-breakout view (add-on to original scan). Removed from main. |
| **logger_config.py** | All scripts | Logging setup (not “business” config). |

**In short:** Change **config.py** for API keys, paths, scanner thresholds, and V2 scan rules (grades, weights, report paths). **pre_breakout_config.py** exists only on branch pipeline-v1.

---

## Watchlist and test data

| File | Purpose |
|------|---------|
| **watchlist.csv** | Main watchlist (type, yahoo_symbol, trading212_symbol, benchmark_index). Used by the pipeline. |
| **watchlist_test.csv** | Test watchlist used for testing (e.g. quick runs, CI, or manual tests). Same format as `watchlist.csv`. Do not remove. |

---

## One-page summary

- **Run:** `python run_pipeline_v2.py` (optionally `--csv` or `--refresh`).
- **Scripts on main:** 01_fetch_yahoo_watchlist_V2, 02_fetch_positions_trading212_V2, 03_prepare_for_minervini_V2, 04_generate_full_report_v2, 05_prepare_chatgpt_data_v2, 06_chatgpt_existing_positions_v2, 07_chatgpt_new_positions_v2. Nothing for pipeline 1.
- **Config:** **config.py** (single config for pipeline and V2).
- **Original pipeline:** Only on branch **pipeline-v1**; see **PIPELINE_ARCHIVE.md**.
