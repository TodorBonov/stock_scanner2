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

## Scripts (V2 only)

| Step | Script | Purpose |
|------|--------|--------|
| 4 V2 | `04_generate_full_report_v2.py` | Run V2 scan; write `reports/scan_results_v2_latest.json` and `reports/v2/sepa_scan_user_report_<ts>.txt`; optional `--csv` |
| 5 | `05_prepare_chatgpt_data.py` | Prepare existing positions for 06: write `reports/new_pipeline/prepared_existing_positions.json` (positions + OHLCV from cache). Works without main 04 scan; prepared_new may be empty. |
| 5 V2 | `05_prepare_chatgpt_data_v2.py` | Load V2 scan JSON; write `reports/v2/prepared_existing_positions_v2.json`, `prepared_new_positions_v2.json` (A+/A with V2 fields) for 08 |
| 6 | `06_chatgpt_existing_positions.py` | ChatGPT analysis for existing (opened) positions; reads `reports/new_pipeline/prepared_existing_positions.json`; writes `reports/new_pipeline/chatgpt_existing_positions_<ts>.txt` |
| 8 | `08_chatgpt_new_positions_v2.py` | ChatGPT analysis for new candidates using V2 structured data; writes `reports/v2/chatgpt_new_positions_v2_<ts>.txt` |

## Data flow

1. **01, 02, 03** – Unchanged. Same cache and `data/prepared_for_minervini.json`.
2. **04 V2** – Reads prepared (or legacy cache), runs `MinerviniScannerV2.scan_universe()` (two-phase: 3M returns → percentile → scan), writes:
   - `reports/scan_results_v2_latest.json` (for LLM and 05 V2)
   - `reports/v2/sepa_scan_user_report_<ts>.txt`
   - Optional CSV via `--csv`
3. **05** – Reads positions + cache; writes `reports/new_pipeline/prepared_existing_positions.json` for 06 (no main 04 scan required).
4. **05 V2** – Reads `scan_results_v2_latest.json`, builds prepared JSON with full V2 fields for 08.
5. **06** – Reads `reports/new_pipeline/prepared_existing_positions.json`, sends each position to ChatGPT; writes `reports/new_pipeline/chatgpt_existing_positions_<ts>.txt`.
6. **08** – Reads `prepared_new_positions_v2.json`, sends to ChatGPT with prompt that references composite_score, base type, rs_percentile, pivot, stop_method, etc.

## Config (V2 only)

- `minervini_config_v2.py` – Prior run, liquidity, price min, composite weights, grade bands, ATR V2, paths.
- Main `config.py` – Unchanged; V2 scanner still uses its trend/base/RS/volume/breakout thresholds where applicable.

## Run order (V2)

**01 → 02 → 03**, then 04 V2 → 05 → 05 V2 → 06 → 08.

**Single entry point:** `python run_pipeline_v2.py` (runs all steps in order). Optional: `python run_pipeline_v2.py --csv`.

Or run step by step:

1. `python 01_fetch_yahoo_watchlist.py`
2. `python 02_fetch_positions_trading212.py`  (optional)
3. `python 03_prepare_for_minervini.py`
4. `python 04_generate_full_report_v2.py`     (optional: `--csv`, `--ticker X`, `--tickers A,B,C`)
5. `python 05_prepare_chatgpt_data.py`           — prepares existing positions for 06
6. `python 05_prepare_chatgpt_data_v2.py`       — prepares V2 new positions for 08
7. `python 06_chatgpt_existing_positions.py`    (optional: `--use-6mo`) — evaluates opened positions
8. `python 08_chatgpt_new_positions_v2.py`      (optional: `--limit N`)

Existing 04→05→06→07 pipeline is unchanged and can be run as before.
