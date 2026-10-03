# Pre-registered hypothesis: PokerFace

Written and committed **before any backtest on real returns** (Fri 2026-10-02, ~23:55 ET). The commit hash of
this file is cited in the quant note. Grounding: `docs/research/literature.md`; rules: `docs/RULEBOOK.md`.
Frozen parameters: `config/signal_spec.json` (v1.0) and `config/strategy.json` (v1.0).

## 1. Economic hypothesis (GQH template)

> We expect **US large-cap stocks** whose CEO publishes an interview with a **high PokerFace tell score**
> (vocal, facial and verbal stress and incongruence relative to that CEO's own past interviews) to
> **underperform a beta-hedged SPY benchmark over the next 20 trading days**, and low-tell interviews to do
> the reverse, because **the other side is attention-driven investors who trade on the scripted verbal
> message and on-camera persuasion**. After CNBC CEO appearances, prices rise about 79 bp on the day and give
> back about 108 bp within 10 days (Kim & Meschke); persuasive delivery moves capital and creates inaccurate
> beliefs (Hu & Ma, JF); analysts underweight negative vocal affect (Mayew & Venkatachalam 2012, JF).
> **The edge persists because** involuntary vocal, facial and verbal leakage of concealed bad news (Koo, Teoh,
> Yoo & Zhao 2026; Hobson, Mayew & Venkatachalam 2012; Larcker & Zakolyukina 2012) is soft information that is
> costly to process at scale (Engelberg 2008), arrives under limited attention (DellaVigna & Pollet 2009;
> Hirshleifer, Lim & Teoh 2009), and is noisy per event (human lie detection is about 54%), so no single trade
> is an arbitrage. The news comes out gradually through guidance and the next earnings report.

We measure **behavioral stress and incongruence relative to a person's own baseline**. We do not claim to
detect lies.

**Edge source:** behavioral bias (underreaction to soft, nonverbal information), with an attention component.

## 2. Primary specification (the only headline result)

| Element | Pre-registered choice |
|---|---|
| Universe | The 20 CEOs in `config/universe.csv`, inside their CEO tenure and after their stock's listing date. Defined by role and video availability, never by returns. |
| Events | Curated videos: `keep = true` with content type TV interview, podcast interview, fireside/conference Q&A, panel, or on-camera earnings-call video. Agents saw only metadata, never prices. |
| Event time | YouTube upload timestamp (UTC). Duplicates (same CEO, publish within 3 days, duration within ±3 s) keep the earliest. Several videos of one CEO with the same entry session are averaged into one event. |
| QC | CEO identity match `id_cos ≥ 0.35`. Face block needs ≥ 1 min of the CEO's face. Gesture needs `fc_hands_visible ≥ 0.5`. Text and voice need ≥ 150 CEO words and ≥ 60 s of CEO speech. Tradeable only with ≥ 5 scorable features across ≥ 2 modalities. |
| Normalization | Robust z vs. the same CEO's previous ≤ 30 videos (strictly earlier), min 5 priors, clipped at ±3. |
| Score | `TELL = weighted mean over modalities {face, voice, text, incongruence}` with equal modality weights. Within a modality, weights ∝ meta-analytic \|d\| and signs from the literature (`config/signal_spec.json`). Folk cues (gaze aversion, blinking, self-touch, head motion, undifferentiated smiling, pauses, fillers, speech rate) are excluded. |
| Signal | `S = −TELL / sd(TELL of all strictly earlier events)` (min 20 priors). Position ∝ clip(S, −2, 2): short high-tell, long low-tell. |
| Entry / exit | Decision = upload + 2 h. Enter at the first regular-session open strictly after; exit at the open **20** sessions later. A new event for the same CEO replaces that CEO's open position (no stacking). |
| Earnings confound | Exclude events whose entry is within ±2 sessions of an 8-K Item 2.02 filing (EDGAR). |
| Sizing & risk | Idio-vol sizing: a full-signal event targets 10% annualized idiosyncratic vol, ≤ 35% notional per event, ≤ 50% per name, ≤ 200% gross. Every leg is hedged with SPY at the 252-day ex-ante beta. |
| Costs | 5 bps per side on stocks, 1 bp on SPY, 30 bps/yr borrow on shorts (25 bps SPY). Costs ×2 is always reported. |
| Samples | IS: entries 2016-01-01..2024-09-30. **OOS (sealed): 2024-10-01..2026-09-30**, evaluated once via `run_all.py --unlock-oos`. |

## 3. Testable predictions (IS first; OOS once)
1. The calendar-time strategy earns a positive net Sharpe with a positive FF5+UMD alpha (Newey-West t reported).
2. 20-day beta-hedged CAR declines monotonically from the low- to the high-TELL tercile, with a negative
   top-minus-bottom spread (date- and CEO-clustered bootstrap CI).
3. Rank IC between S and 20-day CAR is positive.
4. **Pre-registered placebo:** the FOLK score (equal-weight mean of the excluded folk-cue z-scores) has no
   predictive power (|t| < 2). If FOLK predicts as well as TELL, our signal is generic arousal, not concealment.
5. Random pseudo-event dates for the same names, and within-CEO permutations of S, give a null distribution
   that the headline statistic beats.
6. Mechanism (secondary): high TELL predicts higher subsequent realized volatility,
   log(RV[t+1, t+20] / RV[t−60, t−1]).

## 4. Kill conditions
- IS top-minus-bottom 20-day CAR ≥ 0, or calendar-time alpha t < 1.
- The effect disappears after controlling for the 5-day pre-interview run-up (it would just be the
  unconditional Meschke reversal).
- FOLK placebo performs as well as TELL.
- OOS spread has the wrong sign. OOS t is reported, not optimized.

## 5. Pre-declared robustness set (every run is logged in `results/variants_log.csv` and counted for DSR)
Horizons 1, 2, 3, 5, 10, 40, 60 sessions (plateau check, not alternatives); QQQ hedge; earnings windows
included; short-only (high-tell) leg; stack instead of replace; no incongruence term; equal feature weights;
single-modality scores (face, voice, text); drawdown brake on (halve exposure beyond 10% drawdown); costs ×2;
leave-one-CEO-out; by year; a secondary ML variant (walk-forward ridge on the same features, purged by 20 sessions),
which is never promoted to the headline.

## 6. Pre-committed case studies
Elon Musk (TSLA) and Alex Karp (PLTR) tell-score timelines, chosen before any results.
