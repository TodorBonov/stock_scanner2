import csv
from pathlib import Path
from typing import Dict, Optional


def _iter_lines_any_encoding(path: Path):
    last_err = None
    # Try common encodings; file appears to be UTF-16 with BOM.
    for enc in ("utf-8-sig", "utf-8", "utf-16", "utf-16-le", "utf-16-be", "cp1252"):
        try:
            with path.open("r", encoding=enc, errors="strict") as f:
                for raw in f:
                    yield raw
            return
        except UnicodeDecodeError as e:
            last_err = e
            continue
    if last_err:
        raise last_err


def build_ticker_group_map(path: Path) -> Dict[str, str]:
    """
    Build yahoo_symbol -> ticker_group map from legacy text watchlist with grouped sections.

    Rules:
    - Use latest non-empty comment line ('# ...') as group header.
    - Strip leading '#', trim whitespace.
    - If header ends with ' Stocks', strip that suffix.
      Example: '# US Tech Stocks' -> 'US Tech'.
    - Every non-comment, non-empty line under that header is a ticker in that group.
    """
    if not path.exists():
        return {}
    group_by_ticker: Dict[str, str] = {}
    current_group: Optional[str] = None

    for raw in _iter_lines_any_encoding(path):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            header = line.lstrip("#").strip()
            if (
                not header
                or header.startswith("=")
                or header.lower().startswith("add one ticker")
                or header.lower().startswith("lines starting")
            ):
                continue
            h_up = header.upper()
            # Skip meta/comment-only headers that should not become groups
            if (
                h_up.startswith("(NOTE")
                or h_up.startswith("ADDED ")
                or h_up.startswith("ADDED:")
                or h_up.startswith("FOR NOW, ADDING")
                or h_up.startswith("MAJOR HOLDINGS FROM")
            ):
                continue
            # Skip pure country labels; keep the higher-level thematic group
            country_labels = {
                "GERMANY",
                "FRANCE",
                "UK",
                "SPAIN",
                "ITALY",
                "NETHERLANDS",
                "SWEDEN",
                "NORWAY",
                "DENMARK",
                "AUSTRIA",
                "POLAND",
                "BELGIUM",
                "IRELAND",
                "SWITZERLAND",
            }
            if h_up in country_labels:
                continue
            if header.endswith(" Stocks"):
                header = header[: -len(" Stocks")].strip()
            current_group = normalize_ticker_group(header)
            continue
        symbol = line.upper()
        if not symbol or symbol.startswith("#"):
            continue
        if current_group:
            group_by_ticker[symbol] = current_group
    return group_by_ticker


def _region_from_ticker_suffix(ticker: str) -> str:
    t = ticker.upper()
    if t.startswith("^"):
        return "Global"
    if t.endswith(".DE") or t.endswith(".F") or t.endswith(".ETR"):
        return "Europe"
    if t.endswith(".L"):
        return "UK"
    if t.endswith(".PA") or t.endswith(".AS") or t.endswith(".MC") or t.endswith(".MI") or t.endswith(".BR") or t.endswith(".CO") or t.endswith(".ST") or t.endswith(".OL") or t.endswith(".VI"):
        return "Europe"
    if t.endswith(".SW") or t.endswith(".SRX"):
        return "Europe"
    if t.endswith(".TO") or t.endswith(".TSX"):
        return "Canada"
    if t.endswith(".T"):
        return "Japan"
    if t.endswith(".AX"):
        return "Australia"
    # US-listed (default) or ADRs.
    return "US"


def normalize_ticker_group(header: str) -> str:
    """Map raw section headers from watchlist.txt into cleaner, shorter group labels (no region/country)."""
    h = header.strip()
    hu = h.upper()

    # Thematic
    if "QUANTUM COMPUTING" in hu:
        return "Theme – Quantum Computing"
    if "DIVIDEND ARISTOCRATS" in hu:
        return "Theme – Dividend Quality"
    if "GROWTH STOCKS" in hu:
        return "Theme – Growth"
    if "WISDOM TREE ETF HOLDINGS" in hu or "MAJOR HOLDINGS FROM DGRW" in hu:
        return "Theme – WisdomTree Core"
    if "SECTOR ETFS" in hu:
        return "Theme – Sector ETFs"

    # Region + broad bucket
    if "CANADIAN STOCKS" in hu or "ADDITIONAL CANADIAN" in hu:
        return "All"
    if "AUSTRALIAN STOCKS" in hu:
        return "All"
    if "ASIAN STOCKS" in hu or "JAPANESE STOCKS" in hu or "SOUTH KOREA" in hu or "TAIWAN" in hu:
        return "All"

    # US sector-style buckets
    if "US TECH" in hu or "US TECHNOLOGY" in hu:
        return "Technology"
    if "US SEMICONDUCTORS" in hu:
        return "Semiconductors"
    if "US SOFTWARE / CLOUD" in hu:
        return "Software & Cloud"
    if "US CYBERSECURITY" in hu:
        return "Cybersecurity"
    if "US PHARMA" in hu:
        return "Pharma"
    if "US HEALTHCARE / BIOTECH" in hu:
        return "Biotech"
    if "US HEALTHCARE SERVICES" in hu:
        return "Healthcare Services"
    if "US CONSUMER DISCRETIONARY" in hu or "US E-COMMERCE / RETAIL" in hu or "US SPORTS / ATHLETIC" in hu:
        return "Consumer Discretionary"
    if "US CONSUMER STAPLES" in hu:
        return "Consumer Staples"
    if "US ENERGY" in hu:
        return "Energy"
    if "US MATERIALS" in hu:
        return "Materials"
    if "US INDUSTRIALS" in hu or "US AEROSPACE & DEFENSE" in hu:
        return "Industrials & Defense"
    if "US REAL ESTATE / REIT" in hu:
        return "Real Estate"
    if "US TELECOMMUNICATIONS" in hu:
        return "Telecom"
    if "US UTILITIES" in hu:
        return "Utilities"
    if "US FINANCIAL SERVICES" in hu:
        return "Financials"

    # Europe sector-style buckets
    if "EU DEFENCE" in hu or "EUROPEAN DEFENCE" in hu or "EUROPEAN DEFENSE" in hu:
        return "Defence"
    if "EUROPEAN TECHNOLOGY" in hu:
        return "Technology"
    if "EUROPEAN FINANCIALS" in hu:
        return "Financials"
    if "EUROPEAN AUTOMOTIVE" in hu:
        return "Automotive"
    if "EUROPEAN HEALTHCARE" in hu:
        return "Healthcare"
    if "EUROPEAN CONSUMER" in hu:
        return "Consumer"
    if "EUROPEAN INDUSTRIALS" in hu:
        return "Industrials"

    # Index / universe buckets
    if "S&P 1000 COMPONENTS" in hu:
        return "Universe – S&P 1000"

    # Generic fallbacks: strip leading region words like "US ", "EUROPEAN "
    if hu.startswith("US "):
        return header[3:].strip()
    if hu.startswith("EUROPEAN "):
        return header[len("EUROPEAN "):].strip()

    # Fallback: title-case the original header as a last resort
    return h


def classify_region_and_sector(ticker: str, group: str) -> (str, str):
    """
    Heuristic classification into Region and Sector based on legacy group title and ticker suffix.
    Keeps categories relatively coarse but useful for filtering.
    """
    g = (group or "").upper()
    t = ticker.upper()

    # Region
    if "US " in g or g.startswith("US "):
        region = "US"
    elif "EUROPEAN" in g or "ALL EUROPEAN" in g or any(ctry in g for ctry in ("GERMANY", "FRANCE", "UK", "SPAIN", "ITALY", "NETHERLANDS", "SWEDEN", "NORWAY", "DENMARK", "AUSTRIA", "POLAND", "BELGIUM", "IRELAND", "SWITZERLAND")):
        region = "Europe"
    elif "CANADIAN" in g:
        region = "Canada"
    elif "JAPANESE" in g or "JAPAN" in g:
        region = "Japan"
    elif "AUSTRALIAN" in g or "AUSTRALIA" in g:
        region = "Australia"
    elif "ASIAN" in g or "TAIWAN" in g or "SOUTH KOREA" in g or "CHINESE" in g:
        region = "Asia"
    elif "ETF" in g or "S&P" in g:
        region = "Global"
    else:
        region = _region_from_ticker_suffix(t)

    # Sector
    sector = "Other"
    # Tech and adjacent
    if any(x in g for x in ("TECH", "SEMICONDUCTOR", "SOFTWARE", "CLOUD", "CYBERSECURITY", "IT ")):
        sector = "Tech"
    # Healthcare / Biotech
    elif any(x in g for x in ("PHARMA", "HEALTHCARE", "BIOTECH", "MEDICAL", "HOSPITAL")):
        sector = "Healthcare"
    # Financials (incl. dividend quality bucket)
    elif any(x in g for x in ("FINANCIAL", "BANK", "INSURANCE", "DIVIDEND ARISTOCRATS", "ETF HOLDINGS")):
        sector = "Financials"
    elif any(x in g for x in ("CONSUMER DISCRETIONARY", "RETAIL", "SPORTS / ATHLETIC", "LUXURY")):
        sector = "Consumer Discretionary"
    elif any(x in g for x in ("CONSUMER STAPLES", "FOOD & BEVERAGE", "FOOD AND BEVERAGE", "STAPLES")):
        sector = "Consumer Staples"
    elif "ENERGY" in g:
        sector = "Energy"
    elif any(x in g for x in ("MATERIALS", "MINING", "CHEMICAL")):
        sector = "Materials"
    elif any(x in g for x in ("INDUSTRIALS", "AEROSPACE & DEFENSE", "DEFENCE", "DEFENSE")):
        sector = "Industrials"
    elif "UTILITIES" in g:
        sector = "Utilities"
    elif "REAL ESTATE" in g or "REIT" in g:
        sector = "Real Estate"
    elif any(x in g for x in ("TELECOMMUNICATIONS", "TELECOM")):
        sector = "Communication Services"
    elif "ETF" in g:
        sector = "ETF"
    elif "INDEX" in g or "S&P 1000" in g or "S&P 500" in g:
        sector = "Index"
    elif "GROWTH STOCKS" in g:
        sector = "Growth"

    # Explicitly tag pure index tickers as Index sector
    if t.startswith("^"):
        sector = "Index"

    return region, sector


def infer_market_cap_bucket(ticker: str, group: str, row_type: str, benchmark_index: str) -> str:
    """
    Best-effort, descriptive market-cap bucket.

    We do NOT try to be numerically precise – instead:
    - Differentiate between pure indices, ETFs, broad universes, and 'normal' large‑cap indices.
    - Keep text labels that are useful for filtering and relative‑strength work.
    """
    t = (ticker or "").upper()
    g = (group or "").upper()
    rt = (row_type or "").lower()
    bi = (benchmark_index or "").upper()

    # Explicit index rows
    if rt == "index" or t.startswith("^"):
        return "Index (benchmark / RS anchor)"

    # Sector / theme ETFs
    if "SECTOR ETF" in g or "ETF" in g:
        return "ETF"

    # Broad S&P 1000 universe bucket
    if "UNIVERSE – S&P 1000" in g or "UNIVERSE - S&P 1000" in g or "S&P 1000" in g:
        return "Small & Mid Cap (S&P 1000 universe)"

    # Dividend-quality / core buckets – implicitly biased to larger caps
    if "DIVIDEND" in g or "WISDOMTREE CORE" in g:
        return "Large Cap (Dividend / Core Tilt)"

    # Anything explicitly tagged "All" is effectively all‑cap exposure
    if g == "ALL":
        return "All Cap"

    # If we benchmark to a major large‑cap index, assume large‑/mega‑cap tilt.
    if bi in {"^GSPC", "^GDAXI", "^FTSE", "^FCHI", "^SSMI", "^OMXC25", "^IBEX", "^AEX", "^GSPTSE"}:
        if rt == "ticker":
            return "Large / Mega Cap (index component or peer)"

    # Fallback – leave blank so you can manually refine later if needed.
    return ""


def backfill_csv(csv_path: Path, group_map: Dict[str, str]) -> None:
    if not csv_path.exists():
        return
    rows = []
    REGION_COL = "Region"
    SECTOR_COL = "Sector"
    MARKET_CAP_COL = "Market Cap"
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        # We intentionally do NOT persist "Ticker Group" back to the CSV anymore.
        # The legacy group is only used internally to derive Region/Sector/Market Cap.
        fieldnames = [fn for fn in fieldnames if fn.strip().lower().replace(" ", "_") != "ticker_group"]

        # Ensure Region/Sector/Market Cap columns exist.
        if REGION_COL not in fieldnames:
            fieldnames.append(REGION_COL)
        if SECTOR_COL not in fieldnames:
            fieldnames.append(SECTOR_COL)
        if MARKET_CAP_COL not in fieldnames:
            fieldnames.append(MARKET_CAP_COL)
        for row in reader:
            # Drop any legacy "Ticker Group" key coming from older CSV versions.
            for k in list(row.keys()):
                if k and k.strip().lower().replace(" ", "_") == "ticker_group":
                    row.pop(k, None)

            ticker = (row.get("yahoo_symbol") or "").strip().upper()
            if not ticker:
                rows.append(row)
                continue
            # Always (re)derive from mapping when available; CSV is derived from watchlist.txt here.
            group = group_map.get(ticker, "")

            # Derive Region and Sector from group + ticker suffix.
            region, sector = classify_region_and_sector(ticker, group)
            row[REGION_COL] = region
            row[SECTOR_COL] = sector

            # Best-effort descriptive Market Cap bucket (no live data source wired in).
            row_type = (row.get("type") or "").strip()
            benchmark_index = (row.get("benchmark_index") or "").strip()
            row[MARKET_CAP_COL] = infer_market_cap_bucket(ticker, group, row_type, benchmark_index)
            rows.append(row)

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    root = Path(__file__).resolve().parent
    txt_path = root / "watchlist.txt"
    group_map = build_ticker_group_map(txt_path)
    if not group_map:
        return

    backfill_csv(root / "watchlist.csv", group_map)
    backfill_csv(root / "watchlist_test.csv", group_map)


if __name__ == "__main__":
    main()

