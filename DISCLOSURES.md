# Disclosures

## Data sources
| Source | Use | Terms / what we commit |
|---|---|---|
| YouTube (public interview videos) | Faces, voices and words of CEOs; upload timestamps | Accessed with `yt-dlp` for research; only 12-minute analysis windows are processed, then deleted. We commit derived per-video numbers, video ids, titles and timestamps, never media or transcripts |
| Yahoo Finance via `yfinance` | Daily split- and dividend-adjusted OHLCV | Downloaded by `data/download.py`; never committed. A hash of the open-to-open returns is committed so others can verify they have the same data |
| Kenneth R. French Data Library | Daily FF5 and momentum factors | Public; downloaded by `data/download.py` |
| SEC EDGAR submissions API | 8-K Item 2.02 filing dates (earnings-window exclusion) | Public; downloaded by `data/download.py` with a contact User-Agent |
| Loughran-McDonald dictionary (as bundled in `pysentiment2`) | Finance sentiment word lists | Free for academic research |

## Models and libraries
MediaPipe Face Landmarker and Pose Landmarker (Google, Apache-2.0) · openSMILE eGeMAPSv02 (audEERING; research
license) · faster-whisper / Whisper large-v3-turbo (SYSTRAN, MIT; OpenAI weights, MIT) · InsightFace buffalo_sc
MobileFaceNet ArcFace (non-commercial research license; run only on our own machine, not on UF systems) ·
numpy, pandas, scipy, statsmodels, matplotlib, pyarrow (BSD-style) · yt-dlp (Unlicense) · FFmpeg (LGPL/GPL static
build on HiPerGator).

## Compute
UF Research Computing HiPerGator, `ai-workshop` allocation provided by the organizers (regular and burst QOS, two
GPUs). All jobs ran through Slurm; nothing heavy ran on login nodes.

## AI tools
Claude Code (Anthropic) wrote and ran most of the pipeline and analysis code under team direction, and its
sub-agents labeled video metadata for curation (metadata only, never prices) and masked transcripts for the
secondary claims/denials analysis. Every label file is committed. The team reviewed the methodology and can
explain every component.

## Pre-existing work
Everything in this repository was written during the event (after Fri Oct 2, 7:15 PM ET). Commit `c39308a`
(a generic team harness) was replaced and kept only in history.

## Wording
The project measures behavioral stress and incongruence relative to a speaker's own baseline. It does not claim
to detect lies, and case studies use neutral language ("statement later contradicted by ...").
