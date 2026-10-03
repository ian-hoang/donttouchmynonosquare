# Pre-registered follow-up hypotheses (H2, H3)

Written Sat 2026-10-03 ~03:00 ET, **after** the primary hypothesis failed in-sample and out-of-sample
(`results/summary.md`, `results/oos_log.md`) and after the overfitting and walk-forward studies
(`results/overfit_study.json`: best of 192 in-sample variants Sharpe 0.32 vs. 0.66 expected from luck, PBO 86%,
winner −0.87 out-of-sample; `results/walk_forward.json`: walk-forward Sharpe −0.54). Committed **before any data
for the H2 universe is collected**. Nothing in `config/strategy.json` or `config/signal_spec.json` changes.

## H2: the same signal works where attention is lower
**Motivation.** The primary failed on the 20 most-watched CEOs. Limited-attention theory (DellaVigna & Pollet 2009;
Hirshleifer, Lim & Teoh 2009; Engelberg 2008) predicts underreaction to soft information is largest where fewer
investors and analysts are watching. **Prediction.** Applied without any change (frozen `signal_spec.json` v1.0 and
`strategy.json` v1.0) to a new, non-overlapping universe of 20 lower-attention US-listed CEOs (`config/universe_h2.csv`),
the TELL signal predicts 20-session beta-hedged returns with the pre-registered sign.
**Data.** Identical pipeline and curation prompt (round-1 generic + round-2 year-specific searches), identical QC.
Every H2 interview and return is new to us, so the whole 2016-01-01..2026-09-30 period is out-of-sample for this test;
the track's IS/OOS split (OOS 2024-10-01..2026-09-30) is also reported.
**Test statistics (decided now).** Full-period net Sharpe, rank IC of S vs. 20-session CAR, and the top-minus-bottom
tercile spread with a CEO-clustered bootstrap CI. **Supports H2** if IC > 0, the spread is positive with a CI that
excludes zero, and the net Sharpe is positive at 1× and 2× costs. **Fails** otherwise. The pooled 40-CEO result is
secondary. `run_all.py` is run once for H2 with `PF_UNIVERSE=_h2 --unlock-oos` (logged in `results_h2/oos_log.md`).

## H3: post-interview drift (unconditional)
**Origin (disclosed).** In-sample, buying every interviewed stock (SPY-hedged, 20 sessions) had a Sharpe of 0.28,
opposite to the reversal Kim & Meschke report for CNBC. Because the universe is today's famous CEOs, a positive drift
could just be survivorship (these stocks did well on all days). **Test (decided now).** Mean 20-session beta-hedged
CAR after interviews minus the mean CAR of the same names on matched random sessions of the same year (100 draws),
CEO-clustered bootstrap. Evaluated once on (a) the original universe's sealed window 2024-10-01..2026-09-30, where this
signal has never been evaluated, and (b) the full H2 universe. **Supports H3** only if the excess CAR is positive with a
CI excluding zero in both.

## H4: intraday reaction to Musk and Karp videos (1-minute bars)
Registered Sat 2026-10-03 ~03:05 ET, before any minute data is fetched. **Motivation.** TSLA and PLTR are the most
retail-driven names in the universe; if a video's information is absorbed within hours, the daily open-to-open test
cannot see it. **Events.** Every curated Musk (TSLA) and Karp (PLTR) video in `data/manifest/videos.csv` with a valid TELL
signal, split by release type: (a) *YouTube-native* releases (content type podcast_interview, or the uploader is the
original publisher of a fireside/conference video), where upload time is the release time; (b) TV clips, where the
broadcast happened before the upload (reported separately, expected to show nothing). **Trade.** Decision = upload +
30 minutes; enter at the first regular-session minute after decision (or the next open), exit at that session's close.
Hedge with QQQ minute bars at the 252-day daily beta. Costs 2 bps per side on TSLA/PLTR, 0.5 bp on QQQ. Data:
Databento XNAS.ITCH `ohlcv-1m` (from 2018-05), minute windows cached locally and never committed. **Test.** Rank IC of
S versus the hedged entry-to-close return, and the mean signed return with a date-clustered t-statistic, for (a); the
track IS/OOS split is reported. **Supports H4** if IC > 0 and the signed return is positive with t > 2 in (a), net of
costs. Small samples are expected; we report them as they come out.

## H5: the intraday tell, on every other CEO (fresh minute data)
Registered Sat 2026-10-03 ~05:08 ET, after H4 (Musk + Karp) showed a positive rank IC in every subset (0.12 to 0.30)
but no significance (n = 72, t = 0.71), and **before any minute data for the CEOs below is fetched**.
**Events.** Every curated video of the other 39 CEO stints (18 original CEOs excluding Musk and Karp, plus the 21 H2
stints) uploaded on or after 2018-05-02 (Databento XNAS.ITCH start), excluding earnings calls, with a valid TELL signal
from the frozen spec. Both release types pooled (primary); YouTube-native and TV reported separately.
**Trade (identical to H4 except the hedge).** Decision = upload + 30 min; enter at the first regular-session minute
at/after decision (else the next open); exit at that session's close; hedge with **SPY** minute bars at the 252-day
daily beta (the universe is not tech-only); costs **3 bps per side** on the stock and 0.5 bp on SPY.
**Primary test.** Spearman rank IC between S and the hedged entry-to-close return over all events; one-sided p-value
from 2,000 within-CEO permutations of S. **Supports H5** if IC > 0 and p < 0.05. **Trading result reported alongside:**
equal-weight sign(S) per event, net bps per trade, date-clustered t, and an annualized daily-portfolio Sharpe.
Evaluated once. Musk and Karp (H4) are excluded so H5 uses no event seen before.
