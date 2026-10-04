# Test 4 — Month-end FX fix signed by the month's US equity move: results

Pre-registered in `alpha_ideas/PREREGISTRATION_ROUND3.md`. Code: `run.py`.

## Spec choices made during implementation (written before the single run; no FX return had been computed)
1. **Timing of the pre-registration.**
   - The file's text says "about 15:45 ET", but that hand-typed time is wrong (the same ~1h error seen in earlier
     docs). The file's mtime, **2026-10-03 16:42:35 ET**, is the authority.
   - The FX download started right after that time, in the same command that printed the mtime.
   - Data cost: $4.71 for 6E/6B/6A/6C/6S hourly bars. 6J and ES were already cached and are refused if missing.
2. **ES 16:00 ET close.** The CLOSE of the bar starting 15:00 ET. ES trading dates are the dates that have this bar.
   - On early-close days (e.g., the day after Thanksgiving) there is no 15:00 bar, so that day's move falls into the
     next trading day's return.
   - If a month's last trading day is an early close, its move is counted in the next month's MTD.
   - Roll-safe: the previous close is looked up for the same `instrument_id` across ES.v.0 and ES.v.1. One daily
     return in 2010–2026 has no same-contract previous close and is NaN; a month containing it would get no signal.
     In the validation run all 195 months had an MTD.
3. **MTD.** The sum of those daily log returns for ES dates from the 1st of the month up to, but not including, day L.
   That equals "after the last ES close of the previous month".
4. **Ticks** (data-driven rule from the pre-registration, checked before the run):
   - 6B uses the larger tick (0.0001) every year.
   - 6A and 6S use the larger tick in some middle years.
   - 6E, 6J and 6C use the smaller tick throughout.
   - Costs follow the detected tick per currency and year.
5. **Basket.** A currency is in an event's basket only if both its 15:00 and 16:00 London bars exist. At least 4
   currencies are required; costs are the average over the included currencies.
6. **Placebo.** On the second-to-last London business day, MTD is computed up to that day (not up to L).
7. **Statistics.**
   - The primary t is the plain one-sample t, as pre-registered; Newey-West(3) is also shown.
   - The continuous regressions use MTD in %, all months with data, and HC1 standard errors.
8. **Validation (no returns looked at).**
   - 195 months; 159 have |MTD| > 1% and 123 have |MTD| > 2%.
   - 388 of the 390 fix-hour windows have bars for each currency.

## Results (single run, 2026-10-03 ~16:50 ET; full output in `run_output.txt`)

### Plain-English summary
**Verdict: PASS**, with t = 4.4, which clears this repo's "convincing" bar of t ≥ 3. **The edge has shrunk a lot since
2021.**
- **What happens.** On the last London business day of the month, when US stocks are up more than 1% for the month,
  the six major currencies rise against the dollar in the hour before the 4pm London fix and fall back in the hour
  after. When US stocks are down more than 1%, the reverse.
- **The numbers.**
  - The two-hour round trip earned **+7.9 bp per event before costs (t = 4.39)** and was right 72% of the time
    (159 events, about 10 a year).
  - After costs (about 1.1 bp per round trip per window): **+5.6 bp (t = 3.12)**.
  - With costs doubled: **+3.3 bp (t = 1.85)**.
  - Annualized at the true event frequency, the net Sharpe is about **0.77** (0.46 with doubled costs). For context,
    the S&P 500's long-run Sharpe is about 0.4–0.5, and this strategy is in the market only two hours a month.
- **Both halves work.** The run-up into the fix is +3.7 bp (t = 2.65) and the give-back after it is −4.2 bp
  (t = −4.39), which is the inventory story Melvin & Prins describe.
- **But it is fading.**

| Period | Gross (bp/event) | t | Note |
|---|---|---|---|
| 2010–Feb 2015 (old 1-minute fix) | +12.1 | 4.55 | |
| Mar 2015–2020 | +8.6 | 2.96 | |
| 2021–2026 | +3.6 | 1.03 | net only +1.2 bp, t = 0.35 |
| Hackathon OOS (Oct 2024–Sep 2026, 18 events) | +8.5 | 1.72 | |

- **The placebo is partly positive.** The same trade on the second-to-last London business day earned +3.0 bp
  (t = 2.32).
  - In a post-hoc paired comparison over the same 150 months, the month-end day beat its placebo day by 4.4 bp, with
    t = 1.85 (below 2).
  - So the month-end day is stronger, but part of the pattern also shows up the day before. That is plausible if some
    funds rebalance a day early, but it means the effect is not cleanly fix-specific.
- **Yen is the exception.** 6J alone was −2.2 bp (t = −1.17); every other currency was positive.

### Primary and trade (six-currency basket, |MTD| > 1%)
| | Mean bp/event | t | Newey-West t | Hit rate |
|---|---|---|---|---|
| **G = s × (r_pre − r_post)** | **+7.88** | **4.39** | 4.49 | 0.72 |
| Net, base costs | +5.60 | 3.12 | 3.17 | 0.67 |
| Net, 2× costs | +3.33 | 1.85 | 1.87 | 0.62 |

### By sample (gross G)
| Sample | n | Mean bp | t |
|---|---|---|---|
| In-sample (before 2024-10) | 141 | +7.79 | 4.04 |
| OOS (from 2024-10) | 18 | +8.52 | 1.72 |
| 2010-07 → 2015-02 | 47 | +12.11 | 4.55 |
| 2015-03 → 2020-12 | 56 | +8.61 | 2.96 |
| 2021 → 2026 | 56 | +3.59 | 1.03 |
| Quarter-end months | 51 | +9.89 | 3.22 |

### Robustness (reported only)
| Check | Mean bp | t |
|---|---|---|
| Pre-fix leg s·r_pre (predicted > 0) | +3.68 | 2.65 |
| Post-fix leg s·r_post (predicted < 0) | −4.20 | −4.39 |
| 6E alone | +6.04 | 2.62 |
| 6J alone | −2.23 | −1.17 |
| 6B alone | +12.02 | 4.58 |
| 6A alone | +13.54 | 5.28 |
| 6C alone | +6.54 | 2.99 |
| 6S alone | +11.34 | 3.93 |
| GBP/AUD/CHF basket (the blog's choice, so not independent) | +12.30 | 5.39 |
| Threshold 0% (all months, n = 194) | +6.42 | 4.10 |
| Threshold 2% (n = 123) | +9.38 | 5.10 |
| Placebo: second-to-last London business day | +3.03 | 2.32 |
| Regression of r_pre on MTD (all months) | +0.95 bp per 1% | 3.13 |
| Regression of r_post on MTD (all months) | −0.95 bp per 1% | −4.03 |

**Post-hoc, not pre-registered:**
- Month-end minus placebo, paired over 150 months: +4.4 bp (t = 1.85).
- Sharpe at the actual frequency of about 9.8 events a year: gross 1.09, net 0.77, 2× costs 0.46.

### Notes
- One month (of 195) had no valid basket.
- On average all 6 currencies were in the basket.
- Costs averaged 1.14 bp per round trip per window.
- Fills assume the first and last trades of each London hour, plus 1 tick and $2.50 per side, so exact-time execution
  is part of the assumption. The 2× cost stress test covers some slippage.
- This adds **1 primary test** to the repo's disclosed count.
