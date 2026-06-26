"""Tests for the earnings-date guard (compute logic; live fetch is mocked)."""
import importlib.util
from datetime import date, timedelta
from pathlib import Path

SCAN_PATH = Path(__file__).resolve().parent.parent / "04_scan.py"
spec = importlib.util.spec_from_file_location("scan04_eg", SCAN_PATH)
scan04 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan04)


def test_days_until():
    today = date(2026, 1, 1)
    assert scan04.earnings_days_until(date(2026, 1, 8), today) == 7
    assert scan04.earnings_days_until(date(2025, 12, 25), today) == -7
    assert scan04.earnings_days_until(None, today) is None


def test_guard_flags_only_target_grades_within_window(monkeypatch):
    today = date.today()
    near = today + timedelta(days=3)
    far = today + timedelta(days=40)
    mapping = {"AAA": near, "BBB": far, "CCC": near}
    monkeypatch.setattr(scan04, "fetch_next_earnings_date", lambda t, session=None: mapping.get(t))
    monkeypatch.setattr(scan04, "_yf_session", lambda: None)
    monkeypatch.setattr(scan04.time, "sleep", lambda *a, **k: None)

    results = [
        {"ticker": "AAA", "grade": "A+"},   # near earnings -> soon
        {"ticker": "BBB", "grade": "A"},    # far -> not soon
        {"ticker": "CCC", "grade": "C"},    # not an A+/A grade -> not checked
    ]
    soon = scan04.apply_earnings_guard(results, window_days=7, grades=("A+", "A"))

    assert soon == 1
    assert results[0]["earnings"]["soon"] is True
    assert results[0]["earnings"]["days_until"] == 3
    assert results[1]["earnings"]["soon"] is False
    assert "earnings" not in results[2]  # C-grade untouched


def test_guard_handles_missing_earnings_date(monkeypatch):
    monkeypatch.setattr(scan04, "fetch_next_earnings_date", lambda t, session=None: None)
    monkeypatch.setattr(scan04, "_yf_session", lambda: None)
    monkeypatch.setattr(scan04.time, "sleep", lambda *a, **k: None)
    results = [{"ticker": "ZZZ", "grade": "A+"}]
    soon = scan04.apply_earnings_guard(results, window_days=7, grades=("A+",))
    assert soon == 0
    assert results[0]["earnings"] == {"next_date": None, "days_until": None, "soon": False}
