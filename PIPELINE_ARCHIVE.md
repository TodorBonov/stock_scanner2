# Pipeline archive (original pipeline)

The **original pipeline** (01 → 04 → 05 → 06 → 07) is preserved so you can run it anytime. Day-to-day use is **Pipeline V2** (`run_pipeline_v2.py`).

## Where it’s saved

- **Branch:** `pipeline-v1` — snapshot of the repo with both pipelines; original pipeline scripts are unchanged.
- **Tag:** `pipeline-v1-baseline` — permanent reference to that state.

## One-time setup (create branch and tag)

From the repo root, with your current work committed (or at least the state you want to preserve):

```powershell
# Optional: commit current work so branch/tag include it
git add -A
git commit -m "Pipeline V2 as primary; archive original pipeline on pipeline-v1"

# Create archive branch and tag
git branch pipeline-v1
git tag pipeline-v1-baseline -m "Original pipeline (01→04→05→06→07) baseline; use run_pipeline_v2.py on main"
```

To push the branch and tag to the remote (e.g. GitHub):

```powershell
git push origin pipeline-v1
git push origin pipeline-v1-baseline
```

## How to run the original pipeline later

1. **Checkout the archive branch:**
   ```powershell
   git checkout pipeline-v1
   ```

2. **Run the original sequence** (no single runner script; run in order):
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

Or open a specific snapshot anytime with:

```powershell
git checkout pipeline-v1-baseline
```

## Summary

| What              | Where / command                          |
|-------------------|------------------------------------------|
| Use from now on   | `python run_pipeline_v2.py` (on `main`)  |
| Original pipeline | Branch `pipeline-v1`, tag `pipeline-v1-baseline` |
| Docs              | **PIPELINES.md** (original), **PIPELINE_V2.md** (V2) |
