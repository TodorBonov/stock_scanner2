# Trading212 Scanner – Flow (Legacy pipeline)

This document describes the **legacy pipeline** (scripts 01–07): data flow, data stores, and currency handling. The **new pipeline** (New1–New5) is the default on **main**; see **README.md** and **PIPELINES.md** for run order and branch strategy. The legacy pipeline is preserved on branch **pipeline/legacy-01-07**.

---

## 1. Pipeline overview (legacy 01–07)

```
watchlist.txt
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  01_fetch_stock_data.py                                                      │
│  • Load tickers from watchlist.txt                                           │
│  • For each: Yahoo (or Alpha Vantage) → OHLC + stock_info                   │
│  • If stock currency == EUR: convert to USD (get_eur_usd_rate), store as USD  │
│  • Write: data/cached_stock_data.json                                        │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
   data/cached_stock_data.json   (all prices in USD; original_currency set for EUR names)
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  02_generate_full_report.py                                                  │
│  • Load cache → CachedDataProvider                                           │
│  • MinerviniScanner scans each stock (trend, base, RS, volume, breakout)     │
│  • Grades (A+/A/B/C/F), pivot, buy/sell levels, pre-breakout list             │
│  • Write: reports/summary_report_*.txt, detailed_*.txt                       │
│  • Write: reports/scan_results_latest.json  (for 03, 04, 05, 06)            │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
   reports/scan_results_latest.json
      │
      ├─────────────────────────────────────────────────────────────────────────┐
      │                                                                         │
      ▼                                                                         ▼
┌──────────────────────────────┐    ┌──────────────────────────────────────────┐
│  04_chatgpt_validation.py    │    │  03_position_suggestions.py               │
│  • Load scan_results_latest  │    │  • T212 API → open positions             │
│  • Send A/B (and pre-breakout)│    │  • Load grades, base_low, pivot from     │
│    to ChatGPT for validation │    │    scan_results_latest                    │
│  • Write: summary_Chat_GPT   │    │  • suggest_action(entry, current, grade,│
│    _*.txt                    │    │    pivot) → EXIT/REDUCE/HOLD/ADD         │
└──────────────────────────────┘    │  • EUR: get rate+date, label "in EUR",   │
                                    │    structural stop (max(5% stop, base_low))│
                                    │  • Write: position_suggestions_*.txt      │
                                    └──────────────────────────────────────────┘
      │                                                                         │
      ▼                                                                         ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  05_chatgpt_validation_advanced.py                                            │
│  • Positions (from T212 API or report) + A+/A from scan_results               │
│  • For each: build chart/level text; for EUR positions convert entry to USD   │
│    for the prompt; chart data only converted if scan still in EUR (no double) │
│  • Send to ChatGPT (institutional analysis)                                   │
│  • Write: summary_Chat_GPT_advanced_*.txt (with EUR conversion note per pos)  │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Optional / support**

- **07_retry_failed_stocks.py** – Reads cache, retries tickers that failed in 01, updates cache.
- **03 --refresh-tickers** – Refreshes cache and scan for position tickers only (same EUR→USD logic as 01).
- **06_chatgpt_position_suggestions.py** – Reads latest `position_suggestions_*.txt`, sends to ChatGPT, writes `position_suggestions_Chat_GPT_*.txt`.

---

## 2. Data stores

| Store | Path | Written by | Read by |
|-------|------|------------|---------|
| Watchlist | `watchlist.txt` | You | 01 |
| Cache | `data/cached_stock_data.json` | 01, 07, 03 (refresh) | 02, 03, 04, 07 (refresh) |
| Scan results | `reports/scan_results_latest.json` | 02, 03 (refresh) | 03, 04, 05, 06 |
| Summary report | `reports/summary_report_*.txt` | 02 | You |
| Position suggestions | `reports/position_suggestions_*.txt` | 03 | 06, You |
| ChatGPT reports | `reports/summary_Chat_GPT*.txt`, `summary_Chat_GPT_advanced_*.txt` | 04, 05 | You |

---

## 3. Currency flow

**Principle: one numéraire (USD) everywhere except at display and at the T212 position boundary.**

1. **Source (Yahoo / Alpha Vantage)**  
   Prices can be in USD (e.g. US tickers) or EUR (e.g. RWE.DE). `stock_info["currency"]` says which.

2. **01_fetch_stock_data (and 03 refresh)**  
   - If `stock_info["currency"] == "EUR"`:
     - Fetch `get_eur_usd_rate()` (Yahoo `EURUSD=X` = USD per 1 EUR).
     - Multiply OHLC and `current_price` / 52W high/low by that rate → store **USD** in cache.
     - Set `stock_info["currency"] = "USD"`, `stock_info["original_currency"] = "EUR"`.
     - If rate is missing: set `original_currency = "EUR"`, `rate_unavailable = True`, leave data in EUR and log a warning.

3. **02, 03, 04 (scan / grades / pivots)**  
   They only see the cache and/or `scan_results_latest.json`. All numbers there are **USD** (for names that were converted). No extra conversion.

4. **T212 positions**  
   Positions are in **position currency** (EUR or USD). Entry/current from the API are in that currency.

5. **03_position_suggestions**  
   - Fetches EUR/USD rate (and date) only if there is at least one EUR position.
   - Shows entry, stop, targets in **position currency** and labels them “(in EUR)” when currency is EUR; prints “EUR/USD rate: X.XXXX” and “Rate date: YYYY-MM-DD” in the report.

6. **05_chatgpt_validation_advanced**  
   - Needs one currency for the model: **USD**.
   - For **EUR positions**:  
     - Convert **entry** (and current) to USD with the same rate for the prompt.  
     - For **chart/level data**: only convert if the **scan** is still in EUR (`stock_info.currency == "EUR"`). If the scan came from cache it is already USD → no conversion (avoids double conversion).  
   - Report header: “EUR/USD rate (Yahoo): X.XXXX” and “Rate date: YYYY-MM-DD”.  
   - At the end of each EUR position block: “Converted to EUR (1 EUR = X.XXXX USD)” and entry/current in EUR.

7. **Display only (USD → EUR)**  
   When we want to show an amount in EUR (e.g. in a report), we use `currency_utils.usd_to_eur(amount_usd, rate)` (i.e. divide by the “USD per 1 EUR” rate). Used only for human-readable output, not for calculations.

---

## 4. Position-suggestion flow (03)

1. Get open positions from Trading 212 API (ticker, entry, current, currency, etc.).
2. Optionally `--refresh-tickers`: for each position ticker, refresh cache + re-scan and merge into `scan_results_latest.json` (with same EUR→USD rules as 01).
3. Load from `scan_results_latest.json`: grades, base lows, pivots (pivot = `buy_sell_prices.pivot_price` or `base_quality.details.base_high`).
4. For each position:  
   `suggest_action(entry, current, pnl_pct, grade, pivot)`  
   - Stop loss → EXIT  
   - Profit target 2/1 → REDUCE  
   - Weak grade + loss → EXIT  
   - Grade B + profit → REDUCE (if `REDUCE_ON_GRADE_B_IN_PROFIT`)  
   - Strong grade + below target 1: ADD only if current ≥ pivot (if `DO_NOT_ADD_BELOW_PIVOT`); else HOLD  
   - Otherwise → HOLD  
5. Report: for each position, show suggestion, structural stop (max(5% stop, base_low)), targets, and for EUR positions the “(in EUR)” labels and EUR/USD rate/date.

---

## 5. Script order (typical run, legacy pipeline)

Use this order when on branch **pipeline/legacy-01-07** (or when running the legacy flow from main).

1. **01_fetch_stock_data.py** – Refresh cache from watchlist.  
2. **02_generate_full_report.py** – Scan cache → summary + detailed reports + `scan_results_latest.json`.  
3. **03_position_suggestions.py** – Positions + scan results → EXIT/REDUCE/HOLD/ADD and structural stops.  
4. **04_chatgpt_validation.py** and/or **05_chatgpt_validation_advanced.py** – Send scan (and positions in 05) to ChatGPT; get validation/advanced reports.  
5. Optionally **06_chatgpt_position_suggestions.py** – Send latest position suggestions report to ChatGPT for extra commentary.

If you only change the watchlist, run 01 then 02. If you only want position suggestions, run 03 (optionally with `--refresh-tickers`). 05 needs 02 to have been run so that `scan_results_latest.json` exists and contains grades/pivots for your position tickers.
