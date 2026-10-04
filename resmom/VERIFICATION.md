# Residual momentum: independent verification

Run 2026-10-03 under [PREREGISTRATION.md](PREREGISTRATION.md). The teammate's repo isn't on this machine, so this
is a **from-scratch rebuild**. It uses the same data source (Massive grouped daily bars, CS tickers including
delisted ones), my own code (no engine.py), and the conventions stated in the handoff. Full tables are in
[out/summary.md](out/summary.md); the post-hoc check is in [out/posthoc.md](out/posthoc.md).

## Bottom line

1. **Their numbers are real.** Code written independently gets nearly the same results: every headline Sharpe
   lands within 0.05 of theirs. That makes a hidden look-ahead or accounting bug very unlikely, because a bug
   would show up as a gap.
2. **There is one design flaw, and it isn't cheating.** The "residual" signal partly measures *last month's*
   move, in the opposite direction. This is a different, known effect (short-term reversal), and it is expensive
   to trade.
   - The cause: with an intercept, regression residuals add up to zero over the 504-day window, and that window
     includes the skipped month. So a big move in the skipped month pushes the formation-period sum the other
     way.
   - The size: a correlation of −0.17 with the last 21 days' return. Theory predicts about −0.19.
   - The fix: fit the betas on the window ending 21 days earlier. Then turnover falls from 24 to 20 times a year
     and net Sharpe *rises* from 0.46 to 0.56.
3. **"Residual beats classical after costs" is not proven.**
   - The net Sharpe lead is +0.05, with a 95% interval of [−0.33, +0.42]. In 41% of bootstrap resamples it is
     zero or negative. The fixed version is +0.15, still inside noise.
   - What residual momentum really gives is a **smoother ride**: about half the volatility and a max drawdown of
     −21% vs −40%. At equal risk, the annual returns are similar: 6.6% vs 5.9%.
   - It is also more cost-sensitive. Above roughly 15 bps per trade it falls behind classical.

For scale, a Sharpe of 0.4–0.6 is roughly what the S&P 500 does over the long run.

## Headline numbers (net = 10 bps; EW top-minus-bottom decile)

"Reproduced" means within ±0.15 Sharpe (fixed in the pre-registration).

| Item | Teammate | Rebuild | Verdict |
|---|---|---|---|
| Classical MOM12_1 Sharpe, gross / net | 0.449 / 0.396 | 0.47 / 0.41 | PASS |
| Classical turnover / MaxDD | 15.5x / −48% | 15.2x / −40% | PASS / close |
| Residual Sharpe, gross / net | 0.612 / 0.432 | 0.63 / 0.46 | PASS |
| Residual turnover / MaxDD | 24.3x / −22% | 24.2x / −21% | PASS |
| Residual net at 0/5/10/20/30 bps | 0.61 / 0.52 / 0.43 / 0.25 / 0.07 | 0.63 / 0.54 / 0.46 / 0.29 / 0.12 | PASS |
| Residual net, IS / VAL / TEST | 0.39 / 0.25 / 0.65 | 0.07 / 0.51 / 0.67 | TEST PASS; IS/VAL INCONCLUSIVE (split dates aren't in the handoff; I assumed 2012–16 / 2017–21 / 2022–26) |
| Risk-scaled (IV+VT10) net; walk-forward 2017+ | 0.317; 0.317 | not rebuilt; plain residual 2017+ = 0.60 | INCONCLUSIVE (the details aren't stated) |
| Random-rank placebo (gross monthly) | real 0.709, null 0.00 ± 0.27, p 0.008 | real 0.65, null 0.00 ± 0.26, p 0.006 | PASS |
| Sector-shuffle placebo | 0.704 ± 0.025 | not rebuilt (no SIC data here) | — |
| Universe, rebalances | 841 → 1,743, 176 | 855 → 1,748, 175 | PASS |

On the universe row: the size was matched on purpose with a $25M dollar-volume cutoff. I have 175 rebalances
because the Fama-French daily data ends 2026-08-31, which drops the 2026-09 rebalance; it had no holding period
anyway.

## The handoff's numbered tests

| # | Test | Result | Numbers |
|---|---|---|---|
| 1 | Look-ahead in the residual signal | **PASS** (no future data), with a **design flaw** | See below. |
| 2 | Independent MOM12_1 reimplementation | **PASS** | Gross 0.47 vs 0.449. Month-by-month comparison against `phase1_series.pkl` wasn't possible (file not here). |
| 3 | Turnover accounting | **PASS**, cause explained | See below. |
| 4 | Data quality (the −70%/+200% filter) | **PASS** | See below. |
| 5 | Delisting bias (−30% on the bar after a held stock's last one) | **PASS** (doesn't flip) | See below. |
| 6 | Sector map | not testable | No SIC data here. |
| 7 | Market-cap proxy / size terciles | not testable | No shares data here. |
| 8 | Vol-target logic | not testable | The IV+VT10 variant wasn't rebuilt. |
| 9 | Placebo engine | **PASS** (re-derived) | My own random-rank engine, with the same decile size and EW buy-and-hold monthly returns, gives the same null (0.00 ± 0.26) and p 0.006. |
| 10 | Fama-MacBeth | not testable | Not rebuilt. |

**1. Look-ahead.** My signals use only data through day i, and they reproduce the teammate's numbers, so their
code isn't using future data either.
- The handoff's "shifted signal gives −4.9" is explained by the zero-sum-of-residuals identity. At k+1, the
  holding-period returns sit in the skipped month of the beta window, which mechanically pushes the signal the
  opposite way.
- The same identity leaks *last month's* return into the real signal: rank correlation −0.166 with the last-21-day
  return. MOM shows +0.018, and the fixed residual +0.008.

**3. Turnover.**
- My code gives 24.2x (residual) and 15.2x (classical) vs their 24.3 / 15.5, so the accounting matches.
- The extra turnover comes from the reversal leak in test 1. Rank autocorrelation is 0.756 for residual, 0.851
  when fixed, and 0.899 for classical. The fix cuts turnover to 19.7x.
- The first-period entry adds only about 0.14x per year.

**4. Data quality.**
- 1,212 daily returns were filtered, across all tickers from 2010 to 2026.
- With no filter, residual net is 0.48 and classical 0.41.
- Dropping any stock with a filtered return in its 504-day window gives 0.47 / 0.41.
- Bad prints don't drive the result.

**5. Delisting bias.**
- Classical net goes 0.41 → 0.35 and residual 0.46 → 0.38. Residual still beats classical.
- This is a harsh bound: it also hits acquired stocks, which mostly sit in the long leg.

## Bugs and design issues

- **No bugs found in the reported numbers.**
- **Design issue (residual signal):** the beta window includes the skip month, so through the intercept the signal
  embeds about −0.17 correlation with the last month's return (short-term reversal).
  - This raises turnover from 19.7x to 24.2x.
  - It lowers net Sharpe from 0.56 to 0.46. Gross Sharpe also drops, from 0.69 to 0.63.
  - Fix: fit betas on [i−524, i−21]. Corrected code is in `resmom/backtest.py`, column `resid_b`.
  - The fixed version by period (IS / VAL / TEST net): 0.51 / 0.39 / 0.76.

## Pre-registered verdict

Five claims were checked, and all hold:
1. RESID gross > MOM gross: 0.63 vs 0.47.
2. RESID net > MOM net: 0.46 vs 0.41.
3. RESID turnover is higher: 24.2x vs 15.2x.
4. RESID MaxDD is much smaller: −21% vs −40%.
5. Placebo p = 0.006.

The break condition (claim 2 flipping in the rebuild or in variant B) **did not happen**. The results reproduce.
Separately, the post-hoc check shows that claim 2's margin is not statistically meaningful.

## Is it good? (post-hoc context, net 10 bps, 2012-02..2026-09)

| | Classical | Residual | Residual, fixed | SPY |
|---|---|---|---|---|
| Sharpe (t-stat over 14.5 years) | 0.41 (1.6) | 0.46 (1.7) | 0.56 (2.1) | 0.79 (3.0) |
| Daily correlation with SPY | −0.05 | +0.01 | −0.05 | 1 |
| Losing years | 4 | 3 | 4 | 3 |
| 2022 return (SPY −19.5%) | +28.7% | +25.0% | +26.1% | −19.5% |

- Residual momentum spent about 5 years (1,261 sessions, roughly 2014–2018) below its previous peak.
- Mixed 50/50 with SPY at equal risk, Sharpe rises from 0.79 to 0.88 (0.98 for the fixed version), and MaxDD
  improves from −34% to −21%. This mix is sized using the full-sample volatility, so treat it as an illustration.
- So it is valid, but modest on its own. Its value is as a market-neutral diversifier.
- Still not modelled: short-borrow fees and dividends paid on shorts.

## Not covered

- Their exact code paths (tests 6–8 and 10), which need their repo.
- Dividends: prices are split-adjusted only, as in theirs.
- Borrow costs.
- Real delisting returns.
- Both the teammate's version and this rebuild use ticker-level data, so a reused ticker can splice two companies
  together. The −70/+200 filter and the gap rule catch most of these.

## Files and rerun

- `resmom/panel.py` builds the daily panel from the cached grouped bars (about 20 s, no API calls).
- `resmom/backtest.py` holds the signals, portfolios, attacks and placebo (about 1 min).
- `resmom/posthoc.py` is the paired block bootstrap of RESID − MOM net Sharpe. It is not pre-registered.

```
uv run python resmom/panel.py && uv run python resmom/backtest.py && cd resmom && uv run python posthoc.py
```
