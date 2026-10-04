# Massive 8-K scan: findings so far (in-sample 2024-2025 only; out-of-sample untouched)

Status 2026-10-03 ~01:30 ET. Settings throughout: top-100 universe, 3-6 month options, 5% OTM, entry at
the close of the session **after** the filing date (no after-the-bell look-ahead), costs = 5% of each
option premium each way (the notebook's assumption) plus 1 bp each way for shares. Every run is in
`variants.csv` (V001-V004).

## 1 · "Profitable" mostly means "the market went up"
On ordinary days for the same companies, the strategies that own the stock made money net of costs
(e.g. covered call +3.6% to expiry, protective put +1.7%), because 2024-2025 was a bull market.
After 8-Ks the numbers are about the same. Absolute P&L says nothing about the filing.

## 2 · The broad scan finds about what luck predicts
37 categories (33 tags with ≥20 events + 4 combinations written down beforehand) × 5 strategies ×
9 horizons = **1,665 tests** against ordinary days (same ticker mix). 4.7% had |t| > 2; chance
alone gives 5%. A fake-tag benchmark (400 random-day "categories" per real one) puts 8 categories
at luck p ≤ 0.10 where ~3.7 are expected, but several are near-duplicates of each other.

## 3 · The top hit was our own negative control, and a calendar effect
Shareholder-vote results (`shareholder_proposal_outcome`, `annual_meeting_results`) were the
pre-registered negative control in `hypotheses/BRAINSTORM.md`. They topped the scan (cash-secured
put, +0.58% at 21 sessions, t 2.3). 70 of 121 filings fall in May. Against **other top-100
companies on the same dates**, the edge is gone (−0.06%, t −0.4). Lesson for the note: a
ticker-matched placebo is not enough; a date-matched control is needed.

## 4 · What survives the same-day control
**Deal signed (`acquisition_agreement` + `merger_agreement`; pre-registered idea F).** 46 events,
25 companies. Versus same-day peers, the acquirer's stock lags:

| sessions after entry | 5 | 10 | 21 |
|---|---|---|---|
| stock vs peers | −1.36% | −1.97% | −2.08% |
| t, clustered by company | −2.1 | −3.4 | −2.1 |
| collar's option part (bought put + sold call) vs peers | +0.85% | +1.58% | +1.41% |
| t, clustered by company | +2.7 | +4.0 | +2.0 |

- Same sign in 2024 (n=15) and 2025 (n=31). Both sub-tags show it.
- Leave-one-company-out mean at h=10: −1.73% to −2.18%. 68% of events are negative.
- None of the five strategies is profitable in absolute terms after a signing, because all five are
  long the stock. The finding is relative: holding through a signing, the collar loses ~1.6% less
  than the bare stock over 10 sessions.
- Candidate mechanism: merger-arbitrage short selling of the acquirer in stock deals
  (Mitchell, Pulvino & Stafford 2004, "Price Pressure around Mergers").
- Pre-registered F named the covered call; the data points to the collar. Disclose the switch.
- Caveats:
  - Repeated 8-Ks per deal (COF 7, CHTR 6), so the effective sample is ~25 deals.
  - Some tag noise: a CRM credit agreement is tagged as an acquisition agreement.
  - Not yet checked: other expiry buckets, OTM levels, filing-day timing, first-filing-per-deal.

**Debt offering → cash-secured put (pre-registered idea B).** 252 events.
- Versus same-day peers: +0.95% at expiry (t 2.9), +0.08% at 1 session (t 2.1), weak in between.
- Mostly 2025. 2024 is negative at 3-10 sessions.
- The shape contradicts B's written prediction (an edge at 1-21 sessions, fading by 63).

**Dropped:**
- Equity grants: sign flips between years, n=26.
- Executive departures: a −0.2% one-day effect, 2024 only.
- New leadership (A), settlements (C), buybacks (D): nothing against ordinary days.

## Next
1. Pick the final category × strategy. Write its hypothesis file before more tests.
2. Run sensitivity against same-day peers (bucket, OTM, timing, horizon), with one event per deal.
3. Freeze the rule, then run the 2026 out-of-sample window once.

## 5 · Round 2 (V005-V006): eight new angles, mostly honest nulls
Ideas and predictions were written down first in `hypotheses/BRAINSTORM2.md`. Each idea contrasts
two groups of 8-Ks, each measured against quiet same-day peers (no 8-K within ±5 days). About 50
primary tests (horizons 5/10/21): one reached |t| ≥ 2, where luck alone predicts ~2.5.

| idea | verdict | key number |
|---|---|---|
| G · uncertainty resolved vs created | **no trade.** The yardstick points the predicted way, but neither 3-6m nor 1m options capture it | after CREATED filings, \|realized\| ÷ implied exceeds RESOLVED by 0.34 at 2 sessions (t −2.3); trades all \|t\| < 1.1 |
| I · filing-day surprise drift | **no.** Top-100 prices absorb 8-K news within ~2 sessions | signed drift +0.18% at 5 sessions (t 1.0), then ~0 |
| J · Friday filings drift more | **no** | Friday vs Mon-Thu: \|t\| ≤ 1.4, wrong sign at 21 |
| K · company in turmoil | **no** (prediction fails). Unexpected opposite at long horizons, post hoc | bought put loses at 63 sessions (−1.17%, t −3.3) |
| L · sudden vs planned departures | **weak** | bought put +0.49% at 3 sessions (t 2.3), nothing at 5/10/21; only 33 sudden exits |
| M · stock vs cash deals (deal lead's mechanism) | **merger-arbitrage story not supported**: cash deals drift as much as stock deals | h=10: stock/mixed −1.51% vs cash −1.90% |
| N · debt offerings, banks vs others (B's own kill test) | **B fails**: the edge is in financials | non-financial minus financial CSP at 42 sessions −0.87% (t −2.4) |
| E2 · fresh vs stale filings | fresh filings carry bigger surprises, as predicted, but no drift. Deal lead: follow-up filings drift too | mean \|z\| 1.23 fresh vs 0.98 stale |
| H · was it priced in? | 3-6m implied vol is **not** elevated before scheduled filings; the headline bucket is too long-dated to see event premia | median ratio to the company's norm 1.006 scheduled vs 0.997 unscheduled |

What this changes:
- **The deal lead's mechanism.** The drift is still there against peers, but the merger-arbitrage
  explanation no longer fits: cash deals and follow-up filings show it too. The better candidate is
  large-acquirer underperformance (overpayment). Treat the mechanism as open in the note.
- **Idea B is closed.**
- **The search is now large:** V001-V006, ≈1,900 tests in all. The note must disclose this, and
  the deal lead's evidence should be read against it.

## 6 · Profit search with measured costs (V007-V008)
- **Costs from real quotes** (`research/costs.py`, 16,356 entry legs, all with a same-day quote).
  - Median half-spread: 1.6% of the option price (at the money) to 2.4% (5% out of the money).
  - The notebook assumes 5% each way, which overstates costs about 2-3×.
- **Profitable trades exist.** After any non-earnings 8-K, net of measured costs:
  - covered call held to expiry: **+4.30% per trade** (n=1,168, 73% winners, worst 5% ≤ −12.6%)
  - cash-secured put held to expiry: **+1.43%** (84% winners)
- **But the filing isn't why.** The same trades on quiet same-day peers make +3.76% and +1.29%.
  The profit is the option-selling premium plus a rising market in 2024-25.
- **The 8-K-specific "winners" were companies, not filings.** The written rules (V007) let 20 cells
  through; `business_update` and `charter_amendment` also passed the luck check. But:
  - `business_update` is mostly COF (24) and AXP (19) monthly card-metric filings. Removing those
    companies' usual edge vs peers takes the covered call at expiry from +1.79% to +0.02% (t 0.0).
  - Charter amendments, material charges and public offerings fall to t 0.2-1.3 the same way.
- **Only survivor:** equity grants → covered call / protective put at 3 sessions (+0.6-0.8%,
  t ≈ 2.0-2.1 after the company control). With ~2,000 cells searched, luck produces this about as
  often. It's the only candidate left for a single out-of-sample test.

## 7 · Round 3 (V009): a profit the filing causes
**S · selling into option-price spikes.**
- The spike is real and fades: straddle time value falls back vs peers at 2-10 sessions
  (t −2.3 to −3.0).
- Neither the cash-secured put nor the covered call earns from it (|t| ≤ 1.3), because stock moves
  swamp it. A finding for the pricing story, not a trade.

**F-overlay · deal signed → sell a call against shares you already hold.** Idea F's pairing; the
direction and the overlay reporting were both written before results. One filing per deal: 40 deals,
25 companies.

| 10 sessions after entry | sold call, net of measured costs |
|---|---|
| absolute P&L | **+0.64%** of the stock price (t 2.2; 67% winners; median +0.91%) |
| vs same-day peers | +0.96% (t 3.2) |
| vs peers and the company's usual | +0.63% (t 1.8). With all 45 filings: +0.59% (t 2.3) |
| 2024 / 2025 | +0.87% / +0.54% |
| leave one company out | +0.49% .. +0.76% |

- **Decay:** ~0 at 5 sessions, peak at 10, weaker at 21, noise after.
- **Costs:** call premium at entry is a median 4.8% of the stock price; measured round-trip cost is
  ~0.1-0.2%.
- **Caveats:**
  - It's a holder's trade. Buying the stock too gives about −0.2% at 10 sessions, because the stock
    drifts down about 0.8%.
  - The 10-session peak was seen in the data (V003/V004) and must be disclosed.
  - With ~2,000 tests in the search, t ≈ 2 after the company control is suggestive, not proof.
  - The 2026 window should have ~10-15 deals: enough to check the sign.

**Risk numbers for the deal-signed sold call** (`research/sharpe_deal.py`; in-sample; sold call held
10 sessions; measured costs; per $1 of stock; 30 deals with valid exit prices)

| | value |
|---|---|
| per trade | mean +0.64%, volatility 1.91%, 67% winners, worst −3.27%, best +5.23% |
| per-trade Sharpe | 0.33. About 15 deals a year → ≈ 1.3 annualized; 95% range ≈ −0.2 to 2.7 |
| daily strategy (equal weight across open deals, flat otherwise) | +7.1% a year, volatility 9.5%, **Sharpe 0.75**, max drawdown −7.1%, invested 45% of days |
| by year (daily strategy) | 2024 Sharpe 1.23 (+7.8%), 2025 Sharpe 0.57 (+6.9%) |
| same trade on quiet companies, same dates | −0.24% per trade, per-trade Sharpe −0.11 |
| S&P 500 ETF buy and hold, 2024-25 | +19.8% a year, Sharpe 1.21 before the ~4-5% cash rate |

Note: a first version filled stale option prices forward. That admitted 4 more trades, including a
+8.5% CHTR trade, and showed +0.87%. The notebook's rule (no stale exit prices) gives the figures above.

## 8 · Out-of-sample result (V010, run once at 02:15 ET; `research/oos/results.md`)
The rule in `hypotheses/FINAL_RULE.md` was frozen at 02:12 ET and fingerprinted in
`research/OOS_LOCK.json`, then run once on 2026-01-01..2026-08-31.
- **Before the one-shot run:** a rehearsal on 2024-25 (`research/oos_rehearsal.py`) reproduced the
  in-sample +0.64% exactly.
- **Deals:** 19 in the window (14 companies). 15 have valid prices at the 10-session exit.

| at 10 sessions | in-sample 2024-25 (30 trades) | **out-of-sample 2026 (15 trades)** |
|---|---|---|
| sold call, net of measured costs | +0.64% | **+0.75%** (t 1.3) |
| winners | 67% | 67% |
| per-trade Sharpe | 0.33 | 0.35 |
| vs quiet same-day peers | +0.96% (+1.55% with another peer draw) | **+1.19%** (t 2.3) |
| vs peers and the company's usual | +0.63% | +0.96% (t 1.9) |
| full covered call (stock + call) | about −0.2% | −0.97% |

- **Verdict: PASS** under the pre-set rule (both primary numbers positive).
- **Decay:** the sold call stays ahead of peers at every horizon through 63 sessions.
- **The drift itself:** the stock lagged again, so buying the stock to run the trade loses. It
  remains a holder's trade.
- **Caveat:** 15 trades confirm the sign, not significance.

**Erratum on times.** Times typed by hand into the hypothesis files ran 1-1.5 hours fast (for example
"~03:35" in FINAL_RULE.md; the file was saved at 02:12). The authoritative times are the machine
timestamps: file modification times and OOS_LOCK.json. They show every hypothesis file saved before
its test ran. `variants.csv` now uses machine times. FINAL_RULE.md is fingerprinted, so it is left
as frozen.

## 9 · Was it the drift or overpriced options? (`research/attribution.py`, `research/attribution/results.md`)
**Method.**
- Black-Scholes (r = 4%, no dividends, consistent with the parity spot). Each trade's sold-call
  price change is split into: the stock move, the change in the call's implied volatility, and 10
  sessions of time.
- Shapley values over all 6 orders of applying those changes, so the three parts add up exactly
  (residual 0.00%). Measured costs are a separate line.
- **Comparison group:** every quiet top-100 company on the same dates (2,499 trades in-sample, 1,110 in
  2026), not a random 6. With this full comparison the gap is +1.10% in-sample and +1.45% in 2026.
  The two 6-company draws (+0.96%, +1.55%) bracket it.
- **Status:** descriptive. The 2026 part explains trades from the one-time run; the rule is unchanged.

**Edge over quiet companies on the same dates** (per $1 of stock, 10 sessions; t clustered by company):

| | 2024-25 (30 trades) | 2026 (15 trades) |
|---|---|---|
| stock drifting down | **+0.84%** (t 3.7) | **+1.20%** (t 2.1) |
| options cheapening (implied volatility falling) | **+0.24%** (t 2.5) | **+0.24%** (t 3.6) |
| time decay | +0.05% (t 1.2) | 0.00% |
| trading costs | −0.03% | +0.02% |
| **total** | **+1.10%** (t 4.2) | **+1.45%** (t 2.5) |

- **Implied volatility.** Over the hold, the sold call's implied volatility fell 1.14 vol points more
  than for quiet companies in both periods (t −2.6 and −3.6). Acquirers' options were dearer going in
  (median 29-31% vs 25-30% for quiet companies).
- **What the trader pockets** (2024-25, +0.64%): +0.48% ordinary time decay that every call seller
  earns, +0.20% stock drift, +0.24% the volatility drop, −0.28% costs.
- **Answer to "was it priced in?"** No, in two ways.
  1. About three-quarters of the edge is the stock drifting down after the signing, which the market
     doesn't price.
  2. About one-quarter is the acquirer's options being too expensive after the deal and cheapening
     over the next two weeks. This part replicated in 2026 at exactly the same size.
