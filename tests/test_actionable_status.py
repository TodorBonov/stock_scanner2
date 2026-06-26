"""Tests for the entry-actionability status (actionable_status in 04_scan)."""
import importlib.util
from pathlib import Path

SCAN_PATH = Path(__file__).resolve().parent.parent / "04_scan.py"
spec = importlib.util.spec_from_file_location("scan04_as", SCAN_PATH)
scan04 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan04)
S = scan04.actionable_status


def test_ready_just_under_pivot():
    assert S(-1.0, False) == "Ready"
    assert S(0.0, False) == "Ready"


def test_near_and_watch():
    assert S(-4.0, False) == "Near"
    assert S(-10.0, False) == "Watch"


def test_in_breakout_and_extended():
    assert S(1.5, True) == "In-breakout"
    assert S(12.0, True) == "Extended"      # > EXTENDED_DISTANCE_PCT (8)


def test_unknown_when_no_distance():
    assert S(None, False) == "unknown"
    assert S(None, True) == "unknown"
