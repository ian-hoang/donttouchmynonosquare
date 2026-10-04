# Round 2 ideas (written 2026-10-03 ~01:50 ET, after V002-V004, before testing any of these)

**Context.**
- The single-tag scan (V002) found about what luck predicts.
- The same-day control (V003-V004) left one lead: deal signed → collar.
- These ideas use other angles: what the filing text says, whether the event resolves or creates
  uncertainty, the filing-day reaction, and the company's recent filing activity.

**Design, shared by all ideas.**
- Each idea is a **contrast between two groups of 8-Ks**.
- Each event is measured against **quiet same-day peers**: 6 top-100 companies per date with no 8-K
  of any kind within ±5 days. So the generic "news vs no news" effect cancels in the contrast.
- Settings:
  - 3-6m options, 5% OTM
  - entry at the close of the session after the filing date
  - in-sample 2024-2025 only
  - primary horizons 5, 10, 21 sessions (all nine reported)
  - t-stats clustered by company
- About 45 primary tests, so expect ~2 with |t| > 2 by luck alone.

**Disclosure.** Some single tags below were already in the V002 scan (no clear result there). The
groupings, text splits and conditioning variables are new.

## G · Uncertainty resolved vs created → which side of the volatility trade
- **RESOLVED (the risk is gone):** acquisition_completion, merger_completion, divestiture_completion,
  spinoff_completion, deal_termination, settlement_agreement, regulatory_decision.
- **CREATED (a new risk appears):** ceo_departure, cfo_departure, strategic_initiative,
  restructuring_plan, workforce_reduction, business_line_exit, regulatory_investigation,
  material_litigation, cybersecurity_incident, asset_impairment, goodwill_impairment.
- **Story:** option prices lean on the stock's recent history and adjust slowly. After the risk is
  resolved they still charge for it, so selling puts pays. After a new risk appears they still look
  calm, so buying puts pays.
- **Who's on the other side:** vol models anchored on trailing realized volatility, and hedgers
  holding protection they no longer need.
- **Prediction (5-21 sessions):**
  - The cash-secured put beats peers by more after RESOLVED than after CREATED.
  - The bought put (the protective put's option part) does better after CREATED.
  - |realized| ÷ implied is higher after CREATED.
- **Fails if:** there's no difference, or the difference comes from one sub-tag.

## I · Filing-day surprise keeps going ("8-K drift")
- **Rule:** for every company-day with a non-earnings 8-K, compute the surprise
  z = (stock move from t_pre to the entry close − peers' move) ÷ the event's own implied move over that
  window. If |z| > 1, follow the direction: long call after a positive surprise, protective put after
  a negative one.
- **Story:** investors under-react to non-earnings news (limited attention), so prices keep drifting.
- **Prediction:** signed drift (stock vs peers × sign(z)) is positive at 5-21 sessions.
- **Fails if:** it's zero, or it reverses (that would be the liquidity-provision story instead).

## J · Friday filings drift more
- **Rule:** idea I, split by filing weekday.
- **Story:** DellaVigna & Pollet (2009): Friday news gets less attention, a weaker first reaction and
  more drift afterwards.
- **Prediction:** signed drift is larger for Friday filings than for Monday-Thursday filings.

## K · A company in turmoil (many recent 8-Ks)
- **Rule:** intensity = distinct non-earnings 8-K filings by the company in the prior 60 days. The
  top quintile counts as "busy".
- **Story:** a run of filings marks an unstable period, and option prices lean on calm history.
- **Prediction:** after a busy company's 8-K, |realized| ÷ implied vs peers is higher than after a
  quiet company's, and the bought put does better.

## L · Sudden vs planned departures
- **Rule:** CEO, CFO and executive-officer departure filings, split by their text.
  - SUDDEN: "effective immediately", "terminated", "for cause", "mutual", "no longer serve", "cease
    serving", "good reason", with no "retire".
  - PLANNED: "retire" or "retirement".
- **Story:** sudden exits signal trouble (Warner, Watts & Wruck 1988; Denis & Denis 1995), while
  planned retirements are noise.
- **Prediction:** after SUDDEN, the stock lags peers and the bought put gains, relative to PLANNED.

## M · The deal lead's mechanism: stock vs cash deals
- **Rule:** deal-signed filings whose text mentions stock consideration ("exchange ratio", "shares of
  … common stock", "stock consideration") count as STOCK/MIXED. Filings that mention only cash count
  as CASH.
- **Story:** merger-arbitrage funds short the acquirer only when it pays in stock (Mitchell, Pulvino &
  Stafford 2004).
- **Prediction:** the drift (stock vs peers at 5-21) is concentrated in STOCK/MIXED deals.
- **Fails if:** cash deals drift just as much. Then it's something else, such as overpayment.

## N · Debt offerings: banks vs everyone else (idea B's own falsification test)
- **Rule:** debt_issuance / underwriting_agreement filings split by issuer.
  - Financials: AIG AXP BAC BK BLK BRK.B C COF GS JPM MET MS SCHW USB WFC.
  - Non-financials: everyone else.
- **Prediction (B):** the cash-secured put's edge vs peers is in non-financials.

## E2 · Fresh vs stale filings
- **Rule:** parse the first date written in the excerpt ("On May 16, 2025, …").
  - FRESH: filed within 1 business day of that date.
  - STALE: filed 2+ business days later. The news was already out, often by press release.
- **Story:** a stale 8-K repeats public news, so only fresh ones carry surprise.
- **Prediction:**
  - |z| is larger for FRESH filings.
  - Any drift from idea I is concentrated in FRESH filings.
  - For the deal lead, report fresh vs stale separately (many deal 8-Ks are follow-ups).

## H · Was it priced in? (descriptive, for the note)
- **Rule:** implied move on t_pre relative to the same company's typical implied move (the scan's
  pool days).
  - SCHEDULED filings: earnings, annual meetings and votes, dividends, investor presentations.
  - UNSCHEDULED: everything else.
- **Prediction:** implied move is elevated before scheduled filings and normal before unscheduled ones.

## Not now (bigger lifts)
- Widening the universe beyond the top 100 for rare risk events.
- 1-month options.
- EDGAR acceptance times.

## G-1m · Follow-up written 2026-10-03 ~02:05 ET, after seeing G with 3-6m options, before running this
- **What G showed with 3-6m options:**
  - |realized| ÷ implied was higher after CREATED than after RESOLVED at 1-5 sessions (t −2.3 at h=2,
    −2.0 at h=5).
  - Neither trade (cash-secured put, bought put) differed.
  - 3-6m options carry little of a one-week move.
- **Follow-up:** the same contrast with **1-month options** (the notebook's "1m" bucket, 21-45 days to
  expiry), same events, peers and entry.
- **Prediction:**
  - After CREATED, the 1m bought put beats peers by more than after RESOLVED at 2-10 sessions.
  - The 1m cash-secured put does the reverse.
- **Fails if:** there's no difference at 2-10 sessions.
- **Disclosure:** this is a second look at G, so it counts as an extra variant.
