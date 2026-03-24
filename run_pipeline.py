"""
Run the complete pipeline: 01 → 02 → 03 → 04 → 05 → 06 → 07.

  python run_pipeline.py
  python run_pipeline.py --watchlist watchlist_test.csv   # short watchlist
  python run_pipeline.py --refresh                        # fresh Yahoo data
  python run_pipeline.py --watchlist watchlist_test.csv --refresh
  python run_pipeline.py --csv                            # also export CSV from step 04
  python run_pipeline.py --csv --refresh
  python run_pipeline.py --exclude-07                     # skip step 07 (rank candidates)
"""
import argparse
import subprocess
import sys
from pathlib import Path

from config import REPORTS_DIR
from sepa_web_export import main as export_rank_table_html

SCRIPT_DIR = Path(__file__).resolve().parent
STEPS = [
    ("01", "01_fetch_prices.py"),
    ("02", "02_fetch_positions.py"),
    ("03", "03_prepare_data.py"),
    ("04", "04_scan.py"),
    ("05", "05_prep_ai_data.py"),
    ("06", "06_analyze_holdings.py"),
    ("07", "07_rank_candidates.py"),
]


def main():
    parser = argparse.ArgumentParser(description="Run the SEPA scanner pipeline (01 → 02 → 03 → 04 → 05 → 06 → 07)")
    parser.add_argument("--watchlist", default="watchlist.csv", help="Watchlist CSV or .txt (default: watchlist.csv; use watchlist_test.csv for short list)")
    parser.add_argument("--csv", action="store_true", help="Export CSV summary from step 04 (reports/scan/)")
    parser.add_argument("--refresh", action="store_true", help="Force step 01 to refetch all data from Yahoo (ignore cache)")
    parser.add_argument("--exclude-07", action="store_true", help="Skip step 07 (rank candidates)")
    args = parser.parse_args()

    extra_04 = ["--csv"] if args.csv else []
    extra_01 = ["--refresh"] if args.refresh else []
    watchlist_arg = ["--watchlist", args.watchlist]

    # Ensure required directories exist (fresh clone / first run)
    SCRIPT_DIR.joinpath("data").mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    for name, script in STEPS:
        if name == "07" and args.exclude_07:
            print(f"\n{'='*60}\nStep {name}: skipped (--exclude-07)\n{'='*60}")
            continue
        path = SCRIPT_DIR / script
        if not path.exists():
            print(f"[ERROR] Not found: {path}")
            sys.exit(1)
        cmd = [sys.executable, str(path)]
        if name == "01":
            cmd.extend(watchlist_arg)
            if extra_01:
                cmd.extend(extra_01)
        elif name == "03" or name == "05":
            cmd.extend(watchlist_arg)
        elif name == "04" and extra_04:
            cmd.extend(extra_04)
        print(f"\n{'='*60}\nStep {name}: {script}\n{'='*60}")
        rc = subprocess.call(cmd, cwd=str(SCRIPT_DIR))
        if rc != 0:
            print(f"[ERROR] Step {name} exited with code {rc}")
            sys.exit(rc)

        # After step 04 (scan) completes, generate/update the public rank table HTML.
        if name == "04":
            try:
                export_rank_table_html()
            except SystemExit as e:
                # Keep the pipeline running even if HTML export fails.
                print(f"[WARN] Rank table HTML export failed: {e}")
    print("\nPipeline completed.\n")


if __name__ == "__main__":
    main()
