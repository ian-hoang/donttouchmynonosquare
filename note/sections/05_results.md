## 5. Results
| net of costs | in-sample (2016-01 – 2024-09) | out-of-sample (2024-10 – 2026-09) |
|---|---|---|
| events traded | {primary_IS.n_traded|int} | {oos.n_traded|int} |
| annualized return | {primary_IS.ann_return|pct} | {oos.ann_return|pct} |
| volatility | {primary_IS.ann_vol|pct} | {oos.ann_vol|pct} |
| Sharpe (gross / net / costs ×2) | {primary_IS.gross_sharpe} / {primary_IS.sharpe} / {costs_x2_IS.sharpe} | {oos.gross_sharpe} / {oos.sharpe} / {oos.sharpe_costs_x2} |
| max drawdown | {primary_IS.max_drawdown|pct} | {oos.max_drawdown|pct} |
| turnover (× capital / yr) | {primary_IS.turnover_x_per_year|f2} | {oos.turnover_x_per_year|f2} |
| FF5+UMD alpha (NW t) | {primary_IS.ff_alpha_annual|pct} ({primary_IS.ff_alpha_t}) | {oos.ff_alpha_annual|pct} ({oos.ff_alpha_t}) |
| rank IC, S vs 20-day CAR | {event_tests_IS.ic_ic|f3} | {oos.event_tests.ic_ic|f3} |
RESULTS_PARAGRAPH
![Figure 1. Growth of $1: in-sample gross, net and costs ×2, then the sealed out-of-sample period; drawdown below.](equity.png)
**Tests against chance.** Deflated Sharpe {dsr.dsr|f2} over {dsr.n_trials|int} logged trials; PSR(SR>0) {dsr.psr_vs_zero|f2}; bootstrap 95% CI for the in-sample Sharpe [{extra.sharpe_ci_lo}, {extra.sharpe_ci_hi}]. Shuffling S within each CEO beats the actual Sharpe with probability {nulls.permutation.p_ge_actual|f2}; moving every event to a random day of the same year, {nulls.random_dates.p_ge_actual|f2}. **Pre-registered placebo:** the FOLK-cue score earns a Sharpe of {folk_placebo.summary.sharpe} (IC {folk_placebo.event_tests.ic_ic|f3}). **Run-up control:** with the 5-day pre-entry run-up in the regression, S has t = {runup_control.t_s} (corr with run-up {runup_control.corr_s_runup}). **Mechanism (prediction 6):** high TELL and subsequent idiosyncratic volatility, CEO-clustered t = {volatility_mechanism_IS.t_tell_ceo_clustered} (n = {volatility_mechanism_IS.n|int}).
