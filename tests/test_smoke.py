"""Smoke tests: report generation produces expected output.
Note: Loading 02_generate_full_report replaces sys.stdout/stderr on Windows and breaks pytest capture.
Run ticker tests only: python -m pytest tests/test_ticker_utils.py -v
"""
import importlib.util
import sys
from pathlib import Path

import pytest

# Report tests run now that 02 skips stdout/stderr wrap under pytest

_root = Path(__file__).resolve().parent.parent


def _load_report_module():
    """Load 02_generate_full_report (lazy to avoid side effects at collection)."""
    _spec = importlib.util.spec_from_file_location("generate_full_report", _root / "02_generate_full_report.py")
    mod = importlib.util.module_from_spec(_spec)
    sys.modules["generate_full_report"] = mod
    _spec.loader.exec_module(mod)
    return mod


def test_summary_report_contains_headers():
    """Generate summary with minimal fake results; check expected section headers."""
    mod = _load_report_module()
    fake_results = [
        {
            "ticker": "FAKE",
            "overall_grade": "A",
            "meets_criteria": True,
            "position_size": "Half",
            "checklist": {
                "base_quality": {"details": {"base_depth_pct": 10.0, "volume_contraction": 0.8}},
                "relative_strength": {"details": {"rs_rating": 80}},
            },
            "buy_sell_prices": {"pivot_price": 100.0, "buy_price": 100.0, "stop_loss": 95.0, "profit_target_1": 110.0, "distance_to_buy_pct": -1.0},
            "detailed_analysis": {},
        },
    ]
    report_text = mod.generate_summary_report(fake_results, output_file=None)
    assert "MINERVINI SEPA SCAN - SUMMARY REPORT" in report_text
    assert "TOP STOCKS BY GRADE" in report_text
    assert "BEST SETUPS" in report_text
