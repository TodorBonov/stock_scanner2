"""Tests for the weak-volume breakout downgrade in MinerviniScannerV2._component_score_breakout."""
from sepa_scorer import MinerviniScannerV2

scanner = MinerviniScannerV2(None)  # data_provider unused by this method


def _passed(volume_ratio):
    return {"breakout_rules": {"passed": True, "details": {"volume_ratio": volume_ratio}}}


def test_strong_volume_full_credit():
    assert scanner._component_score_breakout(_passed(1.8), 1.0) == 100.0


def test_moderate_volume_downgraded():
    # >= VOLUME_EXPANSION_MIN (1.2) but < strong (1.4)
    assert scanner._component_score_breakout(_passed(1.3), 1.0) == 80.0


def test_weak_volume_downgraded_most():
    assert scanner._component_score_breakout(_passed(1.05), 1.0) == 65.0


def test_prebreakout_bands_unaffected():
    # not passed -> proximity bands unchanged by the volume logic
    cl = {"breakout_rules": {"passed": False}}
    assert scanner._component_score_breakout(cl, -1.0) == 80.0   # tight, just under pivot
    assert scanner._component_score_breakout(cl, 12.0) == 30.0   # extended
