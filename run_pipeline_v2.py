"""
Run the complete Pipeline V2: 01 → 02 → 03 → 04 V2 → 05 V2 → 06 V2 → 07.

  python run_pipeline_v2.py
  python run_pipeline_v2.py --watchlist watchlist_test.csv   # short watchlist
  python run_pipeline_v2.py --refresh                        # fresh Yahoo data
  python run_pipeline_v2.py --watchlist watchlist_test.csv --refresh
  python run_pipeline_v2.py --csv                            # also export CSV from 04 V2
  python run_pipeline_v2.py --csv --refresh
  python run_pipeline_v2.py --exclude-07                     # run pipeline without step 07 (ChatGPT new positions)
"""
import argparse
import subprocess
import sys
from pathlib import Path

from config import REPORTS_DIR
from export_rank_table_for_web_v2 import main as export_rank_table_html

SCRIPT_DIR = Path(__file__).resolve().parent
STEPS = [
    ("01", "01_fetch_yahoo_watchlist_V2.py"),
    ("02", "02_fetch_positions_trading212_V2.py"),
    ("03", "03_prepare_for_minervini_V2.py"),
    ("04 V2", "04_generate_full_report_v2.py"),
    ("05 V2", "05_prepare_chatgpt_data_v2.py"),
    ("06 V2", "06_chatgpt_existing_positions_v2.py"),
    ("07", "07_chatgpt_new_positions_v2.py"),
]


def main():
    parser = argparse.ArgumentParser(description="Run complete Pipeline V2 (01 → 02 → 03 → 04 V2 → 05 V2 → 06 V2 → 07)")
    parser.add_argument("--watchlist", default="watchlist.csv", help="Watchlist CSV or .txt (default: watchlist.csv; use watchlist_test.csv for short list)")
    parser.add_argument("--csv", action="store_true", help="Export CSV from 04 V2 (sepa_scan_summary_<ts>.csv in reportsV2/)")
    parser.add_argument("--refresh", action="store_true", help="Force step 01 to refetch all data from Yahoo (ignore cache)")
    parser.add_argument("--exclude-07", action="store_true", help="Skip step 07 (ChatGPT new positions)")
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
        elif name == "03" or name == "05 V2":
            cmd.extend(watchlist_arg)
        elif name == "04 V2" and extra_04:
            cmd.extend(extra_04)
        print(f"\n{'='*60}\nStep {name}: {script}\n{'='*60}")
        rc = subprocess.call(cmd, cwd=str(SCRIPT_DIR))
        if rc != 0:
            print(f"[ERROR] Step {name} exited with code {rc}")
            sys.exit(rc)

        # After the SEPA V2 scan step (04 V2) completes and writes scan_results_v2_latest.json,
        # generate/update the public rank table HTML in docs/index.html.
        if name == "04 V2":
            try:
                export_rank_table_html()
            except SystemExit as e:
                # Keep the pipeline running even if HTML export fails.
                print(f"[WARN] Rank table HTML export failed: {e}")
    print("\nPipeline V2 completed.\n")


if __name__ == "__main__":
    main()
