"""Tests for cache_utils module."""
import json
import pytest
from pathlib import Path

from cache_utils import load_cached_data, save_cached_data


def test_load_cached_data_missing_returns_none(monkeypatch, tmp_path):
    """When cache file does not exist, load_cached_data returns None."""
    monkeypatch.setattr("cache_utils.CACHE_FILE", tmp_path / "nonexistent.json")
    assert load_cached_data() is None


def test_load_cached_data_invalid_json_returns_none(monkeypatch, tmp_path):
    """When cache file is not valid JSON, load_cached_data returns None."""
    cache_file = tmp_path / "bad.json"
    cache_file.write_text("not json {")
    monkeypatch.setattr("cache_utils.CACHE_FILE", cache_file)
    assert load_cached_data() is None


def test_load_cached_data_valid_returns_dict(monkeypatch, tmp_path):
    """When cache file is valid JSON dict, load_cached_data returns it."""
    cache_file = tmp_path / "cache.json"
    data = {"stocks": {}, "metadata": {}}
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr("cache_utils.CACHE_FILE", cache_file)
    result = load_cached_data()
    assert result == data


def test_save_cached_data_creates_file(monkeypatch, tmp_path):
    """save_cached_data writes JSON to CACHE_FILE."""
    cache_file = tmp_path / "out.json"
    monkeypatch.setattr("cache_utils.CACHE_FILE", cache_file)
    save_cached_data({"stocks": {"AAPL": {}}, "metadata": {}})
    assert cache_file.exists()
    loaded = json.loads(cache_file.read_text(encoding="utf-8"))
    assert loaded["stocks"]["AAPL"] == {}
    assert "metadata" in loaded
