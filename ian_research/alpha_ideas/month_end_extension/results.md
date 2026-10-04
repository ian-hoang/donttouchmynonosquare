# Idea 2 — Month-end index extension sized by the auction calendar: results

(Summary and results sections are filled in after the run; the "Spec choices" section below was written
before `run.py` computed any window return.)

Reproduce: `uv run python alpha_ideas/month_end_extension/run.py` (reads only cached futures bars and
`data/cache/treasury_auctions.json`; prints everything to `run_output.txt`; one row per month in `months.csv`).

## Verdict: FAIL

**Plain-English summary.** Bond index funds have to buy longer bonds at each month-end when the index "extends". We
asked whether the long-bond future (UB) rallies more into month-end in months when a lot of new long-dated Treasury
debt settles, which should mean a bigger extension. UB did rally into month-end on average (+24 bp over the last ~3
days, t = 2.8; this is the well-known month-end effect). The rally was bigger in "big supply" months (+35 bp) than in
"small" months (+14 bp), but the 21 bp gap is not statistically reliable (**Welch t = 1.20**; the pass bar is t ≥ 2).
The matched placebo makes it look weaker still: the same window 10 business days earlier shows a 54 bp gap the
*other* way, so the big/small label is mixed up with other things that happen in those months. Verdict: **FAIL** for
the pre-registered idea. Going long UB in big months did make money (+30 bp a trade after costs), but most of that is
the ordinary month-end rally, which also paid in small months.

## Primary test: UB return over (16:00 on L−3, 15:00 on L], big minus small months

| | value |
|---|---|
| Test months | 170 (2012-08 → 2026-09): 85 big, 85 small |
| Mean UB window return, big months | +34.81 bp |
| Mean UB window return, small months | +13.74 bp |
| **Big − small** | **+21.07 bp** |
| **Welch t (one-sided p)** | **+1.20 (p = 0.115)** |
| All months (the plain month-end effect, for context) | +24.28 bp, t +2.77 |
| Sub-periods, big − small | 2012-08→2016: +4.1 bp (t 0.17); 2017→2020: +2.7 bp (t 0.08); 2021→2026-09: +42.7 bp (t 1.33) |

Any gap comes from 2021 on. Before that, big and small months behaved the same.

**Placebo (same clock window on non-month-end days):**

| placebo | result |
|---|---|
| P1: same-length window ending 15:00 on L−10, same months and labels, big − small | **−53.74 bp, Welch t −2.52** (big months 22.6 bp *weaker*) |
| P2: every non-month-end 3-day window (2,699 days) vs the month-end window | non-month-end −9.23 bp vs month-end +24.28 bp: difference +33.51 bp, t +3.46 |

P2 says the generic month-end effect is real in this sample. P1 says the big/small label is far from a clean
"month-end only" marker: in big months UB does much *worse* in the middle of the month, probably because big-supply
months also carry more auction supply mid-month. The pre-registered month-end gap (+21 bp) is smaller than that
mid-month gap, so we cannot pin it on month-end extension.

## Trade: long 1 UB over the window, big months only

Cost = 2 sides × $32.75 = **$65.50 per trade = 5.24 bp** at the spec price. 85 trades over 14.16 years = 6.0 a year.

| per trade | mean | median | sd | t | hit rate |
|---|---|---|---|---|---|
| gross bp | +34.81 | +37.65 | 100.8 | +3.18 | 66% |
| **net bp** | **+29.57** | +32.41 | 100.8 | +2.70 | 62% |
| gross $ per contract | +$551.87 | +$562.50 | $1,643 | +3.10 | 66% |
| **net $ per contract** | **+$486.37** | +$497.00 | $1,643 | +2.73 | 64% |

Annualised: **+177 bp of UB notional ≈ +$2,919 per contract per year, net Sharpe ≈ 0.72**. For comparison, the same
trade in *small* months averaged +8.5 bp net, and in *all* months +19.0 bp net. The trade is profitable mainly because
it is long into month-end at all, which is a known, published effect. Choosing big months adds a gap that is not
statistically different from zero. **Do not read the trade's t = 2.7 as support for the pre-registered idea.**

## Robustness (reported only; none of these can rescue the primary)

| check | big | small | big − small | t |
|---|---|---|---|---|
| ZB, same window | +31.92 bp | +9.41 bp | +22.51 bp | Welch +1.67 |
| DV01-neutral flattener, UB − 8.947 × ZT | −0.83 bp | −8.97 bp | +8.14 bp | Welch +0.53 |
| Give-back UB, (15:00 L, 16:00 L+1] | +7.45 bp | −14.69 bp | +22.14 bp | Welch +1.35 |

- Flattener: once the general rate move is hedged out with ZT, the long-end-specific part is about zero in big
  months (−0.8 bp gross, **−14.1 bp net** after 13.25 bp of costs, t −1.40). Index extension should show up as long-end
  *outperformance*, and it does not.
- Give-back: there is no reversal after month-end in big months (+7.5 bp, t 0.63). The difference from small months
  points the opposite way to a "pressure then give-back" story.
- Continuous proxy, (i) UB return on log(proxy / trailing-24-month median): slope +11.0 bp per log unit, t(HC1) +0.48.
- Continuous proxy, (ii) UB return on the raw proxy ($tn × years): slope −1.7 bp per $tn·yr, t(HC1) −0.14.
  The size proxy has essentially no linear relation to the month-end return.

## Sanity and look-ahead checks

- Example (printed in `run_output.txt`): for 2012-08, L = Fri 2012-08-31. The window uses 67 bars from the bar ending
  Tue 08-28 17:00 to the bar ending Fri 08-31 15:00. Proxy $1,264bn·yr vs trailing median $1,146bn·yr → big.
  For 2026-09, the proxy equalled the trailing median exactly (2,280), so it is small under the strict "above" rule.
- 12 of 170 windows have no bar exactly at an endpoint: three Good Fridays (2013-03, 2018-03, 2024-03), the Thanksgiving
  early closes in several Novembers, 2020-02 and 2020-06. They are kept per the literal window rule.
- No look-ahead. The trailing median uses months m−24 … m−1 only. In all 170 test months, every auction counted in that
  month's proxy was announced **before** the window opened (0 violations; smallest gap 4.2 days).
- Data came from cache only: no "Downloading" line, and every yearly cache file was confirmed on disk before the run.

## Caveats

- The proxy grows with total issuance, which roughly doubled from 2012–2016 to 2021–2026. Against a trailing 24-month
  median, months during issuance ramp-ups (2018–2021, 2024) are mostly "big" (67–75% of months) and ramp-downs (2014,
  2022) mostly "small" (25%). So the label partly measures *growth* in supply, not just the size of that month's
  extension.
- The sample is 170 months, and UB moves about 100 bp over a 3-day window. A real 10–20 bp extension effect would need
  much more data to pass t ≥ 2.

## Spec choices and ambiguities (written BEFORE running)

Written 2026-10-03 before the first run. The only data looked at beforehand: the auction JSON's fields and date
coverage (issue dates 2010-06-15 → 2026-10-15) and hourly-bar completeness. No proxy split or window return was
computed before this section was written.

1. **Nominal coupon auctions.** `inflation_index_security == "No"` and `floating_rate == "No"` (the cached JSON already
   holds only `security_type` Note/Bond). Remaining `original_security_term` values are 2, 3, 5, 7, 10, 20, 30-Year.
   Reopenings are included (they are new supply). Term in years = the leading number of `original_security_term`
   (a reopened 10-year counts as 10, not 9y10m). Offering amount = `offering_amt` / 10⁹.
2. **Month assignment** = calendar month of `issue_date` exactly as recorded. When month-end falls on a weekend the
   2/5/7-year notes are issued on the next month's first business day and therefore count in the next month (literal).
3. **Big/small.** Proxy for 2010-08 → 2026-09. Big if proxy_m > median(proxy_{m−24} … proxy_{m−1}) (strictly above;
   only past months). Months 2010-08 → 2012-07 are history only. Test months 2012-08 → 2026-09 = 170.
4. **Window.** L = last business day of the month under `CustomBusinessDay(USFederalHolidayCalendar)`; L−3 = three
   such business days earlier. UB return = Π(1 + r) − 1 over `UB.v.0` `roll_safe_returns` for bars whose END time is
   in (16:00 ET on L−3, 15:00 ET on L]. If L is Good Friday (2013-03-29, 2018-03-30, 2024-03-29; not a federal
   holiday, but CME rates were closed or abbreviated) the window just has no bars on L — kept, literal reading.
5. **Primary test.** Mean big-month return − mean small-month return (bp), Welch (unequal-variance) t. Prediction
   one-sided > 0. Months do not overlap, so no Newey–West needed.
6. **Trade.** Long 1 UB over the window in big months only. Cost = 2 sides × (1 tick × 1/32 × $1,000 + $1.50) =
   $65.50 per trade = 5.24 bp at the spec price 125. $ P&L = window return × UB close at window start × $1,000.
   Annualised = mean net per trade × trades per year (n_big / 14.17 years, 2012-08 → 2026-09), plus Sharpe =
   mean / sd × √(trades per year).
7. **Robustness** (reported only):
   - ZB, same window: big − small, Welch.
   - DV01-neutral flattener: r_UB − (17.0 / 1.9) × r_ZT, each leg's window return compounded separately; big − small,
     Welch. Also net in big months with cost = UB 2 sides + (17/1.9) × ZT 2 sides, in bp of UB notional (ZT per side
     at spec price 104: 0.448 bp).
   - Give-back: UB bars ending in (15:00 ET on L, 16:00 ET on L+1); big − small, Welch; and the big-month mean.
   - Continuous proxy regression (OLS, HC1 SE) of the UB window return on (i) log(proxy_m / trailing-24-month median),
     the continuous version of the split, and (ii) the raw proxy in $tn·years, the most literal reading.
     Both are reported; neither can rescue the primary.
8. **Placebo** (shared convention: same clock window on non-event days):
   - P1 (matched): same-length window ending 15:00 on L−10 (start 16:00 on L−13), same months, same big/small labels,
     big − small Welch. If big months are simply bond-bullish months, P1 shows the same gap.
   - P2 (unconditional): mean UB return over (16:00 on d−3, 15:00 on d] for every business day d, 2012-08 → 2026-09,
     whose window does not overlap any month-end window (d not in [L−2, L+2] business days). Newey–West SE with 3 lags
     (windows overlap by up to 3 days). Compared with the all-months month-end mean.
9. **Look-ahead checks.** The trailing median uses only months before m (shift by one). For every test month the
   latest `announcemt_date` (taken as 11:00 ET) of any auction in that month's proxy is compared with the window start
   (16:00 ET on L−3); the number of months where an included auction was announced after the window started is
   printed and reported.

## Bug fixes after the first run

- None. The script ran once as written, and a second run produced byte-identical `run_output.txt`.
