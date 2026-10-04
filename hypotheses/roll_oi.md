# Hypothesis: roll_oi (Roll-Flow, leg 2: how much roll is still left, from open interest)

**Written:** Fri Oct 2 2026, 9:14 PM ET, before any data for this idea was downloaded · **Owner:** Ian Hoang's team

## The sentence
In **16 liquid CME commodity futures** (CL HO RB NG ZC ZS ZW KE ZL ZM LE HE GF GC SI HG), **the share of open interest
still sitting in the front contract, relative to its normal level at the same point of the roll cycle**, predicts **the
front-vs-next calendar spread over the following days**, because **index funds (GSCI rolls on business days 5-9, BCOM on
6-10) and speculators without delivery capacity must mechanically move positions out of the front contract on a known
schedule, and the commercials and spread traders who absorb that flow are paid to do it**. It persists because **the
roll schedules are fixed in published index rules and arbitrage capital for calendar spreads is limited**. It fails if
**the residual front share carries no information beyond the calendar (a plain day-of-month dummy does as well), or the
effect has fully decayed since publication (Mou 2010)**.

## Edge source
- [ ] Risk premium
- [ ] Behavioral bias
- [x] Structural constraint (published roll schedules, delivery constraints)
- [x] Liquidity provision

## Testable predictions
1. Roll leg: during business days 1-9, a higher-than-normal front OI share (more roll still to come) predicts the
   front weakening against the next contract.
2. Liquidation leg: in the final 5 trading days before the front contract's expiry, the front strengthens against the
   next contract in proportion to the front OI still open (the "liquidation premium" of Yan, Irwin, Sanders & Smith 2024).
3. Dose-response: spread returns rise across terciles of the residual share.
4. The signal beats a calendar-only placebo (same windows, constant size).

## Data
- Databento GLBX.MDP3 `statistics` (open interest, settlement) for `.c.0` and `.c.1` of each root, 2010-07 onward
  (priced at ~$2), plus contract expirations from `definition` or symbology.
- Known issues: OI for day T is published on T+1 (Friday's on Sunday), so the signal for day T is only used from the
  next session; returns are computed within each contract (no roll jumps).

## Costs
- 2 bps per side on each leg of the spread (conservative: exchange-listed calendar spreads usually trade one tick wide).
  Also reported with costs doubled.

## Amendment (Fri Oct 2 2026, ~9:50 PM ET, before any roll_oi backtest was run)
Universe narrowed to CL, HO, RB, NG, HE, GF. In grains and metals the first notice day comes before the last
trading day, so the calendar-front contract (`.c.0`) sits in its delivery month for weeks; a speculator can't
hold it there without delivery risk. Energy contracts (no notice before expiry) and cash-settled livestock (HE, GF)
can be held to expiry. Days to expiry come from Databento `definition` (contract expiration), not from realized rolls.

## Kill criteria (decided now, before results)
- Less than one tick per event after costs, or the sign flips in the most recent in-sample third.
- No improvement over the calendar-only placebo.
