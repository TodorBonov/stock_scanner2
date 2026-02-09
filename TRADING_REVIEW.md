# Complete Trading Perspective Review

This document reviews the Minervini SEPA scanner and pipeline from a **trading perspective**: methodology, entry/exit logic, risk management, strengths, and practical recommendations.

---

## 1. Methodology Overview

The system implements **Mark Minervini’s SEPA (Stock Exchange Price Action)** in five parts:

| Part | Purpose | Trading role |
|------|--------|--------------|
| **1. Trend & Structure** | Stage 2 uptrend, price above 50/150/200 SMA, within 15% of 52W high, ≥30% above 52W low | **Non-negotiable** – failure = F grade, no trade. |
| **2. Base Quality** | 3–8 week base, depth ≤25%, tight closes, volume contraction | Filters for **high-probability** consolidation before breakout. |
| **3. Relative Strength** | RS line near highs, RSI > 60, outperforming benchmark | Ensures you buy **strength**, not value. |
| **4. Volume Signature** | Dry volume in base, +40% on breakout (1.4x) | Confirms **institutional** interest. |
| **5. Breakout Rules** | Pivot clearance ≥2%, close in top 30% of range, volume ≥1.2x (multi-day allowed) | Confirms **valid breakout** day. |

**Grading:** A+ (0 failures) → Full position; A (1–2 failures) → Half position; B/C/F → Walk away or watch only. Trend & Structure failure always yields F.

**Alignment with Minervini:** The checklist and thresholds (15% from 52W high, 5% stop, 10%/45% targets, pivot +2%) are consistent with his published rules. Configurable relaxations (multi-day volume, RS relax when strong) make the scanner usable in practice without changing the core bar.

---

## 2. Entry Logic

- **Entry price:** Pivot = base high. Buy when price closes ≥2% above pivot (config: `PIVOT_CLEARANCE_PCT`, `BUY_PRICE_BUFFER_PCT`).
- **Position sizing:** Risk-based. `position_sizing.py` uses:
  - `risk_per_share = buy_price - stop_loss`
  - `shares = (account × risk_pct) / risk_per_share`
  So **total risk per trade = account × risk_pct** (e.g. 1%).
- **Stop loss:** 5% below buy (pivot). Optional ATR-based stop in report when `USE_ATR_STOP = True`.
- **Targets:** 10% (target 1, partial), 45% (target 2, then trail).

**Strength:** Clear, rule-based entry and position sizing. Risk per trade is explicit and configurable.

**Gap:** No automated order placement; entries are **manual** (scan → review → place order). Pre-breakout list helps you **watch** names before the breakout.

---

## 3. Exit & Hold Management

Handled in **05_position_suggestions.py** (Trading 212 positions + latest scan grades):

| Priority | Condition | Suggestion |
|----------|-----------|------------|
| 1 | PnL ≤ −5% (stop) | **EXIT** – cut loss |
| 2 | PnL ≥ 45% (target 2) | **REDUCE** – take more profit |
| 3 | PnL ≥ 10% (target 1) | **REDUCE** – take partial |
| 4 | Weak grade (C/F) + in loss | **EXIT** (if `EXIT_ON_WEAK_GRADE_IF_LOSS`) |
| 5 | Strong grade (A+/A) + below target 1 | **ADD** (if `ALLOW_ADD_ON_STRONG_GRADE`) |
| 6 | Else | **HOLD** |

**Strength:** Simple, repeatable rules; stop and targets aligned with scanner (5%/10%/45%). Grade-based EXIT/ADD adds a structural overlay.

**Gaps:**
- **No trailing stop:** After target 2, “trail stop” is Minervini’s rule but not coded; you must trail manually or in broker.
- **No “break of base” exit:** No automatic suggestion to exit if price breaks below base low (e.g. structure failure). You can use scan base levels (e.g. base_low from scan) manually.
- **Suggestions are advisory:** No execution; you still trade manually.

---

## 4. Data & Execution

- **Data:** Yahoo Finance (yfinance) primary; Alpha Vantage optional. Cache in `data/cached_stock_data.json`; reports show data freshness.
- **Benchmark:** Per run (`--benchmark ^GDAXI` or `^GSPC`). Per-ticker mapping in `benchmark_mapping.py` for mixed US/EU watchlists.
- **Execution:** All execution is **manual** (Trading 212 or other broker). No orders sent by the app.

**Risks:** Delayed or stale data (e.g. 15–20 min) can make pivot/breakout checks slightly lagging. For breakouts, consider using live or near-live data at entry time.

---

## 5. Current Scan Statistics (from latest summary)

From a typical run (e.g. summary_report_20260209_120556.txt):

- **Breakout Rules pass rate: 0%** – No name passes all five parts including breakout. So:
  - **A+ = 0** (no “full position” from checklist).
  - **A = 118** (1–2 failures; usually Base Quality, Relative Strength, or Breakout).
  - Most “meets criteria” names are **pre-breakout or early breakout**; you enter when price clears pivot with volume in real time.

This is **by design**: the scanner surfaces **setups** (trend + base + RS + volume); strict breakout rules keep the bar high so you confirm the actual breakout yourself (e.g. on the day price clears pivot with volume).

---

## 6. Strengths (Trading Perspective)

1. **Config-driven:** Thresholds in `config.py` / `position_suggestions_config.py` / `pre_breakout_config.py` – no need to change code for 15% vs 10% from high, 5% vs 7% stop, etc.
2. **Risk-based position sizing:** `position_sizing.py` enforces fixed risk % per trade (e.g. 1%).
3. **Multi-benchmark:** Per-ticker benchmarks for mixed watchlists; RS relax when strong avoids unfairly failing US names vs DAX.
4. **Pre-breakout list:** Focused “setup ready, not yet broken out” names, sorted by base depth, volume contraction, distance to pivot, RS.
5. **Optional ATR stop and market regime:** Useful for volatile names and for filtering in weak markets (`REQUIRE_MARKET_ABOVE_200SMA`).
6. **Clear R/R:** 5% stop vs 10% first target = 2:1; 45% second target for letting winners run.
7. **Position suggestions:** Ties scan grades to existing positions (EXIT/REDUCE/HOLD/ADD) for consistency with the same methodology.

---

## 7. Risks & Gaps

| Risk / gap | Impact | Mitigation |
|------------|--------|------------|
| **Breakout Rules 0% pass** | No A+ from full checklist; all “meets criteria” are A (1–2 failures). | Use scanner for **setup** list; enter **manually** on pivot clearance + volume. Consider optional relax (e.g. 1.5% clearance or 21-day lookback for “recent breakout”) if you want more names to pass in report. |
| **No trailing stop logic** | After 45%, no system suggestion to trail. | Trail manually (e.g. below 10 SMA or % off high) or in broker. |
| **No “break of base” exit** | No automatic “exit if below base low”. | Manually compare current price to base_low from scan; exit if structure breaks. |
| **Data delay** | Entry/exit decisions on cached data can lag. | Run pipeline regularly; at entry, confirm pivot/volume on live or near-live data. |
| **Concentration** | No built-in limit on positions per sector or total. | Manually cap number of positions and sector exposure. |
| **No backtesting** | No historical hit rate or expectancy. | Use scan for screening only; track your own results or add a separate backtest module. |
| **ChatGPT model** | `OPENAI_CHATGPT_MODEL = "gpt-5.2"` may not exist; could be typo for gpt-4o or similar. | Set in `config.py` to a valid model name. |

---

## 8. Recommendations

**Immediate (no code):**
- Use **A-grade + pre-breakout** as watchlist; **enter only** when price clears pivot (≥2%) with volume in real time.
- Run **position_sizing.py --account X --risk-pct 1 --from-scan** before adding; never size by “full/half” alone – always by risk %.
- For existing positions, run **05_position_suggestions.py** (with Trading 212 API) and respect stop (EXIT at −5%) and targets (REDUCE at 10%/45%).
- Set **REQUIRE_MARKET_ABOVE_200SMA = True** occasionally to see market regime; consider reducing size or skipping new breakouts when market is below 200 SMA.

**Optional (config):**
- If you want more names to “pass” breakout in the report: slightly increase `BREAKOUT_LOOKBACK_DAYS` (e.g. 10) or `VOLUME_CONFIRMATION_DAYS_AFTER_BREAKOUT` (e.g. 3); keep in mind this relaxes the bar.
- For volatile names, enable **USE_ATR_STOP** and use ATR-based level as a reference (wider stop than 5% if ATR is large).

**Future (code):**
- **Trailing stop suggestion:** After target 2, suggest a trailing level (e.g. X% below recent high or below 10 SMA) in position suggestions.
- **Break-of-base exit:** In position suggestions, if scan has base_low and current price &lt; base_low, suggest EXIT (structure broken).
- **Backtest module:** Run scanner logic on historical dates to estimate pass rates and, if desired, hypothetical returns (out of scope of current pipeline).

---

## 9. Summary Table

| Aspect | Status | Notes |
|--------|--------|-------|
| Methodology | ✅ Aligned | Minervini SEPA; configurable relaxations |
| Entry | ✅ Clear | Pivot + 2%, risk-based size |
| Stop / targets | ✅ Defined | 5% stop, 10% / 45% targets |
| Position sizing | ✅ Risk-based | `position_sizing.py` |
| Exit rules | ✅ Implemented | EXIT/REDUCE/HOLD/ADD in 05 |
| Trailing stop | ⚠️ Manual | Not in code |
| Break-of-base exit | ⚠️ Missing | Manual vs base_low |
| Data freshness | ⚠️ Cache-dependent | Run fetch regularly |
| Execution | Manual | No orders sent |
| Backtesting | ❌ None | Screen only |

**Verdict:** The system is **suitable for discretionary swing trading** using Minervini-style breakouts: it screens and grades setups, suggests position size and hold actions, and leaves execution and trailing to you. Use it as a **screening and risk-sizing tool**, not as a fully automated trading system.

---

*Review based on codebase as of the date of this document. For calculation details see CALCULATIONS_REFERENCE.md; for rationale of relaxations see TRADING_IMPROVEMENTS_RATIONALE.md.*
