# Idea 7 — World Cup "sadness trade": country ETFs after knockout losses

Written 2026-10-03, **before any ETF return around a match was looked at** (file mtime is the authority). One
primary test decides the verdict. Robustness items are reported but cannot rescue it. No parameter changes after
results are seen. If an ambiguity forces a choice, it goes into `results.md` with the reason before the final run.
Bug fixes are allowed and logged.

## Hypothesis (Edmans, García & Norli 2007, Journal of Finance)
When a national team loses a World Cup knockout match, that country's investors are in a bad mood. Its stock
market does worse than the world market on the next trading session. The paper's sample ended in 2004, so every
tournament here (2006–2026) is out of sample for them. 2026 is reported on its own as the freshest test.

## Data
- **Matches:** openfootball `worldcup.json` for 2006, 2010, 2014, 2018, 2022 and 2026 (rounds, dates, kickoff
  times, full-time, extra-time and penalty scores). Cross-checked match by match against martj42
  `international_results` (results.csv + shootouts.csv). Any disagreement is resolved by hand and logged before
  returns are computed.
- **Prices:** Massive daily aggregates (split-adjusted open/close) per ETF, plus Massive cash dividends adjusted for
  later splits → total returns. Each ETF is used only from its launch date (EDEN from 2012-01-25, KSA from
  2015-09-16; those tickers belonged to other securities before). Colombia: GXG until 2025-06-20, then COLO.
- **Country → ETF:**
  - Europe: Germany EWG, England EWU, France EWQ, Spain EWP, Italy EWI, Netherlands EWN, Belgium EWK,
    Switzerland EWL, Sweden EWD, Austria EWO, Denmark EDEN, Norway NORW, Poland EPOL, Portugal PGAL, Greece GREK,
    Turkey TUR, Russia RSX, Ireland EIRL.
  - Americas: USA SPY, Canada EWC, Mexico EWW, Brazil EWZ, Argentina ARGT, Chile ECH, Colombia GXG/COLO, Peru EPU.
  - Asia-Pacific & Middle East: Japan EWJ, South Korea EWY, Australia EWA, Saudi Arabia KSA, Qatar QAT,
    New Zealand ENZL.
  - Africa: South Africa EZA, Egypt EGPT, Nigeria NGE.
  - Wales, Scotland and other teams without their own ETF are excluded.
  - A team is used in a tournament only if its ETF has ≥ 150 trading days of data before the tournament's first match.

## Timing (no look-ahead)
- **Match end** = kickoff (local time and UTC offset; 2010 = UTC+2, 2022 = UTC+3 where the offset is missing; 2006
  has no times, so the 21:00 CEST slot is assumed — with 2006 venues the event day is the next session either way)
  + 115 min, + 35 min more with extra time, + 15 min more with a penalty shootout.
- **Event day D** = the first home-market session that opens after the match ends. Each country uses its own
  exchange's local open time and time zone. Weekdays are Mon–Fri, or Sun–Thu for Saudi Arabia, Qatar and Egypt;
  home holidays are ignored.
- The ETF's close-to-close return on U.S. date D covers that home session. If D is not a U.S. trading day, the next
  U.S. trading day is used.

## Abnormal return
- AR = r_i,D − (α_i + β_i · r_basket,D).
- The basket is the equal-weighted total return of all other country ETFs above that trade that day.
- α_i and β_i come from OLS on U.S. trading days −270 … −21 relative to the tournament's first match (≥ 150 days).

## Primary test
- **Events:** knockout-stage losses (round of 32/16, quarter-final, semi-final, third-place match, final). The
  loser is decided after extra time, or by the penalty shootout. Tournaments 2006–2026, mapped teams only.
- **Statistic:** mean event-day AR. t-stat with standard errors clustered by U.S. event date.
  **Prediction: < 0.**
- **PASS:** t ≤ −2.0 **and** the tradable version below is still negative for the country net of costs (i.e. a
  short makes money). t ≤ −3 = convincing. Fewer than 30 events = INCONCLUSIVE.

## Tradable version (reported, part of PASS)
- Short the country ETF and long the basket (scaled by β_i) from the first U.S. price after the match ends to the
  close of D. That price is the 16:00 close if the match ends by 15:50 ET on a U.S. trading day, else the next
  09:30 open.
- Costs per side: 10 bps for ETFs with ≥ $5M median daily dollar volume in the estimation window, 30 bps otherwise;
  5 bps for the basket.

## Robustness (reported only)
1. Group-stage losses (90-minute losses).
2. Wins, knockout and group (the paper found no win effect, so prediction ≈ 0).
3. Two-day window (D and the next U.S. trading day).
4. Market-adjusted AR (β = 1, α = 0).
5. "Soccer nations" only (the paper's list, mapped: Argentina, Brazil, England, France, Germany, Italy,
   Netherlands, Portugal, Spain).
6. 2026 alone.
7. Excluding illiquid ETFs (median dollar volume < $5M).
