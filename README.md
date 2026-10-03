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

## Three intraday prototypes: start here

Liquidity Fatigue, Queue Sacrifice, and The Missing Beat now have separate modules in
`microstrategies/`, written hypotheses in `hypotheses/`, and focused synthetic tests. They are
**untested research hypotheses**, with untuned defaults. This path uses `run_micro.py`; the original
`run.py` / `run_all.py` remain the separate daily-strategy workflow.

Run all three, their ordinary baselines, and normal/double costs without credentials:

```bash
uv run python run_micro.py all --demo
uv run pytest -q
```

The demo checks plumbing on artificial noise; zero signals are possible and its P&L is not evidence.
Mechanism tests use crafted cases that actually trigger each strategy. Private timestamped output
under `results/micro/runs/` includes a comparison table, plot, fills, equity curves, and a frozen
manifest. None of those quote-derived files are automatically included in Git.

| Teammate | Strategy module | What to investigate |
|---|---|---|
| 1 | `microstrategies/liquidity_fatigue.py` | Whether completed recovery episodes worsen before a subsequent directional burst |
| 2 | `microstrategies/queue_sacrifice.py` | Whether front-of-queue cancellations beat ordinary cancellation imbalance |
| 3 | `microstrategies/missing_beat.py` | Whether absent scheduled flow predicts reversal beyond an ordinary flow drop |

Each module exports `DEFAULTS`, `signal(features, **params)`, `baseline(...)`, and `diagnostics(...)`.
Signals must return -1/0/+1 on the exact input index. The shared code owns replay, execution, costs,
risk limits, trial logging, and holdout access. Announce changes to those shared files first.

### Bring in Databento data

1. Select **one actual outright contract**, verify its tick size, dollar multiplier, fees and trading
   hours, and write the chosen universe/dates/costs into each hypothesis. Queue Sacrifice additionally
   requires a verified **FIFO** contract. Then commit and push the hypotheses before market backtests.
   The runner refuses a missing, uncommitted, or modified hypothesis; it does not push anything.
2. Estimate a bounded GLBX.MDP3 MBO request, starting at midnight UTC to include the full snapshot.
   The following symbol and dates are an example to verify before use, not a selected research sample:

   ```bash
   uv run python data/download_micro.py ESZ6 2026-09-28 2026-09-29
   # Only after reviewing size/cost; subject to GQH_MAX_COST_USD:
   uv run python data/download_micro.py ESZ6 2026-09-28 2026-09-29 --download
   ```

3. Use the printed DBN path. Pass actual contract specs and confirm FIFO only after checking it:

   ```bash
   uv run python run_micro.py all --dbn data/cache/<printed-file>.dbn.zst \
     --tick-size 0.25 --multiplier 50 --fee-per-side 2.50 --fifo
   # One teammate can run just one idea with explicitly disclosed overrides:
   uv run python run_micro.py queue_sacrifice --dbn data/cache/<printed-file>.dbn.zst \
     --tick-size 0.25 --multiplier 50 --fee-per-side 2.50 --fifo \
     --set queue_sacrifice.window=20
   ```

   The numerical fee is illustrative. All fees, slippage, latency and risk assumptions are recorded.
   Defaults are 1-second bars, 09:30–16:00 America/New_York, 2-second quote-age limit, 100 ms nominal
   latency (at least one full grid step), one extra adverse tick per side, one contract maximum,
   a 30-second holding cap, $100 trade stop, $300 daily loss brake, and $100,000 accounting capital.
   Stops are observed on the grid and can lose more during gaps; capital is not a verified margin requirement.
   Override these explicitly for the chosen contract and record the economic justification.

4. Exploration uses only the earliest 80% of elapsed history (or all but the final two years for long
   history). There is no random train/test shuffle. After choosing the full experiment, append
   `--final` to the identical command to evaluate IS and OOS separately. `results/micro/OOS_LOCK.json`
   freezes data bytes, shared/strategy code, hypotheses, dependency/runtime versions, all parameters,
   costs, session hours and timing. Commit that lock; unchanged reruns reproduce it. All three and
   their baselines count as tried variants; do not pick a winner after seeing OOS without disclosure.

Each variant/cost/sample run logs a start and success/failure in private
`results/micro/ledger.jsonl`. Combine those logs across teammates; the demo uses a separate log.
Real data has not yet been downloaded or evaluated by these prototypes.

### Intraday limitations to keep visible

- `gqh/microdata.py` replays true GLBX MBO in receive/file order. A leading clear/snapshot is mandatory;
  mixed contracts/publishers, synthesized MBP, unknown-order updates and corrupt book flags fail closed.
  Quotes/flow are published only after `F_LAST`. Synthetic snapshot adds are not new order flow.
  Executed removals identified by preceding fills are excluded from explicit-cancel flow. Modify-only
  reductions are excluded too: cancellation weighting is a conservative proxy, not trader identity.
- Gaps, resets, stale or crossed quotes reset strategy history. Unknown-side trades count in total
  volume, never guessed signed flow. Replay maintains the direct book, not additional implied liquidity.
- `gqh/microengine.py` buys at a later sampled ask and sells at a later sampled bid. It charges spread,
  fees and additional slippage on every side; double-cost stress doubles all three. It never earns
  the price change before entry. It checks displayed size but does not model passive fills, market
  impact, queue competition or exchange-level fill probabilities. It cannot establish HFT feasibility.
- Forced exits wait for valid quotes; a missing executable session-end exit raises an error. The
  configured window's end and data-end liquidation are scheduled in advance. Overnight sessions,
  continuous futures rolls, portfolios, and live order placement are outside this prototype.
- The in-memory Python replay defaults to a two-million-record cap; explicitly raise `--max-records`
  or narrow the sample after checking memory/data cost. A full liquid-futures MBO day can exceed it.
- Annualized statistics require at least 20 observed sessions, and even that is not evidence of
  robustness. No significance, capacity or profitability claim is automated. Fatigue's moving-best
  depth proxy needs level-migration checks; Missing Beat's broad baseline also changes waiting time
  and confirmation count, so a matched cadence ablation is still needed before a mechanism claim.

Input semantics: [Databento GLBX normalization](https://databento.com/docs/knowledge-base/datasets/glbx-mdp3),
[MBO](https://databento.com/docs/schemas-and-data-formats/mbo), and
[order lifecycle](https://databento.com/docs/examples/order-book/order-actions).

### Frozen first real-data experiment

`experiments/micro_opening_2026.json` freezes ESU6, August 3–September 4, 2026,
09:30–10:30 ET. `hypotheses/micro_opening_2026.md` documents costs, minimum sample
requirements, all four execution scenarios and interpretation criteria. The first
20 sessions (August 3–28) are IS; the final five sessions remain reserved.
The shared hypotheses/configuration were committed before looking at market P&L.

Reproduce the fixed research screen with your own Databento entitlement:

```bash
uv run python data/research_micro.py estimate          # no download; prints fresh cost estimates
uv run python data/research_micro.py download          # IS only, cumulative budget at most $20
uv run python data/research_micro.py prepare --workers 3  # stream midnight books, retain opening hour
uv run python backtest_micro.py --plot                 # 24 fixed IS comparisons; never opens holdout
```

The download command also honors a lower `GQH_MAX_COST_USD` setting. Reserved
costs, including failed requests, stay in the private cache ledger. A failed
partial file requires inspection before retrying. Completed downloads and
features are reused with checksum checks. Replay can overlap completed downloads
using `prepare --available`; the backtest still requires all twenty IS sessions.

The batch runner checks that the exact hypotheses/configuration are in HEAD,
logs every strategy/baseline/scenario attempt, verifies signal prefix invariance,
and exports daily P&L, flat-to-flat episode statistics, paired baseline differences,
and five-session block-bootstrap intervals. Results stay in ignored
`results/micro/runs/opening_2026/`. Twenty days of reused history support an
exploratory screen, not a validated alpha claim. No deployment or live orders are
part of this workflow.

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
