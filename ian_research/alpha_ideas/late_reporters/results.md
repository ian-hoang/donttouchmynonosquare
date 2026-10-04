# Late reporters: results

## Audit and spec choices (written before the single run; no return had been computed)

**Signal audit (`build_events.log`)**
1. **How often the signal fires.** Late signals (no item 2.02 filing by E+3) fire for 20% of anchor-quarters.
   - The typical late company reports exactly 7 days after last year's date. Much of that is calendar mechanics
     (53-week fiscal years, "second Tuesday"-type schedules) rather than hidden news. The pre-registered rule is kept
     as written; the stricter E+5 threshold (robustness 3) filters more of these shifts.
   - Of the late signals on universe firms (about 2,900), 96% get their release within 60 trading days, and 96% sit on
     a normal quarterly schedule (an anchor 60–120 days from the previous or next one). The rest come from one-off
     2.02 filings, which is small enough that no extra filter was added.
   - Signals without a release in 60 days are mostly firms acquired or delisted (Xilinx, People's United). Those drop
     out under the universe-membership rule.

**Judgment calls**
2. **Duplicate releases.** For the post-release robustness checks, a release window [E−30, E+90] can catch the same
   filing for two neighbouring anchors. Each filing is kept once, assigned to the anchor it is closest to.
3. **Waiting days.** In robustness 2, events released on O+1 have no waiting days, so their waiting-part CAR is 0;
   they are kept.

## Results (single run, 2026-10-03; full output in `run_output.txt`)

### Plain-English summary
**Verdict: FAIL.** The rule was: short a stock once it is 3 trading days past its usual earnings date with nothing
filed, and hold until the day after it finally reports. Across 2,924 cases (1,061 companies, 2021–2026) that earned
nothing.
- Late reporters matched their peers: mean −0.05% (t = −0.24), median exactly 0%, 49% down and 51% up.
- After costs the short loses 0.38% per trade.
- Late releases weren't followed by extra drift either (late minus on-time: −0.03%, t −0.08).

The market prices the delay. Most "late" companies are just running a week behind on the calendar, and the ones
hiding bad news (e.g. Stride, −54% the day after its delayed report) are offset by others that jump.

### Primary test
| | value |
|---|---|
| Late signals in the universe (firms) | 2,924 (1,061) |
| Mean CAR, O → release day +1 | **−0.052%** (prediction < 0) |
| t, clustered by month | **−0.24** |
| Median / share negative | 0.000% / 49% |
| Short net of 0.43% mean cost | −0.378% per event (t −1.75) |

### Robustness (reported only)
| Variant | N | Mean % | t |
|---|---|---|---|
| 2a Waiting part (E+3 → day before release) | 2,808 | −0.033 | −0.34 |
| 2b Release reaction (day 0 → +1) | 2,808 | −0.115 | −0.67 |
| 3 Stricter threshold (E+5) | 869 | −0.229 | −0.43 |
| 5 O ≥ 2022-07 (skip COVID base year) | 2,375 | +0.048 | +0.19 |
| 7 Signals with no release in 60 days | 116 | +2.254 | +1.41 |
| 1 Post-release drift, ≥ 7 days late | 2,133 | +0.110 | +0.24 |
| 1b Post-release drift, on time | 12,594 | +0.143 | +0.57 |
| 1c Late minus on-time post drift | 14,727 | −0.034 | −0.08 |
| 4 Post-release drift, ≥ 7 days early | 1,114 | −0.536 | −1.29 |
| 6 Calendar-time version | 60 months | +0.184/month | +0.29 |

### Checks
- **Hand check.** Stride (LRN), O = 2025-10-27, held 3 days: the CAR recomputed from raw prices against all 333 peers
  is −55.93%, identical to the file (close 153.53 → 70.05 on 2025-10-29).
- **Outliers don't drive it.** Capping the 1% most extreme CARs on each side leaves the mean at −0.056%.
