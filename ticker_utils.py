"""
Ticker Utility Module
Centralized ticker cleaning and mapping logic for consistent handling across all modules.
Mappings can be edited in data/ticker_mapping.json (see reportsV2/ticker_mapping_errors.txt for failures).
"""
import json
from typing import Dict, List

# Built-in defaults (also kept in data/ticker_mapping.json so file can be edited)
TICKER_MAPPING = {
    "WTAIM_EQ": "WTAI",
    "WTAIm_EQ": "WTAI",
}


def _load_ticker_mapping_from_file() -> Dict[str, str]:
    """Load ticker mapping from config file. Returns {} if file missing or invalid."""
    try:
        from config import TICKER_MAPPING_FILE
        if not TICKER_MAPPING_FILE.exists():
            return {}
        with open(TICKER_MAPPING_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return {str(k).upper(): str(v).upper() for k, v in data.items()}
    except Exception:
        return {}


def get_effective_mapping() -> Dict[str, str]:
    """Merge built-in TICKER_MAPPING with file (file overrides). Use for clean_ticker."""
    file_map = _load_ticker_mapping_from_file()
    return {**TICKER_MAPPING, **file_map}


def clean_ticker(ticker: str, use_mapping: bool = True) -> str:
    """
    Clean a ticker symbol by applying mappings and removing suffixes.
    
    This function:
    1. Checks for special ticker mappings (e.g., WTAIm_EQ -> WTAI)
    2. Strips everything from "_" and including it (e.g., "ASMLa_EQ" -> "ASMLA")
    3. Converts to uppercase
    
    Args:
        ticker: Ticker symbol (may include _EQ suffix or other suffixes)
        use_mapping: If True, apply TICKER_MAPPING first (default: True)
        
    Returns:
        Cleaned ticker symbol (single string, uppercase)
        
    Examples:
        >>> clean_ticker("WTAIm_EQ")
        'WTAI'
        >>> clean_ticker("ASMLa_EQ")
        'ASMLA'
        >>> clean_ticker("AAPL")
        'AAPL'
    """
    if not ticker:
        return ""
    
    ticker_upper = ticker.upper()
    
    # Check for special ticker mappings first (built-in + file)
    if use_mapping:
        mapping = get_effective_mapping()
        if ticker_upper in mapping:
            return mapping[ticker_upper]
    
    # Strip everything from "_" and including it (e.g., "WTAIm_EQ" -> "WTAIm")
    if "_" in ticker:
        return ticker.split("_")[0].upper()
    
    return ticker_upper


def get_possible_ticker_formats(ticker: str, include_exchange_suffixes: bool = True) -> List[str]:
    """
    Generate a list of possible ticker formats to try when searching for stock data.
    
    This is useful for international stocks where the same company may have different
    ticker formats on different exchanges (e.g., ASML vs ASML.AS).
    
    Args:
        ticker: Ticker symbol (may include _EQ suffix or other suffixes)
        include_exchange_suffixes: If True, include common European exchange suffixes
        
    Returns:
        List of possible ticker formats to try, starting with the cleaned ticker
        
    Examples:
        >>> get_possible_ticker_formats("WTAIm_EQ")
        ['WTAI', 'WTAI.L', 'WTAI.AS', ...]
        >>> get_possible_ticker_formats("AAPL")
        ['AAPL', 'AAPL.L', 'AAPL.AS', ...]
    """
    ticker_clean = clean_ticker(ticker)
    possible_tickers = [ticker_clean]
    
    if include_exchange_suffixes:
        # Common European exchange suffixes
        # .L = London (LSE), .AS = Amsterdam (Euronext), .DE = Xetra (Germany)
        # .PA = Paris (Euronext), .MI = Milan (Borsa Italiana), .SW = Swiss
        # .BR = Brussels, .MC = Madrid, .ST = Stockholm, .CO = Copenhagen
        # .VI = Vienna, .LS = Lisbon, .IR = Dublin, .HE = Helsinki
        european_suffixes = [
            ".L", ".AS", ".DE", ".PA", ".MI", ".SW", ".BR", ".MC", 
            ".ST", ".CO", ".VI", ".LS", ".IR", ".HE"
        ]
        
        # Add European variants
        for suffix in european_suffixes:
            possible_tickers.append(f"{ticker_clean}{suffix}")
    
    return possible_tickers


def add_ticker_mapping(trading212_ticker: str, actual_ticker: str):
    """
    Add a new ticker mapping to the TICKER_MAPPING dictionary.
    
    This allows runtime addition of mappings (e.g., from config file).
    
    Args:
        trading212_ticker: Trading 212 ticker format (e.g., "WTAIm_EQ")
        actual_ticker: Actual ticker symbol (e.g., "WTAI")
    """
    TICKER_MAPPING[trading212_ticker.upper()] = actual_ticker.upper()


def get_ticker_mapping(ticker: str) -> str:
    """
    Get the mapped ticker if a mapping exists, otherwise return None.
    
    Args:
        ticker: Ticker symbol to check
        
    Returns:
        Mapped ticker if mapping exists, None otherwise
    """
    return TICKER_MAPPING.get(ticker.upper())

