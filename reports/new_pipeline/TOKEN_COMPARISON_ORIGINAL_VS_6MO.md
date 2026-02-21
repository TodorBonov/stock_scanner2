# Token comparison: Original (full OHLCV) vs 6-month only

Same prompts, same 8000 completion cap, same limits (5 existing positions, 50 A+/A new positions).  
**Only change:** OHLCV data limited to last **126 days (6 months)** per stock in the 6mo pipeline.

## Scripts (6mo-only, suggestion 1)

| Script | Purpose |
|--------|--------|
| `New3_prepare_chatgpt_data_6mo.py` | Loads `prepared_existing_positions.json` and `prepared_new_positions.json`, rewrites OHLCV with last 126 days, writes `*_6mo.json`. Run **after** New3. |
| `New4_chatgpt_existing_positions_6mo.py` | Reads `prepared_existing_positions_6mo.json`, same prompt and 8000 cap as New4. Output: `chatgpt_existing_positions_6mo_<ts>.txt`. |
| `New5_chatgpt_new_positions_6mo.py` | Reads `prepared_new_positions_6mo.json`, same prompt and 8000 cap as New5, default `--limit 50`. Output: `chatgpt_new_positions_6mo_<ts>.txt`. |

## Token usage

| Run | New4 (existing positions) | New5 (new positions, 50 stocks) |
|-----|---------------------------|----------------------------------|
| **Original** (full OHLCV) | 70,748 | 715,270 |
| **6mo only** (126 days OHLCV) | 43,476 | 429,962 |

### New4 (existing positions)

- **Original:** 70,748 tokens (5 positions, full history).
- **6mo:** 43,476 tokens (5 positions, 6 months OHLCV).
- **Reduction:** ~38.5% fewer tokens with 6-month data only.

### New5 (new positions)

- **Original:** 715,270 tokens (50 A+/A stocks, full OHLCV).
- **6mo:** 429,962 tokens (50 A+/A stocks, 6 months OHLCV).
- **Reduction:** ~39.9% fewer tokens with 6-month data only.

## Run order

1. **New3** (full pipeline) → produces `prepared_existing_positions.json`, `prepared_new_positions.json`.
2. **New3_prepare_chatgpt_data_6mo.py** → produces `prepared_existing_positions_6mo.json`, `prepared_new_positions_6mo.json`.
3. **New4_chatgpt_existing_positions_6mo.py** → existing positions report (6mo).
4. **New5_chatgpt_new_positions_6mo.py** → new positions report (6mo), optionally `--limit 50` (default).

## Report files (this run)

- **New4 6mo:** `reports/new_pipeline/chatgpt_existing_positions_6mo_20260220_233649.txt` (43,476 tokens).
- **New5 6mo:** `reports/new_pipeline/chatgpt_new_positions_6mo_20260221_130451.txt` (429,962 tokens).
