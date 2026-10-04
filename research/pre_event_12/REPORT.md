# Pre-earnings ideas 1 and 2: backtest pilot

**Result: no convincing alpha demonstrated.** The ten-session high-IV and earnings-jackpot base rules lost money in the later evaluation. The additional liquidity-recovery rule made money on only two later Nvidia trades. This is a small, coverage-selected pilot, not a broad-universe replication or proof that the underlying hypotheses cannot work.

## Primary results

Each event return is on the stock position, net of observed bid/ask spread, 1 bp adverse slippage per side and 0.5 bp fees per side. Cash P&L is a separate $100,000 unlevered portfolio with maximum $10,000 per position, whole shares and idle cash earning zero.

| Evaluation | Rule | Trades / issuers | Mean net / trade | Mean net less SPY | Mean beta-adjusted | Cash P&L |
|---|---|---:|---:|---:|---:|---:|
| 2024 | High implied uncertainty | 5 / 2 | +5.00% | +2.74% | -0.25% | $2,489 |
| 2024 | High uncertainty + liquidity recovery | 1 / 1 | +10.77% | +7.14% | +1.81% | $1,074 |
| 2024 | Past earnings jackpot | 2 / 1 | +2.61% | +1.01% | -1.14% | $519 |
| 2025–Sep 2026 | High implied uncertainty | 7 / 4 | -0.96% | -2.41% | -2.25% | -$656 |
| 2025–Sep 2026 | High uncertainty + liquidity recovery | 2 / 1 | +2.31% | +2.52% | +3.49% | $461 |
| 2025–Sep 2026 | Past earnings jackpot | 1 / 1 | -5.80% | -7.14% | -9.14% | -$573 |

2023 observations set feature thresholds only. No 2023 strategy P&L was evaluated. Code, inputs and parameters were hashed before the first 2024 result. Final audit found and repaired one calendar-boundary bug after the initial evaluations; both periods were rerun with the same trading rules and parameters. See [CALENDAR_REPAIR.md](CALENDAR_REPAIR.md) for the preserved originals and comparison. These years have been used elsewhere in this workspace, so the later period is temporal validation, not a pristine research holdout.

![Validation cash portfolio P&L](outputs/validation_equity.png)

## All declared variants

| Period | Rule | Hold | Costs | Trades | Mean net | Cash P&L |
|---|---|---:|---:|---:|---:|---:|
| screen | High implied uncertainty | 10 | 1× | 5 | +5.00% | $2,489 |
| screen | High implied uncertainty | 10 | 2× | 5 | +4.95% | $2,467 |
| screen | High uncertainty + liquidity recovery | 10 | 1× | 1 | +10.77% | $1,074 |
| screen | High uncertainty + liquidity recovery | 10 | 2× | 1 | +10.73% | $1,070 |
| screen | Past earnings jackpot | 10 | 1× | 2 | +2.61% | $519 |
| screen | Past earnings jackpot | 10 | 2× | 2 | +2.56% | $509 |
| screen | High implied uncertainty | 5 | 1× | 7 | +1.09% | $749 |
| screen | High implied uncertainty | 5 | 2× | 7 | +1.05% | $720 |
| screen | High uncertainty + liquidity recovery | 5 | 1× | 0 | — | $0 |
| screen | High uncertainty + liquidity recovery | 5 | 2× | 0 | — | $0 |
| screen | Past earnings jackpot | 5 | 1× | 2 | +0.07% | $3 |
| screen | Past earnings jackpot | 5 | 2× | 2 | +0.02% | -$5 |
| validation | High implied uncertainty | 10 | 1× | 7 | -0.96% | -$656 |
| validation | High implied uncertainty | 10 | 2× | 7 | -1.01% | -$694 |
| validation | High uncertainty + liquidity recovery | 10 | 1× | 2 | +2.31% | $461 |
| validation | High uncertainty + liquidity recovery | 10 | 2× | 2 | +2.28% | $454 |
| validation | Past earnings jackpot | 10 | 1× | 1 | -5.80% | -$573 |
| validation | Past earnings jackpot | 10 | 2× | 1 | -5.87% | -$579 |
| validation | High implied uncertainty | 5 | 1× | 3 | -2.13% | -$641 |
| validation | High implied uncertainty | 5 | 2× | 3 | -2.18% | -$656 |
| validation | High uncertainty + liquidity recovery | 5 | 1× | 0 | — | $0 |
| validation | High uncertainty + liquidity recovery | 5 | 2× | 0 | — | $0 |
| validation | Past earnings jackpot | 5 | 1× | 1 | +2.47% | $246 |
| validation | Past earnings jackpot | 5 | 2× | 1 | +2.39% | $238 |

The positive five-session jackpot result is one Shopify trade. It cannot rescue the negative ten-session primary result. The liquidity-recovery variant has three trades across both evaluation periods, all Nvidia. No parameter was changed to increase activity or improve these results.

## Uncertainty and comparison

| Later-period primary rule | Net mean 95% interval | Median net | Win rate | Cash max drawdown | Mean capital deployed | All eligible baseline net / trade |
|---|---:|---:|---:|---:|---:|---:|
| High implied uncertainty | -5.09% to +3.74% | -2.93% | +42.86% | -1.98% | +1.59% | +0.52% (19 events) |
| High uncertainty + liquidity recovery | -5.55% to +10.18% | +2.31% | +50.00% | -0.99% | +0.47% | +0.52% (19 events) |
| Past earnings jackpot | — to — | -5.80% | +0.00% | -1.03% | +0.21% | +2.33% (28 events) |

Intervals resample whole entry weeks, using 3,000 fixed-seed draws. They are not reliable evidence with one or two trades, and do not remove issuer/sector dependence. Market-adjusted returns subtract matched-window SPY total returns. Beta-adjusted returns subtract lagged OLS beta times SPY returns; this is a risk diagnostic, not a traded hedge or complete factor model.

## Data and exclusions

- The starting universe was the 150 most liquid names at December 2022, selected before the study. Original issuer announcements produced 110 completed scheduled earnings events across 14 issuers in 2023–September 2026. This is an archive-coverage sample; inaccessible archives and missing provider coverage materially limit representativeness.
- Every accepted calendar notice was checked against its original body. 73 completed events also have exact-date matches to results press releases. A separate SEC earnings-exhibit dateline history supplies prior quarterly earnings dates. No filing-acceptance timestamp is treated as the earnings release timestamp.
- After advance-notice timing and study-date filters, there are 191 event/window rows across 13 issuers: 89 ten-session and 102 five-session. The ten-session split is 28 calibration, 26 screen and 35 validation events. A notice must exist by the lagged signal time.
- Of 192 retrieved option feature observations, 114 passed the fixed freshness/spread/maturity rules; one failed-IV observation belongs to the subsequently excluded future event. Quote coverage varies strongly by issuer. Missing IV was never replaced with realized volatility. All 3,165 stock quote inputs were retrieved successfully.
- Actual market data came from the existing Massive subscription and cached stock data, not a new Databento purchase. No paid data credits were consumed.
- Price data include splits and available dividends. The inherited company panel has retrospective entity/share-class mapping limitations and lacks a complete delisting-payment history. Present-day archived publication timestamps do not fully establish historical vendor ingestion or revision history.
- No nearby contradictory release datelines were found in the independent schedule check. Unmatched releases are not proven free from early publication. Unscheduled news remains a risk.

## Exact implementation

See [SPECIFICATION.md](SPECIFICATION.md) for the rules frozen before outcomes. For an advertised release on session D, exit at D−1 15:55 ET; enter ten sessions earlier at 15:56 ET. The five-session secondary rule uses the same exit. Features are observed one session before entry. Early-close clocks are adjusted. Orders use the first valid subsequent NBBO, with whole-share capacity and actual fill timestamps.

The high-IV signal is an approximate constant-30-day ATM volatility reconstructed from historical call/put NBBOs and put-call parity. American exercise and a fixed 4% rate are approximations. The jackpot signal is the maximum market-adjusted three-session reaction among four prior verified releases, with availability and quarterly-cadence checks. Thresholds are fixed percentiles of 2023 calibration events, an adaptation of published cross-sectional sorts rather than an exact paper replication.

The liquidity extension uses only information available a minute before entry: spread must improve from the prior session and be no greater than its prior-20-session same-clock median; bid dollar depth must recover relative to both comparisons. No extended-hours execution was simulated. Therefore these results do not test whether premarket or after-hours trading offers an advantage.

## Verification and reproducibility

- Ten financial/timing regression tests and nine calendar-parser regression checks passed.
- Tests cover bid/ask losses, split/dividend accounting, future-information exclusion, missing recent earnings, missing exits, future dates outside calendar coverage and delayed exits that cannot fund earlier entries.
- No chosen trade was dropped for a bad realized return or unfavorable exit spread. Unresolved exits would stop evaluation. All simulated positions fit displayed entry size; selected exits also fit displayed bid size.
- Independent QA reconciled all 256 return rows and 20 nonempty cash portfolios. All 22 unique selected event/window trades across variants exit before a verified actual release date; 14 of 128 unselected/selected evaluation baseline windows lack independently verified actual releases. See `options_final_verification.json`.
- Inputs and implementation are recorded in `data/frozen_manifest.json`; all trade-level rows, equity paths, thresholds, counts and summaries are in `outputs/`.

```sh
.venv/bin/python research/pre_event_12/run.py --period screen
.venv/bin/python research/pre_event_12/run.py --period validation
.venv/bin/python research/pre_event_12/report.py
```

The cached licensed inputs are required for reproduction and remain excluded from Git. Results do not justify live deployment. A broader historical announcement calendar, more issuers and a fresh validation period are needed before estimating a dependable edge.
