# Round 3 pre-registration: commodity curve composite (#3) and month-end FX fix (#4)

Written 2026-10-03, about 15:45 ET, **before any of the data below was downloaded.** The file's mtime is the authority
on timing. The ideas come from `IDEA_LIST_DATABENTO.md` (#3 and #4). Ian approved running both ("go ahead, backtest #3
and #4"). Rules follow `PREREGISTRATION_ROUND2.md`:
- each test has one primary statistic that decides the verdict;
- robustness checks are reported but cannot rescue a failed primary;
- nothing changes after results are seen;
- any implementation choice goes in that test's `results.md` before the single run.

This adds **2 primary tests** to the repo's disclosed count, making 15 for 2026-10-03.

**Pass bar (same as round 2).** These labels decide the verdict:
- **PASS** = the primary statistic is in the predicted direction with t ≥ 2.0, **and** mean net P&L > 0 at base costs
  **and** at doubled costs.
- **WEAK PASS (cost-fragile)** = the same, except net P&L is ≤ 0 at doubled costs.
- **FAIL** = anything else.
- t ≥ 3 is what "convincing" means here.

The hackathon OOS window is the last 2 years (from 2024-10-01). It is reported separately for both tests.

---

## Test 3: commodity curve composite (relative basis + basis-momentum + skewness)  (`alpha_ideas/curve_composite/`)

**Hypothesis.** Commodities whose futures curve is unusually steep at the front relative to further out (high
*relative basis*: Gu, Kang, Lou & Tang, FMG DP942, data 1979–2019), whose front contract has outperformed its next
contract (high *basis-momentum*: Boons & Prado 2019) and whose returns are not lottery-like (low *skewness*:
Fernandez-Perez et al. 2018) earn higher returns the following month.

- **Data.**
  - GLBX.MDP3 `ohlcv-1d`, `ROOT.c.0`–`ROOT.c.3` (calendar-ranked), from 2010-06-06 to 2026-10-01. The quote was
    $3.00; abort above $4.00.
  - Contract names (e.g. "ZCZ6") come from free parent symbology (`gqh.data.instrument_symbols`), which gives each
    contract's delivery month and year.
  - Daily price = the bar's close (last trade of the UTC day).
- **Universe (18 roots):** CL HO RB NG GC SI HG PL PA ZC ZW KE ZS ZM ZL LE GF HE.
- **Approximate expiry by root** (for time scaling and eligibility):
  - CL: day 20 of the month before delivery.
  - HO, RB: last day of the month before delivery.
  - NG: day 27 of the month before delivery.
  - GC, SI, HG, PL, PA: day 27 of the delivery month.
  - Grains (ZC ZW KE ZS ZM ZL): day 14 of the delivery month.
  - LE: last day of the delivery month.
  - HE: day 14 of the delivery month.
  - GF: day 25 of the delivery month.
- **Eligible to hold during month h:**
  - Physically delivered roots whose delivery notices start before expiry (grains, GC SI HG PL PA, LE): delivery
    month ≥ h + 2. That avoids the first notice day.
  - All other roots: approximate expiry later than 5 days after the end of month h.
  - The *nearby ladder* for month h is the eligible contracts in expiry order, with a price no more than 5 calendar
    days old: N1, N2, N3.
- **Timing (one-day lag).**
  - M_t = the last day of month t on which at least 12 roots have a `c.0` bar.
  - D_t = the trading day before M_t.
  - Signals use prices up to D_t. Positions are entered at the M_t close and exited at the M_{t+1} close, in the N1
    contract that is eligible for month t+1.
- **Signals at D_t:**
  - Relative basis: RB = [ln F(N1) − ln F(N2)]/(τ2 − τ1) − [ln F(N2) − ln F(N3)]/(τ3 − τ2), with τ in years to
    approximate expiry.
  - Basis-momentum: BM = cumulative 12-month return of the N1 chain minus that of the N2 chain. Each chain holds
    that month's N1 (or N2) from one M close to the next; the last month runs from M_{t−1} to D_t.
  - Skew: sample skewness of the N1 chain's daily log returns over the last 252 trading days to D_t, within the same
    contract only; at least 200 returns required.
- **Composite and portfolio.**
  - Composite = (z_RB + z_BM − z_Skew)/3, using cross-sectional z-scores across roots with all three signals.
  - At least 10 roots are needed, otherwise that month has no position.
  - **Long the top 4, short the bottom 4.** Weights are inverse volatility (63-day daily volatility of the N1 chain),
    normalized so each leg sums to 1.
  - Monthly return = Σ_long w·r − Σ_short w·r, where r is each root's N1 return from the M_t close to the M_{t+1}
    close (the same contract).
- **Costs.**
  - Per side: 1 tick + $2.50 per contract, as a fraction of notional.
  - Ticks: CL .01, HO .0001, RB .0001, NG .001, GC .10, SI .005, HG .0005, PL .10, PA .05, ZC/ZW/KE/ZS .25,
    ZM .10, ZL .01, LE/GF/HE .025.
  - Contract point values ($ per price unit): CL 1,000; HO/RB 42,000; NG 10,000; GC 100; SI 5,000; HG 25,000;
    PL 50; PA 100; ZC/ZW/KE/ZS 50; ZM 100; ZL 600; LE 400; GF 500; HE 400.
  - Turnover is |Δw| in the same contract, or |w_old| + |w_new| when the contract changes (a roll).
  - "Doubled costs" multiplies these by 2.
- **PRIMARY:** mean monthly **gross** composite long–short return over all holding months, with a Newey-West
  (3 lags) t-stat. Prediction: > 0.
- **Robustness (reported only):**
  - each signal alone (RB, BM, −Skew), built the same way;
  - RB alone in 2020–2026, which is fresh out-of-sample for its paper;
  - an RB tercile sort, equal-weighted, as in the paper;
  - in-sample vs OOS;
  - each calendar year;
  - excluding livestock;
  - a long-only equal-weight benchmark of all roots.

---

## Test 4: month-end FX fix signed by the month's US equity move  (`alpha_ideas/fx_fix/`)

**Hypothesis** (Melvin & Prins 2015). When US stocks rise over a month, foreign investors who hedge their US equity
holdings become under-hedged. At the month-end WM/R 4pm London fix they sell dollars to rebalance, so foreign
currencies rise into the fix and give it back afterwards. When US stocks fall, the reverse.

- **Data.**
  - GLBX.MDP3 `ohlcv-1h`, `6E.v.0, 6B.v.0, 6A.v.0, 6C.v.0, 6S.v.0`, from 2010-06-06 to 2026-10-01. The quote was
    $4.77; abort above $6.00.
  - Plus cached `6J.v.0` (round 2) and cached `ES.v.0/ES.v.1` hourly bars (t1_shift).
- **Event day L.** The last London business day of each month (weekdays that are not England & Wales bank holidays,
  per python `holidays` UK subdivision ENG). Months run 2010-07 to 2026-09.
- **Signal.** ES month-to-date log return.
  - It is the sum of roll-safe daily returns between 16:00 ET closes, from the last ES close of the previous month
    to the last ES close dated before L.
  - A 16:00 ET close is the CLOSE of the bar starting 15:00 ET. Roll-safe means the previous close comes from the
    same `instrument_id`, looked up across v.0 and v.1.
  - s = sign(MTD) if |MTD| > 1%, otherwise no trade that month.
- **Windows** (London time, converted to UTC per day):
  - Pre-fix: OPEN → CLOSE of the bar starting 15:00 London.
  - Post-fix: OPEN → CLOSE of the bar starting 16:00 London.
  - Returns are log returns of USD-per-foreign-unit futures, so long a contract = long that currency.
  - **Basket** = equal-weight average over the six majors (6E 6J 6B 6A 6C 6S) with a valid window; at least 4 are
    needed.
  - The six majors are used instead of the GBP/AUD/CHF/NZD set in the idea list. That set came from a blog's
    in-sample results; the mechanism applies to all majors. GBP/AUD/CHF is reported as robustness.
- **Per-event statistic.** G = s × (r_pre − r_post), the basket in bp.
- **PRIMARY:**
  - Statistic: mean of G over events, with a plain t-stat (monthly events don't overlap; Newey-West(3) also shown).
  - Prediction: > 0.
- **Trade.** Hold s × basket over the pre-fix hour and −s × basket over the post-fix hour.
  - Net = G − cost_pre − cost_post, where each cost is the basket's average round-trip cost.
  - Round-trip cost per currency = (tick + $5/contract size) / price.
  - Tick per root and year: the smaller candidate if any price that year sits on an odd multiple of it, otherwise
    the larger. Candidates: 6E/6B/6A/6C/6S 0.00005 or 0.0001; 6J 0.0000005 or 0.000001.
  - Contract sizes: 6E 125,000; 6J 12.5M; 6B 62,500; 6A 100,000; 6C 100,000; 6S 125,000.
- **Robustness (reported only):**
  - the pre-fix leg alone (s·r_pre, predicted > 0) and the post-fix leg alone (s·r_post, predicted < 0);
  - each currency;
  - the GBP/AUD/CHF basket;
  - a continuous regression of basket r_pre on MTD over all months;
  - thresholds of 0% and 2%;
  - a placebo on the second-to-last London business day;
  - sub-periods 2010-07→2015-02 (the old 1-minute fix window), 2015-03→2020-12 and 2021→2026;
  - in-sample vs OOS (events from 2024-10);
  - quarter-end months only.
