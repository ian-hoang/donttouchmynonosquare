# Devpost submission draft (fill bracketed numbers from results/summary.md after the final run)

**Title:** PokerFace: trading the gap between what CEOs say and how they say it

**Tagline:** Face, voice and words from 1,800+ CEO interviews, scored against each CEO's own baseline, in a pre-registered, market-neutral event strategy.

## Inspiration
CEOs talk to markets constantly: CNBC hits, podcasts, conference fireside chats. Research shows these appearances move prices (Kim & Meschke), that delivery persuades investors independently of content (Hu & Ma, JF), and that executives' voices and words leak concealed bad news (Mayew & Venkatachalam 2012; Larcker & Zakolyukina 2012; Koo et al. 2026). Nobody had turned that into a tradeable, cost-aware, out-of-sample-tested strategy built on open-source tools.

## What it does
For each of 20 mega-cap CEOs we collect their public video interviews, measure facial action proxies (MediaPipe), voice quality (openSMILE eGeMAPS) and language (Loughran–McDonald, Larcker–Zakolyukina categories) from the CEO's own speech only, and compare each interview with the CEO's previous 30. A pre-registered, literature-weighted TELL score drives a beta-hedged long/short position for 20 trading days. Headline: in-sample net Sharpe [x], sealed out-of-sample [y], costs ×2 [z].

## How we built it
- **Corpus:** two rounds of YouTube search, then LLM curation agents that see metadata only (never prices) and keep only genuine unscripted Q&A. 5,531 candidates became 1,833 interviews with exact upload timestamps inside verified CEO tenures.
- **Compute:** UF HiPerGator. Slurm arrays run MediaPipe face + pose on up to 118 CPU workers (regular + burst QOS), and faster-whisper runs on L4/B200 GPUs. YouTube bot-checks datacenter IPs, so a Mac feeder downloads 12-minute windows and the cluster only computes.
- **Identity and speaker attribution:** the CEO is the face that recurs across their interviews (ArcFace consensus), and audio-visual utterance voting decides who is talking.
- **Research discipline:** hypothesis, cue signs and weights, and trading rules committed before any backtest (`6fe0912`); lookahead tests that wreck future data; a sealed 2-year OOS evaluated once; Deflated Sharpe over every logged trial; FOLK-cue placebo; permutation and random-date nulls; costs ×2; capacity via square-root impact.

## Challenges
MediaPipe 1.0 leaks about 2 MB per frame (it crashed our laptop) and needs RGBA on GPU but RGB on CPU. YouTube blocked the cluster's IPs mid-run. Search results skew to recent years, which starved the in-sample period until we added year-specific searches. CEO tenures changed in 2026 (Cook, Iger) and had to be verified against filings.

## Accomplishments
A fully reproducible pipeline from public video to a tested strategy in 36 hours, with every rule written down before the results.

## What we learned
[fill after results: what worked, what failed, which modality carried the signal]

## What's next
Broadcast airtimes for earlier entries, speaker diarization for response latency, earnings-call video across the Russell 1000, and the TELL score as a volatility input for options.

**Built with:** Python, MediaPipe, OpenCV, openSMILE, faster-whisper, InsightFace ArcFace, yt-dlp, pandas, statsmodels, UF HiPerGator (Slurm), Claude Code.
