# Backtest — Quick First Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-command backtest tool (`backtest/run_backtest.py`) that replays the live `MinerviniScannerV2` engine against point-in-time-truncated history for the current watchlist, joins forward returns, and reports whether grade bands (A+/A/B/C/REJECT) actually predict forward performance.

**Architecture:** Three new files under `backtest/` (`config.py`, `replay.py`, `analysis.py`, `run_backtest.py`) plus one small, backward-compatible parameter addition to the existing `fetch_utils.py`. The replay step reuses the *exact* live scoring path (`MinerviniScannerV2.scan_universe`) by subclassing the existing `CachedDataProviderV2` from `04_scan.py` (loaded via `importlib`, the same technique `tests/test_scan_cached_provider.py` already uses for numbered modules) and overriding only `get_historical_data` to truncate to an as-of date. No scoring logic is reimplemented anywhere in this plan.

**Tech Stack:** Python, pandas, pytest — same stack as the rest of the project. No new dependencies.

## Global Constraints

- Must be runnable as a single command with no required arguments: `python backtest/run_backtest.py`.
- Must not modify the live daily pipeline's behavior or output paths — the extended cache, snapshot file, and config are all backtest-only and separate from `data/cached_stock_data_new_pipeline.json`, `config.py`, and `reports/scan/`.
- Must call `MinerviniScannerV2.scan_universe()` / `scan_stock()` unmodified — truncation happens only in the data provider layer.
- Deviation from the approved spec (`docs/superpowers/specs/2026-08-03-backtest-quick-first-pass-design.md`): the design listed only `replay.py` and `run_backtest.py` as the folder's Python files. This plan splits out `analysis.py` for the forward-return join and grade-band summary, since `replay.py`'s stated responsibility is "point-in-time snapshot generation" — the returns/summary logic is a distinct concern (what happened *after* each snapshot, not the snapshot itself) and keeping it separate matches the spec's own file-structure principle of one responsibility per file.
- Yahoo's `yfinance` period parameter only accepts specific bucket values (`1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max` — see `data_provider.py:513`). There is no `"3y"` bucket, and passing an invalid string silently falls back to `"1y"` (`data_provider.py:513`), which would silently defeat the whole backtest. The spec's "3 years" requirement is satisfied by fetching the `"5y"` bucket (the smallest valid bucket ≥ 3 years) — `BACKTEST_FETCH_PERIOD = "5y"`, not a `BACKTEST_YEARS_HISTORY` int.

---

### Task 1: `backtest/config.py` and folder scaffolding

**Files:**
- Create: `backtest/__init__.py` (empty)
- Create: `backtest/config.py`

**Interfaces:**
- Produces: `BACKTEST_FETCH_PERIOD`, `BACKTEST_SLICE_WINDOW_YEARS`, `BACKTEST_SLICE_INTERVAL_DAYS`, `BACKTEST_FORWARD_WINDOWS`, `BACKTEST_CACHE_FILE`, `BACKTEST_CACHE_MAX_AGE_DAYS`, `BACKTEST_SNAPSHOTS_FILE`, `BACKTEST_REPORTS_DIR`, `BACKTEST_DEFAULT_BENCHMARK` — consumed by every later task.

This is a constants-only file (same category as the existing `config.py`, which has no dedicated test file in `tests/`) — no test cycle for this task, per the project's own convention.

- [ ] **Step 1: Create the package and config file**

`backtest/__init__.py`:
```python
```
(empty file — makes `backtest` importable as a package)

`backtest/config.py`:
```python
"""
Backtest-only settings: how far back to fetch, slice cadence, forward-return windows,
and output paths. Kept separate from the top-level config.py, which is scoped to what
governs a *live* grade (see REFERENCE.md) — these are offline-analysis knobs, not
live-pipeline knobs.
"""
from pathlib import Path

# yfinance only accepts specific period buckets (data_provider.py); "5y" is the smallest
# bucket that comfortably covers the >=3 years of trailing history the point-in-time
# replay needs (2 years of slice dates + ~1 year of leading buffer for the 200-day SMA).
BACKTEST_FETCH_PERIOD = "5y"

BACKTEST_SLICE_WINDOW_YEARS = 2       # how far back the slice dates themselves go
BACKTEST_SLICE_INTERVAL_DAYS = 21     # ~1 month, calendar days
BACKTEST_FORWARD_WINDOWS = (20, 60, 120)   # trading days

BACKTEST_CACHE_FILE = Path("data/cached_stock_data_backtest.json")
BACKTEST_CACHE_MAX_AGE_DAYS = 7

BACKTEST_REPORTS_DIR = Path("reports/backtest")
BACKTEST_SNAPSHOTS_FILE = BACKTEST_REPORTS_DIR / "snapshots.jsonl"

BACKTEST_DEFAULT_BENCHMARK = "^GDAXI"  # same default as 04_scan.py's --benchmark
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `python -c "import backtest.config as c; print(c.BACKTEST_FETCH_PERIOD, c.BACKTEST_SNAPSHOTS_FILE)"`
Expected: `5y reports/backtest/snapshots.jsonl` (or `reports\backtest\snapshots.jsonl` on Windows), no errors.

- [ ] **Step 3: Commit**

```bash
git add backtest/__init__.py backtest/config.py
git commit -m "backtest: add config module and package scaffolding"
```

---

### Task 2: Add an optional `period` parameter to `fetch_stock_data_batch`

**Files:**
- Modify: `fetch_utils.py:110-153` (`fetch_stock_data_batch`)
- Test: `tests/test_fetch_utils.py` (new)

**Interfaces:**
- Produces: `fetch_stock_data_batch(tickers, provider, stock_info_workers=4, period="1y")` — the existing 3-arg call sites (`01_fetch_prices.py`) get identical behavior; the backtest fetch step (Task 8) will call it with `period=BACKTEST_FETCH_PERIOD`.

This is the one change to shared/live-pipeline code in this plan. It must be provably backward-compatible: default value unchanged, only the two internal `provider.get_historical_data_batch(...)` calls gain a variable instead of a hardcoded literal.

- [ ] **Step 1: Write the failing test**

`tests/test_fetch_utils.py`:
```python
"""Tests for fetch_stock_data_batch's period parameter (backward compat + threading)."""
from unittest.mock import MagicMock

import pandas as pd

from fetch_utils import fetch_stock_data_batch


def _ohlcv_df(n=250):
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1_000_000},
        index=dates,
    )


class TestFetchStockDataBatchPeriod:
    def test_default_period_is_1y(self):
        provider = MagicMock()
        provider.get_historical_data_batch.return_value = {"AAA": _ohlcv_df()}

        fetch_stock_data_batch(["AAA"], provider)

        provider.get_historical_data_batch.assert_called_once_with(["AAA"], period="1y", interval="1d")

    def test_explicit_period_is_threaded_through(self):
        provider = MagicMock()
        provider.get_historical_data_batch.return_value = {"AAA": _ohlcv_df()}

        fetch_stock_data_batch(["AAA"], provider, period="5y")

        provider.get_historical_data_batch.assert_called_once_with(["AAA"], period="5y", interval="1d")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_fetch_utils.py -v`
Expected: FAIL — `fetch_stock_data_batch() got an unexpected keyword argument 'period'` (the test calling `period="5y"` fails; the default-period test may pass by coincidence since `"1y"` is already hardcoded, but both must be driven by the real parameter once Step 3 lands).

- [ ] **Step 3: Add the parameter and thread it through**

In `fetch_utils.py`, change the signature at line 110:
```python
def fetch_stock_data_batch(tickers: List[str], provider: StockDataProvider, stock_info_workers: int = 4, period: str = "1y") -> Dict[str, Dict]:
```
And the two internal calls (lines 125 and 153) from `period="1y"` to `period=period`:
```python
        chunk_hist = provider.get_historical_data_batch(chunk, period=period, interval="1d")
```
```python
        retry_hist = provider.get_historical_data_batch(failed, period=period, interval="1d")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_fetch_utils.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full suite to confirm no regression in `01_fetch_prices.py`'s usage**

Run: `python -m pytest -q`
Expected: all tests pass (78 + 2 new = 80)

- [ ] **Step 6: Commit**

```bash
git add fetch_utils.py tests/test_fetch_utils.py
git commit -m "fetch_utils: add optional period param to fetch_stock_data_batch

Backward compatible (default \"1y\", unchanged for 01_fetch_prices.py).
Needed so the backtest tool can fetch a 5y history bucket through the
same batching/backoff/retry machinery instead of duplicating it."
```

---

### Task 3: `generate_slice_dates` — pure slice-date generation

**Files:**
- Create: `backtest/replay.py`
- Test: `tests/test_backtest_replay.py` (new)

**Interfaces:**
- Consumes: nothing (pure function, stdlib `datetime` only)
- Produces: `generate_slice_dates(latest_date: date, window_years: float, interval_days: int) -> List[date]` — ascending, consumed by Task 7 (`run_backtest.py`).

- [ ] **Step 1: Write the failing test**

`tests/test_backtest_replay.py`:
```python
"""Tests for backtest/replay.py's pure logic (no network)."""
from datetime import date

from backtest.replay import generate_slice_dates


class TestGenerateSliceDates:
    def test_ascending_and_bounded(self):
        dates = generate_slice_dates(date(2026, 1, 1), window_years=1, interval_days=30)
        assert dates == sorted(dates)
        assert dates[0] >= date(2025, 1, 1)  # roughly 1 year back
        assert dates[-1] <= date(2026, 1, 1)

    def test_includes_latest_date_or_stops_before_it(self):
        dates = generate_slice_dates(date(2026, 1, 1), window_years=0.1, interval_days=10)
        assert dates[-1] <= date(2026, 1, 1)
        assert len(dates) >= 1

    def test_two_year_monthly_window_has_about_24_slices(self):
        dates = generate_slice_dates(date(2026, 8, 3), window_years=2, interval_days=21)
        assert 30 <= len(dates) <= 36  # ~730 days / 21 days per slice

    def test_rejects_non_positive_interval(self):
        import pytest
        with pytest.raises(ValueError):
            generate_slice_dates(date(2026, 1, 1), window_years=1, interval_days=0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backtest_replay.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.replay'`

- [ ] **Step 3: Write minimal implementation**

`backtest/replay.py`:
```python
"""
Point-in-time replay for the quick-first-pass backtest. Reuses the live V2 scanner
(sepa_scorer.MinerviniScannerV2) and the live scan's cache-only data provider
(CachedDataProviderV2, defined in 04_scan.py) unmodified — the only new code is a
truncating subclass of that provider, so the backtest measures the same engine that
produces live grades, not a reimplementation of it.
"""
from datetime import date, timedelta
from typing import List


def generate_slice_dates(latest_date: date, window_years: float, interval_days: int) -> List[date]:
    """
    Ascending list of dates from (latest_date - window_years*365 days) to latest_date,
    spaced interval_days calendar days apart. Truncation to an actual trading date happens
    later, per ticker, in PointInTimeDataProvider — this only picks the "as of" calendar
    dates the replay will use.
    """
    if interval_days <= 0:
        raise ValueError("interval_days must be positive")
    start = latest_date - timedelta(days=int(window_years * 365))
    dates: List[date] = []
    d = start
    while d <= latest_date:
        dates.append(d)
        d += timedelta(days=interval_days)
    return dates
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_backtest_replay.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backtest/replay.py tests/test_backtest_replay.py
git commit -m "backtest: add generate_slice_dates"
```

---

### Task 4: `PointInTimeDataProvider` — truncating subclass of the live scan's provider

**Files:**
- Modify: `backtest/replay.py`
- Test: `tests/test_backtest_replay.py`

**Interfaces:**
- Consumes: `CachedDataProviderV2` (loaded from `04_scan.py` via `importlib`, same technique as `tests/test_scan_cached_provider.py:16-27`)
- Produces: `PointInTimeDataProvider(cached_stocks: dict, as_of: date)` with `.get_historical_data(ticker, period="1y", interval="1d") -> pd.DataFrame` truncated to `as_of` — consumed by Task 5's `run_point_in_time_replay`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_backtest_replay.py`:
```python
from datetime import date

import pandas as pd

from backtest.replay import PointInTimeDataProvider


def _cached_entry(n=250, start_date="2025-01-01"):
    """Cache entry shaped like fetch_stock_data_batch's output (see fetch_utils.py)."""
    dates = pd.date_range(start_date, periods=n, freq="D")
    data = [
        {"Open": 100.0 + i, "High": 101.0 + i, "Low": 99.0 + i, "Close": 100.0 + i, "Volume": 1_000_000}
        for i in range(n)
    ]
    return {
        "data_available": True,
        "historical_data": {"index": [str(d) for d in dates], "data": data},
        "stock_info": {"currency": "USD"},
    }


class TestPointInTimeDataProvider:
    def test_truncates_to_as_of_date(self):
        cached = {"AAA": _cached_entry(n=250, start_date="2025-01-01")}
        # Day 100 of the series (2025-01-01 + 100 days) is roughly 2025-04-11
        as_of = date(2025, 4, 11)
        provider = PointInTimeDataProvider(cached, as_of)

        hist = provider.get_historical_data("AAA")

        assert not hist.empty
        assert hist.index.max().date() <= as_of
        assert len(hist) < 250  # confirms it's actually truncated, not the full series

    def test_full_series_returned_when_as_of_is_after_all_data(self):
        cached = {"AAA": _cached_entry(n=250, start_date="2025-01-01")}
        as_of = date(2030, 1, 1)
        provider = PointInTimeDataProvider(cached, as_of)

        hist = provider.get_historical_data("AAA")

        assert len(hist) == 250

    def test_missing_ticker_returns_empty_no_crash(self):
        provider = PointInTimeDataProvider({}, date(2025, 1, 1))
        hist = provider.get_historical_data("ZZZ")
        assert hist.empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backtest_replay.py -v`
Expected: FAIL with `ImportError: cannot import name 'PointInTimeDataProvider'`

- [ ] **Step 3: Write minimal implementation**

Add to `backtest/replay.py` (after the imports, before `generate_slice_dates`):
```python
import importlib.util
from pathlib import Path

import pandas as pd

_SCAN_MODULE_PATH = Path(__file__).resolve().parent.parent / "04_scan.py"


def _load_scan_module():
    """
    04_scan.py's name starts with a digit, so it can't be `import`ed normally.
    Loaded via importlib instead — the same technique tests/test_scan_cached_provider.py
    already uses to reuse CachedDataProviderV2 for testing.
    """
    spec = importlib.util.spec_from_file_location("scan04_for_backtest", _SCAN_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_scan04 = _load_scan_module()
CachedDataProviderV2 = _scan04.CachedDataProviderV2


class PointInTimeDataProvider(CachedDataProviderV2):
    """
    CachedDataProviderV2, but get_historical_data() is truncated to an as-of date. Every
    other method (get_stock_info, calculate_relative_strength) is inherited unmodified and
    therefore automatically operates on the truncated series too, since the parent's
    calculate_relative_strength calls self.get_historical_data(...) internally — no RS math
    is reimplemented here.
    """

    def __init__(self, cached_stocks: dict, as_of):
        super().__init__(cached_stocks, original_provider=None)
        self.as_of = as_of

    def get_historical_data(self, ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        hist = super().get_historical_data(ticker, period, interval)
        if hist.empty:
            return hist
        cutoff = pd.Timestamp(self.as_of)
        if hist.index.tz is not None and cutoff.tzinfo is None:
            cutoff = cutoff.tz_localize(hist.index.tz)
        return hist[hist.index <= cutoff]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_backtest_replay.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add backtest/replay.py tests/test_backtest_replay.py
git commit -m "backtest: add PointInTimeDataProvider (truncating CachedDataProviderV2 subclass)"
```

---

### Task 5: `run_point_in_time_replay` — the actual snapshot generation loop

**Files:**
- Modify: `backtest/replay.py`
- Test: `tests/test_backtest_replay.py`

**Interfaces:**
- Consumes: `PointInTimeDataProvider` (Task 4), `generate_slice_dates` (Task 3), `sepa_scorer.MinerviniScannerV2`
- Produces: `run_point_in_time_replay(cached_stocks: dict, tickers: List[str], benchmark_overrides: dict, slice_dates: List[date], default_benchmark: str) -> List[dict]` — each row has keys `slice_date` (ISO string), `ticker`, `grade`, `composite_score`, `trend_score`, `base_score`, `rs_score`, `volume_score`, `breakout_score`. Consumed by Task 8 (`run_backtest.py`) and Task 6 (`analysis.py`'s forward-return join).

This test exercises the real `MinerviniScannerV2` end to end (no mocking of the scorer) — the whole point of the design is that the replay is provably the same engine as the live scan, so the test proves the wiring works, not that a specific grade comes out (a short synthetic series will legitimately REJECT on eligibility, and that's fine — the test checks shape and plumbing, not a forced grade).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_backtest_replay.py`:
```python
from backtest.replay import run_point_in_time_replay


class TestRunPointInTimeReplay:
    def test_returns_one_row_per_ticker_per_slice_date(self):
        cached = {
            "AAA": _cached_entry(n=250, start_date="2025-01-01"),
            "BBB": _cached_entry(n=250, start_date="2025-01-01"),
        }
        slice_dates = [date(2025, 6, 1), date(2025, 9, 1)]

        rows = run_point_in_time_replay(
            cached_stocks=cached,
            tickers=["AAA", "BBB"],
            benchmark_overrides={},
            slice_dates=slice_dates,
            default_benchmark="^GDAXI",
        )

        assert len(rows) == 4  # 2 tickers x 2 slice dates
        pairs = {(r["ticker"], r["slice_date"]) for r in rows}
        assert ("AAA", "2025-06-01") in pairs
        assert ("BBB", "2025-09-01") in pairs

    def test_row_shape_has_all_score_fields(self):
        cached = {"AAA": _cached_entry(n=250, start_date="2025-01-01")}
        rows = run_point_in_time_replay(
            cached_stocks=cached,
            tickers=["AAA"],
            benchmark_overrides={},
            slice_dates=[date(2025, 9, 1)],
            default_benchmark="^GDAXI",
        )
        row = rows[0]
        for key in ("slice_date", "ticker", "grade", "composite_score",
                    "trend_score", "base_score", "rs_score", "volume_score", "breakout_score"):
            assert key in row
        assert row["grade"] in ("A+", "A", "B", "C", "REJECT")

    def test_insufficient_history_at_early_slice_is_reject_not_a_crash(self):
        # Only 250 days of data starting 2025-01-01; a slice date before there's 200
        # trading days of history must not crash the replay.
        cached = {"AAA": _cached_entry(n=250, start_date="2025-01-01")}
        rows = run_point_in_time_replay(
            cached_stocks=cached,
            tickers=["AAA"],
            benchmark_overrides={},
            slice_dates=[date(2025, 1, 15)],
            default_benchmark="^GDAXI",
        )
        assert rows[0]["grade"] == "REJECT"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backtest_replay.py -v`
Expected: FAIL with `ImportError: cannot import name 'run_point_in_time_replay'`

- [ ] **Step 3: Write minimal implementation**

Add to `backtest/replay.py` (needs `MinerviniScannerV2` imported at the top: `from sepa_scorer import MinerviniScannerV2`):
```python
from sepa_scorer import MinerviniScannerV2


def run_point_in_time_replay(
    cached_stocks: dict,
    tickers: List[str],
    benchmark_overrides: dict,
    slice_dates: List[date],
    default_benchmark: str,
) -> List[dict]:
    """
    For each slice date, build a truncated-to-that-date provider and run the real
    MinerviniScannerV2.scan_universe() over it — exactly what 04_scan.py does for a live
    scan, just fed history that stops at `slice_date` instead of "today".
    """
    rows: List[dict] = []
    for slice_date in slice_dates:
        provider = PointInTimeDataProvider(cached_stocks, slice_date)
        scanner = MinerviniScannerV2(provider, benchmark=default_benchmark)
        results = scanner.scan_universe(tickers, benchmark_overrides or None)
        for r in results:
            rows.append({
                "slice_date": slice_date.isoformat(),
                "ticker": r.get("ticker"),
                "grade": r.get("grade"),
                "composite_score": r.get("composite_score"),
                "trend_score": r.get("trend_score"),
                "base_score": r.get("base_score"),
                "rs_score": r.get("rs_score"),
                "volume_score": r.get("volume_score"),
                "breakout_score": r.get("breakout_score"),
            })
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_backtest_replay.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add backtest/replay.py tests/test_backtest_replay.py
git commit -m "backtest: add run_point_in_time_replay"
```

---

### Task 6: `backtest/analysis.py` — forward-return join

**Files:**
- Create: `backtest/analysis.py`
- Test: `tests/test_backtest_analysis.py` (new)

**Interfaces:**
- Consumes: snapshot rows shaped like Task 5's output (`ticker`, `slice_date` keys), a `full_history: Dict[str, pd.DataFrame]` (untruncated per-ticker OHLCV — the same DataFrames the replay's `cached_stocks` are built from, before any truncation)
- Produces: `compute_forward_returns(snapshots: List[dict], full_history: Dict[str, pd.DataFrame], forward_windows: Tuple[int, ...]) -> List[dict]` — each input row plus `forward_return_{N}d` keys for each `N` in `forward_windows` (float percent, or `None` if there isn't `N` trading days of future data). Consumed by Task 7's `summarize_by_grade`.

- [ ] **Step 1: Write the failing test**

`tests/test_backtest_analysis.py`:
```python
"""Tests for backtest/analysis.py (no network)."""
import pandas as pd

from backtest.analysis import compute_forward_returns


def _flat_growth_df(n=300, daily_growth=0.001, start_date="2025-01-01"):
    dates = pd.date_range(start_date, periods=n, freq="D")
    price = 100.0
    closes = []
    for _ in range(n):
        closes.append(price)
        price *= (1 + daily_growth)
    return pd.DataFrame({"Close": closes}, index=dates)


class TestComputeForwardReturns:
    def test_positive_growth_gives_positive_forward_return(self):
        history = {"AAA": _flat_growth_df(n=300, daily_growth=0.002)}
        snapshots = [{"ticker": "AAA", "slice_date": "2025-03-01", "grade": "A"}]

        out = compute_forward_returns(snapshots, history, forward_windows=(20, 60))

        assert out[0]["forward_return_20d"] > 0
        assert out[0]["forward_return_60d"] > 0
        assert out[0]["forward_return_60d"] > out[0]["forward_return_20d"]

    def test_window_beyond_available_data_is_none(self):
        # Only 300 days total; a slice near the end has no room for a 120-trading-day forward window.
        history = {"AAA": _flat_growth_df(n=300, daily_growth=0.001)}
        snapshots = [{"ticker": "AAA", "slice_date": "2025-10-01", "grade": "B"}]

        out = compute_forward_returns(snapshots, history, forward_windows=(120,))

        assert out[0]["forward_return_120d"] is None

    def test_missing_ticker_history_gives_none_for_all_windows(self):
        snapshots = [{"ticker": "ZZZ", "slice_date": "2025-03-01", "grade": "C"}]
        out = compute_forward_returns(snapshots, {}, forward_windows=(20, 60, 120))
        assert out[0]["forward_return_20d"] is None
        assert out[0]["forward_return_60d"] is None
        assert out[0]["forward_return_120d"] is None

    def test_original_snapshot_fields_are_preserved(self):
        history = {"AAA": _flat_growth_df(n=300)}
        snapshots = [{"ticker": "AAA", "slice_date": "2025-03-01", "grade": "A", "composite_score": 88.0}]
        out = compute_forward_returns(snapshots, history, forward_windows=(20,))
        assert out[0]["grade"] == "A"
        assert out[0]["composite_score"] == 88.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backtest_analysis.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.analysis'`

- [ ] **Step 3: Write minimal implementation**

`backtest/analysis.py`:
```python
"""
Turns replay snapshots (Task 5's run_point_in_time_replay output) into a forward-return
analysis: for each (ticker, slice_date) snapshot, what did the price actually do next,
and does that differ by grade band?
"""
from datetime import date as date_cls
from typing import Dict, List, Tuple

import pandas as pd


def compute_forward_returns(
    snapshots: List[dict],
    full_history: Dict[str, pd.DataFrame],
    forward_windows: Tuple[int, ...],
) -> List[dict]:
    """
    For each snapshot, look up the close price at slice_date and at slice_date + N trading
    days (for each N in forward_windows) in the *untruncated* full_history, and compute
    percent return. None when there isn't N trading days of future data yet, or the
    ticker's history isn't available at all.
    """
    out: List[dict] = []
    for snap in snapshots:
        row = dict(snap)
        ticker = snap.get("ticker")
        hist = full_history.get(ticker)
        as_of = pd.Timestamp(snap["slice_date"])

        pos = None
        if hist is not None and not hist.empty:
            cutoff = as_of
            if hist.index.tz is not None and cutoff.tzinfo is None:
                cutoff = cutoff.tz_localize(hist.index.tz)
            eligible_idx = hist.index[hist.index <= cutoff]
            if len(eligible_idx) > 0:
                pos = hist.index.get_loc(eligible_idx[-1])

        for window in forward_windows:
            key = f"forward_return_{window}d"
            if pos is None:
                row[key] = None
                continue
            target_pos = pos + window
            if target_pos >= len(hist):
                row[key] = None
                continue
            start_price = float(hist["Close"].iloc[pos])
            end_price = float(hist["Close"].iloc[target_pos])
            row[key] = ((end_price / start_price) - 1.0) * 100.0 if start_price else None
        out.append(row)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_backtest_analysis.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backtest/analysis.py tests/test_backtest_analysis.py
git commit -m "backtest: add compute_forward_returns"
```

---

### Task 7: `backtest/analysis.py` — grade-band summary

**Files:**
- Modify: `backtest/analysis.py`
- Test: `tests/test_backtest_analysis.py`

**Interfaces:**
- Consumes: output of `compute_forward_returns` (Task 6)
- Produces: `summarize_by_grade(rows: List[dict], forward_windows: Tuple[int, ...]) -> Dict[str, Dict[int, dict]]` — `{grade: {window: {"avg_return": float, "hit_rate": float, "count": int}}}`, and `format_summary_report(summary: dict, forward_windows: Tuple[int, ...]) -> str` — human-readable text. Both consumed by Task 8 (`run_backtest.py`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_backtest_analysis.py`:
```python
from backtest.analysis import summarize_by_grade, format_summary_report


class TestSummarizeByGrade:
    def test_avg_return_and_hit_rate_per_grade_and_window(self):
        rows = [
            {"grade": "A+", "forward_return_20d": 10.0},
            {"grade": "A+", "forward_return_20d": -2.0},
            {"grade": "REJECT", "forward_return_20d": 1.0},
        ]
        summary = summarize_by_grade(rows, forward_windows=(20,))

        a_plus = summary["A+"][20]
        assert a_plus["count"] == 2
        assert a_plus["avg_return"] == 4.0        # (10 + -2) / 2
        assert a_plus["hit_rate"] == 0.5           # 1 of 2 positive

        rej = summary["REJECT"][20]
        assert rej["count"] == 1
        assert rej["hit_rate"] == 1.0

    def test_none_returns_excluded_from_average(self):
        rows = [
            {"grade": "B", "forward_return_60d": 5.0},
            {"grade": "B", "forward_return_60d": None},
        ]
        summary = summarize_by_grade(rows, forward_windows=(60,))
        b = summary["B"][60]
        assert b["count"] == 1  # the None row doesn't count
        assert b["avg_return"] == 5.0

    def test_grade_with_zero_usable_rows_reports_zero_count_not_a_crash(self):
        rows = [{"grade": "C", "forward_return_20d": None}]
        summary = summarize_by_grade(rows, forward_windows=(20,))
        assert summary["C"][20]["count"] == 0
        assert summary["C"][20]["avg_return"] is None
        assert summary["C"][20]["hit_rate"] is None


class TestFormatSummaryReport:
    def test_report_is_nonempty_string_mentioning_each_grade(self):
        rows = [
            {"grade": "A+", "forward_return_20d": 10.0},
            {"grade": "REJECT", "forward_return_20d": -1.0},
        ]
        summary = summarize_by_grade(rows, forward_windows=(20,))
        report = format_summary_report(summary, forward_windows=(20,))
        assert "A+" in report
        assert "REJECT" in report
        assert isinstance(report, str) and len(report) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backtest_analysis.py -v`
Expected: FAIL with `ImportError: cannot import name 'summarize_by_grade'`

- [ ] **Step 3: Write minimal implementation**

Add to `backtest/analysis.py`:
```python
GRADE_ORDER = ("A+", "A", "B", "C", "REJECT")


def summarize_by_grade(rows: List[dict], forward_windows: Tuple[int, ...]) -> Dict[str, Dict[int, dict]]:
    """
    Group snapshot+forward-return rows by grade, and per forward window compute average
    return, hit rate (% positive), and the usable row count. Rows with a None forward
    return for a given window are excluded from that window's stats only.
    """
    summary: Dict[str, Dict[int, dict]] = {}
    for grade in {r.get("grade") for r in rows}:
        summary[grade] = {}
        grade_rows = [r for r in rows if r.get("grade") == grade]
        for window in forward_windows:
            key = f"forward_return_{window}d"
            values = [r[key] for r in grade_rows if r.get(key) is not None]
            if not values:
                summary[grade][window] = {"avg_return": None, "hit_rate": None, "count": 0}
                continue
            avg_return = sum(values) / len(values)
            hit_rate = sum(1 for v in values if v > 0) / len(values)
            summary[grade][window] = {"avg_return": avg_return, "hit_rate": hit_rate, "count": len(values)}
    return summary


def format_summary_report(summary: Dict[str, Dict[int, dict]], forward_windows: Tuple[int, ...]) -> str:
    """Plain-text grade-vs-forward-return report, in the style of sepa_report.py's output."""
    lines = ["=" * 80, "BACKTEST SUMMARY — GRADE vs FORWARD RETURN (quick first pass, survivorship-biased)", "=" * 80, ""]
    ordered_grades = [g for g in GRADE_ORDER if g in summary] + [g for g in summary if g not in GRADE_ORDER]
    header = "Grade".ljust(8) + "".join(f"{'D'+str(w)+'d avg%':>14}{'hit%':>8}{'n':>7}" for w in forward_windows)
    lines.append(header)
    lines.append("-" * len(header))
    for grade in ordered_grades:
        parts = [grade.ljust(8)]
        for window in forward_windows:
            stats = summary[grade].get(window, {"avg_return": None, "hit_rate": None, "count": 0})
            avg = f"{stats['avg_return']:.2f}" if stats["avg_return"] is not None else "—"
            hit = f"{stats['hit_rate']*100:.0f}" if stats["hit_rate"] is not None else "—"
            parts.append(f"{avg:>14}{hit:>8}{stats['count']:>7}")
        lines.append("".join(parts))
    lines.append("")
    lines.append("Survivorship-biased quick first pass: current watchlist only, no delisted names.")
    lines.append("See docs/superpowers/specs/2026-08-03-backtest-quick-first-pass-design.md for scope.")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_backtest_analysis.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add backtest/analysis.py tests/test_backtest_analysis.py
git commit -m "backtest: add summarize_by_grade and format_summary_report"
```

---

### Task 8: JSONL snapshot storage + cache-staleness check

**Files:**
- Create: `backtest/run_backtest.py`
- Test: `tests/test_backtest_run.py` (new)

**Interfaces:**
- Consumes: `BACKTEST_CACHE_FILE`, `BACKTEST_CACHE_MAX_AGE_DAYS`, `BACKTEST_SNAPSHOTS_FILE` (Task 1)
- Produces: `write_snapshots_jsonl(rows: List[dict], path: Path) -> None`, `read_snapshots_jsonl(path: Path) -> List[dict]`, `is_cache_stale(path: Path, max_age_days: int) -> bool` — consumed by Task 10 (the CLI entry point).

- [ ] **Step 1: Write the failing test**

`tests/test_backtest_run.py`:
```python
"""Tests for backtest/run_backtest.py's I/O helpers (no network)."""
import time

from backtest.run_backtest import write_snapshots_jsonl, read_snapshots_jsonl, is_cache_stale


class TestSnapshotJsonlRoundTrip:
    def test_write_then_read_round_trips(self, tmp_path):
        path = tmp_path / "snapshots.jsonl"
        rows = [
            {"ticker": "AAA", "slice_date": "2025-06-01", "grade": "A+"},
            {"ticker": "BBB", "slice_date": "2025-06-01", "grade": "REJECT"},
        ]
        write_snapshots_jsonl(rows, path)
        result = read_snapshots_jsonl(path)
        assert result == rows

    def test_write_overwrites_not_appends(self, tmp_path):
        path = tmp_path / "snapshots.jsonl"
        write_snapshots_jsonl([{"ticker": "AAA"}], path)
        write_snapshots_jsonl([{"ticker": "BBB"}], path)
        result = read_snapshots_jsonl(path)
        assert result == [{"ticker": "BBB"}]

    def test_creates_parent_directory(self, tmp_path):
        path = tmp_path / "nested" / "snapshots.jsonl"
        write_snapshots_jsonl([{"ticker": "AAA"}], path)
        assert path.exists()


class TestIsCacheStale:
    def test_missing_file_is_stale(self, tmp_path):
        assert is_cache_stale(tmp_path / "nope.json", max_age_days=7) is True

    def test_fresh_file_is_not_stale(self, tmp_path):
        path = tmp_path / "cache.json"
        path.write_text("{}")
        assert is_cache_stale(path, max_age_days=7) is False

    def test_old_file_is_stale(self, tmp_path):
        path = tmp_path / "cache.json"
        path.write_text("{}")
        old_time = time.time() - (8 * 86400)
        import os
        os.utime(path, (old_time, old_time))
        assert is_cache_stale(path, max_age_days=7) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backtest_run.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.run_backtest'`

- [ ] **Step 3: Write minimal implementation**

`backtest/run_backtest.py`:
```python
"""
Pipeline step: quick-first-pass backtest. Single entry point — run with no arguments for
the default 2-year monthly point-in-time replay against the current watchlist.

    python backtest/run_backtest.py

See docs/superpowers/specs/2026-08-03-backtest-quick-first-pass-design.md for scope
(survivorship-biased, current watchlist only — not a full historical-universe backtest).
"""
import json
import time
from pathlib import Path
from typing import List


def write_snapshots_jsonl(rows: List[dict], path: Path) -> None:
    """Overwrite path with one JSON object per line. Each run is a fresh, complete
    replay (unlike reports/scan/history.jsonl, which appends across runs) — there is no
    incremental accumulation to preserve."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def read_snapshots_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def is_cache_stale(path: Path, max_age_days: int) -> bool:
    if not path.exists():
        return True
    age_seconds = time.time() - path.stat().st_mtime
    return age_seconds > (max_age_days * 86400)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_backtest_run.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backtest/run_backtest.py tests/test_backtest_run.py
git commit -m "backtest: add snapshot JSONL I/O and cache-staleness check"
```

---

### Task 9: Extended fetch + full-history DataFrame loading

**Files:**
- Modify: `backtest/run_backtest.py`
- Test: `tests/test_backtest_run.py`

**Interfaces:**
- Consumes: `fetch_stock_data_batch(..., period=...)` (Task 2), `watchlist_loader.load_watchlist/get_yahoo_symbols_for_fetch/get_ticker_rows`, `backtest.replay._scan04.convert_cached_data_to_dataframe` (reused, not duplicated — same reasoning as Task 4)
- Produces: `load_extended_cache(path: Path) -> dict`, `save_extended_cache(data: dict, path: Path) -> None`, `build_full_history(cached_stocks: dict, tickers: List[str]) -> Dict[str, pd.DataFrame]` — consumed by Task 10.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_backtest_run.py`:
```python
import pandas as pd

from backtest.run_backtest import load_extended_cache, save_extended_cache, build_full_history


def _cached_entry(n=250):
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    data = [{"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1_000_000} for _ in range(n)]
    return {"data_available": True, "historical_data": {"index": [str(d) for d in dates], "data": data}}


class TestExtendedCacheIO:
    def test_save_then_load_round_trips(self, tmp_path):
        path = tmp_path / "cache.json"
        data = {"stocks": {"AAA": _cached_entry()}}
        save_extended_cache(data, path)
        result = load_extended_cache(path)
        assert result["stocks"]["AAA"]["data_available"] is True

    def test_load_missing_file_returns_empty_shape(self, tmp_path):
        result = load_extended_cache(tmp_path / "nope.json")
        assert result == {"stocks": {}}


class TestBuildFullHistory:
    def test_returns_dataframe_per_ticker_with_data(self):
        cached_stocks = {"AAA": _cached_entry(), "BBB": {"data_available": False}}
        history = build_full_history(cached_stocks, tickers=["AAA", "BBB"])
        assert "AAA" in history
        assert not history["AAA"].empty
        assert "BBB" not in history  # no data_available -> excluded, not a crash
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backtest_run.py -v`
Expected: FAIL with `ImportError: cannot import name 'load_extended_cache'`

- [ ] **Step 3: Write minimal implementation**

Add to `backtest/run_backtest.py`:
```python
from typing import Dict

import pandas as pd

from backtest.replay import _scan04  # reuse convert_cached_data_to_dataframe, not duplicate it

convert_cached_data_to_dataframe = _scan04.convert_cached_data_to_dataframe


def load_extended_cache(path: Path) -> dict:
    if not path.exists():
        return {"stocks": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) and "stocks" in data else {"stocks": {}}
    except Exception:
        return {"stocks": {}}


def save_extended_cache(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def build_full_history(cached_stocks: dict, tickers: List[str]) -> Dict[str, pd.DataFrame]:
    """Convert cache entries to DataFrames for tickers with usable data. Tickers with no
    data_available (or an unconvertible/too-short series) are simply absent from the
    result — callers already treat a missing ticker as REJECT/None, not an error."""
    history: Dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        entry = cached_stocks.get(ticker)
        if not entry or not entry.get("data_available", False):
            continue
        df = convert_cached_data_to_dataframe(entry)
        if df is not None and not df.empty:
            history[ticker] = df
    return history
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_backtest_run.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add backtest/run_backtest.py tests/test_backtest_run.py
git commit -m "backtest: add extended cache I/O and full-history DataFrame loading"
```

---

### Task 10: CLI entry point — wire it all together

**Files:**
- Modify: `backtest/run_backtest.py`

**Interfaces:**
- Consumes: everything from Tasks 1–9
- Produces: `main()` — no return value consumed elsewhere; this is the terminal task, same as `04_scan.py`'s `main()` has no dedicated unit test (per project convention — verified by running it, not asserting on it).

No new unit test for `main()` itself, matching how `04_scan.py`'s orchestration is verified (this project has no `test_04_scan_main.py`). Step 5 below is the real verification: an actual end-to-end run against real data.

- [ ] **Step 1: Write `main()`**

Add to `backtest/run_backtest.py`:
```python
import argparse
import os
from datetime import datetime

from dotenv import load_dotenv

from config import DEFAULT_ENV_PATH
from data_provider import StockDataProvider
from fetch_utils import fetch_stock_data_batch
from watchlist_loader import load_watchlist, get_yahoo_symbols_for_fetch, get_ticker_rows
from backtest.config import (
    BACKTEST_FETCH_PERIOD,
    BACKTEST_SLICE_WINDOW_YEARS,
    BACKTEST_SLICE_INTERVAL_DAYS,
    BACKTEST_FORWARD_WINDOWS,
    BACKTEST_CACHE_FILE,
    BACKTEST_CACHE_MAX_AGE_DAYS,
    BACKTEST_SNAPSHOTS_FILE,
    BACKTEST_REPORTS_DIR,
    BACKTEST_DEFAULT_BENCHMARK,
)
from backtest.replay import generate_slice_dates, run_point_in_time_replay
from backtest.analysis import compute_forward_returns, summarize_by_grade, format_summary_report

if Path(DEFAULT_ENV_PATH).exists():
    load_dotenv(Path(DEFAULT_ENV_PATH))


def main():
    parser = argparse.ArgumentParser(description="Quick-first-pass backtest: point-in-time replay + forward returns")
    parser.add_argument("--watchlist", default="watchlist.csv", help="Watchlist CSV (default: watchlist.csv)")
    parser.add_argument("--refresh", action="store_true", help="Force refetch of the extended (5y) cache")
    args = parser.parse_args()

    rows_wl = load_watchlist(args.watchlist)
    all_symbols = get_yahoo_symbols_for_fetch(rows_wl)   # tickers + benchmark indices
    ticker_rows = get_ticker_rows(rows_wl)
    tickers = [r["yahoo_symbol"] for r in ticker_rows]
    benchmark_overrides = {r["yahoo_symbol"]: r["benchmark_index"] for r in ticker_rows if r.get("benchmark_index")}

    print(f"\n{'='*80}\nBACKTEST: EXTENDED FETCH ({BACKTEST_FETCH_PERIOD})\n{'='*80}")
    cache_data = load_extended_cache(BACKTEST_CACHE_FILE)
    cached_stocks = cache_data.get("stocks", {})
    stale = args.refresh or is_cache_stale(BACKTEST_CACHE_FILE, BACKTEST_CACHE_MAX_AGE_DAYS)
    to_fetch = [t for t in all_symbols if stale or t not in cached_stocks or not cached_stocks[t].get("data_available", False)]
    if to_fetch:
        print(f"Fetching {len(to_fetch)}/{len(all_symbols)} symbols...")
        provider = StockDataProvider(alpha_vantage_api_key=os.getenv("ALPHA_VANTAGE_API_KEY"), prefer_yfinance=True)
        batch_results = fetch_stock_data_batch(to_fetch, provider, period=BACKTEST_FETCH_PERIOD)
        cached_stocks.update(batch_results)
        save_extended_cache({"stocks": cached_stocks}, BACKTEST_CACHE_FILE)
    else:
        print("Extended cache is fresh — nothing to fetch.")

    full_history = build_full_history(cached_stocks, all_symbols)
    print(f"Usable history: {len(full_history)}/{len(all_symbols)} symbols")

    latest_dates = [df.index.max() for df in full_history.values() if not df.empty]
    if not latest_dates:
        print("No usable history — aborting.")
        return
    latest_date = max(latest_dates).date()
    slice_dates = generate_slice_dates(latest_date, BACKTEST_SLICE_WINDOW_YEARS, BACKTEST_SLICE_INTERVAL_DAYS)
    print(f"\n{'='*80}\nBACKTEST: POINT-IN-TIME REPLAY ({len(slice_dates)} slices x {len(tickers)} tickers)\n{'='*80}")

    scannable_tickers = [t for t in tickers if t in full_history]
    snapshots = run_point_in_time_replay(cached_stocks, scannable_tickers, benchmark_overrides, slice_dates, BACKTEST_DEFAULT_BENCHMARK)
    print(f"Snapshots: {len(snapshots)}")

    snapshots_with_returns = compute_forward_returns(snapshots, full_history, BACKTEST_FORWARD_WINDOWS)
    write_snapshots_jsonl(snapshots_with_returns, BACKTEST_SNAPSHOTS_FILE)
    print(f"Wrote {BACKTEST_SNAPSHOTS_FILE}")

    summary = summarize_by_grade(snapshots_with_returns, BACKTEST_FORWARD_WINDOWS)
    report = format_summary_report(summary, BACKTEST_FORWARD_WINDOWS)
    BACKTEST_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = BACKTEST_REPORTS_DIR / f"summary_{ts}.txt"
    summary_path.write_text(report, encoding="utf-8")
    print(f"\n{report}\n\nWrote {summary_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the full unit test suite (confirms nothing upstream broke)**

Run: `python -m pytest -q`
Expected: all tests pass (80 from Task 2 + 10 from Task 3–5 + 7 from Tasks 6–7 + 9 from Tasks 8–9 = 106 total, exact count may vary slightly by how tests were tallied — the key bar is zero failures)

- [ ] **Step 3: Commit**

```bash
git add backtest/run_backtest.py
git commit -m "backtest: wire up run_backtest.py CLI entry point"
```

- [ ] **Step 4: Run it end to end against real data**

Run: `python backtest/run_backtest.py`

Expected: fetches the 5y cache (first run only — several minutes, same batching/backoff behavior as step 01), then completes the replay (~16 minutes: 24 slices x ~40s per full-universe scan, per the performance note in `docs/superpowers/specs/2026-08-03-backtest-quick-first-pass-design.md`), and prints the grade-vs-forward-return summary table to the console. `reports/backtest/snapshots.jsonl` and `reports/backtest/summary_<ts>.txt` should both exist afterward.

- [ ] **Step 5: Report the actual summary table back to the user**

This is the deliverable the user asked to see before deciding whether the design was worth pursuing further — the printed summary table (or the `summary_<ts>.txt` file contents) is the answer to "does a higher grade predict a better forward return?" Do not just report "it ran successfully" — report the actual numbers.

---

## Self-Review Notes

- **Spec coverage:** every data-flow step in the design spec (extended fetch, slice dates, point-in-time replay via the unmodified scorer, forward-return join, JSONL storage, grade-band summary, single-command execution, dedicated config) has a task. The one deviation (splitting `analysis.py` out of `replay.py`) is called out explicitly in Global Constraints with its rationale.
- **No reimplemented scoring:** confirmed by construction — `PointInTimeDataProvider` only overrides `get_historical_data`; `calculate_relative_strength` and everything in `sepa_checklist.py`/`sepa_scorer.py` is inherited/called unmodified.
- **Yahoo period-bucket bug avoided:** caught during planning (not "3y", which doesn't exist as a yfinance bucket and would have silently degraded to 1y) — `BACKTEST_FETCH_PERIOD = "5y"` used throughout instead.
- **Timezone handling:** the live cache-to-DataFrame conversion (`convert_cached_data_to_dataframe`) produces a UTC-aware index; both `PointInTimeDataProvider.get_historical_data` (Task 4) and `compute_forward_returns` (Task 6) defensively localize the cutoff timestamp to match, and Task 4's tests exercise truncation against a real converted (tz-aware) series via `_cached_entry`.
- **No placeholders:** every step has real, complete code — none deferred to "add error handling" or "similar to Task N."
