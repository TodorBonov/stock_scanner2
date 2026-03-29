# Potential Improvements

---

## To-Do

1. **Backtesting** — validate that composite scores predict forward returns
2. ~~EUR/USD mixing in steps 06/07~~ — **done**: step 05 now checks the cached OHLCV's actual stored currency (not just the live rate) and converts correctly; `ohlcv_currency` is passed to step 06 so the prompt labels OHLCV and position prices with their correct currencies
3. ChatGPT grade extraction is regex-based — if the model doesn't follow the exact format, the grade is silently empty; needs validation or a structured output approach
4. ~~Historical scan storage~~ — **done**: each run appends flattened rows to `reports/scan/history.jsonl`
5. Alert system — notify (email / Slack) when a new A+ or A stock appears in the scan
6. Performance tracking — record what was recommended (HOLD/ADD/TRIM/EXIT) and what the stock actually did afterward; feeds back into backtesting

---

## Backtesting design

The scanner produces a **point-in-time signal**: as of date T, ticker X had composite score Y and grade Z. Backtesting means asking whether higher scores predicted better forward returns.

### What you need

- **Historical scan snapshots** — run the scanner on past dates using OHLCV data as it existed on those dates (point-in-time, no lookahead). Requires storing daily OHLCV going back further than 1 year.
- **Forward returns** — for each (ticker, scan_date) pair, record the return N days later (e.g. 20, 60, 120 trading days).
- **Grade labels** — A+, A, B, C, REJECT for each snapshot.

### Questions to answer

- Do A+ stocks outperform A stocks in forward returns? Do A outperform B/C?
- What is the average return 20/60/120 days after an A+ signal?
- What is the hit rate (% of A+ signals that are profitable at 60 days)?
- Are composite score deciles monotonically related to forward returns?
- Which component score (trend, base, RS, volume, breakout) has the highest predictive power individually?

### Approach

1. **Gather historical data** — extend `01_fetch_prices.py` to fetch 3–5 years of daily OHLCV instead of 1 year.
2. **Point-in-time replay** — for each date T in the past, slice the OHLCV to `hist[:T]` and run `MinerviniScannerV2.scan_stock()`. This avoids lookahead bias.
3. **Store snapshots** — save each (date, ticker, grade, composite_score, component_scores) to a CSV or SQLite table.
4. **Compute forward returns** — join snapshots with OHLCV to get return from T to T+N.
5. **Analyse** — group by grade, plot average forward return and hit rate per grade band; run correlation between composite score and forward return.

### Key risk: survivorship bias

The current watchlist only contains stocks you chose to watch. To test the scanner objectively, the universe at each historical date should be the same universe that existed then — delisted stocks must be included. Without this, results will be optimistic.

### Suggested first pass (simpler, biased but fast)

Run the scanner on the current watchlist using the last 2 years of data, slicing at monthly intervals. This has survivorship bias but gives a directional answer quickly and validates the tooling before investing in a clean dataset.

---

## EUR/USD currency handling

**Problem:** Step 01 converts EUR stock OHLCV to USD on fetch. Step 02 stores positions with their original currency (EUR or USD). Step 05 passes both to ChatGPT in the same prompt — the OHLCV is in USD but the entry price shown is in EUR. For a EUR stock this makes the entry price look drastically different from the chart prices.

**Fix options:**
- Convert position entry prices to USD in step 05 before building the prompt (using the same EUR/USD rate applied in step 01).
- Or store the original currency flag per position and explicitly label each price in the prompt so ChatGPT knows which currency it is reading.

---

## ChatGPT output validation

**Problem:** Steps 06 and 07 extract recommendations (HOLD/ADD/TRIM/EXIT) and grades (A+/A/B/C/D) using regex on free-form text. If the model deviates from the expected format the result is silently empty or wrong.

**Fix options:**
- Use OpenAI structured outputs (JSON mode with a schema) so the model is forced to return a machine-readable object.
- At minimum, add a validation step that checks the extracted value is in the expected set and logs a warning with the raw response when it isn't.

---

## Historical scan storage

**Problem:** `reports/scan/latest.json` is overwritten every run. There is no record of how a stock's score changed over time or when it first appeared as A+.

**Fix:** Archive each scan result with its timestamp — either append to a JSONL file or store in SQLite. The existing `scan_<ts>.txt` files serve this purpose for human reading but aren't machine-queryable.

---

## Composite score weight tuning

Current weights (trend 20%, base 25%, RS 25%, volume 15%, breakout 15%) were chosen judgementally. Backtesting (item 1) will show which components actually predict forward returns and whether the weights should change. Until then, the weights are a hypothesis, not a validated signal.

---

## Extended stock thresholds

Currently a stock is flagged as "Extended" if `distance_to_pivot_pct > EXTENDED_DISTANCE_PCT` (8%). The breakout score penalty also kicks in at > 5%. If you find too many names being flagged, raise these:

| Constant | Current | Suggested |
|----------|---------|-----------|
| `EXTENDED_DISTANCE_PCT` | 8.0 | 10–12 |
| `BREAKOUT_SCORE_TIGHT_HIGH_PCT` (score drops at) | 5% above pivot | 8% |
| `PRICE_TOO_CLOSE_TO_HIGH_PCT` (late-stage warning) | 10% | 15% |

All three are in `config.py`.
