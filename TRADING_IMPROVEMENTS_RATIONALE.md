# Why the Trading Improvements Were Made

This document explains the **reasons** behind the configurable trading improvements in the Minervini SEPA scanner. The changes keep the core checklist intact but make the scanner more usable for real-world trading. All behaviour is controlled by options in `config.py` so you can tune or disable it without code changes.

---

## 1. Multi-Day Volume Confirmation (Breakout Rules)

### Problem

The original logic required **all three** of the following on the **same day**:
- Price closes ≥ 2% above base high (pivot clearance).
- Close in the top 30% of that day’s range.
- Volume ≥ 1.2× (or 1.4×) the 20-day average.

In real breakouts, volume often **follows** the price move: the first day clears the pivot with a strong close, and volume spikes on that day or the next 1–2 days. Requiring volume on the exact same day produced a **0% breakout pass rate** in scans, so no stock was ever labelled “in breakout” even when the move was valid.

### Change

- **`USE_MULTI_DAY_VOLUME_CONFIRMATION`** (default True): When True, volume confirmation can occur on the **breakout day** or on any of the **next N days** (within the same lookback window).
- **`VOLUME_CONFIRMATION_DAYS_AFTER_BREAKOUT`** (default 2): Number of days after the breakout day to look for volume ≥ `VOLUME_EXPANSION_MIN`. So we still require one clear “breakout day” (pivot clearance + strong close), but we allow volume to confirm on that day or on the next 1–2 days.

### Rationale

- Aligns with how breakouts often unfold (price leads, volume can follow).
- Still enforces pivot clearance and strong close on a single day, so the “breakout day” is well defined.
- Remains Minervini-consistent (he emphasises volume confirmation, not necessarily same-day only).
- **Configurable:** Set `VOLUME_CONFIRMATION_DAYS_AFTER_BREAKOUT = 0` to restore strict same-day-only behaviour.

---

## 2. Relax RS Line Decline When Stock Is Strong (Relative Strength)

### Problem

Relative strength is measured against a **single benchmark** per run (e.g. DAX `^GDAXI`). Many watchlists include US or other non-EU names. Those names can be strong in absolute terms (RSI > 60, strong price trend) and outperform their **own** market (e.g. S&P 500), but look weak vs DAX. The scanner was failing them on “RS line declining from recent high” even when they were strong stocks, which:
- Skewed the A-grade list toward names that happen to beat DAX.
- Pushed otherwise good US (or other region) names out of the “meets criteria” set.

### Change

- **`RS_RELAX_LINE_DECLINE_IF_STRONG`** (default True): When the stock **outperforms** the benchmark **and** RSI ≥ 60, we **do not** add a failure for “RS line X% below recent high”. So if the stock is strong (outperforming + RSI above threshold), a decline in the RS line from its recent high is not treated as a fail.

### Rationale

- Keeps the bar high (outperformance + RSI ≥ 60) so we only relax when the stock is clearly strong.
- Avoids penalising strong US (or other region) names when the run uses a single EU benchmark.
- You can still use a region-appropriate benchmark via script args (e.g. `--benchmark ^GSPC` for US); the relax option helps when you use a **single** benchmark for a mixed watchlist.
- **Configurable:** Set `RS_RELAX_LINE_DECLINE_IF_STRONG = False` to restore strict RS-line behaviour.

---

## 3. Benchmark Set Per Run (Not in Config)

### Why It’s Done This Way

The benchmark (e.g. `^GDAXI`, `^GSPC`) is passed into the scanner when the pipeline runs (e.g. `02_generate_full_report.py --benchmark ^GDAXI`). It is **not** stored in `config.py` so that:
- You can run the same code for different markets (e.g. one run with DAX, another with S&P 500) without editing config.
- Scripts (01, 02) already support `--benchmark`; the rationale doc only explains why “one benchmark for everyone” is limiting and why we added the RS relax option and per-run benchmark choice.

---

## 4. Pre-Breakout Search (Part 2 of MINERVINI_LOGIC_IMPROVEMENTS)

### Why a Dedicated “Pre-Breakout” View

The five-part checklist plus grading already produce “Best Setups” (A-grade names). The **pre-breakout** view is an extra **search** layer:

- **Filter:** Grade ≥ B, has pivot, **not** yet broken out (no close ≥ 2% above base high in last 5 days), and within X% **below** pivot.
- **Sort:** Same as Best Setups (base depth, volume contraction, distance to pivot, RS).

So you get:
- **Best Setups:** Best A-grade names (some may already be in breakout).
- **Pre-Breakout:** Names that are “setup ready” but still **below** the pivot, so you can watch for the breakout.

This doesn’t change Minervini logic; it only defines which scan results are shown together and how they’re ranked. All pre-breakout parameters are in `pre_breakout_config.py` so the main checklist config stays clean.

---

## 5. Summary Table

| Improvement | Config / Where | Why |
|-------------|----------------|-----|
| Multi-day volume confirmation | `USE_MULTI_DAY_VOLUME_CONFIRMATION`, `VOLUME_CONFIRMATION_DAYS_AFTER_BREAKOUT` in config.py | Same-day volume gave 0% breakout pass rate; volume often confirms 1–2 days after pivot clearance. |
| RS relax when strong | `RS_RELAX_LINE_DECLINE_IF_STRONG` in config.py | Single benchmark (e.g. DAX) unfairly fails strong US/other-region names; when outperforming + RSI ≥ 60 we don’t fail on RS line decline. |
| Benchmark per run | Script args (e.g. `--benchmark ^GSPC`) | Lets you choose region without editing config. |
| Pre-breakout view | pre_breakout_config.py | Focused list of “setup ready, not yet broken out” names, ranked like Best Setups. |

All of the above are **configurable** or **optional**: you can turn multi-day volume off, turn RS relax off, and use or ignore the pre-breakout section. The core Minervini checklist (trend, base, RS, volume, breakout) and grading logic are unchanged except where explicitly relaxed by these options.
