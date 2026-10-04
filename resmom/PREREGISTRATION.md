# Residual momentum — independent rebuild (pre-registered)

Written 2026-10-03, after the panel was built and the universe size was matched. No signal, portfolio or return
statistic had been computed yet. The file's mtime is the timestamp.

## Why this exists

A teammate's study (`residual-momentum`, not on this machine) reports that residual momentum beats classical
12-1 momentum. I have **not** seen their code or REPORT.md, only the handoff's list of headline numbers, so this
is a replication, not a discovery test. Where the handoff states a convention (timing, costs, the bad-return
filter, the 504-day beta window, delisted stocks earning 0), I copy it so the numbers are comparable. Everything
else is my own choice, fixed here.

## Data

- Massive grouped daily bars, 2010-01-04..2026-09-30 (cached by `alpha_ideas/smooth_losers/fetch_data.py`).
  Prices are split-adjusted with no dividends, and the data is ticker-level.
- Common stocks only (Massive type CS, active and delisted).
- Fama-French daily factors (Mkt−RF, SMB, HML, RF) through 2026-08-31.
- Daily return = close / last available close − 1, set to NaN if it spans more than 5 missing sessions.
- Returns outside (−70%, +200%) are set to NaN. A NaN return counts as 0 for a held stock.

## Signals at rebalance day i (last session of each month)

- **MOM12_1** = P[i−21] / P[i−252] − 1, using adjusted closes, with both prices present.
- **Residual (RESID)**:
  - Run OLS of daily excess returns on [1, Mkt−RF, SMB, HML] over the 504 sessions ending at i. A stock
    needs at least 400 valid days.
  - Signal = sum of the residuals over sessions i−251..i−21 ÷ the standard deviation of the residuals over
    those same sessions.
- **Universe at i**: all of
  - CS ticker;
  - raw close at i ≥ $5;
  - 63-session mean dollar volume ≥ $25M (nominal). This cutoff was picked only so the counts match the
    teammate's (855 vs 841 in 2012-02, 1,727 vs 1,743 in 2026-09);
  - at least 400 valid returns in the last 504 sessions;
  - both signals defined.

  Both strategies use the same universe.

## Portfolio

- **Deciles:** the top decile (EW long) and bottom decile (EW short) by signal; decile size = floor(N/10).
- **Timing:** trade at close i+1. Positions earn daily returns from i+2 through the next rebalance's i+1 (buy
  and hold, weights drift).
- **Turnover** = Σ|w_new − w_drifted| across both legs, where each leg sums to 1.
- **Cost** = bps × turnover, charged on day i+2. Main cost: 10 bps.
- **L/S daily return** = long leg − short leg − cost.
- **Sharpe** = daily mean / std × √252, with no risk-free rate subtracted. MaxDD is on the compounded L/S NAV.
- **Rebalances:** the first is the first month-end with enough history; the last with a full holding period is
  2026-08-31.

## Comparisons (teammate's number → mine)

1. Classical and residual Sharpe, gross and net at 10 bps, plus turnover/yr and MaxDD.
2. Residual net at 0 / 5 / 10 / 20 / 30 bps.
3. Residual net by period. Their split boundaries aren't in the handoff, so I assume:
   - IS 2012-02..2016-12;
   - VAL 2017..2021;
   - TEST 2022-01..2026-09 (4.75 years, which matches "test window is only 4.75 years").

   Walk-forward OOS = 2017+.
4. Random-rank placebo: 2,000 draws, each a random ranking every month with the same decile size, gross. I use
   monthly holding-period returns, and the Sharpe is computed on that monthly series.
5. Universe size and rebalance count.

**Not rebuilt:** the risk-scaled IV+VT10 variant, the sector-shuffle placebo, Fama-MacBeth, and size terciles.
These need SIC codes or shares data, or have unstated details.

## Attacks (from the handoff's test list; all reported, none used to choose anything)

- **A. Turnover and signal persistence:** the month-to-month rank autocorrelation of each signal, and how much
  turnover comes from entries and exits of the universe itself.
- **B. Last-month leak through the regression intercept.** With an intercept, OLS residuals sum to zero over the
  504-day window, so the formation-window sum = −(the residuals in year −2 + the residuals in the skipped last
  21 days). The residual signal therefore carries some short-term *reversal*, a different and expensive-to-trade
  effect. Two tests:
  - the cross-sectional rank correlation of RESID with the last-21-day return;
  - a variant whose betas are fit on the 504 sessions ending at i−21 (the skip month is excluded entirely).

  If RESID's edge over MOM shrinks a lot in that variant, the edge is partly mislabeled reversal.
- **C. Data quality:** keep all returns (no −70/+200 filter), or drop any stock with a filtered return in its
  signal window.
- **D. Delisting:** a held stock whose bars end before the holding period ends gets −30% on its last bar
  (an extreme assumption) instead of 0.

## What counts as "reproduced" (fixed now)

- **Numbers:** a Sharpe within ±0.15 of theirs counts as reproduced. Given different universe membership, any
  closer match would be luck.
- **Qualitative claims to confirm or break:**
  1. RESID gross Sharpe > MOM gross;
  2. RESID net (10 bps) > MOM net;
  3. RESID turnover > MOM turnover;
  4. RESID MaxDD much smaller than MOM's;
  5. placebo p < 0.05 for RESID gross.
- **Break condition:** if claim 2 flips in my rebuild or in variant B, the "residual beats classical after
  costs" story does not hold.
