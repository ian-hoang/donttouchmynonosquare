# GQH Systematic Trading: team research harness

A shared backtesting harness for the Gator Quant Hacks 2026 Systematic Trading track, built on Databento
data. Each idea lives in its own file. The shared code applies the track rules for you: signals are
lagged one bar, out-of-sample data stays locked, every result is net of costs, and every number in the
note is reproducible.

**Deadlines:** Devpost (note PDF + repo link) **Sunday Oct 4, 10:00 AM ET**. Code pushes until 11:00 AM.

## Setup

```bash
uv sync                      # or: python -m venv .venv && pip install -r requirements.txt
cp .env.example .env         # add DATABENTO_API_KEY
uv run pytest -q             # sanity check
uv run python run.py example_tsmom   # runs on synthetic data, no key needed
```

## Reproduce our results (judges start here)

```bash
uv run python data/download.py <strategy>   # fetch the data from Databento (needs your own key)
uv run python run_all.py --final            # every table and figure in the note -> results/<strategy>/
```

## Team workflow

1. **Write the hypothesis first.** Copy `hypotheses/TEMPLATE.md` to `hypotheses/<idea>.md`, fill it in, then
   commit and push it **before** your first backtest. `run.py` warns until it's committed.
2. **One file per idea.** Copy `strategies/_template.py` to `strategies/<idea>.py`; the file name is the
   strategy name. You own your file, so nobody collides in git. Announce changes to `gqh/` (shared) first.
3. **Explore in-sample:**
   ```bash
   uv run python run.py <idea>                                       # defaults
   uv run python run.py <idea> --set lookback=120                    # change params
   uv run python run.py <idea> --sweep lookback=20,60 vol_target=0,0.1   # every combination
   uv run python run.py <idea> --cost-mult 2                         # does it survive double costs?
   uv run python run.py <idea> --plot                                # results/explore/<idea>.png
   ```
4. **Pick the final strategy** and set `FINAL` at the top of `run_all.py`. `uv run python run_all.py` writes
   the full in-sample report to `results/<idea>/summary.md`.
5. **Evaluate out-of-sample once:** `uv run python run_all.py --final`. Commit `results/OOS_LOCK.json`.
   Later changes are refused unless you pass `--relock "reason"`, and the reason goes in the note.
6. **Write the note** from `note/NOTE_TEMPLATE.md`. Its sections follow `summary.md` and the judging rubric,
   and it ends with the submission checklist.

From a notebook, use the same functions so trials are still logged and out-of-sample stays hidden:

```python
import strategies
from gqh import research
strat = strategies.get("my_idea")
prep = research.prepare(strat)                                   # use prep.in_sample only
res, m = research.evaluate(strat, prep.in_sample, {"lookback": 60})
```

## Databento tips

- **Check the price first:** `gd.price("GLBX.MDP3", ["ES.c.0"], "ohlcv-1m", "2020-01-01", "2026-10-01", "continuous")`.
  Downloads above `GQH_MAX_COST_USD` (default $5) are refused. `gd.available("GLBX.MDP3")` lists dates and schemas.
- **Download once, share privately.** Files are cached in `data/cache/`. One person downloads and sends the folder
  to teammates (AirDrop or Drive); never commit it, since the data is licensed.
- **`ohlcv-1d` bars are UTC days.** For futures that's a consistent daily sample (close at midnight UTC). For
  stocks/ETFs the "close" would be an after-hours print, so pull `ohlcv-1m` and use `gd.session_daily()`.
- **Futures rolls:** fetch `ES.c.0` and `ES.c.1` with `stype_in="continuous"`; `gd.roll_safe_returns()` removes
  roll jumps. `.c.` rolls by calendar, `.v.` by volume, `.n.` by open interest.
- **Stocks/ETFs aren't split or dividend adjusted.** The data checks in `summary.md` flag suspicious jumps.
- **Justify costs:** `gd.futures_cost_bps(price, tick_size, multiplier)` turns contract specs into bps per side.
- Use a fixed `end` date in `load()` so judges download exactly the same history.

## Layout

```
gqh/            shared library
  data.py         Databento download/cache/price, session bars, roll-safe returns, cost estimates
  split.py        out-of-sample rule
  engine.py       vectorized backtest (applies the one-bar lag)
  risk.py         vol targeting, position/gross caps, drawdown brake (all lookahead-safe)
  metrics.py      performance, exposure, warnings, Deflated Sharpe
  checks.py       lookahead check, data-quality check
  ledger.py       local trial log (python -m gqh.ledger prints counts)
  analysis.py     returns by year, factor regression, capacity model
  research.py     prepare / run / evaluate, hypothesis-commit check
  report.py       figures and markdown
strategies/     one file per idea; base.py is the interface, _template.py the starting point
hypotheses/     one written hypothesis per idea, committed before testing
note/           quant note template and submission checklist
data/           download.py (tracked); cache/ holds raw Databento files (gitignored)
results/        run_all.py output; ledger.csv is your local trial log (gitignored)
run.py          in-sample exploration
run_all.py      reproduces the note
```

## Rules the code enforces

| Track rule | Where |
|---|---|
| Hypothesis before results | `run.py` warns until `hypotheses/<idea>.md` is committed; `summary.md` shows the commit time |
| Signals lagged one bar (no same-bar trading) | `gqh/engine.py` shifts every weight |
| Out-of-sample = most recent 20% or 2 years, whichever is shorter | `gqh/split.py`; `run.py` never sees it |
| Evaluate out-of-sample once | `results/OOS_LOCK.json` |
| No lookahead | `gqh/checks.py` re-runs on truncated data |
| Net of costs, and with costs doubled | `cost_bps` per strategy; `run_all.py` reports x1 and x2 |
| Disclose number of variants tried | `uv run python -m gqh.ledger` (combine teammates' counts) |
| "Sharpe above 3 usually means a bug" | warnings in `run.py` and `summary.md` |
| Risk management, liquidity and capacity | `gqh/risk.py`, exposure table, automatic capacity estimate |

## Data sources

Databento (market data), Ken French Data Library (factor returns). Cite any others you add.
