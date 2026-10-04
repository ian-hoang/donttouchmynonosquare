# Idea 4 — Smooth losers at month-end: results

**Verdict: FAIL.** The pre-registered primary statistic has the wrong sign: +0.86 bp/day, t = +0.22, 208 months.
The pass bar needed t ≤ −2.0.

The "Spec choices" section near the end was written on 2026-10-03 at 04:44 EDT, before any data was fetched or any
test was run. Item 17 was added at about 04:50, while the data was downloading and before `run.py` first ran.
Everything above that section was written after the run.

## In plain English

- **The idea.** Momentum means buying recent winners and shorting recent losers ("WML", winners-minus-losers). A
  2026 paper (Nathan, Suominen & Tasa) finds that most of momentum's profit comes in about six trading days just
  before month-end. They call that window "PreTOM". They explain it with funds selling losing stocks to raise cash
  for month-end. A second 2026 paper (Cai, Li & Keasey) finds momentum works better for stocks whose price moved in
  a smooth, steady line. "Trend clarity" (TC) measures that smoothness as how well a straight line fits the past
  year of prices. Our guess was that month-end sellers dump the *obvious* losers, the ones with a smooth downtrend.
  If so, smooth losers should fall more than choppy ("rough") losers in the PreTOM window, compared with the rest of
  the month.
- **What we found.** They don't. Inside the window, smooth losers did 0.3 bp/day worse than rough losers. Outside
  the window they did 1.2 bp/day worse. So the window gap is actually *less* negative, the opposite of the
  prediction, and the difference is pure noise (t = +0.22). (A bp, or basis point, is 0.01%. A t-stat measures how
  many "standard errors" a result is from zero. Below about 2 in size, it could easily be luck.) Every robustness
  version gives the same answer, and no 6-day window of the month stands out in the placebo scan.
- **Does the published pattern exist in our data at all?** Partly. Losers really do lose in the PreTOM window:
  −9.7 bp/day there versus +6.4 bp/day on other days of the month (t = −2.2). Plain WML earns +11.7 bp/day in the
  window versus +1.7 bp/day outside, which points the right way but is weaker (t = 1.7). The Ken French CRSP
  momentum factor shows the same pattern over the same years (t = 2.1). So the paper's effect is real but modest in
  2007–2026. Our extra twist (smooth vs. rough losers) adds nothing.
- **The trade.** Long smooth winners and short smooth losers, held only for the 6 PreTOM days. Gross, it makes
  +9.7% a year (t = 2.7). After costs of 40 bps per month (0.40%, see the cost convention below), that drops to
  +4.9% a year with a Sharpe of 0.32 and t = 1.35. That is not distinguishable from zero. It is almost the same
  trade as plain WML in the window: the two have a correlation of 0.97, and the smooth filter adds only
  +1.3%/yr (t = 1.5). At 80 bps/month in costs it earns nothing (+0.1%/yr).
- **Bottom line.** Nothing here is worth building on. If anything is left to look at, it is the plain loser effect in
  the PreTOM window, which is a published result rather than our idea. Even that is too small to pay for trading in
  and out every month.

## 1. Replication check: is the published PreTOM pattern in our data?

Mean daily return in the PreTOM window versus the rest of the month. "in − out" is computed month by month, and t
is the month-level t-stat of that difference over 237 months, 2007-01 → 2026-09. Units are bp per day. Base
portfolios: top-1,000 universe, deciles, equal weight.

| series | in PreTOM | outside | in − out | t | share of the sample's total return earned in the window |
|---|---|---|---|---|---|
| WML (winners − losers) | +11.7 | +1.7 | +10.0 | +1.66 | 74% (6 of ~21 days would be 29%) |
| Losers (raw) | −9.7 | +6.4 | −16.1 | **−2.22** | |
| Winners (raw) | +2.0 | +8.1 | −6.1 | −1.02 | |
| Losers − universe average | −8.0 | +0.1 | −8.1 | **−2.18** | |
| Winners − universe average | +3.8 | +1.8 | +2.0 | +0.55 | |
| Universe, equal-weight | −1.7 | +6.3 | −8.0 | −1.81 | |
| *Ken French daily Mom factor (CRSP, value-weighted), same window, 2007-01→2026-08* | +6.3 | −1.4 | +7.7 | +2.14 | 205% (it loses money outside the window) |

- Our daily WML has a correlation of **0.89** with the Ken French momentum factor (4,946 days). That is high for
  two different constructions (ours: equal-weight deciles of the 1,000 most-traded stocks, rebalanced monthly;
  French's: value-weighted 30/70 splits, rebalanced daily), so the Massive data behaves like CRSP.
- The paper's story is "losers losing" in the window, and that part replicates (t ≈ −2.2). The WML concentration
  points the right way but is weaker than published.
- The day-by-day profile (`daily_profile.csv`) is noisy. WML also has big days outside the window, e.g. 13 and 16
  trading days before month-end.

## 2. Primary test (pre-registered)

For each month: S = (smooth-loser return − rough-loser return), daily. DiD = mean S over the 6 PreTOM days minus mean
S over the other days of the month. Prediction: DiD < 0, meaning smooth losers do relatively worse in the window.

| N months | S in window | S outside | **mean DiD** | **t** |
|---|---|---|---|---|
| 208 | −0.31 bp/day | −1.18 bp/day | **+0.86 bp/day** | **+0.22** |

Only 208 of 237 months count, because 29 months had fewer than 5 smooth or 5 rough losers. The rule splits on the
*universe* median TC. Stocks with extreme momentum have smoother trends than average, so smooth losers outnumber
rough ones by about 62 to 36 on average. In some months, such as early 2010 after the 2009 rebound, there are almost
no smooth losers at all. A split at the losers' own median would balance the two groups. It was **not** pre-registered,
so it was not tested. With a standard error of about 4 bp/day and a point estimate on the wrong side of zero, it
would be very unlikely to change the conclusion.

## 3. The trade

Each row is monthly returns on \$1 long + \$1 short. Annualized return = 12 × monthly mean. Vol = √12 × monthly
standard deviation. Sharpe = return / vol. Max DD = worst peak-to-trough fall of the compounded curve.

| strategy | ann. return | ann. vol | Sharpe | t | max DD | % months > 0 | N months |
|---|---|---|---|---|---|---|---|
| Smooth WML, PreTOM only, gross | +9.73% | 15.6% | 0.62 | +2.67 | −26.8% | 62% | 221 |
| **Smooth WML, PreTOM only, net (40 bps/mo)** | **+4.93%** | 15.6% | **0.32** | **+1.35** | −31.8% | 58% | 221 |
| Plain WML, PreTOM only, gross | +8.35% | 14.7% | 0.57 | +2.53 | −21.4% | 61% | 237 |
| Plain WML, PreTOM only, net (40 bps/mo) | +3.55% | 14.7% | 0.24 | +1.07 | −38.3% | 54% | 237 |
| Plain WML, all month, gross | +11.46% | 26.7% | 0.43 | +1.91 | −72.4% | 60% | 237 |
| Plain WML, all month, net (turnover-based) | +10.06% | 26.7% | 0.38 | +1.67 | −73.0% | 59% | 237 |
| *Stricter costs (80 bps/mo in-window; 20 bps/side on turnover all-month):* | | | | | | | |
| Smooth WML, PreTOM only, net | +0.13% | 15.6% | 0.01 | +0.04 | −56.2% | 51% | 221 |
| Plain WML, PreTOM only, net | −1.25% | 14.7% | −0.09 | −0.38 | −64.4% | 49% | 237 |
| Plain WML, all month, net | +8.66% | 26.7% | 0.32 | +1.44 | −73.6% | 58% | 237 |

- **Cost convention.** We charge 10 bps per side for every dollar traded, in each leg. Entering and leaving the long
  leg costs 20 bps, and the same again for the short leg, so the PreTOM trades pay **40 bps per month**. That matches
  the pre-registration's "~40 bps per month for the long-short pair". WML held all month pays the same 10 bps per
  side on its actual monthly turnover. Turnover averages 1.17 dollars traded per month, summed over both legs, which
  is about 12 bps/month.
- **Same months, head to head.** Over the 221 months both strategies trade, smooth WML beats plain WML in the
  window by +1.3%/yr gross (t = 1.46). The two have a monthly correlation of 0.97. The smooth filter adds very little.
- Smooth WML skips 16 months for lack of names (fewer than 5 smooth winners or smooth losers). In the chart and the
  per-year table those months count as cash.
- **Chart:** `cumulative_in_window.png` shows growth of \$1 on a log scale for the three net strategies plus smooth
  WML gross. Holding WML all month collapsed in the 2009 momentum crash (−73% peak-to-trough). The PreTOM-only
  versions avoid most of that but earn little after costs.

Per-year compounded returns. A skipped month counts as cash.

| year | smooth WML in-window gross | net | plain WML in-window gross | net | WML all month gross | net |
|---|---|---|---|---|---|---|
| 2007 | +20.3% | +14.8% | +19.3% | +13.8% | +53.0% | +50.7% |
| 2008 | +20.2% | +14.7% | +26.6% | +20.8% | −2.5% | −3.7% |
| 2009 | −9.5% | −13.1% | −3.8% | −8.3% | −55.6% | −56.4% |
| 2010 | +11.4% | +8.8% | −0.2% | −4.9% | +3.2% | +1.5% |
| 2011 | +1.1% | −2.9% | +2.8% | −2.0% | +9.5% | +7.9% |
| 2012 | +10.1% | +5.0% | +13.0% | +7.7% | +13.9% | +12.4% |
| 2013 | +4.1% | −0.7% | +4.0% | −0.9% | +30.4% | +28.7% |
| 2014 | +8.2% | +3.1% | +2.0% | −2.7% | −2.9% | −4.1% |
| 2015 | +21.8% | +16.2% | +19.9% | +14.3% | +36.2% | +34.6% |
| 2016 | −6.1% | −10.5% | −6.2% | −10.7% | −21.4% | −22.6% |
| 2017 | +2.4% | −2.4% | +2.4% | −2.4% | +5.7% | +4.3% |
| 2018 | −4.6% | −9.1% | −4.1% | −8.7% | +12.0% | +10.6% |
| 2019 | +6.1% | +1.2% | +4.4% | −0.5% | +3.0% | +1.6% |
| 2020 | +16.6% | +11.1% | +12.8% | +7.6% | +36.4% | +34.6% |
| 2021 | +13.5% | +10.9% | +21.4% | +15.8% | −1.8% | −3.3% |
| 2022 | +25.3% | +19.5% | +21.0% | +15.4% | +55.8% | +53.9% |
| 2023 | +2.1% | −2.7% | +1.9% | −2.9% | −18.5% | −19.7% |
| 2024 | +16.2% | +10.9% | +14.1% | +8.8% | +40.9% | +38.9% |
| 2025 | +5.3% | +0.4% | +0.9% | −3.8% | +20.6% | +19.0% |
| 2026 (Jan–Sep) | +6.0% | +2.3% | +4.5% | +0.8% | +11.1% | +10.1% |

## 4. Robustness (reported; cannot rescue the primary)

| variant | N | DiD bp/day | t | S in window | S outside | trade gross ann. | trade net ann. | net Sharpe | net t |
|---|---|---|---|---|---|---|---|---|---|
| base (pre-registered) | 208 | +0.86 | +0.22 | −0.31 | −1.18 | +9.7% | +4.9% | 0.32 | +1.35 |
| dollar-volume weights | 208 | +3.55 | +0.61 | +3.55 | −0.00 | +11.2% | +6.4% | 0.33 | +1.41 |
| no T+1 shift ([L−9, L−4] always) | 208 | +1.12 | +0.28 | −0.17 | −1.28 | +8.7% | +3.9% | 0.24 | +1.04 |
| top-500 universe | 172 | +3.20 | +0.65 | +2.62 | −0.58 | +8.4% | +3.6% | 0.22 | +0.90 |
| momentum quintiles | 229 | −0.09 | −0.04 | −1.85 | −1.76 | +6.8% | +2.0% | 0.16 | +0.70 |
| *descriptive:* months before Jun-2024 | 180 | +0.66 | +0.15 | −1.02 | −1.68 | +9.7% | +4.9% | 0.32 | +1.27 |
| *descriptive:* months from Jun-2024 (T+1) | 28 | +2.12 | +0.31 | +4.22 | +2.09 | +9.8% | +5.0% | 0.30 | +0.46 |

Every variant has |t| < 0.7 on the DiD, and four of the five have the wrong sign. The only one with the predicted
sign is quintiles (t = −0.04).

**Placebo scan.** The same DiD for every 6-day window [L−k−5, L−k], with the same k in every month (`placebo.csv`).
The real PreTOM is k = 4, or k = 3 after May 2024.

| window | smooth − rough losers DiD (bp/day) | t | plain WML DiD (bp/day) | t |
|---|---|---|---|---|
| [L−5, L−0] | −0.98 | −0.30 | −3.67 | −0.72 |
| [L−6, L−1] | −3.04 | −0.77 | +0.33 | +0.06 |
| [L−7, L−2] | −1.86 | −0.42 | +3.87 | +0.64 |
| [L−8, L−3] | +3.19 | +0.79 | +8.97 | +1.48 |
| **[L−9, L−4]** | +1.12 | +0.28 | +8.26 | +1.31 |
| [L−10, L−5] | +4.77 | +1.18 | +5.31 | +0.86 |
| [L−11, L−6] | +1.41 | +0.40 | +7.25 | +1.03 |
| [L−12, L−7] | +1.35 | +0.36 | +3.85 | +0.58 |
| [L−13, L−8] | +5.18 | +1.34 | +6.77 | +1.12 |
| [L−14, L−9] | +1.06 | +0.27 | +5.18 | +0.82 |
| [L−15, L−10] | +0.72 | +0.18 | +1.31 | +0.21 |
| [L−16, L−11] | −2.74 | −0.59 | +8.67 | +1.37 |
| [L−17, L−12] | −2.08 | −0.51 | +3.65 | +0.60 |

No window is special for the smooth-vs-rough spread: all |t| < 1.4. For plain WML, the windows just before
month-end have the largest values (t ≈ 1.3–1.5), which fits the paper's pattern, but several mid-month windows come
close.

## 5. Data and caveats

- **Data:** 5,470 trading days (2005-01-03 → 2026-09-30) and 24.0 million stock-days for 11,812 CS tickers. The
  Massive CS reference list has 11,951 unique tickers: 5,322 active rows and 6,634 inactive. No day was thin (no day
  had fewer than 80% of the usual ticker count). We dropped 2,712 daily returns with |r| > 100% and 13,140 returns
  bridging a gap of more than 5 trading days.
- **Universe:** after the $5 (unadjusted) and top-1,000 dollar-volume screens, 973 names a month on average
  (range 926–990) have enough history for momentum and TC. Deciles hold about 98 names. Smooth losers average 62
  names and rough losers 36.
- **Survivorship gap (biggest caveat).** Massive's CS list is missing many large stocks that delisted or changed
  ticker before about 2015: EMC, Bear Stearns, Wachovia, Genzyme, Sears, and Priceline under its old ticker PCLN.
  Some of those tickers now belong to ETFs or ADRs. In 2007 we see about 3,900 CS tickers a day, against
  something like 4,500–5,000 U.S. common stocks in CRSP at the time (a rough figure, not checked against CRSP here).
  In the Q4-2007 check, 359 of the 1,300 most-traded tickers were not in the CS list, though most of those are ETFs
  and ADRs that are rightly excluded. By 2021–2026 we see about 5,100–5,600 a day. The 0.89 correlation with the CRSP-based French factor suggests the momentum
  portfolios are still representative.
- **Ticker reuse and changes.** The match is by ticker string with no date check. A company that changed ticker
  (e.g. FPL → NEE) loses its history, and a reused ticker can join two companies across a short gap.
- **No delisting returns, no dividends.** These are price returns only. A failing loser that delists simply drops out,
  so its last loss is missing. That makes losers look better than they were, which works *against* the short-loser
  trades.
- **Split-adjusted only.** Spin-offs are not adjusted. For example, Altria shows a fake −70% on 2008-03-31, the day
  Philip Morris International was spun off. There are rare bad prints with |r| ≤ 100% that survive the filter, such
  as a glitch on 2007-06-13 affecting 8 universe names. Spike-and-reverse events among held names are rare (424 over
  20 years, mostly real crash days in late 2008 and March 2020).
- **Execution.** Trades are assumed to fill at the close. The in-window trade needs about 12 round trips a year in
  each leg, so its result depends heavily on costs. The 40 bps/month assumption is modest for the short side of
  losers (borrow fees are not included).
- **The T+1 period is short:** only 28 months, so nothing can be said about the June-2024 shift specifically.

## Bug fixes after the first run

- **bug:** in the trade table, *plain* WML (in-window and all-month) was also dropped in the 16 months where smooth
  winners or smooth losers had fewer than 5 names. Plain WML doesn't use those portfolios, so this contradicted spec
  item 11. **fixed:** each strategy is dropped only when its own portfolios are thin, so plain WML now uses all 237
  months. Plain WML in-window gross changed from +8.42% to +8.35%/yr, and all-month gross from +12.98% to
  +11.46%/yr. The primary test and the smooth trade are unchanged.
- **Chart only:** the axis and title formatting were fixed (dollar signs were read as math markup), and months a
  strategy skips are now drawn as flat cash instead of a straight line across the gap. The numbers did not change.

## Files

- `fetch_data.py` downloads the data into `data/cache/massive_grouped/` (gitignored).
- `run.py` runs the whole analysis: `uv run python alpha_ideas/smooth_losers/run.py`, about 1 minute.
- `monthly_primary.csv` has, per month: portfolio sizes, median TC, and S in/out/DiD.
- `monthly_trades.csv` has monthly gross and net returns of the three strategies, plus WML turnover.
- `yearly.csv` holds the per-year table, `robustness.csv` the robustness table, and `placebo.csv` the window scan.
- `replication.csv` holds the PreTOM concentration check, including the Ken French factor.
- `daily_profile.csv` has the mean bp/day by trading day before month-end, k = 0…22.
- `cumulative_in_window.png` is the cumulative chart.

## Spec choices made before running (ambiguities in PREREGISTRATION.md, Idea 4)

Each item: the choice, then why. Where the pre-registration is explicit, it is followed literally.

1. **Data.** Massive grouped daily bars `GET /v2/aggs/grouped/locale/us/market/stocks/{date}`, 2005-01-03 → 2026-09-30,
   weekdays only (holidays come back empty and are skipped). Stored as one parquet per year in
   `data/cache/massive_grouped/` (gitignored). The trading calendar is the set of dates with a non-empty response.
2. **Common stocks.** Ticker kept if it appears in Massive `/v3/reference/tickers?market=stocks&type=CS` with
   `active=true` **or** `active=false`. Why: the pre-registration says "type CS, active and delisted". No date-matching
   of ticker vs. company (see caveats: ticker reuse).
3. **Two price series.** Returns, momentum and trend clarity use **split-adjusted** closes (`adjusted=true`), as
   pre-registered. The **$5 price screen uses the unadjusted close** (`adjusted=false`, i.e. the price that actually
   traded on the formation day). Why: "price ≥ $5 at formation" literally means the traded price; screening on
   today's split-adjusted history would drop stocks that later split (future winners like AAPL/NVDA in 2007 show
   adjusted prices < $5) and keep stocks that later reverse-split — a look-ahead bias. Dollar volume is split-invariant,
   so it is computed as adjusted close × adjusted volume.
4. **Daily return** of a ticker on trading day t = close_t / (its most recent earlier close) − 1. Dropped (set missing)
   if that earlier close is more than 5 trading days old (i.e. more than 5 missing trading days in between), or if
   |r| > 100%. A return that spans a short gap (≤ 5 missing days) is booked on the day the stock reappears.
5. **L** = last trading day of the month in our calendar. **L−k** = k trading days before L.
   **PreTOM** = [L−9, L−4] (6 days, inclusive) for month-ends up to and including **May 2024**; [L−8, L−3] for
   month-ends from **June 2024** on. Why: the pre-registration says "from June 2024 on" — so the May-2024 month-end
   (whose L−3 is 2024-05-28, the first T+1 day) still uses the old window.
6. **Formation** for holding month m happens on F = L of month m−1. Portfolios are held for every trading day of
   month m (returns of day F+1 … L_m). Everything used at formation is known at the close of F.
7. **Universe order of operations.** (a) CS stocks with a bar on F and unadjusted close ≥ $5; (b) rank by 63-day
   average dollar volume and keep the top 1,000; (c) then drop names without a valid momentum or TC (fewer than 200
   closes in the window, or a missing end-point close). Deciles and the TC median are computed over what is left.
   Why: the pre-registration defines the universe by price and dollar volume, and lists the 200-day requirement as a
   requirement of TC, so it is applied after the universe is formed (the most literal reading). The average number of
   names lost in step (c) is reported.
8. **63-day average dollar volume** = sum of close×volume over the 63 trading days ending on F (inclusive), divided by
   63; a day with no bar counts as zero dollar volume.
9. **Momentum** = adjusted close at L(m−2) / adjusted close at L(m−13) − 1. If a stock has no bar exactly on one of
   those two dates, its last close within the 5 previous trading days is used; otherwise momentum is missing.
10. **Trend clarity (TC)** = R² of an OLS of the adjusted daily close (price level, not log) on the trading-day index,
    using every available close with L(m−13) ≤ date ≤ L(m−2) (both ends included, ~232 days). At least 200 closes
    required. Missing days are simply skipped (the time index keeps the true trading-day spacing).
11. **Portfolios.** Winners = top momentum decile, losers = bottom decile (`qcut` of momentum rank into 10 equal-count
    bins within the universe). Smooth = TC strictly above the universe median TC that month; rough = the rest.
    Equal-weighted, **rebalanced daily to equal weights** among members with a valid return that day (this is what
    "mean daily return" means). A month is dropped from a test if any portfolio it needs has fewer than 5 names.
12. **Primary statistic.** For each holding month m: S_t = r(smooth losers)_t − r(rough losers)_t.
    in_m = mean of S_t over the 6 PreTOM days; out_m = mean of S_t over all other trading days of month m (including the
    turn-of-month days L−3…L or L−2…L). DiD_m = in_m − out_m. Statistic = mean of DiD_m over 2007-01 … 2026-09,
    plain t-stat across months (months do not overlap, so no Newey-West). Prediction: mean < 0.
    **Pass bar** (from the pre-registration): t ≤ −2.0 **and** the net trade return > 0. t ≤ −3 = convincing;
    −3 < t ≤ −2 = worth a second look.
13. **Trade.** Long smooth winners / short smooth losers, in the PreTOM window only, cash otherwise. Enter at the close
    of the day before the window, exit at the close of the window's last day. Monthly trade return per \$1 long + \$1
    short = (∏(1+r_long) − 1) − (∏(1+r_short) − 1) over the 6 window days.
14. **Cost convention.** 10 bps per side, per dollar traded, per leg = 20 bps round trip per leg. An in-window
    trade enters and exits both legs every month: 2 legs × 20 bps = **40 bps per month** per \$1 long + \$1 short —
    the "~40 bps per month for the long-short pair" stated in the pre-registration. "WML held all month" is charged the
    same 10 bps per side on its actual monthly turnover (sum of |weight changes| per leg at the monthly rebalance,
    using equal weights at formation), so it is not over-charged. A stricter sensitivity at **80 bps** per month
    (20 bps per side per leg) is also reported; it cannot rescue or sink the verdict, which uses 40 bps.
15. **Metrics.** Monthly returns: annualized return = 12 × mean; vol = √12 × std; Sharpe = ratio of those two (no
    risk-free rate subtracted: the strategy is a self-financing long-short); t = mean / (std/√N); max drawdown on the
    compounded monthly equity curve; per-year table = compounded return within each calendar year.
16. **Robustness (reported, cannot rescue the primary):** (i) dollar-volume weights — weights proportional to the
    formation 63-day average dollar volume, held at those relative weights (renormalized daily over names with a
    valid return); (ii) no T+1 shift — [L−9, L−4] for every month; (iii) top-500 universe; (iv) momentum quintiles
    instead of deciles; (v) plain-WML replication of the PreTOM concentration (WML, losers and winners: mean daily
    return in vs. out of PreTOM, month-level t); (vi) placebo: the same DiD statistic for every 6-day window
    [L−k−5, L−k], k = 0…12, using the same k in every month (a pure "clock position" scan; k = 4 is the pre-T+1
    PreTOM). It shows whether the PreTOM position is special or just one of many similar windows.
17. **Observation while fetching (before any test ran), kept as-is:** Massive's CS reference list (11,951 tickers:
    5,322 active, 6,634 inactive) misses many large stocks that delisted or changed ticker before ~2015 — e.g. EMC,
    Bear Stearns (BSC), Wachovia (WB), Genzyme (GENZ), Sears (SHLD), Priceline under its old ticker PCLN, Staples
    (SPLS). Some of those tickers now belong to ETFs/ADRs, some old records have no type at all (RIMM). Of the 1,300
    highest dollar-volume tickers in Q4-2007, 359 are not in the CS list (most are ETFs/ADRs, correctly excluded, but
    many are genuine U.S. common stocks). The pre-registered rule ("type CS, active and delisted") is applied anyway;
    this is a survivorship gap that shrinks over time and is listed under the caveats.
18. **Data sanity check (not a test):** correlation of our daily WML with the Ken French daily momentum factor
    (`data/cache/F-F_Momentum_Factor_daily_CSV.zip`, through 2026-08), and the same in/out-of-PreTOM split computed on
    that CRSP-based factor as a reference point for the replication.
