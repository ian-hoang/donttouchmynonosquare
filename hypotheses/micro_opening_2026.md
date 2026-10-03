# Frozen first market-data experiment: all three intraday hypotheses

This specification is written before market-data strategy results. It accompanies
the existing Liquidity Fatigue, Queue Sacrifice and Missing Beat hypotheses.
The exact parameters and scenarios are in `experiments/micro_opening_2026.json`;
the hypothesis/config Git commit is the preregistration timestamp. The purpose is
an honest initial screen, not parameter selection or a claim of proven alpha.

## Fixed universe and sample

- Databento GLBX.MDP3 MBO, raw outright **ESU6**, instrument **42140870**.
- Twenty-five weekdays, **2026-08-03 through 2026-09-04**, chosen before P&L.
  Restrict analysis to **09:30–10:30 America/New_York**, one-second completed bars.
  Reconstruct from each UTC-midnight snapshot through 14:31 UTC. The hour is a
  cost-bounded liquid-market screen; results do not generalize to the full day.
- The track's elapsed-time split applied to August 3 13:30 UTC through September
  4 14:30 UTC gives **2026-08-29 04:42 UTC**. Thus the first twenty sessions,
  August 3–28, are IS. **August 31–September 4 are reserved and remain unopened.**
  Never shorten the nominal full sample to reclassify observed IS as a new OOS.
- API metadata estimated all 25 opening-hour reconstruction requests at about
  **$11.26**. This does not mean only one hour of source records is downloaded:
  the book must be reconstructed from midnight. Download only IS initially and
  reserve every charged attempt against a cumulative **$20** ceiling.
- Contract definition retrieved for August 3 reports `match_algorithm=F`,
  `min_price_increment=0.25`, and `unit_of_measure_qty=50`. Use **$50/point**
  and **$12.50/tick**, consistent with CME's E-mini specifications. The undefined
  `contract_multiplier` sentinel is not used. FIFO is verified for this actual
  contract; no assumption that all CME futures use FIFO is made.
  [CME specifications and matching FAQ](https://www.cmegroup.com/articles/faqs/frequently-asked-questions-micro-e-mini-equity-index-futures.html)

## Frozen signals and execution

Use each module's current DEFAULTS unchanged; the JSON stores every value.
No search over parameters, cadence, bar widths, markets, or dates follows the
results. Compare every signal with its already-written ordinary baseline.

Base case: one contract, observed bid/ask spread plus an assumed **$2.50 fee per
side** and **one additional adverse tick per side**, **100 ms nominal latency**
rounded to a strictly later one-second grid point. The fee is an assumption,
not a retrieved personal broker schedule. Initial accounting capital is $100,000;
this is not a margin or capacity claim. Four-tick maximum entry spread, $100
trade stop, $300 daily loss brake, 30-second maximum hold, and scheduled flat
at 10:30 ET. New price-triggered risk exits must also respect latency; pending
exits cannot assume a fill during bad data. Stops can lose more than their threshold.

Run four predeclared scenarios for each signal and baseline:

1. Base case.
2. All trading frictions doubled, including spread.
3. Three-second execution latency, otherwise base assumptions.
4. Spread-only execution with zero explicit fee and extra slippage, still delayed.
   This is an optimistic diagnostic, **not a deployable cost assumption**.

Book replay must preserve receive/message order, snapshot priority and F_LAST,
exclude executed removals from voluntary cancel flow, and reject corrupt or
incomplete books. Invalid bars reset signal history. Data-quality corrections
are allowed before results but must be tested and disclosed; they are not
permission to change economic thresholds after losses.

## Evidence and interpretation decided before P&L

Report each of the 24 signal/baseline/scenario combinations, failures included:
net dollar P&L, session P&L, closed position episodes, turnover, drawdown, fees,
exposure, trigger counts, and data validity. A direct reversal within a continuously
held exposure is one flat-to-flat episode in the evidence helper and must be labeled.
Use seeded, five-session block-bootstrap intervals on daily P&L and paired daily
differences to the baseline; 5,000 repetitions, seed 1729. Intervals remain
exploratory and are withheld below twenty sessions. Require at least **100 closed
episodes across twenty sessions** to even consider a positive screen informative;
this threshold is not a statistical guarantee. Report sparse signals as inconclusive.

A negative base-case result rejects this fixed implementation as currently
tradable on this sample. A positive result is only a candidate, particularly if
it fails doubled costs, slower latency, or is concentrated in a few days.
There are three hypotheses and many correlated comparisons: no unadjusted
95% interval alone establishes a discovery. Do not choose only the best row.

Missing Beat's baseline changes confirmation count and waiting time; matched
cadence controls and timing placebos are still needed for a cadence claim.
Fatigue needs control for moving-best-quote level changes and current market
state. Queue Sacrifice needs common-sample markouts and state/turnover controls.
No capacity, market-neutral alpha, significance, or live-trading conclusion is
established by this screen. Preserve the final holdout for a frozen final design.
