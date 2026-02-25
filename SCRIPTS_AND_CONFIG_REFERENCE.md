# Scripts & configs — quick reference

**You use Pipeline V2.** One command: `python run_pipeline_v2.py`

This file explains what each script and config is, so the names stop being confusing.

---

## What to run (Pipeline V2)

| You run | It runs these in order |
|--------|-------------------------|
| `python run_pipeline_v2.py` | 01 → 02 → 03 → **04 V2** → 05 → **05 V2** → 06 → **08** |

So you never need to remember “04 vs 04_v2” or “07 vs 08” — the runner calls the right ones.

---

## Scripts: name → role

### Scripts on main (Pipeline V2 only)

| Script | Step | What it does |
|--------|------|--------------|
| `01_fetch_yahoo_watchlist.py` | 01 | Fetch/cache Yahoo OHLCV for watchlist |
| `02_fetch_positions_trading212.py` | 02 | Fetch open positions from Trading212 |
| `03_prepare_for_minervini.py` | 03 | Build prepared data for the scanner |
| `04_generate_full_report_v2.py` | 04 V2 | V2 scan → `reports/v2/sepa_scan_user_report_*.txt`, `scan_results_v2_latest.json` |
| `05_prepare_chatgpt_data_v2.py` | 05 V2 | Prep existing + new from V2 scan → `reports/v2/prepared_*_v2.json` |
| `06_chatgpt_existing_positions_v2.py` | 06 V2 | ChatGPT for existing positions → `reports/v2/chatgpt_existing_positions_v2_*.txt` |
| `08_chatgpt_new_positions_v2.py` | 08 | ChatGPT for new candidates → `reports/v2/chatgpt_new_positions_v2_*.txt` |

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
| **config.py** | Almost everything | Main settings: API keys, paths, rate limits, OpenAI model, **original** scanner thresholds, cache paths. |
| **minervini_config_v2.py** | V2 scan & V2 reports only | V2-only: prior run %, grade bands (A+/A/B/C), composite weights, ATR stop, paths for `reports/v2/` and `scan_results_v2_latest.json`. |
| **pre_breakout_config.py** | Only on branch pipeline-v1 | Pre-breakout view (add-on to original scan). Removed from main. |
| **logger_config.py** | All scripts | Logging setup (not “business” config). |

**In short:**  
- Change **config.py** for API keys, OpenAI model, and general paths.  
- Change **minervini_config_v2.py** for V2 scan rules (grades, weights, thresholds).  
- **pre_breakout_config.py** exists only on branch pipeline-v1 (removed from main).

---

## One-page summary

- **Run:** `python run_pipeline_v2.py` (optionally `--csv` or `--refresh`).
- **Scripts on main:** 01, 02, 03, 04_generate_full_report_v2, 05_prepare_chatgpt_data_v2, 06_chatgpt_existing_positions_v2, 08_chatgpt_new_positions_v2. Nothing for pipeline 1.
- **Config:** **config.py** + **minervini_config_v2.py**.
- **Original pipeline:** Only on branch **pipeline-v1**; see **PIPELINE_ARCHIVE.md**.
