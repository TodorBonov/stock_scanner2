"""
Watchlist loader: CSV (type, yahoo_symbol, trading212_symbol, benchmark_index) or legacy one-symbol-per-line.
Used by 01 (fetch) and 03 (prepare for Minervini).
"""
import csv
from pathlib import Path
from typing import List, Dict, Any

from logger_config import get_logger
from benchmark_mapping import get_benchmark

logger = get_logger(__name__)

# CSV columns
TYPE = "type"
YAHOO_SYMBOL = "yahoo_symbol"
TRADING212_SYMBOL = "trading212_symbol"
BENCHMARK_INDEX = "benchmark_index"
TICKER_GROUP = "ticker_group"
REGION = "region"
SECTOR = "sector"
MARKET_CAP = "market_cap"

VALID_TYPES = ("ticker", "index")


def load_watchlist_csv(path: str) -> List[Dict[str, str]]:
    """
    Load watchlist from CSV.

    Required logical columns:
    - type
    - yahoo_symbol
    - trading212_symbol
    - benchmark_index

    Optional logical columns (if present in the CSV header, names are matched
    case-insensitively and with spaces/underscores normalized):
    - ticker_group
    - region
    - sector
    - market_cap
    type must be 'ticker' or 'index'. Returns list of dicts with keys normalized (strip, uppercase where needed).
    """
    out: List[Dict[str, str]] = []
    p = Path(path)
    if not p.exists():
        logger.error("Watchlist CSV not found: %s", path)
        return []
    with open(p, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        # Normalize field names (strip, lowercase)
        fieldmap = {fn.strip().lower().replace(" ", "_"): fn for fn in reader.fieldnames}
        for row in reader:
            raw_type = (row.get(fieldmap.get("type", "type")) or "").strip().lower()
            yahoo = (row.get(fieldmap.get("yahoo_symbol", "yahoo_symbol")) or "").strip().upper()
            t212 = (row.get(fieldmap.get("trading212_symbol", "trading212_symbol")) or "").strip().upper()
            bench = (row.get(fieldmap.get("benchmark_index", "benchmark_index")) or "").strip().upper()
            group = (row.get(fieldmap.get("ticker_group", "ticker_group")) or "").strip()
            region = (row.get(fieldmap.get("region", "region")) or "").strip()
            sector = (row.get(fieldmap.get("sector", "sector")) or "").strip()
            market_cap = (row.get(fieldmap.get("market_cap", "market_cap")) or "").strip()
            if not yahoo:
                continue
            if raw_type not in VALID_TYPES:
                raw_type = "ticker"
            if not bench and yahoo:
                bench = get_benchmark(yahoo, None) or "^GDAXI"
            rec: Dict[str, Any] = {
                TYPE: raw_type,
                YAHOO_SYMBOL: yahoo,
                TRADING212_SYMBOL: t212 or "",
                BENCHMARK_INDEX: bench or "^GDAXI",
                TICKER_GROUP: group,
            }
            # Attach optional enrichment only if present (keep loader backward compatible).
            if region:
                rec[REGION] = region
            if sector:
                rec[SECTOR] = sector
            if market_cap:
                rec[MARKET_CAP] = market_cap
            out.append(rec)
    logger.info("Loaded %d rows from watchlist CSV %s", len(out), path)
    return out


def load_watchlist_legacy(path: str) -> List[Dict[str, str]]:
    """Load legacy watchlist (one symbol per line, # comments). Returns list of dicts with type=ticker, benchmark from suffix."""
    out: List[Dict[str, str]] = []
    p = Path(path)
    if not p.exists():
        logger.error("Watchlist file not found: %s", path)
        return []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            symbol = line.strip()
            if not symbol or symbol.startswith("#"):
                continue
            symbol = symbol.upper()
            bench = get_benchmark(symbol, None) or "^GDAXI"
            out.append({
                TYPE: "ticker",
                YAHOO_SYMBOL: symbol,
                TRADING212_SYMBOL: "",
                BENCHMARK_INDEX: bench,
            })
    logger.info("Loaded %d symbols from legacy watchlist %s", len(out), path)
    return out


def load_watchlist(path: str) -> List[Dict[str, str]]:
    """
    Load watchlist: if path ends with .csv or file exists as CSV, use CSV format;
    otherwise use legacy one-symbol-per-line. Returns list of dicts with type, yahoo_symbol, trading212_symbol, benchmark_index.
    """
    p = Path(path)
    if p.suffix.lower() == ".csv" or (p.exists() and p.suffix.lower() == ".csv"):
        return load_watchlist_csv(path)
    # Try CSV first if watchlist.csv exists in same dir or default
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                first = f.readline()
            if first.strip().lower().startswith("type") or "," in first:
                return load_watchlist_csv(path)
        except Exception:
            pass
        return load_watchlist_legacy(path)
    # Try watchlist.csv in same directory
    csv_path = p.parent / "watchlist.csv"
    if csv_path.exists():
        return load_watchlist_csv(str(csv_path))
    return load_watchlist_legacy(path)


def get_yahoo_symbols_for_fetch(rows: List[Dict[str, str]]) -> List[str]:
    """Return list of yahoo_symbol to fetch (tickers + indexes). No duplicates, order preserved."""
    seen = set()
    out: List[str] = []
    for r in rows:
        y = (r.get(YAHOO_SYMBOL) or "").strip().upper()
        if y and y not in seen:
            seen.add(y)
            out.append(y)
    return out


def get_ticker_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Return only rows with type=ticker (exclude indexes)."""
    return [r for r in rows if (r.get(TYPE) or "").lower() == "ticker"]
