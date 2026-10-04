# Profit search: rules written before results (2026-10-03 ~02:20 ET)

Ian's goal: a strategy that **makes money after costs**, not only one that "loses less". Written
after V001-V006 and before this search.

## Costs: measured, not assumed
- The key has option quotes. For every traded leg, read the last bid/ask before the close on the
  entry session.
- Cost = half the spread to get in, plus the same dollar half-spread to get out (spreads in dollars
  are stable for a contract), plus 1 bp each way for shares.
- Where a quote is missing, use the median for that leg type.
- The notebook's 5%-of-premium-each-way haircut is kept as a pessimistic sensitivity.

## Search space
- **Categories:** every tag with ≥ 15 company-days in 2024-2025, plus groupings written down earlier:
  - the scan's 4 combinations
  - G's RESOLVED and CREATED classes
  - "all non-earnings 8-Ks"
- **Trades:** the 5 strategies × 9 fixed horizons.
- **Settings:** 3-6m options, 5% OTM, entry at the close of the session after the filing date.
- **Window:** in-sample 2024-2025 only. The 2026 window stays closed.

## A cell "passes" only if all of these hold
1. **Profitable:** mean net P&L per trade > 0, t ≥ 2 (clustered by company).
2. **Because of the 8-K:** the event trade beats the same trade on quiet same-day peers (top-100
   companies with no 8-K within ±5 days), t ≥ 2.
3. **Not a one-horizon spike:** an adjacent horizon also beats peers with t ≥ 1.5.
4. **Not one year:** the gap over peers is positive in both 2024 and 2025.

## Luck check
- For each category, build 400 fake categories of the same size out of quiet company-days.
- Record the best min(t_profit, t_vs_peers) across the 45 cells in each fake.
- A real category needs to beat 95% of its fakes.

## After the search
- Survivors get the sensitivity grid: OTM 3/5/10%, 1m/2m/3-6m buckets, filing-day vs next-session.
- Only the final frozen rule goes to the 2026 window, once.
