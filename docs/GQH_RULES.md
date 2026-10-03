# Gator Quant Hacks 2026: rules we are optimizing for

Extracted 2026-10-02 ~23:00 ET from gqhacks.com/tracks/systematic-trading, /tracks/systematic-trading/massive,
gqhacks.notion.site/hacker-guide, and gqhacks.devpost.com. If anything conflicts, the official brief or an
organizer announcement wins.

## Deadlines (Eastern)
- Hacking began Fri Oct 2, 7:15 PM. **Pre-existing work not allowed**: everything is built during the event.
- **Devpost submission: Sun Oct 4, 10:00 AM** (quant note PDF + public GitHub link). Late = not judged.
- **Final code push: Sun Oct 4, 11:00 AM.** Commits after that are not reviewed.
- Judging/expo 1:00–3:00 PM Sun (Matthews Suite); closing 3:35 PM.

## Track 03: Systematic Trading (sponsored by Webull)
Deliverables: **quant note (PDF, ≤5 pages incl. figures/tables, 11pt+, standard margins; references +
optional appendix don't count)** + **public GitHub repo**. Both are required.

### Rubric: 5 criteria × 10 = 50
1. **Economic Foundation**: strength of the economic hypothesis; why it should perform.
2. **Innovation**: creativity and distinctiveness.
3. **Risk Management Plan**: comprehensiveness and effectiveness of risk controls (limits per name/sector,
   gross/net exposure, pre-set de-risking rules, factor exposure regression, tail/regime behavior).
4. **Liquidity & Capital**: liquidity and capital deployment (size as fraction of ADV, $ capacity via
   square-root impact, results when costs double).
5. **Performance & Analytical Evidence**: use of data/evidence to demonstrate potential.
   - **CAP RULE: capped at 4/10** if judges can't run the code, if it gives materially different numbers
     than the note, or if they find lookahead or tuning on the out-of-sample period.
- **Ties broken by Performance & Evidence first, then Economic Foundation.**
- No P&L leaderboard. "A Sharpe of 0.6 you can defend beats a 4 you can't explain." Sharpe > 3 on daily = bug.

### What judges want
1. Hypothesis up front, written before results. **Commit the hypothesis to the repo before the first
   backtest** (the commit timestamp is the evidence).
2. Fair test: realistic costs; out-of-sample never tuned on.
3. The failures too: what didn't work and **how many variants were tried in total**.
4. Code that runs: a judge can run it and get the same headline numbers.

### Hypothesis framing they suggest
"Who's on the other side?" Edge sources: risk premium / behavioral bias / structural constraint /
liquidity provision. Template: We expect [universe] to [behavior] over [horizon] because [other side], and
the edge persists because [why]. If true we should see [testable prediction]; it fails if [kill condition].

### Data rules
- Sponsor data optional (Databento, Webull OpenAPI). Free public sources allowed (FRED, Ken French).
  **Cite every source in the note.**
- Any liquid publicly traded market.
- **Out-of-sample: most recent 20% of history or most recent 2 years, whichever is shorter.** Evaluate once.
- Handle and explain: survivorship, corporate actions (adjusted data), missing data (never fill with future).

### Rules
- Every reported result **net of transaction costs**; state bps per trade and justify. Show **costs ×2**.
- Open-source libraries and published research allowed, cited. Copying a strategy is allowed only if
  clearly extended and the extension is stated.
- AI tools allowed; every team member must be able to explain everything.
- Lag every signal (no same-bar signal and fill).
- Report at minimum, **IS and OOS separately**: annualized return, volatility, Sharpe, max drawdown,
  turnover, equity curve.
- Pitfalls they check: p-hacking, overfitting (many params / ML on short history), lookahead,
  survivorship, ignoring costs, test-set leakage, misleading Sharpe (short data, overlapping returns),
  regime dependence (one good year), unrealistic capacity. Deflated Sharpe Ratio is explicitly referenced.
  Show parameter plateaus (neighbor values work too). Regress on market/momentum/value factors.

### Suggested note blueprint (5 pages)
Summary 0.25 · Economic hypothesis 0.5 · Data & universe 0.5 · Methodology 1.0 · Results 1.25 ·
Risk management 0.5 · Liquidity & capacity 0.5 · Limitations & next steps 0.5 · References (free) ·
Appendix (free, optional, judges may skip).

### Repo requirements
README with setup + **one command** reproducing headline results; requirements.txt; all signal/backtest/
analysis code; data download scripts. **Never commit raw licensed data or API keys** (.env.example only).
Example layout: data/download.py, src/{signals,backtest,analysis}.py, run_all.py.

### Submission checklist (from site)
PDF ≤5pp · hypothesis before results · IS/OOS separate net of costs · Sharpe/MDD/turnover/equity curve ·
risk + liquidity/capacity sections · number of variants disclosed · public repo w/ README + deps ·
one command reproduces headline · no keys/licensed data · all team members listed on Devpost.

## Massive bonus (sub-track; optional)
"Trade the 8-K": Massive 8-K disclosure categories as the signal, options as the instrument (long call,
covered call, protective put, collar, cash-secured put). Fixed horizons [1,2,3,5,10,21,42,63] + expiry,
top-100 US cos, sealed judge window. $500 + 1 month Massive data. Key via #massive on Discord. Different
thesis from ours, so we do NOT target it (would dilute the note). Massive 8-K data could still serve as a
confound control.

## Sponsor prizes (separate challenges, stackable with track prize)
- **ElevenLabs**: Best Project Built with ElevenLabs (earbuds + 3 mo Scale). Free access via coupon
  (hacker-guide "Free ElevenLabs Access").
- **Databento**: Best Use of Databento ($4,000 credits).
- Gemini API (MLH swag), Snowflake API (Raspberry Pi 4), Vultr (portable screens), Tiger Data
  (Stream Deck Mini), Solana (Ledger).

## Eligibility / misc
Team 1–4, in person. One track per team. Disqualification: plagiarism, misrepresentation, data not
permitted for the track, non-reproducible code, CoC violation.
