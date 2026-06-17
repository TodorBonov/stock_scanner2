"""Tests for Marker 2 sector-strength classification (compute_sector_strength in 04_scan)."""
import importlib.util
from pathlib import Path

SCAN_PATH = Path(__file__).resolve().parent.parent / "04_scan.py"
spec = importlib.util.spec_from_file_location("scan04_ss", SCAN_PATH)
scan04 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan04)
compute_sector_strength = scan04.compute_sector_strength


def _r(ticker, sector, rs3):
    return {"ticker": ticker, "sector": sector, "relative_strength": {"rs_3m": rs3}}


def test_terciles_leading_lagging_inline():
    results = [
        _r("A", "Tech", 30.0), _r("B", "Tech", 28.0),       # top -> leading
        _r("C", "Energy", -10.0), _r("D", "Energy", -12.0),  # bottom -> lagging
        _r("E", "Health", 5.0), _r("F", "Health", 6.0),      # middle -> inline
    ]
    medians, market_3m = compute_sector_strength(results)
    by = {r["ticker"]: r["sector_strength"]["status"] for r in results}
    assert by["A"] == "leading" and by["B"] == "leading"
    assert by["C"] == "lagging" and by["D"] == "lagging"
    assert by["E"] == "inline" and by["F"] == "inline"
    assert set(medians) == {"Tech", "Energy", "Health"}


def test_unknown_when_no_sector_or_no_return():
    results = [
        _r("X", "", 10.0),                                    # no sector
        {"ticker": "Y", "sector": "Tech", "relative_strength": {"rs_3m": None}},  # no return
    ]
    compute_sector_strength(results)
    assert results[0]["sector_strength"]["status"] == "unknown"
    assert results[1]["sector_strength"]["status"] == "unknown"


def test_flag_only_does_not_touch_grade():
    results = [_r("A", "Tech", 10.0), _r("B", "Energy", -5.0)]
    for r in results:
        r["grade"] = "A+"
    compute_sector_strength(results)
    assert all(r["grade"] == "A+" for r in results)  # grades untouched
