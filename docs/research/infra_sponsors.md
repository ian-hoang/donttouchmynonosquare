# Data infrastructure, sponsor prizes, and the agentic layer

Compiled Fri 2026-10-02, about 23:40 ET. **VERIFIED** means I fetched the source or ran the code tonight. **UNVERIFIED** means a secondary source or my inference; check it before relying on it.
Tested code is in `.scratch/quant_infra/` (`test_sec.py`, `test_ff.py`, `test_costs.py`, `dbn_spreads.py`) and `.scratch/sponsors/agentic_wrappers.py`. Every script was run as a single Python process with peak RSS under 225 MB.

---

## 0. Things the lead needs to act on

1. **Deadline conflict.** `docs/GQH_RULES.md` gives the Devpost deadline as 10:00 AM Sunday, quoting the gqhacks.com track page. Devpost ("Deadline: Oct 4, 2026 @ 11:00am EDT") and the Notion hacker guide ("Submissions are due on Devpost by 11:00 AM on Sunday") both say 11:00. **Plan for 10:00.** (VERIFIED: `.scratch/sponsors/devpost.html.txt`, `notion.txt`)
2. **Databento key.** `.env` has no keys yet. All three values are empty, because the file is a copy of `.env.example`. Devpost Resources: "Databento, Massive, and Webull access is released when hacking begins," with setup help at Friday office hours. Get the key from the GQH Discord or the organizers. New Databento accounts also get **$125 in free credit**. (VERIFIED: databento.com/equities page text)
3. **The Databento prize is not on the Devpost prize list.** Devpost shows 12 non-cash prizes: 6 MLH prizes (ElevenLabs, Gemini, Solana, Tiger Data, Vultr, Snowflake), Trading 1st and 2nd, Puzzles 1st and 2nd, Massive, and Hardware. "Best Use of Databento ($4,000 credits)" appears only in the Notion guide. Ask in Discord how to be considered for it. A Databento representative is listed as a Devpost judge. (VERIFIED)
4. **Item 2.02 8-Ks are not all earnings releases.** TSLA has 90 Item-2.02 8-Ks since 2016, about 2 per quarter, because its delivery reports are also filed under 2.02 (for example 2026-07-02 13:01Z and 2026-10-02 13:04Z). Filter them (§2).
5. **Ken French daily factors end 2026-08-31**, so September 2026 of the OOS window has no FF5 or momentum data yet. Either run the factor regression through 2026-08-31 and disclose that, or proxy the market factor with SPY minus RF for September.
6. **Free daily spread estimators fail on mega caps.** Abdi-Ranaldo CHL on yfinance bars gives 0.0 bp for AAPL/MSFT/TSLA/META/AMD and 55 bp for NVDA. That noise is the reason to measure costs with Databento quotes (§1d).
7. Something I saw in passing in another agent's log (`.scratch/fetch_meta.log`): yt-dlp is hitting YouTube's "Sign in to confirm you're not a bot" wall on several videos. This is a risk to the corpus.

---

## 1. Databento

### 1a. Dataset IDs, start dates and schemas

| Dataset | What it is | History start | Status / source |
|---|---|---|---|
| `XNAS.ITCH` | Nasdaq TotalView-ITCH, venue-only prints and quotes; covers all US-listed names traded on Nasdaq | **2018-05-01** | VERIFIED: dataset page JSON-LD `temporalCoverage` and pricing widget `data_start` (databento.com/datasets/XNAS.ITCH) |
| `XNYS.PILLAR` | NYSE Integrated (primary venue for JPM) | **2023-03-28** | VERIFIED: JSON-LD on databento.com/datasets/XNYS.PILLAR |
| `ARCX.PILLAR` | NYSE Arca Integrated (primary venue for **SPY**, XLK, XLF, SMH) | **2018-05-01** per the pricing widget; the JSON-LD says 2017-05-21 | VERIFIED but conflicting. Confirm with `metadata.get_dataset_range` (free) |
| `XNAS.BASIC` | Nasdaq Basic + NLS Plus (includes TRF prints); schemas cbbo/tcbbo/cmbp-1 | 2024-07-01 | VERIFIED: page `data_start` |
| `EQUS.MINI` | Synthetic "mini" NBBO blended from prop feeds, no exchange license fee | **2023-03-28** | VERIFIED: databento.com/blog/databento-us-equities-mini-now-available ("starts from March 28, 2023"). The blog lists mbp-1 and trades. bbo-1m/tbbo are UNVERIFIED; check with `list_schemas` |
| `EQUS.SUMMARY` | Consolidated EOD OHLCV across all exchanges and ATSs, with official volumes | **2024-07-01** (UNVERIFIED: search-engine summary; my fetch of the dataset page hit a JS shell). Daily only, no ohlcv-1m | The "100% … consolidated end-of-day prices (OHLCV)" description is VERIFIED from the equities page |
| `DBEQ.BASIC` | Legacy bundle (IEX TOPS, NYSE Chicago, NYSE National) | 2023-03-28 | Deprecated (search summary says 2025-01-13; UNVERIFIED). **Do not use** |
| also in the SDK enum | `EQUS.ALL, EQUS.PLUS, EQUS.SIP, XNYS.TRADES, XNYS.BBO, XNYS.TRADESBBO, XNAS.QBBO, XNAS.NLS, IEXG.TOPS, XBOS.ITCH, XPSX.ITCH` | — | VERIFIED: `databento.Dataset` in databento 0.87.0 |

Schemas available on the venue datasets (VERIFIED on the XNAS/XNYS/ARCX pages): mbo, mbp-1, mbp-10, **tbbo**, trades, **bbo-1s/bbo-1m** ("last best bid, best offer, and sale sampled at fixed 1-second or 1-minute intervals … forward-filled"), **ohlcv-1s/1m/1h/1d**, imbalance, **statistics** (official open, high, low and close from the venue), status, definition. SDK `Schema` also has `ohlcv-eod`, `cbbo-1s/1m`, `tcbbo` and `cmbp-1`. Record sizes (VERIFIED, `databento_dbn` 0.70): BBO/MBP-1/Stat = 80 B, Trade = 48 B, OHLCV = 56 B. `StatType.OPENING_PRICE` = 1.

**What this means for the backtest.** No Databento dataset covers 2016-01 to 2018-04. Consolidated daily bars start only in 2024-07. Keep **yfinance adjusted daily bars as the backtest backbone** over 2016 to 2026. That is already what `event_bt.py` uses. Use Databento for (i) intraday cost calibration and minute-level reaction paths from 2018-05-01 onward, and (ii) an **OOS data audit**: compare EQUS.SUMMARY consolidated closes against yfinance closes for 2024-10 to 2026-09 and report the largest deviation.

**Primary-venue mapping.** AAPL, MSFT, NVDA, GOOGL, AMZN, META, TSLA, AMD, COIN and PLTR are Nasdaq-listed, so XNAS.ITCH carries their opening and closing crosses. PLTR moved to Nasdaq in Nov 2024 (UNVERIFIED date); before that it was NYSE. JPM uses XNYS.PILLAR (from 2023-03-28). SPY uses ARCX.PILLAR. Before 2023-03-28, NYSE names fall back to Nasdaq-venue quotes, which are close to the NBBO for mega caps but are not the primary venue. Footnote this.

### 1b. Python (signatures VERIFIED against the installed databento 0.87.0)

```python
import databento as db, pandas as pd
c = db.Historical(key=KEY)                                    # gateway hist.databento.com
c.metadata.get_dataset_range(dataset="XNAS.ITCH")             # free
c.metadata.list_schemas(dataset="EQUS.MINI")                  # free
# get_cost(dataset, start, end=None, mode=?, symbols=None, schema='trades', stype_in='raw_symbol', limit=None) -> float USD, free
usd = c.metadata.get_cost(dataset="EQUS.SUMMARY", schema="ohlcv-1d", symbols=["NVDA","SPY"],
                          stype_in="raw_symbol", start="2024-07-01", end="2026-10-01")
# get_range(dataset, start, end=None, symbols=None, schema='trades', stype_in='raw_symbol', stype_out='instrument_id', limit=None, path=None) -> DBNStore
d1 = c.timeseries.get_range(dataset="EQUS.SUMMARY", schema="ohlcv-1d", symbols=["NVDA","SPY"],
                            stype_in="raw_symbol", start="2024-07-01", end="2026-10-01").to_df()
t0 = pd.Timestamp("2025-08-28 09:25", tz="America/New_York"); t1 = t0 + pd.Timedelta("65min")
m1  = c.timeseries.get_range(dataset="XNAS.ITCH", schema="ohlcv-1m", symbols=["NVDA"], stype_in="raw_symbol",
                             start=t0.tz_convert("UTC"), end=t1.tz_convert("UTC")).to_df(tz="America/New_York")
bbo = c.timeseries.get_range(dataset="XNAS.ITCH", schema="bbo-1m",  symbols=["NVDA"], stype_in="raw_symbol",
                             start=t0.tz_convert("UTC"), end=t1.tz_convert("UTC")).to_df(tz="America/New_York")
spy = c.timeseries.get_range(dataset="ARCX.PILLAR", schema="bbo-1m", symbols=["SPY"], stype_in="raw_symbol",
                             start=t0.tz_convert("UTC"), end=t1.tz_convert("UTC")).to_df(tz="America/New_York")
```
Defaults of `to_df()` (VERIFIED): `price_type="float"` (already divided by 1e9), `pretty_ts=True`, `map_symbols=True`, `tz=UTC`. ohlcv-1m emits a bar **only for minutes that had trades**, with no forward fill. bbo-1m is forward-filled.
The full guarded pipeline is `.scratch/quant_infra/dbn_spreads.py`: get_cost first, a `$DBN_MAX_USD` cap, then bbo-1m, ohlcv-1m, 60 s of tbbo and the official open from `statistics`. Its `entry_costs()` was tested offline on a synthetic window: compile OK and correct bps arithmetic. The network path is **untested** because there is no key.

### 1c. Splits and dividends
- Databento market data is **raw and unadjusted** (UNVERIFIED in docs; implied by the existence of the separate adjustment product). Adjustment lives in the **Reference API**: `db.Reference(key).adjustment_factors.get_range(start, end, symbols, stype_in, countries, security_types)` and `.corporate_actions.get_range(..., events, pit=False)`. Both are VERIFIED to exist in SDK 0.87. Pricing is a separate subscription, **"starts at $225/month"** for adjustment factors and **$299/month** for corporate actions (search summary of databento.com/blog/adjustment-factors and /blog/corporate-actions; UNVERIFIED). That is not worth buying here.
- Approach: every Databento-derived quantity is **intraday** (spread at the open, minute path as a ratio to the open), so splits don't matter. Multi-day returns come from yfinance adjusted prices. If raw Databento daily bars are ever used across days, apply yfinance `Ticker.splits` ratios.

### 1d. Best genuine use, for the "Best Use of Databento" prize
**"Measured, not assumed, costs."** For every traded event (entry at the first open after the video timestamp), pull the stock and SPY (the hedge) with bbo-1m from 09:25 to 10:30 ET, tbbo for 09:30:00 to 09:31:00, and statistics for the official open. Then:
1. Quoted half-spread at 09:31 and the median over the first hour.
2. Volume-weighted **effective half-spread** of trades in the first 60 s: |px − mid| / mid.
3. **Auction slippage**: official open versus the 09:31 mid.
4. Per-trade cost = (2) + (3) + square-root impact at our size. Then report the backtest with **per-trade measured costs**, alongside the flat 5 bp, 10 bp and 2× assumptions.
5. Minute reaction paths: ohlcv-1m for stock and SPY over the first 60 to 390 minutes after the open, giving market-hedged path plots (does the move happen at the open or drift?) and a check on **execution-timing sensitivity** (enter at 09:31 or 10:00 VWAP instead of the open).

Size estimate (UNVERIFIED; run `get_cost`): 600 events × 2 symbols × 65 min × 80 B is about 6 MB of bbo-1m, plus a similar amount of tbbo and ohlcv-1m. Total cost is likely a few dollars. **Do not** pull full-history ohlcv-1m for the whole universe: 16 symbols × 8.4 years is about 13 M rows, roughly 740 MB, which breaks the 300 MB disk cap.

---

## 2. Tested snippets (each run alone, one process at a time)

**SEC EDGAR 8-K Item 2.02** (`.scratch/quant_infra/test_sec.py`, ran in 32 s, peak RSS 221 MB). It uses `company_tickers.json`, then `data.sec.gov/submissions/CIK##########.json`, and pages through `filings.files[]`. The User-Agent header contains a contact email.
- TSLA: 90 Item-2.02 8-Ks since 2016 (2016-01-04 to 2026-10-02). NVDA: 45 (2016-02-17 to 2026-08-26). JPM: 43. COIN: 24 (from 2021-04-06). PLTR: 25 (from 2020-11-12).
- **`acceptanceDateTime` is true UTC.** Spot checks against known release times: NVDA 2026-08-26T20:21Z = 16:21 ET, which matches NVDA's after-close release. TSLA 2026-07-02T13:01Z = 09:01 ET, which matches Tesla's 9 AM delivery release. The 8-K can **lag** the press release: PLTR 02:06Z (21:06 ET) and COIN 00:06Z (20:06 ET). Treat it as an upper bound on announcement time. Under the next-open entry rule this changes nothing.
- Earnings filter: drop Item-2.02 8-Ks whose exhibit-99.1 title lacks "results" or "financial results", or keep the first 2.02 filing 15 to 60 days after fiscal quarter end. JPM has many non-2.02 8-Ks (168k rows in recent filings), so filter on the `items` field, as the script already does.

**Ken French daily FF5 + Momentum** (`test_ff.py`, 2 s, 147 MB). It downloads `F-F_Research_Data_5_Factors_2x3_daily_CSV.zip` (150 KB) and `F-F_Momentum_Factor_daily_CSV.zip` (85 KB) from `mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/`, divides percentages by 100, and does an inner join. Output: FF5 1963-07-01 to **2026-08-31**; Mom 1926-11-03 to 2026-08-31; columns `Mkt-RF, SMB, HML, RMW, CMA, RF, Mom`. VERIFIED.

**Liquidity and impact inputs** (`test_costs.py`, yfinance, 63-day window ending 2026-10-02): ADV in $bn and daily vol in %. SPY 33.5 / 0.69. NVDA 26.5 / 2.41. QQQ 25.3 / 1.19. AAPL 14.8 / 1.70. TSLA 13.4 / 3.21. MSFT 13.0 / 2.37. META 12.4 / 2.99. AMD 12.2 / 4.08. AMZN 10.0 / 2.49. GOOGL 9.4 / 2.15. PLTR 5.5 / 4.39. SMH 4.9 / 2.46. JPM 2.66 / 1.19. XLF 1.86 / 0.79. COIN 1.53 / 4.71. XLK 1.40 / 1.63. **Ignore its AR-spread column** (see §0.6).

---

## 3. Cost assumptions for mega caps and SPY

| Component | Value | Source |
|---|---|---|
| Quoted half-spread, mega caps | Tick floor: $0.01 / $180 = 0.28 bp half-spread (NVDA); SPY at about $650 gives about 0.08 bp. Spreads at the open are several times wider. | Arithmetic from the Reg NMS penny tick. Measure the real value with §1d |
| **Base one-way all-in assumption** | **5 bp per side for single stocks, 1 to 2 bp for the SPY hedge**, covering half-spread, opening-auction slippage and impact at ≤$10M. Stress at **2× = 10 bp**, per the GQH rule. | Conservative relative to the tick floor; calibrate with Databento |
| SEC Section 31 fee (sells only) | **$20.60 per $1M = 0.206 bp** on charge dates from 2026-04-04. It was **$0.00/M** from 2025-05-14 to 2026-04-03. | SEC fee-rate advisory, sec.gov/rules-regulations/fee-rate-advisories/2026-2; FINRA Information Notice 2026-03-17 (finra.org/rules-guidance/notices/information-notice-20260317). VERIFIED via search snippets |
| FINRA TAF (sells) | $0.000195/share, max $9.79 per trade (2026) | finra.org/rules-guidance/guidance/faqs/trading-activity-fee; SEC SR-FINRA-2026 exhibit. Search snippet |
| Borrow (short leg or SPY short) | General collateral: **about 25 bp/yr** value-weighted, and GC stocks 17 bp/yr value-weighted mean (D'Avolio 2002, JFE "The market for borrowing stock"). S&P 500 names are "almost always GC". A 5-day hold costs about 25 bp × 5/360 = **0.35 bp**. Assume **50 bp/yr** to be conservative. | sciencedirect.com/science/article/abs/pii/S0304405X02002064 |
| Impact model | **I = Y · σ_daily · √(Q/ADV)**, Y ≈ 0.6 for equities (Almgren et al. 2005); 0.5 to 0.6 (Tóth et al. 2011); "of order unity". **Use Y = 1** for conservatism and show Y = 0.6. | arxiv.org/pdf/2205.07385 (Said, review); Tóth et al. 2011 PRX |

**Capacity from the square-root law.** Q* = ADV · (c_max / (Y·σ))². With Y = 1 and an impact budget of c_max = 10 bp: SPY ≈ $700M, AAPL ≈ $51M, NVDA ≈ $46M, MSFT ≈ $23M, GOOGL ≈ $20M, JPM ≈ $19M, AMZN ≈ $16M, META ≈ $14M, TSLA ≈ $13M, AMD ≈ $7M, PLTR ≈ $2.9M, COIN ≈ $0.7M. At $10M per trade, participation is 0.04 to 0.08% of ADV for the megacaps and 0.65% for COIN. COIN and PLTR are the binding names. Report a capacity curve of net Sharpe versus $ per trade.

---

## 4. Sponsor prizes: requirements, stacking, and the minimal genuine integration

**Stacking.** The Notion guide lists "Sponsor Prizes" separately from "Track Prizes", and Devpost lists each MLH prize as its own category. The rule "each team may submit to only one track" covers tracks, not sponsor challenges. Nothing explicitly says prizes stack (UNVERIFIED), so ask in Discord. In standard Devpost practice you opt into each prize category on the submission form; do that before 10:00. Also: the Trading 1st prize already includes "3 months of ElevenLabs Pro" per member.

| Prize (as listed) | What it requires (Devpost/Notion text) | Genuine fit for PokerFace | Minimal integration | Effort |
|---|---|---|---|---|
| **ElevenLabs**: Devpost "MLH: Best Use of ElevenLabs" (earbuds); Notion "Best Project Built with ElevenLabs" (earbuds plus 3 months Scale, $897 per member) | Integrate ElevenLabs audio into the hack | **Strong.** Scribe diarization isolates the CEO's speech from the interviewer's. That is a precondition for clean vocal features and **response latency** (CEO turn start minus interviewer turn end). Word timestamps give speech rate and pauses; `audio_event` tags give laughter and similar | `scribe_v2`, `diarize=True`, `timestamps_granularity="word"`, `tag_audio_events=True`. Pick the CEO speaker by talk time or Gemini label. Cache the JSON. Optional: a 60 to 90 s **TTS audio abstract** of the results with a stock voice (`eleven_flash_v2_5` or `eleven_v4`), **never a cloned CEO voice** | Scribe 1.5 to 2.5 h; TTS 20 min |
| **Databento**: "Best Use of Databento", $4,000 credits (Notion only) | Use Databento data | **Strong.** §1d measured-cost calibration plus minute reaction paths plus OOS data audit | `dbn_spreads.py` | 1.5 to 2 h after the key arrives |
| **Gemini API** (MLH swag) | Build with the Gemini API | **Good.** (a) Agentic curation: video metadata to `{is_unscripted_interview, speaker_is_target_ceo, recording_date_evidence, format}`. (b) **Entity-masked** utterance labels (hedge, non-answer, deflection, certainty). Masking stops the model from using what it knows about later stock moves. Labels are frozen and cached before the backtest and enter the pre-specified score with literature weights, not fitted ones | `agentic_wrappers.gemini_json` + `mask_entities` | 2 to 3 h |
| **Tiger Data** (Stream Deck Mini) | "most innovative, impactful, and performance-driven use of Tiger Data" | **Moderate.** TimescaleDB hypertable `utterance_features(ceo, ts, feature...)`. The **per-CEO trailing baseline** becomes a windowed and as-of query (`time_bucket` plus window over strictly earlier rows), which enforces no lookahead in SQL. A continuous aggregate feeds the dashboard | Mirror parquet to Tiger Cloud behind an optional `--store tiger` flag, so a judge's one-command run never needs the DB. **psycopg is not installed** (needs pip approval). Free plan is reportedly 750 MB, plus a 30-day Performance trial (UNVERIFIED; tigerdata.com/pricing) | 1.5 to 2 h |
| Vultr (portable screens) | Deploy on Vultr | **Plausible and useful.** Run the MediaPipe and audio extraction on a Vultr VM instead of the 16 GB Mac, which addresses the crash | Needs an account the user creates; rsync the code; run `extract.py` | 1 to 2 h; low priority |
| Snowflake (Raspberry Pi 4) | Snowflake REST/Cortex LLM | Duplicates Gemini; **skip** | — | — |
| Solana (Ledger) | Build on Solana | No genuine fit. The only defensible idea is a devnet memo carrying the SHA-256 of the pre-registered hypothesis and weights, a tamper-evident timestamp on top of the git commit. It's a gimmick; **skip** unless time is left | — | 45 min |

---

## 5. Gemini API as of Oct 2026 (VERIFIED, ai.google.dev fetched tonight)
- **Stable model ids**: `gemini-3.8-flash` (flagship Flash), `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3.5-transcribe` (STT with diarization and word timestamps), `gemini-3.8-flash-tts`. **Preview**: `gemini-3.1-pro-preview`, `gemini-3-flash-preview`. **Gemini 2.5 is access-limited** to prior users, and `gemini-2.0-flash` and `gemini-3-pro-preview` are shut down. (ai.google.dev/gemini-api/docs/models)
- **Pricing and free tier** (ai.google.dev/gemini-api/docs/pricing). Free tier exists for 3.8-flash, 3.6-flash, 3.5-flash-lite, 3.1-flash-lite and 3.5-transcribe. **3.1-pro-preview has no free tier.** Paid rates per 1M tokens in/out: 3.5-flash-lite $0.30/$2.50; 3.1-flash-lite $0.25/$1.50; 3.8-flash $0.75/$3.75 through 2026-12-31. **On the free tier, content is used to improve Google products.** Public YouTube text is fine; don't send anything private.
- **Free-tier RPM/RPD numbers are no longer printed** on the rate-limits page; it says to view them in AI Studio (aistudio.google.com/rate-limit). Exact limits are UNVERIFIED. Design for about 10 RPM: sequential calls, exponential backoff on 429, and the cache.
- **Temperature.** Google says: "For all Gemini 3 models, we strongly recommend keeping the temperature parameter at its default value of 1.0." Going lower "may lead to unexpected behavior, such as looping" (ai.google.dev/gemini-api/docs/gemini-3). So **do not set temperature 0**. Get determinism from the **disk cache plus a fixed `seed`**. `thinking_level` defaults are high for 3 Flash/Pro and minimal for 3.1 Flash-Lite. `thinking_level` and `thinking_budget` cannot be sent together (that returns a 400).
- **SDK** (google-genai **2.28.0** installed; VERIFIED by introspection). The docs now show the new Interactions API: `client.interactions.create(model=..., input=..., response_format={"type":"text","mime_type":"application/json","schema": Model.model_json_schema()}, generation_config={"seed":7,"thinking_level":...}, store=False)`. The classic path still exists and is simpler: `client.models.generate_content(model, contents, config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=PydanticModel, seed=7, thinking_config=types.ThinkingConfig(thinking_level="low")))`. `GenerateContentConfig` has `temperature, seed, response_mime_type, response_schema, response_json_schema, thinking_config, media_resolution`. Neither path was run live (no key).
- **Recommended model:** `gemini-3.5-flash-lite` (stable, free tier, cheap). Pin it in config and print it in the README.
- **Disk-cache wrapper** (`.scratch/sponsors/agentic_wrappers.py`, tested offline: a hit returns the first value with one underlying call, and an offline miss raises):
  - The key is sha256 of the canonical JSON of {model id, prompt-template version, masked input, JSON schema, seed}.
  - The file is `cache/<stage>/<hash>.json` holding {request, response, ts}, written atomically (tmp then rename).
  - `--offline` raises on a miss, so a judge without keys still gets identical numbers. Commit `cache/`; it's small JSON. Never re-query when an entry exists.
  - Log the model id and SDK version per stage. Run calls in one process, sequentially.

## 6. ElevenLabs Scribe (VERIFIED from SDK 2.70.0 introspection and elevenlabs.io docs)
- **Model ids**: `scribe_v2` (batch), `scribe_v2_realtime`, `scribe_v2_medical`. `scribe_v1` is **deprecated**. TTS ids: `eleven_v4`, `eleven_v4_turbo`, `eleven_v3`, `eleven_v3_conversational`, `eleven_multilingual_v2`, `eleven_flash_v2_5` (elevenlabs.io/docs/overview/models).
- **Call**: `ElevenLabs(api_key=...).speech_to_text.convert(model_id="scribe_v2", file=open(p,"rb"), diarize=True, num_speakers=None, timestamps_granularity="word", tag_audio_events=True, language_code="en", keyterms=[...])`. Other parameters: `diarization_threshold, source_url, cloud_storage_url, webhook, use_multi_channel, entity_detection, no_verbatim, detect_speaker_roles, seed, temperature`. Endpoint `POST /v1/speech-to-text`.
- **Response** (`SpeechToTextChunkResponseModel`): `language_code, language_probability, text, words[], channel_index, additional_formats, transcription_id, entities, audio_duration_secs, edited_transcript`. Each word (`SpeechToTextWordResponseModel`) has `text, start, end, type ("word"|"spacing"|"audio_event"), speaker_id ("speaker_0"…), logprob, characters, channel_index`.
- **Limits**: up to 32 speakers; up to 10 h of audio. The file cap is "3 GB" on the capabilities page but "5.0GB" in the API reference, with `source_url` ≤ 2 GB. Concurrency = min(4, ceil(duration_s/480)).
- **Surcharges**: keyterms +20% (minimum 20 s billable if more than 100 terms), entity_detection +30%, detect_speaker_roles +10%. Don't use `no_verbatim`, because fillers and false starts are deception cues.
- **Pricing** (elevenlabs.io/pricing/api, cached): API pay-as-you-go is **$0.22 per audio hour** for Scribe v2 ($0.39/h realtime). On subscription credits, STT costs **330 credits per minute**. Free 10k credits is about 30 min. Starter 30k is about 1.5 h. Creator 121k is about 6.1 h. Pro 600k is about 30 h. Scale 1.8M is about 91 h.
- **GQH coupon**: claimed through the ElevenLabs Discord bot (#coupon-codes, then "Start Redemption", choose Gator Quant Hacks, use the registration email). **What it grants is UNVERIFIED**; MLH-style coupons are often one month of Creator. Plan for about 6 h of Scribe. 300 interviews × 15 min of CEO audio is about 75 h, which won't fit. Options: (a) Scribe only the event-relevant clips or the OOS set, and use local mlx-whisper (word timestamps, no diarization) elsewhere; (b) the user pays as they go, 75 h × $0.22 ≈ $17 (their decision; needs their card); (c) send 16 kHz mono Opus to keep uploads small.
- Diarization utilities (`ceo_words`, `turns`, response latency) were tested offline on a synthetic Scribe response: CEO picked by talk time, turns grouped by a 0.8 s gap, latency 1.1 s.

## Sources
devpost: gqhacks.devpost.com (overview, prizes, resources, rules; cached in `.scratch/sponsors/`) · Notion hacker guide gqhacks.notion.site/hacker-guide (`notion.txt`) · databento.com/datasets/{XNAS.ITCH,XNYS.PILLAR,ARCX.PILLAR,XNAS.BASIC} · databento.com/equities · databento.com/blog/databento-us-equities-mini-now-available · databento.com/blog/introducing-databento-us-equities · databento.com/blog/adjustment-factors · databento.com/blog/nasdaq-historical-data-changes-2026-09 (instrument_id remap and after-hours fix effective 2026-10-31; no effect on us) · sec.gov submissions API · Ken French data library · sec.gov fee-rate advisory 2026-2 · FINRA TAF FAQ · D'Avolio (2002) JFE · Almgren, Thum, Hauptmann & Li (2005) Risk · Tóth et al. (2011) PRX · ai.google.dev/gemini-api/docs/{models,pricing,rate-limits,structured-output,gemini-3,text-generation} · elevenlabs.io/docs/{api-reference/speech-to-text/convert,capabilities/speech-to-text,overview/models} · elevenlabs.io/pricing/api · tigerdata.com/pricing.
