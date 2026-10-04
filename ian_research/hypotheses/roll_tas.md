# Hypothesis: roll_tas (Roll-Flow, leg 1: the Trade-at-Settlement premium)

**Written:** Fri Oct 2 2026, 9:14 PM ET, before any data for this idea was downloaded · **Owner:** Ian Hoang's team

## The sentence
In **WTI crude oil futures (CME CL)**, the **volume-weighted premium at which Trade-at-Settlement (TAS) contracts trade
before 14:00 ET** predicts **the front contract's move from 14:15 ET into the 14:28-14:30 ET settlement window, and a
partial reversal after settlement**, because **index funds, commodity ETFs and other settlement-benchmarked hedgers buy
or sell through TAS whatever the cost, and the dealers who take the other side hedge that inventory by trading the
outright during the settlement window**. It persists because **the benchmark users care about tracking error, not a few
ticks, and the dealer's hedging pressure is the compensation for warehousing the risk**. It fails if **the TAS premium
carries no information about the window move, or the move doesn't reverse (the impact is permanent, i.e. informed)**.

## Edge source
- [ ] Risk premium
- [ ] Behavioral bias
- [x] Structural constraint (benchmarking to the settlement price)
- [x] Liquidity provision (the reversal leg)

## Testable predictions
1. Leg A: sign(premium) predicts the sign of the 14:15 ET -> settlement return.
2. Leg B: after settlement, price partly reverses the settlement-window push (14:30 -> 16:30 ET).
3. Dose-response: both effects grow across quintiles of |premium| x TAS volume / ADV.
4. Mechanism check: both are stronger on commodity-index roll days (GSCI business days 5-9 of the month) than on other days.

## Data
- Databento GLBX.MDP3: `trades` for parent `CLT.FUT` (TAS contracts, 2012 onward; existence confirmed), `ohlcv-1m` for
  the front outright, `statistics` for official settlement prices.
- In-sample 2012-01 to the out-of-sample start (most recent 2 years); out-of-sample locked until the final run.
- Known issues: TAS prices are tick offsets from settlement, not prices; map each TAS month (CLT X6) to its outright (CL X6);
  exclude TAS calendar spreads; CL time zone is Central (times above are ET).

## Costs
- Assumed 2 bps per side: CL tick 0.01 on ~$70 = 1.4 bp, half-spread + slippage of one tick plus ~$2.50/contract fees
  (`gd.futures_cost_bps`); the exit at settlement uses TAS, which costs its own premium (charged inside the 2 bps).
  Results are also reported with costs doubled.

## Kill criteria (decided now, before results)
- In-sample, top-minus-bottom quintile window return under 1 tick, or not monotone across quintiles.
- Net-of-cost in-sample Sharpe below 0.3 for both legs, or the effect exists only in one sub-period (e.g. 2020).
