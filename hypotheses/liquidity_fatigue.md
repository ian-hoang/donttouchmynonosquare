# Hypothesis: Liquidity Fatigue

**Written:** October 2, 2026 (America/New_York). **Status:** first market experiment
specified in `hypotheses/micro_opening_2026.md` and `experiments/micro_opening_2026.json`;
no market-data performance results at preregistration.
Commit this hypothesis and freeze the data/experiment specification before the
first market-data backtest. Synthetic unit tests check implementation only.

## The sentence

In one liquid futures contract, comparable aggressive bursts followed by
progressively worse opposing-depth recovery predict greater continuation after
a subsequent burst in that direction. Liquidity suppliers may have limited
inventory capacity or revise their willingness to absorb repeated demand. The
proposed signal measures this changing response, rather than merely thin depth
at the decision time. Its persistence and economic profitability are unknown.

## Evidence and proposed extension

[Xu et al., *Limit-order book resiliency after effective market orders: Spread,
depth and intensity*](https://arxiv.org/abs/1602.00731) studies recovery after
different types of effective market orders in Chinese stocks. It supports
studying the recovery process; it does not establish this signal, its transfer
to futures, or executable profitability. Our proposed extension is deterioration
across several comparable, completed recovery episodes.

## Predeclared prototype

- Use one actual contract and completed, equally spaced UTC bars. Initial
  engineering configuration: one-second bars, 60 preceding bars of warmup,
  five following bars per recovery observation, and a ten-bar holding period.
  These are placeholders, not fitted values or empirically justified horizons.
- A burst has absolute signed volume at least 2.5 times the median total volume
  in the preceding 60 bars (with a one-contract floor), and absolute signed
  volume divided by total volume at least 0.6. The current bar never enters its
  own reference median.
- An eligible recovery episode also requires opposing best-quote size to fall
  at least 10% from the previous bar. Record the pre-burst depth, post-burst
  depth, and immediate directional mid-price impact per signed contract.
- Observe exactly the next five complete bars. A further burst contaminates
  the pending observation, so discard it and begin a fresh observation if
  eligible. Incomplete observations never enter the history.
- Refill is `(terminal depth - post-burst depth) / (pre-burst depth -
  post-burst depth)`, clipped to [0, 2]. Recovery delay is the first following
  bar reaching 90% of pre-burst depth, or six if never reached. These are
  best-quote depth proxies: the quote price may change. They do not identify
  the same resting liquidity or participants.
- On a subsequent burst, inspect the last three completed episodes in the
  same direction, all no more than 600 bars old. Including the current burst,
  the largest signed burst must be at most twice the smallest.
- Require at least two monotone deteriorations across those episodes: refill
  falls by at least 0.2; recovery delay increases by at least one bar; or
  immediate impact per signed contract increases by at least 25% from a
  strictly positive initial impact. Intermediate episodes must preserve the
  direction of each qualifying change. A burst can trigger without itself
  having a measurable depth drop; its prior completed observations establish
  the fatigue condition.
- Enter in the current burst direction only after the decision bar. The
  shared simulator must execute at a later available bid/ask with explicit
  latency, not the decision mid. Hold one contract for ten decision bars;
  ignore further entry triggers until flat. Invalid data, a new UTC date, or
  an instrument change clears the signal and all feature state. Such a reset
  requests flattening; it cannot assume an execution on a missing quote.

## Data and costs to freeze before research

Use Databento trades and reconstructed top-of-book quotes; MBO may supply both
and also supports the other team ideas. Record dataset, actual contract ID,
dates, bar width, trade-sign convention, freshness rule, and matching/feed
limitations. No continuous-contract splice is permitted within a run. Exclude
or explicitly handle trading halts, resets, missing messages, auctions and
session breaks. UTC dates are a simple prototype boundary, not exchange
trading sessions. Unknown aggressor sides cannot count as signed flow.

Use executable bid/ask fills, product-specific multiplier, tick size, fees and
adverse slippage in the shared simulator. These values are deliberately not
invented before choosing the contract. Report base and doubled fee/slippage
costs and longer execution delays; include the spread in every fill. Report
turnover, exposure, drawdowns, event counts and volume participation. One
contract is a research sizing choice, not a capacity estimate.

## Baseline, ablations and kill criteria

1. Compare to the included ordinary directional-burst baseline with identical
   burst thresholds, holding horizon and execution assumptions.
2. At event level, match current spread, depth, signed flow, recent returns,
   volatility and time of day. Test whether recovery history adds predictive
   information beyond those variables. Bootstrap by day, not overlapping bars.
3. Ablate refill, recovery delay and impact separately; disclose every variant
   and failed experiment. Do not select a subset from the final holdout.
4. Kill the economic claim if the incremental effect disappears with these
   controls, after executable costs/delay, or outside a few isolated sessions.
   Kill the recovery interpretation if price-level changes explain the effect
   or equal-size bursts do not show the proposed worsening response.
5. Treat insufficient events as inconclusive. Freeze an event-count threshold
   and uncertainty criterion before examining strategy P&L. Avoid optimizing
   thresholds to make a sparse experiment appear significant.

Explore only the prescribed in-sample partition. Freeze code, parameters,
data identity and costs before the single final evaluation of the most recent
20% of history or two years, whichever is shorter. This module does not enforce
that research gate itself and does not establish a profitable strategy.
