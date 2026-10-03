# Case ledger: CEO public statements later contradicted by company action or regulators

Compiled 2026-10-02 (~23:20 ET) for PokerFace (GQH 2026, Systematic Trading). Machine-readable version:
`docs/research/case_ledger.csv` (17 rows). Event-day returns: `docs/research/case_ledger_reactions_v2.csv`,
from `.scratch/case_ledger/rx2.py` (yfinance adjusted closes; abnormal = stock return minus SPY return on the
first day the information could be traded; 5d = cumulative stock minus SPY over 5 sessions). NKLA, RIDE and
SIVB are delisted with no yfinance data, so their moves are the figures reported in the cited articles.

**How to use this.** These cases are for illustration and motivation in the quote note ("why vocal and
nonverbal tells might matter"). Do not use them as training or calibration data. They were selected *because*
they ended badly (hindsight and selection bias), n is tiny, and 5 of them fall inside the sealed OOS window
(2024-10-01..2026-09-30): C01, C02, C03 (ALJ ruling), C15, C16. Looking at OOS-window events while choosing
weights would count as test-set leakage under the GQH rules.

**Wording policy.** Neutral throughout: "statement later contradicted by…", "the SEC alleged, in a settled
action…". Never say "lied". Most regulatory outcomes are settlements without admission or denial; this is
noted per row.

Verdict scale: **confirmed** means both the statement and the contradicting event are confirmed by at least
2 independent sources. **partially_confirmed** means the contradiction is real but the spoken or on-video
element, or the attribution, is weaker than the anecdote suggests. **unverifiable** means the claim is not
supported, or there is no established contradiction (these rows serve as negative controls).

---

## 1. User anecdote: Musk, Model S/X, and Optimus. PARTIALLY CONFIRMED, not as described

**What actually happened**
- **2026-01-28, Q4 2025 earnings call (5:30 pm ET, audio webcast).** Musk: "We expect to wind down S and X
  production next quarter and basically stop production of Model S and X next quarter." He also said "it's
  time to bring the Model S and X programs to an end with an honorable discharge." The Fremont S/X space
  becomes an Optimus line (long-run target 1M units/yr). Sources:
  [Fool transcript](https://www.fool.com/earnings/call-transcripts/2026/01/28/tesla-tsla-q4-2025-earnings-call-transcript/),
  [CNBC](https://www.cnbc.com/2026/01/28/tesla-ending-model-s-x-production.html),
  [TechCrunch](https://techcrunch.com/2026/01/28/tesla-is-killing-off-the-model-s-and-model-x/),
  [Teslarati](https://www.teslarati.com/tesla-brings-closure-flagship-sentimental-model-s-model-x/).
  Production ended in roughly early May 2026, and the line was torn down in 46 days
  ([Yahoo/Electrek](https://electrek.co/2026/04/01/tesla-model-s-x-production-over-only-inventory-left/)).
- **The prior "denial" did happen, but not from Musk and not a month earlier.** On 2025-02-24, Lars Moravy
  (VP Vehicle Engineering) said on the *Ride the Lightning* podcast that S/X were "not going anywhere anytime
  soon", with a refresh coming in 2025
  ([TorqueNews](https://www.torquenews.com/11826/tesla-confirms-model-s-x-will-get-refresh-few-months-adds-there-no-plan-discontinue-vehicles),
  [Electrek](https://electrek.co/2025/02/24/tesla-announces-model-s-and-model-x-refresh-later-this-year/)).
  The gap to the reversal is **about 11 months**. Musk's own on-record S/X comment is from 2019: they were made
  "more for sentimental reasons than anything else"
  ([TechCrunch 2019](https://techcrunch.com/2019/10/23/elon-musk-model-s-model-x-production-continues-for-sentimental-reasons)).
  We searched for a Musk denial in Oct–Dec 2025 and found none, including in Q3 2025 call coverage.
  **UNVERIFIED / likely did not happen as described.**
- **TSLA reaction on 2026-01-29:** -3.45% raw, **-3.25% vs SPY**, -4.57% 5-day abnormal. This is heavily
  confounded by the same-call Q4 results, the capex guidance and the FCF outlook, so it cannot be attributed
  to the S/X news.
- **Safe wording:** "In Feb 2025 a Tesla engineering VP said the S/X were not going anywhere; 11 months later
  Musk announced their end."

## 2. User anecdote: Karp "does handstands before earnings calls". NOT SUPPORTED (unverifiable)

- No source documents a handstand or any other pre-earnings ritual.
- **What is documented.** At the **NYT DealBook Summit on 2025-12-03** (on video, with Andrew Ross Sorkin),
  Karp fidgeted visibly, half-rose from his chair and gestured heavily. The clip went viral. He has described
  dyslexia as "the formative moment of my life." On 2025-12-07, Palantir announced a "Neurodivergent
  Fellowship" for people "unable to sit still"
  ([Yahoo](https://ca.news.yahoo.com/alex-karps-body-language-viral-142846277.html),
  [Futurism](https://futurism.com/future-society/palantir-joke-ceo-cocaine)).
- **The handstand clips.** Videos of Karp doing handstand push-ups on his chair's armrests circulated after
  DealBook. They are described as **AI-generated** (meme pages label them so, and press coverage describes
  AI-generated exaggerations). One X account claims it was real, with no corroboration
  ([X post](https://x.com/neerajKh_/status/1998000294203199629),
  [meme template](https://magicmeme.com/meme/alex-karp-handstand-using-a-chair-ai-generated)).
- **His real routines:** near-daily cross-country skiing and tai chi/qigong
  ([InsideHook](https://www.insidehook.com/wellness/palantir-ceo-alex-karp-workout-routine), Axios 2023).
  Neither is tied to earnings.
- **PLTR reaction:** 2025-12-03 +2.81% vs SPY; 2025-12-08 +0.15% vs SPY. The market did not react to the
  body-language episode.
- **Do not repeat the online drug speculation.** Some outlets read Palantir's "skiing" wording as a joke, but
  there is no evidence for that speculation.
- **Relevance to PokerFace:** this is a useful cautionary example. Karp's nonverbal baseline is unusually
  "high-motion", which is exactly why PokerFace normalizes each CEO against their *own* baseline rather than
  against a population.

## 3. Ledger (15 further cases)

| id | CEO / ticker | Statement (date, venue, video?) | Contradicting event (date) | Reaction (abnormal vs SPY) | Verdict |
|---|---|---|---|---|---|
| C03 | Musk / TSLA | 2019-04-22 Autonomy Day livestream (video): "next year for sure, we'll have over a million robotaxis on the road" | No 2020 fleet. CA DMV accusations (filed 7/28/22, public 8/5/22); ALJ ruled marketing deceptive 2025-12-16 | 4/23/19 -0.46%; 8/5/22 -6.46%; 12/16/25 +3.34% | confirmed |
| C04 | Musk / TSLA | 2022-04-28 tweet (text): "No further TSLA sales planned after today" | Form 4s 8/9/22: ~$6.9B sold; more in Nov and Dec 2022 | 4/29 +2.93%; 8/10 +1.79%; 11/9 -5.11% | confirmed (not spoken) |
| C05 | Musk / TSLA | 2018-08-07 tweet (text): "Funding secured" | SEC complaint 9/27/18, settled 9/29 ($20M+$20M, no admit/deny); 2023 jury found Musk not liable | 8/7 +10.66%; 9/28 -13.91% | confirmed (not spoken) |
| C06 | Huang / NVDA | FY2018 calls (audio) and 10-Q MD&A: gaming growth attributed to gaming | 11/15/18 "crypto hangover" miss; SEC order 5/6/22 ($5.5M, no admit/deny); SCOTUS let the private suit proceed 12/11/24 | 11/16/18 -19.02% (5d -24.8%); 5/6/22 -0.30% | partial |
| C07 | Muilenburg / BA | 2019-04-29 post-AGM press conference (video): "no surprise or gap … slipped through [the] certification process" | Forkner messages 10/18/19; SEC settled charges 9/22/22 ($200M + $1M, no admit/deny) | 4/29 -0.61%; 10/18 -6.35%; 9/22/22 -2.36% | confirmed |
| C08 | Milton / NKLA | 2016–2020 TV, podcasts, unveilings (video): truck capability and technology claims | Hindenburg 9/10/20; resigned 9/21/20; SEC charges and indictment 7/29/21; convicted Oct 2022; 4-yr sentence 12/18/23; pardoned Mar 2025 | ~-11% (9/10, reported); -19% (9/21, reported) | confirmed |
| C09 | Burns / RIDE | 2020–21 filings, calls, media: 100k+ pre-orders as evidence of fleet demand | Special committee: pre-order disclosures "in certain respects, inaccurate"; CEO/CFO resigned 6/14/21; SEC settled 2/29/24 | 6/14/21 -18.84% (reported) | partial |
| C10 | Cook / AAPL | 2018-11-01 call (audio): "I would not put China in that category" | 1/2/19 guidance cut citing China; $490M class settlement (Mar 2024, no admission) | 11/2/18 -6.04%; 1/3/19 -7.57% | confirmed |
| C11 | Dimon / JPM | 2012-04-13 call (audio): "tempest in a teapot" | 5/10/12 ~$2B CIO loss disclosed (later ~$6.2B) | 4/13 -2.45%; 5/11 -8.98% (5d -12.9%) | confirmed |
| C12 | Stumpf / WFC | 2016-09-20 Senate testimony (video); 2015–16 certifications (written) | SEC settled charges 11/13/20 over certifications of the cross-sell metric ($2.5M) | 9/8/16 +0.49%; 11/13/20 -0.29% | partial (SEC finding concerns written certifications) |
| C13 | Zuckerberg / META | 2021-03-25 House hearing (video): social apps "can have positive mental-health benefits" | WSJ Facebook Files 9/14/21 on internal Instagram teen research; Haugen testimony 10/5/21 (Meta disputes) | 3/25 -1.77%; 9/14 +0.54% | partial |
| C14 | Gelsinger / INTC | 2024 foundry "significant traction / growing demand" | 8/1/24 miss, 15% job cuts, dividend suspended. **Suit dismissed (Mar and Jul 2025): statements not misleading** | 4/3/24 -8.33%; 8/2/24 -24.20% | unverifiable (negative control) |
| C15 | Witty / UNH | 2025-04-17 call (audio): revised 2025 adj EPS $26.00–26.50 | 5/13/25 outlook suspended, CEO out; WSJ DOJ probe report 5/14 (UNH confirmed cooperation 7/24) | 4/17 -22.52%; 5/13 -18.45%; 5/15 -11.42% | partial (OOS) |
| C16 | Liang / SMCI | No contradicted CEO statement identified | Hindenburg 8/27/24; 10-K delay 8/28; EY resignation disclosed 10/30; special committee found no misconduct 12/2/24 | 8/28 -18.44%; 10/30 -32.37%; 12/2 +28.50% | unverifiable (negative control, OOS) |
| C17 | Becker / SIVB | 2023-03-09 client call (audio, reported): "We now ask you not to panic" | Bank closed and FDIC appointed receiver on 3/10/23 | 3/9 ~-60% (reported); halted | confirmed |

The full source URLs for each row are in the CSV `sources` column. The main ones:
SEC [2022-170](https://www.sec.gov/newsroom/press-releases/2022-170) (Boeing),
SEC [2020-281](https://www.sec.gov/newsroom/press-releases/2020-281) (Stumpf),
[CNN on the NVDA SEC order](https://www.cnn.com/2022/05/06/tech/nvidia-sec-settlement-crypto-mining/index.html),
[CNN 2018 on the NVDA crypto hangover](https://edition.cnn.com/2018/11/16/tech/nvidia-stock-earnings-cryptocurrency/index.html),
[Courthouse News on SCOTUS/NVDA](https://courthousenews.com/supreme-court-dumps-nvidia-brawl-against-fraud-by-hindsight-suit/),
[Fast Company on AAPL $490M](https://www.fastcompany.com/91061197/apple-tim-cook-comment-just-cost-490-million-class-action-lawsuit),
[NPR on the London Whale](https://www.npr.org/sections/money/2012/05/11/152488354/jp-morgans-2-billion-loss-explained),
[CNBC on the 2019 Autonomy Day](https://www.cnbc.com/2019/04/22/elon-musk-says-tesla-robotaxis-will-hit-the-market-next-year.html),
[CNBC on the 2022 DMV accusations](https://www.cnbc.com/2022/08/05/california-dmv-says-tesla-fsd-autopilot-marketing-deceptive.html),
[Engadget on the 2025 ALJ ruling](https://www.engadget.com/transportation/evs/tesla-used-deceptive-language-to-market-autopilot-california-judge-rules-035826786.html),
[Electrek on Aug 2022 sales](https://electrek.co/2022/08/09/elon-musk-sells-massive-6-5-billion-chunk-of-tesla-tsla-stake/),
[NPR on the 2018 SEC settlement](https://www.npr.org/2018/09/29/653014733/elon-musk-settles-with-sec-agrees-to-step-down-as-tesla-chairman),
[ISS on the 2023 jury verdict](https://insights.issgovernance.com/posts/musk-tesla-win-rare-securities-class-action-trial/),
[CNBC on the Milton sentence](https://www.cnbc.com/2023/12/18/nikola-founder-trevor-milton-sentencing-fraud-charges.html),
[CNBC on Milton's resignation](https://www.cnbc.com/2020/09/21/nikola-founder-trevor-milton-to-voluntarily-step-down-as-executive-chairman.html),
[TechCrunch on the Lordstown SEC case](https://techcrunch.com/2024/02/29/lordstown-motors-sec-charged-misleading-investors/),
[CNBC on the Lordstown resignations](https://www.cnbc.com/2021/06/14/lordstown-motors-ceo-and-cfo-resign-.html),
[Claims Journal on the INTC dismissal](https://www.claimsjournal.com/news/national/2025/03/06/329304.htm),
[CNBC on the UNH CEO exit](https://www.cnbc.com/2025/05/13/unitedhealth-group-ceo-andrew-witty-steps-down.html),
[CNBC on the UNH DOJ report](https://www.cnbc.com/2025/05/15/unitedhealth-group-stock-doj-investigation-report.html),
[CNBC on the SMCI special committee](https://www.cnbc.com/2024/12/02/super-micro-computer-pops-14percent-after-special-committee-finds-no-evidence-of-misconduct.html),
[Bloomberg Law on SVB](https://news.bloomberglaw.com/tech-and-telecom-law/svb-ceo-becker-asks-silicon-valley-bank-clients-to-stay-calm),
[CNBC on SVB -60%](https://www.cnbc.com/2023/03/09/svb-financial-falls-more-than-50percent-as-tech-bank-looks-to-raise-more-cash.html).

## 4. What the ledger implies for the strategy (read this, lead quant)

1. **On statement day the market mostly did not react.** Abnormal returns on statement day: BA -0.6%,
   TSLA (Autonomy Day) -0.5%, META -1.8%, JPM -2.5%. AAPL -6.0% is contaminated by earnings. This is
   consistent with the "information is not priced at the statement" premise. It is anecdotal, though, and
   should not be presented as evidence.
2. **The lag from statement to contradiction is long and highly variable:** 1 day (SVB), 4 weeks (JPM), 2
   months (AAPL), 6 months (BA, META), about 11 months (TSLA S/X), and 15 months to years (NVDA, NKLA, TSLA
   robotaxi). A fixed short-horizon event window (1–21d) will miss most of these. Pre-register the horizon
   and expect a low hit rate.
3. **Most of the price impact comes at first disclosure, not at the regulator's date.** SEC settlement days
   moved little: NVDA -0.3%, BA -2.4%, WFC -0.3%. Do not date "truth revealed" events by SEC actions.
4. **Many of the strongest cases are not usable by a video or audio model.** C04 and C05 are tweets. C06,
   C10, C11, C15 and C17 are audio-only calls or audio-only private calls. Cases with the CEO speaking on
   camera: C02, C03, C07, C08, C09, C12, C13, C14. Recorded video exists, but YouTube URLs were not verified
   in this session.
5. **Negative controls matter.** INTC (suit dismissed), SMCI (no misconduct found) and PLTR show large
   moves, or viral "weird behavior", with no established misstatement. These are good examples for the
   note's limitations section on false positives.
6. **Selection bias.** The median contradiction-day abnormal return across these 16 events is about -11%.
   That number only reflects how the cases were chosen and must not appear as a performance claim.

## 5. Open items and UNVERIFIED items
- C06: the exact Huang spoken quote from the FY2018 calls was not retrieved; the SEC order concerns written
  10-Q MD&A.
- C09: the exact on-video Burns pre-order quote was not pinned down (statement_date 2020-10-26 is an
  approximate start of the class period). The SEC penalty amount for Burns was not verified.
- C08: the conviction day is given as Oct 2022 in sources (14 Oct per memory, UNVERIFIED). The
  statement_date 2016-12-01 is the Nikola One unveiling.
- Video URLs for every on-video row: UNVERIFIED (only the Lordstown CNBC clip URL came up in search).
- The current status of the NVDA private suit after Dec 2024: UNVERIFIED.
