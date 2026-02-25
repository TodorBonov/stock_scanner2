# Why the Top Candidates Are "Already Grown" (and how to find them earlier)

## The feeling

You see stocks at the top of the report **after** they’ve already had a big move. You’d like to find them **before** they explode.

That’s not a bug – it’s how the current scoring and ranking are built.

---

## Why the scanner favors "already grown" names

### 1. **Composite score rewards “already strong”**

The composite is a weighted sum of:

| Component | Weight | What pushes the score up |
|-----------|--------|---------------------------|
| **Trend** | 20% | Price **already** well above 200 MA (≥30% above = 100) |
| **Base** | 25% | Good base **after** an advance (prior run ≥25%) |
| **RS** | 25% | **Already** in the top of the universe (3M return percentile) |
| **Volume** | 15% | Dry base / expansion (supporting “already working” move) |
| **Breakout** | 15% | Close to or above pivot (ready/triggered) |

So the **highest composite** = already in an uptrend, already had a prior run, already strong RS, good base, near breakout. By design, the very top names are the ones that have **already** done a lot of the work.

### 2. **RS percentile = “already outperformed”**

RS is **3‑month return percentile** vs your universe. So:

- **RS 95** = that stock was one of the **best performers** over the last 3 months.
- To get A+ you need RS %ile ≥ 80.

So the top grades are literally the names that have **already** had strong 3M performance. You’re sorting by “who already ran,” not “who is starting to run.”

### 3. **Prior run requirement**

You require **≥25% advance** before the base. So you only look at stocks that have **already** had a meaningful run, then consolidated. That’s great for “buy the breakout of a rest after a run,” but it excludes **first base off the bottom** or very early setups.

### 4. **Ranking = sort by composite**

The report sorts by **composite score descending**. So the first page is always “maximum composite” = maximum “already trend + already base + already RS + near breakout.” That’s exactly the “already grown” slice.

---

## What would surface names *before* they expand

To get a list of **early** or **building** candidates (before the big expansion), you need a different slice and/or a different sort.

### Option A: **“Early candidates” section in the report**

Define “early” as:

- **Not yet extended** – e.g. trend score 40–70 (about 5–20% above 200 MA), not 100.
- **Building RS** – e.g. RS percentile **50–80** (improving but not already top decile).
- **Good setup** – base quality OK, near pivot (e.g. distance −5% to 0%).
- **Grade B or better** – so the setup is still valid.

Then in the report:

- Add a section **“Early candidates (before extension)”**.
- Fill it with eligible names that pass the above filters.
- Sort by e.g. **distance to pivot** (closest first) or **power_rank**, so you see “best setup among the not-yet-extended” names.

That list is biased toward **before they expand** instead of **after they’ve grown**.

### Option B: **Alternative ranking in the main table**

Keep the current table as “best composite,” but add a **second table** (or CSV) that ranks by something like:

- **Power rank** (0.5×RS %ile + 0.5×prior_run), or  
- **Distance to pivot** (closest first), or  
- **Custom “early score”** = base_score + breakout_score + (100 − trend_score) so that “not yet extended” gets a boost.

Then you can scan the “early” list for names that aren’t yet at the top of the composite list.

### Option C: **Loosen “prior run” for an early watchlist**

If you want to see **first base** or **early base** (before a 25%+ run), you could:

- Add a separate run or filter where **prior run &lt; 25%** is **allowed** (e.g. not a hard REJECT), and
- Label those as “Early / first base” and rank them separately (e.g. by base quality + RS + distance to pivot).

That would surface names that haven’t yet had the “required” prior run and are more “before they expand.”

---

## Summary

| Reason | Why it favors “already grown” |
|--------|-------------------------------|
| Composite weights | High trend + high RS + good base + near breakout = already moved |
| RS = 3M percentile | Top RS = already top performers over 3 months |
| Prior run ≥25% | Only bases **after** a meaningful advance |
| Sort by composite | Top of list = maximum “already strong” |

To find names **before** they expand, add an **“Early candidates”** view (filter: not extended, RS 50–80, good base, near pivot; sort by distance to pivot or power_rank) or an alternative ranking that rewards “building” rather than “already best.”

If you want, the next step is to implement the **“Early candidates”** section in the V2 report (and optionally a small config for the thresholds).
