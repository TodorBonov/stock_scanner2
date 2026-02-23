# Trading212 Scanner – Complete Review

**Date:** 2026-02-20  
**Scope:** Currency conversion, trading logic, technical implementation.

---

## 1. Currency Conversion – Explicit Check

### 1.1 Design (correct)

- **Single numéraire:** All internal calculations and scan logic use **USD**. EUR is only for display and for positions held in EUR.
- **Source:** `currency_utils.py` uses Yahoo Finance `EURUSD=X`, which is **USD per 1 EUR** (e.g. 1.08 = 1 EUR = 1.08 USD). This matches standard FX convention and was verified against Yahoo/CME documentation.
- **Conversion formulas:**
  - **EUR → USD:** `amount_eur * rate` (e.g. 100 EUR × 1.08 = 108 USD) — used in `01_fetch_stock_data.py` and `05_chatgpt_validation_advanced.py` for entry/chart data.
  - **USD → EUR:** `amount_usd / rate` in `currency_utils.usd_to_eur()` — used when displaying EUR equivalents in reports.

### 1.2 Where conversion is used

| Location | What is converted | Direction | Correct? |
|----------|-------------------|-----------|----------|
| `01_fetch_stock_data.py` | OHLC + `current_price`, 52W high/low for stocks with `currency == "EUR"` | EUR → USD before cache | Yes |
| `currency_utils.usd_to_eur()` | Report display (e.g. “X EUR”) | USD → EUR | Yes |
| `05_chatgpt_validation_advanced.py` | Position entry sent to ChatGPT for EUR positions | EUR → USD | Yes |
| `05_chatgpt_validation_advanced.py` | Chart/level data for EUR positions | Only when scan is still in EUR | Fixed (see below) |

### 1.3 Bug fixed: double conversion in advanced validation

- **Issue:** For EUR positions, chart data sent to ChatGPT was always multiplied by `eur_usd_rate`. Scan results that come from the **cache** are already in USD (because 01 converts EUR→USD and sets `currency="USD"`, `original_currency="EUR"`). Multiplying again would overstate prices (e.g. 51.94 USD → 61.29 “USD”).
- **Fix (applied):** In `05_chatgpt_validation_advanced.py`, only pass `eur_to_usd_rate` into `format_chart_data_for_advanced()` when the **scan** is still in EUR: `scan_currency == "EUR"`. If the scan has `stock_info.currency == "USD"` (cached data), do not convert again.

### 1.4 Inconsistency: `03_position_suggestions.refresh_data_for_tickers()`

- **Issue:** When 03 refreshes data for tickers, it fetches and writes to the cache **without** the EUR→USD normalization that `01_fetch_stock_data.py` does. So a run that only refreshes via 05 can leave EUR-denominated prices in the cache, and downstream (02, 07) would treat them as USD.
- **Recommendation:** Reuse the same normalization block as in 01 (detect `stock_info.currency == "EUR"`, fetch `get_eur_usd_rate()`, convert OHLC and stock_info fields, set `currency="USD"` and `original_currency="EUR"`) inside `refresh_data_for_tickers()` so cache is always USD-normalized.

### 1.5 Rate freshness and fallback

- **Current:** One rate per run from Yahoo (`EURUSD=X`), 5d history Close or `regularMarketPrice`. No caching of the rate between scripts.
- **Suggestions:**
  - Log the rate and (optionally) its date in reports so you can audit “as of” when reviewing past reports.
  - If Yahoo fails, consider a fallback (e.g. another provider or last-known rate with a clear “stale rate” warning in the report).

---

## 2. Trading Perspective – Improvements

### 2.1 Position sizing and risk

- **Current:** Grades (A+, A, B, C, F) and position-size labels (Full/Half/None) are in config; position suggestions use fixed % stop (5%) and targets (10%, 45%).
- **Suggestions:**
  - Make position size depend on **volatility** (e.g. ATR-based) or base depth: tighter bases could allow slightly larger size; wider bases could suggest half-size or smaller.
  - Optionally use **ATR stop** (config has `USE_ATR_STOP`) as the primary or alternative stop and show it in position suggestions (05/06), not only in the main report.

### 2.2 Stop and target in position currency

- **Current:** 05 shows stop/targets in the same units as entry/current (T212 gives entry in position currency). So EUR positions see EUR stop/targets; no explicit “EUR” label next to the numbers when currency is EUR.
- **Suggestion:** Always label “Entry/Stop/Target in EUR” (or USD) when the position is EUR, and optionally show the EUR/USD rate in the position block so the user can mentally convert if needed.

### 2.3 Grade-based rules

- **Current:** `EXIT_ON_WEAK_GRADE_IF_LOSS` and `ALLOW_ADD_ON_STRONG_GRADE` are clear; suggestion priority is documented in config.
- **Suggestions:**
  - Consider “REDUCE” (trim) when grade drops from A to B and position is still in profit, instead of only EXIT on weak grade + loss.
  - Optional “do not add below pivot” rule: if current price is below scan pivot, suppress ADD even for strong grades (avoids adding in pullbacks).

### 2.4 Base support in suggestions

- **Current:** Base low from scan is used in 05: “Base support: X – consider exit if price breaks below base.”
- **Suggestion:** If base low is above the fixed 5% stop, consider suggesting the **tighter** of (5% stop, base low) as the “structural stop” so the report is consistent with Minervini-style structure-based exits.

### 2.5 Benchmark and region

- **Current:** Benchmark can be set per run (e.g. ^GDAXI, ^GSPC); `RS_RELAX_LINE_DECLINE_IF_STRONG` helps when a single benchmark is used for mixed regions.
- **Suggestion:** Document recommended benchmarks per region (e.g. US vs EU) and that running with a region-specific benchmark (e.g. ^GDAXI for EU names) gives more meaningful RS for those names.

---

## 3. Technical Perspective – Improvements

### 3.1 Currency

- **Double conversion:** Fixed in 07 as above.
- **05 refresh path:** Align with 01: normalize EUR→USD when writing to cache in `refresh_data_for_tickers()`.
- **Explicit currency in scan results:** Ensure `stock_info.currency` and `original_currency` are always set and persisted in `scan_results_latest.json` so 07 (and any future consumer) can reliably decide whether to convert chart data.

### 3.2 Configuration and typing

- **Config:** `config.py` is well commented; consider splitting into smaller modules (e.g. `config_api.py`, `config_minervini.py`) if it keeps growing.
- **Typing:** Add `TypedDict` or `Protocol` for “scan result” and “position” dicts so currency fields and nested `stock_info` are explicit and IDEs/linters catch misuse.

### 3.3 Rate and date in reports

- **Current:** 07 (and 05) print “EUR/USD rate (Yahoo): X.XXXX”.
- **Suggestion:** Add “Rate date: YYYY-MM-DD” (from the history index or from a dedicated rate-fetch response) so reports are auditable.

### 3.4 Error handling and robustness

- **currency_utils:** `get_eur_usd_rate()` returns `None` on failure; callers handle it. Consider logging a warning when the rate is unavailable and EUR positions exist.
- **01_fetch_stock_data:** If `currency == "EUR"` but `get_eur_usd_rate()` returns None, current code does not convert and leaves EUR in the cache; downstream then assumes USD. Consider: either skip caching that ticker and retry later, or cache with a “currency: EUR, rate_unavailable: true” and have 02/05 treat that explicitly (e.g. skip or warn).

### 3.5 Tests

- **Currency:** Add unit tests for `usd_to_eur`, `get_eur_usd_rate` (mock yfinance), and for the 01 conversion loop (EUR input → USD output, and `original_currency` set).
- **07:** Test that when `scan.stock_info.currency == "USD"` (cached), chart data is not multiplied by the rate; when `"EUR"`, it is.

### 3.6 Dependencies and environment

- **config.py:** `OPENAI_CHATGPT_MODEL = "gpt-5.2"` is valid (OpenAI GPT-5.2, Dec 2025). See platform.openai.com/docs/models.
- **yfinance:** Rate limiting and backoff are already in place in `data_provider`; same pattern could be used in `currency_utils.get_eur_usd_rate()` if you see rate limits on EURUSD=X.

---

## 4. Summary

| Area | Status | Action |
|------|--------|--------|
| EUR/USD formula and usage | Correct | None |
| Double conversion in 07 | Bug | Fixed (only convert when scan is EUR) |
| 05 refresh vs 01 normalization | Inconsistent | Normalize EUR→USD in 05 refresh |
| Rate date in reports | Missing | Add optional “rate as of” date |
| EUR position labels in 05 | Minor | Label “in EUR” for clarity |
| Position/volatility sizing | Enhancement | Consider ATR/base depth in sizing |
| Typing and tests | Enhancement | **Done** – trading_types.py, tests for currency + 07 + suggest_action |

Overall, the currency design (USD internally, EUR only at display and for T212 EUR positions) is sound. The important fix was avoiding double conversion when scan data is already in USD from cache; the next priority is aligning the 05 refresh path with 01’s EUR→USD normalization and making the rate (and its date) explicit in reports.
