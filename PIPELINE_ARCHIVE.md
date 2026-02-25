# Pipeline archive (original pipeline)

**main** has only **Pipeline V2** and shared code; any script or config used only by the original pipeline has been removed from main.

The **original pipeline** (01 → 04 → 05 → 06 → 07) lives on branch **V1**. Shared files (01, 02, 03, 05, 06, config, etc.) exist on both branches and can evolve separately.

## Where the original pipeline lives

- **Branch: `V1`** — full repo with everything the old pipeline needs (04_generate_full_report.py, 07_chatgpt_new_positions.py, pre_breakout_*, generate_full_report.py, etc.).
- **Branch: `pipeline-v1`** / **Tag: `pipeline-v1-baseline`** — earlier snapshot with both pipelines in one tree (before we split).

## How to run the original pipeline

1. **Checkout V1:**
   ```powershell
   git checkout V1
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
| **main** | Pipeline V2 only + shared code. Run: `python run_pipeline_v2.py`. No 04_generate_full_report.py, 07_chatgpt_new_positions.py, pre_breakout_*, etc. |
| **V1** | Everything the original pipeline needs. Same shared scripts (01, 02, 03, 05, 06) plus original scan, report, and ChatGPT scripts. |

Shared files (e.g. 01, 02, 03, 05, 06, config.py) are present on both branches and can have their own life (fixes or changes on main vs V1).
