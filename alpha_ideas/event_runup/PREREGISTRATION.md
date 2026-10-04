# Earnings Eve (idea 1A): pre-registration

Written 2026-10-03, Sat evening ET, **before any return around these events was computed**. The file's mtime is the
authority on timing. Any rule below that turns out to be ambiguous is resolved in `results.md` with the reason,
**before** the run. Nothing may be changed after results are seen.

**Hypothesis.** Stocks that are "hot" going into earnings get bid up in the days before the release:
- retail attention to past winners (Aboody, Lehavy & Trueman 2010);
- over-extrapolation from past earnings-day jumps (Ertan, Karolyi, Kelly & Stoumbos 2016);
- the pre-announcement premium in high-uncertainty stocks (Gao, Hu & Zhang; Johnson & So 2018).

So a long position in the hottest stocks, bought 5 sessions before the release and sold in the last closing auction
**before** the release, earns a positive, market-hedged return after costs.

## Data
- **Earnings events:**
  - Source: 8-K filings with item 2.02 from the cached SEC submissions (`data/cache/ai_washing/sec/submissions`). These
    cover 2,078 CIKs that were in the monthly top-1,000 at some point, with filings 2019-01 → 2026-10-02.
  - Only form `8-K` counts; `8-K/A` is ignored.
  - Times are acceptance times converted to America/New_York.
- **Episodes and events:**
  - For each CIK, filings less than 22 calendar days apart form one episode.
  - The **event** is the first filing of an episode.
  - It is kept only if the previous episode started 50–130 calendar days earlier: a regular quarterly reporter, checked
    with past information only.
- **Prices:**
  - Stocks: `data/cache/ai_washing/prices.parquet`, daily total returns (`ret`), 2020-01-02 → 2026-09-30.
  - Market: SPY closes from `data/cache/massive_grouped`. These are price only, so a short SPY hedge is charged 0.5 bp
    per day per unit of beta as dividend carry.
- **Universe:** the CIK must be in `universe.parquet` (point-in-time top 1,000 by 63-day dollar volume) at the last month-end before entry.

## Timing: the last clean close X
Let A = the acceptance timestamp and F = A's calendar date. All "sessions" are trading days of `calendar.parquet`.

**Case 1:** A is before 16:00 ET on a trading day, or F is not a trading day.
- X = the last trading day strictly before F.
- The release happened before F's close, or late the evening before, so the close before F is clean.

**Case 2:** A is at or after 16:00 ET on a trading day F. The release was usually after the close on F, but some
filings are late paperwork for a pre-market release earlier on F. Massive hourly bars (04:00–20:00 ET) decide which:
- **Volumes on F:**
  - AH = after-hours volume, bars starting 16:00–19:00.
  - PM = pre-market volume, bars starting 04:00–08:00.
- **Baselines:** the medians of AH and PM over the previous 20 sessions, each floored at 100 shares.
- **Ratios:** rAH = AH / baseline_AH and rPM = PM / baseline_PM.
- **Rule:** if rAH ≥ rPM, the release was after the close on F, so X = F. Otherwise X = the trading day before F.
- **No bars on F:** X = F (acceptance-time default).

**Entry and returns:**
- Entry E = 5 sessions before X. Hold from the close of E to the close of X (sessions E+1 … X).
- Missing returns inside the window → the event is dropped (count reported).

## Signal: the "heat" score, all measured at E's close with data up to E only
1. **R12:** total return from the close 252 sessions before E to the close of E. Needs ≥ 200 valid daily returns.
2. **PREAC:** the mean of the last 4 (minimum 2) **earnings reactions** whose window ended on or before E.
   - Reaction = the SPY-adjusted return (beta 1) from the close of the session before F to the close of the session
     after F.
   - This 2-session window catches every release timing without needing the bars.
   - Every 8-K 2.02 episode start counts here, including ones outside the quarterly filter.
3. **IVOL60:** the standard deviation of the daily (stock − SPY) return over the 60 sessions ending at E. Needs ≥ 40 valid.

**Ranking and selection:**
- Each day, rank each measure as a percentile across universe stocks that have all three measures.
- Score = the mean of the three percentile ranks, re-ranked across the same cross-section.
- **Hot** = score percentile ≥ 0.8 (top quintile). **Cold** = ≤ 0.2.
- Events without all three measures are excluded and counted.

**Hedge beta:**
- The OLS slope of the stock's daily return on SPY's over the 252 sessions ending at E (≥ 120 valid), clipped to [0.2, 3.0].
- If it can't be estimated, beta = 1.

## Trade, costs and the primary test
- **Per-event return:**
  - gross = r_stock(E→X) − beta × r_SPY(E→X), both compounded over the 5 sessions;
  - cost = 8 bp per side on the stock (closing auctions, top-1,000 mix of large and mid caps);
  - plus 1 bp per side × beta on SPY;
  - plus dividend carry 0.5 bp × 5 sessions × beta;
  - net = gross − cost.
- **In-sample (IS):** entries 2021-01-01 → 2025-12-31.
- **Out-of-sample (OOS):** entries 2026-01-01 → the last E whose X ≤ 2026-09-30. Opened **once**, after the IS verdict,
  with unchanged code and parameters.
- **Primary statistic:** the mean **net** return per **hot** event in IS.
  - t-stat with standard errors clustered by the ISO week of E (week clustering absorbs earnings-season co-movement).
  - Prediction: positive.
- **Verdict:**
  - PASS = mean > 0 and t ≥ 2.0.
  - "Convincing" = t ≥ 3.0, given the ~1,900 earlier tests in this repo.
  - Otherwise FAIL.
- **OOS pass:** mean net > 0 for hot events in 2026. The t-stat is reported; it will be low-powered.

## Secondary results (reported; they cannot rescue a failed primary)
- **S1, earnings or just hot stocks?** The same hot events with the window moved 30 sessions earlier (E−30 → X−30),
  same beta and costs. Report placebo net and (event − placebo) with clustered t.
- **S2:** all scored events, unfiltered.
- **S3:** cold events.
- **S4:** the top quintile on each single measure (R12, PREAC, IVOL60).
- **S5:** conservative timing, X = the trading day before F for every event.
- **S6:** a 10-session window, entry 10 sessions before X.
- **S7:** a market-adjusted hedge (beta = 1).
- **S8:** costs doubled.
- **S9:** by calendar year of E.
- **S10:** predictable-schedule subset. The event date must be within ±7 calendar days of the matching episode start
  364 days earlier (episode starts 340–388 days earlier).
- **S11:** calendar-time portfolio.
  - Each day, equal-weight all open hot positions on their daily hedged returns.
  - Entry cost is charged on day E+1 and exit cost on day X; days with no position earn 0.
  - Report the annualized mean, volatility, Sharpe (√252) and max drawdown.

## Disclosure
This is the 12th pre-registered test of 2026-10-03, on top of the ~1,900 earlier tests. S1–S11 are reported in full,
whatever they show.
