# Pipeline V2

**Run:** `python run_pipeline_v2.py` (optionally `--csv`, `--refresh`).

**Script and config names confusing?** See **SCRIPTS_AND_CONFIG_REFERENCE.md** for a clear map of what each script and config does and what to ignore when using V2.

---

V2 is now the primary pipeline. It writes to `reports/v2/` and `scan_results_v2_latest.json`; it does not overwrite `scan_results_latest.json` or the original report paths.

## What V2 Changes

- **Structural eligibility** – Separate gate: trend + valid base + liquidity (min $ volume) + min price. If not eligible → REJECT, no scoring.
- **Prior run** – Base must follow a ≥25% advance (config: `MIN_PRIOR_RUN_PCT`). Fails base quality and penalizes composite if below.
- **RS percentile** – 3M return computed for full universe; percentile rank (0–100) used as RS component score.
- **Base type** – `flat_base` | `cup` | `high_tight_flag` | `standard_base` from depth/prior run/length.
- **Composite score** – Weighted 0–100: Trend 25%, Base 25%, RS 20%, Volume 15%, Breakout 15%. Grade from score: ≥85 A+, 75–84 A, 65–74 B, 55–64 C, &lt;55 REJECT.
- **ATR stop (optional)** – If `USE_ATR_STOP_V2` is True: stop = max(pivot - ATR×mult, lowest low of breakout week).
- **Output** – Single deterministic JSON per ticker (see spec in task). Two outputs: **LLM/engine JSON** and **user-friendly text report**.

## Scripts (main has only these — Pipeline V2 only)

| Step | Script | Purpose |
|------|--------|--------|
| 01 | `01_fetch_yahoo_watchlist.py` | Fetch/cache Yahoo OHLCV for watchlist |
| 02 | `02_fetch_positions_trading212.py` | Fetch open positions from Trading212 |
| 03 | `03_prepare_for_minervini.py` | Build `data/prepared_for_minervini.json` for scanner |
| 04 V2 | `04_generate_full_report_v2.py` | V2 scan → `reports/scan_results_v2_latest.json`, `reports/v2/sepa_scan_user_report_<ts>.txt`; optional `--csv` |
| 05 V2 | `05_prepare_chatgpt_data_v2.py` | Prep existing + new from V2 scan → `reports/v2/prepared_existing_positions_v2.json`, `prepared_new_positions_v2.json` |
| 06 V2 | `06_chatgpt_existing_positions_v2.py` | ChatGPT for existing positions → `reports/v2/chatgpt_existing_positions_v2_<ts>.txt` |
| 08 | `08_chatgpt_new_positions_v2.py` | ChatGPT for new candidates → `reports/v2/chatgpt_new_positions_v2_<ts>.txt` |

## Data flow

1. **01, 02, 03** – Same cache and `data/prepared_for_minervini.json`.
2. **04 V2** – Runs V2 scan; writes `reports/scan_results_v2_latest.json`, `reports/v2/sepa_scan_user_report_<ts>.txt`; optional CSV.
3. **05 V2** – Reads `scan_results_v2_latest.json` + positions + cache (with watchlist T212→Yahoo mapping); writes `reports/v2/prepared_existing_positions_v2.json` and `prepared_new_positions_v2.json`.
4. **06 V2** – Reads `reports/v2/prepared_existing_positions_v2.json`; writes `reports/v2/chatgpt_existing_positions_v2_<ts>.txt`.
5. **08** – Reads `prepared_new_positions_v2.json`; writes `reports/v2/chatgpt_new_positions_v2_<ts>.txt`.

## Config (V2 only)

- `minervini_config_v2.py` – Prior run, liquidity, price min, composite weights, grade bands, ATR V2, paths.
- Main `config.py` – Unchanged; V2 scanner still uses its trend/base/RS/volume/breakout thresholds where applicable.

## Run order (V2)

**01 → 02 → 03 → 04 V2 → 05 V2 → 06 V2 → 08.**

**Single entry point:** `python run_pipeline_v2.py` (runs all steps). Optional: `--csv`, `--refresh`.

Step by step: 01, 02, 03, then `04_generate_full_report_v2.py`, `05_prepare_chatgpt_data_v2.py`, `06_chatgpt_existing_positions_v2.py`, `08_chatgpt_new_positions_v2.py`.

Original pipeline (01→04→05→06→07) is on branch **pipeline-v1** only; see **PIPELINE_ARCHIVE.md**.
