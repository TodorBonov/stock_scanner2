# Improvements TODO (code review 2026-06-11)

Temporary tracking file. Delete when all items are merged.
Working branch: `review-fixes` (off `main`).

## Correctness (high impact)

- [x] **1. Multi-currency normalization.** DONE. Added `get_fx_rate_to_usd` (cached,
  generic `<CUR>USD=X` lookup, GBp/GBX/ZAc/ILA/USX minor-unit handling) and
  `convert_ohlcv_and_info_to_usd` to `currency_utils.py`. Refactored `fetch_utils.py`
  (`fetch_stock_data`, `_build_result_from_hist`), `02_fetch_positions.py` and step 05's
  `ohlcv_currency` labeling to use it. 15 new unit tests. Worst case (`.L` pence 100x) fixed.

- [x] **2. RS uses live Yahoo instead of cache in V2 scan.** DONE. Implemented
  `CachedDataProviderV2.calculate_relative_strength` to compute RS from the cached snapshot
  (cache-first for both ticker and benchmark), falling back to the live provider only when a
  series is genuinely missing from cache. Eliminates ~2 live calls/stock and the mixed-vintage
  inconsistency. New test file `tests/test_scan_cached_provider.py` (loads `04_scan.py` via
  importlib) asserts no live calls + correct RS sign + live fallback.

- [x] **3. Benchmark history re-fetched twice per call and per stock.** DONE.
  `_check_relative_strength` now fetches benchmark history once and reuses it for both the
  manual-RS fallback and the RS-line check (was 2 fetches + the live call's internal fetch).

- [x] **4. Single/small-ticker scans under-grade (RS percentile = 0 caps A+/A).** DONE.
  Added `MIN_UNIVERSE_FOR_RS_PERCENTILE = 20` to config. `scan_universe` now only computes
  percentiles when the universe is large enough, else leaves them unset; `scan_stock` skips
  the RS grade cap when `rs_percentile is None`. Single-ticker scans keep their composite
  grade. New `tests/test_rs_percentile_gating.py` (3 tests).

## Maintainability / consistency

- [x] **5. Fragile control flow.** DONE. `_check_volume_signature` now computes `lookback_days`
  explicitly (from base start_date with a buffer, else default) instead of `if ... not in locals()`.

- [x] **6. `scan_stock` mutates `base_info["data"]` then restores.** DONE. Now builds a shallow
  copy with a clipped `data` frame (`base_info_for_breakout`) and passes that to the breakout /
  buy-sell calls; shared `base_info` is never mutated.

- [x] **7. Step 06/07 print "08 V2" headers / argparse say "08".** DONE. Fixed the two "08 V2"
  strings in `07_rank_candidates.py` (argparse description + report header) to "07 V2".
  (06 was already correct.)

- [x] **8. `config.py` comments reference renamed files that no longer exist on main.** DONE.
  Updated comments: `03_prepare_for_minervini.py`→`03_prepare_data.py`,
  `04_generate_full_report.py`→`04_scan.py`, `05_prepare_chatgpt_data.py`→`05_prep_ai_data.py`.

- [x] **9. `data_provider.py` logs outside the project logger hierarchy.** DONE. Switched to
  `logger_config.get_logger(__name__)` so its logs reach the rotating file handler.

## Security (low)

- [ ] **10. `validate_api_key` / `mask_credential` defined but unused.** (optional)
  - Plan: validate keys at client init, mask in logs.

## Notes
- `pytest` not installed locally; install `requirements.txt` to validate against existing tests.
- `bot.py` / `trading_bot.py` / `position_sizing.py` may be legacy — confirm before relying on them.
