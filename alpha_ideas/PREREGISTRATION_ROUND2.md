# Round 2 pre-registration: Gotobi (6J) and Gold Asia-vs-New York (GC)

Written 2026-10-03, about 13:50 ET, **before any 6J or GC data was downloaded.** The file's mtime is the authority on
timing. The ideas come from `IDEA_LIST_DATABENTO.md` (#1 and #2). Ian approved running both ("go ahead, backtest #1
and #2").

Each test has **one primary statistic**, and that statistic decides the verdict. Everything marked robustness or
descriptive is reported but cannot rescue a failed primary. No parameter here may change after results are seen. If an
ambiguity forces a choice during implementation, the choice and its reason go in that idea's `results.md` before the
single run. These add **2 primary tests** to the count the repo must disclose.

## Shared conventions
- **Data:** Databento GLBX.MDP3 `ohlcv-1h`, `stype_in="continuous"`, from 2010-06-06 to 2026-10-01 (end exclusive).
  - 6J: `6J.v.0` only, about $0.95. GC: `GC.v.0` only, about $0.97.
  - Fetched through `gqh.data.databento` in calendar-year chunks, using the repo cache and cost guard.
  - Abort if the quoted total exceeds $2.50.
- **Bars:** `ts_event` is the bar's **start**. A bar's OPEN is its first trade in the hour and its CLOSE is its last.
  - Each window is entered at the OPEN of its first bar and exited at the CLOSE of its last bar, so both prices are
    trades that really happened. A missing bar removes that window; there is no filling.
- **Rolls:** a window counts only if its first and last bar have the same `instrument_id`. Windows that span a `.v.0`
  contract switch are dropped and counted.
- **Returns:** log returns in bp of the quoted price.
- **Costs per round trip (RT):** 1 tick + $2.50 per side, as a fraction of notional on that day:
  `cost_bp = (tick + 5/multiplier) / price × 1e4`.
  - 6J: multiplier 12,500,000. The tick is 0.0000005 in any calendar year where prices on the half-tick grid
    (odd multiples of 0.0000005) appear in the data; otherwise 0.000001.
  - GC: multiplier 100 oz, tick 0.10.
  - "Doubled costs" multiplies the whole `cost_bp`.
- **Pass bar:**
  - **PASS** = the primary statistic is in the predicted direction with t ≥ 2.0, **and** the trade's mean net P&L is
    above 0 at base costs **and** at doubled costs.
  - If it holds at base costs but not at doubled costs, the verdict is **WEAK PASS (cost-fragile)**.
  - Anything else is **FAIL**.
  - Given about 1,900 earlier tests in this repo, t ≥ 3 is what "convincing" means.
- **Samples reported:**
  - full sample, which decides the verdict
  - in-sample to 2024-09-30
  - hackathon out-of-sample 2024-10-01 → 2026-09-30 (the most recent 2 years)
  - every calendar year
- **Units:** one observation per day; plain t-stats, with Newey-West (5 lags) also shown.

---

## Test 1: Gotobi (Tokyo 9:55 fixing) in yen futures  (`alpha_ideas/gotobi/`)

**Hypothesis.** On gotobi days, Japanese importers' must-pay dollar purchases at the 9:55 JST fixing push USD/JPY up
into the fix, and it falls back afterwards. 6J is quoted in USD per JPY, so the USD/JPY log return is −ln(P_end/P_start).

- **Tokyo business days:**
  - weekdays that are not Japanese national holidays (python `holidays`, country JP, which includes substitute and
    citizens' holidays) and not Dec 31 or Jan 1–3 (bank holidays);
  - non-business days are excluded completely;
  - **primary sample: Tuesday–Friday** (as in Bessho, Sugimoto & Suzuki 2023). Mondays are reported separately.
- **Gotobi days:**
  - nominal dates are the 5th, 10th, 15th, 20th, 25th, 30th and the last calendar day of the month;
  - a nominal date that isn't a Tokyo business day moves to the **previous** Tokyo business day;
  - the gotobi set is the resulting unique business days. All other Tokyo business days are controls.
- **Windows** (UTC; Japan has no daylight saving, so JST = UTC+9 always):
  - Pre-fix: OPEN of the bar starting 23:00 UTC on the previous calendar day → CLOSE of the bar starting 00:00 UTC.
    That is 08:00 → 10:00 JST, and contains the 9:55 fix.
  - Post-fix: OPEN of the bar starting 01:00 UTC → CLOSE of the bar starting 02:00 UTC. That is 10:00 → 12:00 JST.
  - Known bias, against the hypothesis: the drop right after 9:55 falls inside the pre-fix bar.
- **Daily statistic:** S(d) = r_pre(d) − r_post(d), in USD/JPY bp. A day needs both windows to be valid.
- **PRIMARY:**
  - Statistic: D = mean S over gotobi days − mean S over control days (Tue–Fri, full sample), with a Welch t-stat.
  - Prediction: D > 0.
- **Trade (gotobi days only):**
  - Leg 1: short one 6J over the pre-fix window (long USD).
  - Leg 2: long one 6J over the post-fix window (short USD).
  - Net P&L(d) = S(d) − cost_bp(pre) − cost_bp(post).
  - Report: mean, t, hit rate, annualized Sharpe (mean/std × √(gotobi days per year)), and the same with costs doubled.
- **Robustness and descriptive (reported only):**
  - each leg separately (gotobi vs control);
  - month-end gotobi vs the 5/10/…/25 dates;
  - March (Japanese fiscal year-end);
  - Monday-only;
  - the "next business day" holiday rule;
  - nominal dates only (no holiday shift);
  - excluding Japan MoF intervention days (2010-09-15, 2011-03-18, 2011-08-04, 2011-10-31, 2022-09-22,
    2022-10-21, 2022-10-24, 2024-04-29, 2024-05-01, 2024-07-11, 2024-07-12; each date ±1 Tokyo business day);
  - 1%/99% winsorized means;
  - average USD/JPY path by UTC hour (20:00 → 05:00) on gotobi vs control days;
  - sub-periods 2010–2017, 2018–2020 (the paper's years) and 2021–2026 (new).

---

## Test 2: Gold "Asia buys, New York sells" with a China-holiday placebo  (`alpha_ideas/gold_clock/`)

**Hypothesis.** Gold's price is pushed by different buyers in different time zones. Asian physical, Chinese and
central-bank demand lifts it during Asian hours; Western financial selling and hedging weighs on it during New York
hours.

- **Sessions:** the CME session for trade date d runs from 18:00 ET on day d−1 to 17:00 ET on day d. Bar times are
  converted from UTC to America/New_York, which also tracks the CME clock since CT and ET shift together.
- **Windows** (both 9 hours long, so a steady trend cancels out in the spread):
  - Asia: OPEN of the bar starting 18:00 ET on d−1 → CLOSE of the bar starting 02:00 ET on d (that is, 03:00 ET).
  - New York: OPEN of the bar starting 08:00 ET on d → CLOSE of the bar starting 16:00 ET on d (that is, 17:00 ET).
  - Europe (descriptive only): 03:00 → 08:00 ET.
- **PRIMARY:**
  - Statistic: mean over sessions of (r_Asia − r_NY), in bp, with a one-sample t-stat. Full sample; a session needs
    both windows to be valid.
  - Prediction: > 0.
- **Trade:**
  - Long one GC over Asia, short one GC over New York.
  - Net P&L = r_Asia − r_NY − cost_bp(Asia) − cost_bp(NY).
  - Report: mean, t, hit rate, annualized Sharpe (√252), and the same with costs doubled.
- **SECONDARY (China-holiday placebo; a test of the mechanism, not part of the verdict):**
  - Session d is "Shanghai closed" if Beijing date d is a weekday on which the Shanghai Stock Exchange
    (`exchange_calendars` XSHG) is closed. The Shanghai Gold Exchange follows the same State Council holiday
    schedule. The Asia window covers Beijing date d from about 06:00/07:00 to 15:00/16:00. Otherwise the session is
    "Shanghai open".
  - Statistic: mean r_Asia (open) − mean r_Asia (closed), Welch t. Prediction: > 0. The same comparison on
    (r_Asia − r_NY) is also reported.
- **Robustness and descriptive (reported only):**
  - long-only Asia net of costs;
  - the Europe window;
  - average return by ET hour (all 23 trading hours);
  - every calendar year;
  - in-sample vs out-of-sample;
  - excluding 2024–2026, the period whose World Gold Council regional breakdown we have already seen, so it is not blind;
  - 1%/99% winsorized means.
- **Disclosure:** the 2024–2026 Asia-vs-NY pattern was known from WGC and press reports before this test. The recent
  period is therefore not a blind check for Test 2, unlike Test 1, where 2021–2026 has not been published.
