# Pipelines and branch strategy

This repo contains two pipelines. The **new pipeline** is the default workflow on **main**. The **legacy pipeline** is preserved on a separate branch for reference or occasional use.

---

## Branch strategy

| Branch | Purpose |
|--------|--------|
| **main** | Default. Use this for day-to-day work. New pipeline (New1–New5) is the recommended workflow. Legacy scripts (01–07) remain in the tree but are not the primary flow. |
| **pipeline/legacy-01-07** | Snapshot of the repo with the **legacy pipeline** (01–07) as the preserved reference. Check out this branch when you need to run or refer to the old pipeline. |

**To use the legacy pipeline:**

```bash
git checkout pipeline/legacy-01-07
# Run 01 → 02 → 03 → 04 (and optionally 05, 06, 07) as in FLOW.md
# Or use run_full_pipeline.ps1 / run_latest_data_pipeline.ps1
```

**To return to the new pipeline:**

```bash
git checkout main
```

---

## New pipeline (default on main)

**Scripts:** New1 → New2 → New3 → [New4, New5]. Optional 6-month OHLCV variants: New3_6mo, New4_6mo, New5_6mo.

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

**Data paths (new pipeline):**

- Cache: `data/cached_stock_data_new_pipeline.json`
- Positions: `data/positions_new_pipeline.json`
- Prepared: `reports/new_pipeline/prepared_existing_positions.json`, `prepared_new_positions.json` (and `*_6mo.json` if using 6mo)
- Reports: `reports/new_pipeline/chatgpt_*.txt`

**Typical run order:**

1. `python New1_fetch_yahoo_watchlist.py`
2. `python New2_fetch_positions_trading212.py`   (optional if you only want new-position suggestions)
3. `python New3_prepare_chatgpt_data.py`
4. Optionally: `python New3_prepare_chatgpt_data_6mo.py`
5. `python New4_chatgpt_existing_positions.py`  (and/or `New4_chatgpt_existing_positions_6mo.py`)
6. `python New5_chatgpt_new_positions.py`       (and/or `New5_chatgpt_new_positions_6mo.py`)

Token usage and 6mo vs full OHLCV comparison: see `reports/new_pipeline/TOKEN_COMPARISON_ORIGINAL_VS_6MO.md` and `TOKEN_RECORD_AND_IMPROVEMENTS.md`.

---

## Legacy pipeline (branch pipeline/legacy-01-07)

**Scripts:** 01 → 02 → 03 → 04 / 05 / 06. Optional: 07.

| Step | Script | Purpose |
|------|--------|--------|
| 1 | `01_fetch_stock_data.py` | Fetch and cache from watchlist → `data/cached_stock_data.json` |
| 2 | `02_generate_full_report.py` | Minervini scan → summary/detailed reports + `reports/scan_results_latest.json` |
| 3 | `03_position_suggestions.py` | Trading212 positions + scan results → EXIT/REDUCE/HOLD/ADD → `reports/position_suggestions_*.txt` |
| 4 | `04_chatgpt_validation.py` | ChatGPT validation of A/B stocks → `reports/summary_Chat_GPT_*.txt` |
| 5 | `05_chatgpt_validation_advanced.py` | ChatGPT advanced (positions + A+/A) → `reports/summary_Chat_GPT_advanced_*.txt` |
| 6 | `06_chatgpt_position_suggestions.py` | Send position suggestions report to ChatGPT |
| 7 | `07_retry_failed_stocks.py` | Retry failed fetches, update cache |

**Data paths (legacy):**

- Cache: `data/cached_stock_data.json`
- Scan results: `reports/scan_results_latest.json`
- Reports: `reports/summary_report_*.txt`, `reports/position_suggestions_*.txt`, `reports/summary_Chat_GPT*.txt`

**Full description:** See **FLOW.md** (currency, position-suggestion logic, script order).

**Convenience scripts (legacy):**

- `run_full_pipeline.ps1` / `run_full_pipeline.cmd` — 01 → 02 → 03 → 04 → 06 (and optional push)
- `run_latest_data_pipeline.ps1` — 02 → 03 → 04 using existing cache (no fetch)

Use these on branch **pipeline/legacy-01-07** when you want to run the legacy pipeline.
