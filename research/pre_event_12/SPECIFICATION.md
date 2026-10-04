# Pre-earnings ideas 1 and 2: frozen research design

Written 2026-10-03 before computing any returns for these strategies. Event and
quote coverage may be audited without observing outcomes. The input inventory,
this specification and code are hashed before the first evaluation. Later fixes
must be explained and all changed runs retained. No threshold or holding-window
selection is permitted after inspecting outcomes.

## Scope and primary hypotheses

1. High 30-calendar-day ATM option-implied volatility predicts positive stock
   returns before earnings. The high group is above the 80th percentile of valid
   2023 calibration observations, fixed for all later years. This is a temporal
   calibration adaptation of the literature's cross-sectional sort, not an exact
   replication. Do not substitute realized volatility if IV is missing.
2. A large previous earnings reaction predicts positive returns before the next
   release. Signal is the maximum three-session market-adjusted return around the
   previous four verified quarterly releases, all fully observed by signal time,
   within 450 calendar days. The high group is above the 90th percentile of valid
   2023 calibration observations. Four past releases are required. Do not use an
   average reaction or generic momentum as an undisclosed substitute.

Selection thresholds are calculated separately for the two holding windows;
the five-session result cannot rescue a failed ten-session primary hypothesis.
Thresholds depend on historical features only, never subsequent returns.
At least ten valid calibration observations are required for each threshold;
otherwise that strategy/window is reported as unavailable without lowering the
minimum after observing outcomes.
For jackpot history completeness, the four successive prior quarterly release
dates must be separated by 40-140 days, and the latest must be within 150 days of
signal time. Failed recent reactions are not replaced by older available ones.

## Universe and event knowledge

Fixed top 150 companies by cached trailing 63-session dollar volume at
2022-12-30. No inclusion based on future performance. The underlying cached
company panel has retrospective entity/share-class mapping limitations; disclose
them. Prices include available cash dividends and split adjustments, but do not
include a complete delisting-payment database.

Only issuer-identifiable advance press releases with explicit future earnings
release dates qualify. Dates of calls alone do not qualify. Original issuer/wire
pages are checked where accessible. Require notice publication by signal time.
Stock symbols in news metadata alone cannot establish issuer identity.

The nominal period is 2023 feature calibration, 2024 initial evaluation,
2025-2026 temporal validation. Report actual data coverage; do not call the final
period pristine out-of-sample because this workspace has many previous studies.
Sparse or absent calendar coverage is a limitation, not evidence of no events.
Publisher timestamps are public-availability evidence; historical vendor ingest
times and subsequent webpage revisions are not fully available.

Known revisions before entry replace previous schedules. Unexpected post-entry
release changes are flagged and retained, not retrospectively excluded to remove
bad outcomes. Actual earnings release dates are distinct from SEC filing times.

## Trading clock

Let D be the first trading session on/after the advertised release calendar date.
Primary exit X is session D-1, at 15:55 ET (12:55 on an early close).
Primary entry E is X-10 trading sessions, at 15:56 ET (12:56 early close).
Features use E-1 at 15:55 ET. This one-session feature lag makes this a conservative
adaptation, not exact replication of papers measuring IV eleven days before.
Secondary entry is X-5 sessions, with the same one-session feature lag.
Notice must have been public by the feature timestamp. Neither realized return
nor event-day volume may determine the assumed release timing or exit date.

## Options feature

Use valid stock NBBO and the nearest paired ATM call/put strike for each of two
expiries bracketing 30 calendar days within 21-45 days. Standard 100-share
contracts only. Maximum quote age 60 seconds; maximum relative option spread
25%; nearest strike within 5% of parity-implied forward; implied forward within
10% of stock midpoint. No opportunistic search across farther strikes.
Interpolate total variance. Paired call-put parity with fixed 4% discount rate
absorbs much of carry/dividends; American exercise is only approximated by Black
pricing. These are quote-implied estimates, not OptionMetrics vendor surfaces.
Quote-quality exclusions are applied before observing outcomes and reported.

## Execution and costs

Use the first valid stock NBBO at/after each scheduled trading time, before the
session close. Buy at ask, sell at bid. Add 1 bp adverse slippage and 0.5 bp fees
per side. Entry spread must be at most 20 bp. Never filter an exit because its
spread is unfavorable. Report any missing exits as unresolved; do not quietly
discard them. Doubled costs double observed half-spreads and both added charges.

Per-event net long return includes available cash dividends and splits. A
separate matched-window SPY total return gives market-adjusted performance; this
is an opportunity-cost comparison, not a claim of a physically shorted hedge.
Show the same-event all-eligible-stock baseline under the same costs.
Also report a secondary beta-adjusted return using an OLS beta from up to 252
daily stock/SPY returns ending before signal day, minimum 120 observations. This
diagnostic is not a traded hedge and does not remove all risk-factor exposures.

Cash portfolio: start with $100,000, $10,000 maximum per position, whole shares,
no leverage, no overlapping positions in the same stock. Need sufficient cash
and displayed entry ask size. Simultaneous entries sort descending signal then
ticker. Exits at 15:55 precede entries at 15:56. Cash earns zero. Daily adjusted
closes mark holdings; dividends accrue on ex-date. Each strategy and period has
its own portfolio. No parameter search or reinvestment-dependent sizing.
If an exit's displayed bid size is smaller than the position, retain the trade
but flag the cash-portfolio result as relying on unverified deeper liquidity.
Use actual fill timestamp ordering if an exit is delayed beyond the entry time.

## Inference and interpretation

Report counts, issuers, mean/median net return, win rate, gross return,
market-adjusted net return, worst/best event, year splits, doubled costs,
cash-portfolio P&L, deployment, drawdown and daily Sharpe with zero cash yield.
Bootstrap whole entry-week clusters (3,000 draws, fixed seed) for confidence
intervals. Events are not independent observations. Broad market beta and
sector concentration can still affect these comparisons.

No convincing alpha claim with fewer than 100 selected events or 20 issuers;
even above that threshold, positive held-period results and a confidence interval
above zero on market-adjusted returns after stressed costs are necessary, not
sufficient, evidence. Every planned variant is reported, including failures.

An additional predeclared idea-1 execution variant requires a recovery signal
at E 15:55, before the 15:56 entry: spread is strictly narrower than at S 15:55,
bid dollar depth is at least its S value, current spread is no greater than the
median over the previous 20 sessions at the same clock time, and current bid
dollar depth is at least the corresponding historical median. At least 15 valid
historical quotes are required. The high-IV selection threshold stays identical.
This variant tests the proposed liquidity-recovery extension; report it even if
it makes no trades. No other liquidity thresholds are searched. Extended-hours
execution advantage remains outside this liquid-session pilot.
