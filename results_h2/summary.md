# PokerFace results (IS + OOS)
Generated 2026-10-03 04:46 | git 53e352a | config 7ed7a3b4554c | prices yfinance (fingerprint 893be98b0e0c6036)

Events: {'total': 442, 'IS': 300, 'OOS': 142, 'excluded_near_earnings': 96} | QC: {'videos_in': 946, 'after_identity_qc': 827, 'face_ok': 745, 'voice_ok': 706, 'text_ok': 732}

| metric | in-sample | out-of-sample |
|---|---|---|
| annualized return (net) | 0.80% | -9.03% |
| volatility | 7.45% | 9.81% |
| Sharpe (net) | 0.14 | -0.92 |
| Sharpe (gross) | 0.22 | -0.82 |
| max drawdown | -21.51% | -23.66% |
| Calmar | 0.04 | -0.38 |
| turnover (x/yr) | 16.47 | 31.09 |
| events traded | 298 | 142 |

Costs x2 Sharpe (IS): 0.08 | DSR: 0.11 over 23 trials | PSR(>0): 0.66 | bootstrap Sharpe CI: [-0.58, 0.90]
FF5+Mom alpha: 0.55% (t = 0.21), R2 0.02
Event IC (rank, 20d): -0.004 | tercile spread: 0.64% CEO-clustered CI [-0.021463819310478388, 0.03598468377982056] | hit rate 52.00%
Run-up control: beta_S t = -0.31, corr(S, run-up) = 0.03
Volatility mechanism (pred. 6): beta 0.038, CEO-clustered t = 0.69, n = 300
FOLK placebo Sharpe: 0.33 | IC 0.039
Nulls: permutation p = 0.28, random_dates p = 0.26
Capacity (net Sharpe = half gross): $25M

## Robustness (in-sample, all logged as trials)
| variant                         |   sharpe |   ann_return |   max_drawdown |   n_traded |
|:--------------------------------|---------:|-------------:|---------------:|-----------:|
| PRIMARY                         |    0.144 |        0.008 |         -0.215 |        298 |
| costs_x2                        |    0.081 |        0.003 |         -0.225 |        298 |
| horizon_1                       |   -0.891 |       -0.013 |         -0.117 |        298 |
| horizon_2                       |   -0.472 |       -0.01  |         -0.101 |        298 |
| horizon_3                       |   -0.398 |       -0.01  |         -0.099 |        298 |
| horizon_5                       |   -0.212 |       -0.007 |         -0.102 |        298 |
| horizon_10                      |    0.103 |        0.004 |         -0.095 |        298 |
| horizon_40                      |    0.031 |       -0.002 |         -0.295 |        298 |
| horizon_60                      |   -0.083 |       -0.015 |         -0.322 |        298 |
| hedge_QQQ                       |    0.27  |        0.018 |         -0.24  |        298 |
| earnings_included               |    0.393 |        0.03  |         -0.155 |        359 |
| benchmark_short_every_interview |    0.087 |        0.004 |         -0.223 |        298 |
| benchmark_long_every_interview  |   -0.251 |       -0.021 |         -0.316 |        298 |
| short_only                      |    0.145 |        0.008 |         -0.183 |        194 |
| stack_overlap                   |    0.029 |       -0.001 |         -0.197 |        298 |
| dd_brake_0.10                   |    0.053 |        0.001 |         -0.184 |        298 |
| no_incongruence                 |    0.181 |        0.011 |         -0.207 |        298 |
| equal_feature_weights           |    0.009 |       -0.002 |         -0.249 |        298 |
| face_only                       |    0.052 |        0.001 |         -0.172 |        303 |
| voice_only                      |    0.03  |       -0     |         -0.212 |        293 |
| text_only                       |    0.053 |        0.001 |         -0.207 |        298 |
| leave_out_arora                 |    0.164 |        0.009 |         -0.212 |        286 |
| leave_out_bancel                |    0.229 |        0.014 |         -0.195 |        280 |
| leave_out_bastian               |    0.122 |        0.006 |         -0.185 |        268 |
| leave_out_baszucki              |    0.144 |        0.008 |         -0.215 |        298 |
| leave_out_chesky                |    0.146 |        0.008 |         -0.185 |        272 |
| leave_out_dell                  |    0.176 |        0.01  |         -0.181 |        280 |
| leave_out_ek                    |    0.213 |        0.013 |         -0.189 |        291 |
| leave_out_fink                  |    0.194 |        0.011 |         -0.231 |        253 |
| leave_out_green                 |    0.182 |        0.011 |         -0.223 |        292 |
| leave_out_kurtz                 |   -0.018 |       -0.004 |         -0.227 |        286 |
| leave_out_lawson                |    0.177 |        0.01  |         -0.191 |        283 |
| leave_out_mcdermott             |    0.11  |        0.005 |         -0.215 |        290 |
| leave_out_narayen               |    0.229 |        0.014 |         -0.223 |        283 |
| leave_out_niccol_cmg            |    0.245 |        0.015 |         -0.173 |        294 |
| leave_out_niccol_sbux           |    0.144 |        0.008 |         -0.215 |        298 |
| leave_out_prince                |    0.111 |        0.005 |         -0.224 |        287 |
| leave_out_robbins               |   -0.024 |       -0.004 |         -0.23  |        272 |
| leave_out_schulman              |   -0.01  |       -0.003 |         -0.262 |        284 |
| leave_out_spiegel               |    0.079 |        0.003 |         -0.214 |        280 |
| leave_out_tenev                 |    0.112 |        0.006 |         -0.201 |        290 |
| leave_out_xu                    |    0.124 |        0.006 |         -0.215 |        293 |
| ml_ridge_secondary              |   -0.208 |       -0.013 |         -0.172 |        220 |

## Alpha decay
|   h |   signed_car_bps |      t |     ic |   n |
|----:|-----------------:|-------:|-------:|----:|
|   1 |          -27.258 | -2.047 | -0.061 | 300 |
|   2 |          -24.093 | -1.374 | -0.027 | 300 |
|   3 |          -43.199 | -1.978 | -0.059 | 300 |
|   5 |          -35.123 | -1.104 | -0.054 | 300 |
|  10 |           20.728 |  0.455 | -0.012 | 300 |
|  20 |           46.776 |  0.7   | -0.004 | 300 |
|  40 |           15.476 |  0.171 | -0.027 | 300 |
|  60 |           39.24  |  0.34  | -0.01  | 300 |

## Stress windows
| window             | start      | end        |   strategy |     spy |   strategy_max_dd |   days_with_position |
|:-------------------|:-----------|:-----------|-----------:|--------:|------------------:|---------------------:|
| 2018Q4 selloff     | 2018-10-01 | 2018-12-24 |    -0.0125 | -0.1875 |           -0.0259 |                   41 |
| COVID crash        | 2020-02-19 | 2020-03-23 |     0.0141 | -0.3019 |           -0.0153 |                   18 |
| 2022 bear market   | 2022-01-03 | 2022-10-12 |    -0.149  | -0.2583 |           -0.1558 |                  196 |
| SVB crisis         | 2023-03-08 | 2023-03-24 |     0.0071 |  0.0031 |           -0.008  |                   13 |
| Aug-2024 vol spike | 2024-07-16 | 2024-08-07 |    -0.0021 | -0.0692 |           -0.0115 |                   17 |

## By year (net)
|   Date |   return |
|-------:|---------:|
|   2016 |   0      |
|   2017 |   0      |
|   2018 |   0.0031 |
|   2019 |  -0.0089 |
|   2020 |   0.0799 |
|   2021 |   0.007  |
|   2022 |  -0.064  |
|   2023 |   0.1916 |
|   2024 |  -0.1112 |

## Per CEO
| ceo_id     |   n |     pnl |    hit |
|:-----------|----:|--------:|-------:|
| arora      |  12 | -0.0106 | 0.25   |
| bancel     |  18 | -0.0518 | 0.5    |
| bastian    |  30 |  0.0059 | 0.5    |
| chesky     |  26 | -0.0051 | 0.5385 |
| dell       |  18 | -0.0148 | 0.5    |
| ek         |   7 | -0.0416 | 0.4286 |
| fink       |  45 | -0.0409 | 0.4889 |
| green      |   6 | -0.0226 | 0.3333 |
| kurtz      |  12 |  0.1045 | 0.4167 |
| lawson     |  15 | -0.0209 | 0.4    |
| mcdermott  |   8 |  0.0249 | 0.875  |
| narayen    |  15 | -0.0517 | 0.5333 |
| niccol_cmg |   4 | -0.0751 | 0.25   |
| prince     |  11 |  0.0236 | 0.3636 |
| robbins    |  26 |  0.1251 | 0.5769 |
| schulman   |  14 |  0.0971 | 0.5    |
| spiegel    |  18 |  0.0452 | 0.6111 |
| tenev      |   8 |  0.0227 | 0.625  |
| xu         |   5 |  0.0157 | 1      |