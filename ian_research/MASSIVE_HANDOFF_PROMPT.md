# Handoff prompt: Massive "Trade the 8-K" bonus challenge (Gator Quant Hacks 2026)

Paste everything below into a new Claude Code session opened in `/Users/hqdatt/Documents/GQH`.

---

You're helping me (Ian, ian-hoang on GitHub) and my team compete in the **Massive "Trade the 8-K" bonus challenge**, part
of the Systematic Trading track at **Gator Quant Hacks 2026** (a 36-hour quant competition at the University of Florida's
Reitz Union, Oct 2–4, 2026). As of **Fri Oct 2, ~11:55 PM ET**, hacking has been running since 7:15 PM Friday.

## Deadlines (Eastern Time)
- **Sun Oct 4, 10:00 AM: Devpost submission closes** (quant note PDF + public GitHub repo link). Late = not judged.
- **Sun 11:00 AM:** last code push that gets reviewed.
- Sun 1:00 PM: GQH judges send their top 10 Massive entries to Massive. 2:30 PM: Massive picks the winner.
  3:35 PM: closing ceremony, winner announced.
- **Sat Oct 3, 1:00 PM: Massive workshop**, Reitz Union Room 2355 (challenge walkthrough, 8-K dataset, starter notebook, Q&A).
- Sat 5:00–6:00 PM: track check-ins and **Sunday presentation sign-ups**, Reitz Union Grand Ballroom.

## Read these first (the challenge pages are the source of truth)
- Massive bonus challenge page (full brief, starter-kit download, endpoint and taxonomy links):
  https://www.gqhacks.com/tracks/systematic-trading/massive
- Systematic Trading track brief (rules that also apply to Massive entries): https://www.gqhacks.com/tracks/systematic-trading
- Hacker guide (logistics, schedule, contacts): https://gqhacks.notion.site/hacker-guide
- Devpost: https://gqhacks.devpost.com
- Massive API docs: https://massive.com/docs (data comes from `https://api.massive.com`)
- OptionsPlaybook (the payoff conventions the challenge uses): https://www.optionsplaybook.com
- GQH Discord: https://discord.gg/kQX9ZtWFHG. Use **#massive** for API keys and data help, #ask-organizers for rules.

Read the pages with the browser tool (they're JS-rendered). On the Massive page, follow its **DOWNLOAD KIT**, **ENDPOINT DOCS**
and **TAXONOMY** links. I don't have those exact URLs.

## The challenge in short
- **Signal:** Massive's Filings & Disclosures dataset tags every 8-K since **Jan 2022** with one of **119 AI-tagged event types**
  (`tertiary_category`). Endpoint: `/stocks/filings/8-K/vX/disclosures`.
- **Instrument:** US options. The chain is taken as it existed the session **before** the filing (`t_pre`), via
  `/v3/reference/options/contracts?as_of=…`. Each leg's daily bars come from `/v2/aggs/ticker/O:…/range/1/day/…`.
  The stock price is recovered from the chain by put-call parity.
  - There is **no stock feed, no index-membership feed and no earnings calendar**. The notebook builds the trading
    calendar from NYSE holiday rules.
  - Three of the five strategies need 100 shares. The notebook builds those as a **synthetic long** (long ATM call +
    short ATM put).
- **Task:** pick one or more 8-K categories and **one of five fixed strategies**, and argue the category is a signal to enter it.
  - The five strategies:
    1. long call
    2. covered call
    3. protective put
    4. collar
    5. cash-secured put
  - Define the rule: which filings, which contracts, when to enter and when to exit.
  - Test it on the **100 largest US companies**. That list is static, so state the survivorship bias.
  - Compare against **ordinary days for the same names**.
  - Show **out-of-sample** results and **parameter sensitivity**.
- **Core idea: implied vs. realized move.**
  - Implied move = (ATM call + ATM put) / spot at `t_pre`.
  - Buying options wins when the realized move beats the implied move. Selling wins when it doesn't.
  - Watch for **IV crush**: a long call can lose even when the stock moves the right way.
  - Say which side of IV crush your strategy is on.
- **Notebook config (fixed by Massive unless noted):**
  - `EVENT_TAG` (e.g. `"cfo_appointment"`, ours to change)
  - `STUDY` 2024-01-01 → 2025-12-31 (in-sample)
  - `OOS` 2026-01-01 → 2026-08-31 (evaluate **once**; never tune on it)
  - `HOLDOUT`: a sealed window the **judges** choose and rerun our pipeline on
  - `TOP_100`
  - `EXPIRY_BUCKETS` 1m / 2m / 3–6m (the headline bucket is 3–6m)
  - **HORIZONS `[1, 2, 3, 5, 10, 21, 42, 63]` sessions plus expiry: fixed for every team; report all of them**
  - `OTM_PCT` 0.05 (grid 3/5/10%)
  - `ENTRY` `"post"` (tradeable) vs. `"pre"` ("was it priced in?")
  - `RUN_PLACEBO`: set it to False while exploring to save ~8 min per run, and back to True before submitting
  - The first run makes about 6,500 requests and takes ~10 min. Responses are cached in `.massive_cache/`.
- **Worked example in the notebook: CFO appointments.**
  - 70 in-sample events.
  - The best result was the collar: +0.42% versus ordinary days, before costs.
  - After costs it was −0.18%, using a haircut of 5% of the premium on each side at 21 sessions.
  - Only 12 out-of-sample events.
  - Conclusion: **no tradeable edge**. Our job is to find a category (or combination) that survives across horizons,
    out of sample, and after costs.
- **Three tiers:**
  - Baseline: one category, one strategy, one expiry bucket, plus a written interpretation.
  - Stretch (this is what separates the top teams): decay across horizons and expiry buckets, combined categories,
    a placebo control, timing refinements, a realistic trade spec.
  - Sealed window: judges call one function with dates we've never seen. **The pipeline must take a start and end date as inputs.**
- **Exception to the track's 20% holdout rule:** for Massive entries, the notebook's OOS window plus the sealed window
  replace it. Every other track rule still applies.

## How it's judged
1. **GQH judges, Systematic Trading rubric** (5 criteria × 10 = 50 points): Economic Foundation, Innovation, Risk Management Plan,
   Liquidity & Capital, Performance & Analytical Evidence.
   - **Score cap:** Performance is capped at 4/10 in any of these cases:
     - the code won't run
     - the code doesn't reproduce the numbers in the note
     - there's lookahead bias
     - the out-of-sample period was used for tuning
2. **Massive, for the bonus** (100 points):
   - **30 points, hypothesis and novelty:** a non-obvious, economically motivated link from category to strategy.
     "Guidance up, buy a call" is the floor.
   - **30 points, analytical rigor:** every horizon, a placebo or baseline, out-of-sample results, uncertainty, sensitivity.
   - **20 points, sealed-window replication:** the result holds on the judges' window, *or* we predicted its fragility and were right.
   - **10 points, trade realism:** entry respects the filing lag; costs, liquidity and capacity come from the data.
   - **10 points, communication.**
   - **"A well-argued null result with a clear decay curve beats a lucky backtest."**
- **Prize:** $500 toward the team prize, a month of Massive Advanced per member, and swag. The hacker guide lists AirPods 4 per
  member for the Massive subtrack winner.

## What we submit
1. **A quant note PDF of at most 5 pages**, 11pt or larger. References and appendix don't count toward the limit, but judges
   may not read the appendix. It must cover:
   - the hypothesis (which categories, which strategy, why the market should misprice it)
   - the method
   - results with uncertainty at every fixed horizon, in-sample and out-of-sample
   - what would make it break
   - how we'd trade it
   - a sensitivity check (expiry bucket, OTM distance, entry session, horizon, category definition)
2. **A public GitHub repo:**
   - the notebook (built on the starter) runs from a clean kernel with **only `MASSIVE_API_KEY`** set
   - it takes a start date and an end date as inputs
   - a README and a dependency file
   - **never commit `.env`, the API key, or `.massive_cache/`** (the data is licensed)

Massive's 12-item submission checklist is on the bonus page. Go through it before submitting.

## Setup steps
1. **API key:** ask in **#massive** on the Discord. I'll put it in `.env` as `MASSIVE_API_KEY=...` myself. Don't ask me to paste
   it in chat. Never put it in a notebook cell.
2. **Starter kit:** download it from the bonus page (zip: notebook, `setup.sh`/`setup.ps1`, `requirements.txt`, `.env.example`,
   `.gitignore`, README). Python 3.10+.
3. **Reproduce the CFO example end to end** before changing anything.

## Our repo and what NOT to touch
`/Users/hqdatt/Documents/GQH` is our repo (GitHub `ian-hoang/gqh-strategy`, private for now; it must be public by Sunday 10 AM).
- **Our main-track work is finished and locked. Don't change it:**
  - `strategies/roll_oi.py`: commodity futures roll / liquidation flows. Out-of-sample was run once and recorded in
    `results/OOS_LOCK.json`.
  - Also leave alone: `strategies/treasury_auction.py`, `strategies/roll_tas.py`, `run_all.py` (its `FINAL` points at
    `roll_oi`), and the shared harness in `gqh/`. `run_all.py --final` must keep reproducing the locked numbers.
- **Codex (another AI agent) is building its own 3 strategies in this same folder. Don't edit, run or commit its files:**
  `microstrategies/`, `gqh/microdata.py`, `gqh/microengine.py`, `run_micro.py`, `data/download_micro.py`,
  `hypotheses/{liquidity_fatigue,missing_beat,queue_sacrifice}.md`, `tests/test_*micro*`,
  `tests/test_{liquidity_fatigue,missing_beat,queue_sacrifice}.py`, and the `results/micro/` entries in `.gitignore`.
- **Put all Massive work in a new folder, `massive/`.** Give it its own `.env`, and add `.gitignore` entries for `massive/.env`
  and `massive/.massive_cache/`.
- **Open question for the organizers (ask in #ask-organizers before we decide):** the Massive page says a Massive entry
  *is* a Systematic Trading submission. Can one team submit **two** Devpost projects, `roll_oi` for the main track and a
  Massive project? Or must the Massive project be our single track entry? That decides whether this becomes a second
  repo or submission.

## How I like to work
- **Keep everything local.** No git commits or pushes unless I explicitly ask.
- **Explain things simply.** I'm newer to options.
- **Be honest about weak or null results.** Never present cherry-picked numbers.
- **Write the hypothesis first** (who is mispricing what, and why it persists). Commit it only when I say.
- **Out-of-sample:** evaluate the notebook's OOS window **once**, at the end, on the final rule.
- **Count variants:** keep track of every category/strategy/parameter combination tried, so we can disclose the count.

## Suggested plan
1. Read the three challenge pages above, then get the key and kit and reproduce the CFO run.
2. Pull the **taxonomy of 119 categories**. Brainstorm 5–8 non-obvious category → strategy pairings, each with an economic
   reason for mispricing (who is on the other side, which way IV should be wrong). Rank them by novelty and by how many
   events the top-100 universe has 2024–2025 (sample size is the main constraint). Check with me before deep work.
3. Run the pipeline in-sample for the top 2–3 pairings:
   - all horizons, against ordinary days
   - placebo on
   - uncertainty bands
   - sensitivity grid
4. Choose the final rule using **in-sample results only**, then run OOS once.
5. Write the trade spec:
   - entry versus the filing lag
   - costs (in bps / as a premium haircut)
   - liquidity from option volume
   - capacity
6. Write the predicted fragility for the sealed window. Then write the note and README, and make sure the notebook
   runs clean with only the key.
