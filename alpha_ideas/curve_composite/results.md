# Test 3 — Commodity curve composite (relative basis + basis-momentum + skewness): results

Pre-registered in `alpha_ideas/PREREGISTRATION_ROUND3.md`. Code: `run.py`.

## Spec choices made during implementation (written before the single run; no portfolio return had been computed)
1. **Timing of the pre-registration.**
   - The file's text says "about 15:45 ET", but that hand-typed time is wrong. The file's mtime,
     **2026-10-03 16:42:35 ET**, is the authority.
   - The data download started right after that time, in the same command that printed the mtime.
   - Data cost: $3.00 for `c.0`–`c.3` daily bars on 18 roots.
2. **Contract names** come from free parent symbology (`gqh.data.instrument_symbols`) starting 2010-06-06. The first
   attempt used 2010-06-01, which the API rejects because it is before the dataset starts.
   - Only outright names (ROOT + month code + year digit or digits) are used.
   - A one-digit year is read as the first year, on or after the contract's first appearance in our data, that ends
     in that digit.
3. **Daily price** = the `ohlcv-1d` close (last trade of the UTC day).
   - For energy and metals, that close falls 1–2 hours into the next CME session. This is the same for every
     contract of a root, so spreads and returns within a root are consistent.
4. **Ladders and holding.**
   - A contract is in the ladder at D_t only if it has a close within 5 calendar days and is eligible for month t+1.
   - The held contract is the N1 of that ladder.
   - The entry price is its close at M_t (at most 5 days old) and the exit price its close at M_{t+1} (at most 10 days
     old). With no exit price, the return is set to 0 and counted.
5. **Basis-momentum.** Uses the contracts the rule would actually have chosen at each past D_j: 11 full months plus
   the partial current month to D_t. All 12 months must be valid.
   - A look-ahead in the first draft (the last month read M_{t+1}) was found and fixed before any run.
6. **Skew and volatility.** Computed from the N1 chain's daily log returns between consecutive available closes of
   the same contract: each month's N1 from M_j to M_{j+1}, and the current month to D_t.
7. **Cross-section.**
   - z-scores use the sample standard deviation across roots that have all three signals, a volatility and an entry
     price.
   - Months with fewer than 10 such roots have no position. The position history then resets, so the next month pays
     full opening costs.
8. **Roll cost.** Closing the old contract is charged at the cost fraction of the new contract's entry price: same
   root, nearly the same price.
9. **Reporting.** Sharpe = monthly mean ÷ standard deviation × √12. The RB tercile robustness check is equal-weighted
   with ⌊n/3⌋ roots per leg. OOS = holding months that end on or after 2024-10-01.
10. **Extra contract months bought before the run** (`c.4`–`c.5`, $1.49, so the test's data total is $4.49).
    - A plumbing check on the cached roots found that with `c.0`–`c.3` alone, HO, RB, GC, SI and HG *never* had three
      contracts eligible to hold. For HO and RB, the front contract always expires at month-end. For metals, the
      nearest ranks are thin serial months.
    - Relative basis would therefore have been impossible to compute for 7 of the 18 roots, silently dropping them.
    - The pre-registered signal is defined on the first three *eligible* contracts, so more ranks are needed to
      compute it as written. No return had been computed.
11. **Contracts are keyed by (root, instrument_id).**
    - The same check found that Databento reuses instrument ids across products over time. For example, id 497 was
      GCV6 in 2016 and belonged to another product in 2020.
    - Keying by id alone would have mixed up two products' metadata.
12. **Name-consistency filter.** A contract is dropped, and counted, if it traded more than 7 days after its name-based
    expiry, or if its last day as `c.0` is more than 20 days from that expiry (for contracts that reached `c.0`
    before 2026-09).
13. **KE (Kansas City wheat).** `KE.FUT` only resolves on GLBX from 2013, after CME absorbed the Kansas City exchange.
    KE names are taken from 2013 on; any earlier KE contract without a name is dropped.

## Results (single run, 2026-10-03 ~17:25 ET; full output in `run_output.txt`)

### Plain-English summary
**Verdict: FAIL.** The composite made money on paper, but far too noisily to tell it apart from luck.
- **Composite (long the top 4, short the bottom 4 commodities each month).**
  - Before costs: **+0.65% per month (t = 1.48 Newey-West, 1.50 plain)**, an annualized Sharpe of 0.39.
  - After costs (about 0.08% a month): +0.57% per month (t = 1.31). With costs doubled: +0.49% (t = 1.13).
  - The pre-registered bar needs t ≥ 2, so the result could easily be luck.
- **Very bumpy.** Calendar-year returns ranged from −40.8% (2018) to +41.8% (2022). Volatility is about 20% a year,
  so a 0.65%-a-month edge would need decades to show up reliably.
- **The "fresh" signal did not replicate.**
  - Relative basis alone (Gu, Kang, Lou & Tang reported +0.81% a month, t = 3.99, over 1979–2019) earned
    **+0.17% a month (t = 0.43)** on 2011–2026 CME data.
  - In 2020–2026, which is fresh out-of-sample for that paper, it earned +0.34% (top/bottom 4) and +0.40%
    (equal-weighted terciles, as in the paper), both with t < 0.7.
- **The older signals were positive but not significant.**
  - Basis-momentum: +0.68% a month (t = 1.77).
  - Low-skew: +0.67% a month (t = 1.51).
  - The three signals are only weakly correlated (0.10–0.28), which is why combining them helped a little.
- **Recent period.**
  - 2020–2026: +1.06% a month (t = 1.44), vs +0.32% (t = 0.63) in 2011–2019.
  - Hackathon OOS (Oct 2024–Sep 2026, 24 months): +1.28% a month (t = 1.08).
- **Not a rescue.** The composite without livestock reached t = 2.22, but it is a reported-only robustness check and
  was not the pre-registered test.

### Primary and trade (183 holding months, 2011-07 → 2026-09)
| | Mean %/month | t (plain) | t (Newey-West 3) | Hit rate | Sharpe |
|---|---|---|---|---|---|
| **Gross** | **+0.647** | 1.50 | **1.48** | 0.56 | 0.39 |
| Net, base costs | +0.566 | 1.31 | 1.29 | 0.55 | 0.34 |
| Net, 2× costs | +0.485 | 1.13 | 1.11 | 0.55 | 0.29 |

### By sample (composite)
| Sample | Gross %/month | t | Net %/month | t |
|---|---|---|---|---|
| In-sample (to 2024-09) | +0.55 | 1.19 | +0.47 | 1.01 |
| OOS (2024-10 → 2026-09) | +1.28 | 1.08 | +1.20 | 1.02 |
| 2011–2019 | +0.32 | 0.63 | +0.24 | 0.47 |
| 2020–2026 | +1.06 | 1.44 | +0.98 | 1.33 |

Calendar years, gross:

| 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 (9 mo) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| +4.1% (6 mo) | −7.0% | −2.4% | −23.7% | +36.9% | +9.1% | +33.1% | −40.8% | +23.3% | +10.6% | +19.5% | +41.8% | −11.7% | +4.4% | +8.4% | +12.9% |

### Robustness (reported only)
| Portfolio | Gross %/month | t | Net %/month |
|---|---|---|---|
| Relative basis alone (top/bottom 4) | +0.17 | 0.43 | +0.09 |
| Relative basis, equal-weighted terciles (paper-style) | +0.11 | 0.29 | +0.02 |
| Relative basis 2020–2026, top/bottom 4 | +0.34 | 0.59 | — |
| Relative basis 2020–2026, terciles | +0.40 | 0.67 | — |
| Basis-momentum alone | +0.68 | 1.77 | +0.60 |
| Low skew alone | +0.67 | 1.51 | +0.60 |
| Composite without livestock | +1.02 | 2.22 (Newey-West 2.36) | +0.94 |
| Long-only, all roots equal-weighted | +0.26 | 0.91 | — |

### Notes
- Average roots per month: relative basis 16.7, basis-momentum 17.0, skew 17.8. Every month had at least 14 roots
  with all signals.
- No exit lacked a price.
- 29 contracts had no outright name, and 47 were dropped by the name-consistency filter, mostly platinum.
- This adds **1 primary test** to the repo's disclosed count.
