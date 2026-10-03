# Hypothesis: The Missing Beat

**Written:** October 2, 2026 (America/New_York). **Owner:** team, Missing Beat prototype.
**Status:** speculative and untested on market data. Commit this document and freeze the experiment configuration before the first market backtest. Synthetic unit tests validate mechanics only.

The first market sample and all execution choices are now specified in
`hypotheses/micro_opening_2026.md` and `experiments/micro_opening_2026.json`.

## The sentence

In one liquid futures contract, a missing expected burst after repeated, same-direction aggressive-flow bursts predicts a short reversal when the prior price displacement remains. The proposed mechanism is the withdrawal of temporary execution demand. A disappearance of predictable flow may be more informative than an ordinary reduction in volume. We do not identify an institution, infer an actual parent order, or claim that the proposed edge survives costs or competing participants.

Persistence is uncertain. The hypothesis fails if an ordinary flow-drop signal explains the effect, the effect ends before a realistically delayed fill, or feed/timestamp aggregation creates the apparent cadence.

## Edge source and predeclared mechanism

- Candidate source: temporary liquidity demand and subsequent liquidity provision.
- A large directional bar starts a fixed `window_bars` observation window. Its phase is set using past and current information only.
- Require `cycles` confirmed, comparable bursts of the same sign at the fixed `cadence_bars` spacing. A fully observed extra burst in the gap cancels the sequence.
- Wait until the entire next scheduled window closes. Both anticipated-side volume and absolute signed volume must fall below `missing_fraction` of their reference medians.
- Fade only if the price displacement from before the earliest retained confirmed burst still exceeds `min_displacement_ticks` and retains `retention_fraction` of its peak observed during those bursts.
- Emit a one-contract target opposite prior flow and retain it for `hold_bars` completed rows. All invalid rows, session changes, and instrument changes clear the state and target. Every sequence produces at most one trade opportunity.
- The shared simulator must execute after the decision, using executable bid/ask prices and all costs. No fills at the triggering historical midpoint are assumed.

The implementation defaults (6-bar cadence, 2-bar observation window, 3 confirmed cycles, 20-contract minimum burst, 80% directional share, 50% repeat-size ratio, 20% missing fraction, 50% displacement retention, one tick minimum retained displacement, 0.25 tick size, 3-bar holding period) are engineering placeholders, not selected results. The chosen bar duration, contract, actual tick size, latency and costs must be written into the experiment manifest before testing. There is no automatic cadence search.

## Testable predictions and comparators

1. A missing scheduled burst predicts reversal more reliably than matched ordinary declines in flow when prior return, spread, signed volume, time of day and volatility are comparable.
2. More complete disappearance should strengthen the conditional effect; this is an analysis of the frozen signal, not permission to select a threshold on the holdout.
3. The supplied `baseline` uses the same burst, disappearance, displacement and holding rules, but observes the next adjacent window without requiring repeated cadence. Compare timing and sample composition as well as aggregate P&L.
   This is a broad comparator, not an isolated cadence ablation: both waiting time and confirmation count change. Before claiming cadence adds information, also match opportunities on elapsed waiting time, prior burst count, volume and displacement, then compare regular versus irregular earlier timing. That conditional analysis is not implemented by the initial runner.
4. Predeclare a placebo that shifts the expected observation phase. Report it even if it outperforms the hypothesis. Do not select the best phase afterward.

## Data and timing

- Source: Databento trades and contemporaneous best bid/ask quotes for one actual futures instrument. Dataset, contract and dates remain to be selected before research. MBO is optional for this signal; signed aggressive volume and executable quotes are required.
- Reference: [Databento trades schema](https://databento.com/docs/schemas-and-data-formats/trades) and [MBP-1 schema](https://databento.com/docs/schemas-and-data-formats/mbp-1). These establish input semantics, not evidence for the trading hypothesis.
- Use completed, equal-width bars with a sorted, unique UTC end-time index. Unknown aggressor-side trades contribute to total volume but must not be guessed into buy or sell volume. Each row contains the actual instrument ID and a `valid` fresh, uncrossed-quote flag.
- This prototype uses the shared UTC-calendar-date `session` label for resets; it does not claim to model an exchange trading session. The shared normalizer must mark data gaps invalid rather than compress elapsed time into fewer bars.
- Verify event-time versus receive-time semantics and repeated timestamps. Inspect raw events around detections to rule out packet batching, artificial bar boundaries, duplicate executions, stale quotes and scheduled exchange activity as the source of periodicity. Avoid counting both trade and fill messages as separate executions.
- No continuous-contract roll boundary may form one sequence. Contract changes reset state. Do not bridge missing quotes or treat a snapshot as newly occurring traded flow.

## Costs, risk and evaluation freeze

Choose a liquid contract and a feasible trading horizon before the test. Charge bid/ask spread, contract-specific fees, latency and any additional slippage in the shared simulator; rerun the frozen specification at double costs. No fee or capacity number has been established yet. A one-contract target is a prototype exposure cap, not a portfolio risk model; apply the harness's loss, concentration and participation controls.

Use the track's chronological holdout rule and open it only after the model, sample, data provenance, clock, costs and analysis are frozen. Record all variants and failures across teammates. Report separate in-sample and held-out performance, signal counts, turnover, drawdown and cost sensitivity. Prefer session/block-aware uncertainty estimates because nearby observations are dependent.

## Kill criteria (before market results)

- Reject an economic edge if it disappears after achievable latency, executable spread/fees, or double-cost stress.
- Reject the cadence mechanism if the ordinary-flow-drop comparator or predeclared timing placebo explains equivalent conditional performance.
- Reject an apparent cadence if raw-event inspection attributes it to feed batching, duplicates, timestamp processing or the chosen bar boundary.
- Do not promote the result if there are too few independent sessions and detections to support the claimed uncertainty; determine the minimum sample requirement in the frozen experiment manifest.
- Reject a result dependent on one isolated parameter setting, one exceptional session, future information, or changing the final holdout after inspection.
