"""Tests for the pure helpers in edgar_fundamentals (no network)."""
from edgar_fundamentals import quarterly_values, yoy_and_accel, classify, _norm_name


def test_quarterly_values_filters_ytd_and_sorts():
    units = {"USD/shares": [
        {"start": "2025-01-01", "end": "2025-06-30", "val": 5.0},   # ~180d YTD -> drop
        {"start": "2025-04-01", "end": "2025-06-30", "val": 2.0},   # ~90d Q -> keep
        {"start": "2025-01-01", "end": "2025-03-31", "val": 1.0},   # ~90d Q -> keep
        {"start": "2025-07-01", "end": "2025-09-30", "val": 3.0},   # ~92d Q -> keep
    ]}
    assert quarterly_values(units, "USD/shares") == [1.0, 2.0, 3.0]  # ascending by end


def test_yoy_and_accel():
    # len 5 -> YoY computable, acceleration not (needs 6)
    yoy, accel = yoy_and_accel([1, 1, 1, 1, 2])
    assert round(yoy) == 100 and accel is None
    # len 6 -> accelerating: latest YoY 100% > prev YoY 50%
    yoy, accel = yoy_and_accel([1, 1, 1, 1, 1.5, 2])
    assert round(yoy) == 100 and accel is True
    # decelerating
    _, accel = yoy_and_accel([1, 1, 2, 1, 3, 1.2])  # latest 1.2/1-... prev 3/1
    assert accel is False
    # negative base -> None
    yoy, _ = yoy_and_accel([-1, 1, 1, 1, 2])
    assert yoy is None


def test_classify():
    assert classify(30.0, True) == "strong"
    assert classify(30.0, False) == "ok"   # high growth but not accelerating
    assert classify(10.0, True) == "ok"
    assert classify(-5.0, None) == "weak"
    assert classify(None, None) == "n/a"


def test_name_overlap_guards_collisions():
    # Airbus vs AAR Corp -> no overlap (the collision we must reject)
    assert not (_norm_name("Airbus") & _norm_name("AAR CORP"))
    # SAP vs SAP SE -> overlap (legit match; 'SE' is dropped)
    assert _norm_name("SAP") & _norm_name("SAP SE")
