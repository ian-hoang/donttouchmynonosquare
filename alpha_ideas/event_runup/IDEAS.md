# Event run-up ideas: buy before the event, sell before it

Written 2026-10-03 (Sat afternoon ET) **before any return data was looked at for these ideas.** No backtest has
been run. The only data checks were plumbing:
- free Databento cost estimates;
- confirming that Massive bars cover pre- and post-market hours;
- two events looked at by eye to check release-time detection: ABT 2026-04-16 and NVDA 2025-08-27.

Nothing here is a pre-registration yet. Before testing an idea, freeze its rules in a `PREREGISTRATION.md` (repo habit).

Revised the same afternoon after the extended-hours research came back. Changes:
- The release-day session (#1B) and the mega-cap earnings-day index trade (#1D) moved up.
- The pre-market exit and the Blue Ocean overnight variant moved down.

## What the research says

Checked by me against the papers, abstracts or summaries:

| Finding | Source |
|---|---|
| ~71–72% of the extra return stocks earn around earnings arrives in the 10 days **before** the release (0.31% of 0.42% in a 21-day window). High-uncertainty stocks (high option implied vol 11 days out) earn **+1.52%** market-adjusted over those 10 days; low-uncertainty stocks earn ~0. | Gao, Hu & Zhang, *Management Science* ("Uncertainty Risk Resolution Before Earnings Announcements") |
| Top 1% past-12-month winners: **+1.58%** market-adjusted in the 5 days before earnings, then **−1.86%** in the 5 days after (1971–2005), "significant after transaction costs". The full sample is +0.30% before. Small-trader *buy* imbalance before, gone after. For after-hours announcers, day-1 close-to-open is **+0.93%**, then negative open-to-close. | Aboody, Lehavy & Trueman (2010, *Rev. Acc. Studies*) |
| Individuals over-extrapolate past earnings-day returns. Top-decile firms on that measure see ~10% more individual buying in the 5 pre-earnings days. Their daily returns are **+11 bp/day** higher. The long-short decile earns **>17 bp/day** of 4-factor alpha pre-earnings (value-weighted, before costs), then reverses **~13 bp/day** after. | Ertan, Karolyi, Kelly & Stoumbos (2016, AFA; SSRN 2720573) |
| Before earnings, selling becomes costlier than buying: intermediaries cut their exposure. That creates "a predictable upward bias in prices that increases preannouncement, and subsequently reverses". | Johnson & So (2018, *JAR* 56(1)) |
| On the biggest **after-close** earnings days (the 3 most prominent per Jan/Apr/Jul/Oct, 1999–2018), the market rises **+0.34% vs +0.02%** on a normal day: 0.11% the evening before and 0.23% in the regular session before the release. The announcing stocks rise **+0.61%** on that pre-release day. **Before-open clusters show nothing**, and they are 2/3 of the clusters. | Chen, Cohen & Wang (2020 WP), via CXO Advisory |
| Attention stocks: positive overnight returns, then intraday reversals. The opening price is too high; the hidden cost of buying at the open often exceeds the half-spread. It is concentrated in retail-attention, hard-to-value stocks. | Berkman, Koch, Tuttle & Zhang (2012, *JFQA*) |
| >95% of US earnings releases come outside regular hours; the most common time is 4:05 pm. Quoted spread: 5 bp at 4:00 pm, **60 bp at the release**, 30 bp 10–20 minutes later. After-hours averages 58.1 bp vs 8.4 bp in regular hours (~7x). Trading the after-hours reaction worked in 2008–15 but was insignificant after spreads in 2016–20. | Christensen, Timmermann & Veliyev (2026, arXiv 2601.08962) |
| ATM straddles bought 3 days before earnings and held to the announcement date: **+3.34%** (significant). This is bigger in small, volatile, costly-to-trade names, so costs matter a lot. | Gao, Xing & Zhang (2018, *JFQA*) |
| Retail buys options heavily before earnings, most in names with high expected volatility, and loses money doing so. Dealers are on the other side. | de Silva, Smith & So ("Losing is Optional", 2025 version) |
| Dividend month premium: +53 bp/month vs all stocks, +37 bp vs payers in non-dividend months. Alphas build from declaration to ex-day. | Hartzmark & Solomon (2013, *JFE*) |
| Pre-earnings reversal: 1.45% vs 0.22% on normal days, **but the holding window t−1..t+1 includes the release**. Quantpedia's out-of-sample check is slightly negative. | So & Wang (2014, *JFE*) |
| Pre-FOMC drift "essentially disappeared after 2015" (sample extended to 2019). | Kurov, Wolfe & Gilbert |
| Splits: 45 Russell 1000 splits since 2019 rose ~4% the week after the announcement, with **no effect around the effective date**. | Goldman Sachs study, via press |
| Published anomalies are ~26% weaker out of sample and ~58% weaker after publication. Expect decay. | McLean & Pontiff (2016, *JF*) |

From the research agent's report, **not re-checked by me**:
- **Run-up timing:** the high-retail-attention premium on after-close cluster days reverses the next day (Da, Hua, Hung &
  Peng 2024, *MS*).
- **Don't enter early:** stocks drift −2 to −3 bp/day for about a month before the 2-week pre-release window, so don't
  enter more than ~2 weeks early (Linnainmaa & Zhang 2019).
- **Little lost by exiting:** the release itself earns only ~12–15 bp on average for S&P 500 names, 2010–21 (Liu, Mao,
  Tang & Zhou 2023). Exiting before it gives up little.
- **Overnight effects are fading:**
  - Overnight returns persist week to week but reverse intraday, so you must sell at the open (Aboody, Even-Tov,
    Lehavy & Trueman 2018).
  - The S&P futures overnight drift is ~0 since 2021 (Boyarchenko et al.; NY Fed 2026).
  - Overnight returns shrink when the "open" is a 5-minute VWAP instead of the official open print (Bogousslavsky 2021).
- **The overnight venue (8 pm–4 am) is thin and expensive:**
  - It is ~0.11% of US volume, 61% of it ETFs, and ~80% of the flow is Asia-Pacific.
  - Effective spreads are ~64–69 bp vs 16–30 bp in regular hours (Eaton, Shkilko & Werner 2025; NYSE 2025).
- **Auction mechanics:** the opening auction is only 1–4% of daily volume; the closing auction is ~7.5–9%. Nasdaq's
  market-on-close cutoff is 3:55 pm.

Market structure (Cboe/NYSE 2025):
- Extended hours were >11% of US equity volume in Jan 2025, and pre-market is now >55% of extended-hours shares.
- Retail is a big share of pre-market volume. Robinhood says up to 25% of its trading happens outside regular hours on
  busy days.
- **Coming soon:**
  - Nasdaq 23-hour trading was approved in April 2026.
  - The 23.5-hour public consolidated feed (SIP) is planned for Dec 2026, per the agent, citing a Massive blog post.

## Data we already have / can get

| Need | Source | Cost |
|---|---|---|
| Earnings dates 2020-07 → 2026-07 (~40.7k 8-K item 2.02 filings, ~2,078 firms ever in the top 1,000) | `data/cache/ai_washing/sec/earnings_8k.parquet` | cached |
| Point-in-time top-1,000 universe, daily total-return closes | `data/cache/ai_washing/{universe,prices}.parquet` | cached |
| Release session (pre-market vs after-close) and approximate hour | Massive hourly/minute bars, 04:00–20:00 ET, 2019+ (2015 had no extended bars) | free (key) |
| Official open and close, pre-market first print, after-hours last print | Massive `/v1/open-close/{tk}/{date}` | free |
| ES / NQ hourly bars | cached GLBX `ohlcv-1h` (used by `alpha_ideas/t1_shift`) | cached |
| Overnight session 20:00–04:00 (Blue Ocean ATS) | Databento `OCEA.MEMOIR`, from 2025-08-24 | 1-min bars, 50 names, full history: $1.87 |
| Nasdaq / NYSE auction imbalance messages | Databento `XNAS.ITCH` / `XNYS.PILLAR` `imbalance` | expensive in bulk; targeted pulls only |
| Option prices | Massive option quotes (2024+, tooling in `massive/eightk.py`) | free |
| Option open interest | Databento `OPRA.PILLAR` statistics | ~$0.13–0.19 per stock-day |

Do not use Databento OPRA for anything broad: daily option bars for AAPL for one year cost $68.

The 8-K acceptance time is **not** the release time. About 20% of filings are accepted during market hours; for example,
ABT's 8-K was accepted at 11:36, but the volume spike shows the release came about 07:00. Use the first big
extended-hours volume spike instead.

**Assumed costs per side:**

| Where | Large caps | Mid caps |
|---|---|---|
| Closing auction | 2–5 bp | 8–20 bp |
| Opening auction | 3–8 bp | — |
| Pre-market / after-hours | 25–35 bp | 50–150 bp |
| Overnight venue | 15–35 bp+ | — |

These are agent estimates anchored on the spreads above. Calibrate them before trusting any net result.

## Ranked ideas

### 1. Earnings Eve: buy the "hot" stocks into earnings, get out at the last auction before the release (flagship)
**The selection score (used by 1A and 1B):** the average cross-sectional rank of three published, ex-ante predictors:
1. past 12-month return (Aboody et al.);
2. average of the last 4 earnings-day reactions (Ertan et al.);
3. 60-day idiosyncratic volatility, a free proxy for implied vol (Gao, Hu & Zhang). Use Massive IV for 2024+ as a
   robustness check.

Trade the top quintile, hedge the market with SPY or ES, equal weight per event.

**Why it should work:** three mechanisms all predict a price push *before* the release: retail attention buying,
over-extrapolation, and lopsided liquidity. All three predict a give-back after it, which we avoid.

#### 1A. Five-day version — **TESTED 2026-10-03: FAIL** (−0.25% net per trade, t −0.96, N 3,522; see `results.md`)
- **Trade:**
  - Buy at the closing auction 5 sessions before the *last clean close*. That close is the release day for after-close
    reporters and the day before for pre-market reporters.
  - Sell at the last clean close.
- **Size if it survives:** papers show ~+0.5% to +1.5% per event for the hottest names. Expect less after decay.
- **Costs:** ~5–10 bp round trip, auctions only.
- **Test time:** ~3–4 h with cached data plus free Massive hourly bars.

#### 1B. Release-day session, after-close reporters only (moved up)
- **Trade:**
  - Buy at the opening auction on the day of a 4:05 pm-type release.
  - Sell with a market-on-close order (cutoff 3:55 pm), minutes before the release.
- **Evidence:** +0.61% for prominent after-close announcers on that day (1999–2018); +0.89% for past winners (Aboody).
  Da et al.: only when retail attention is high.
- **Why it fits:**
  - This is the purest "buy into the event, sell right before" trade: one session, two auctions.
  - It sidesteps the before-open releases, which show no premium.
- **New here:**
  - the score filter;
  - the 2020–2026 sample;
  - all after-close names, not just cluster days.

#### 1C. Nights only (direct test of the extended-hours idea)
- **Trade:** in the 1A window, hold only from each close to the next open, trading only the two auctions.
- **Hypothesis:** the pre-earnings buying sits in the overnight legs (Berkman et al.).
- **Caveats:**
  - It is untested.
  - The opening auction is thin.
  - Overnight effects are fading.
  - It has more turnover than 1A.

  It only wins if the intraday legs are ≤ 0.

#### 1D. Mega-cap earnings-day index trade (new; uses Databento futures)
- **Trade:** buy ES/NQ at the open and sell at the close on the 3 biggest after-close earnings days per season, e.g.
  when several mega-caps report after the bell.
- **Evidence:** market +0.34% vs +0.02% on normal days (Chen, Cohen & Wang, 1999–2018).
- **Data:** cached ES/NQ bars; days chosen from the cached 8-K data plus bar-detected timing for the top ~50 names.
- **Odds:** cheap, but only ~12 events a year, so the sample is small.

### 2. Volatility ramp: long a straddle into earnings, sell before the release
- **Trade:** buy an ATM straddle in the expiry just after earnings, 3–5 sessions before, and sell at the last clean
  close. Implied vol rises into the event (Gao, Xing & Zhang +3.34%).
- **Optimize:**
  - only the tightest-spread names;
  - only where implied vol is low vs the stock's past earnings moves.
- **Risk:** our measured option half-spreads were 1.6–2.4%, so a straddle round trip could eat most of the gain.
- **Data:** Massive quotes 2024+, existing tooling.

### 3. "Vanna squeeze": dealer hedging into earnings (novel options-flow idea, unpublished as far as we found)
- **Mechanism:**
  - Retail buys out-of-the-money calls before earnings, and dealers sell them.
  - As implied vol ramps, the delta of an out-of-the-money call rises, so a short-call dealer must **buy stock**.
  - After the release, vol collapses and the flow reverses.
- **Signal:** heavy out-of-the-money call open interest relative to put open interest, scaled by average daily volume, in
  the expiry spanning the release.
- **Trade:** long the stock from about the −5 close to the last clean close.
- **Data:** open interest from OPRA at ~$0.15 per stock-day (≈$45 for 300 events); call volume from Massive is a free
  proxy.
- **Odds:** highest novelty, least evidence.

### 4. Dividend run-up, sold before the ex-date (Hartzmark & Solomon)
- **Trade:** buy ~5 sessions before a predicted ex-date and sell at the close before the ex-date, so we never take the
  dividend.
- **Data:** cached (`dividends_adj.parquet` has declaration and ex dates).
- **Size:** small per trade, many trades.
- **Test time:** ~1–2 h.

### 5. Investor-day / conference run-up
- **Trade:** buy ~5–10 sessions before a pre-announced investor day and sell the day before.
- **Evidence:** thin. Conference-day reactions exist; we found no published pre-event drift.
- **Data:** heavy. It needs 8-K item 7.01 exhibits plus text tagging from EDGAR, and the date the event was announced is
  unknown.
- **Status:** novel but not hackathon-sized.

### Measurement only (moved down)
- **Pre-market exit before a before-open release:**
  - No pre-release premium has been found for before-open announcers.
  - Pre-market costs are 25–35 bp per side, more for mid caps.
  - Unfilled limit orders force you to cross a wide spread or hold through the release.
- **Blue Ocean overnight session:**
  - ~0.11% of US volume, mostly ETFs and Asia-Pacific flow.
  - Effective spreads ~65 bp.
  - Only 13 months of data.

  Interesting to describe, unlikely to be profitable.

### Bonus (post-event, not "sell before"): fade the hangover
After a hot name's release, its opening print is inflated (Aboody: +0.93% close-to-open, then intraday losses). It
gives back about −1.86% over 5 days, or ~13 bp/day per Ertan et al.
- **Trade:** short the next open and cover after ~5 days.
- **Fit:** the natural second half of #1, but it is a short trade with different risk.

## Not recommended (evidence says weak or gone)
- Pre-FOMC drift: gone after 2015.
- Split effective-date run-up: no effect at the effective date.
- PDUFA run-ups: practitioner lore only, and date data is hard to get.
- So & Wang pre-earnings reversal: it holds through the release, and out-of-sample it is slightly negative.
- Trading the after-hours reaction itself: insignificant after spreads since 2016.

## Testing discipline (repo already has ~1,900 tests disclosed)
- One primary test per idea, frozen before running.
- The 2026 H1 events stay as a single hold-out. Convincing = t ≥ 3 in-sample, net of costs, then a pass on the hold-out.
- **Placebos:**
  1. the same stocks, the same 5-day window, 30 sessions earlier;
  2. all earnings events, unscored.
- **Look-ahead checks:**
  - Use the actual release date only when it was predictable (within ±3 days of last year's same-quarter date; see
    `alpha_ideas/late_reporters`).
  - Detect release timing from bars, not 8-K stamps.
  - Use the point-in-time universe.
- **Prices:**
  - Use the **official** open and close auction prices, not first or last trades.
  - Use midquotes for anything traded in extended hours.

## Sources
- Gao, Hu & Zhang: https://pubsonline.informs.org/doi/10.1287/mnsc.2022.03240 ; summary https://quantpedia.com/pre-announcement-returns/
- Aboody, Lehavy & Trueman: https://www.anderson.ucla.edu/documents/areas/fac/accounting/earnings_paper08.pdf
- Ertan, Karolyi, Kelly & Stoumbos: https://mendoza.nd.edu/wp-content/uploads/2019/01/2016_spring_finance_seminar_series_peter_kelly_paper_updated_3_22_2016.pdf
- Johnson & So (2018): https://ideas.repec.org/a/bla/joares/v56y2018i1p217-263.html
- Chen, Cohen & Wang (clusters): https://www.cxoadvisory.com/calendar-effects/three-high-attention-earnings-announcement-clusters-drive-market/
- Christensen, Timmermann & Veliyev (2026): https://arxiv.org/html/2601.08962v1
- Berkman et al. (2012): https://ideas.repec.org/a/cup/jfinqa/v47y2012i04p715-741_00.html
- Gao, Xing & Zhang (2018): https://alphaarchitect.com/straddle-earnings-announcements-and-win/
- de Silva, Smith & So: https://www.gsb.stanford.edu/faculty-research/publications/losing-optional-retail-option-trading-expected-announcement
- Hartzmark & Solomon: https://www.cxoadvisory.com/fundamental-valuation/dividend-month-premium
- So & Wang (2014): https://quantpedia.com/Screener/Details/307
- Kurov, Wolfe & Gilbert: https://www.skidmore.edu/economics/documents/KurovWolfeGilbert-TheDisappearingPre-FOMC-Announce-Drift-200914.pdf
- Splits (Goldman Sachs via Motley Fool): https://www.fool.com/investing/2024/06/07/nvidia-just-announced-a-stock-split-history-says-t
- Extended hours: https://www.cboe.com/insights/posts/early-birds-and-night-owls-how-extended-trading-hours-are-reshaping-u-s-equities-markets-/ ; https://www.nyse.com/research/insights/the-early-bird-gets-the-worm-a-new-normal-in-off-hours-us-equities-trading
- Agent-only sources (not re-checked):
  - Eaton, Shkilko & Werner: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5181159
  - Linnainmaa & Zhang: https://sites.insead.edu/facultyresearch/research/file.cfm?fid=65574
  - Liu, Mao, Tang & Zhou: https://www.aeaweb.org/conference/2024/program/paper/5GGEki7i
  - Bogousslavsky: https://ideas.repec.org/a/eee/jfinec/v141y2021i1p172-194.html
  - NY Fed on the overnight drift: https://libertystreeteconomics.newyorkfed.org/2026/07/the-disappearing-overnight-drift/
  - Massive on 23.5-hour trading: https://massive.com/blog/us-equities-move-to-23-5-trading
