# VRP short straddle: independent rebuild results

Run 2026-10-03, following [PREREGISTRATION.md](PREREGISTRATION.md). I wrote this code from scratch on our own
Massive data and did not look at the teammate's code. Full tables are in [out/summary.md](out/summary.md).

## Bottom line

**The rebuild agrees with the teammate's KILL verdict.**

- Selling hedged straddles on SPY/QQQ is a bit like selling insurance. It earns a small premium about 60–70% of
  the time, then gives a large part of it back in a crash. April 2025 was the crash in this window.
- The "only sell when VRP_Z > 0" filter looks helpful out-of-sample. But all of that help comes from
  happening to sit out April 2025. Remove those 8 weeks and the filter **hurts**: Sharpe 0.49 vs 0.79 for
  always selling.
- Random filters that sell on the same number of weeks match or beat it over a third of the time (p = 0.36), so it is not
  distinguishable from luck.
- Simply holding SPY did much better over the same period: Sharpe 1.05 raw, or 0.80 after subtracting the
  T-bill rate, vs 0.30.

## Side by side with the teammate's claims

| Claim | Teammate | Rebuild, main (30-day option held to expiry−1) | Rebuild, 1-week hold |
|---|---|---|---|
| OOS Sharpe, filter (Z>0) | 0.41 | **0.30** | −0.15 |
| OOS Sharpe, always short | 0.13 | **0.23** | −0.60 |
| SPY buy & hold, OOS | 0.83 | **1.05** raw / 0.80 minus T-bill | same |
| Without 2025-03-20..05-15: always vs filter | 0.66 vs 0.48 | **0.79 vs 0.49** | 0.08 vs −0.15 |
| Placebo p (random weeks) | ≈ 0.14 | **0.36** | 0.16 |
| OOS 95% CI, filter Sharpe (21-day block bootstrap) | — | [−0.80, 1.60] | [−1.07, 0.93] |

The exact numbers differ, which is expected: my rules for days-to-expiry, holding period and costs are my
own guesses. Their FROZEN_RULES.md is not on this machine. **Every qualitative claim reproduces:**
- the filter beats always-short OOS only because of April 2025;
- both lose to SPY;
- the placebo test is not significant.

### Where April 2025 sits (main version, OOS total P&L in bp of underlying price)

| | Mar 20 – May 15, 2025 | Rest of OOS | Total |
|---|---|---|---|
| Filter (Z>0) | −371 | +1,009 | +637 |
| Always short | −1,472 | +2,230 | +759 |

Always-short actually made more money in total. The filter only wins on Sharpe because it skipped some of
the crash and carried less risk.

## Pre-registered verdict

Breaking KILL needed all three of the following. None held, in any variant (both holds, both mark rules):

| Condition | Result |
|---|---|
| Placebo p < 0.05 | 0.36 (H5: 0.16) ✗ |
| Filter OOS Sharpe > SPY B&H | 0.30 vs 1.05 ✗ |
| Filter > always with the April 2025 window removed | 0.49 vs 0.79 ✗ |

## Sensitivities (OOS, main version: filter / always)

- Half the spread (k = 0.5): 0.43 / 0.39.
- No spread (k = 0): 0.56 / 0.55.
- Unhedged: 0.55 / 0.35.
- Cheaper costs lift both versions equally, so the filter still adds ~nothing.
- The 1-week hold is worse everywhere, because it pays the bid-ask spread 4× as often.

## Checks on my own code (the handoff's test list, applied to the rebuild)

| # | Check | Result |
|---|---|---|
| 1 | P&L accounting: one trade (SPY 2024-07-24 → 08-22) recomputed by hand from raw quotes | PASS. Option P&L, spread and commission match to the cent. The hedge sign is right: it lost $12.56 to the August 2024 whipsaw while the straddle decayed $5.32. |
| 2 | Look-ahead | PASS. RV uses closes through t−1 (`shift(1)`). Z is trailing, including t (min_periods 126, first Z 2022-09-02). S is the 15:44 bar close. |
| 3 | Timestamps, DST, half-days | PASS after a fix. Marks are built in America/New_York. All 9 early closes are found, but only after a fix (below). |
| 4 | IV and delta math | PASS. Straddle IV always lies between the call-only and put-only Black-Scholes IVs from a separate solver. The analytic delta equals a numerical bump to 5 decimals. VIX isn't available on our key, so I couldn't compare against it. |
| 5 | Stale marks | Bug found and fixed (below). Effect: 0.30 → 0.29. |
| 6 | Selection | Wednesdays only. QQQ skips 11 of 210 Wednesdays because no $1 strike was listed. |
| 7 | Block boundaries | PASS. Trades are assigned by entry date. IS trades' P&L running into July 2024 stays in IS. The OOS series holds only OOS trades. |

## Deviations and bugs (disclosed)

1. **Early closes** (fixed before any P&L existed). SPY's after-hours volume on Black Friday 2024 and 2025 beat
   the 5% test, so two half-days would have been marked at 15:45. The fix: a day counts as an early close if
   either ticker flags it.
2. **Mark validity** (post-hoc, after the first run). The pre-registered "spread ≤ 25% of mid" rule rejected
   far-OTM legs quoted 0.02/0.03 near expiry. It flagged 194 of 401 main-version exits and carried a stale,
   higher price forward. The fixed rule accepts any sane quote when marking held legs. Both versions are
   reported; the change is 0.30 → 0.29.
3. **$1 strikes are not always listed.** After rallies to new highs, only $5 strikes may exist about 30 days out.
   The rule therefore fails on 46 of 2,306 underlying-days (mostly QQQ).

## What this rebuild cannot tell you

- **Bugs specific to their code.** Agreeing with their verdict through different code and rules is strong
  evidence the KILL isn't a coding artifact. Their exact 0.41 / 0.13 still needs their repo.
- **Their claim 3** (single-name cross-section). Not rebuilt.
- **The 2020 crash.** Option quotes on our key start 2022-03-07. Other weekday cohorts weren't tested either.
- **Other simplifications.** American exercise is ignored and there is no financing cost on the hedge.

This is 1 more pre-registered test for the 2026-10-03 tally.

## Files

- `vrp/data.py` pulls and caches everything into `data/cache/vrp/` (~23k Massive calls; reruns are free).
- `vrp/backtest.py` builds features, the ledger and the stats in about 5 s.
- `vrp/out/`: `summary.md`, per-trade CSVs (`trades_*.csv`), daily features, and the OOS daily series.

```
uv run python vrp/data.py && uv run python vrp/backtest.py
```
