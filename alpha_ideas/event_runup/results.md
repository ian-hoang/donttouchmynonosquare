# Earnings Eve (1A): results

## Audit and spec choices (written before the single run; no return had been computed)

**Event build (`build_events.log`)**
- 51,775 8-K item 2.02 filings (2019-01-02 → 2026-10-02) form 49,814 episodes; 3.7% of episodes hold more than one
  filing.
- 45,232 pass the quarterly-cadence filter: the previous episode started 50–130 days earlier.
- Of those, 17,923 are "case 2" (accepted ≥ 16:00 ET on a trading day) and were checked against Massive hourly bars.
- SEC `acceptanceDateTime` is true UTC. Check: NVDA's 2019-08-15 8-K shows 20:27Z = 16:27 ET, right after its ~16:20 release.

**Change 1: the timing rule for case 2 (made before any return was computed).**
- **What went wrong:** the pre-registered ratio rule (rAH = AH / median AH vs rPM = PM / median PM, 100-share floors)
  labelled 15% of filings accepted 16:00–16:59 as "released earlier in the day". Spot checks show many of those are
  genuine after-close reporters: KLAC 2025-07-31, COF 2021-10-26, CB 2022-10-25, CHGG 2021-08-09.
- **Cause:**
  - Pre-market baselines are often tiny, so the 100-share floor turns any pre-market trading on F into a ratio of
    20–60.
  - After-hours baselines are large because the 16:00 bar carries late closing prints, so a real after-close spike
    shows as a ratio of only 2–10.
- **Effect:** the error only ever moves the exit one session *earlier*. It never causes holding through a release. But it
  would cut the release-day session from many after-close events.
- **New rule (v2):** compare *extra* volume as a share of the stock's median daily volume (all hours, prior 20 sessions):
  - xAH = (AH_F − median AH) / median daily volume;
  - xPM = (PM_F − median PM) / median daily volume.
- **First form of v2:** "after the close if xAH ≥ xPM". It flipped quiet names with no spike in either session (WERN,
  ES, TTMI, FDX, COKE) to "earlier" on noise of ±0.001.
- **Final form of v2:** "earlier" only with positive evidence of a pre-market release (xPM > xAH **and** xPM ≥ 0.01,
  i.e. at least 1% of a normal day's volume traded extra before the open). Otherwise the after-close acceptance stamp
  stands.
- Both iterations used volumes only. No return had been computed.
- **Kept for transparency:** v1 labels are stored as `timing_v1`. The primary result under v1 is reported as an extra
  robustness line, along with S5 (exit the session before F for everything), which bounds both rules.

**Judgment calls**
- **Not checked by bars:** case-2 events with no ticker or outside the fetch window keep X = the session before F, the
  conservative choice. This mostly affects events before 2020-11, which are used only for the reaction history.
- **Merged episodes:** a pre-announcement followed by the scheduled release within 21 days counts as one episode. The
  event is the *first* filing, so the trade exits before any 2.02 news in the episode. Example: CLF 2023-04-11 and
  2023-04-24.

## Results (single in-sample run, 2026-10-03 evening; full output in `run_output_is.txt`)

### Plain-English summary
**Verdict: FAIL.**
- **The rule:** buy the hottest 20% of stocks 5 sessions before earnings and sell at the last close before the release.
  "Hottest" means past-year winners whose earnings days usually jump, with high volatility.
- **The result:** it earned nothing before costs and lost after costs: 3,522 trades, 2021–2025.
  - Before costs: −0.03% per trade.
  - After costs: −0.25% per trade (t −0.96).
  - Hit rate 49%.
- **The other checks agree:**
  - None of the three ingredients works alone.
  - A 10-session window is worse.
  - The conservative exit is the same.
  - Only 2024 was positive (+0.50%, t 1.1).
- **Bottom line:** the published pre-earnings run-up (1971–2005 and 1996–2013 samples) is not there in 2021–2025 US large
  and mid caps.

### Primary test
| | value |
|---|---|
| Hot events (score ≥ 0.8), IS entries 2021–2025 | 3,522 |
| Mean **net** return per event (beta-hedged, 5 sessions) | **−0.254%** (prediction > 0) |
| t, clustered by ISO week of entry | **−0.96** |
| Mean gross / hit rate | −0.033% / 48.6% |

### Secondary (reported only)
| Line | N | Mean % | t |
|---|---|---|---|
| S1 placebo, same stocks 30 sessions earlier (net) | 3,521 | +0.141 | +0.60 |
| S1 event − placebo (paired) | 3,521 | −0.379 | −1.31 |
| S2 all scored events, net / gross | 17,812 | −0.248 / −0.040 | −2.21 / −0.35 |
| S3 cold events, net | 3,656 | −0.303 | −2.27 |
| S4 top quintile on R12 / PREAC / IVOL60 alone, net | ~3,500 each | −0.146 / −0.205 / −0.535 | −0.57 / −1.04 / −1.56 |
| S5 conservative exit (session before F for all) | 3,523 | −0.218 | −0.83 |
| S5b pre-registered v1 timing rule | 3,522 | −0.266 | −1.00 |
| S6 10-session window | 3,552 | −0.360 | −1.23 |
| S7 beta = 1 hedge | 3,522 | −0.161 | −0.57 |
| S8 2x costs | 3,522 | −0.475 | −1.80 |
| S9 by year: 2021 / 2022 / 2023 / 2024 / 2025 | 671–737 | −1.28 / −0.03 / −0.39 / +0.50 / −0.12 | −1.26 / −0.07 / −1.36 / +1.11 / −0.24 |
| S10 predictable-schedule subset | 3,137 | −0.260 | −1.01 |
| S11 calendar-time portfolio | — | −5.4%/yr, vol 25.5%, Sharpe −0.21, max DD −68% | — |

### Checks
- **Hand check.** Five random hot events were recomputed from raw closes plus dividends and SPY closes; they match the
  file exactly: ACHC, WMB, ASAN, COP, APA. Timing on those is right:
  - ACHC and ASAN are after-close reporters that exit on the release day;
  - COP and APA exit the session before the filing date.
- **Hot names look right.** Median ranks are 0.87 (R12), 0.87 (PREAC) and 0.76 (IVOL60). Examples: LLY, NUE, AXON, MELI,
  FICO, MU, DECK, EME, HWM.

### Exploratory (not a test; decided after seeing the primary)
Mean beta-hedged daily return around the release. Day 0 = the last clean close; day +1 = first session after the release.

| Days | −9 | −8 | −7 | −6 | −5 | −4 | −3 | −2 | −1 | 0 | +1 | +2 | +3 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| All (17,815) | +0.02 | +0.02 | −0.01 | +0.02 | −0.02 | +0.00 | −0.02 | +0.00 | +0.00 | −0.02 | −0.10 | −0.02 | −0.03 |
| Hot (3,522) | +0.07 | +0.03 | +0.07 | +0.06 | +0.02 | −0.00 | −0.02 | −0.08 | +0.07 | −0.03 | +0.03 | −0.05 | −0.07 |
| Hot, after-close (1,888) | +0.07 | +0.08 | −0.04 | −0.01 | +0.02 | +0.03 | −0.03 | −0.10 | +0.03 | **−0.12** | +0.06 | −0.01 | −0.10 |

- The hot group drifts up a little 6–9 sessions out (~+0.2% in total), then is flat to negative into the release. A
  daily standard error is ~0.05%, so all of this is near noise.
- On the release-day session for hot after-close reporters (idea 1B), the average is −0.12%. That idea has now been
  peeked at, so it can no longer be tested cleanly on this sample.

### Hold-out
The 2026 hold-out was **not opened**. The in-sample verdict is FAIL, so there is nothing to confirm, and keeping 2026
sealed leaves it clean for a different future idea.

### Why it may have died (untested explanations)
1. **Decay.** The anomaly is old and well known; McLean & Pontiff find ~58% decay after publication.
2. **Universe.** These are top-1,000 large and mid caps. Aboody's top-1% winners and Gao-Hu-Zhang's high-uncertainty
   stocks lean small.
3. **Regime.** 2021's hot names (the post-meme peak) crashed, the only year below −1%. Even without 2021, the mean is
   around zero.

### Disclosure
This was the 12th pre-registered primary test of 2026-10-03. The timing-rule change was made before any return was
computed and is reported with its alternatives (S5, S5b). The exploratory event-time table is extra and not a test.
