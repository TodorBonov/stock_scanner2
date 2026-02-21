"""Tests for position suggestion logic (suggest_action, pivot / grade rules)."""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

# Load 05 module to get suggest_action (and config)
import importlib.util
_spec = importlib.util.spec_from_file_location("position_suggestions", _root / "03_position_suggestions.py")
_mod = importlib.util.module_from_spec(_spec)
# Avoid side effects: config is loaded when module runs
_spec.loader.exec_module(_mod)
suggest_action = _mod.suggest_action


def test_stop_loss_triggers_exit():
    action, reason = suggest_action(100.0, 94.0, -6.0, "A", pivot=None)
    assert action == "EXIT"
    assert "Cut loss" in reason or "stop" in reason.lower()


def test_profit_target_1_triggers_reduce():
    action, reason = suggest_action(100.0, 111.0, 11.0, "A", pivot=None)
    assert action == "REDUCE"
    assert "partial" in reason.lower() or "target" in reason.lower()


def test_grade_b_in_profit_triggers_reduce():
    action, reason = suggest_action(100.0, 103.0, 3.0, "B", pivot=None)
    assert action == "REDUCE"
    assert "B" in reason and "trim" in reason.lower()


def test_strong_grade_below_pivot_suggests_hold_not_add():
    # ADD would apply (strong grade, below target 1); but current < pivot -> HOLD
    action, reason = suggest_action(100.0, 98.0, -2.0, "A", pivot=99.0)
    assert action == "HOLD"
    assert "pivot" in reason.lower() or "pullback" in reason.lower()


def test_strong_grade_above_pivot_can_suggest_add():
    action, reason = suggest_action(100.0, 101.0, 1.0, "A", pivot=99.0)
    assert action == "ADD"
    assert "Strong" in reason or "adding" in reason.lower()


def test_weak_grade_in_loss_triggers_exit():
    action, reason = suggest_action(100.0, 98.0, -2.0, "F", pivot=None)
    assert action == "EXIT"
    assert "Weak" in reason or "loss" in reason.lower()
