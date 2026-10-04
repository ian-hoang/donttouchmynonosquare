# Idea 8 — Late reporters: does the market fully price a delayed earnings release?

Written 2026-10-03, **before any return for this test was looked at** (file mtime is the authority). One primary
test decides the verdict; robustness is reported but cannot rescue it. No parameter changes after results are seen.
Ambiguities are resolved in `results.md` before the single run. Bug fixes are allowed and logged.

## Hypothesis
Companies that report earnings later than their usual schedule tend to carry bad news (Bagnoli, Kross & Watts 2002;
Johnson & So 2018). If the market does not fully price the delay once it becomes visible, the stock keeps falling
relative to peers until — and through — the late release.

## Data (all already cached; see `alpha_ideas/ai_washing/`)
- **Earnings releases:** every SEC 8-K with item 2.02 of universe companies, accepted 2020-07-01 → 2026-06-30
  (`data/cache/ai_washing/sec/earnings_8k.parquet`). Day 0 of a filing follows the same rule as before: the
  acceptance day if accepted ≤ 16:00 ET on a trading day, else the next trading day.
- **Prices, universe and industry:** the company-level total-return prices, the monthly top-1,000 universe, and the SEC
  SIC codes built for the AI-washing test.

## The usual date (built only from the past)
- A firm's 2.02 filings are grouped into **reporting episodes**. A gap of more than 21 calendar days starts a new
  episode. An episode's **anchor** is the day 0 of its last filing, so a preliminary release a week before the main
  one does not set the anchor.
- **Expected date** E = anchor + 364 calendar days (same weekday, one year later).
- **Observation day** O = the 3rd U.S. trading day after E. If E is not a trading day, count from the first trading
  day after it.

## Signal (no look-ahead)
- **Late signal at O:** the firm has filed no item 2.02 8-K accepted between E − 30 days and O's 16:00 close.
- The firm must be in the universe at the last month-end before O.
- **Sample:** O between 2021-07-01 and 2026-03-31. The end date leaves room to see the late release inside the data.

## Trade and outcome
- Short at the close of O. Cover at the close of day +1 of the firm's next 2.02 filing accepted after O's close, or
  at O + 60 trading days if none comes.
- **Abnormal return:** stock minus its peers (same 2-digit SIC and dollar-volume tercile at that month-end,
  equal-weighted, excluding the firm; same fallbacks as before), summed over the holding days. A day with no stock
  return counts as 0.

## Primary test
- **Statistic:** mean cumulative abnormal return (CAR) per late-signal event. t-stat with standard errors clustered
  by the calendar month of O. **Prediction: < 0.**
- **Costs for the tradable short:** 10 bps per side per leg (40 bps round trip, stock and peer basket) plus 1%/yr
  borrow, pro-rated over the holding days.
- **PASS:** t ≤ −2.0 **and** mean CAR is more negative than the mean cost, so the short is profitable net.
  t ≤ −3 = convincing. Fewer than 100 events = INCONCLUSIVE.

## Robustness (reported only)
1. **Post-release drift.** Releases at least 7 calendar days later than E, abnormal return from day +2 to +63
   (cut at the firm's next release day +1). Compared with on-time releases (within ±3 days of E).
2. **Split the signal events in two:** the waiting part (O → the day before the release) and the release reaction
   (day 0 → +1).
3. **Stricter threshold:** observation day at E + 5 trading days.
4. **Early releases** (≥ 7 days before E): drift from +2 to +63. Prediction: not negative.
5. **Skip the COVID base year:** only events with O ≥ 2022-07-01 (2020 schedules were distorted).
6. **Calendar-time version** of the primary: daily mean AR of open short positions, summed by month, Newey-West t.
7. **Late signals that never got a release** within 60 trading days, reported separately (often delistings or
   fiscal-year changes).
