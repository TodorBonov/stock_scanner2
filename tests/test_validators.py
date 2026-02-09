"""Tests for validators module."""
import pytest

from validators import (
    ValidationError,
    sanitize_ticker,
    validate_ticker_list,
    validate_file_path,
    validate_api_key,
    mask_credential,
)


def test_sanitize_ticker_valid():
    assert sanitize_ticker("AAPL") == "AAPL"
    assert sanitize_ticker("  msft  ") == "MSFT"


def test_sanitize_ticker_empty_raises():
    with pytest.raises(ValidationError, match="cannot be empty"):
        sanitize_ticker("")


def test_sanitize_ticker_not_string_raises():
    with pytest.raises(ValidationError, match="must be a string"):
        sanitize_ticker(123)


def test_sanitize_ticker_invalid_chars_raises():
    with pytest.raises(ValidationError, match="invalid characters"):
        sanitize_ticker("AAPL@")


def test_validate_ticker_list_valid():
    assert validate_ticker_list(["AAPL", "MSFT"]) == ["AAPL", "MSFT"]


def test_validate_ticker_list_empty_raises():
    with pytest.raises(ValidationError, match="cannot be empty"):
        validate_ticker_list([])


def test_validate_file_path_valid():
    # Use current file path which exists
    path_str = __file__
    result = validate_file_path(path_str, must_exist=True)
    assert result is not None
    assert result.exists()


def test_validate_file_path_empty_raises():
    with pytest.raises(ValidationError, match="cannot be empty"):
        validate_file_path("")


def test_validate_api_key_valid():
    assert validate_api_key("a" * 15) == "a" * 15


def test_validate_api_key_too_short_raises():
    with pytest.raises(ValidationError, match="too short"):
        validate_api_key("short")


def test_mask_credential_masks():
    from config import MASKED_CREDENTIAL_LENGTH
    s = "secretkey1234"
    masked = mask_credential(s)
    assert masked.endswith(s[-MASKED_CREDENTIAL_LENGTH:])
    assert masked == "*" * (len(s) - MASKED_CREDENTIAL_LENGTH) + s[-MASKED_CREDENTIAL_LENGTH:]
    assert mask_credential("ab") == "****"
