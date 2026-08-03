# Backtest — Quick First Pass (Design)

Date: 2026-08-03
Status: Approved

## Motivation

The V2 composite scorer's weights (trend 20%, base 25%, RS 25%, volume 15%, breakout 15%) and grade
bands (A+/A/B/C/REJECT) were chosen judgementally and have never been checked against forward returns —
this is stated plainly in `IMPROVEMENTS.md`. The trading review (Research Note 02) ranked this as the
top-priority open item: every other refinement to the scanner is speculative until there's a measurement
of whether higher grades actually predict better forward performance.

This is the **quick first pass** variant `IMPROVEMENTS.md` itself proposes as a fast, directional check
before investing in a clean, survivorship-bias-free dataset: run the scanner against the *current*
watchlist's own history, sliced at monthly intervals, and see whether composite score deciles /
grade bands are monotonically related to forward returns.

## Explicit non-goals

- **Not survivorship-bias-free.** Only today's watchlist tickers are used; delisted/removed names
  are not included. Results will skew optimistic. This is a known, accepted limitation of the
  "quick first pass," not an oversight — see `IMPROVEMENTS.md`'s "Key risk: survivorship bias" note.
  A full bias-free backtest is a separate, future piece of work requiring a point-in-time historical
  universe source that doesn't currently exist in this project.
- **Not a new scoring engine.** The replay must call the existing `MinerviniScannerV2.scan_stock()`
  unmodified, fed a truncated price history per slice date. It must not reimplement or approximate
  the scoring logic, or the backtest would be measuring a different system than the one producing
  live grades.
- **Not integrated into `run_pipeline.py`.** This is an offline analysis tool run on demand, not a
  step in the daily 01–07 pipeline.

## Architecture

New top-level folder, physically separate from the existing flat pipeline layout, because this is a
distinct concern (offline analysis, its own entry point) rather than a daily pipeline step:

```
backtest/
├── config.py           # backtest-only settings (see below)
├── replay.py            # point-in-time snapshot generation
└── run_backtest.py      # single entry point — the one command

data/
└── cached_stock_data_backtest.json   # extended-history cache, separate from the live 1y cache

reports/backtest/
├── snapshots.jsonl      # one row per ticker per slice date
└── summary_<ts>.txt     # grade-vs-forward-return report
```

Existing pipeline files (`config.py`, `data_provider.py`, `fetch_utils.py`, `sepa_scorer.py`, etc.)
stay exactly where they are — no reorganization of the current flat repo-root layout. That was
evaluated separately and rejected: the file count doesn't justify the import/doc-command churn it
would cause today.

## Data flow

1. **Extended fetch.** `run_backtest.py` checks `data/cached_stock_data_backtest.json`. If missing or
   older than `BACKTEST_CACHE_MAX_AGE_DAYS`, it fetches `BACKTEST_YEARS_HISTORY` (3) years of daily
   OHLCV for the watchlist via the existing `data_provider` / `fetch_utils` batch-fetch machinery
   (same batching, adaptive backoff, and USD normalization as step 01 — reused, not reimplemented),
   writing to the backtest-specific cache file so the live 1-year pipeline cache is never touched or
   overwritten.

2. **Slice dates.** Generate monthly slice dates (`BACKTEST_SLICE_INTERVAL_DAYS` ≈ 21 trading days
   apart) covering the most recent 2 years, reserving enough trailing history before the earliest
   slice for a 200-day SMA and enough trailing days after the latest usable slice for the longest
   forward-return window (120 trading days) to be computable. This is why 3 years are fetched for a
   2-year window of slices, not 2.

3. **Point-in-time replay.** For each slice date T and each ticker, truncate the cached OHLCV to
   `hist[:T]` and call `MinerviniScannerV2.scan_stock()` exactly as `04_scan.py` does today. Record
   `(slice_date, ticker, grade, composite_score, trend_score, base_score, rs_score, volume_score,
   breakout_score)` — the same fields already flattened into `reports/scan/history.jsonl`, so the row
   shape is consistent with a pattern that already exists in this codebase.

4. **Forward returns.** For each snapshot, join the close price at T with the close price at
   T+20, T+60, and T+120 trading days (from the same extended cache) to compute forward return %.
   Snapshots too close to the end of the fetched history to have a full 120-day forward window are
   marked with `null` for that window rather than dropped — the row still has value for the shorter
   windows.

5. **Storage.** Append each snapshot row to `reports/backtest/snapshots.jsonl` — mirrors the existing
   `reports/scan/history.jsonl` convention (one flat JSON object per line) rather than introducing a
   new storage engine. At ~1,700 tickers × 24 monthly slices, this is ~40K rows — well within what
   JSONL handles comfortably; no database is warranted.

6. **Analysis / summary report.** After all snapshots are written, group by grade band (A+/A/B/C/
   REJECT) and compute, per band, per forward window (20/60/120 days):
   - average forward return
   - hit rate (% of signals with positive forward return)
   - count of snapshots in the band
   Also report whether composite-score deciles are monotonically related to average forward return
   (a simple sort-and-compare, not a formal statistical test — this is a directional first pass).
   Written to `reports/backtest/summary_<ts>.txt`, human-readable, following the plain-text report
   style already used by `sepa_report.py`.

## Configuration — `backtest/config.py` (new file)

Kept separate from the existing `config.py` because these are offline-analysis knobs, not live-grading
knobs — `config.py` is already ~700 lines and REFERENCE.md documents it as scoped to "what governs a
live grade." Mixing in backtest-only settings would be the same kind of unrelated-concern growth just
removed from `config.py` in PR #14.

```python
from pathlib import Path

BACKTEST_YEARS_HISTORY = 3
BACKTEST_SLICE_INTERVAL_DAYS = 21          # ~1 month, trading days
BACKTEST_SLICE_WINDOW_YEARS = 2            # how far back the slice dates themselves go
BACKTEST_FORWARD_WINDOWS = (20, 60, 120)   # trading days
BACKTEST_CACHE_FILE = Path("data/cached_stock_data_backtest.json")
BACKTEST_CACHE_MAX_AGE_DAYS = 7
BACKTEST_SNAPSHOTS_FILE = Path("reports/backtest/snapshots.jsonl")
BACKTEST_REPORTS_DIR = Path("reports/backtest")
```

## Execution

Single command, no required arguments:

```powershell
python backtest/run_backtest.py
```

Optional flags, matching the existing pipeline's conventions for familiarity:
- `--refresh` — force refetch of the extended cache even if not stale
- `--watchlist <path>` — override the default `watchlist.csv`

## Error handling

- Reuses the existing batch-fetch retry/backoff logic in `fetch_utils.py` / `data_provider.py` —
  no new network error handling is written.
- A ticker with insufficient history at a given slice date (e.g., newer listings) is skipped for
  that slice only, not the whole ticker — consistent with how `04_scan.py` already handles
  insufficient data (REJECT / unavailable rather than a crash).
- Missing/failed tickers are not separately re-reported here; `problems_with_tickers.txt` from the
  live pipeline already serves that purpose and this tool is not the place to duplicate it.

## Testing

Following the pattern already established by `edgar_fundamentals.py` (pure helpers unit-tested, no
network calls in tests): the pieces that are pure logic and warrant unit tests are slice-date
generation, forward-return computation, and the grade-band summary aggregation. The replay step
itself (which calls the real scanner against real cached data) is exercised by running the tool, not
by a unit test — same as `04_scan.py` has no unit test of the full scan, only of its components.

## Open questions for the implementation plan

None — this design is considered complete for the quick-first-pass scope. Deferred/future work
(survivorship-bias-free backtest, statistical significance testing beyond hit rate/average return) is
explicitly out of scope per "Explicit non-goals" above and would get its own design when prioritized.
