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

- [ ] **5. Fragile control flow.** `_check_volume_signature` uses `if 'lookback_days' not in locals()`.
  - Files: `sepa_checklist.py`
  - Plan: compute `lookback_days` explicitly at the top of the function.

- [ ] **6. `scan_stock` mutates `base_info["data"]` then restores.**
  - Files: `sepa_scorer.py`
  - Plan: pass a clipped copy to `_check_breakout_rules`/`_calculate_buy_sell_prices`
    instead of mutating shared state.

- [ ] **7. Step 06/07 print "08 V2" headers / argparse say "08".**
  - Files: `06_analyze_holdings.py`, `07_rank_candidates.py`
  - Plan: correct labels to 06 / 07.

- [ ] **8. `config.py` comments reference renamed files that no longer exist on main.**
  - Files: `config.py`
  - Plan: update comments to current step filenames.

- [ ] **9. `data_provider.py` logs outside the project logger hierarchy.**
  - Files: `data_provider.py`
  - Plan: use `logger_config.get_logger(__name__)` so logs hit the rotating file handler.

## Security (low)

- [ ] **10. `validate_api_key` / `mask_credential` defined but unused.** (optional)
  - Plan: validate keys at client init, mask in logs.

## Notes
- `pytest` not installed locally; install `requirements.txt` to validate against existing tests.
- `bot.py` / `trading_bot.py` / `position_sizing.py` may be legacy — confirm before relying on them.
