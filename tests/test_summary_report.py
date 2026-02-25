"""Tests for summary report actionability sort.
Note: These tests load 04_generate_full_report which replaces sys.stdout/stderr (Windows).
Run with: python -m pytest tests/test_ticker_utils.py -v  (ticker tests only, no 02 load).
"""
import importlib.util
import sys
from pathlib import Path

import pytest

# Report tests run now that 02 skips stdout/stderr wrap under pytest


def _get_actionability_sort_key():
    """Load 04_generate_full_report and return actionability_sort_key (lazy to avoid side effects at import)."""
    _root = Path(__file__).resolve().parent.parent
    _spec = importlib.util.spec_from_file_location("step04_report", _root / "04_generate_full_report.py")
    _report = importlib.util.module_from_spec(_spec)
    sys.modules["step04_report"] = _report
    _spec.loader.exec_module(_report)
    return _report.actionability_sort_key


def _make_result(base_depth=10.0, vol_contract=0.9, dist_buy=-2.0, rs_rating=80):
    """Build a minimal scan result dict for actionability_sort_key."""
    return {
        "checklist": {
            "base_quality": {"details": {"base_depth_pct": base_depth, "volume_contraction": vol_contract}},
            "relative_strength": {"details": {"rs_rating": rs_rating}},
        },
        "buy_sell_prices": {"distance_to_buy_pct": dist_buy},
    }


def test_actionability_sort_key_lower_base_depth_first():
    """Tighter base (lower base_depth) should sort before looser base."""
    key = _get_actionability_sort_key()
    r1 = _make_result(base_depth=5.0)
    r2 = _make_result(base_depth=15.0)
    assert key(r1) < key(r2)


def test_actionability_sort_key_lower_volume_contraction_first():
    """Drier volume (lower vol_contract) should sort before wetter."""
    key = _get_actionability_sort_key()
    r1 = _make_result(vol_contract=0.7)
    r2 = _make_result(vol_contract=1.1)
    assert key(r1) < key(r2)


def test_actionability_sort_key_closer_to_pivot_first():
    """Closer to pivot (smaller abs dist_buy) should sort before farther."""
    key = _get_actionability_sort_key()
    r1 = _make_result(dist_buy=-1.0)
    r2 = _make_result(dist_buy=-10.0)
    assert key(r1) < key(r2)


def test_actionability_sort_key_higher_rs_first():
    """Higher RS rating should sort before lower (we use -rs_rating in key)."""
    key = _get_actionability_sort_key()
    r1 = _make_result(rs_rating=100)
    r2 = _make_result(rs_rating=50)
    assert key(r1) < key(r2)


def test_actionability_sort_key_sort_order():
    """Full tuple order: base_depth, vol_contract, abs_dist_buy, -rs_rating."""
    key = _get_actionability_sort_key()
    results = [
        _make_result(base_depth=8.0, vol_contract=0.8, dist_buy=-2.0, rs_rating=90),
        _make_result(base_depth=8.0, vol_contract=0.8, dist_buy=-2.0, rs_rating=70),
        _make_result(base_depth=12.0, vol_contract=0.7, dist_buy=-1.0, rs_rating=80),
    ]
    sorted_results = sorted(results, key=key)
    # First should be tighter base (8) + high RS (90)
    assert sorted_results[0]["checklist"]["relative_strength"]["details"]["rs_rating"] == 90
    assert sorted_results[0]["checklist"]["base_quality"]["details"]["base_depth_pct"] == 8.0
