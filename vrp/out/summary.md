## HX (prereg marks)

| Block | Conditional (Z>0) | Always short | SPY B&H (raw / minus T-bill) |
|---|---|---|---|
| IS | 0.51 | 0.44 | 1.29 / 0.97 |
| OOS | 0.30 | 0.23 | 1.05 / 0.80 |
| OOS_exApr | 0.49 | 0.79 | 1.21 / 0.90 |

OOS bootstrap 95% CI: cond [-0.79, 1.60], always [-1.03, 1.75], cond−always [-0.74, 0.90]. Placebo p = 0.363 (median random-subset Sharpe 0.22).

| OOS sensitivity | Conditional | Always |
|---|---|---|
| k=0.5 | 0.43 | 0.39 |
| k=0 | 0.57 | 0.54 |
| unhedged | 0.54 | 0.34 |
| drop flagged exits | 0.42 | 0.49 |

| Trades | Block | Set | N | Mean P&L (bp of S0) | Hit rate | Worst (bp) |
|---|---|---|---|---|---|---|
| SPY | IS | cond | 59 | 30.7 | 0.75 | -101 |
| SPY | IS | always | 94 | 20.8 | 0.66 | -101 |
| SPY | OOS | cond | 67 | 7.9 | 0.69 | -493 |
| SPY | OOS | always | 112 | 7.4 | 0.70 | -493 |
| QQQ | IS | cond | 64 | 0.9 | 0.59 | -397 |
| QQQ | IS | always | 92 | 2.3 | 0.62 | -397 |
| QQQ | OOS | cond | 58 | 13.2 | 0.64 | -278 |
| QQQ | OOS | always | 103 | 6.4 | 0.58 | -553 |

Flagged trades (any carried-forward mark): 202 of 401; flagged exits: 194.

## H5 (prereg marks)

| Block | Conditional (Z>0) | Always short | SPY B&H (raw / minus T-bill) |
|---|---|---|---|
| IS | -0.06 | 0.08 | 1.42 / 1.10 |
| OOS | -0.15 | -0.60 | 1.05 / 0.80 |
| OOS_exApr | -0.15 | 0.08 | 1.21 / 0.90 |

OOS bootstrap 95% CI: cond [-1.07, 0.93], always [-1.76, 0.88], cond−always [-0.74, 1.66]. Placebo p = 0.158 (median random-subset Sharpe -0.52).

| OOS sensitivity | Conditional | Always |
|---|---|---|
| k=0.5 | 0.09 | -0.34 |
| k=0 | 0.34 | -0.07 |
| unhedged | -0.27 | -0.24 |
| drop flagged exits | -0.15 | -0.60 |

| Trades | Block | Set | N | Mean P&L (bp of S0) | Hit rate | Worst (bp) |
|---|---|---|---|---|---|---|
| SPY | IS | cond | 59 | 3.0 | 0.54 | -125 |
| SPY | IS | always | 94 | 2.2 | 0.54 | -125 |
| SPY | OOS | cond | 69 | 2.1 | 0.57 | -161 |
| SPY | OOS | always | 115 | -1.5 | 0.57 | -406 |
| QQQ | IS | cond | 64 | -3.8 | 0.50 | -163 |
| QQQ | IS | always | 92 | -1.1 | 0.53 | -163 |
| QQQ | OOS | cond | 60 | -5.5 | 0.65 | -224 |
| QQQ | OOS | always | 106 | -9.3 | 0.58 | -514 |

Flagged trades (any carried-forward mark): 1 of 407; flagged exits: 1.

## HX (fixed marks)

| Block | Conditional (Z>0) | Always short | SPY B&H (raw / minus T-bill) |
|---|---|---|---|
| IS | 0.63 | 0.54 | 1.29 / 0.97 |
| OOS | 0.29 | 0.23 | 1.05 / 0.80 |
| OOS_exApr | 0.49 | 0.80 | 1.21 / 0.90 |

OOS bootstrap 95% CI: cond [-0.80, 1.60], always [-1.04, 1.76], cond−always [-0.75, 0.89]. Placebo p = 0.377 (median random-subset Sharpe 0.22).

| OOS sensitivity | Conditional | Always |
|---|---|---|
| k=0.5 | 0.43 | 0.39 |
| k=0 | 0.56 | 0.55 |
| unhedged | 0.55 | 0.35 |
| drop flagged exits | 0.35 | 0.31 |

| Trades | Block | Set | N | Mean P&L (bp of S0) | Hit rate | Worst (bp) |
|---|---|---|---|---|---|---|
| SPY | IS | cond | 59 | 31.7 | 0.75 | -102 |
| SPY | IS | always | 94 | 21.8 | 0.66 | -102 |
| SPY | OOS | cond | 67 | 7.9 | 0.69 | -512 |
| SPY | OOS | always | 112 | 7.7 | 0.70 | -512 |
| QQQ | IS | cond | 64 | 5.1 | 0.59 | -341 |
| QQQ | IS | always | 92 | 6.1 | 0.62 | -341 |
| QQQ | OOS | cond | 58 | 12.8 | 0.64 | -278 |
| QQQ | OOS | always | 103 | 6.3 | 0.58 | -553 |

Flagged trades (any carried-forward mark): 20 of 401; flagged exits: 15.

## H5 (fixed marks)

| Block | Conditional (Z>0) | Always short | SPY B&H (raw / minus T-bill) |
|---|---|---|---|
| IS | -0.06 | 0.08 | 1.42 / 1.10 |
| OOS | -0.15 | -0.60 | 1.05 / 0.80 |
| OOS_exApr | -0.15 | 0.08 | 1.21 / 0.90 |

OOS bootstrap 95% CI: cond [-1.07, 0.93], always [-1.76, 0.88], cond−always [-0.74, 1.66]. Placebo p = 0.158 (median random-subset Sharpe -0.52).

| OOS sensitivity | Conditional | Always |
|---|---|---|
| k=0.5 | 0.09 | -0.34 |
| k=0 | 0.34 | -0.07 |
| unhedged | -0.27 | -0.24 |
| drop flagged exits | -0.15 | -0.60 |

| Trades | Block | Set | N | Mean P&L (bp of S0) | Hit rate | Worst (bp) |
|---|---|---|---|---|---|---|
| SPY | IS | cond | 59 | 3.0 | 0.54 | -125 |
| SPY | IS | always | 94 | 2.2 | 0.54 | -125 |
| SPY | OOS | cond | 69 | 2.1 | 0.57 | -161 |
| SPY | OOS | always | 115 | -1.5 | 0.57 | -406 |
| QQQ | IS | cond | 64 | -3.8 | 0.50 | -163 |
| QQQ | IS | always | 92 | -1.1 | 0.53 | -163 |
| QQQ | OOS | cond | 60 | -5.5 | 0.65 | -224 |
| QQQ | OOS | always | 106 | -9.3 | 0.58 | -514 |

Flagged trades (any carried-forward mark): 1 of 407; flagged exits: 1.


## Diagnostics

- SPY: IV median 0.15, RV median 0.13, VRP>0 on 0.65 of days; Z defined from 2022-09-02; share of Wednesdays with Z>0: 0.54.
- QQQ: IV median 0.20, RV median 0.19, VRP>0 on 0.61 of days; Z defined from 2022-09-02; share of Wednesdays with Z>0: 0.53.
- Daily rule valid on 2260/2306 underlying-days (2nd/3rd strike used 66 times).
- Leg marks fetched: 9206; invalid call 284, put 271.
