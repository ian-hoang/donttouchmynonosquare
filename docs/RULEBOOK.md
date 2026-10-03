# PokerFace research rulebook

The rules we hold ourselves to, written before any backtest (2026-10-02, ~23:45 ET). Every rule names how
it is enforced. A rule without enforcement is a wish, so most rules point to code, a test, or a committed
log. If a rule is broken, the note says so.

## A. Pre-registration
- **A1. Hypothesis first.** `HYPOTHESIS.md` (economic mechanism, primary signal, horizon, universe, trade
  rule, kill conditions) is committed before the first strategy backtest touches real returns.
  *Enforced:* git timestamps; the note cites the commit hash.
- **A2. One primary specification.** Exactly one pre-registered primary strategy is reported as the headline.
  Everything else is a labeled robustness check or variant. *Enforced:* `config/strategy.json` is frozen at
  the hypothesis commit; `run_all.py` reads it.
- **A3. No return-fitted primary signal.** Feature signs and weights come from published effect sizes
  (`config/signal_spec.json`), never from our returns. ML models are secondary variants only.
- **A4. Case studies chosen in advance.** Musk (TSLA) and Karp (PLTR) are pre-committed case studies.
  No case study is added after seeing results.

## B. Data integrity
- **B1. Point-in-time timestamps.** Event time = YouTube upload timestamp (UTC, to the second). A re-upload
  can only make an event later, never earlier. Original air dates are used only if provably earlier and
  public. *Enforced:* `events.py`, manifest columns.
- **B2. Survivorship.** The CEO universe is defined by tenure and video availability, not performance.
  Delisted names are not silently dropped; INTC (Gelsinger) and MSTR (Saylor) are in-universe for their
  tenures. The bias is disclosed and bounded in the note.
- **B3. Corporate actions.** Prices are split- and dividend-adjusted (Yahoo adjusted OHLC; Databento raw ×
  Yahoo adjustment factor). Returns are open-to-open. *Enforced:* data download fingerprint.
- **B4. Missing data.** Never fill a gap with data from after it. Events without a valid entry price are
  dropped and counted.
- **B5. Licensing.** Raw market data, raw video/audio, and transcripts are never committed. Committed:
  per-video derived features, manifests (ids, titles, timestamps), LLM labels, results.
- **B6. Curation is blind to returns.** Video curation (rules + LLM agents) sees only metadata, never
  prices or returns. *Enforced:* curation prompts and inputs are committed.

## C. Lookahead
- **C1. Signal lag.** Decision time = upload + 2h processing buffer; entry at the first open strictly after.
- **C2. Baselines use the past only.** CEO baselines use videos strictly earlier than the scored video; the
  signal scale uses tell scores strictly earlier. Betas and vols use sessions strictly before entry.
- **C3. Proof by perturbation.** `tests/test_no_lookahead.py` wrecks all data after t and asserts no signal,
  weight or return before t changes. Runs in `run_all.py` before any number is printed.
- **C4. LLM hindsight.** Any LLM labeling of transcripts uses entity masking (names, companies, products,
  tickers, dates) and is excluded from the primary signal. A leak test (can the model name the speaker?) is
  reported.

## D. Out-of-sample
- **D1. The split.** IS = 2016-01-01..2024-09-30, OOS = 2024-10-01..2026-09-30 (track rule: most recent 2
  years binds). Event membership is by entry date.
- **D2. Sealed.** OOS results are computed only via `run_all.py --unlock-oos`, which appends a timestamp,
  git hash and config hash to `results/oos_log.md`. Run once. Any rerun after a change is logged and
  disclosed as such.
- **D3. No peeking through side doors.** No plotting, printing, or summarizing of OOS-period events'
  returns before D2. Case-ledger rows in the OOS window are not used to choose anything.

## E. Multiple testing
- **E1. Ledger.** Every IS evaluation appends its config hash and Sharpe to `results/variants_log.csv`.
  The note reports the total number of variants tried.
- **E2. Deflated Sharpe.** Headline Sharpe is reported with DSR (Bailey & Lopez de Prado 2014) using the
  ledger's trial count and cross-trial Sharpe variance, and PBO (CSCV) across the variant matrix.
- **E3. Plateaus, not peaks.** Horizons 1/2/3/5/10/21 and neighboring parameters are reported together.
  A result that lives at one parameter value is reported as fragile.

## F. Execution realism
- **F1. Costs.** Every number is net of costs: stock 5 bps per side (half-spread + slippage + fees for
  mega-caps), SPY 1 bp, borrow 30 bps/yr (GC). Calibrated with Databento quoted spreads when available.
  Costs ×2 is always reported.
- **F2. Tradeable entry.** Entry at the regular-session open; no same-bar signal and fill.
- **F3. Capacity.** Square-root impact on each name's ADV; report AUM at which net Sharpe halves and
  participation as % of ADV.

## G. Risk
- **G1. Market neutral.** Every stock leg is hedged with SPY at the ex-ante 252-day beta.
- **G2. Limits.** ≤35% notional per event, ≤50% per name, ≤200% gross; idio-vol sizing (10% per full-size event).
- **G3. Pre-set de-risking.** Drawdown brake (halve exposure beyond a 10% drawdown) is reported as a
  pre-specified overlay with and without.
- **G4. Factor check.** Daily returns regressed on FF5 + momentum (Newey-West); alpha reported with t-stat.

## H. Inference
- **H1. Clustered uncertainty.** Event-level means use date- and CEO-clustered bootstrap CIs; Sharpe uses a
  stationary bootstrap.
- **H2. Placebos.** Same-name random pseudo-event dates (matched count and timing) and within-CEO signal
  permutations give the null distribution of the headline statistic.
- **H3. Concentration.** Results by year, by CEO, and leave-one-CEO-out. A result driven by one CEO or one
  year is reported as such.

## I. Reporting
- **I1. Minimum metrics, IS and OOS separately:** annualized return, vol, Sharpe, max drawdown, turnover,
  equity curve; all net of costs.
- **I2. Failures section.** Every variant that failed and every pipeline problem goes in the note.
- **I3. Honest framing.** We measure behavioral stress and incongruence relative to a person's own baseline.
  We never claim to detect lies. Real cases are described as "statements later contradicted by ...".

## J. Reproducibility
- **J1. One command.** `python run_all.py` reproduces every headline number from committed features plus
  freely downloadable prices, in minutes, without API keys.
- **J2. Determinism.** Fixed frame sampling, pinned model files and versions, seeded bootstraps, cached
  LLM responses. The price download prints a fingerprint so a judge can confirm identical inputs.

## K. Compute and conduct
- **K1. Mac safety.** At most 3 MediaPipe workers; landmarkers recycled every 150 frames (memory leak).
- **K2. HiPerGator policy.** No heavy work on login nodes; all work via Slurm with right-sized requests;
  no idle GPUs; no models from countries of concern on UF systems (ArcFace identity runs on the Mac only).
- **K3. YouTube.** Polite request rates, no credential sharing, public videos only.
- **K4. Sponsors.** A sponsor tool is claimed only where it does real work in the pipeline.
