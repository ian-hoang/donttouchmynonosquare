# PokerFace results (in-sample only; OOS sealed)
Generated 2026-10-03 02:40 | git 070a190 | config 7ed7a3b4554c | prices yfinance (fingerprint dd92ad1a0c4f386b)

Events: {'total': 901, 'IS': 667, 'OOS': 234, 'excluded_near_earnings': 142} | QC: {'videos_in': 1813, 'after_identity_qc': 1596, 'face_ok': 1369, 'voice_ok': 1296, 'text_ok': 1341}

| metric | in-sample | 
|---|---|
| annualized return (net) | 0.25% |
| volatility | 9.53% |
| Sharpe (net) | 0.07 |
| Sharpe (gross) | 0.20 |
| max drawdown | -33.31% |
| Calmar | 0.01 |
| turnover (x/yr) | 34.13 |
| events traded | 661 |

Costs x2 Sharpe (IS): -0.04 | DSR: 0.15 over 23 trials | PSR(>0): 0.59 | bootstrap Sharpe CI: [-0.57, 0.72]
FF5+Mom alpha: 0.27% (t = 0.09), R2 0.01
Event IC (rank, 20d): 0.025 | tercile spread: 0.31% CEO-clustered CI [-0.01589097987569898, 0.022334563623176967] | hit rate 49.93%
Run-up control: beta_S t = 0.62, corr(S, run-up) = -0.08
Volatility mechanism (pred. 6): beta 0.023, CEO-clustered t = 0.48, n = 667
FOLK placebo Sharpe: -0.11 | IC -0.011
Nulls: permutation p = 0.06, random_dates p = 0.17
Capacity (net Sharpe = half gross): $8M

## Robustness (in-sample, all logged as trials)
| variant                         |   sharpe |   ann_return |   max_drawdown |   n_traded |
|:--------------------------------|---------:|-------------:|---------------:|-----------:|
| PRIMARY                         |    0.074 |        0.003 |         -0.333 |        661 |
| costs_x2                        |   -0.036 |       -0.008 |         -0.35  |        661 |
| horizon_1                       |   -0.311 |       -0.007 |         -0.084 |        661 |
| horizon_2                       |   -0.149 |       -0.005 |         -0.148 |        661 |
| horizon_3                       |   -0.271 |       -0.012 |         -0.242 |        661 |
| horizon_5                       |   -0.286 |       -0.017 |         -0.286 |        661 |
| horizon_10                      |   -0.244 |       -0.021 |         -0.33  |        661 |
| horizon_40                      |   -0.12  |       -0.018 |         -0.409 |        661 |
| horizon_60                      |   -0.157 |       -0.022 |         -0.406 |        661 |
| hedge_QQQ                       |    0.217 |        0.017 |         -0.235 |        661 |
| earnings_included               |   -0.019 |       -0.007 |         -0.318 |        770 |
| benchmark_short_every_interview |   -0.523 |       -0.053 |         -0.504 |        661 |
| benchmark_long_every_interview  |    0.283 |        0.023 |         -0.257 |        661 |
| short_only                      |   -0.043 |       -0.007 |         -0.349 |        411 |
| stack_overlap                   |    0.139 |        0.009 |         -0.284 |        661 |
| dd_brake_0.10                   |    0.06  |        0.002 |         -0.242 |        661 |
| no_incongruence                 |    0.02  |       -0.003 |         -0.336 |        661 |
| equal_feature_weights           |   -0.032 |       -0.007 |         -0.318 |        661 |
| face_only                       |    0.1   |        0.005 |         -0.323 |        672 |
| voice_only                      |    0.215 |        0.016 |         -0.19  |        648 |
| text_only                       |   -0.561 |       -0.056 |         -0.457 |        665 |
| leave_out_armstrong             |    0.091 |        0.004 |         -0.333 |        642 |
| leave_out_barra                 |    0.062 |        0.001 |         -0.334 |        622 |
| leave_out_benioff               |    0.096 |        0.005 |         -0.347 |        614 |
| leave_out_cook                  |    0.152 |        0.01  |         -0.32  |        628 |
| leave_out_dimon                 |   -0.064 |       -0.01  |         -0.34  |        577 |
| leave_out_farley                |    0.111 |        0.006 |         -0.333 |        647 |
| leave_out_gelsinger             |   -0.111 |       -0.014 |         -0.372 |        642 |
| leave_out_huang                 |    0.123 |        0.007 |         -0.295 |        637 |
| leave_out_iger                  |    0.057 |        0.001 |         -0.333 |        657 |
| leave_out_jassy                 |    0.112 |        0.006 |         -0.333 |        652 |
| leave_out_karp                  |   -0.08  |       -0.012 |         -0.355 |        633 |
| leave_out_khosrowshahi          |    0.107 |        0.006 |         -0.331 |        634 |
| leave_out_moynihan              |    0.012 |       -0.003 |         -0.356 |        593 |
| leave_out_musk                  |    0.213 |        0.015 |         -0.262 |        629 |
| leave_out_nadella               |    0.132 |        0.008 |         -0.295 |        605 |
| leave_out_pichai                |    0.113 |        0.006 |         -0.298 |        635 |
| leave_out_saylor                |    0.092 |        0.004 |         -0.309 |        619 |
| leave_out_solomon               |    0.122 |        0.007 |         -0.313 |        626 |
| leave_out_su                    |    0.067 |        0.002 |         -0.328 |        640 |
| leave_out_zuckerberg            |    0.058 |        0.001 |         -0.336 |        627 |
| ml_ridge_secondary              |   -0.05  |       -0.008 |         -0.23  |        580 |

## Alpha decay
|   h |   signed_car_bps |      t |     ic |   n |
|----:|-----------------:|-------:|-------:|----:|
|   1 |           -0.065 | -0.007 |  0.004 | 667 |
|   2 |            6.986 |  0.578 |  0.001 | 667 |
|   3 |           -3.342 | -0.239 | -0.001 | 667 |
|   5 |          -10.28  | -0.524 |  0.005 | 667 |
|  10 |          -18.034 | -0.652 | -0.038 | 667 |
|  20 |           17.348 |  0.42  |  0.025 | 667 |
|  40 |           -5.838 | -0.093 | -0.004 | 667 |
|  60 |          -18.213 | -0.225 |  0.025 | 667 |

## Stress windows
| window             | start      | end        |   strategy |     spy |   strategy_max_dd |   days_with_position |
|:-------------------|:-----------|:-----------|-----------:|--------:|------------------:|---------------------:|
| 2018Q4 selloff     | 2018-10-01 | 2018-12-24 |     0.0201 | -0.1875 |           -0.0312 |                   59 |
| COVID crash        | 2020-02-19 | 2020-03-23 |    -0.0844 | -0.3019 |           -0.0958 |                   24 |
| 2022 bear market   | 2022-01-03 | 2022-10-12 |     0.0837 | -0.2583 |           -0.0866 |                  196 |
| SVB crisis         | 2023-03-08 | 2023-03-24 |    -0.0459 |  0.0031 |           -0.0494 |                   13 |
| Aug-2024 vol spike | 2024-07-16 | 2024-08-07 |     0.0579 | -0.0692 |           -0.0124 |                   17 |

## By year (net)
|   Date |   return |
|-------:|---------:|
|   2016 |   0      |
|   2017 |   0.0667 |
|   2018 |   0.0404 |
|   2019 |  -0.1507 |
|   2020 |  -0.1425 |
|   2021 |  -0.0153 |
|   2022 |   0.2337 |
|   2023 |  -0.1253 |
|   2024 |   0.1904 |

## Per CEO
| ceo_id       |   n |     pnl |    hit |
|:-------------|----:|--------:|-------:|
| armstrong    |  19 | -0.0129 | 0.4737 |
| barra        |  39 |  0.0353 | 0.5641 |
| benioff      |  47 | -0.014  | 0.4894 |
| cook         |  33 | -0.054  | 0.4242 |
| dimon        |  84 |  0.087  | 0.5357 |
| farley       |  14 | -0.0165 | 0.5714 |
| gelsinger    |  19 |  0.1435 | 0.6316 |
| huang        |  24 | -0.0051 | 0.4167 |
| iger         |   4 |  0.0349 | 0.5    |
| jassy        |   9 | -0.0151 | 0.4444 |
| karp         |  28 |  0.101  | 0.5    |
| khosrowshahi |  27 | -0.0056 | 0.4444 |
| moynihan     |  68 |  0.0699 | 0.5588 |
| musk         |  32 | -0.0959 | 0.5938 |
| nadella      |  56 | -0.0583 | 0.5179 |
| pichai       |  26 | -0.0245 | 0.5385 |
| saylor       |  42 | -0.0005 | 0.5238 |
| solomon      |  35 | -0.0442 | 0.2857 |
| su           |  21 |  0.0227 | 0.6667 |
| zuckerberg   |  34 |  0.0179 | 0.4412 |