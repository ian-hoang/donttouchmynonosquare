# World Cup sadness trade: results

## Spec choices and data checks (written before the single run)

**Match data**
1. **Two sources, full agreement.** openfootball and martj42 agree on all 424 matches (scores and shootout winners).
   The only fixes were spelling aliases ("Bosnia & Herzegovina", "Serbia and Montenegro" → "Serbia"). The
   knockout-stage round names come in several spellings; with all of them included, every tournament has 16
   knockout matches (32 in 2026).
2. **Event days are computed from kickoff times and each country's exchange open** (`build_events.log` lists every
   knockout loss). U.S. holidays roll forward: Brazil's Friday 2010-07-02 quarter-final loss lands on Tuesday
   2010-07-06.

**Prices**
3. **ETFs before launch.** EDEN and KSA price rows before the funds launched (2012-01-25, 2015-09-16) belong to other
   securities and are dropped, along with their dividends.
4. **Colombia.** GXG (to 2025-06-20) and COLO (from 2025-06-23) are stitched as one fund. The printout shows both
   closes so a break would be visible.
5. **Total returns.** Dividends (adjusted for later splits) are added on the ex-date. That matters here: country ETFs
   pay in June and December, inside the tournaments.
6. **Stale prices.** A daily return spanning more than 5 missing U.S. trading days is treated as missing. If the ETF
   didn't trade on the event day, its first trade after that day is used: return from its last close, basket
   compounded over the same days, α scaled by the number of days. If that reaches more than 5 trading days past the
   event day, the event is dropped as stale and listed.

**Tradable version**
7. **Entry and exit.** Entry is the U.S. close if the match ends 09:30–15:50 ET on a U.S. trading day, otherwise the
   next open; exit is the close of the event day.
8. **Hedge and costs.** The hedge is β × the equal-weighted basket (over the same interval). Round-trip cost is
   2 × (country cost + |β| × 5 bps).

**Diagnostic**
9. **Not pre-registered.** The mean AR over all ETF-days during the tournaments is printed as a check that the
   abnormal-return model is centred near zero. It cannot affect the verdict.

## Results (single run, 2026-10-03; full output in `run_output.txt`)

### Plain-English summary
**Verdict: FAIL.** After a World Cup knockout loss, the country's ETF didn't do worse than the rest of the world the
next session. Across 77 losses from 2006 to 2026 the average was **+0.06%** (t = +0.61), and only 47% were negative.

This is more than "no evidence". The 95% range of our estimate, about −0.13% to +0.25%, excludes the −0.49% the
original paper found for 1973–2004. A short bet after each loss, hedged with the world basket, made −0.09% per
event before costs and −0.53% after.

Whatever drove the effect in the paper's sample is not there in modern, globally traded country ETFs.

### Primary test
| | value |
|---|---|
| Knockout losses with an ETF (dates) | 77 (41) |
| Mean event-day abnormal return | **+0.058%** (prediction < 0) |
| t, clustered by date | **+0.61** |
| Share negative | 47% |
| Tradable short, gross / net per event | −0.093% / −0.528% (mean cost 0.44%) |

By tournament (mean AR, n): 2006 −0.22% (10), 2010 +0.07% (9), 2014 −0.15% (13), 2018 +0.27% (14),
2022 −0.24% (12), 2026 +0.38% (19).

### Robustness (reported only)
| Variant | N | Mean % | t |
|---|---|---|---|
| 1 Group-stage losses | 102 | +0.023 | +0.25 |
| 2 All wins (prediction ≈ 0) | 250 | +0.124 | +2.46 |
| 2b Knockout wins | 88 | +0.142 | +1.89 |
| 3 Two-day window | 77 | +0.001 | +0.00 |
| 4 Market-adjusted (β = 1) | 77 | +0.129 | +1.25 |
| 5 "Soccer nations" only | 34 | −0.023 | −0.14 |
| 6 2026 only | 19 | +0.376 | +2.26 (wrong sign) |
| 7 Liquid ETFs only | 50 | +0.018 | +0.14 |
| All losses pooled | 179 | +0.038 | +0.58 |

Wins coming out positive (t 2.5) is one of ten robustness lines, so luck is the likely explanation. It wasn't the
hypothesis, and the original paper found no win effect.

### Checks
- **Hand check against raw prices.** Brazil 2022: the quarter-final loss on penalties to Croatia (EWZ −2.74%, AR
  −3.27%) and the group loss to Cameroon (−3.42%, AR −2.13%) both match the file to six decimals.
- **The abnormal-return model is centred.** Mean AR over all 4,167 ETF-days during the tournaments is +0.001%.
- **No stale prices.** Every ETF traded on its event day; no events were dropped as stale.
- **Colombia stitch is continuous.** GXG 29.41 → COLO 29.33.
