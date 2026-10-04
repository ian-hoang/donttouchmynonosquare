# <Strategy title>

**Team:** <names> · **Gator Quant Hacks 2026, Systematic Trading** · **Repo:** <public GitHub link>

> Limit: **5 pages** including figures and tables, **11pt or larger**, standard margins. References and an
> optional appendix don't count, but judges don't have to read the appendix: anything that matters goes
> in the 5 pages. Every number comes from `results/<strategy>/summary.md`, so the note matches the code.

## 1. Summary (~0.25 page)
What the strategy does, the edge in one sentence, headline out-of-sample Sharpe net of costs, and the
honest verdict (including if it's weak).

## 2. Economic hypothesis (~0.5 page) · *Economic Foundation*
- The sentence from `hypotheses/<strategy>.md` and **when it was committed** (summary: "Hypothesis timing").
- Who is on the other side, why they keep losing, why it isn't arbitraged away.
- What would make it fail. Cite related research and **say what's new** (*Innovation*).

## 3. Data and universe (~0.5 page)
- Sources: Databento dataset, schema, symbols, dates (cite every source).
- Bar construction (UTC-day `ohlcv-1d` vs. session bars), roll handling, splits/dividends.
- Data problems found and how they were handled (summary: "Data checks").
- In-sample / out-of-sample dates and the 20%-or-2-years rule.

## 4. Methodology (~1 page)
- Signal, timing (decided at row end, traded next row), position sizing.
- Cost assumption in bps per side **and where the number comes from** (`gd.futures_cost_bps`).
- Number of variants tried, in total across the team (summary: "Variants tried") and the Deflated Sharpe.

## 5. Results (~1.25 pages) · *Performance & Analytical Evidence*
At minimum, **in-sample and out-of-sample separately, net of costs**: annualized return, volatility, Sharpe,
max drawdown, turnover, and the equity curve (summary: "Performance", `equity_curve.png`). Also:
- Costs x2 (does the edge survive?), returns by year (`by_year.png`), parameter plateau (`plateau_*.png`).
- Lookahead check result. What didn't work, and why.

## 6. Risk management (~0.5 page) · *Risk Management Plan*
- Limits: per position, gross and net exposure (summary: "Exposure"); the overlays used (`gqh/risk.py`).
- De-risking rules set in advance (e.g. drawdown brake), worst day/month, drawdown length.
- Factor exposure: is it just beta/momentum/value? (summary: "Factor exposure"). Tail and regime behaviour.

## 7. Liquidity and capacity (~0.5 page) · *Liquidity & Capital*
- Participation as % of ADV, cost per trade at your AUM, and capacity in dollars (summary: "Capacity").
- State the impact assumptions; show what happens when costs double.

## 8. Limitations and next steps (~0.5 page)
Biases you couldn't remove, small samples, what you'd test next with more time.

## References
(Not counted toward the 5 pages.)

---

## Submission checklist (Devpost closes **Sunday 10:00 AM ET**; code pushes until 11:00 AM)
- [ ] Quant note as a PDF, 5 pages or fewer (excluding references and appendix)
- [ ] Hypothesis stated before results (committed timestamp)
- [ ] In-sample and out-of-sample results reported separately, net of costs
- [ ] Sharpe, max drawdown, turnover, and an equity curve included
- [ ] Risk management and liquidity/capacity sections included
- [ ] Number of strategy variants tested disclosed
- [ ] Public GitHub repo linked, with a README and dependency file
- [ ] One command reproduces the headline numbers (`uv run python run_all.py --final`)
- [ ] No API keys or licensed raw data committed (`git status` shows no `.env` or `data/cache/`)
- [ ] All team members listed on Devpost

**Score cap:** if judges can't run the code, it gives materially different numbers from the note, or they find
lookahead or out-of-sample tuning, Performance & Analytical Evidence is capped at 4/10. Rerun
`run_all.py --final` right before submitting and copy the numbers from that run.
