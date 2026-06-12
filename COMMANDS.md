# Commands — by flow

Quick reference for running the scanner the way it's intended. Commands use `python`
(use `py` instead if that's how Python is on your PATH). Run them from the repo root.

---

## 0. One-time setup

```powershell
pip install -r requirements.txt
Copy-Item .env.example .env      # then edit .env and fill in your keys
```

`.env` keys (all optional except where a step needs them):
- `OPENAI_API_KEY` — required for the AI steps (06, 07)
- `TRADING212_API_KEY` / `TRADING212_API_SECRET` — required for step 02 (your portfolio)
- `ALPHA_VANTAGE_API_KEY` — optional fallback data source

---

## Flow 1 + 2 — Fetch all data, then math scan (everyday run, no AI)

This fetches OHLCV for your whole watchlist **and** your Trading212 positions, then runs the
deterministic Minervini V2 scanner. No tokens spent.

```powershell
# Normal run (reuses cached Yahoo data)
python run_pipeline.py --no-ai

# Fresh data from Yahoo — also refetches OHLCV for portfolio tickers that
# aren't in the watchlist. Use this on the FIRST run and whenever you want current data.
python run_pipeline.py --no-ai --refresh

# Also write a CSV summary of the scan
python run_pipeline.py --no-ai --csv
```

Result: `reports/scan/latest.json`, `reports/scan/scan_<timestamp>.txt`, and `docs/index.html`.

---

## Flow 3 — Run through AI as well (rare)

Same as above but also runs the two ChatGPT steps. **Costs OpenAI tokens** and needs
`OPENAI_API_KEY`. Use sparingly.

```powershell
# Full pipeline incl. both AI steps
python run_pipeline.py

# Full pipeline, fresh data
python run_pipeline.py --refresh

# Only review my holdings with AI (skip candidate ranking)
python run_pipeline.py --exclude-07

# Only rank new candidates with AI (skip holdings review)
python run_pipeline.py --exclude-06
```

Result (in addition to the scan files): `reports/ai/holdings_<ts>.txt`,
`reports/ai/candidates_<ts>.txt`.

---

## Flow 4 — Test flow (small watchlist)

`watchlist_test.csv` is a 6-ticker list for quick, cheap runs.

```powershell
# Fast math-only test on the short list (recommended for testing)
python run_pipeline.py --watchlist watchlist_test.csv --no-ai --refresh

# Short list including the AI steps (still costs a few tokens)
python run_pipeline.py --watchlist watchlist_test.csv --refresh
```

Unit tests (no network, no tokens):

```powershell
python -m pytest -q
```

---

## Running individual steps (debugging / advanced)

The steps must run in order because each reads the previous step's output.

```powershell
python 01_fetch_prices.py --watchlist watchlist.csv [--refresh]   # OHLCV -> data/cached_stock_data_new_pipeline.json
python 02_fetch_positions.py [--refresh]                          # positions (+OHLCV with --refresh)
python 03_prepare_data.py --watchlist watchlist.csv               # -> data/prepared_for_minervini.json
python 04_scan.py [--csv] [--benchmark ^GSPC]                     # -> reports/scan/latest.json + report
python 05_prep_ai_data.py --watchlist watchlist.csv               # -> reports/data/ai_*_input.json
python 06_analyze_holdings.py [--limit N] [--model MODEL]         # -> reports/ai/holdings_<ts>.txt
python 07_rank_candidates.py [--limit N] [--max-rank N]           # -> reports/ai/candidates_<ts>.txt
```

Scan a single name or a few (needs steps 01 + 03 to have run first so the cache exists):

```powershell
python 04_scan.py --ticker AAPL
python 04_scan.py --tickers AAPL,MSFT,NVDA
```

---

## Where everything lands

| Path | Written by | Contents |
|------|-----------|----------|
| `data/cached_stock_data_new_pipeline.json` | 01 (02 `--refresh`) | OHLCV cache (all prices normalized to USD) |
| `data/positions_new_pipeline.json` | 02 | Your Trading212 positions |
| `data/prepared_for_minervini.json` | 03 | Merged input for the scanner |
| `reports/problems_with_tickers.txt` | 03 | Tickers that couldn't be mapped / lacked data |
| `reports/scan/latest.json` | 04 | Machine-readable scan results (source of truth) |
| `reports/scan/scan_<ts>.txt` | 04 | Human-readable scan report |
| `reports/scan/scan_summary_<ts>.csv` | 04 `--csv` | CSV summary |
| `reports/scan/history.jsonl` | 04 | One row per ticker per run (history) |
| `reports/ai/holdings_<ts>.txt` | 06 | AI review of your holdings |
| `reports/ai/candidates_<ts>.txt` | 07 | AI ranking of new candidates |
| `docs/index.html` | 04 | Live HTML rank table |

---

## Notes

- **First run / new portfolio tickers:** use `--refresh`. Without it, a holding that isn't in
  your watchlist has no cached price history, so step 06 reviews it without OHLCV. The simplest
  guarantee of full coverage is to also keep your portfolio tickers in `watchlist.csv`.
- **Cost control:** the deterministic scan (steps 01–05) never calls an LLM. Only 06/07 spend
  tokens — `--no-ai` is the routine mode; drop it only when you want the AI pass.
- **Currencies:** all OHLCV is normalized to USD at fetch time (incl. London `.L` pence), so the
  scanner's price/liquidity thresholds and the rank table compare like-for-like.
