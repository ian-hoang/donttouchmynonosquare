# Idea 5 — Kalshi CPI crowd vs. Cleveland Fed nowcast

## Verdict: **FAIL** (by the pre-registered bar), with a strong forecasting result inside it

The crowd really is a better CPI forecaster than the Cleveland Fed model (slope 1.06, **t = 7.1**, 57 releases),
so half of the pass bar is cleared easily. The other half, "net of costs still positive where a trade is defined",
is not: the ZN trade loses **−4.5 bp per release after costs** (−1.4 bp before costs, t = −0.2). The bond market
already knows what the Kalshi crowd knows, so the crowd's edge over the model is not an edge over the bond market.

One sensitivity flips this (spec choice 7 below): with the uncorrected "label" median the trade nets +4.9 bp
(t = 0.75), which would nominally pass. That version is biased toward long bonds (72 % of trades long), and just
being long ZN on these mornings earns about the same. That choice was written down before the first run.

## Plain-English summary

**The idea.** Each month, before the CPI inflation number comes out (08:30 ET), people bet on Kalshi on contracts
like "Will CPI rise more than 0.3% this month?". A contract trading at 70¢ means the crowd thinks there's about a 70 %
chance. With a ladder of these contracts (above 0.1, above 0.2, …) you can read off the crowd's middle guess (the
**median**). The Cleveland Fed publishes a free model forecast of the same number (the **nowcast**). The question:
when the crowd and the model disagree, who is right? And can you trade bonds on it?

**What we measured.** For every CPI release we took each contract's last trade price at or before 07:55 ET that
morning. From those prices we got the crowd median. We took the model's last forecast from the day before, and we
read the real CPI number from how Kalshi settled the contracts.
- d = crowd median − model forecast. Positive d means the crowd expects hotter inflation than the model.
- The test regresses (actual − model) on d. A slope of 1 means "whenever they disagree, the actual lands where the
  crowd said". A slope of 0 means the crowd's disagreement is noise.
- The trade: if the crowd is hotter than the model, sell 10-year Treasury futures (ZN) at 08:00 ET and buy back at
  10:00 ET. If cooler, buy. Hotter inflation usually means lower bond prices. "bp" means basis points
  (0.01 %) of the futures price. One ZN contract is about $111k notional, so 1 bp ≈ $11 per contract.

**What we found.**
1. **The crowd beats the model, and by a lot.** Slope = 1.06 (standard error 0.15), t = 7.1, R² = 0.48. The usual bar
   for "probably not luck" is t ≥ 2, and with ~1,900 earlier tests in this repo t ≥ 3 is the bar for "convincing";
   t = 7 clears both. The slope is close to 1, so when the two disagree you should basically just believe the crowd.
   It holds in both halves of the sample (2021–23: t = 5.0; 2024–26: t = 4.1) and for core CPI (t = 3.9).
   Typical miss (mean absolute error): crowd median 0.085 percentage points vs model 0.125. Rounded to one
   decimal, the crowd median hits the exact printed number 42 % of the time vs 32 % for the model.
2. **But you can't make money trading bonds on it.** Gross −1.4 bp per release, net −4.5 bp after 3.1 bp round-trip
   costs. That's a coin flip: 53 % hit rate, t = −0.2. The bonds aren't ignoring CPI. ZN moves hard on the
   *surprise relative to the crowd* (about −29 bp per 0.1 pp surprise, t = −7). It just doesn't move on
   *crowd vs model* (t = −0.4). Bond traders already price the consensus view. The Cleveland model is the slow
   one here, not the bond market.

**Bottom line for the strategy book:** keep this as a useful fact, not a strategy. Kalshi CPI prices are a good
real-time consensus forecast, better than the free Cleveland Fed nowcast. Use them as an input: for example, define
"surprise" as actual − Kalshi median when studying post-release moves. Do not trade ZN on crowd-vs-model
disagreement.

## Key numbers (headline CPI, primary sample)

| | value |
|---|---|
| Releases used (N) | **57** (Nov 2021 → Sep 2026 release dates; target months Oct 2021 → Aug 2026) |
| Primary slope of (actual − nowcast) on d | **1.061** (SE 0.150), **t = 7.09** (White/HC1 t = 7.24), intercept −0.005, R² 0.48 |
| Trade: ZN −sign(d), 08:00→10:00 ET | gross **−1.37 bp**/release (t −0.21); net **−4.46 bp** (t −0.67); hit rate 52.6 %; 46 % of trades long; total −254 bp |
| Cost assumption | 1.54 bp per side = 3.09 bp per round trip (0.5 tick spread + 0.5 tick slippage + $1.50, ZN @111) |
| Mean absolute error vs actual | crowd median 0.085 pp · crowd mean 0.088 · nowcast 0.125 |
| RMSE / bias (actual − forecast) | crowd median 0.118 / −0.005 · nowcast 0.164 / −0.010 |
| Exact hit after rounding to 0.1 | crowd median 42 % · crowd mean 46 % · nowcast 32 % |

## Robustness (reported, cannot rescue the primary)

| variant | N | slope (t) | trade gross / net bp |
|---|---|---|---|
| Primary (crowd median, continuity-corrected) | 57 | 1.06 (7.09) | −1.37 / −4.46 |
| Crowd **mean** instead of median | 57 | 1.04 (6.41) | +0.24 / −2.84 |
| **Drop 2025-shutdown-delayed** releases (Sep 2025, Nov 2025; Oct 2025 already out) | 55 | 1.06 (6.94) | −1.53 / −4.61 |
| **Core CPI** (`CPICORE`/`KXCPICORE`, Jun 2022 → Aug 2026 data months) | 50 | 0.64 (3.94; HC1 3.57) | −1.48 / −4.56 |
| Sensitivity: label-scale median, no +0.05 correction (spec choice 7) | 57 | 1.06 (7.09) identical | +8.03 / **+4.94** (t 0.75), 72 % long |

Core accuracy (MAE): crowd median 0.076 pp, crowd mean 0.084, nowcast 0.092. The edge is smaller for core.
The model and the crowd agree more often on core, so there is less disagreement to exploit.

**About the label-scale row.** Without the +0.05 correction, the crowd median sits 0.045 pp *below* the actual on
average (bias +0.045 in the actual − forecast sense, versus −0.005 with the correction). That pushes d negative, so
the rule goes long ZN 72 % of the time. Being long ZN in this window on these 57 mornings earns +3.2 bp gross
(+0.1 bp net, t 0.48) all by itself. The positive net is mostly that long tilt plus noise (t 0.75), not
information in sign(d).

## Placebo (same 08:00→10:00 window, non-CPI days)

- On the 57 CPI mornings, ZN's average absolute 2-hour move is 37.6 bp (std 50.4). On 1,200 non-CPI business days in
  the same period it is 15.4 bp (std 21.1, mean −0.6 bp). CPI really is the event in this window.
- Placebo trade: each release's position applied to the same window on the 5 business days before that release.
  Mean −0.19 bp per day, t = −0.17. Nothing there, as expected.

## Post-hoc diagnostics (added after the first run to explain it; not pre-registered)

- Primary slope by sub-period: 2021–2023: 1.12 (t 5.0, N 25); 2024–2026: 1.07 (t 4.1, N 32). Spearman rank
  correlation of d with (actual − nowcast): 0.74. So the result isn't driven by a few big months. For most of 2023
  the Cleveland headline nowcast ran 0.1–0.2 pp too hot, and the crowd did not.
- ZN return (bp) on surprise vs crowd (actual − crowd median): slope −291 bp per 1 pp (t −7.1, R² 0.47). ZN return on
  d: slope −27 (t −0.4, R² 0.003). This is the mechanism behind the failed trade.
- Always long ZN on the 57 release mornings: +3.19 bp gross, +0.11 bp net (t 0.48).

## Data coverage & caveats

- **Events.** Series `KXCPI` lists 67 headline events (`CPI-21JUN` … `KXCPI-26DEC`); 63 have been released. 57 are
  used. Excluded: Jun–Sep 2021 (a single strike each, so no ladder), Feb 2022 (all 4 strikes 0.4–0.7 traded above
  50 %, so the median sits above the ladder; actual was 0.8), and Oct 2025 (BLS never published it because of the
  shutdown, though Kalshi settled it at 0.2). Every used market's `rules_primary` is headline CPI month-over-month.
  None are year-over-year.
- **Trades.** 502 headline and 448 core strike snapshots, from Kalshi's live and historical trade endpoints combined.
  The newest strike trade is typically 8 h before the 07:55 cut-off (median). Through mid-2025 there was little
  overnight trading. Since Jul 2025 it is minutes before. Tail strikes are often days or weeks stale (median of the
  oldest strike: 138 h). The median is robust to stale tails; the mean is less so. 24 of 57 ladders needed a
  monotone fix (66 strike prices adjusted).
- **Timing.** In 2021 the markets closed the evening before release, and Sep 2025's markets closed 9 days before
  the delayed release. In those cases the crowd snapshot is older than 07:55 on release day. The nowcast vintage is
  the day before release (every release), so the crowd has at most an overnight information advantage.
- **Release days** come from Kalshi close times (08:25/08:29 ET on release day) and were cross-checked against ZN
  volume. The 08:00–09:00 bar's volume is a median 3.0× its prior-20-day norm. Three days were below 1.5×
  (Nov 10 2021, Mar 11 2026, Apr 10 2026), and all three match the BLS calendar.
- **Nowcast vintages.** We assume the Cleveland Fed chart shows each day's nowcast as it was published then. If
  any history was recomputed later, the model would look better than it was in real time, which works against
  the crowd. So it can't create the crowd's advantage.
- **Nov 2025.** BLS had no October index, so the November "m/m" that Kalshi settled (0.2) is unusual. Dropping both
  shutdown-affected releases barely changes anything.
- **Sample size.** 57 monthly observations. The forecast result is far beyond noise. The trade result is plain
  noise: the 2-hour P&L standard deviation is ~50 bp against costs of 3 bp, so the trade fails before costs, not
  because of them.

_Everything under "Spec choices" was written before `run.py` was first run (results.md last saved 04:51:38 ET; first
run log 04:53:36 ET on 2026-10-03). Before that, we had only checked coverage: which events and strikes exist,
close times, settlement fields. No forecast errors, regressions or ZN returns had been computed._

## Spec choices (written before running)

The pre-registration (`alpha_ideas/PREREGISTRATION.md`, Idea 5) is implemented as written. Where it was silent or
ambiguous, these are the choices, each with the reason:

1. **Which events.** Kalshi's API files both the legacy `CPI-*` events (2021–Oct 2024) and the newer `KXCPI-*`
   events under series ticker `KXCPI`; that is the "CPI then KXCPI" pair the prereg names. Every market's
   `rules_primary` reads "If the CPI increases by more than X% in <month>…" — headline CPI month-over-month, never
   year-over-year — and is checked in code. The separate `KXECONSTATCPI` product (late 2025 →) is not named in the
   prereg and is not used.
2. **Release day.** 2022+ markets close at 08:25/08:29 ET on the scheduled release day → that date. The 2021
   markets closed the evening before; their `expiration_time` date is the release day (matches the BLS calendar).
   Exception: September 2025 CPI was delayed by the 2025 shutdown from 10-15 to **2025-10-24** (markets closed on
   10-15, settled 10-24). November 2025 markets already had their close moved to the actual day (2025-12-18). Release
   days are sanity-checked in the run against ZN volume in the 08:00–09:00 ET bar.
3. **October 2025 is excluded.** BLS never published an October 2025 CPI (BLS API: "Data unavailable due to the
   2025 lapse in appropriations", cached in `raw/bls_CUSR0000SA0.json`). Kalshi still settled the event at 0.2, but
   that is not a BLS headline CPI m/m and there is no release day for the nowcast cut-off or the ZN trade.
4. **Events need a ladder.** June–September 2021 had a single strike each, so no median can be interpolated → excluded.
   Any event with fewer than 2 strikes that traded before the cut-off is excluded.
5. **"Last trade at or before 07:55 ET".** The newest trade with `created_time` ≤ 07:55 ET on release day, taken
   from the union of Kalshi's live and historical trade endpoints (Kalshi archives older trades, so one market's
   history can be split between them). When several fills share that exact timestamp (one order sweeping several
   price levels — the API does not order them reliably) the contract-weighted average of those fills is used.
   Where the market closed before 07:55 (2021 events; the delayed Sept-2025 release) the last trade before close is
   used ("or the latest available before that"). A strike with no trade before the cut-off is dropped.
6. **Monotone fix.** P(CPI > X) must not rise with X. Fixed with isotonic regression (pool-adjacent-violators,
   non-increasing, equal weights) on the strike-ordered last-trade prices.
7. **Strike scale (continuity correction).** The market "above X%" settles on the *single-decimal* published
   number, so "above 0.2" is Yes for 0.3, 0.4, … — i.e. for unrounded CPI ≥ 0.25. On the CPI scale (the scale of the
   nowcast and the actual) the effective threshold of the market labelled X is X + 0.05. The crowd median is
   therefore the interpolated crossing on the label scale **plus 0.05**. Without this, a crowd that is certain the
   print is 0.3 (P(>0.2)=1, P(>0.3)=0) would get median 0.25. Note: this is a constant shift, so the **primary slope
   and t-stat are identical either way**; it only affects sign(d) for the trade and the accuracy table. The
   uncorrected "label" median is reported as a sensitivity row.
8. **Median outside the ladder.** If P(>lowest strike) < 0.5 or P(>highest strike) ≥ 0.5 there is no interpolation
   point → the event is excluded and counted.
9. **Crowd mean (robustness).** Probability mass between neighbouring strikes is placed at the published-grid
   value(s) in that interval (for strikes 0.1 apart, mass in (X_k, X_k+1] sits at X_k+1); the lower tail mass
   1 − P(>X_1) at X_1 and the upper tail P(>X_K) at X_K + 0.1 (tails are truncated at the nearest grid value).
10. **Nowcast.** Series "CPI Inflation" (core robustness: "Core CPI Inflation"). Vintage labels "MM/DD" are read from
    each data point's tooltip; non-date category labels (vertical markers such as "PCE Jul", "CPI Jan") are skipped.
    The year of a vintage is the one that puts it within [first day of target month − 62 days, + 200 days]. The
    vintage used is the latest one with a value whose date is strictly before release day.
11. **Actual.** The market's `expiration_value` (strip "%", e.g. ".9%" → 0.9); all strikes of an event must agree,
    and the value is checked against every strike's Yes/No result. One core event (Aug 2026) has the text
    "Above 0.2%" in that field; its actual is inferred from the results (0.2 settled Yes, 0.3 settled No → 0.3).
    A voided core listing (`KXCPICORE-25DEC`, no settlement value; re-listed as `KXCPICORE-25DECT`) is skipped.
12. **Primary statistic.** OLS with intercept of (actual − nowcast) on d; classical OLS t-stat of the slope is the
    primary t (one observation per release, no overlap). White/HC1 t is reported alongside.
13. **Verdict mapping** (prereg pass bar): PASS = slope t ≥ 3 and mean net trade > 0; WORTH A SECOND LOOK =
    2 ≤ t < 3 and mean net trade > 0; FAIL otherwise.
14. **Trade.** ZN.v.0 hourly bars stamped at bar END; roll-safe hourly returns compounded over bars ending in
    (08:00, 10:00] ET on release day = close of the 10:00 bar vs close of the last bar ending ≤ 08:00. Position
    −sign(d) (d = 0 exactly → flat, no cost). Costs: ZN per side = 0.5 tick spread + 0.5 tick slippage + $1.50 at
    price 111, tick 1/64, $1000/pt (`gqh.data.futures_cost_bps`) = 1.54 bp per side, 3.09 bp per round trip.
15. **Placebo** (shared convention: same clock window on non-event days). (a) ZN 08:00→10:00 return statistics on
    every business day in the sample that is not a CPI release day; (b) placebo trade: each release's position
    −sign(d) applied to the same window on the 5 business days before that release (other CPI days excluded),
    averaged per release, t-stat across releases.
16. **Shutdown robustness** drops September 2025 (released 9 days late) and November 2025 (released 8 days late;
    BLS had no October index, so its "m/m" is unusual). October 2025 is already out (item 3).
17. **Core robustness.** Series `KXCPICORE` (legacy `CPICORE-*` from June 2022 → `KXCPICORE-*`), same pipeline,
    core nowcast, core settlement value; same ZN trade with −sign(d_core).

## Change log (after the first run)

- **No bug fixes and no parameter changes** after the first run. The primary, trade, placebo and robustness numbers
  are identical in both runs.
- Added after the first run: the "post-hoc diagnostics" block in `run.py`/`summary.json` (sub-period slopes,
  Spearman, always-long benchmark, ZN-on-surprise regressions). It is clearly labelled and not used for the verdict.
- Before the first run, during coverage checks: we fixed four things. A "02/29" vintage label in a non-leap year
  crashed the parser. Core rules have three wordings ("more than" / "above" / "is greater than"). One core ticker
  is `KXCPICORE-25DECT`. One core settlement value is text (spec choice 11).

## Files

- `fetch.py`: downloads and caches every raw input into `raw/`. Kalshi events/markets/trade snapshots, the Cleveland
  Fed JSON and the BLS check. Public GET endpoints only.
- `run.py`: the whole analysis (`uv run python alpha_ideas/kalshi_cpi/run.py`). It reads `raw/`, re-downloading
  nothing that is cached. ZN bars come from the existing Databento cache (no download triggered).
- `per_release.csv`: one row per headline release. Release date, crowd median/mean (plus the label-scale median),
  nowcast + vintage, actual, d, nowcast error, ZN 08:00→10:00 return, position, gross/net trade P&L,
  ladder diagnostics, and `used_in_primary`.
- `per_release_core.csv`: the same for core CPI.
- `summary.json`: every number quoted above.
