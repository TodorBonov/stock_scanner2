"""
Benchmark mapping for relative strength by region/exchange.
When scanning mixed US + EU watchlists, use this to pick the right benchmark per ticker.
"""
from typing import Optional

# Ticker suffix or exchange -> benchmark symbol (Yahoo Finance)
# Source: Yahoo Finance index symbols (widely used for relative strength).
# US (no suffix or .US, NYSE/NASDAQ) -> S&P 500; Canadian -> TSX; European -> regional index.
BENCHMARK_BY_SUFFIX = {
    ".TO": "^GSPTSE",   # Canada TSX
    ".V": "^GSPTSE",
    ".PA": "^FCHI",     # CAC 40
    ".MC": "^IBEX",     # Madrid
    ".MI": "^FTMIB",    # Milan
    ".SW": "^SSMI",     # Swiss
    ".AS": "^AEX",      # Amsterdam
    ".DE": "^GDAXI",    # Xetra/DAX
    ".L": "^FTSE",      # London FTSE 100
    ".HA": "^GDAXI",    # Hamburg
    ".F": "^GDAXI",     # Frankfurt
    ".BR": "^BFX",      # Brussels
    ".ST": "^OMX",      # Sweden OMX Stockholm 30
    ".OL": "^OSEAX",    # Norway Oslo All Share
    ".CO": "^OMXC25",   # Denmark Copenhagen 25
    ".WA": "^WIG20",    # Poland WIG 20
    ".VI": "^ATX",      # Austria ATX
}

# Default for no suffix (US-style tickers like AAPL, MSFT)
DEFAULT_US_BENCHMARK = "^GSPC"
# Default for unknown/other (e.g. EU when no suffix)
DEFAULT_EU_BENCHMARK = "^GDAXI"


def get_benchmark(ticker: str, default_benchmark: Optional[str] = None) -> str:
    """
    Resolve benchmark for a ticker by exchange/suffix.
    
    Args:
        ticker: Symbol e.g. AAPL, REP.MC, BMO.TO
        default_benchmark: Fallback when no mapping (e.g. from --benchmark)
        
    Returns:
        Benchmark symbol (e.g. ^GSPC, ^GDAXI)
    """
    if not ticker:
        return default_benchmark or DEFAULT_EU_BENCHMARK
    ticker_upper = ticker.upper().strip()
    for suffix, bench in BENCHMARK_BY_SUFFIX.items():
        if ticker_upper.endswith(suffix):
            return bench
    # No suffix: assume US
    if default_benchmark:
        return default_benchmark
    return DEFAULT_US_BENCHMARK
