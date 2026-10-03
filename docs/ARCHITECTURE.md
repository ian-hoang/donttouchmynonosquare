# PokerFace architecture

Two layers, deliberately separated so judges can reproduce the headline numbers in minutes:

1. **Heavy pipeline (`pipeline/`)**: video → per-video feature vector. Hours of compute and needs YouTube
   access. Deterministic: fixed frame sampling, fixed model versions, CPU inference, seeds pinned.
   Its output, `data/features/video_features.csv` (one row per video, derived numbers only, no media and
   no transcripts), is **committed**.
2. **Research layer (`src/pokerface/`, `run_all.py`)**: committed features + freely downloadable prices →
   signal → backtest → statistics → every table and figure in the note. `python run_all.py` reproduces
   the headline numbers in under 5 minutes with no API keys.

## Data contracts

| File | Producer | Committed | Contents |
|---|---|---|---|
| `config/universe.csv` | hand + research | yes | ceo_id, name, ticker, tenure_start, tenure_end, hedge_etf |
| `data/manifest/candidates_raw.csv` | `pipeline/corpus_search.py` | yes | raw YouTube search hits |
| `data/manifest/curation_labels.csv` | agentic layer | yes | per-video LLM curation verdict + rationale |
| `data/manifest/videos.csv` | `pipeline/build_manifest.py` | yes | curated corpus: video_id, ceo_id, ticker, channel, title, duration_s, publish_ts_utc, setting |
| `data/cache/frames/{vid}.parquet` | `pipeline/extract_video.py` | no | per-frame face/pose signals |
| `data/cache/transcripts/{vid}.json` | `pipeline/transcribe.py` | no | words with start/end/speaker |
| `data/features/video_features.csv` | `pipeline/aggregate.py` | **yes** | per-video features + QC columns |
| `data/features/utterance_labels.csv` | `agentic/label_utterances.py` | yes | per-video counts of claim/denial/hedge (masked LLM) |
| `data/market/*.parquet` | `data/download.py` | no (licensed) | daily OHLCV, FF factors, earnings dates |
| `results/` | `run_all.py` | yes | tables (csv/md), figures (png/svg), `variants_log.csv`, `oos_log.md` |

## Time and lookahead rules (enforced in code and tests)
- `publish_ts_utc` = YouTube upload timestamp (or verified original air time if earlier is provable; never later).
- Decision time = publish + 2h processing buffer. Entry = first regular-session **open** strictly after decision
  time. Exit = open H sessions later. P&L marked open-to-open.
- Baseline for CEO c at time t uses only that CEO's videos with publish time < t (expanding, min 5 prior).
- Hedge beta uses 252 trading days strictly before entry.
- `tests/test_no_lookahead.py` perturbs all data after t and asserts signals/positions at t are unchanged.
- Out-of-sample is sealed: `run_all.py` evaluates it only with `--unlock-oos`, which appends to
  `results/oos_log.md` (timestamp + git hash + config hash). Every IS evaluation appends to
  `results/variants_log.csv` (feeds the Deflated Sharpe trial count).

## Module map
```
pipeline/   corpus_search.py  curate.py  build_manifest.py  fetch_media.py  identity.py
            face_pose.py  audio_features.py  transcribe.py  extract_video.py  run_pipeline.py  aggregate.py
agentic/    llm_cache.py  gemini_client.py  curation_agent.py  utterance_agent.py  masking.py
src/pokerface/  data.py  events.py  signal.py  backtest.py  stats.py  capacity.py  report.py
data/download.py   run_all.py   tests/
note/       note.html → note.pdf (headless Chrome)
```
