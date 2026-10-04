# Was it the drift or overpriced options? (attribution of the frozen rule's trades)

Black-Scholes, r = 4%, no dividends; Shapley split over the stock move, the change in the call's implied volatility, and 10 sessions of time. Positive = made money for the call seller.

### In-sample 2024-25: 30 trades from 22 companies; comparison: 2499 quiet-company trades on the same 38 dates

Sold-call P&L per $1 of stock over the 10-session hold (mean; t clustered by company).

| | after deal filings | quiet companies, same dates | difference (t) |
|---|---|---|---|
| **Total, net of costs** | +0.64% | -0.42% | +1.10% (+4.2) |
| Stock move | +0.20% | -0.56% | +0.84% (+3.7) |
| Implied volatility change | +0.24% | -0.04% | +0.24% (+2.5) |
| Time decay | +0.48% | +0.42% | +0.05% (+1.2) |
| Residual (unsolvable IVs) | -0.00% | +0.00% | -0.00% (-1.0) |
| Trading costs | -0.28% | -0.24% | -0.03% (-0.6) |

| Implied volatility of the sold call | after deal filings | quiet companies | difference (t) |
|---|---|---|---|
| level on t_pre (before the filing), median | 30.4% | 25.3% | |
| level at entry, median | 29.2% | 25.5% | |
| IV change around the filing (t_pre → entry), vol points, mean | +0.27 | +0.17 | +0.14 (+0.5) |
| IV change over the hold (entry → exit), vol points, mean | -1.14 | +0.22 | -1.14 (-2.6) |

Calls: median strike +6.0% above the stock at entry, median premium 4.77% of the stock price. Unsolvable implied vols among deal trades: 0.

### 2026 (the trades from the one-time out-of-sample run, explained, not re-tested): 15 trades from 11 companies; comparison: 1110 quiet-company trades on the same 18 dates

Sold-call P&L per $1 of stock over the 10-session hold (mean; t clustered by company).

| | after deal filings | quiet companies, same dates | difference (t) |
|---|---|---|---|
| **Total, net of costs** | +0.75% | -0.82% | +1.45% (+2.5) |
| Stock move | +0.57% | -0.79% | +1.20% (+2.1) |
| Implied volatility change | +0.09% | -0.12% | +0.24% (+3.6) |
| Time decay | +0.49% | +0.50% | -0.00% (-0.1) |
| Residual (unsolvable IVs) | +0.00% | -0.00% | +0.00% (+3.0) |
| Trading costs | -0.40% | -0.41% | +0.02% (+0.3) |

| Implied volatility of the sold call | after deal filings | quiet companies | difference (t) |
|---|---|---|---|
| level on t_pre (before the filing), median | 33.4% | 30.2% | |
| level at entry, median | 30.5% | 30.4% | |
| IV change around the filing (t_pre → entry), vol points, mean | -1.14 | +0.10 | -1.19 (-2.1) |
| IV change over the hold (entry → exit), vol points, mean | -0.41 | +0.61 | -1.14 (-3.6) |

Calls: median strike +7.8% above the stock at entry, median premium 5.51% of the stock price. Unsolvable implied vols among deal trades: 0.

