# Literature synthesis: grounding the hypothesis and pre-specifying the tell score

Compiled 2026-10-02 (about 23:30 ET) for PokerFace (GQH 2026, Systematic Trading). The hypothesis and weights in
section D are meant to be **committed before any backtest**. Every weight comes from published effect sizes and
nothing is fitted on our data.

**Sources and verification.** Paper texts were read from `.scratch/deception/` and `.scratch/finlit/`, which hold
the PDF-extracted text of DePaulo et al. 2003, Vrij, Hartwig & Granhag 2019, Levine 2018, Koo/Teoh/Yoo/Zhao 2026,
Hu & Ma, Gorodnichenko/Pham/Talavera 2023, Dzielinski/Wagner/Zeckhauser 2017, Hsu/Lin/Chung 2025,
Talavera/Yin/Zhang 2025, Hobson/Mayew/Peecher/Venkatachalam 2017 and VolTAGE 2020. The other papers were checked
against their published abstracts on the web this session.
- **VERIFIED** means I read the number in the paper text or in the official abstract.
- **UNVERIFIED** means it comes from memory or a secondary summary and should be checked before it goes in the note.
- **PDF sign loss.** The extracted DePaulo text lost its minus signs. I restored the directions from the paper's
  prose, from Levine 2018 Table 2 (which prints the signs), and from Vrij 2019 Table 2.

---

## A. Effect sizes for deception and stress cues (meta-analyses)

**Convention.** d > 0 means liars show more of the cue. "DP03" is DePaulo et al. 2003, *Psych Bull* 129(1):74-118
(https://doi.org/10.1037/0033-2909.129.1.74). It pools 1,338 estimates of 158 cues. Its **median |d| across 88 cues
is 0.10**, and only 2 cues reach |d| ≥ 0.5 (VERIFIED, depaulo.txt l.2309).

**Sporer & Schwandt numbers.** "S&S" stands for Sporer & Schwandt 2006, *Appl Cogn Psych* 20:421-446
(https://onlinelibrary.wiley.com/doi/abs/10.1002/acp.1190; paraverbal), and Sporer & Schwandt 2007, *Psych Pub Pol
Law* 13:1-34 (nonverbal). Their |d| values are taken from Levine 2018 Table 1, *IJoC* 12:2461
(https://ijoc.org/index.php/ijoc/article/download/7838/2374), VERIFIED. The S&S directions come from the S&S 2006
abstract and from secondary summaries of S&S 2007.

### A1. Cues we KEEP (non-zero in at least one meta-analysis and measurable from YouTube video)

| Cue | Dir. in liars | d [95% CI] (DP03) | Other meta | How we measure it (pipeline column) |
|---|---|---|---|---|
| Voice pitch (F0) | higher | +0.21* [0.08, 0.34], k=12. **Motivated senders: +0.59* [0.31, 0.88]; identity-relevant: +0.67*** (DP03 Tables 10-11) | S&S06 +0.18* | openSMILE eGeMAPS F0 semitone mean, within-CEO z (`voc_f0_mean_st`) |
| Vocal tension | more | +0.26* [0.13, 0.39], k=10 (rater impressions) | n/a | Acoustic proxy: mean of z(jitter), z(shimmer) and −z(HNR) (`voc_jitter`, `voc_shimmer_db`, `voc_hnr_db`). The mapping from rated tension to acoustics is an **assumption** |
| Nervous/tense (overall) | more | +0.27* [0.16, 0.38], k=16. Motivated: +0.35* | n/a | Impression only. Not measured directly; the vocal tension and facial items above capture part of it |
| Response latency | longer | +0.02 [−0.06, 0.10], k=32. **Identity-relevant: +0.36** (n.s.) | S&S06 +0.21* | Gap from end of interviewer turn to CEO speech onset, median per interview (`voc_response_latency_s`) |
| Chin raise (AU17) | more | +0.25* [0.12, 0.37], k=4 | n/a | MediaPipe blendshape `mouthShrugLower` (`fc_chin_raise`) |
| Lip press (AU24) | more | +0.16* [0.01, 0.30], k=4 | n/a | Blendshapes `mouthPressLeft/Right` (`fc_lip_press`) |
| Facial pleasantness | less | −0.12* [−0.22, −0.02], k=13 | n/a | Duchenne-weighted smile intensity (`fc_pleasant`) |
| Genuine (Duchenne) smile, when faking positive affect | fewer | −0.70* [−0.97, −0.43], k=2. Feigned smile +0.31, k=2 | n/a | `fc_duchenne_frac`. **k=2, so it is not weighted.** It motivates the incongruence term instead |
| Illustrators (gestures) | fewer | −0.14* [−0.24, −0.04], k=16 | S&S07 \|0.03\| | Wrist motion energy while speaking, only when hands are visible (`fc_gesture_energy`) |
| Hand movements | fewer | 0.00 [−0.08, 0.08], k=29 | S&S07 \|0.38\|* (decrease) | Same column as illustrators. The evidence is mixed, so it gets no separate weight |
| Head nods | fewer | +0.01, k=16 | S&S07 \|0.18\|* (decrease) | Needs nod detection from head-pitch oscillation. **Not in the pipeline yet**, so it is optional |
| Details | fewer | −0.30* [−0.38, −0.21], k=24 | Hauch 2015: fewer sensory-perceptual words | Text proxy: numerals and number words per 100 words (`txt_numbers`). A specificity proxy, imperfect |
| Verbal and vocal uncertainty (impression) | more | +0.30* [0.17, 0.43], k=10 | **Hauch 2015 (computer-coded): liars NOT more uncertain** | **Excluded from the text block** because the computerized meta-analysis is null. Kept implicitly through pitch and tension |
| Verbal immediacy | less | −0.31* [−0.50, −0.13], k=3. Verbal and vocal immediacy impressions −0.55*, k=7 | Hauch 2015: more distancing | First-person singular rate, negative sign (`txt_first_singular`) |
| Word/phrase repetitions | more | +0.21* [0.02, 0.41], k=4 | S&S \|0.17\| | **Not used.** Whisper-family ASR tends to drop repetitions and fillers (UNVERIFIED for mlx-whisper here) |
| Negative statements/complaints | more | +0.21* [0.09, 0.32], k=9 | Hauch 2015: more negative emotion | **Excluded for CEOs.** It conflicts with L&Z, where deceptive CEOs use fewer extreme-negative and anxiety words |
| Pupil dilation | more | +0.39* [0.21, 0.56], k=4 | Zuckerman81 1.49 | **Not measurable** at YouTube resolution |

\* = p<.05 in the source. All DP03 d and CI values are VERIFIED from depaulo.txt Tables 3-11, with signs restored as
explained at the top.

**Linguistic meta-analysis.** Hauch, Blandón-Gitlin, Masip & Sporer 2015, *PSPR* 19(4):307-342
(https://doi.org/10.1177/1088868314556539). It pools 79 cues from 44 studies that used software coding. Relative to
truth-tellers, liars show:
- more cognitive load,
- **more negative emotion**,
- **more distancing**,
- **fewer sensory-perceptual words**,
- fewer cognitive-process words,
- and they are **not more uncertain**.

The overall effects are small and moderated by event type, motivation and interaction (VERIFIED from the abstract).
The individual g values are **UNVERIFIED** because I could not get the full text, so no Hauch weights are used.

**Accuracy and why the cues are weak:**
- **Bond & DePaulo 2006**, *PSPR* 10:214-234. Across 206 documents and 24,483 judges, humans are **54%** accurate
  (47% on lies, 61% on truths). Accuracy is 52% from video only, **63% from audio only** and 56% from audio plus
  video. Experts do no better than laypeople (VERIFIED in Vrij 2019 text, l.581-620, and the abstract via
  https://www.semanticscholar.org/paper/66f48d526f9a31c8360cda3ef251c93c4cbca0f9). **Implication:** speech content
  and voice carry more signal than the face, so the verbal and vocal blocks get the larger total weight.
- **Hartwig & Bond 2011**, *Psych Bull* 137(4):643 (https://eric.ed.gov/?id=EJ930171). This is a lens-model
  meta-analysis of 66 cues in 153 samples. Judges do **not** rely on the wrong cues. Lie detection fails because
  **the cues themselves are weak**. Deception judgments correlate with perceived incompetence (r=.59) and
  ambivalence (r=.49), and with eye contact at only r=−.15 (VERIFIED from the abstract).
- **Hartwig & Bond 2014** (multiple cues, via Vrij 2019 and Levine 2018). Within a single study, a multi-cue model
  reaches R≈.52, but most of that comes from one cue (r=.43). Even with objectively coded cues and statistical
  combination, accuracy is only **67.68%**. **Stakes and motivation did not moderate detectability**, because truth
  tellers become nervous too.
- **Levine 2018 decline effect.** Across DP03 cues, effect size falls as the number of studies k rises, and the
  correlation is negative and significant. **Expect real-world effects at or below the meta-analytic d.** This is
  the main reason not to tune weights on our own data.

**Moderator relevant to CEOs.** In DP03, cues were stronger when senders were motivated. Pitch was +0.59 for
motivated senders against −0.02 with no motivation. Under identity-relevant motivation, response latency was +0.36
and silent pauses +0.38. Under instrumental incentives, **filled pauses (−0.13/−0.14) and non-ah disturbances
(−0.10/−0.17) fell**: motivated liars over-control their speech. This agrees with L&Z's finding that deceptive
CEOs use *fewer* hesitation words. So **disfluency has no reliable sign for media-trained CEOs and is excluded.**

### A2. Folk cues that do NOT replicate, which we EXCLUDE (keep only as a placebo, see D5)

| Folk cue | DP03 d [CI], k | S&S \|d\| | Pipeline column (diagnostic only) |
|---|---|---|---|
| Gaze aversion | +0.03 [−0.11, 0.16], k=6 | n/a | `fc_gaze_aversion` |
| Eye contact | +0.01 [−0.06, 0.08], k=32. Motivated: −0.15* (small) | 0.02 | n/a |
| Blinking | +0.07 [−0.01, 0.14], k=17 | 0.01 | `fc_blink_per_min` |
| Self-fidgeting / self-touch | −0.01 [−0.09, 0.08], k=18 | adaptors 0.04 | `fc_self_touch` |
| Facial fidgeting (face touching) | +0.08 [−0.09, 0.25], k=7 | n/a | `fc_self_touch` |
| Object fidgeting | −0.12, k=5 (n.s.) | n/a | n/a |
| Fidgeting, undifferentiated | +0.16* [0.03, 0.28], k=14. **Heterogeneous** (Q=28.2*), and no specific fidget behavior replicates | n/a | not used |
| Posture shifts | +0.05, k=29 | 0.02 | n/a |
| Head movements (undifferentiated) | −0.02, k=14 | 0.12 | `fc_head_motion` |
| Smiling (undifferentiated) | 0.00 [−0.07, 0.07], k=27 | 0.06 | `fc_smile_frac` |
| Filled pauses ("um") | 0.00 [−0.08, 0.08], k=16. Motivated: −0.13 | 0.08 | `txt_filler` |
| Non-ah speech disturbances | 0.00, k=17 | 0.08 | n/a |
| Silent pauses | +0.01, k=15 | 0.03 | `voc_pause_per_min` |
| Speech rate | +0.07, k=23 | 0.02 | `txt_words_per_min` |
| Response length | −0.03, k=49 | 0.08 | `n_words` |
| Foot/leg movements | −0.09, k=28 | 0.13* | not visible in interviews |

Vrij, Hartwig & Granhag 2019, *Annu Rev Psych* 70:295 (https://doi.org/10.1146/annurev-psych-010418-103135),
Table 2, lists gaze aversion (.03), self-fidgeting (−.01), facial fidgeting (.08) and posture shifts (.05) as cues
people *believe* signal lying but that do not (VERIFIED in vrij2019.txt l.640-680).

---

## B. Larcker & Zakolyukina 2012 and word lists

**Larcker & Zakolyukina 2012**, "Detecting Deceptive Discussions in Conference Calls", *JAR* 50(2):495-540
(https://doi.org/10.1111/j.1475-679X.2012.00450.x; abstract VERIFIED at
https://ideas.repec.org/a/bla/joares/v50y2012i2p495-540.html). Calls are labeled "deceptive" when there is a later
restatement plus severity criteria. Predictors are LIWC-style word categories applied to CEO and CFO Q&A answers.

| Category | CEO sign | CFO sign | Status |
|---|---|---|---|
| References to general knowledge ("you know", "everybody knows") | **+** | **+** | VERIFIED (abstract) |
| Non-extreme positive emotion | **−** | **−** | VERIFIED |
| References to shareholder value | **−** | **−** | VERIFIED |
| Extreme positive emotion ("fantastic", "superb") | **+** | n.s. | VERIFIED (CEO) |
| Anxiety words | **−** | n.s. | VERIFIED (CEO) |
| Self-references (I) | − | n/a | Working-paper version, secondary source. UNVERIFIED in the published version |
| 3rd-person plural and impersonal pronouns | + | n/a | Same as above |
| Extreme negative emotion | − | **+** | WP / secondary. CFO + is reported in several summaries |
| Certainty words, hesitations | − | n/a | WP / secondary |
| Negations, swear words | n.s. | **+** (swearing mainly in SEC-involved cases) | Secondary. UNVERIFIED |

- **Accuracy.** Out-of-sample, the models are **6-16% better than a random guess** and at least as good as models
  built on financial and accounting variables. A portfolio of the firms with the **highest CFO-narrative deception
  scores earns −4% to −11% annualized alpha** (VERIFIED, abstract). The working-paper version reported 4-6% above
  random and 50-65% accuracy (secondary).
- **Full category set (UNVERIFIED, from memory of Table 1).** Word count; I, we, they, ipron; genknlref; assent;
  posemone, posemoextr; negate, anx, anger, swear, negemoextr; certain, tentat, hesit; shvalue, value creation.
- **Exact word lists.** These are in the paper's appendix. The Stanford PDF needs a login (`.scratch/deception/lz.pdf`
  is a login page), so I could not read them. `pipeline/text_features.py` already has approximations (PHRASES and
  WORDS).

**Loughran-McDonald Master Dictionary** (https://sraf.nd.edu/loughranmcdonald-master-dictionary/, VERIFIED):
- CSV: https://drive.google.com/file/d/1iq2RUf8qGFEAk1g8wQntP3habOnR3fXF/view
- Categories: **Negative, Positive, Uncertainty, Litigious, Strong_Modal, Weak_Modal, Constraining**, plus
  Complexity (2024).
- Free for academic research; commercial use needs a license. Cite Loughran & McDonald 2011, *JF* 66(1):35-65.
- Dzielinski/Wagner/Zeckhauser 2017 (https://www.hks.harvard.edu/sites/default/files/centers/mrcbg/files/Zeckhauser_Final_2017-02_v2.pdf)
  use LM **Uncertainty (297 words)** as a vagueness measure and LM **Weak_Modal (27 words)** as "weasel words".
  Markets respond **less and more slowly** to vague managers (VERIFIED in hks.txt). This supports underreaction to
  verbal style.

**Free lists for hedges, certainty and negation:**
- Hedges: LM Weak_Modal plus Uncertainty.
- Certainty: LM Strong_Modal.
- Negation: the closed-class list in `text_features.py` (`no not never none nobody nothing neither nor n't cannot`).
- Emotion: NRC Emotion Lexicon (https://saifmohammad.com/WebPages/NRC-Emotion-Lexicon.htm, free for research;
  UNVERIFIED this session).
- LIWC itself is proprietary, so do not claim LIWC.

---

## C. Finance evidence (magnitudes)

| Paper | Setting | Finding (magnitude) | Status |
|---|---|---|---|
| **Kim & Meschke, "CEO Interviews on CNBC"** (SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2339529; early version https://www.fbv.kit.edu/symposium/9th/papers/Mes.pdf) | 6,937 CNBC CEO interviews | Pre-interview 2-day CAR **+84 bp**, interview day **+79 bp** (about +162 bp over 3 days), then **−108 bp over the next 10 trading days**. The reversal is linked to abnormal interview-day short selling and attention | VERIFIED from abstract summaries; the short-selling attribution should be checked |
| **Koo, Teoh, Yoo & Zhao (June 2026 WP)**, "Detecting Deception in CEO Interviews: modal incongruence" (`.scratch/finlit/siew.txt`) | 2,439 CEO interviews 2010-2023 (CNBC, CNN, WSJ, bank conferences, YouTube podcasts); Imentiv.ai affect over 6 Ekman emotions per modality | Incongruence = mean cosine distance across the text-audio, text-video and audio-video emotion vectors, computed per CEO-speaking block. A 1 SD rise means **10-13% higher probability of a negative earnings surprise**, **+32% restatement probability** and **+27% SEC comment-letter amendment probability**. Elevated under SEC investigation (+28% of an SD), F-score > 2.45 (+35% SD) and residual short interest (1 SD → +13% SD). **Single-channel affect is weaker and less stable.** It is also linked to insider selling and analyst dispersion | VERIFIED (text). **Closest prior work: cite it and state our extension**: open-source features, own-CEO baseline, a tradeable return test with costs, and an OOS seal |
| **Mayew & Venkatachalam 2012**, *JF* 67(1):1-44 (https://doi.org/10.1111/j.1540-6261.2011.01705.x) | Conference-call audio, LVA software | Positive and negative managerial affect predict future unexpected earnings. The market reacts. Analysts' recommendations incorporate positive affect but not negative affect, which is underreaction to negative vocal cues | VERIFIED (abstract). Coefficient magnitudes UNVERIFIED |
| **Hobson, Mayew & Venkatachalam 2012**, *JAR* 50(2):349-392 (https://doi.org/10.1111/j.1475-679X.2011.00433.x) | CEO speech in calls, vocal dissonance markers (LVA) | Positively associated with irregularity restatements. Diagnostic accuracy **11% better than chance**, similar to accounting-only models, and incremental to both accounting and linguistic predictors | VERIFIED (abstract) |
| Hobson, Mayew, Peecher & Venkatachalam 2017 (auditors; `.scratch/deception/duke.txt`) | Experiment on CEO call narratives | Experienced auditors are *less* accurate on fraud firms unless told that **negative affect** is a cue | VERIFIED |
| **Hu & Ma, "Persuading Investors: A Video-Based Study"**, *JF* (`.scratch/finlit/hm.txt`) | 1,139 accelerator pitch videos, 2010-2019 | +1 SD "Pitch Factor" (passion and warmth) gives **+3.0 pp funding probability, or +35.2% on an 8.52% base**. Visual happiness: +1.5 pp. **Among funded startups, positive pitches underperform.** An experiment shows delivery induces **inaccurate beliefs** | VERIFIED. This is the "persuasion moves money and is wrong on average" channel |
| **Gorodnichenko, Pham & Talavera 2023**, *AER* 113(2):548-584 (https://doi.org/10.1257/aer.20220129) | Fed Chair voice tone (positive/negative/neutral) | +1 SD positive voice tone moves the S&P 500 about **+75 bp**, similar to a 1 SD forward-guidance shock. The day-0 effect is weak. **The SPY response builds over about 5 days** to roughly 100 bp per unit, then levels off. It also moves VIX and inflation expectations | VERIFIED (text) |
| **Curti & Kazinnik 2023**, *JME* 139:110-126 (https://ideas.repec.org/a/eee/moneco/v139y2023icp110-126.html) | Facial expressions at FOMC press conferences | Investors react negatively to negative facial expressions after controlling for the verbal content. The search summary gives about −0.53 bp on the S&P 500 per 1 SD of negative emotion in a 3-minute window | Direction VERIFIED (abstract). Exact magnitude UNVERIFIED |
| **Akansu, Cicon, Ferris & Sun 2017**, *J Behav Finance* 18(4):373-389 | Automatic facial emotion recognition on CEO interview video | Anger and disgust are followed by higher next-quarter profitability, happiness by lower. **Fear explains announcement-period returns but is transient** | Direction VERIFIED (secondary). Magnitudes UNVERIFIED |
| **Qin & Yang 2019**, ACL P19-1038 (https://aclanthology.org/P19-1038/) | 572 S&P 500 calls in 2017 (280 firms), text plus audio | Target: log std of daily returns over n ∈ {3, 7, 15, 30} days after the call. **MSE: past volatility 2.99 / 0.83 / 0.42 / 0.23 against MDRM text+audio 1.37 / 0.42 / 0.30 / 0.22.** The gain is large at 3-7 days and **gone by 30 days** | VERIFIED from VolTAGE Table 1 (`.scratch/finlit/voltage.txt`) |
| **VolTAGE** (Sawhney et al. 2020, EMNLP, https://aclanthology.org/2020.emnlp-main.643.pdf); **MAEC** (Li et al. 2020, CIKM) | Same task, graph fusion | MSE3 0.63, MSE30 0.14. Earnings-call audio predicts **volatility** (risk), not direction | VERIFIED (VolTAGE). MAEC details UNVERIFIED |
| Hsu, Lin & Chung 2025 (EFMA; `.scratch/finlit/efma_vocal.txt`) | Taiwanese press briefings, LVA | Vocal uncertainty in Q&A is priced. Reactions are stronger for bad news. **Investors take longer to respond to linguistic tone than to vocal uncertainty**, linked to limits to arbitrage and attention | VERIFIED |
| Talavera, Yin & Zhang 2025 WP (https://repec.cal.bham.ac.uk/pdf/22-11.pdf) | Earnings calls, tough analyst questions | Vocal and verbal "emotional resilience" amplifies the reaction to good news. Analysts use vocal cues on bad news | VERIFIED |
| **DellaVigna & Pollet 2009**, *JF* 64(2):709-749 (https://doi.org/10.1111/j.1540-6261.2009.01447.x) | Friday earnings announcements | **15% lower immediate response, 70% higher delayed response**, 8% lower volume | VERIFIED (abstract) |
| **Hirshleifer, Lim & Teoh 2009**, *JF* 64(5):2289-2325 (https://doi.org/10.1111/j.1540-6261.2009.01501.x) | Same-day announcement load | More competing announcements give a weaker immediate reaction and stronger drift. A distraction strategy earns "substantial alphas" | VERIFIED (qualitative). Magnitudes UNVERIFIED |
| **Engelberg 2008** (SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1107998) | Qualitative earnings text | Soft information predicts returns **at longer horizons** than hard information. Processing frictions cause drift | VERIFIED (abstract) |

**What this literature says about the trade:**
1. **Direction.** Concealment cues predict *bad* outcomes: Koo, L&Z, HMV, and the CFO alpha of −4% to −11%. The
   predictive side is asymmetric (short the high-tell names).
2. **Speed.** Media-driven price pressure reverses within about 10 days (Meschke). Voice effects build over about
   5 days (GPT 2023). Soft information drifts longer (Engelberg, DellaVigna-Pollet). Multimodal call features
   forecast volatility mainly at 3-7 days (Qin & Yang).
3. **Who is on the other side.** Attention-driven buyers persuaded by delivery (Hu & Ma, Meschke), and analysts who
   ignore negative vocal affect (M&V 2012).

---

## D. Recommended pre-specified composite and primary hypothesis

### D1. Normalization (already in ARCHITECTURE.md; restated)

For CEO c, feature k and interview i:

`z_ik = (x_ik − median_{j<i}(x_jk)) / (1.4826 · MAD_{j<i}(x_jk))`

- The median and MAD use the CEO's own earlier interviews only (publish time < t), on an expanding window.
- At least 5 prior interviews are required.
- Winsorize z at ±3.
- Robustness only, not the primary: a CEO × setting baseline (TV / podcast / conference) when ≥ 5 priors exist.

**Missing features.** Renormalize the weights over the features present. Trade only if at least 60% of the total
weight is present. Facial and gesture items need face QC to pass. Gestures need `fc_hands_visible` ≥ 0.5.

### D2. Weights

The rule is mechanical: **w_k ∝ |d_k|**.
- |d| is the mean of the DP03 and S&S |d| values where both exist.
- Cues with sign evidence but no d, which are the L&Z categories, get **|d| = 0.10**, the DP03 median cue effect.

| # | Block | Feature (pipeline col) | Sign s_k | \|d\| used (source) | w_k |
|---|---|---|---|---|---|
| 1 | Vocal | F0 mean (`voc_f0_mean_st`) | + | 0.195 (DP03 0.21, S&S 0.18) | 0.094 |
| 2 | Vocal | Tension = mean(z jitter, z shimmer, −z HNR) | + | 0.26 (DP03 vocal tension) | 0.125 |
| 3 | Vocal | Response latency (`voc_response_latency_s`) | + | 0.115 (DP03 0.02, S&S 0.21) | 0.055 |
| 4 | Face | Chin raise AU17 (`fc_chin_raise`) | + | 0.25 (DP03) | 0.120 |
| 5 | Face | Lip press AU24 (`fc_lip_press`) | + | 0.16 (DP03) | 0.077 |
| 6 | Face | Facial pleasantness (`fc_pleasant`) | − | 0.12 (DP03) | 0.058 |
| 7 | Body | Illustrators (`fc_gesture_energy`) | − | 0.085 (DP03 0.14, S&S 0.03) | 0.041 |
| 8 | Verbal | Detail/specificity (`txt_numbers`) | − | 0.30 (DP03 details) | 0.144 |
| 9 | Verbal | General-knowledge refs (`txt_general_knowledge`) | + | 0.10 (L&Z sign) | 0.048 |
| 10 | Verbal | Shareholder-value refs (`txt_shareholder_value`) | − | 0.10 (L&Z) | 0.048 |
| 11 | Verbal | Extreme positive emotion (`txt_extreme_positive`) | + | 0.10 (L&Z CEO) | 0.048 |
| 12 | Verbal | Anxiety words (`txt_anxiety`) | − | 0.10 (L&Z CEO) | 0.048 |
| 13 | Verbal | Non-extreme positive (`txt_lm_positive` − `txt_extreme_positive`) | − | 0.10 (L&Z) | 0.048 |
| 14 | Verbal | First-person singular (`txt_first_singular`) | − | 0.10 (DP03 immediacy, Hauch distancing, L&Z WP) | 0.048 |

The weights sum to 1.00. The block shares are verbal 43%, vocal 27%, face 25% and body 4%. That ordering fits Bond &
DePaulo's audio-only > audiovisual > video-only accuracy, so I did not adjust it.

`CUE_i = Σ_k w_k · s_k · z_ik`

### D3. Verbal-nonverbal incongruence term

This follows Koo et al. 2026, path channel 1: verbal positivity minus nonverbal positivity. DP03 adds support:
genuine smiles drop (d = −0.70) when people fake positive affect.

- `FNP_i = z(fc_pleasant) − z(fc_brow_down)` (facial net positivity)
- `INC_i = z(txt_lm_net_tone) − FNP_i`, then re-standardized within CEO on the trailing window.
- INC is positive when the words are more upbeat than the face.

The term is signed because the trade is directional. Koo's main measure is unsigned. The unsigned cosine version
can be reported as a robustness row, counted as a variant.

### D4. Final score

`TELL_i = 0.75 · CUE_i + 0.25 · INC_i`

- The 0.25 gives cross-modal incongruence the weight of one "channel" in four: vocal, face/body, verbal and
  cross-modal. Koo et al. find it beats single channels.
- Signal: `S_i = TELL_i / sd(TELL)`, where sd uses an expanding window of past events only.
- Terciles use expanding-window breakpoints from past events only.
- **This is variant #1.** Every other weighting is a logged variant that feeds the DSR trial count.

### D5. Pre-registered placebo (negative control)

`FOLK_i = mean(z fc_gaze_aversion, z fc_blink_per_min, z fc_self_touch, z txt_filler, z fc_head_motion)`

Prediction: FOLK has **no** return predictability (|t| < 2). If FOLK predicts as well as TELL, the signal is
generic arousal or context, not deception-specific. This turns the "debunked folk cues" literature into a
falsification test.

### D6. PRIMARY hypothesis (GQH template)

> **We expect** US mega-cap stocks whose CEO publishes a video interview with a high PokerFace tell score (top
> tercile of the own-baseline-normalized score) **to underperform** a beta-hedged benchmark (SPY or the sector ETF)
> **over the next 20 trading days** (entry at the first open after publish + 2h, exit at the open 20 sessions
> later). **The other side** is attention-driven buyers who trade on the scripted verbal message and on-camera
> persuasion. After CEO TV appearances, prices rise about +79 bp on the day and give back about 108 bp within 10
> days (Kim & Meschke), and persuasive delivery creates inaccurate beliefs (Hu & Ma). Analysts also underweight
> negative vocal affect (Mayew & Venkatachalam 2012). **The edge persists because** involuntary vocal and facial
> leakage of concealed bad news (Koo et al. 2026; Hobson et al. 2012; L&Z 2012) is soft information. It is costly
> to process at scale (Engelberg 2008), it arrives under limited attention (DellaVigna & Pollet 2009; Hirshleifer et
> al. 2009), and it is noisy per event (humans reach 54%), so no single trade is an arbitrage. The bad news comes
> out gradually through guidance and the next earnings report.
>
> **If true we should see:**
> 1. A monotone decline in 20-day beta-hedged CAR from the low to the high TELL tercile in IS, with a negative
>    top-minus-bottom spread.
> 2. More negative next-quarter earnings surprises (SUE) after high-TELL interviews, which is Koo's mechanism.
> 3. A larger effect when interview-day abnormal volume (attention) is high.
> 4. Higher post-interview abnormal realized volatility (H2 below).
> 5. A null FOLK placebo.
>
> **It fails if:**
> - in IS the top-minus-bottom 20-day CAR is ≥ 0, or the calendar-time alpha has t < 1;
> - or the effect disappears after controlling for the pre-interview 5-day run-up, meaning it is just the
>   unconditional Meschke reversal;
> - or the FOLK placebo performs as well as TELL;
> - and in the single OOS evaluation, if the spread has the wrong sign. OOS t is reported, not optimized.

**Why 20 days and not 10 or 60.**
- The fast channel finishes inside about 10 days: the Meschke reversal, voice effects that level off after about 5
  days (GPT 2023), and short-horizon volatility predictability (Qin & Yang).
- The slow channel, revelation of concealed news (L&Z monthly alpha, Koo's next-quarter surprise), runs longer.
- 20 trading days (about one month) captures all of the fast channel and the start of the slow one. It matches L&Z's
  monthly-rebalanced alpha (−4% to −11% per year ≈ −0.3% to −0.9% per month).
- It keeps same-CEO overlap manageable. Rule: a new interview for the same CEO replaces the open position; it does
  not stack.
- **5, 10, 40 and 60 days are reported as a pre-declared plateau check, not as alternatives to pick from.**

**Why direction is primary and volatility secondary.**
- Volatility has the stronger literature: Qin & Yang, VolTAGE and MAEC, plus Koo's link to analyst dispersion.
- But monetizing volatility needs option prices. Equity-only data cannot give an honest net-of-cost P&L, and the
  rubric scores a tradeable strategy.
- So **H2 (pre-registered secondary / mechanism test)**: high TELL predicts higher log(RV[t+1, t+20] / RV[t−60, t−1])
  after controlling for an earnings date inside the window. Use H2 as primary only if option data (OPRA or Massive)
  is actually wired in.

**Honest power check (UNVERIFIED inputs; compute from data).**
- Assume a mega-cap 20-day idiosyncratic sd of about 6-7% and about 150 IS events per tercile.
- Then the SE of the spread is about 0.75%, so the detectable spread at t = 2 is about 1.5% per 20 days.
- Literature magnitudes (Meschke about 1%/10 days unconditional; L&Z about 0.3-0.9%/month) sit **at or below** that
  floor, and Levine's decline effect pushes them lower.
- Frame the note around an unbiased estimate with a CI, a modest net Sharpe (around 0.3-0.7) and mechanism tests,
  not a big t.

---

## E. Statistics formulas (for `src/pokerface/stats.py`)

Standard formulas, written from the original papers (from memory, cross-checked for internal consistency;
UNVERIFIED against the PDFs this session).

**Probabilistic and Deflated Sharpe** (Bailey & López de Prado 2012 *J Risk*; 2014 *JPM* 40(5):94-107,
"The Deflated Sharpe Ratio").

Inputs:
- SR̂: Sharpe ratio per period (not annualized), over T return observations.
- γ̂₃: skewness. γ̂₄: kurtosis (not excess; it equals 3 under normality).

```
PSR(SR*) = Φ( (SR̂ − SR*) · sqrt(T − 1) / sqrt(1 − γ̂₃·SR̂ + ((γ̂₄ − 1)/4)·SR̂²) )
SR₀      = sqrt(V[{SR̂_n}]) · ( (1 − γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e)) ),   γ = 0.5772156649 (Euler-Mascheroni)
DSR      = PSR(SR₀)
```

- N is the number of independent trials, taken from `results/variants_log.csv`.
- V[{SR̂_n}] is the cross-trial variance of per-period SRs. If N is small, use the null sampling variance
  (1 − γ̂₃SR̂ + (γ̂₄−1)/4·SR̂²)/(T−1).
- Report DSR, and MinTRL = 1 + (1 − γ̂₃SR̂ + (γ̂₄−1)/4·SR̂²)·(Φ⁻¹(α)/(SR̂ − SR*))².

**PBO via CSCV** (Bailey, Borwein, López de Prado & Zhu 2017, *J Comput Finance* 20(4)):
1. Build matrix M (T × N): daily returns of the N variants. Split the rows into S even contiguous blocks (S = 16).
2. For each of the C(S, S/2) combinations, J = the union of S/2 blocks (IS) and J̄ = its complement (OOS).
3. n* = argmax_n SR(J)_n. ω̄ = rank of n* within SR(J̄) divided by (N + 1). λ = ln(ω̄ / (1 − ω̄)).
4. **PBO = (1/C)·Σ 1[λ ≤ 0]**.
5. Also report the slope from regressing OOS SR on IS SR (performance degradation) and P[SR_OOS < 0].
6. With N ≤ 5 variants PBO is coarse. Say so.

**Multiple testing** (Harvey, Liu & Zhu 2016, *RFS* 29(1):5-68):
- The hurdle for a newly tested factor is **t > 3.0** (about p < 0.0027).
- Bonferroni: p_i ≤ α/M. Holm: step-down α/(M − i + 1). BHY: FDR with c(M) = Σ 1/j.
- Haircut Sharpe (Harvey & Liu 2015 *JPM*): convert SR to a p-value, adjust it for M tests, and convert back.
- Our primary is a single pre-registered test, so the 1.96 threshold is defensible. Still report whether t > 3.

**Event study with clustered events.**

Abnormal returns (market or sector-ETF model, estimated on [−250, −30] excluding other interview and earnings
days):

`AR_it = R_it − α̂_i − β̂_i R_mt`,  `CAR_i = Σ_{t=τ1}^{τ2} AR_it`,  `L = τ2 − τ1 + 1`

- **Patell standardization.** `SCAR_i = CAR_i / (σ̂_i · sqrt(L · (1 + 1/T_est) + (Σ_τ (R_mτ − R̄_m))² / Σ_est (R_mt − R̄_m)²))`.
  The second term is the forecast-error correction. The simple form is σ̂_i·√L.
- **BMP** (Boehmer, Masumeci & Poulsen 1991 *JFE* 30:253): `t_BMP = sqrt(N) · mean(SCAR) / sd(SCAR)`. Robust to
  event-induced variance.
- **Kolari & Pynnönen 2010** (*RFS* 23(11):3996), adjusted for cross-correlation when event dates cluster:
  `t_KP = t_BMP · sqrt( (1 − r̄) / (1 + (N − 1)·r̄) )`, where r̄ is the mean pairwise correlation of
  estimation-window residuals across events. Mega-caps cluster on days such as Davos and earnings season, so this
  adjustment matters.
- Rank alternative: Kolari & Pynnönen 2011 GRANK.
- **Calendar-time portfolio (recommended headline).** Each day, form the portfolio of all open event positions,
  regress its daily return on MKT, SMB, HML, RMW, CMA and UMD, and report α with a Newey-West t (lags ≥ 20). It
  handles overlap and clustering by construction and *is* the tradeable P&L (Fama 1998; Mitchell & Stafford 2000).
- **Panel regressions** of CAR on TELL plus controls (pre-run-up, earnings in window, venue, log duration):
  two-way clustered SEs by firm and event week (Petersen 2009 *RFS*; Cameron, Gelbach & Miller 2011).
- **Overlapping h-day returns:** Newey-West with h − 1 lags, or a block bootstrap by calendar month.

---

## F. Risks and caveats for the note

1. **Domain transfer.** Lab deception (students, low stakes) is not media-trained CEOs in rehearsed interviews. The
   motivation moderator cuts both ways: DP03 finds stronger cues, Hartwig & Bond 2014 find no stakes effect.
2. **Decline effect** (Levine 2018). True effects are likely below the d values used.
3. **Measurement validity.** Blendshapes are not FACS AUs; `mouthShrugLower` as AU17 is an approximation. Jitter,
   shimmer and HNR are degraded by YouTube Opus/AAC compression and background audio. The within-CEO z only
   partly absorbs channel effects.
4. **Closest prior: Koo et al. 2026.** We must cite it and state the extension (open-source pipeline, own-CEO
   baseline, tradeable test with costs, OOS seal), or risk a novelty or "copying" critique.
5. **Selection.** The case ledger examples are hindsight-selected and partly fall in OOS. Never use them to set
   weights.
6. **Asymmetry.** The evidence is strongest that high tell predicts bad outcomes. The "low tell = long" leg has
   weaker grounding (M&V positive affect, GPT positive tone). Report the short leg alone too.
