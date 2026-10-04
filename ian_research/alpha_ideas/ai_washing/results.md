# AI-washing test: results

## Spec choices and ambiguities (written before the final run)

These fill gaps in `PREREGISTRATION.md`. They were fixed before any return was computed for this test.

**Data plumbing**
1. **Ticker → company mapping.** Massive's reference list only holds each company's latest ticker, so old tickers
   (FB, SQ, ANTM…) are recovered from Massive's ticker-change events. Those events are per *company*, not per share
   class: GOOGL's FIGI returns GOOG's history. So events are only used for a share class whose own ticker ends that
   history; other classes keep their own ticker. Ties are settled by three rules:
   - A ticker belongs to one listed company at a time.
   - An event-dated claim beats an open-ended one.
   - Otherwise the claim that ends first wins, because a delisted company held the ticker before any later re-use.
   - Anything still tied is dropped and counted in `build_universe.log`.
   - Before a company's first recorded event, two weak claims stand in: its first recorded ticker, and its own
     current ticker. The second is needed for Honeywell, whose history holds only a two-week "HONI" in 2026-06.
     Weak claims lose every conflict.
   - A company trades under one ticker per day: an event-dated claim first, then its own ticker, then the more
     traded one.
   - Mapping audit (`build_universe.log`): among the 1,500 most-traded tickers that look like common stock, only 2–6
     map to no company. Most are ADRs or Barrick, which don't file 8-Ks. The other two are delisted companies whose
     tickers were later re-used: CoreSite (COR, 2021) and Bed Bath & Beyond (BBBY).
   - Known gap: in 2026-07 Exxon moved to a new holding company (new CIK). XOM's prices stay attached to the new CIK,
     but its 2020–2026 earnings 8-Ks were filed under the old CIK. So XOM can be a peer but never an event.
2. **One share class per CIK:** the one with the largest total dollar volume, 2020–2026. Prices are stitched across
   ticker renames within that class.
3. **Dividends.** Massive files dividends under the company's current ticker, in pre-split units. Each cash dividend
   (types CD and SC, USD only) is divided by every later split ratio. It is matched to the company through its
   reference ticker, only inside the company's trading life. It lands on the first trading row on or after the
   ex-date.
4. **Gaps.** A daily return spanning ≤ 5 missing trading days is assigned to the day trading resumes. Longer gaps
   leave the return missing.

**Earnings releases**
5. **10-K filings:** form `10-K` only (not 10-K/A or 10-KT). "Before day 0" means filing date < day 0's date.
6. **Duplicate releases.** If a firm has two earnings releases with text on the same day 0, the longer one (more
   words) is kept. Window truncation uses every earnings 8-K of the firm, with or without press-release text,
   because an announcement happened either way.
7. **Baseline:** built only from releases with text, since an AI count needs text.
8. **R&D:** used only if the 10-K has both the current and prior fiscal-year values for the same concept;
   otherwise R&D = 0 in both years. Capex needs both years too.

**Abnormal returns**
9. **Unknown industry.** A firm with no SIC code never forms an "industry" group. Its benchmark goes straight to
   same-tercile peers.
10. **Announcement reaction** (robustness 9) = abnormal return on day 0 plus day +1, close-to-close.
11. **Months kept:** a month counts only if the washer portfolio held ≥ 10 events on average across its trading
    days. Days with nothing held count as 0 in that average.

**Robustness**
12. **Robustness 3:** uses all eligible events in the primary window. Day-0 quarter and SIC2 fixed effects; SIC2 = −1
    (unknown) is its own group there.
13. **Robustness 6:** factors are the Fama-French daily 3-factor file plus daily momentum, both cached through
    2026-08-31. The regression covers 2023-02-01 → 2026-08-31.

## Bug fixes to the AI count (found by a text-only audit; no return had been computed)

`features.log` prints random contexts for every token, plus every way a release defines "(AI)". The audit found
four kinds of words being counted as AI talk when they weren't:

| Problem | Example | Fix |
|---|---|---|
| "GPT" means *gathering, processing and transportation* in oil & gas | Chord Energy, ~15 per release in 21+ releases | `GPT` removed from the dictionary |
| "AI" defined as something else | Tyson "avian influenza (AI)" (24 releases), Advance Auto Parts "Autopart International (AI)" (9), "aromatase inhibitor (AI)" (3) | bare `AI` tokens not counted in a release that defines AI as anything but artificial intelligence (36 releases) |
| Encoded junk instead of text | Liberty Global 2020-07: random characters spelled "AI" 48 times | releases with < 5% stop words or > 1% `;@>=<^\`` symbols are treated as "no press-release text" (18 releases) |

The 498 other "(AI)" definitions all say artificial intelligence. A known limit remains: some firms added AI
language to their legal risk boilerplate ("our use of artificial intelligence (AI)…"). That counts as AI talk here.

## Results (single run, 2026-10-03; full output in `run_output.txt`)

### Plain-English summary
**Verdict: FAIL.** The idea was that companies hyping AI in earnings releases without spending more on it would
lag their peers afterwards. They didn't:
- **Washers** (AI talk jumps, spending doesn't): 247 events at 142 firms, 2023–2026. They beat same-industry,
  same-size peers by +0.20% a month (t = +0.43). That is the wrong direction, and statistically just noise.
  Shorting them would have lost about 0.4% a month after costs.
- **Washers minus investors**: the gap also points the wrong way, with washers beating investors by +1.3% a month
  (t = +1.95).
- **Event-level regression**: more AI mentions predict nothing (t = −0.13).
- **Why the spending filter misfires.** It flags companies that *sell* AI (Nvidia, Dell, HPE, Bloom Energy) as
  "washers": their last annual capex+R&D hadn't jumped, but their AI talk was about real sales. They are among the
  biggest washer winners. The biggest washer losers are C3.ai, Cognizant, Roblox, Lumen and Opendoor.

### Primary test
| | value |
|---|---|
| Washer events (firms) | 247 (142) |
| Months used (avg events held ≥ 10) | 30 of 44 (avg 20.7 held) |
| Mean monthly abnormal return | **+0.200%** (prediction < 0) |
| Newey-West t (3 lags) | **+0.43** |
| Short-washer trade, net of 0.23%/month costs | −0.43%/month (t −0.93) |

### Robustness (reported only)
| Variant | Events | Months | Mean AR %/month | t |
|---|---|---|---|---|
| 1 All AI jumps | 577 | 40 | +0.140 | +0.36 |
| 2 Investors (jump, growth ≥ 10%) | 298 | 35 | −0.267 | −0.42 |
| 2b Washers − investors (pred. < 0) | | 26 | +1.263 | +1.95 |
| 3 Event regression, CAR on ΔAI | 13,299 | | −0.021 per mention | −0.13 |
| 4 Strict dictionary | 216 | 25 | +0.642 | +1.18 |
| 5 Length-normalised jump | 165 | 22 | −0.274 | −0.52 |
| 6 FF3+momentum alpha | | 892 days | −0.204 | −0.36 |
| 7 One-month hold | 247 | 8 | +0.520 | +1.15 |
| 8 Excluding core tech | 110 | 9 | +1.497 | +2.41 (wrong sign) |
| 9 Announcement reaction, days 0..+1 | 247 vs 12,722 | | washers +0.80% vs others −0.10% | +1.11 |
| 10 Pre-ChatGPT placebo | 14 | | not tested (< 30 events) | |

### Checks
- **Hand check.** Nvidia, 2024-05-23 release, abnormal return recomputed by hand from raw prices and its 20 peers:
  +27.3045%, identical to the file. Nvidia was up 21.5% while its peers were down 4.4%.
- **Benchmarks are fair.** Ordinary (non-jump) releases average −0.09% against their peers.
- **Missing data is small.** Days with no own return (set to 0): 5,059 of about 1.1 million event-days.
- **Guards passed.** The no-look-ahead asserts all held: formation month-end before day 0, 10-K filed before
  day 0, holding starts at day +2.

### Not pre-registered (observations only)
"Investors" (AI talk plus ≥ 10% spending growth) drifted down against peers. They were −28% cumulative at the
2026-02 trough and −9% by 2026-09. On its own this is not significant (t −0.42), and it is the reverse of the
original story. It would need its own pre-registered test on new data.
