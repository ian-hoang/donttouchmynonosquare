# TASKS

> **STATUS UPDATE (Claude, 2026-10-03 01:00 ET).** Much of the table below is stale. Current state:
> - Pre-registration DONE: `HYPOTHESIS.md`, `docs/RULEBOOK.md`, `config/signal_spec.json`, `config/strategy.json` committed in `dc55459` before any real-returns backtest. Post-registration changes: `docs/DEVIATIONS.md`.
> - Decision D1 resolved: multi-CEO (20) primary, with Karp + Musk as pre-committed case studies.
> - Corpus DONE: 2 search rounds, 5,531 candidates labeled by curation agents, 1,833 curated in-tenure interviews (1,382 in-sample / 451 OOS).
> - HiPerGator: Slurm arrays running (`pipeline/hpg/`). YouTube bot-checks the cluster's IPs, so the Mac downloads (`pipeline/feeder.py`) and HPG computes (`stage_a_poll.py`, regular + burst QOS); Whisper large-v3-turbo on L4/B200 GPUs.
> - Research engine DONE: `run_all.py` (lookahead tests gate it; IS report, robustness, nulls, FOLK placebo, DSR, capacity, OOS lock). Note generator: `note/build_note.py`.
> - Remaining: finish processing (~01:45), full IS analysis, one-time OOS, labeling (claims/denials, exploratory), note PDF, Devpost text. GDELT airtimes (1.4) are a nice-to-have robustness item, not on the critical path.


Deadlines (ET, from `docs/GQH_RULES.md`): hacking began Fri Oct 2 7:15 PM. **Devpost + quant note: Sun Oct 4 10:00 AM.
Final code push: Sun Oct 4 11:00 AM.** Plan backwards from those, not from "H0 = now".

Status: `[ ]` todo, `[~]` in progress, `[x]` done, `[!]` blocked. Owner: `Claude`, `Yoan`, `Ojas` (HPG user), `?` unassigned.

## What already exists in the repo (PokerFace, committed before this session)

The repo is a **multi-CEO** design (20 CEOs in `config/universe.csv`, Karp and Saylor among them), not Karp-only.

| Brief item | Repo status |
|---|---|
| Candidate discovery | Done for 20 CEOs: `data/manifest/candidates_raw.csv` (4,939 rows, 465 Karp), `candidates_karp_extra.csv` (101). The search script itself is NOT committed (`.scratch/`). |
| Metadata / timestamps | `pipeline/fetch_metadata.py`: YouTube upload timestamps only. No GDELT, no airtime, no `time_source` / `time_confidence`. |
| Verify (is it Karp?) | No ref-photo check. `pipeline/assemble.py` does ArcFace track clustering plus a per-CEO reference, which replaces `karp_scraper.py verify`. |
| Dedupe | Documented (`(ceo, duration ±3s)` + title check) but not implemented. 744 candidate ids share a duration with another. |
| Curation | `curation_labels_part1.csv`: 697 rows labelled by an LLM, 356 keep. Karp coverage unchecked. |
| Download | `pipeline/run_local.py` pulls a 12-minute window (15s to 735s), runs vision, writes 16 kHz FLAC, deletes the video. Not full-length. |
| Transcription | `pipeline/transcribe.py` (captions, Whisper, Scribe fallback). No diarization, no business-relevance pass. |
| Vocal features | `pipeline/audio_features.py` (openSMILE eGeMAPS). Brief asks for parselmouth/librosa. |
| Face / rPPG / Gemini | MediaPipe blendshapes + pose in `vision.py`. No py-feat, no pyVHR, no Gemini score. |
| Baseline z-scoring | In `assemble.py` / `signal.py` (expanding, min 5 prior). Not verified for Karp. |
| Market data | `data/download.py`: **daily** yfinance prices (Databento optional, daily only), FF factors, EDGAR earnings dates. No minute bars. |
| Event timing, backtest, stats | `src/pokerface/{events,signal,backtest,stats}.py` and `tests/test_no_lookahead.py`: open-to-open, 2h buffer. |
| HiPerGator | `docs/HIPERGATOR.md`, `pipeline/hpg/setup_env.sh`. Allocation `ai-workshop`: 250 NCUs, 5 GPUs, 2 TB shared. The `sbatch` scripts the doc mentions are NOT in the repo. |
| Pre-registration | **Missing.** `HYPOTHESIS.md` and `docs/RULEBOOK.md` are referenced by README/code but do not exist. |
| `run_all.py`, results/, DISCLOSURES.md, demo, note | Missing. |

`karp/karp_scraper.py` (your script, copied in this session) adds the only things the repo lacks: **GDELT TV airtimes**
(true broadcast time, coverage ends ~2024-09-30; CNBC 123, Bloomberg 55, FBC 16 clips) and the
time_source/time_confidence logic. Its YouTube search and verify stages are redundant with the repo.

## Decisions needed from you (these change the plan)

- [ ] **D1. Karp-only or multi-CEO?** The brief says Karp + optional Saylor. The repo and the 3k-video HPG run are multi-CEO. Recommendation: keep the multi-CEO pipeline, but pre-register Karp as the primary subject and the others as a pooled robustness check. One subject alone is weak on sample size.
- [ ] **D2. Primary event time.** Repo uses upload time with a 2h buffer, open-to-open daily returns. Brief wants airtime and minute bars. Daily open-to-open is safer for upload-time error; minute bars only help for GDELT/earnings events with real airtimes.
- [ ] **D3. Prosody stack.** Repo has openSMILE eGeMAPS; brief names parselmouth/librosa. Recommendation: keep eGeMAPS, add three parselmouth features (F0 SD, speech rate, pause fraction) as the pre-registered primary so the hypothesis stays one number.

## Phase 0: Setup and pre-registration (do first, nothing else touches returns until this is committed)

| # | Task | Owner | Status | Notes |
|---|---|---|---|---|
| 0.1 | Write `HYPOTHESIS.md`: primary hypothesis, primary feature, windows, holdout rule, test statistic, kill condition | ? | [ ] | Referenced by `events.py`; must be committed BEFORE any return regression. Commit hash = proof. |
| 0.2 | Write `docs/RULEBOOK.md` (referenced in README) or drop the reference | ? | [ ] | |
| 0.3 | Fix windows and holdout in code config (e.g. 1d, 3d, 5d; last 20% by date) | ? | [ ] | `GQH_RULES`: OOS = last 20% or 2 years, whichever is shorter. |
| 0.4 | `DISCLOSURES.md`: libraries + licences, data sources, AI tools (Claude Code, Claude curation labels), scraping method | ? | [ ] | Start now, update at the end. |
| 0.5 | Verify Databento key; decide if used at all | Yoan | [ ] | Only useful if we go intraday. |
| 0.6 | Confirm HPG login and `ai-workshop` allocation; HPG training done | Ojas | [ ] | Claude cannot see HPG state. |
| 0.7 | Confirm pre-existing-work compliance for commit `c39308a` ("team research harness") | Yoan | [ ] | Rules: everything built during the event. |

## Phase 1: Karp corpus and timestamps (checkpoint: >= ~80 unique timestamped appearances)

| # | Task | Owner | Status | Notes |
|---|---|---|---|---|
| 1.1 | Count current Karp corpus: candidates (284 after prefilter) -> curated keep -> deduped | Claude | [ ] | Check which Karp rows `curation_labels_part1.csv` covers (it has only 697 of 3,717 rows). |
| 1.2 | Finish LLM curation for remaining rows (at least all Karp + Saylor) | Claude | [ ] | Needs your OK on cost/volume. |
| 1.3 | Implement dedupe (duration ±3s, title tokens, keep earliest/official) | Claude | [ ] | Port `_same`/`_priority` from `karp_scraper.py`. |
| 1.4 | Run GDELT pull and join to YouTube clips by show/date to upgrade timestamps | Claude | [~] | GDELT sanity check done: fields and station codes correct. Join logic not written. |
| 1.5 | Add `time_source` / `time_confidence` columns to the manifest | Claude | [ ] | |
| 1.6 | Podcast pubDate / earnings-call times (EDGAR 8-K already in `data/download.py`) | Claude | [ ] | |
| 1.7 | Report counts by year, source type, time_confidence. **GO/NO-GO** on Saylor | Claude | [ ] | |

Known issue found this session: running `karp_scraper.py discover` on this Mac hit YouTube bot checks (1,648 errors) because
it uses the default web client. The repo's fix is `player_client=["mweb"]`. Do not re-run discover; use the repo's
`candidates_raw.csv` and `fetch_metadata.py` instead. The channel-search URL in the scraper also appears not to filter on "karp".

## Phase 2: Media processing (HiPerGator; the 3k-video run)

| # | Task | Owner | Status | Notes |
|---|---|---|---|---|
| 2.1 | Report state of the running HPG job: videos done / failed / queued, GPU hours used | Ojas | [ ] | I cannot see it. Share `squeue`/`sacct` output or the `data/cache` counts. |
| 2.2 | Prioritise Karp and Saylor videos in the queue | Ojas | [ ] | `run_local.py` round-robins CEOs, so Karp fills slowly. |
| 2.3 | Commit the missing `sbatch` files (`extract_array.sbatch`, `whisper_gpu.sbatch`) | Ojas | [ ] | Docs reference them; not in repo. |
| 2.4 | Check how many of the 12-minute windows are business-relevant | Claude | [ ] | Window is fixed at 15s-735s, so it may miss the key segment of long interviews. |
| 2.5 | Diarization (pyannote) or rely on face-talking attribution | ? | [ ] | `assemble.attribute_words` already uses mouth activity; decide if pyannote is worth it. |
| 2.6 | Gemini relevance pass: business-relevant segment + key-moment timestamp | Claude | [ ] | Costs credits; ask first. |

## Phase 3: Features and market data

| # | Task | Owner | Status | Notes |
|---|---|---|---|---|
| 3.1 | Primary prosody features (F0 SD, rate, pause fraction) on Karp speaker turns only | Claude | [ ] | |
| 3.2 | Assemble `data/features/video_features.csv` via `assemble.py` | Claude | [ ] | Committed output, no media. |
| 3.3 | Exploratory: MediaPipe AUs (have), Gemini score, rPPG (pyVHR) | ? | [ ] | rPPG on 360p compressed video is likely junk; drop unless time allows. |
| 3.4 | Karp baseline z-scores (expanding, min 5 prior) | Claude | [ ] | |
| 3.5 | `python data/download.py` for PLTR, QQQ, FF factors, earnings dates | Claude | [ ] | Free, small. |
| 3.6 | Abnormal returns: beta-adjusted vs QQQ over pre-registered windows | Claude | [ ] | `GQH_RULES` also wants factor regression. |

## Phase 4: Analysis

| # | Task | Owner | Status | Notes |
|---|---|---|---|---|
| 4.1 | Primary regression with controls (earnings dummy / EPS surprise); effect size + CI | Claude | [ ] | |
| 4.2 | Placebo: random non-appearance timestamps | Claude | [ ] | |
| 4.3 | Exploratory features with Benjamini-Hochberg, labelled exploratory | Claude | [ ] | |
| 4.4 | Trading rule fixed ex ante; Sharpe, max DD, turnover, costs 0-20 bps and x2, Deflated Sharpe | Claude | [ ] | `variants_log.csv` must count every trial. |
| 4.5 | Risk plan, capacity (% ADV, sqrt impact), parameter plateaus | Claude | [ ] | Rubric criteria 3 and 4. |
| 4.6 | `run_all.py` reproducing headline numbers in < 5 min, no API keys | Claude | [ ] | Cap rule: numbers must match the note. |
| 4.7 | **Unlock holdout once**, log in `results/oos_log.md` | Yoan | [ ] | Last analysis step. |

## Phase 5: Demo (only if Phases 1-4 are on track)

| # | Task | Owner | Status | Notes |
|---|---|---|---|---|
| 5.1 | WebSub listener (ytnoti) on Vultr -> relevance -> features -> signal | ? | [ ] | Cut first if behind. |
| 5.2 | Dashboard: latest appearance, z-scores, signal, equity curve | ? | [ ] | |

## Phase 6: Packaging (finish by Sun 8:00 AM)

| # | Task | Owner | Status | Notes |
|---|---|---|---|---|
| 6.1 | Quant note PDF, <= 5 pages, 11pt+, with limitations and kill conditions | ? | [ ] | `note/` does not exist yet. |
| 6.2 | QuantStats tearsheet vs PLTR buy-and-hold | Claude | [ ] | |
| 6.3 | 3-minute demo video | ? | [ ] | Optional. |
| 6.4 | Final DISCLOSURES.md pass; README reproduction section | Claude | [ ] | |
| 6.5 | Public GitHub repo, media gitignored | Yoan | [ ] | Check `git status` for stray media. |
| 6.6 | Devpost submit by Sun 10:00 AM; final push by 11:00 AM | Yoan | [ ] | |

## Local scratch from this session

- `karp/` holds `karp_scraper.py` (patched: search URL form, case-insensitive official-channel check), a Python 3.12 venv with
  `face_recognition` working, and the aborted `discover.log`. Its `.gitignore` excludes `.venv/`, `data/`, `media/`, `refs/`.
  Delete the folder once GDELT logic is ported into `pipeline/`.
- `ffmpeg` is not installed on this Mac; `run_local.py` needs it.
