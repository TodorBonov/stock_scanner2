# Scripts & Config — Quick Reference

**One command to run everything:** `python run_pipeline.py`

---

## Pipeline scripts

| Script | Step | Role |
|--------|------|------|
| `01_fetch_prices.py` | 01 | Fetch and cache Yahoo OHLCV for every ticker in the watchlist |
| `02_fetch_positions.py` | 02 | Fetch your open positions from Trading212 |
| `03_prepare_data.py` | 03 | Merge cache + positions + watchlist into a single prepared file |
| `04_scan.py` | 04 | Run the SEPA scorer → grades, scores, report |
| `05_prep_ai_data.py` | 05 | Extract A+/A stocks and holdings and format them for AI |
| `06_analyze_holdings.py` | 06 | ChatGPT review of your existing holdings |
| `07_rank_candidates.py` | 07 | ChatGPT ranking of new entry candidates |

---

## Scanner engine

| File | Role |
|------|------|
| `sepa_checklist.py` | 5-part Minervini checklist — pure pass/fail for each criterion |
| `sepa_scorer.py` | Takes checklist results → composite score (0–100) → grade (A+/A/B/C/REJECT) |
| `sepa_report.py` | Formats scan results into human-readable `.txt` and optional CSV |
| `sepa_web_export.py` | Generates `docs/index.html` — sortable HTML rank table |

---

## Config

| File | Used by | What it controls |
|------|---------|-----------------|
| `config.py` | Everything | API keys, file paths, all scanner thresholds, scoring weights, grade bands, ATR settings, OpenAI model |
| `logger_config.py` | All scripts | Logging setup only |

**One config for everything.** All scanner thresholds (SMA periods, base depth, RS, volume, grading bands) and all paths live in `config.py`.

---

## Reports

| Path | What ends up there |
|------|--------------------|
| `reports/scan/scan_<ts>.txt` | Human-readable SEPA scan report per run |
| `reports/scan/latest.json` | Machine-readable scan output (input to step 05) — overwritten each run |
| `reports/ai/holdings_<ts>.txt` | ChatGPT review of existing holdings (step 06) |
| `reports/ai/candidates_<ts>.txt` | ChatGPT ranking of new candidates (step 07) |
| `reports/data/` | Intermediate JSON prepared for steps 06/07 — regenerated each run, gitignored |
| `reports/problems_with_tickers.txt` | Tickers with data issues — check here if a stock is missing |

---

## Watchlist files

| File | Purpose |
|------|---------|
| `watchlist.csv` | Main watchlist — columns: `type, yahoo_symbol, trading212_symbol, benchmark_index` |
| `watchlist_test.csv` | Short list for quick test runs. Same format. |

---

## Old pipeline

The original pipeline (before scoring and grading) is archived on branch **`pipeline-v1`**. Nothing from that branch is needed on `main`.
