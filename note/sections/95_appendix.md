## Appendix (outside the 5-page limit)
**A1. Robustness (all pre-declared, in-sample, each logged as a trial).**
![Figure A1. In-sample net Sharpe of every pre-declared variant; the primary specification in blue.](robustness.png)
![Figure A2. Signal decay: mean signed beta-hedged CAR by horizon (event level, 95% CI).](alpha_decay.png)
![Figure A3. Null distributions: Sharpe under within-CEO permutation and random event dates; red line = actual.](nulls.png)
**A2. Stress windows** (strategy vs. SPY, in-sample).
{{STRESS_TABLE}}
**A3. Pre-committed case studies.** Tell score per interview against the stock's price relative to SPY. *Illustration, chosen with hindsight, not evidence:* of four ledger cases with interviews in the 180 days before a later-contradicting event, only one stands out. Pat Gelsinger's most stressed interview in our sample (100th percentile of his own history) came on 2024-04-08, three days after he told CNBC Intel expected its foundry business to break even in 2027; INTC fell about 19% beta-hedged over the next 20 sessions, and on 2024-08-01 Intel suspended its dividend. Cook (before the January 2019 revenue warning) and Musk show nothing unusual.
![Figure A4. Alex Karp (PLTR).](case_karp.png)
![Figure A5. Elon Musk (TSLA).](case_musk.png)
**A4. Deviations from the pre-registration.** Every post-registration change, with time and reason, is listed in `docs/DEVIATIONS.md`: corpus round 2 (year-specific search, same curation rules), verified CEO tenure corrections (Cook, Iger), and pipeline fixes made before any in-sample result. None was informed by returns.
**A5. Exploratory (not pre-registered): what CEOs say × how they say it.** LLM agents labeled masked CEO answers as claims, denials, promises and hedges (`data/features/utterance_labels.csv`). Despite masking, agents could identify the speaker in {claims_exploratory_IS.leak_rate_speaker_identifiable|pct} of videos, so these labels could carry hindsight and are kept out of the trading signal. 20-day CAR after interviews with a denial: {claims_exploratory_IS.car_denial|pct2} (n = {claims_exploratory_IS.n_denial|int}); denial + high tell: {claims_exploratory_IS.car_denial_high_tell|pct2} (n = {claims_exploratory_IS.n_denial_high_tell|int}); denial + low tell: {claims_exploratory_IS.car_denial_low_tell|pct2} (n = {claims_exploratory_IS.n_denial_low_tell|int}).
