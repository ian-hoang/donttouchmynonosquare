# Idea 6 — "AI-washing": cheap AI talk in earnings releases → later underperformance

Written 2026-10-03, **before any press-release text or any return in this test was looked at** (file mtime is
the authority). One primary test decides the verdict; robustness items are reported but cannot rescue it. No
parameter below changes after results are seen. If an ambiguity forces a choice, it is written in `results.md`
with the reason before the final run. Bug fixes are allowed and logged ("bug: … fixed: …").

## Hypothesis
After ChatGPT (2022-11-30), firms whose earnings press releases suddenly talk a lot more about AI, **without a
matching rise in real investment**, are cheap-talking. Their stocks underperform comparable firms over the next
~3 months as the hype fades.

## Data
- **Prices:** Massive grouped daily bars (cached in `data/cache/massive_grouped/`, split-adjusted closes), plus
  Massive cash dividends adjusted for later splits → daily total returns, stitched by company (CIK) across ticker
  changes. Daily |return| > 100% or returns after a gap of > 5 trading days are treated as missing.
- **Universe:** each month-end, U.S. common stocks (Massive type CS) with raw close ≥ $5, top 1,000 by 63-day average
  dollar volume, one share class per CIK (the most traded). Ticker→CIK from Massive reference tickers
  (a delisted ticker row is valid up to its delisting date; the active row after that).
- **Earnings releases:** SEC EDGAR submissions of universe CIKs: form `8-K` (no amendments) with item `2.02`,
  accepted 2020-07-01 → 2026-06-30. The press release = the first `EX-99*` document in the filing. No EX-99 → dropped.
- **Investment:** SEC XBRL company facts. From the latest `10-K` filed **strictly before** day 0: capex + R&D for the
  latest fiscal year vs the prior fiscal year, both taken from that same 10-K.
  Capex = first available of `PaymentsToAcquirePropertyPlantAndEquipment`, `PaymentsToAcquireProductiveAssets`,
  `PaymentsForCapitalImprovements`. R&D = first available of `ResearchAndDevelopmentExpense`,
  `ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost`; R&D missing → 0. Capex missing → investment unknown.
- **Industry:** SEC submissions `sic`, 2-digit.

## Signal
- **AI_count** of the press-release text (HTML stripped). Case-insensitive phrases: "artificial intelligence",
  "machine learning", "deep learning", "neural network(s)", "large language model(s)", "ChatGPT", "agentic".
  Case-sensitive whole tokens: `AI`, `A.I.`, `GenAI`, `OpenAI`, `LLM`, `LLMs`, `GPT` (token = not touching a letter or
  digit on either side; `AI-powered` counts once).
- **Baseline** = mean AI_count of the firm's previous up-to-4 earnings releases accepted within the prior 15 months;
  at least 3 required.
- **AI jump:** AI_count − baseline ≥ 3 **and** AI_count ≥ 3.
- **Investment growth** g = (capex+R&D)_FY / (capex+R&D)_FY−1 − 1.
- **Washer** = AI jump and g < 10%.  **Investor** = AI jump and g ≥ 10%.

## Timing (no look-ahead)
- Acceptance time converted to New York time. Day 0 = that trading day if accepted at or before 16:00 ET on a trading
  day, else the next trading day.
- The firm must be in the universe at the last month-end before day 0.
- Holding window: trading days +2 … +63 (return from the close of day +1), cut short at the same firm's next
  release day +1 and at 2026-09-30.
- **Benchmark:** universe peers at that same month-end in the same 2-digit SIC and the same dollar-volume tercile,
  excluding the firm. If < 10 peers, use same 2-digit SIC with any tercile. If still < 10, use same tercile with all
  industries. Equal-weighted daily total return of the peers.
- **Abnormal return** AR_i,t = r_i,t − bench_i,t. If the stock has no return that day (halt/delisting), AR = 0 for the
  day (position treated as closed).

## Primary test
- Events: washers with day 0 in 2023-01-01 → 2026-06-30.
- Calendar-time portfolio: each trading day, equal-weighted mean AR over washer events in their window. Monthly AR =
  sum of daily ARs in the month. Months 2023-02 → 2026-09, keeping only months where the average number of held
  events is ≥ 10.
- **Statistic:** mean monthly AR, Newey-West t (3 lags). **Prediction: < 0.**
- **Costs** for the tradable version (short washers, long their peer baskets): 10 bps per side per leg, so 40 bps per
  event round trip, plus 1%/yr short borrow. Monthly cost = (event entries in month × 0.40%) / (average events held
  in month) + 0.083%.
- **PASS:** t ≤ −2.0 **and** mean monthly AR is more negative than the mean monthly cost, so the trade is profitable net.
  t ≤ −3 = convincing. Fewer than 100 washer events = INCONCLUSIVE.

## Robustness (reported only)
1. All AI-jump events, ignoring investment.
2. Investors on their own, and washers minus investors (prediction < 0).
3. Event-level regression of CAR(+2 … window end) on ΔAI (winsorised 1/99%), with day-0-quarter and SIC2 fixed
   effects, clustered by day-0 month. Prediction: slope < 0.
4. Strict dictionary: only "artificial intelligence" and the `AI` token.
5. Length-normalised jump: ΔAI per 1,000 words ≥ 1.0 and AI_count ≥ 3.
6. Daily washer AR regressed on Fama-French Mkt-RF, SMB, HML plus momentum (alpha).
7. One-month holding (+2 … +21).
8. Excluding core tech: SIC 3570–3579, 3670–3679, 7370–7379.
9. Announcement reaction (days 0 … +1) of washers vs other events (descriptive: did the market reward the talk?).
10. Pre-ChatGPT placebo: the same washer rule with day 0 in 2021-07-01 → 2022-11-29.
