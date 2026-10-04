# Hypothesis: treasury_auction (dealer inventory around Treasury coupon auctions)

**Written:** Fri Oct 2 2026, 9:14 PM ET, before any data for this idea was downloaded · **Owner:** Ian Hoang's team

## The sentence
In **US Treasury futures (CME ZT, ZF, ZN, ZB, UB)**, **an upcoming coupon auction in the matching maturity** predicts
**the future cheapening in the days before the auction and recovering after the 13:00 ET result**, because **primary
dealers must absorb new supply announced a week ahead, and end investors don't commit capital in time, so dealers
demand a price concession to warehouse the bonds**. It persists because **issuance has grown much faster than dealer
balance sheets, and the Treasury and auction buyers pay the concession rather than spread purchases out**. It fails if
**auction windows earn nothing beyond matched non-auction windows (a placebo), e.g. if the 2022 bond selloff is the only
thing making the short look good**.

## Edge source
- [x] Risk premium (compensation for dealer inventory risk)
- [ ] Behavioral bias
- [x] Structural constraint (fixed, pre-announced issuance; limited dealer balance sheets)
- [x] Liquidity provision (the post-auction recovery)

## Testable predictions
1. Pre-auction leg: short the matching future from the close k business days before the auction to 13:00 ET on
   auction day earns a positive return, net of costs and net of a matched non-auction placebo.
2. Post-auction leg: long from the result to the next day's close earns a positive return.
3. Dose-response: the concession grows with the DV01 being auctioned (offering amount x maturity).
4. A curve-neutral version (short the auctioned maturity, long a neighbouring one, DV01-matched) keeps most of the
   effect, showing it is supply-specific rather than a general rate move.

## Data
- Databento GLBX.MDP3 `ohlcv-1h` for ZT, ZF, ZN, ZB, UB (volume-ranked continuous `.v.0`/`.v.1`, roll-safe), 2010-07 onward.
- Auction calendar and offering amounts: U.S. Treasury Fiscal Data API (free, public), cited in the note.
- Maturity map: 2y/3y -> ZT, 5y -> ZF, 7y/10y -> ZN, 20y -> ZB, 30y -> UB. TIPS and FRNs excluded.
- Known issues: CPI releases often land in 10-year auction weeks (flagged); reopenings count as auctions.

## Costs
- 1 bp per side (Treasury futures are among the most liquid contracts: ZN tick 1/64 on ~110 = 0.14 bp; fees dominate).
  Also reported with costs doubled.

## Kill criteria (decided now, before results)
- Net pre-auction return no better than the placebo windows in-sample.
- The entry offset k is chosen in-sample only from {1, 2, 3, 5}, and every choice tried is disclosed.
