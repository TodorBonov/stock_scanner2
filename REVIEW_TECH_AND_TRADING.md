# Minervini SEPA Scanner – Complete Review (Tech + Trading)

**Date:** 2026-02-23  
**Scope:** Technical implementation, code quality, and trading/methodology improvements.

---

## Executive summary

The project is a well-structured Minervini SEPA scanner with a single **pipeline** (New1–New5), good config centralization, and solid documentation (README, PIPELINES.md, CALCULATIONS_REFERENCE.md). The legacy pipeline (01–07) has been removed. Critical issues (missing `openai_utils`, config model name) were fixed; the rest are improvements for maintainability, robustness, and trading edge.

---

## Part 1: Technical review

### 1.1 ~~Critical: Missing `openai_utils` module~~ (Fixed)

**Resolved:** `openai_utils.py` was added with `require_openai_api_key` and `send_to_chatgpt`. New4 and New5 import it. Legacy scripts 04, 05, 06 were removed with the legacy pipeline.

---

### 1.2 Config: OpenAI model name

**Resolved:** `OPENAI_CHATGPT_MODEL` is set to `"gpt-5.2"` (valid as of OpenAI’s Dec 2025 release). See [OpenAI models](https://platform.openai.com/docs/models). Other options include `gpt-5.2-chat-latest`, `gpt-5.2-pro`, `gpt-4o`, etc.

---

### 1.3 Data provider: possible syntax/merge error

**Issue:** In `data_provider.py`, around lines 191–198, the end of `_get_stock_info_alpha_vantage` is followed by a stray docstring fragment (`Args:`, `ticker:`, etc.) that looks like it belongs to another function. This can cause a syntax error or confusion.

**Fix:** Remove the orphaned block or attach it to the correct method (e.g. the next method that fetches historical data).

---

### 1.4 Path and cache duplication (new vs legacy)

**Issue:** Legacy pipeline uses `config.CACHE_FILE` → `data/cached_stock_data.json` and `cache_utils.load_cached_data()`. New pipeline uses hardcoded paths in each New* script (e.g. `NEW_PIPELINE_CACHE = Path("data/cached_stock_data_new_pipeline.json")`). Duplication makes it easy for paths to drift and for scripts to point at the wrong cache.

**Suggestion:** Centralize in `config.py`:

- `CACHE_FILE_LEGACY`, `CACHE_FILE_NEW`, `POSITIONS_FILE_NEW`, `NEW_PIPELINE_REPORTS_DIR`
- Have New1/New2/New3/New4/New5 import from config (and optionally from a small `paths_new_pipeline.py` if you want to keep new-pipeline paths in one place).

---

### 1.5 Error handling and logging

**Good:** Scanner returns structured error dicts (`"error": "..."`, `overall_grade: "F"`). Retries and timeouts are configured for API calls.

**Improvements:**

- **Yahoo Finance:** Rate-limit handling with backoff exists; ensure all yfinance call sites use it (e.g. in `get_historical_data`) so one rate limit doesn’t kill the whole run.
- **Logging:** Some modules use `logging.getLogger(__name__)` and others use `logger_config.get_logger(__name__)`. Standardize on one (e.g. `logger_config.get_logger`) so level and file output are consistent.
- **Fail-fast for missing inputs:** New3/New4/New5 could exit with a clear message if required input files are missing instead of proceeding with empty data.

---

### 1.6 Tests

**Good:** Pytest is in requirements; there are tests for minervini_scanner (insufficient data → F), validators, currency, cache, position suggestions, ticker utils, smoke.

**Improvements:**

- Add a test that **loads the scanner with mocked data** and runs one full checklist (e.g. one stock with enough history) and asserts on `overall_grade` and `meets_criteria` to guard against regressions in grading.
- Add a test for **benchmark_mapping** (e.g. `.DE` → `^GDAXI`, no suffix → `^GSPC` when default is US).
- Optionally add an integration test that runs New1 → New3 with a tiny watchlist and checks that prepared JSON is produced (can be slow; mark with `@pytest.mark.slow`).

---

### 1.7 Type hints and structure

**Good:** Many functions have type hints and docstrings; config is well commented.

**Improvements:**

- Use `Optional[X]` and `Dict[str, Any]` consistently for scan results and cache structures so IDEs and mypy can help.
- Consider a small `types.py` or dataclasses for “scan result”, “position”, “prepared stock” to avoid ad-hoc dicts everywhere.

---

### 1.8 Security

**Good:** `.env` and secrets are gitignored; validators limit ticker length and allowed characters; credentials are masked in logs.

**Suggestions:**

- Ensure `.env` is never logged or included in error messages.
- When writing reports, avoid dumping raw API keys or secrets into any file.

---

## Part 2: Trading review

### 2.1 Methodology alignment (Minervini SEPA)

**Strong points:**

- All five parts of the checklist are implemented (Trend & Structure, Base Quality, Relative Strength, Volume Signature, Breakout Rules).
- Grading (A+/A/B/C/F) and position sizing (Full/Half/None) match the described rules.
- CALCULATIONS_REFERENCE.md and config comments make the logic auditable.
- Per-ticker benchmark mapping (e.g. US vs EU) is correct for mixed watchlists.
- Trading-oriented options (multi-day volume confirmation, RS relax when strong, ATR stop option) are documented and configurable.

**Suggestions:**

- **Market regime:** `REQUIRE_MARKET_ABOVE_200SMA` is optional and off. Consider enabling it as a **warning** in the report (e.g. “Market below 200 SMA – consider reducing size or waiting”) rather than a hard filter, so users are aware of environment.
- **Base identification:** Base is identified with a mix of volatility and range; multiple methods are tried. Document in CALCULATIONS_REFERENCE which method was used when (e.g. “primary: low-vol % of days”) so backtests and tuning are interpretable.

---

### 2.2 Position sizing and risk

**Current:** Fixed 5% stop, 10% / 45% targets; position sizing by risk % of account (position_sizing.py) is sound.

**Suggestions:**

- **Volatility-aware sizing:** Use ATR (or base depth) so that wider bases / higher volatility suggest smaller position size or wider stop, and document it in reports (you already have `USE_ATR_STOP` and ATR in config; expose in position suggestions and New4/New5 context when possible).
- **Max position cap:** Cap position size as a % of account (e.g. no single position > 20%) to avoid over-concentration even when risk-per-trade math allows more.
- **Label currency:** In New4/05/06, always label “Entry/Stop/Target in EUR” (or USD) for each position so there’s no ambiguity (as in REVIEW_COMPLETE.md).

---

### 2.3 Data and timing

**Current:** Yahoo Finance is primary; cache is per run; 52-week high/low and SMAs are computed from cached history.

**Suggestions:**

- **Cache timestamp:** Store “data as of” (e.g. last date of OHLCV) in cache metadata and in reports so users know how stale the scan is.
- **Pre-market / delayed data:** If yfinance returns pre-market or delayed data for some tickers, consider logging a warning or flagging in the report so users don’t treat delayed data as real-time.
- **Refresh strategy:** Document when to re-run New1 (e.g. daily before market open) and when New3→New5 can be re-run on existing cache to save API cost and time.

---

### 2.4 Reporting and usability

**Good:** Summary report, detailed report, pre-breakout list, ChatGPT validation, and new-pipeline reports (existing + new positions) give a clear workflow.

**Suggestions:**

- **One-pager summary:** Add a short “today’s action” section at the top of the main report: number of A+/A, number of pre-breakout, best 3–5 tickers by grade/distance, and any “market above/below 200 SMA” line when enabled.
- **Exit rules:** Document recommended exit rules (e.g. “exit on close below 50 SMA” or “trail after +20%”) in README or a TRADING_RULES.md so the scanner output is actionable.
- **Backtest disclaimer:** Keep and possibly strengthen the disclaimer that past/scanner results do not guarantee future returns and that users should do their own research.

---

### 2.5 ChatGPT prompts and token use

**Good:** New pipeline has 6-month OHLCV option to reduce tokens; prompts are structured and ask for specific outputs (e.g. entry quality score, HOLD/ADD/TRIM/EXIT).

**Suggestions:**

- **Structured output:** Where possible, ask the model for JSON or a fixed format (e.g. “Reply with a JSON object: {\"ticker\": \"...\", \"action\": \"HOLD\"|...}”) so parsing is robust and you can reorder/rank programmatically.
- **Token logging:** You already log token usage in some scripts; ensure all ChatGPT scripts log and optionally write token usage to a small `reports/new_pipeline/token_usage_*.json` for cost tracking.

---

## Part 3: Priority action list

| Priority | Item | Effort |
|----------|------|--------|
| **P0** | Add `openai_utils.py` and fix 04 import | Small |
| ~~P0~~ | ~~Set OPENAI_CHATGPT_MODEL to valid model~~ (using gpt-5.2) | Done |
| **P1** | Fix data_provider.py orphaned docstring block | Small |
| **P1** | Centralize new-pipeline paths in config | Small |
| **P2** | Add 1–2 scanner tests with full checklist and benchmark_mapping test | Small |
| **P2** | Document “data as of” in cache and reports | Small |
| **P3** | ATR/volatility in position sizing and report labels | Medium |
| **P3** | Market regime as warning when benchmark below 200 SMA | Small |
| **P3** | One-pager summary at top of main report | Medium |

---

## References

- **Existing review:** REVIEW_COMPLETE.md (currency, trading logic, double-conversion fix).
- **Methodology:** README.md, CALCULATIONS_REFERENCE.md, PIPELINES.md.
- **Config:** config.py, pre_breakout_config.py.
