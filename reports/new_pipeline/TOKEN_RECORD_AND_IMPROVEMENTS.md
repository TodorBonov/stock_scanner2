# New Pipeline – Token Record & Improvement Suggestions

The new pipeline (New1–New5) is the default workflow on the **main** branch. See **PIPELINES.md** in the repo root for branch strategy and run order.

**Run date:** 2026-02-20  
**Watchlist:** full (watchlist.txt)  
**New1:** 1,912 tickers → Fetched 1,707, Skipped 172, Errors 33  
**New2:** 5 positions (Trading212)  
**New3:** 1,742 scanned → 5 positions prepared, **84 A+/A** prepared (New5 used default `--limit 50`)  
**Model:** gpt-5.2  

---

## Token usage (this run)

| Step   | Items | Total tokens | Tokens per item |
|--------|-------|--------------|-----------------|
| **New4** (existing positions) | 5  | **70,748**  | ~14,150 |
| **New5** (new positions A+/A) | 50 | **715,270** | ~14,305 |
| **Total**                    | 55 | **786,018** | —       |

- New5 was capped at 50 stocks (script default `--limit 50`). There were **84 A+/A** in prepared data.
- **Extrapolated full New5** (84 stocks): 84 × ~14,305 ≈ **1,201,620** tokens → **Total full run ≈ 1,272,368 tokens**.

---

## Estimated cost (this run, GPT-5.2)

- Assumption: ~25% input, ~75% output.
- 786,018 tokens → ~196.5k input, ~589.5k output.
- At $1.75/1M input, $14/1M output: **~$8.50** for this run.
- **Full run (84 A+/A):** ~**$14** (New4 + New5 with no limit).

---

## Suggested improvements to reduce tokens

### 1. **Limit OHLCV to last 6 months (New3)** — High impact on input
- **Current:** Full 1-year daily (~252 rows) per stock → ~3,000–4,000 input tokens per request.
- **Change:** In `New3_prepare_chatgpt_data.py`, in `ohlcv_to_csv_rows()`, take only the **last N trading days** (e.g. 126).
- **Effect:** Roughly **30–40% fewer input tokens** per call; 200-day MA still possible.

### 2. **Cap output length (New4 & New5)** — High impact on cost
- **Current:** `max_completion_tokens = 8000` per request; model often writes long reports.
- **Change:** Lower to **4,000** (or 3,000) and add to the prompt: *"Keep your response under 4,000 tokens. Be concise; focus on key levels, rating, and exact action (HOLD/ADD/TRIM/EXIT or STRONG BUY/BUY ON PULLBACK/WAIT/PASS)."*
- **Effect:** **~40–50% fewer output tokens** per call; output is the main cost driver for GPT-5.2.

### 3. **Use `--limit` on New5 for routine runs** — Direct control of cost
- **Current:** Default `--limit 50` (this run); 84 A+/A available.
- **Change:** Keep `--limit 50` for weekly runs, or set **20–30** for cheaper runs. Use full list only when needed.
- **Effect:** Linear: 20 stocks ≈ 286k tokens for New5 instead of 715k.

### 4. **Shorten the prompt template (New4 & New5)** — Moderate impact
- **Current:** Long 8-section prompt (~400–500 tokens per request).
- **Change:** Use a condensed version: e.g. "Trend (50/150/200), key support/resistance, Minervini pivot, HOLD/ADD/TRIM/EXIT (or buy recommendation), stop and add levels. Be concise."
- **Effect:** **~10–15% fewer input tokens** per call.

### 5. **Optional: weekly bars for OHLCV (New3)** — Large input reduction
- **Current:** Daily bars (~252 rows).
- **Change:** Resample to weekly in New3 before building CSV (~52 rows).
- **Effect:** **~80% fewer OHLCV input tokens**; analysis becomes more swing/weekly.

### 6. **Cheaper model for routine runs**
- **GPT-4o:** Similar quality, lower cost (~$5 for this run instead of ~$8.50).
- **GPT-4o mini:** Much cheaper (~$0.50 for this run), less depth.

---

## Quick reference: tokens per run (full watchlist)

| Scenario              | New4 (5 pos) | New5 (50 A/A) | New5 (84 A/A) | Total (approx) |
|-----------------------|--------------|---------------|---------------|----------------|
| This run              | 70,748       | 715,270       | —             | 786,018        |
| Full New5 (no limit)  | 70,748       | —             | ~1,201,620    | ~1,272,368     |
| With improvements 1+2| ~45,000      | ~430,000      | ~722,000      | ~475,000 / ~767,000 |

Improvements 1 and 2 together can bring a 50-stock run into the **~475k token** range and cut cost by about **40%** for the same number of stocks.
