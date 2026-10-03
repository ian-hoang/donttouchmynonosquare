## Appendix (outside the 5-page limit)
**A1. Robustness (all pre-declared, in-sample, each logged as a trial).**
![Figure A1. In-sample net Sharpe of every pre-declared variant; the primary specification in blue.](robustness.png)
![Figure A2. Signal decay: mean signed beta-hedged CAR by horizon (event level, 95% CI).](alpha_decay.png)
![Figure A3. Null distributions: Sharpe under within-CEO permutation and random event dates; red line = actual.](nulls.png)
**A2. Pre-committed case studies.** Tell score per interview against the stock's price relative to SPY.
![Figure A4. Alex Karp (PLTR).](case_karp.png)
![Figure A5. Elon Musk (TSLA).](case_musk.png)
**A3. Deviations from the pre-registration.** Every post-registration change, with time and reason, is listed in `docs/DEVIATIONS.md`: corpus round 2 (year-specific search, same curation rules), verified CEO tenure corrections (Cook, Iger), and pipeline fixes made before any in-sample result. None was informed by returns.
**A4. Exploratory (not pre-registered): what CEOs say × how they say it.** LLM agents labeled masked CEO answers as claims, denials, promises and hedges (`data/features/utterance_labels.csv`). Despite masking, agents could identify the speaker in {claims_exploratory_IS.leak_rate_speaker_identifiable|pct} of videos, so these labels could carry hindsight and are kept out of the trading signal. 20-day CAR after interviews with a denial: {claims_exploratory_IS.car_denial|pct2} (n = {claims_exploratory_IS.n_denial|int}); denial + high tell: {claims_exploratory_IS.car_denial_high_tell|pct2} (n = {claims_exploratory_IS.n_denial_high_tell|int}); denial + low tell: {claims_exploratory_IS.car_denial_low_tell|pct2} (n = {claims_exploratory_IS.n_denial_low_tell|int}).
