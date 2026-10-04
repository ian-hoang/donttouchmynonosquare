# Alpha ideas: pre-registered tests

Written 2026-10-03 ~04:40 ET, **before any of these tests touched data**. The file's mtime is the authority on timing.
Each idea has **one primary test** that decides its verdict. Everything marked "robustness" is reported but cannot
rescue a failed primary test. No parameter in this file may be changed after results are seen; if an ambiguity
forces a choice, the implementer writes the choice in that idea's `results.md` with the reason, before running.

Test budget: 5 primary tests (+1 replication of a published strategy). Pass bar: primary t-stat ≥ 2.0 in the predicted
direction **and** net of costs still positive where a trade is defined. Given ~1,900 earlier tests in this repo,
t ≥ 3 is what "convincing" means; 2–3 is "worth a second look".

Shared conventions
- All work lives in `alpha_ideas/<idea>/`. Nothing in `gqh/`, `strategies/`, `microstrategies/`, `massive/` or
  `results/` is modified. `gqh` helpers may be imported read-only.
- Times are America/New_York. Databento hourly bars are re-stamped to their END time (`gqh.data.stamp_bar_end`).
- Treasury futures: cached `ohlcv-1h` for ZT, ZF, ZN, ZB, UB (`.v.0`, `.v.1`), 2010-07-01 → 2026-10-01, returns via
  `gqh.data.roll_safe_returns`. Per-side cost per contract = 0.5 tick spread + 0.5 tick slippage + $1.50 fee
  (same as `strategies/treasury_auction.py`).
- Standard errors: event-level (one observation per event or per month), Newey-West where days overlap.
- A placebo is always reported: the same clock window on non-event days.

---

## Idea 1 — Treasury buyback "reverse V"  (`alpha_ideas/buyback_v/`)
Since May 2024 the U.S. Treasury buys back old coupon securities on a pre-announced schedule. It is the mirror image of
an auction: the government is a forced buyer.

- Events: Fiscal Data `buybacks_operations`, `security_type == "Nominal Coupons"`, `operation_type == "Liquidity
  Support"`, operation date ≥ 2024-05-01. (TIPS, Cash Management and Small Value excluded from the primary test.)
- Bucket → future: 20Y–30Y → UB; 10Y–20Y → ZB; 7Y–10Y → ZN; 5Y–7Y → ZN; 3Y–5Y → ZF; 2Y–3Y → ZT; 1Mo–2Y → ZT.
- Windows (hourly bar END times; operation open time O and close time C from the data):
  - Pre: bars ending in (16:00 previous business day, last full hour ≤ O].
  - Post: bars ending in (first full hour ≥ C + 1h, 16:00 next business day].
- Prediction: pre-window return > 0 (bonds richen into the buyback); post-window return < 0 (give-back).
- **Primary test:** long-end events only (10Y–20Y → ZB, 20Y–30Y → UB). Statistic = mean of (pre − post) return per
  event in bp of price, minus the same statistic on placebo days (all other business days for that contract, same
  clock windows). One-sided prediction: positive. t-stat from the event-vs-placebo difference.
- Trade: long pre-window, short post-window, 1 contract per event. Report net $ per event after 2 round trips.
- Robustness: all buckets; pre and post legs separately; dropping events within 1 business day of a coupon auction
  mapped to the same contract; scaling by accepted par amount.

## Idea 2 — Month-end index extension sized by the auction calendar  (`alpha_ideas/month_end_extension/`)
Bond index funds must buy longer bonds when the Treasury index extends at month-end. Extension is largest when lots of
new long-dated supply settles that month.

- Months: 2010-08 → 2026-09. L = last business day of the month (US federal holiday calendar).
- Predicted extension proxy for month m (known in advance from the auction calendar): Σ over nominal coupon auctions
  (no TIPS, no FRNs; source `data/cache/treasury_auctions.json`) whose `issue_date` falls in month m of
  offering amount ($bn) × original term (years).
- Big month: proxy above the median of the previous 24 months' proxies (only past months; first 24 months used only
  as history). Small month: otherwise.
- Window: long UB from the bar ending 16:00 on L−3 business days to the bar ending 15:00 on L.
- **Primary test:** mean UB window return (bp) in big months minus small months; prediction > 0; Welch t-stat.
- Trade: long UB in the window in big months only. Report net per trade and annualised.
- Robustness: same window but ZB; DV01-neutral flattener (long UB / short ZT, ZT notional scaled by duration
  17.0/1.9); the give-back from 15:00 on L to 16:00 on L+1; continuous proxy regression instead of the split.

## Idea 3 — T+1 shift hunt + replication of Harvey, Mazzoleni & Melone (2025) "front-running rebalancers"
(`alpha_ideas/t1_shift/`)  — uses new data: ES ohlcv-1h `ES.v.0`, `ES.v.1`, 2010-06-07 → 2026-10-01 (~$1.88, approved).

Daily returns use 16:00 ET closes for both ES and ZN (`gqh.data.session_daily` on hourly bars, then roll-safe).

**3a. Replication (exact paper rule, NBER w33554 Section 4 and Appendix B):**
- 60/40 ES/ZN portfolio. Threshold signal δ: weight drifts with returns; reset to 60% on the day after |w−60%| ≥ δ;
  signal = drifted weight − 60% (eq. B.1). Final Threshold signal = average over δ ∈ {0.0%, 0.1%, …, 2.5%}.
- Calendar signal: same drift, reset at the last business day of each month (eq. B.2).
- Position w_t = average of (a) −Threshold_t / 1.5% and (b) modified Calendar: sign(−Calendar_t) if t is in the
  last 5 business days of the month; sign(Calendar_{t−4}) on the first business day of a month (t−4 = four trading
  days earlier); 0 otherwise.
- Strategy return_{t+1} = w_t × (R_ES,t+1 − R_ZN,t+1). Costs: |Δw| × (ES cost + ZN cost) per side.
- Report gross and net: (i) 2010-06 → 2023-03-17 (paper's overlap; paper reports Sharpe 1.11 over 1997–2023),
  (ii) **2023-03-20 → 2026-09-30 = genuine out-of-sample, never published.** Verdict on (ii).

**3b. T+1 shift hunt (the new idea):**
- Regimes by U.S. equity settlement cycle: T+3 (to 2017-09-04), T+2 (2017-09-05 → 2024-05-27), T+1 (2024-05-28 →).
- Settlement-aligned dash-for-cash window: the 3 trading days ending on the last day whose sale settles by month-end,
  i.e. [L−S−2, L−S] for settlement S (T+3: [L−5, L−3]; T+2: [L−4, L−2]; T+1: [L−3, L−1]).
- Outcome: ES daily excess return (16:00 to 16:00).
- **Primary test:** in the T+1 regime, mean ES return on the settlement-aligned window [L−3, L−1] minus the mean on
  the old T+2 window [L−4, L−2], compared with the same difference in the T+2 regime. Prediction: the T+1 regime
  shows relatively more selling pressure (more negative returns) in the shifted window — a difference-in-differences
  < 0. Month-level observations, Welch t-stat.
- Robustness: same using the Harvey rebalancing-signed spread y_t = −sign(Calendar_{t−1}) × (R_ES − R_ZN);
  the T+3 → T+2 shift (2017) as a second natural experiment; full day-by-day profiles k = −10…+2 per regime.
- Honest prior: only ~28 T+1 months, so low power. A null is uninformative, not proof of absence.

## Idea 4 — Smooth losers at month-end  (`alpha_ideas/smooth_losers/`)
Combines Nathan–Suominen–Tasa (2026, "Intramonth Momentum Cycle") with Cai–Li–Keasey (JFQA 2026, "Trended Momentum").

- Data: Massive grouped daily bars (split-adjusted), U.S. common stocks only (Massive reference type CS, active and
  delisted), 2006 → 2026-09. Price returns (no dividends, no delisting returns — a known bias against the short leg).
- Universe each month: price ≥ $5 at formation and top 1,000 by 63-day average dollar volume.
- Formation at the end of month m−1: momentum = return from end of m−13 to end of m−2 (skip a month).
  Trend clarity TC = R² of a regression of daily close on a time trend over the same window (≥ 200 days required).
- Portfolios: winners = top momentum decile, losers = bottom decile. Smooth = TC above the universe median that
  month; rough = below. Equal-weighted.
- PreTOM window (Nathan et al.): the 6 trading days [L−9, L−4] (L = last trading day); from June 2024 on, [L−8, L−3]
  (their documented T+1 shift).
- **Primary test:** daily loser returns in the PreTOM window, smooth losers minus rough losers (a long-rough /
  short-smooth spread, measured per window), 2007-01 → 2026-09. Prediction: smooth losers underperform rough losers in
  the window by more than they do outside the window (difference-in-differences < 0). Month-level t-stat.
- Trade: in the window only, long smooth winners / short smooth losers; 20 bps round-trip per side per leg cost (so
  ~40 bps per month for the long-short pair). Compare with plain WML in the window and with WML held all month.
- Robustness: dollar-volume weights; no T+1 shift; top 500 universe; momentum quintiles; plain-WML replication of the
  PreTOM concentration itself (does the published pattern show up in our data at all?).

## Idea 5 — Kalshi CPI crowd vs. a model forecast  (`alpha_ideas/kalshi_cpi/`)
- CPI releases with Kalshi markets: series `CPI` (2021–) and `KXCPI` (later), headline CPI m/m.
- Crowd forecast: from the strike ladder ("CPI m/m above X%"), last trade price of each strike at or before 07:55 ET on
  release day (or the latest available before that); build P(CPI > X) (monotone-fixed), take the **median**
  (interpolated strike where P crosses 0.5) — the median is immune to the known longshot overpricing in the tails.
- Model forecast: Cleveland Fed nowcast of headline CPI m/m for that month, latest vintage dated before release day
  (free JSON, `nowcast_month.json`).
- d = crowd median − nowcast. Actual = BLS headline CPI m/m (one decimal, from the market's settlement value).
- **Primary test (forecast skill):** regress (actual − nowcast) on d across releases; prediction slope > 0.
- Trade (secondary): ZN position = −sign(d) (crowd sees hotter inflation than the model → short bonds), entered at the
  bar ending 08:00 ET on release day, exited at the bar ending 10:00 ET. Report gross and net bp per release.
- Robustness: mean instead of median; core CPI where markets exist; dropping releases delayed by the 2025 shutdown.
