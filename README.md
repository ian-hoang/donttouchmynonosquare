# PokerFace: trading the gap between what CEOs say and how they say it

**Gator Quant Hacks 2026 · Systematic Trading track.** We measure facial, vocal and verbal stress in public
CEO interviews, relative to each CEO's own baseline, and test whether it predicts the stock's beta-hedged
return over the next 20 trading days. The hypothesis, signal weights and every trading rule were committed
**before any backtest on real returns** ([`HYPOTHESIS.md`](HYPOTHESIS.md), commit `6fe0912`).

> We do not claim to detect lies. Human lie detection from demeanor is about 54% accurate (Bond & DePaulo
> 2006). We measure behavioral stress and incongruence against a person's own history, using only cues with
> meta-analytic support, and we report whatever the data say.

## Headline results

<!-- RESULTS:START -->
| | In-sample (2016-01 – 2024-09) | Out-of-sample (2024-10 – 2026-09, evaluated once) |
|---|---|---|
| Events traded | 661 | 234 |
| Annualized return (net) | 0.3% | -3.7% |
| Volatility | 9.5% | 10.0% |
| Sharpe, net (gross) | 0.07 (0.20) | -0.33 (-0.17) |
| Sharpe, costs ×2 | -0.04 | -0.47 |
| Max drawdown | -33.3% | -14.2% |
| Turnover (× capital / yr) | 34.13 | 44.81 |

Deflated Sharpe 0.15 over 23 logged trials · FOLK placebo Sharpe -0.11 · config `7ed7a3b4554c` · full report: `results/summary.md`
<!-- RESULTS:END -->

## Reproduce the headline numbers (judges start here)

```bash
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -r requirements.txt
python data/download.py          # prices (Yahoo, adjusted), Fama-French factors, SEC earnings dates (~1 min, free)
python run_all.py                # in-sample report: results/summary.md + figures (~2 min)
python run_all.py --unlock-oos   # the sealed out-of-sample evaluation (already run once; see results/oos_log.md)
```

`run_all.py` runs the lookahead test suite first and refuses to print numbers if it fails. It reads the committed
per-video features (`data/features/video_features.csv`), so judges do not need to re-process video.
`data/market/download_meta.json` holds a fingerprint of the price data so you can confirm you downloaded the
same history we used.

## How it works

```
YouTube search ─► agentic curation ─► exact upload timestamps ─► curated corpus (data/manifest/videos.csv)
      │                (LLM sees metadata only, never prices)
      ▼
HiPerGator Stage A (Slurm array, CPU)              HiPerGator GPU (L4 + B200)
  12-min window ─► MediaPipe face mesh             faster-whisper large-v3-turbo
  (52 blendshapes, head pose) + pose ─► FLAC  ───► word timestamps
      │
      ▼
Mac Stage B: ArcFace identity (the CEO = the face that recurs across their interviews) ─► audio-visual
utterance voting (who is talking) ─► facial cues · openSMILE eGeMAPS voice · LIWC-style + Loughran-McDonald text
      │
      ▼
data/features/video_features.csv ─► baseline z-scores (CEO's own last 30 interviews, strictly earlier)
  ─► TELL score (literature-weighted, frozen) ─► S = −TELL/σ ─► beta-hedged 20-day position ─► run_all.py
```

| Stage | Code |
|---|---|
| Candidate search (2 rounds) | `pipeline/corpus_search.py` |
| Agentic curation | Claude agents over metadata only; labels in `data/manifest/curation_labels*.csv` |
| Upload timestamps | `pipeline/fetch_metadata.py` |
| Corpus rules (tenure, listing, Q&A settings, dedupe) | `pipeline/build_manifest.py` |
| Download + MediaPipe + audio (HiPerGator array) | `pipeline/run_local.py`, `pipeline/vision.py`, `pipeline/hpg/stage_a.sbatch` |
| Transcription (HiPerGator GPU) | `pipeline/hpg/whisper_worker.py`, `pipeline/hpg/whisper_*.sbatch` |
| Identity, speaker attribution, feature assembly | `pipeline/assemble.py`, `pipeline/assemble_all.py` |
| Facial / vocal / verbal features | `pipeline/assemble.py`, `pipeline/audio_features.py`, `pipeline/text_features.py` |
| Signal (baseline z, TELL, S) | `src/pokerface/signal.py`, `config/signal_spec.json` |
| Event timing (upload + 2 h, next open) | `src/pokerface/events.py` |
| Backtest (hedged, idio-vol sized, caps, costs, borrow) | `src/pokerface/backtest.py`, `config/strategy.json` |
| Statistics (Sharpe, DSR, PSR, PBO, bootstrap, FF5+Mom) | `src/pokerface/stats.py` |
| Research pipeline, nulls, robustness, capacity | `src/pokerface/research.py`, `run_all.py` |
| Lookahead proofs | `tests/test_no_lookahead.py` |

## Rules we hold ourselves to

| Track rule | How it is enforced |
|---|---|
| Hypothesis before results | `HYPOTHESIS.md`, `config/*.json` committed in `6fe0912` before any real-returns backtest |
| No lookahead | Signals use only strictly earlier videos; entry is the first open ≥ 2 h after upload; betas and vols use strictly earlier sessions. `tests/test_no_lookahead.py` wrecks all future data and asserts nothing earlier changes, and `run_all.py` refuses to run if it fails |
| Out-of-sample = last 2 years, evaluated once | `config/strategy.json`; `run_all.py --unlock-oos` appends to `results/oos_log.md` and refuses re-tuning without a disclosed `--relock` reason |
| Net of costs, and costs ×2 | 5 bps/side stocks, 1 bp SPY, 30 bps/yr borrow; costs ×2 in every table; Abdi-Ranaldo spread estimates justify the level |
| Disclose number of variants | `results/variants_log.csv` feeds the Deflated Sharpe Ratio |
| Failures reported | Pre-registered kill conditions; FOLK placebo; every robustness run is in `results/robustness.csv` |
| Deviations | `docs/DEVIATIONS.md` |

## Data sources (all cited in the note)

YouTube (public interviews; only derived numbers are committed, never media or transcripts) · Yahoo Finance via
`yfinance` (daily adjusted OHLCV) · Kenneth R. French Data Library (FF5 + momentum) · SEC EDGAR submissions API
(8-K Item 2.02 earnings dates). Never committed: raw market data, video, audio, transcripts, API keys.

## Compute

UF HiPerGator (`ai-workshop` allocation): Slurm CPU arrays for MediaPipe and two GPUs (L4, B200) for Whisper.
The InsightFace ArcFace model runs only on our own machine, not on UF systems, per UF policy on software from
countries of concern.

## Team

Ojasva Mishra, Ian Hoang, Yoan Exposito. AI tools: Claude Code (pipeline, analysis, curation agents),
used under the track's AI policy. Every team member can explain the strategy.
