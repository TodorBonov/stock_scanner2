"""
Shared cache helpers for stock data.
Used by 01_fetch_stock_data.py, 02_generate_full_report.py, 03_chatgpt_validation.py, 04_retry_failed_stocks.py.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from config import CACHE_FILE

logger = logging.getLogger(__name__)


def load_cached_data() -> Optional[Dict[str, Any]]:
    """
    Load cached stock data from CACHE_FILE.
    Returns None if file missing or invalid; otherwise returns dict with 'stocks' and 'metadata' keys.
    """
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.debug("Cache file content is not a dict")
            return None
        return data
    except Exception as e:
        logger.debug("Failed to load cache from %s: %s", CACHE_FILE, e, exc_info=True)
        return None


def save_cached_data(data: Dict[str, Any]) -> None:
    """Save stock data to CACHE_FILE. Raises on write error."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
