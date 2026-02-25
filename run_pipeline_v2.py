"""
Run the complete Pipeline V2: 01 → 02 → 03 → 04 V2 → 05 → 05 V2 → 06 → 08.

  python run_pipeline_v2.py
  python run_pipeline_v2.py --csv       # also export CSV from 04 V2
  python run_pipeline_v2.py --refresh   # force step 01 to refetch from Yahoo (ignore cache)
  python run_pipeline_v2.py --csv --refresh
"""
import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
STEPS = [
    ("01", "01_fetch_yahoo_watchlist.py"),
    ("02", "02_fetch_positions_trading212.py"),
    ("03", "03_prepare_for_minervini.py"),
    ("04 V2", "04_generate_full_report_v2.py"),
    ("05", "05_prepare_chatgpt_data.py"),
    ("05 V2", "05_prepare_chatgpt_data_v2.py"),
    ("06", "06_chatgpt_existing_positions.py"),
    ("08", "08_chatgpt_new_positions_v2.py"),
]


def main():
    parser = argparse.ArgumentParser(description="Run complete Pipeline V2 (01 → 02 → 03 → 04 V2 → 05 → 05 V2 → 06 → 08)")
    parser.add_argument("--csv", action="store_true", help="Export CSV from 04 V2 (sepa_scan_summary_<ts>.csv in reports/v2/)")
    parser.add_argument("--refresh", action="store_true", help="Force step 01 to refetch all data from Yahoo (ignore cache)")
    args = parser.parse_args()

    extra_04 = ["--csv"] if args.csv else []
    extra_01 = ["--refresh"] if args.refresh else []

    for name, script in STEPS:
        path = SCRIPT_DIR / script
        if not path.exists():
            print(f"[ERROR] Not found: {path}")
            sys.exit(1)
        cmd = [sys.executable, str(path)]
        if name == "01" and extra_01:
            cmd.extend(extra_01)
        elif name == "04 V2" and extra_04:
            cmd.extend(extra_04)
        print(f"\n{'='*60}\nStep {name}: {script}\n{'='*60}")
        rc = subprocess.call(cmd, cwd=str(SCRIPT_DIR))
        if rc != 0:
            print(f"[ERROR] Step {name} exited with code {rc}")
            sys.exit(rc)
    print("\nPipeline V2 completed.\n")


if __name__ == "__main__":
    main()
