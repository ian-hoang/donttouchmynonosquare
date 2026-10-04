# Hypothesis: Queue Sacrifice

**Written:** October 2, 2026 (America/New_York). Exact pretest timestamp must be the Git commit.
**Owner:** Team Queue Sacrifice. **Status:** Untested prototype; no real-data results.

Commit this hypothesis before the first market-data backtest. Synthetic unit tests only verify
mechanics; they do not establish predictive power or profitability.

## The sentence

In one liquid futures contract whose matching algorithm is verified to be FIFO, unusually
one-sided cancellations near the front of the best-price queue predict a subsequent price
move away from the canceled side. Canceling an executable position may reflect a liquidity
provider's changed willingness to trade. The proposed informational component is queue
position conditional on ordinary canceled quantity. Anonymous order IDs cannot identify a
trader or establish why they canceled. This is a structural/liquidity hypothesis, not an
assertion of informed trading or a demonstrated exploitable edge.

FIFO uses price and time priority, which makes an earlier position advantageous for execution.
Products can use different matching algorithms; the team's selected contract must be checked
against current product rules. The cited agricultural-market explanation is evidence for the
FIFO mechanism, not evidence that every CME product is FIFO.
[CME matching explanation](https://www.cmegroup.com/education/articles-and-reports/overview-what-makes-ags-markets-work)

## Data and exact first specification

- Databento GLBX.MDP3 MBO for one explicit, unexpired outright instrument ID at a time.
  Select the contract and fixed date range, record fees/tick size/multiplier, verify FIFO, and
  freeze those choices before examining market-data results. Do not concatenate continuous
  futures IDs into one order book. The first selected sample and all execution
  choices are frozen in `hypotheses/micro_opening_2026.md` and
  `experiments/micro_opening_2026.json` before its market-data backtest.
- Databento MBO provides order-level events and IDs. The replay must distinguish cancellation
  from execution and handle snapshots and order modifications using venue-specific semantics.
  Synthetic snapshot additions must not count as flow. [Databento MBO schema](https://databento.com/docs/schemas-and-data-formats/mbo)
- For each voluntary cancel at the best bid or ask immediately before that event, the replay
  computes `canceled_quantity / (1 + quantity_ahead_at_same_price)`. Sum these weights by side
  in completed equal-width bars. This is a deliberately simple priority proxy; it is not the
  monetary value of a place in line. It does not use order age, participant identity, or
  future execution information.
- Use ten completed bars. Let `A` and `B` be summed priority-weighted ask and bid cancels.
  The score is `(A - B) / (A + B)`, with zero for an empty denominator.
  Require at least 20 raw canceled contracts across both sides in the same window.
- Target +1 contract when score is at least 0.5, -1 when score is at most -0.5, otherwise zero.
  Recompute every completed bar; no separate discretionary holding rule. Bar width is a
  runner setting that must be predeclared before market-data testing and reported with results.
- Warm up for ten consecutive valid bars. Reset across a UTC date boundary, instrument change,
  invalid/stale/crossed quotes, or invalid cancellation quantities. UTC dates are analysis
  boundaries, not the exchange's trading-session definition.
- Decision time is after the bar completes. The engine enters only at a strictly later
  executable quote with declared latency. Same-bar prices and midpoint fills are forbidden.

## Edge source and testable predictions

- Structural constraint / liquidity withdrawal: abandoning execution priority may contain
  information beyond an ordinary depth change. Any persistence could be limited by fees,
  adverse selection, or the cost of reacting quickly enough. There is no established reason
  this information must remain tradable at the team's latency.
- Primary prediction: queue weighting adds predictive information beyond ordinary cancellation
  imbalance, after controlling for raw canceled volume, current spread and depth, recent
  signed trades, recent returns, volatility, and time of day.
- Direction: excess priority-weighted bid cancellations predict negative subsequent changes;
  excess ask cancellations predict positive changes. Compare both sides independently.
- Dose response: larger absolute scores should show larger signed subsequent changes within
  matched cancellation-activity and market-state groups. Predeclare any binning on in-sample
  data and apply it unchanged to the final holdout.

## Baseline and comparability controls

The built-in baseline replaces weighted quantities with raw at-touch cancellation quantities
in the same normalized imbalance. It uses the same ten-bar window, score threshold, raw
activity gate, valid sample, costs, latency, and risk/execution settings. On equal raw bid/ask
cancellations, the baseline is flat; Queue Sacrifice can react if queue positions differ.
With every cancellation at the front, the two scores coincide.

A P&L difference alone does not isolate information value: the strategies can have different
turnover and event selection. Compare future signed markouts on a common eligible sample,
match canceled volume and observable market state, and report turnover and both sides.
Match against recent price changes so that canceling already-stale quotes does not masquerade
as advance information. Include an ablation that removes queue weighting, and disclose every
other tested variant. These comparisons are planned research, not completed analysis.

## Costs, risk, and capacity

Use actual future bid/ask quotes, per-contract exchange/broker fees, declared extra slippage,
and finite execution latency. Report a doubled-cost scenario and longer latency scenarios;
never assume that a historical cancel could have been traded before receipt. Record the
chosen contract's units and fees rather than adopting generic basis points.

The prototype target is capped at one contract and sends a flat decision on invalid bars.
Shared execution must handle the next available executable exit; flat intent is not proof
of an immediate fill during missing data. Flatten at the configured session end, cap exposure
and loss in the runner, and report turnover, adverse moves, and available displayed depth.
No scaling or capacity claim follows from a one-contract backtest. Measure participation and
impact before proposing capital deployment.

## Kill criteria decided before results

1. Reject use on a product without verified FIFO or on data whose snapshot, fill, modification,
   or cancellation semantics cannot support causal queue reconstruction.
2. Reject the incremental hypothesis if queue weighting adds no consistent value relative to
   the ordinary-cancellation baseline on a common, state-matched sample.
3. Reject the deployable-strategy claim if returns disappear after executable bid/ask costs,
   actual fees, and feasible latency, or if profitability depends on same-bar execution.
4. Reject robustness if the result is concentrated in one day, one side, corrupted replay,
   a single finely tuned threshold, or an unreported search over variants.
5. Freeze the full pipeline and parameters before one final untouched OOS evaluation using
   the hackathon split rule. Disclose a failure without changing the locked design.
