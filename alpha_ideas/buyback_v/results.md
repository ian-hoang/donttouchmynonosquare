# Idea 1 — Treasury buyback "reverse V": results

(Summary and results sections are filled in after the run; the "Spec choices" section below was written
before `run.py` computed any event or placebo return.)

Reproduce: `uv run python alpha_ideas/buyback_v/run.py` (reads only cached futures bars and the cached buyback JSON
in this folder; prints everything to `run_output.txt`; per-event rows in `events.csv`, placebo rows in `placebo.csv`).

## Verdict: FAIL

**Plain-English summary.** Since mid-2024 the U.S. Treasury has been buying back old bonds on a published schedule, so
we asked whether long-bond futures (ZB, UB) drift *up* in the day before a buyback of long bonds and *give it back* the
day after, the mirror image of the well-known auction "concession". Across 53 long-end buybacks (June 2024 to
September 2026), the "before minus after" move was 11.8 basis points (bp) bigger than on ordinary days. That is the
predicted direction, but these futures routinely move about 90 bp over the same windows, so 11.8 bp is easily noise
(t = 0.90; the pass bar is t ≥ 2). The trade (buy 1 contract before, sell 1 after) made about $134 per event before
costs and **about $3 per event after $131 of costs**, which is effectively zero. Verdict: **FAIL**. With only ~22
long-end events a year, an effect this size would take many more years of data to tell apart from luck, if it is
there at all.

## Primary test (long-end events: 10Y–20Y → ZB, 20Y–30Y → UB)

| | value |
|---|---|
| Events | 53 (27 UB, 26 ZB; the 2026-10-01 ZB event is after the data ends) |
| Mean (pre − post) on event days | +11.48 bp |
| Mean (pre − post) on placebo days (1,155 ZB/UB contract-days, buyback era) | −0.27 bp (UB −0.48, ZB −0.06) |
| **Statistic: event − placebo** | **+11.76 bp** |
| **t-stat (Driscoll–Kraay / Newey–West, 2 lags)** | **+0.90** (simple event-only t +0.92) |
| Share of events above the placebo mean / median abnormal | 60% / +15.2 bp |
| Per contract | UB +15.4 bp (t 0.76), ZB +8.0 bp (t 0.49) |
| By year (abnormal mean) | 2024 +26.9 bp (n=8), 2025 −4.3 bp (n=21), 2026 +20.8 bp (n=24) |

The standard deviation of a single event's (pre − post) is about 93 bp, so with 53 events the standard error of the
mean is about 13 bp. An 11.8 bp difference is less than one standard error.

## Trade: long 1 contract over the pre window, short 1 over the post window, every long-end event

Cost = 2 round trips = 4 sides × $32.75 = **$131 per event** (11.10 bp for ZB, 10.48 bp for UB at the spec prices).

| per event | mean | median | sd | t | hit rate |
|---|---|---|---|---|---|
| gross bp | +11.48 | +15.15 | 92.6 | +0.90 | 60% |
| net bp | +0.70 | +4.05 | 92.6 | +0.05 | 53% |
| gross $ per contract | +$133.84 | +$187.50 | $1,089 | +0.89 | 60% |
| **net $ per contract** | **+$2.84** | +$56.50 | $1,089 | +0.02 | 53% |

Annualised (21.9 events a year): **+$62 net per contract per year, Sharpe ≈ 0.01**. Total net over all 53 events:
+$151. For scale, the same trade on every non-event day averaged −0.27 bp gross.

## Robustness (reported only; none of these can rescue the primary)

| check | N | event − placebo | t |
|---|---|---|---|
| All buckets (ZT, ZF, ZN, ZB, UB) | 103 | +8.84 bp | +1.28 |
|   ZT events (1Mo–2Y, 2Y–3Y) | 19 | −1.89 bp | −0.54 |
|   ZF events (3Y–5Y) | 11 | −0.85 bp | −0.11 |
|   ZN events (5Y–7Y, 7Y–10Y) | 20 | +16.65 bp | +2.05 |
|   ZB events (10Y–20Y) | 26 | +7.99 bp | +0.49 |
|   UB events (20Y–30Y) | 27 | +15.39 bp | +0.76 |
| Long-end PRE leg only (predicted > 0) | 53 | +4.11 bp | +0.47 |
| Long-end POST leg only (predicted < 0) | 53 | −7.65 bp | −0.88 |
| All-bucket PRE leg (predicted > 0) | 103 | +3.08 bp | +0.67 |
| All-bucket POST leg (predicted < 0) | 103 | −5.77 bp | −1.24 |
| Long-end, dropping 6 events within 1 business day of a same-contract coupon auction | 47 | +14.41 bp | +1.01 |
| Long-end, abnormal scaled by accepted par / mean par | 53 | +5.18 bp | +0.43 |
| Long-end, regression of abnormal on accepted par ($bn) | 53 | slope −37.3 bp per $bn | −2.02 |

How to read these:
- Every leg points the predicted way (up before, down after), but none is close to significant.
- ZN (the 5–10 year buckets) reaches t = 2.05. It is one of five contract subgroups and was not the pre-registered
  test, so a t near 2 in one of five slices is about what luck alone produces. It does not rescue the verdict.
  It might be worth writing down as a fresh hypothesis to test on future events only.
- Scaling by buyback size goes the *wrong* way. Bigger accepted amounts go with smaller abnormal moves (slope t −2.0).
  Almost every long-end operation is exactly $2bn, so this slope rests on 5 or 6 odd-sized operations ($0.2bn, $0.79bn,
  and the $4–5bn ones in September 2026). Also, accepted par is only published after the operation, so this is a
  diagnostic, not something you could trade on.

Side note (not pre-registered): measured against a 2010-07 → 2024-04 placebo instead of the buyback-era placebo, the
statistic is +12.72 bp, t +1.00. The choice of placebo period does not matter.

## Sanity and look-ahead checks

- Example windows (printed in `run_output.txt`): for the 2024-06-05 UB event (operation 13:40–14:00 ET), the pre window
  uses 20 hourly bars from the bar ending Tue 06-04 17:00 to the bar ending Wed 06-05 13:00. The post window uses 24
  bars from the bar ending Wed 15:00→16:00 to the bar ending Thu 06-06 16:00. The CME 17:00–18:00 halt is the only gap.
- All 103 measured events have a bar exactly at every window endpoint. 105 of 2,917 placebo days do not (holiday early
  closes).
- No look-ahead. Operation dates, buckets and times come from Treasury's published schedule (tentative quarterly
  calendar, then a per-operation announcement). The pre window ends at the last full hour *before* the operation
  opens, and the post window starts at least an hour after it closes. Nothing uses the results. The one exception is
  the par-scaling diagnostic, flagged above.
- Data came from cache only: the run printed no "Downloading" line, and every yearly cache file was confirmed on disk
  before the run.

## Spec choices and ambiguities (written BEFORE running)

Written 2026-10-03 before the first run. The only data looked at beforehand: the buyback table's columns/row counts
(to see the bucket labels and operation times) and hourly-bar completeness (which hours exist, NaN counts). No
window return was computed before this section was written.

1. **Event set (literal filter).** `security_type == "Nominal Coupons"`, `operation_type == "Liquidity Support"`,
   `operation_date >= 2024-05-01`: 104 operations, 54 long-end (27 × 10Y–20Y → ZB, 27 × 20Y–30Y → UB).
   - 2024-07-17 3Y–5Y has `total_par_amt_accepted = "null"` (looks like it did not complete; the same bucket ran again
     on 2024-07-18). It matches the literal filter, so it stays in the all-bucket robustness; it is not long-end so it
     is not in the primary test. It is dropped only from the par-scaling check (no par).
   - Operations with 0 accepted (2024-07-24 7Y–10Y) are kept (filter does not mention accepted amount).
   - The futures cache ends 2026-10-01 00:00 UTC (= 2026-09-30 20:00 ET). The 2026-10-01 10Y–20Y operation therefore
     has no pre/post data and is dropped. Rule: any event or placebo window that ends after the last bar is dropped.
2. **Clock.** O and C are the `operation_start_time_est` / `operation_close_time_est` strings, read as New York wall
   clock. "Last full hour ≤ O" = O floored to the hour (13:40 → 13:00). "First full hour ≥ C + 1h" = (C + 1h) ceiled
   to the hour (14:00 → 15:00; 14:05 → 16:00; 11:00 → 12:00). Windows are left-open/right-closed on hourly bar END
   times, so the pre return runs from the 16:00 close of the previous business day to the 13:00 close on the operation
   day, and the post return runs from the 15:00 close on the day to the 16:00 close on the next business day.
   Window return = Π(1 + r) − 1 over the `<root>.v.0` `roll_safe_returns` of the bars ending in the window.
   Previous/next business day = `CustomBusinessDay(USFederalHolidayCalendar)`.
3. **Per-event statistic** y = (pre − post) × 10⁴ (bp of price).
4. **Placebo days.** For contract c: every business day d from 2024-05-01 to the last day whose post window is inside
   the data (2026-09-29) that is **not an event day for c**. Days that are event days for a different contract stay in
   c's placebo set ("all other business days for that contract"). Placebo windows use the modal operation clock
   (O = 13:40, C = 14:00: pre (16:00 d−1, 13:00 d], post (15:00 d, 16:00 d+1]). All 54 long-end events use exactly
   this clock. The placebo period is the buyback era (same span as the event filter), not 2010–2024, so event and
   placebo days share the same rate regime. As a side note (not pre-registered, cannot change the verdict), the
   same statistic against a 2010-07 → 2024-04 placebo is also printed.
5. **Combining ZB and UB.** abnormal_i = y_i − mean(placebo y of contract(i)). Primary statistic = mean of abnormal_i
   over long-end events. This is "event mean minus placebo mean" done per contract and weighted by event count.
6. **t-stat.** Placebo windows overlap (the post window of day d overlaps the pre window of day d+1) and ZB/UB windows
   on the same day are close to the same trade, so the standard error is Driscoll–Kraay style: every event and
   placebo observation's contribution (influence) to the statistic is summed by calendar date, and a Newey–West
   (Bartlett, 2 business-day lags) variance is taken over the daily sums. The simple event-only t
   (mean abnormal / (sd / √N)) is printed too. Prediction is one-sided: statistic > 0.
7. **Trade.** Long 1 contract over the pre window, short 1 contract over the post window, every long-end event.
   $ P&L of a leg = window return × (`.v.0` close at the leg's start) × $1,000/point. Costs: 2 round trips = 4 sides ×
   (1 tick × $1,000 × 1/32 + $1.50) = 4 × $32.75 = $131 per event (ZB and UB have the same tick). In bp: 4 × per-side
   bp at the pre-registered spec prices (ZB 118, UB 125). Annualised = mean net per event × events per year, where
   events per year = N / (2024-05-01 → 2026-09-30 in years).
8. **Robustness definitions** (reported only, cannot rescue the primary):
   - All buckets: same statistic on all events with the pre-registered bucket → contract map; events with a
     non-modal clock (2026-01-16 10:40–11:00, 2026-04-23 13:40–14:05) use their own clock, placebo uses the modal one.
   - Legs separately (long-end): pre − placebo pre (predicted > 0), post − placebo post (predicted < 0).
   - Auction proximity: drop long-end events with a nominal coupon auction (no TIPS/FRN; reopenings included) mapped
     to the same contract by `strategies/treasury_auction.py`'s `TERM_TO_CONTRACT` (20-Year → ZB, 30-Year → UB)
     whose `auction_date` is D−1, D or D+1 business days. Placebo set unchanged.
   - Par scaling: abnormal_i × par_i / mean(par) over the long-end events with non-null par. Caveat: accepted par is
     only published after the operation closes, so this is a diagnostic, not a tradable rule.

## Bug fixes after the first run

- None that changed any number. Cosmetic only: formatted the `date` column as a string before writing the CSVs, to
  silence a pandas warning. Re-running gave byte-identical `run_output.txt`, `events.csv` and `placebo.csv`.
