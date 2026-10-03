# Corpus feasibility: YouTube CEO interview candidates

Run date: 2026-10-02 (23:10 to 23:30 ET). Tool: yt-dlp 2026.08.19 (https://github.com/yt-dlp/yt-dlp), used as a
library in one Python process, with one query at a time. JS challenge runtime: deno 2.9.4. curl_cffi is installed.
Peak RSS was about 105 MB for search and about 190 MB for the metadata fetch. Total network use was under 60 MB
(search pages, about 35 MB of metadata JSON, and 1.8 MB of media).

Outputs
- `data/manifest/candidates_raw.csv`: 4,714 unique video ids with columns
  `video_id,ceo,ticker,query,title,channel,channel_id,duration_s,view_count`.
- Scratch (reproducible): `.scratch/corpus/search.py` (search), `.scratch/corpus/build_candidates.py` (filter, dedupe and
  stats), `.scratch/corpus/meta_parse.py`, `.scratch/corpus/ceo_stats.csv`, `loose_genuine.csv`, `strict_genuine.csv`,
  `meta_sample_summary.csv`, and `hits.jsonl` (all 12,000 raw hits with a 300-character description snippet).

## 1. Search: what was run
- There are 20 CEOs and 10 query templates, each run as `ytsearch60:` with `extract_flat`, for 200 queries. Templates:
  `{n} interview`, `{n} CNBC interview`, `{n} Bloomberg interview`, `{n} full interview`, `{n} podcast`,
  `{n} interview 2017|2019|2021|2023|2025`.
- All 200 queries returned the full 60 hits. There were no errors, no bot checks, and no throttling. Each query
  took 1.4 to 2.5 s, and the full run took about 9 min.
- Funnel: 12,000 raw hits had 7,019 unique ids. 9,238 hits were in the 180 to 7,200 s range, 107 were junk by title,
  and 700 did not mention the CEO's name or company in the title, description snippet or channel. After dedupe by
  id, **4,714 candidates** remain (about 108.8k minutes, median 13.5 min).
  - The dedupe keeps the row whose CEO name is in the title. This settles cross-CEO collisions such as panels.
- **Deviation (flag): I did not apply the "AI" junk word literally.** A case-sensitive `\bAI\b` title filter would drop
  1,348 raw hits and 533 of the kept candidates (11%). Most of these are genuine recent Huang, Nadella, Pichai, Karp
  and Zuckerberg interviews ("Jensen Huang Thinks A.I. Alarmism Has Gone Too Far | The Ezra Klein Show"). I removed
  only AI-generated content markers (`AI voice|AI generated|AI clone|(AI)|deepfake`) plus the other listed junk
  words and a few more (`giveaway`, `parody`, `SNL`, `rules for success`, `best moments`, ...). The regex is in
  `build_candidates.py`.
- **Flat search returns no dates.** `timestamp`, `upload_date` and `release_timestamp` are null in every flat hit (this
  was confirmed in the prior attempt's `.scratch/corpus/test.jsonl` and in this run). Getting dates needs one full
  metadata call per video (section 3).

## 2. Per-CEO counts
- "loose": the name is in the title, the video is at least 300 s long, and the title has no keyword marking it as a
  keynote, earnings call, testimony, hearing, speech, product launch, analysis or body-language video.
- "strict": loose, plus the channel is on a hand-made list of original broadcasters, hosts or company channels.
  The list includes CNBC, Bloomberg*, Yahoo Finance, Fox Business, CBS, WSJ, TED, Stanford GSB, Lex Fridman,
  All-In, Goldman Sachs, Palantir, and others.
- "Strict" is still noisy. In the 20-video top-view sample, about 4 of 20 were not sit-down interviews: an NVIDIA CES
  live keynote, the Salesforce "Agentforce 2.0" launch, an AMD CES promo, and a WSJ product feature.

| CEO | ticker | candidates | loose | strict | channels (loose) | median min (loose) | >=25 genuine in-window 2016-2026? |
|---|---|---|---|---|---|---|---|
| Elon Musk | TSLA | 307 | 243 | 94 | 147 | 32.8 | Yes |
| Jensen Huang | NVDA | 286 | 180 | 80 | 105 | 27.3 | Yes (skews to 2023+) |
| Alex Karp | PLTR | 241 | 195 | 102 | 76 | 19.0 | Yes, but only after PLTR listed (2020-09-30, UNVERIFIED) |
| Mark Zuckerberg | META | 220 | 132 | 47 | 106 | 17.9 | Yes |
| Tim Cook | AAPL | 252 | 170 | 57 | 122 | 15.2 | Yes |
| Satya Nadella | MSFT | 265 | 181 | 83 | 113 | 17.9 | Yes |
| Sundar Pichai | GOOGL | 224 | 137 | 42 | 101 | 14.4 | Yes |
| Andy Jassy | AMZN | 177 | 92 | 47 | 55 | 23.5 | Probably. Pre-2021-07 hits are AWS-CEO era (sample `EHgJMSLrwQc` is 2020) |
| Lisa Su | AMD | 185 | 116 | 48 | 79 | 13.9 | Yes (many hits are CES/Computex keynotes; exclude them) |
| Jamie Dimon | JPM | 263 | 200 | 133 | 89 | 18.8 | Yes (best covered) |
| Brian Armstrong | COIN | 222 | 178 | 66 | 109 | 22.1 | Yes, but only after COIN listed (2021-04-14, UNVERIFIED) |
| Marc Benioff | CRM | 233 | 171 | 94 | 96 | 22.2 | Yes |
| Dara Khosrowshahi | UBER | 221 | 153 | 83 | 69 | 15.0 | Yes, after the UBER IPO (2019-05, UNVERIFIED) |
| Pat Gelsinger | INTC | 225 | 135 | 38 | 82 | 21.8 | **Borderline.** Tenure is 2021-02-15..2024-12-01 only, and many hits are VMware-era or "Former Intel CEO" (sample `BzKKMH2S06Y` is 2025-10) |
| Bob Iger | DIS | 252 | 187 | 63 | 118 | 14.4 | **Borderline.** Tenure 2 starts 2022-11-20; many hits are tenure 1 or the 2019 book tour (usable only for baseline) |
| Mary Barra | GM | 158 | 100 | 45 | 68 | 18.4 | Yes (likely) |
| Jim Farley | F | 210 | 131 | 46 | 80 | 12.7 | Probably. CEO from 2020-10 (UNVERIFIED); many short CNBC clips |
| Michael Saylor | MSTR | 324 | 274 | 43 | 158 | 13.6 | **Risky.** High volume, but mostly crypto podcasts and re-uploads. He was CEO only until about 2022-08 (UNVERIFIED), and MSTR mostly tracks BTC |
| Brian Moynihan | BAC | 225 | 151 | 101 | 56 | 17.2 | Yes |
| David Solomon | GS | 224 | 147 | 73 | 70 | 22.2 | Yes. CEO from 2018-10 (UNVERIFIED). The "David Solomon" DJ channel adds noise |

Reading the table:
- Every CEO has at least 38 strict and at least 92 loose candidates. On raw volume, all 20 plausibly reach 25.
- **No in-window count is verified**, because flat search has no dates. The binding limits are:
  - the tenure and listing windows above;
  - recency skew: in the 20-id sample, 14 of 20 uploads are from 2023-2026 and 3 of 20 from 2016-2019, so the 2016-2019
    baseline will be thin for most CEOs;
  - re-uploads (below).
- About 15 confidently reach 25 or more. Gelsinger, Iger and Saylor need date-verified counts before inclusion.
  Jassy and Farley are probable.
- **Re-uploads are common.** 744 candidate ids (350 groups) share an exact `(ceo, duration_s)` with another id. The
  same interview often appears from CBS Sunday Morning and CBS News, or from CNBC and re-upload channels such as
  "Vampyre Drakul", "DRM News" and "Forbes Breaking News".
  - Dedupe on `(ceo, |dur| <= 3 s)` and then a title or audio check, and keep the earliest `timestamp`.
  - A re-upload carries a later timestamp, so it is safe against lookahead. But it would double-count in the baseline
    and in the events.

## 3. Full-metadata sample (20 ids, one per CEO, highest-view "strict" hit)
Command (one process, sequential, no cookies, no special args):
`python -m yt_dlp --skip-download --dump-json --no-warnings --ignore-errors -a sample_ids.txt`
took 23.8 s for 20 videos, about 1.2 s per video. Per-video results are in `.scratch/corpus/meta_sample_summary.csv`.

| Field | Result |
|---|---|
| `timestamp` (exact UTC epoch, to the second) | **20/20** |
| `upload_date` | 20/20. It equals the UTC date of `timestamp` in 20/20 |
| `release_timestamp` | 2/20 (one live stream, one premiere). For `was_live`, `timestamp` is later than `release_timestamp`, so `timestamp` is the conservative choice |
| English automatic captions (`en` / `en-orig`) | **17/20** |
| Manual English subtitles | 9/20 |
| No captions at all | 3/20: Goldman Sachs 2018 `92LhIvO2FaM`, Goldman Sachs 2020 `EHgJMSLrwQc`, AMD 2020 `6gTrhD81jkk`. A Whisper fallback is required |
| 360p video-only formats | 20/20 have avc1 (format 134). vp9 and av01 are also available |
| Bot-check / "Sign in to confirm" errors | **0**, here and in 200 searches and 3 more calls. `-v` shows `JS Challenge Providers: ... deno` with deno 2.9.4 |

Sample URLs, for example:
- https://www.youtube.com/watch?v=zIwLWfaAg-8 (TED 2017)
- https://www.youtube.com/watch?v=MqgVORcKvXM (Face the Nation 2025)
- https://www.youtube.com/watch?v=l-NVtsOF6qU (CNBC 2025)

Bot-check avoidance. **The default args worked. None of the fallbacks below were needed or tested (UNVERIFIED).**
- Stay sequential and add `--sleep-requests 1 --sleep-interval 2 --max-sleep-interval 6`.
- Keep deno on PATH, and keep yt-dlp current (`yt-dlp -U` / pip).
- If blocked, use `--extractor-args "youtube:player_client=default,tv_simply"`. Use `--cookies-from-browser` only as a
  last resort, and with a throwaway account.
- Practical warning: `--dump-json` is about **1.7 MB per video** (format and caption URL lists). For 4.7k ids that is
  about 8 GB of JSON. Use `--print "%(id)s\t%(timestamp)s\t%(release_timestamp)s\t%(upload_date)s\t%(channel_id)s\t%(language)s"`
  (or `-O`) instead, and keep the caption languages from `automatic_captions` keys in-process.
- Timing for dating every candidate at about 1.2 s per id: strict set (1,385) about 28 min, loose set (3,273) about
  65 min, all candidates (4,714) about 95 min, one process.

## 4. Download test (one video, then deleted)
Video `l-NVtsOF6qU` (CNBC, 506 s), `--download-sections "*120-180"`:
- Video only: `-f "bv*[height=360][vcodec^=avc1]/bv*[height<=360]"` gave format 134, avc1 640x360 at 30 fps.
  **0.856 MB for 60.05 s (114 kb/s)** in 2.2 s wall time.
- Audio only: `-f "ba[ext=m4a]/ba"` gave format 140, AAC 44.1 kHz 129 kb/s. **0.972 MB for 60.0 s** in 2.9 s.
- ffprobe confirmed both durations. Both files were deleted. Section cutting via ffmpeg 8.1 works.

Median bitrates across the 20-video sample (from `tbr` in the metadata), in MB per minute:

| Format | MB/min (median) |
|---|---|
| 134 (360p avc1) | 0.90 |
| 243 (360p vp9) | 1.24 |
| 396 (360p av01) | 0.77 |
| 133 (240p) | 0.44 |
| 140 (m4a 129k) | 0.97 |
| 251 (opus about 118k) | 0.89 |
| 250 (opus about 63k) | 0.47 |
| 249 (opus about 50k) | 0.38 |
| 139 (m4a 49k) | 0.37 |

Budget:
- 134 + 140: about **1.9 MB/min**. 134 + 250: about **1.4 MB/min**. Opus 250 at 48 kHz is ample for F0, jitter and
  shimmer after resampling to 16 kHz.
- Full corpus at 134 + 250: strict (1,385 videos, 31.1k min) about 43 GB; loose (3,273 videos, 89.1k min) about
  122 GB. Stream, process and delete one at a time.
- Sampling 3 windows of 120 s per video costs about 10 MB per video, or about 14 GB for the strict set.
- The 300 MB cap in this task covers only about 3 hours of full-rate media.

## 5. Recommendations
1. Run one sequential `--print` metadata pass over the strict set (about 28 min) to get `timestamp` and channel.
   Then apply the tenure and listing windows and recount per CEO per year before freezing the universe. Gelsinger, Iger
   and Saylor are the ones most likely to drop out.
2. Dedupe re-uploads by duration and title similarity, and prefer the original broadcaster's earliest upload.
3. Exclude keynotes, product launches and CES/Computex events. They are scripted delivery, and the literature cues
   assume spontaneous Q&A.
4. Captions cover about 85%. Use them for the cheap verbal pass, and run mlx-whisper on the rest and wherever word
   timings and diarization matter.
5. Expect the 2016-2019 baseline to be thin. The prior-video "min 5" rule in ARCHITECTURE.md will push the first
   tradable event for many CEOs to 2019-2021.

## Side note for the lead
While I finished up (23:25 ET), a separate process was running that I did not start:
`.venv/bin/python pipeline/fetch_metadata.py --workers 3 --candidates data/manifest/candidates_prefiltered.csv`.
It uses 3 workers, which conflicts with the "one Python process at a time" safety rule. I did not touch it.
