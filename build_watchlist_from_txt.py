"""
Build watchlist.csv from watchlist.txt.

Reads one-symbol-per-line from watchlist.txt (comments with #), assigns benchmark_index
via benchmark_mapping (Yahoo Finance indices as source of truth), and writes watchlist.csv
with columns: type, yahoo_symbol, trading212_symbol, benchmark_index.

Also adds index rows for each unique benchmark so the pipeline can fetch index data.
"""
import csv
from pathlib import Path
from typing import Dict, List, Optional

from benchmark_mapping import get_benchmark


def _find_watchlist_txt(project_dir: Path) -> Optional[Path]:
    """Resolve watchlist.txt: project dir then parent (Scripts)."""
    for p in (project_dir / "watchlist.txt", project_dir.parent / "watchlist.txt"):
        if p.exists():
            return p
    return None


def load_tickers_from_txt(path: Path) -> List[str]:
    """Load unique tickers from a one-symbol-per-line file. Skip comments and empty lines."""
    seen: set[str] = set()
    out: list[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip().upper()
            if not s or s.startswith("#"):
                continue
            if s not in seen:
                seen.add(s)
                out.append(s)
    return out


def build_csv_rows(tickers: List[str]) -> List[Dict[str, str]]:
    """Build CSV rows: one ticker row per symbol, then one index row per unique benchmark."""
    rows: List[Dict[str, str]] = []
    benchmarks_seen: set[str] = set()

    for yahoo_symbol in tickers:
        bench = get_benchmark(yahoo_symbol, None)
        # T212 symbol: leave empty; pipeline can use Yahoo symbol where same
        t212 = yahoo_symbol if "." not in yahoo_symbol else ""
        rows.append({
            "type": "ticker",
            "yahoo_symbol": yahoo_symbol,
            "trading212_symbol": t212,
            "benchmark_index": bench,
        })
        benchmarks_seen.add(bench)

    # Append index rows so we fetch benchmark data (order: match common usage)
    for idx in sorted(benchmarks_seen):
        rows.append({
            "type": "index",
            "yahoo_symbol": idx,
            "trading212_symbol": "",
            "benchmark_index": idx,
        })

    return rows


def main() -> None:
    project_dir = Path(__file__).resolve().parent
    txt_path = _find_watchlist_txt(project_dir)
    if not txt_path:
        raise SystemExit("watchlist.txt not found in project or parent directory.")

    tickers = load_tickers_from_txt(txt_path)
    if not tickers:
        raise SystemExit("No tickers found in watchlist.txt.")

    rows = build_csv_rows(tickers)
    out_path = project_dir / "watchlist.csv"
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["type", "yahoo_symbol", "trading212_symbol", "benchmark_index"])
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(tickers)} tickers + {len(rows) - len(tickers)} index rows to {out_path}")


if __name__ == "__main__":
    main()
