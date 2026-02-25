# Pipeline archive (original pipeline)

**main** has only **Pipeline V2** and the code needed to run it. Scripts and configs used only by the original pipeline have been removed from main.

The **original pipeline** (01 → 04 → 05 → 06 → 07) lives on branch **pipeline-v1**. Shared files (01, 02, 03, 05, 06, config, etc.) exist on both branches and can evolve separately.

## Where the original pipeline lives

- **Branch: `pipeline-v1`** — full repo with everything the old pipeline needs (04_generate_full_report.py, 07_chatgpt_new_positions.py, pre_breakout_*, generate_full_report.py, etc.).

## How to run the original pipeline

1. **Checkout pipeline-v1:**
   ```powershell
   git checkout pipeline-v1
   ```

2. **Run the original sequence** (in order):
   ```powershell
   python 01_fetch_yahoo_watchlist.py
   python 02_fetch_positions_trading212.py
   python 03_prepare_for_minervini.py
   python 04_generate_full_report.py
   python 05_prepare_chatgpt_data.py
   python 06_chatgpt_existing_positions.py
   python 07_chatgpt_new_positions.py
   ```

3. **Switch back to main** when done:
   ```powershell
   git checkout main
   ```

## Summary

| Branch | Contents |
|--------|----------|
| **main** | Pipeline V2 only. Run: `python run_pipeline_v2.py`. No 04_generate_full_report.py, 07_chatgpt_new_positions.py, pre_breakout_*, etc. |
| **pipeline-v1** | Everything the original pipeline needs. Same shared scripts (01, 02, 03, 05, 06) plus original scan, report, and ChatGPT scripts. |

Shared files (e.g. 01, 02, 03, 05, 06, config.py) are on both branches and can have their own life (fixes on main vs pipeline-v1).
