# Naming proposal: scripts and configs

Suggested names based on **what each file does** (action + subject). No numbers; the pipeline runner would still call them in order.

---

## Pipeline scripts

| Current name | Suggested name | Rationale |
|--------------|----------------|-----------|
| `01_fetch_yahoo_watchlist.py` | **`fetch_yahoo_watchlist.py`** | Fetches Yahoo data for the watchlist. Drop "01" – order is in the runner. |
| `02_fetch_positions_trading212.py` | **`fetch_trading212_positions.py`** | Fetches positions from Trading212. Subject (trading212_positions) after action. |
| `03_prepare_for_minervini.py` | **`prepare_scanner_input.py`** | Prepares the single input file the scanner(s) need. "Minervini" is implied by the repo. |
| `04_generate_full_report.py` | **`scan_sepa_original.py`** | Original SEPA scan. Name says "scan" and "original" (vs V2). |
| `04_generate_full_report_v2.py` | **`scan_sepa_v2.py`** | V2 SEPA scan (composite score, grades). Clear pair with original. |
| `05_prepare_chatgpt_data.py` | **`prepare_chatgpt_existing.py`** | Prepares **existing positions** for ChatGPT (OHLCV + mapping). |
| `05_prepare_chatgpt_data_v2.py` | **`prepare_chatgpt_new_v2.py`** | Prepares **new candidates** from V2 scan for ChatGPT. |
| `06_chatgpt_existing_positions.py` | **`chatgpt_existing_positions.py`** | ChatGPT analyzes existing positions. Drop "06". |
| `06_chatgpt_existing_positions_v2.py` | **`chatgpt_existing_positions_v2.py`** | Same, V2 payload variant (if you keep it). |
| `07_chatgpt_new_positions.py` | **`chatgpt_new_candidates_original.py`** | ChatGPT ranks new candidates (original pipeline). "Candidates" = new ideas. |
| `08_chatgpt_new_positions_v2.py` | **`chatgpt_new_candidates_v2.py`** | ChatGPT ranks new candidates using V2 data. |
| `run_pipeline_v2.py` | **`run_pipeline.py`** | Single pipeline entry point. Drop "v2" once V2 is the only one you run. |

---

## Config files

| Current name | Suggested name | Rationale |
|--------------|----------------|-----------|
| `config.py` | **`config.py`** (keep) or **`app_config.py`** | Central app config (API, paths, OpenAI). "config" is standard; optional "app_" if you want to distinguish from "scan" config. |
| `minervini_config_v2.py` | **`scan_config.py`** | Config for the **V2 scan** (grades, weights, thresholds). No "minervini" in name if the repo is already Minervini-focused. |
| `pre_breakout_config.py` | **`pre_breakout_config.py`** (keep) | Already clear: config for the pre-breakout view. |
| `logger_config.py` | **`logger_config.py`** (keep) | Logging only; name is fine. |

---

## Summary (Pipeline V2 only)

If you rename only what the pipeline uses, the runner would call:

1. `fetch_yahoo_watchlist.py`
2. `fetch_trading212_positions.py`
3. `prepare_scanner_input.py`
4. `scan_sepa_v2.py`
5. `prepare_chatgpt_existing.py`
6. `prepare_chatgpt_new_v2.py`
7. `chatgpt_existing_positions.py`
8. `chatgpt_new_candidates_v2.py`

Entry point: **`run_pipeline.py`**

Configs you touch for V2: **`config.py`** (API, OpenAI, paths) and **`scan_config.py`** (V2 scan rules).

---

## If you adopt this

- Update **`run_pipeline_v2.py`** (or `run_pipeline.py`) **STEPS** list with the new script names.
- Search the repo for imports or subprocess calls that use the old filenames (e.g. `04_generate_full_report_v2`) and update them.
- Update **PIPELINE_V2.md**, **SCRIPTS_AND_CONFIG_REFERENCE.md**, **README**, and **PIPELINES.md** to use the new names.
- **minervini_config_v2.py** is imported by several modules; renaming to **scan_config.py** means changing those imports (and the module name inside the file if you want `import scan_config`).

I can apply the renames and reference updates across the repo if you want to go ahead.
