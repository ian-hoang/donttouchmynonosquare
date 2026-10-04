# Test 2 — Gold "Asia buys, New York sells" (GC): results

Pre-registered in `alpha_ideas/PREREGISTRATION_ROUND2.md` (mtime 2026-10-03 13:44:32 ET, before any GC data was
downloaded). Code: `run.py`.

## Spec choices made during implementation (written before the single run; no GC return had been computed)
1. **Session dates.** Every weekday from 2010-06-07 through 2026-09-30. On CME holidays and early closes a needed
   bar is missing, so that window is dropped and counted; there is no filling.
2. **Clock.** Window times are built in America/New_York and converted to UTC to match the bars.
   - Daylight-saving switches happen at 02:00 on Sundays; no window uses a Sunday 02:00 time.
   - A Monday's Asia window starts Sunday 18:00 ET, when CME reopens.
3. **Shanghai closed.** A weekday on which `exchange_calendars` 4.13.2 XSHG has no session. Session date d maps to
   Beijing date d, because the Asia window runs about 06:00/07:00 → 15:00/16:00 Beijing time on date d.
4. **Hourly profile.** All bars are used, including any holiday sessions. Returns are close-to-close between
   consecutive hourly bars of the same contract, grouped by ET bar-start hour.
5. **"Ex 2024–2026."** Sessions dated before 2024-01-01.
6. **Winsorizing.** The 1%/99% cut-offs come from all valid sessions.
7. **Sharpe.** Annualized with √252; "ann_bp" = mean × 252.

## Results (single run, 2026-10-03 ~15:12 ET; full output in `run_output.txt`)

### Plain-English summary
**Verdict: FAIL.**
- **No reliable Asia-vs-New York split.** Over 2010–2026, gold's Asian-hours return minus its New York-hours return
  was **+1.7 bp per day (t = 1.20)**, which could easily be luck. After two round trips of costs (about 1.9 bp a day)
  it is −0.15 bp per day.
- **The Asian-hours gain is mostly gold's bull run.** Asian hours alone rose +1.75 bp per day (t = 2.24), but gold
  more than tripled over the sample ($1,243 → $4,216). New York hours were flat (+0.02 bp).
- **Recent years look better but weren't a blind test.**
  - Out of sample (Oct 2024–Sep 2026): +8.2 bp per day (t = 1.48); net +7.3 bp, Sharpe 0.95.
  - Most of that is 2026: +18 bp per day (Asia +9.1, NY −8.9).
  - That matches the World Gold Council reports we had already seen. It is not significant.
- **The China-holiday check went the predicted way** (secondary; it can't rescue the verdict).
  - Asian-hours return was **−3.8 bp** on days Shanghai was closed vs **+2.2 bp** on open days (difference +6.0 bp,
    t = 2.32).
  - That fits Chinese buyers driving part of the Asian-hours move. But there are only 273 closed days, bunched
    around Golden Week and Lunar New Year, so seasonality could explain it.

### Primary (full sample, n = 4,020 sessions)
| | Mean bp/day | t | Newey-West t | Hit rate | Sharpe |
|---|---|---|---|---|---|
| **r_Asia − r_NY** | **+1.73** | **1.20** | 1.22 | 0.50 | 0.30 |
| Asia leg | +1.75 | 2.24 | 2.29 | 0.51 | 0.56 |
| NY leg | +0.02 | 0.02 | 0.02 | 0.50 | 0.01 |

### Trade (long Asia, short NY, 2 round trips a day; base cost averaged 0.94 bp per round trip)
| | Mean bp/day | t | Sharpe |
|---|---|---|---|
| Gross | +1.73 | 1.20 | 0.30 |
| Net, base costs | −0.15 | −0.10 | −0.03 |
| Net, 2× costs | −2.03 | −1.41 | −0.35 |

### Secondary: China-holiday placebo (Shanghai open vs closed)
| | Open | Closed | Difference | t |
|---|---|---|---|---|
| r_Asia (prediction: open > closed) | +2.16 | −3.82 | +5.98 | 2.32 |
| r_Asia − r_NY | +2.52 | −9.03 | +11.54 | 2.06 |
| r_NY (no prediction) | −0.35 | +5.21 | −5.57 | −1.11 |

### By sample
| Sample | Asia − NY (bp/day) | t | Net (bp/day) | Sharpe |
|---|---|---|---|---|
| In-sample to 2024-09-30 | +0.84 | 0.58 | −1.19 | −0.22 |
| OOS 2024-10 → 2026-09 | +8.15 | 1.48 | +7.32 | 0.95 |
| Before 2024 | +1.18 | 0.78 | −0.89 | −0.16 |

By calendar year, the spread was positive in 9 of 17 years, ranging from −6.8 bp (2022) to +18.0 bp (2026).

### Robustness and descriptive (reported only)
- Long-only Asian hours, net of costs: +0.81 bp per day (t = 1.04, Sharpe 0.26).
- Europe window, 03:00→08:00 ET: −1.02 bp per day (t = −1.52).
- Winsorized spread: +1.76 bp (t = 1.33).
- **Hour by hour.** These are post-hoc patterns across 24 hours and were not tested; each is about one round trip of
  cost or less:
  - Largest: the thin last CME hour, 16:00–17:00 ET (+0.97 bp, t = 5.2).
  - The Asian-open hours, 18:00–20:00 ET, are positive (t = 2.1 and 2.6).
  - 09:00–10:00 ET (New York open and the LBMA morning auction) is negative (t = −2.7).

### Notes
- Windows dropped: Asia 71 missing bars and 54 rolls; NY 181 missing bars, mostly CME holidays and early closes.
- This adds **1 primary test** to the repo's disclosed count.
