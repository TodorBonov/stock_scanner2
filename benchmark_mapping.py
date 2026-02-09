"""
Benchmark mapping for relative strength by region/exchange.
When scanning mixed US + EU watchlists, use this to pick the right benchmark per ticker.
"""
from typing import Optional

# Ticker suffix or exchange -> benchmark symbol (Yahoo Finance)
# US (no suffix or .US, NYSE/NASDAQ) -> S&P 500
# Canadian (.TO, .V) -> TSX
# European: .DE (Xetra), .PA (Paris), .MC (Madrid), .MI (Milan), .SW (Swiss), .AS (Amsterdam), .L (London) -> DAX or regional
BENCHMARK_BY_SUFFIX = {
    ".TO": "^GSPTSE",   # Canada TSX
    ".V": "^GSPTSE",
    ".PA": "^FCHI",     # CAC 40
    ".MC": "^IBEX",     # Madrid (or ^GDAXI for broad EU)
    ".MI": "^FTMIB",    # Milan
    ".SW": "^SSMI",     # Swiss
    ".AS": "^AEX",      # Amsterdam
    ".DE": "^GDAXI",    # Xetra/DAX
    ".L": "^FTSE",      # London
    ".HA": "^GDAXI",    # Hamburg
    ".F": "^GDAXI",     # Frankfurt
    ".BR": "^BFX",      # Brussels
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
