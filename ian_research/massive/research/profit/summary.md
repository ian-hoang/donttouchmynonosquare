# Profit search results (in-sample 2024-2025; measured costs)

43 categories × 45 cells = 1,935 cells. Cells passing all four rules: **20**.

## Baseline: the same trades on ordinary (quiet) days, net of measured costs

| strategy | h=1 | h=2 | h=3 | h=5 | h=10 | h=21 | h=42 | h=63 | h=exp |
|---|---|---|---|---|---|---|---|---|---|
| long_call | -0.27% | -0.22% | -0.20% | -0.10% | +0.04% | +0.39% | +0.84% | +1.15% | +1.43% |
| covered_call | -0.19% | -0.11% | -0.06% | +0.07% | +0.29% | +0.76% | +1.86% | +2.81% | +3.76% |
| protective_put | -0.16% | -0.08% | -0.02% | +0.13% | +0.39% | +1.00% | +1.93% | +2.51% | +2.14% |
| collar | -0.45% | -0.40% | -0.37% | -0.29% | -0.17% | +0.13% | +0.75% | +1.22% | +1.46% |
| cash_secured_put | -0.23% | -0.19% | -0.17% | -0.13% | -0.06% | +0.10% | +0.48% | +0.91% | +1.29% |

## Categories ranked by the luck check (best cell = highest min(t_net, t_vs_peers))

| category | company-days | best cell | min(t) | luck p | fakes' 95th pct | passing cells |
|---|---|---|---|---|---|---|
| business_update | 54 | covered_call @ exp | +5.80 | 0.00 | +2.67 | 6 |
| quarterly_earnings | 131 | collar @ exp | +2.85 | 0.04 | +2.65 | 0 |
| charter_amendment | 36 | covered_call @ exp | +3.14 | 0.04 | +2.97 | 2 |
| material_charge_or_gain | 29 | collar @ exp | +2.85 | 0.06 | +2.89 | 5 |
| equity_compensation_grant | 33 | protective_put @ 3 | +2.48 | 0.11 | +2.88 | 2 |
| public_offering | 19 | long_call @ exp | +2.25 | 0.13 | +2.79 | 5 |
| combo:debt_offering | 292 | cash_secured_put @ exp | +1.76 | 0.21 | +2.38 | 0 |
| debt_issuance | 277 | cash_secured_put @ exp | +1.60 | 0.24 | +2.30 | 0 |
| share_repurchase_program | 36 | cash_secured_put @ exp | +1.79 | 0.26 | +2.76 | 0 |
| investor_presentation | 149 | covered_call @ 5 | +1.37 | 0.34 | +2.23 | 0 |
| preferred_stock_modification | 20 | collar @ exp | +1.57 | 0.36 | +2.94 | 0 |
| preliminary_results | 25 | covered_call @ 2 | +1.59 | 0.41 | +2.82 | 0 |
| cfo_appointment | 34 | collar @ 21 | +1.28 | 0.44 | +2.54 | 0 |
| class:created | 153 | long_call @ 63 | +1.30 | 0.46 | +2.54 | 0 |
| merger_agreement | 27 | cash_secured_put @ 63 | +1.13 | 0.50 | +2.62 | 0 |
| guarantee_or_letter_of_credit | 42 | protective_put @ 10 | +1.08 | 0.51 | +2.51 | 0 |
| acquisition_consideration_shares | 15 | protective_put @ exp | +1.02 | 0.52 | +2.81 | 0 |
| executive_compensation_change | 174 | covered_call @ 10 | +1.19 | 0.54 | +2.59 | 0 |
| all non-earnings 8-Ks | 1458 | collar @ exp | +0.73 | 0.56 | +1.66 | 0 |
| guidance_issuance_or_update | 60 | collar @ 21 | +1.26 | 0.57 | +2.80 | 0 |
| debt_retirement | 40 | cash_secured_put @ exp | +1.00 | 0.57 | +2.93 | 0 |
| deal_termination | 25 | covered_call @ 2 | +1.09 | 0.63 | +2.94 | 0 |
| credit_facility | 62 | collar @ exp | +1.17 | 0.65 | +2.75 | 0 |
| dividend_declaration | 79 | protective_put @ exp | +1.04 | 0.66 | +2.71 | 0 |
| shareholder_proposal_outcome | 121 | collar @ exp | +1.03 | 0.67 | +2.45 | 0 |
| strategic_initiative | 34 | collar @ 21 | +1.03 | 0.68 | +2.82 | 0 |
| annual_meeting_results | 150 | collar @ exp | +0.98 | 0.71 | +2.47 | 0 |
| acquisition_completion | 24 | covered_call @ 10 | +0.81 | 0.76 | +3.08 | 0 |
| director_departure | 101 | protective_put @ 5 | +0.78 | 0.78 | +2.53 | 0 |
| combo:new_leadership | 49 | collar @ 21 | +0.73 | 0.78 | +2.66 | 0 |
| bylaw_amendment | 47 | protective_put @ 3 | +0.75 | 0.79 | +2.80 | 0 |
| cfo_departure | 31 | covered_call @ 21 | +0.62 | 0.80 | +2.61 | 0 |
| executive_officer_appointment | 105 | cash_secured_put @ 63 | +0.54 | 0.83 | +2.64 | 0 |
| class:resolved | 99 | cash_secured_put @ 21 | +0.53 | 0.85 | +2.66 | 0 |
| director_appointment | 97 | collar @ 21 | +0.59 | 0.85 | +2.54 | 0 |
| combo:leadership_exit | 61 | long_call @ exp | +0.44 | 0.85 | +2.62 | 0 |
| underwriting_agreement | 146 | cash_secured_put @ exp | +0.56 | 0.87 | +2.52 | 0 |
| ceo_departure | 31 | long_call @ exp | +0.46 | 0.88 | +2.86 | 0 |
| settlement_agreement | 24 | protective_put @ 1 | +0.45 | 0.89 | +2.69 | 0 |
| ceo_appointment | 17 | collar @ 42 | +0.31 | 0.92 | +3.02 | 0 |
| executive_officer_departure | 132 | collar @ 63 | +0.13 | 0.95 | +2.63 | 0 |
| acquisition_agreement | 29 | cash_secured_put @ 21 | -0.26 | 0.99 | +3.09 | 0 |
| combo:deal_signed | 53 | cash_secured_put @ 21 | -0.65 | 0.99 | +2.62 | 0 |

## Cells that pass all four rules

| category | strategy | h | n | net per trade (t) | vs peers (t) | 2024 / 2025 vs peers | with 5% haircut: t net / t vs peers |
|---|---|---|---|---|---|---|---|
| business_update | covered_call | exp | 45 | +5.17% (+7.1) | +1.79% (+5.8) | +2.18% / +1.45% | +6.8 / +6.1 |
| business_update | cash_secured_put | 42 | 49 | +0.92% (+4.6) | +0.66% (+4.3) | +0.32% / +0.97% | +4.1 / +4.4 |
| business_update | cash_secured_put | 63 | 45 | +1.58% (+5.7) | +0.77% (+4.0) | +0.83% / +0.72% | +5.2 / +3.8 |
| business_update | covered_call | 63 | 42 | +5.04% (+6.3) | +2.31% (+3.5) | +2.17% / +2.43% | +6.2 / +3.7 |
| charter_amendment | covered_call | exp | 25 | +7.37% (+7.9) | +3.26% (+3.1) | +2.85% / +3.71% | +7.9 / +3.1 |
| equity_compensation_grant | covered_call | 3 | 25 | +0.78% (+2.2) | +0.69% (+2.9) | +0.52% / +0.93% | +1.2 / +2.2 |
| material_charge_or_gain | collar | exp | 26 | +4.08% (+4.3) | +3.06% (+2.8) | +3.56% / +2.26% | +4.1 / +3.1 |
| charter_amendment | collar | exp | 21 | +4.63% (+5.0) | +2.33% (+2.8) | +2.11% / +2.57% | +5.1 / +2.8 |
| equity_compensation_grant | protective_put | 3 | 26 | +0.94% (+2.5) | +0.84% (+2.8) | +0.62% / +1.20% | +1.9 / +2.4 |
| material_charge_or_gain | covered_call | exp | 28 | +7.36% (+7.6) | +4.14% (+2.6) | +4.33% / +3.84% | +7.5 / +2.7 |
| business_update | covered_call | 42 | 44 | +3.64% (+10.2) | +1.14% (+2.5) | +1.78% / +0.61% | +9.4 / +2.5 |
| material_charge_or_gain | covered_call | 63 | 28 | +4.87% (+5.8) | +3.38% (+2.3) | +3.51% / +3.20% | +5.8 / +2.4 |
| business_update | collar | 63 | 40 | +2.58% (+3.7) | +1.44% (+2.3) | +1.42% / +1.45% | +3.4 / +2.6 |
| public_offering | long_call | exp | 18 | +3.99% (+2.9) | +4.12% (+2.3) | +8.27% / +0.80% | +2.8 / +2.3 |
| public_offering | covered_call | exp | 17 | +7.68% (+6.1) | +3.56% (+2.2) | +3.19% / +3.88% | +6.0 / +2.3 |
| material_charge_or_gain | collar | 63 | 27 | +2.59% (+3.4) | +2.20% (+2.2) | +2.82% / +1.20% | +3.4 / +2.6 |
| public_offering | protective_put | exp | 13 | +6.32% (+5.1) | +4.31% (+2.2) | +7.73% / +0.33% | +5.3 / +2.2 |
| public_offering | cash_secured_put | 63 | 16 | +2.16% (+3.1) | +1.81% (+2.1) | +2.53% / +1.09% | +3.1 / +2.3 |
| public_offering | collar | 42 | 16 | +1.74% (+2.1) | +2.02% (+2.0) | +3.48% / +0.89% | +2.1 / +2.3 |
| material_charge_or_gain | cash_secured_put | exp | 26 | +2.59% (+8.5) | +1.51% (+2.0) | +1.09% / +2.18% | +8.7 / +2.2 |

## Most profitable cells in absolute terms (t_net), whatever the reason

| category | strategy | h | n | net per trade (t) | vs peers (t) |
|---|---|---|---|---|---|
| all non-earnings 8-Ks | covered_call | exp | 1168 | +4.30% (+10.4) | +0.23% (+0.5) |
| business_update | covered_call | 42 | 44 | +3.64% (+10.2) | +1.14% (+2.5) |
| all non-earnings 8-Ks | covered_call | 63 | 1159 | +3.08% (+9.0) | +0.14% (+0.4) |
| material_charge_or_gain | cash_secured_put | exp | 26 | +2.59% (+8.5) | +1.51% (+2.0) |
| all non-earnings 8-Ks | covered_call | 42 | 1208 | +1.89% (+8.3) | -0.12% (-0.5) |
| combo:debt_offering | cash_secured_put | exp | 226 | +1.95% (+7.9) | +0.53% (+1.8) |
| charter_amendment | covered_call | exp | 25 | +7.37% (+7.9) | +3.26% (+3.1) |
| material_charge_or_gain | covered_call | exp | 28 | +7.36% (+7.6) | +4.14% (+2.6) |
| debt_issuance | cash_secured_put | exp | 216 | +1.90% (+7.5) | +0.49% (+1.6) |
| preferred_stock_modification | cash_secured_put | 63 | 15 | +1.97% (+7.5) | +0.53% (+0.6) |
| material_charge_or_gain | cash_secured_put | 63 | 27 | +1.75% (+7.3) | +1.32% (+1.9) |
| annual_meeting_results | covered_call | exp | 118 | +5.24% (+7.3) | +0.13% (+0.2) |
