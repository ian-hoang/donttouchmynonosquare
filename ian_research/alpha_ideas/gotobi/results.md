# Test 1 — Gotobi (Tokyo 9:55 fixing) in yen futures: results

Pre-registered in `alpha_ideas/PREREGISTRATION_ROUND2.md` (mtime 2026-10-03 13:44:32 ET, before any 6J data was
downloaded). Code: `run.py`.

## Spec choices made during implementation (written before the single run; no 6J return had been computed)
1. **Sample days.** Tokyo business days from 2010-06-08, the first Tuesday after the data starts, through
   2026-09-30. Monday 2010-06-07 is outside the primary Tue–Fri sample anyway.
2. **What "missing bar" means.** There is no `ohlcv-1h` bar with exactly that UTC start time; Databento omits hours
   with no trades. There is no filling, so that window is dropped.
3. **Tick by year.** A whole calendar year gets the 0.0000005 tick if any of its bar prices sits on an odd multiple of
   0.0000005. A year in which CME switched mid-year therefore gets the smaller tick (and cost) for the entire year.
4. **Sharpe annualization.** Sharpe uses √(gotobi Tue–Fri trades per year), where trades per year = the count of valid
   gotobi days ÷ the sample length in years (2010-06-08 → 2026-09-30).
5. **Month-end subgroup.** "Month-end gotobi" is the business day produced by the last calendar day of the month
   under the previous-business-day rule. In 31-day months, the 30th's business day joins the 5/10/15/20/25/30 group
   unless it is the same day as the month-end one.
6. **Intervention exclusion.** Each listed MoF intervention date, plus the nearest Tokyo business day before and after it.
7. **Winsorizing.** The 1%/99% cut-offs come from all valid Tue–Fri days of S, gotobi and control together.
8. **Hourly path.** Bar-to-bar USD/JPY returns use consecutive hourly bars of the same contract only, averaged by UTC
   start hour across days in each group (Tue–Fri).
9. **Calendars.** `holidays` package (country JP) plus Dec 31 and Jan 1–3 as bank holidays.

## Results (single run, 2026-10-03 ~15:10 ET; full output in `run_output.txt`)

### Plain-English summary
**Verdict: WEAK PASS (cost-fragile)** by the pre-registered rule. In practice: **real, but too small to trade, and it has
faded since 2021.**
- **The effect is real.** Over 2010–2026, on gotobi days USD/JPY rose more into the 9:55 fix and fell more after it
  than on ordinary days: **+2.2 bp per day more (t = 2.38)**. The Tokyo payday dollar buying shows up in CME yen
  futures.
- **But it's tiny.**
  - Before costs, the trade earned 2.9 bp per gotobi day (t = 3.78).
  - Two round trips cost about 2.1 bp, which leaves **+0.8 bp per day (t = 1.08, Sharpe 0.27)**.
  - With costs doubled it **loses 1.2 bp per day**.
- **It has faded.** Net trade P&L per gotobi day:

| Period | Net per gotobi day | t |
|---|---|---|
| 2010–2017 | +2.75 bp | 2.12 |
| 2018–2020 (the paper's years) | +1.45 bp | 1.14 |
| 2021–2026 (new) | −2.00 bp | −1.70 |

  In the hackathon OOS window (Oct 2024–Sep 2026) the gotobi effect is ≈ 0 (D = +0.09 bp, t = 0.04) and the trade
  loses 1.55 bp per day.
- **Where it lived.**
  - Mostly on **month-end** gotobi days: +5.8 bp vs ordinary days, t = 3.22, n = 167. The 5/10/15/20/25/30 days
    were weaker: +1.5 bp, t = 1.53.
  - Almost all of it came from the **run-up before the fix** (+1.4 bp, t = 2.28). The give-back after the fix was
    small (−0.7 bp, t = −1.06).
  - These splits are reported only and were not chosen in advance, so they cannot change the verdict.

### Primary (Tue–Fri, full sample)
| | Mean S, gotobi | Mean S, control | D | Welch t | Newey-West t | n |
|---|---|---|---|---|---|---|
| S = USD/JPY return 08→10 JST minus 10→12 JST (bp) | +2.90 | +0.71 | **+2.19** | **2.38** | 2.42 | 1,050 / 2,171 |

### Trade (gotobi Tue–Fri only, about 64 trades a year)
| | Mean bp/day | t | Hit rate | Sharpe |
|---|---|---|---|---|
| Gross | +2.90 | 3.78 | 0.56 | 0.94 |
| Net, base costs (~1.03 bp per round trip × 2) | **+0.83** | 1.08 | 0.52 | 0.27 |
| Net, 2× costs | −1.24 | −1.61 | 0.47 | −0.40 |

### By sample
| Sample | D (bp) | t | Trade net (bp/day) | t |
|---|---|---|---|---|
| In-sample to 2024-09-30 | +2.48 | 2.51 | +1.17 | 1.41 |
| OOS 2024-10 → 2026-09 | +0.09 | 0.04 | −1.55 | −0.78 |
| 2010–2017 | +2.69 | 1.77 | +2.75 | 2.12 |
| 2018–2020 | +3.87 | 2.44 | +1.45 | 1.14 |
| 2021–2026 | +0.66 | 0.46 | −2.00 | −1.70 |

### Robustness (reported only; none can rescue or change the verdict)
| Check | Diff (bp) | t |
|---|---|---|
| Pre-fix leg only (gotobi − control) | +1.44 | 2.28 |
| Post-fix leg only (predicted < 0) | −0.73 | −1.06 |
| Month-end gotobi vs control | +5.79 | 3.22 |
| 5/10/15/20/25/30 gotobi vs control | +1.51 | 1.53 |
| March only | +2.11 | 0.50 |
| Mondays only | −1.53 | −0.42 |
| "Next business day" holiday rule | +0.80 | 0.86 |
| Nominal dates only (no holiday shift) | +0.94 | 0.97 |
| Excluding intervention days ±1 | +2.04 | 2.34 |
| Winsorized 1%/99% | +2.15 | 2.78 |

### Notes
- The 6J tick was 0.0000005 in every year of the data, so base costs averaged about 1.03 bp per round trip.
- Pre-fix windows dropped: 53 contract rolls and 47 missing bars. Post-fix windows dropped: 46 missing bars.
  Valid Tokyo business days: 3,890 of 3,991.
- **Fix after the run:** the descriptive hour-by-hour table (`hourly_path`) printed NaN on the first run, because its
  helper compared each bar's timestamp with itself.
  - The fix touches only that table. The rerun reproduced every other line exactly; the first output is kept as
    `run_output_first.txt`.
  - In the fixed table, the 22:00 UTC row is noise: n = 2 and 10, from bars around CME's daily break.
- This adds **1 primary test** to the repo's disclosed count.
