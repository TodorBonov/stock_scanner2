# V2 run comparison (after config changes)

## What was run

- **04 V2** (with `--csv`): New scan → `scan_results_v2_latest.json`, **sepa_scan_user_report_20260223_232224.txt**
- **05 V2**: Prepared data → `prepared_new_positions_v2.json` (70 A+/A)
- **08**: ChatGPT analysis was started (may still be running); when finished → **chatgpt_new_positions_v2_<new_ts>.txt**

## Score comparison: new SEPA vs old SEPA

| Report | File | Top-5 scores (Rank table) |
|--------|------|---------------------------|
| **Old SEPA** | sepa_scan_user_report_20260223_223636.txt | NEOG 96.9, FOLD 95.6, TTC 95.4, GEV 95.3, PLAB 92.1 |
| **New SEPA** | sepa_scan_user_report_20260223_232224.txt | NEOG 96.9, FOLD 95.6, TTC 95.4, GEV 95.3, PLAB 92.1 |

**Result:** The ranked table and **composite scores are identical** between the two SEPA reports. Same universe (1710), same 278 eligible, same 70 A+/A, same order and same score per ticker.

**Why:** The config changes we made did not change the **values** of the scoring parameters (same weights, same band numbers). We only moved hardcoded numbers into config and changed:
- `EXTENDED_DISTANCE_PCT`: 5 → 8 (only affects “Extended” **status** and breakout **component** when distance > 8%)
- `EXTENDED_RISK_WARNING_PCT`: 10 → 15 (only affects Risk Warnings section)
- No ticker in this run had distance in (5%, 8%] or >15%, so **no visible change** in status or risk warnings for this dataset.

## ChatGPT report vs SEPA report (scores)

**By design, composite scores in the ChatGPT report are the same as in the SEPA report** for the same run. Both use the same source: `scan_results_v2_latest.json` (SEPA from 04, ChatGPT from 05 → 08).

- **Old run:** chatgpt_new_positions_v2_20260223_225937 shows FOLD composite=95.6, TTC composite=95.4, etc. — **matches** sepa_scan_user_report_20260223_223636 (FOLD 95.6, TTC 95.4).
- **New run:** When 08 finishes, the new ChatGPT file will show the same composite scores as sepa_scan_user_report_20260223_232224 (because they share the same scan).

So you **already had** “closer” (identical) scores between ChatGPT and SEPA for the same run. The **order** in the ChatGPT RANKING is different (ChatGPT re-orders by its own recommendation; SEPA orders by composite_score). The **numbers** (composite_score per ticker) are the same.

## Summary

1. **New SEPA (232224) vs old SEPA (223636):** Scores and table are **identical**. Config change had no effect on scores for this data; only extended thresholds were changed and no ticker fell in the affected ranges.
2. **ChatGPT vs SEPA scores:** For a given run, they are **the same** (same scan JSON). So you don’t get “closer” scores with the new run — they were already aligned; the new ChatGPT output will again match the new SEPA report’s scores.
3. **When 08 finishes:** Check `reports/v2/` for the newest `chatgpt_new_positions_v2_<timestamp>.txt`; its composite values will match `sepa_scan_user_report_20260223_232224.txt` for each ticker.
