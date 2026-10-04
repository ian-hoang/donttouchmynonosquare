# Databento idea list: researched, ranked, NOT backtested

Written 2026-10-03, about 13:30 ET. **No strategy P&L was computed for anything here.** Inputs:

- Six literature reviews run in parallel, each focused on evidence from *after* the paper was published:
  - time-of-day drifts
  - leveraged-ETF flows
  - closing auctions
  - futures factors
  - option-overlay and vol-control flows
  - benchmark fixes
- Free Databento cost quotes (`metadata.get_cost`). No data was bought.
- One feasibility check: the size of leveraged-ETF rebalancing compared with trading volume (idea 7).

None of this touches `roll_oi`, the locked OOS, Codex's files or `massive/`.

**How to read P.** P is my estimate of the chance that one test, with its rules fixed in advance, shows both:
- a net-of-cost result with t-stat ≥ 2 (a gap that size would rarely appear by luck), and
- a positive result in the most recent ~2 years.

Context: this repo has already run about 1,900 tests, and nearly every one failed. Published anomalies typically lose a third to a half of their returns after publication. So **20–25% is a good idea here**; nothing below is a sure thing.

**Words used:**
- *bp* = 0.01%.
- *Round trip* = buy and sell once.
- *Sharpe* = return per unit of risk per year; the S&P 500 is about 0.4–0.5 long-run.
- *OOS* = data held back for one final check.

---

## Top pick: "Gotobi", the Tokyo payday dollar squeeze (yen futures, 6J)

> **Tested 2026-10-03 (pre-registered, run once; see `gotobi/results.md`): WEAK PASS (cost-fragile).**
> - The effect is real over 2010–2026: +2.2 bp/day vs ordinary days, t = 2.38.
> - Net of costs it is only +0.8 bp/day (t = 1.08), and it loses money at 2× costs.
> - It has faded: the 2021–26 net is −2.0 bp/day, and the OOS effect is ≈ 0.

**In plain words.** Japanese companies traditionally settle bills on *gotobi* days: dates ending in 5 or 0, plus month-end. Importers who owe dollars buy them from their bank at a rate fixed at **9:55 a.m. Tokyo time**. The banks buy those dollars in the market before 9:55. So on these days the dollar tends to rise against the yen into 9:55, then slip back right after. Think of a shop that always restocks on the same day at the same hour: suppliers know it, and prices bunch up around it.

**Why it could still work**
- The buyer doesn't care about price. They must pay the bill that day, and a business custom sets the clock, not a trader. Flow like that pays whoever absorbs it.
- It has been documented twice, years apart:
  - Ito & Yamada (*J. International Economics* 2017) cover 2006–2013.
  - Bessho, Sugimoto & Suzuki (arXiv 2023) used EBS interbank data for 2018–2020. Buying USD before 9:55 and selling after made 167 trades: 63% winners, profit factor 2.6, after the bid-ask spread.
- No one has published anything for 2021–2026, so our test would be **genuinely blind**.
- It is unrelated to everything else in the repo (commodity rolls, Treasuries, 8-K options).

**Why it could fail**
- The move may be only a few bp. That is close to the CME 6J cost: about 1.3–2 bp per round trip, and there are two round trips per event.
- Banks may now net or algo-slice the orders, flattening it.
- Days when Japan's Ministry of Finance or the Bank of Japan intervenes can swamp the averages.

**Test (fix every rule before running)**
- **Data.** `6J.v.0` `ohlcv-1h`, 2010-06 → 2026-10, about **$0.95**.
  - Japan has no daylight saving, so in UTC the windows never move: 08:00–10:00 JST = 23:00–01:00 UTC, and 10:00–12:00 JST = 01:00–03:00 UTC.
  - 6J is quoted in dollars per yen, so "dollar up" means 6J down.
- **Gotobi days.** Tokyo business days dated 5, 10, 15, 20, 25, plus the month's last business day. If the date is a weekend or holiday, use the previous business day (*verify this convention*). Tuesday–Friday is the primary sample, as in Bessho et al.; report Mondays separately.
- **Trade.** One contract per leg:
  - Short 6J 23:00→01:00 UTC: long USD into the fix.
  - Then long 6J 01:00→03:00 UTC: fade after the fix.
- **Primary statistic.** For each day, take the pre-fix USD return minus the post-fix USD return. Compare the gotobi-day mean with the non-gotobi mean (one observation per day; plain t-stat).
  - **Pass:** t ≥ 2 and net P&L > 0 after 1 tick + $2.50 per side per leg, also with costs doubled.
- **Report separately:** 2010–17, 2018–20 (the paper's years), and 2021–26 (new). Hackathon OOS = the last 2 years.
- **Known bias, against us.** Hourly bars blur the exact 9:55 turn: the 9:55–10:00 drop falls in the pre-fix bar. If the hourly result is promising, refine with 1-minute bars for Tokyo mornings only (about $9–17; ask first).
- **Robustness (cannot rescue a failed primary):**
  - month-end vs other gotobi days
  - Japanese fiscal year-end (March)
  - intervention days removed
- **Effort and odds.** About $1 and 1–2 hours. **P ≈ 20–25%.**

## Runner-up: "Asia buys, New York sells", gold's time-zone split, with a China-holiday test

> **Tested 2026-10-03 (pre-registered, run once; see `gold_clock/results.md`): FAIL.**
> - Asia − NY = +1.7 bp/day (t = 1.20); net −0.15 bp/day.
> - The China-holiday check went the predicted way: Asian-hours return was −3.8 bp on Shanghai-closed days vs +2.2 bp
>   on open days (t = 2.32). As a secondary result, it can't rescue the verdict.

**In plain words.** Gold has different buyers in different time zones. Chinese and Indian physical buyers and central banks are active in Asian hours; Western funds and hedgers trade in London and New York hours. Several studies find gold tends to rise in Asian hours and drift down in New York hours.

**The twist that would make it convincing.** If Chinese buyers cause the Asian-hours gain, it should **disappear when the Shanghai Gold Exchange is closed**: Golden Week (happening right now), Lunar New Year and other PRC holidays. Most backtests have no placebo like that built in.

**Evidence**
- COMEX overnight returns were positive and day-session returns negative over 1985–2012. Sources: Blose & Gondhalekar 2014; Blose, Gondhalekar & Kort 2018, whose abstract says it survives costs.
- A 2019 CBS thesis (GC 5-minute bars, 2001–2018) finds +12.3%/yr accrued from 18:00–02:00 ET. It was strong to 2010, then positive but not significant over 2011–18.
- The World Gold Council says Asian hours drove most of the 2024 rally. For H1 2026 it reports Asia +12.9% vs North America −15% (via Caixin; secondary source).

**Risks**
- Gold's huge bull run makes "long Asia" look good for the wrong reason. So the primary test is the **long-Asia / short-NY spread**, not long-only.
- We have already seen WGC's 2024–26 breakdown, so the recent period is not blind. Disclose that.
- Weak over 2011–18.
- Two round trips a day: about 0.5 bp each at $4,000 gold, about 1.5 bp at $1,200.

**Test**
- **Data.** `GC.v.0` hourly, about **$0.97**.
- **Windows,** in local exchange time, set exactly before running: Asia = 18:00 → 03:00 ET; New York = 08:20 → 17:00 ET.
- **Primary statistic.** Mean daily (Asia return − NY return), t-stat, net of 2 round trips.
- **Secondary.** The same gap on days the Shanghai Gold Exchange is closed vs open. Prediction: about zero when it's closed.
- **Robustness.** SI, HG, PL (about $3 more).
- **Odds.** **P ≈ 20%** for the spread. Long-only Asian hours ≈ 35%, but mostly gold's trend.

---

## The full ranked list

| # | Idea | What you trade | Why it could work | Novelty | P | Data cost |
|---|---|---|---|---|---|---|
| 1 | **Gotobi Tokyo fix** | 6J, Tokyo morning | Importers' must-pay dollar buying at 9:55 JST | High | 20–25% | ~$1 |
| 2 | **Gold Asia vs NY** + China-holiday placebo | GC | Buyers split by time zone | Med-high | ~20% | ~$1 |
| 3 | Commodity **"relative basis"** composite (+ skew, basis-momentum) | 18 commodity futures, monthly | Futures-curve pressure; relative basis paper's data ends 2019 | Medium | 15–18% | ~$2–5 |
| 4 | **Month-end FX fix** signed by the month's equity move | 6B/6A/6S/6N at the 4pm London fix | Global funds re-hedge currency after equity moves | Low-med | ~15% | ~$4 |
| 5 | **Closing-auction pressure fade** | S&P 500 stocks, close→next open via auctions | ~83% of closing price impact is temporary | Low-med | 15–20% | $20–40 (ask) |
| 6 | **VIX leveraged-ETP rebalancing fade** (+ basis) | VX futures (2018-11+) | Todorov (*RoF* 2024): Sharpe 1.78 | Medium | ~15% | ~$7 |
| 7 | **Single-stock leveraged-ETF rebalance** | MSTR/TSLA/NVDA/COIN…, close→open | Forced closing flow is big (sized below) | High | 10–15% | ~$0.05 + Massive |
| 8 | Dealer gamma × late-day momentum | ES 15:30→16:00 | Baltussen et al., *JFE* 2021 | Low | ~15% | OPRA open interest: expensive |
| 9 | **Bitcoin ETF benchmark hour** | CME BTC, 15:00–16:00 ET | ETF NAVs are struck on trades in that hour | High | 10–12% | ~$1 |
| 10 | Treasury quarterly roll / ES roll basis | TY/FV/TU spreads; ES | Asset managers vs basis traders roll on a schedule | Low | 7–8% | $0 (cached) |

Testable today for ≤ $5 in total: 1, 2, 3, 4, 9, 10. Ideas 5, 6 and 8 need a budget decision first.

### 3. Commodity relative-basis composite

> **Tested 2026-10-03 (pre-registered, run once; see `curve_composite/results.md`): FAIL.**
> - Composite: +0.65%/month gross (Newey-West t = 1.48); net +0.57%/month. Very volatile.
> - Relative basis alone did not replicate: +0.17%/month (t = 0.43), and +0.3–0.4% (t < 0.7) in its fresh 2020–26
>   window.
- **Signals,** computed at month-end:
  - *Relative basis* = time-scaled [ln(F1/F2) − ln(F2/F3)] (Gu, Kang, Lou & Tang, AFA 2025). In their data: long top third / short bottom third earned 0.81%/month (t = 3.99), with 0.69% alpha after market, momentum and basis-momentum. **Their data ends in 2019, so 2020–26 is fresh.**
  - *Basis-momentum* = the 12-month return of the 1st-nearby contract minus the 2nd (Boons & Prado, *JF* 2019; Sharpe about 0.3–0.45 after 2015).
  - *Skewness* = skew of the last 12 months of daily returns; short high skew (Fernandez-Perez et al., *JBF* 2018; about 0.44 after publication).
- **Composite.** Equal-weight z-scores. Long the top 4, short the bottom 4, inverse-volatility weights, monthly.
- **Universe.** CL HO RB NG GC SI HG PL PA ZC ZW KE ZS ZM ZL LE GF HE.
- **Contract series.** Build 1st/2nd/3rd nearby from `statistics` settlements plus `definition` expiries, and roll before first notice day.
- **Costs.** 1 tick + $2.50 per side, + 1 tick per roll; double as a stress test.
- **Risks.** Only 3–4 names per leg. Most other commodity factors (carry, momentum, hedging pressure, open-interest sorts) have faded since 2015.

### 4. Month-end FX fix

> **Tested 2026-10-03 (pre-registered, run once; see `fx_fix/results.md`): PASS.**
> - +7.9 bp/event gross (t = 4.39), +5.6 net (t = 3.12), +3.3 at 2× costs. Net Sharpe about 0.77 at the true event
>   frequency.
> - Fading: 2021–26 net is +1.2 bp (t = 0.35).
> - The placebo day (the day before) is also +3.0 bp (t = 2.32).
- **Mechanism.** Melvin & Prins (*JFM* 2015, 2004–12): when a country's stocks beat the others over a month, its currency weakens into the 4pm London fix on the last business day, about 14 bp per 10% of outperformance. About 72% of that reverses by noon the next day.
- **Post-2015 evidence:**
  - The fix window was widened to 5 minutes.
  - HSBC (2019) said month-end models had "broken down".
  - A 2026 blog replication (unverified) finds about 2 bp per 1% S&P month in GBP, CHF, AUD and NZD.
- **Rule.** If ES is up more than 1% for the month as of the second-to-last day, buy a foreign-currency basket 15:00→16:00 London, then sell it 16:00→17:00 London. If ES is down more than 1%, the reverse. Hourly UTC bars line up exactly with London hours.
- **Size.** Only about 195 events, so power is low.

### 5. Closing-auction pressure fade
- **Evidence.**
  - Jegadeesh & Wu (*JFE* 2022): taking the other side of closing imbalances earned 6.8 bp to the next open and 25 bp over 5 days, equal-weighted, before costs.
  - Bogousslavsky & Muravyev (2023): closing-price dislocations mostly revert.
  - The catch: for S&P 500 names, the part you can capture after the imbalance is published is only about 1–3 bp per night. Imbalances that persist to the close carry real information. And this is a crowded trade.
- **Data.**
  - Official auction prices come cheaply from Databento `statistics`: stat_type 1 = opening, 11 = closing, on XNAS.ITCH, XNYS.PILLAR and ARCX.PILLAR.
  - Imbalance messages are the cost driver: about $0.95 per day for all NYSE names and about $9.64 per day for all Nasdaq names. Pull narrow time windows only.
- **Rule-change dates that split the sample:** 2018-10-29, 2019-04-01, 2019-04-15, 2022-06-10.

### 6. VIX leveraged-ETP rebalancing fade
- **Evidence.** Todorov (*Review of Finance* 28(3), 2024): ETPs often hold more than 40% of VIX futures. Leverage rebalancing creates a price gap with no fundamental cause, of about 0.61 vol points. Trading on the sign of that gap gave Sharpe 1.78; whether that is net of costs isn't stated.
- **Our simpler version.**
  - Predicted demand = Σ AUM × L(L−1) × the day's move, over UVXY, UVIX, SVXY and SVIX. AUM history comes from Massive's dated shares outstanding.
  - Fade it at the 16:00 ET settlement and exit the next day.
  - Optionally add the VIX basis carry signal (Simon & Campasano 2014; weak since 2010 by secondary accounts).
- **Data.** CFE data starts 2018-11 (VX daily about $6.93). Tail risk: March 2020, August 2024.

### 7. Single-stock leveraged-ETF rebalance pressure
- **Mechanics.** A daily-reset fund with leverage L must trade **AUM × L(L−1) × r** at the close, in the direction of the day's move. That holds for 2x, −1x and −2x funds alike.
- **Size check** (Massive dated shares outstanding × unadjusted price; no P&L):

| Day | Move | Predicted LETF trade | Share of whole-day $ volume |
|---|---|---|---|
| MSTR 2024-11-21 | −16.2% | −$1.9B | 4.2% |
| MSTR 2025-03-10 | −16.7% | −$0.9B | 12.0% |
| TSLA 2025-03-10 | −15.4% | −$1.4B | 3.2% |
| NVDA 2025-01-27 | −17.0% | −$2.3B | 2.3% |

  The closing auction is only a slice of the day's volume, so this flow can be a large share of the auction.
- **Why only 10–15%.**
  - Zhao (2026, preliminary, AI-assisted) finds **no next-day reversal** in 8 US names across 5,168 stock-days; MSTR is the only clear outlier.
  - Ivanov & Lenkey (2018): fund inflows and outflows offset rebalancing.
  - Single stocks tend to *reverse* in the last 30 minutes (Baltussen, Da & Soebhag 2025).
  - Supporting it: Tuzun (Fed 2013) finds index-LETF pressure fully reverses the next day.
- **Best identification.** Compare the same stock before vs after its LETFs launched.
- **Data.** Official auction prices for 25 names 2022–26 cost about $0.05. Massive returns dated shares outstanding for ETFs (verified: TSLL had 117M shares in 2024-06 and 424M in 2025-06); check how often it updates.

### 8. Dealer gamma × late-day momentum
- **Evidence.** Baltussen, Da, Lammers & Martens (*JFE* 2021, 1996–2020): the last 30 minutes follow the rest of the day only when dealers' net gamma is negative (β = 0.066, t = 4.8).
- **Concerns.** The repo's unconditional SPY version already failed. Rosa (2022) finds it gone out of sample except on large moves.
- **Data.** Needs SPX open interest from OPRA `statistics`. That is about $10 per month for SPY alone, so a multi-year SPX history is likely hundreds of dollars.

### 9. Bitcoin ETF benchmark hour
- **Mechanism.** IBIT and about 5 other ETFs strike their NAV on CF Benchmarks' BRRNY: trades from 15:00–16:00 ET, cut into 12 five-minute slices. Kaiko measured that hour's share of volume rising from 4.5% to 6.7% after the ETFs launched.
- **Evidence.** No study tests price pressure or reversal in this window.
- **Rule.** CME BTC 15:00→16:00 vs 16:00→17:00 ET, signed by the prior day's Farside net flows (top and bottom fifths only). Day-T flows are known only on T+1.
- **Natural experiment.** In-kind creations were allowed in 2025 (*verify the date*), which should weaken the effect afterwards.
- **Data.** About $0.51 for BTC hourly bars plus $0.32 for IBIT.

### 10. Treasury quarterly roll / ES roll basis
- **Treasury roll.** Asset managers are long Treasury futures and basis traders are short. The roll happens in the 10 days before First Intention Day. Quantitative Brokers reports mild reversal of pre-roll spread moves (details behind a form; unverified).
- **ES roll basis.** Hazelkorn, Moskowitz & Vasudevan (*JF* 2023): a rich futures basis predicts lower returns.
- **Data.** Free: the hourly bars are cached.

---

## Checked and dropped (do not spend tests here)

| Idea | Why dropped |
|---|---|
| ES "overnight drift" at the European open (Boyarchenko, Larsen & Whelan, *RFS* 2023) | The authors' own July 2026 note: ≈ 0 since 2021. Algorithms now slice closing flow, so dealers carry less inventory overnight. |
| Covered-call ETF roll windows (QYLD/XYLD), JEPI, YieldMax | No evidence of price effects; Cboe found no volatility suppression. P 2–6%. |
| Buffer/defined-outcome ETF monthly resets | No studies; only about $6–7B resets a month across issuers. P ≈ 3%. |
| Vol-control fund flows / "window drop-off" days | The main index uses smoothed volatility, so there is no drop-off day. No academic evidence. P 5–8%. |
| Gold LBMA PM fix | The pre-2015 pattern was information leaking, not a reversal. Nothing exploitable after 2015. P ≈ 7%. |
| Treasury / crude / Russell time-of-day drifts | No credible evidence; ZN's 1.4 bp tick cost swamps any hourly drift. |
| Generic commodity carry, momentum, hedging pressure, open-interest sorts, Hong & Yogo open-interest growth | Faded after 2015; Hong & Yogo has only about 16 independent observations. |

## Data costs (free quotes taken 2026-10-03)

| Request | Cost |
|---|---|
| Any one futures root, `ohlcv-1h`, 2010-06 → 2026-10 (NQ, GC, SI, HG, 6E, 6J, CL, NG, ZC…) | $0.51–0.97 |
| 19 commodity roots, c.0 + c.1, `ohlcv-1d` / `statistics`, 2010–26 | $1.57 / $2.24 |
| XNAS.ITCH `statistics` (official auction prices), 25 stocks, 2022-07 → 2026-10 | $0.05 |
| XNAS.ITCH `ohlcv-1m`, 25 stocks, same period (EQUS.MINI from 2023-03: $6.03) | $10.94 |
| XNAS.ITCH `imbalance`, 25 stocks, same period | $22.23 |
| `imbalance`, ALL symbols, one day: NYSE / Nasdaq | $0.95 / $9.64 |
| VX c.0–c.2 `ohlcv-1d`, 2018-11 → 2026-10 | $6.93 |
| OPRA `statistics` (open interest), SPY, one month | $10.02 |
| ES `ohlcv-1m` 2010–26 / six FX roots `ohlcv-1m` 2012–26 / BTC+MBT `ohlcv-1m` 2018–26 | $20.83 / $103.90 / $11.85 |
| **Already cached (free):** ES and Treasury `ohlcv-1h` 2010–26; CL `ohlcv-1m` 2012–26; energy `statistics` (CL/HO/RB/NG c.0/c.1) 2010–26 | $0 |

## Gotchas for whoever builds the tests
- Databento bars are stamped at bar **start**; re-stamp them with `gqh.data.stamp_bar_end`. Hours with no trades are simply missing.
- Do window logic in the exchange's local time. Tokyo has no daylight saving; London and New York switch on different dates for 2–3 weeks a year.
- `.v.0` switches contract by volume. Compute returns within a contract (`gqh.data.roll_safe_returns`).
- Costs in bp change with the price level, so compute them per day.
- Databento `trades` has no auction flag. Use `statistics` stat_type 1 (opening) and 11 (closing) for official auction prices.
- Every new primary test adds to the count that must be disclosed. Write a pre-registration before pulling any data.

## Sources
- Ito & Yamada (2017), *J. International Economics* 109:214–234. https://ideas.repec.org/a/eee/inecon/v109y2017icp214-234.html
- Bessho, Sugimoto & Suzuki (2023), arXiv:2301.13204. https://arxiv.org/abs/2301.13204 · HTML version: https://ar5iv.labs.arxiv.org/html/2301.13204
- Blose & Gondhalekar (2014), *Applied Economics Letters* 21(18). https://ideas.repec.org/a/taf/apeclt/v21y2014i18p1269-1272.html
- Blose, Gondhalekar & Kort (2018), *J. Economics and Finance* 42(3). https://ideas.repec.org/a/spr/jecfin/v42y2018i3d10.1007_s12197-017-9403-0.html
- Donati & Jung (2019), CBS MSc thesis. https://research.cbs.dk/en/studentProjects/gold-price-dynamics-around-the-clock/
- World Gold Council (2024). https://www.gold.org/goldhub/gold-focus/2024/11/lets-tally-rally
- Gu, Kang, Lou & Tang, "Relative basis", LSE FMG DP942. https://www.fmg.ac.uk/sites/default/files/2026-01/DP942.pdf
- Boons & Prado (2019), *JF* 74(1). https://4nations.albertjmenkveld.com/papers/boonsprado17.pdf
- Fuertes & Zhao (2023), *J. Commodity Markets* (post-publication factor decay). https://openaccess.city.ac.uk/id/eprint/30907/1/SSRN-id4112383.pdf
- Fernandez-Perez, Frijns, Fuertes & Miffre (2018), *JBF* 86. https://openaccess.city.ac.uk/id/eprint/17843/
- Melvin & Prins (2015), working-paper version. https://www.ecb.europa.eu/events/pdf/conferences/131216/Third_FX_Workshop_MELVIN_PRINS_Equity%20hedging%20and%20exchange%20rates%20Nov%202013.pdf
- Krohn, Mueller & Whelan (2024), *JF* 79(1), working paper. https://www.bankofcanada.ca/wp-content/uploads/2021/10/swp2021-48.pdf
- Jegadeesh & Wu (2022), *JFE* 143(3). https://ideas.repec.org/a/eee/jfinec/v143y2022i3p1120-1139.html
- Bogousslavsky & Muravyev (2023), *J. Financial Markets* 66. https://ideas.repec.org/a/eee/finmar/v66y2023ics1386418123000502.html
- Todorov (2024), *Review of Finance* 28(3):831–863. https://revfin.org/when-passive-funds-affect-prices-evidence-from-volatility-and-commodity-etfs/ · BIS WP 952: https://www.bis.org/publ/work952.htm
- Tuzun (2013), FEDS 2013-48. https://www.federalreserve.gov/pubs/feds/2013/201348/201348pap.pdf
- Ivanov & Lenkey (2018), working-paper version. https://www.federalreserve.gov/econresdata/feds/2014/files/2014106pap.pdf
- Zhao (2026), "Preying on Leveraged ETFs", arXiv 2608.03703 (preliminary). https://arxiv.org/abs/2608.03703
- Baltussen, Da, Lammers & Martens (2021), *JFE* 142(1). https://doi.org/10.1016/j.jfineco.2021.04.029
- Boyarchenko, Larsen & Whelan, "The Disappearing Overnight Drift" (2026). https://libertystreeteconomics.newyorkfed.org/2026/07/the-disappearing-overnight-drift/
- CF Benchmarks, BRRNY methodology note (2025). https://www.cfbenchmarks.com/blog/suitability-analysis-of-the-cme-cf-bitcoin-reference-rate-new-york-variant-as-a-basis-for-regulated-financial-products-march-2025-update
- Kaiko, "BTC ETFs' impact on spot market structure". https://www.kaiko.com/resources/btc-etfs-impact-on-spot-market-structure
- Cboe Insights (2024), option-income funds and volatility. https://www.cboe.com/insights/posts/are-option-income-funds-suppressing-volatility/
- Hazelkorn, Moskowitz & Vasudevan (2023), *JF* 78(1), working paper. https://www.nber.org/papers/w26773
