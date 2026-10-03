"""Glue between strategies and the engine: load, split off the out-of-sample period, run, evaluate.

From a notebook:

    import strategies
    from gqh import research
    strat = strategies.get("my_idea")
    prep = research.prepare(strat)                       # explore on prep.in_sample only
    res, m = research.evaluate(strat, prep.in_sample, {"lookback": 60})   # logged like run.py
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any

import pandas as pd

from gqh import ROOT, ledger, metrics
from gqh.engine import Result, backtest
from gqh.split import oos_start, truncate


@dataclass
class Prepared:
    data: Any               # full history, out-of-sample included. Only run_all.py --final uses it.
    in_sample: Any          # what exploration is allowed to see
    oos_start: pd.Timestamp


def prepare(strategy) -> Prepared:
    data = strategy.load()
    index = strategy.asset_returns(data).index
    start = oos_start(index)
    last_in_sample = index[index < start].max()
    return Prepared(data, truncate(data, last_in_sample), start)


def params_for(strategy, overrides: dict) -> dict:
    unknown = set(overrides) - set(strategy.defaults)
    if unknown:
        raise SystemExit(f"Unknown parameter(s) {sorted(unknown)} for {strategy.name}; "
                         f"known: {sorted(strategy.defaults)}")
    return {**strategy.defaults, **overrides}


def run(strategy, data, params: dict, cost_mult: float = 1.0) -> Result:
    weights = strategy.weights(data, **params)
    returns = strategy.asset_returns(data)
    return backtest(weights, returns, strategy.cost_bps * cost_mult, strategy.periods_per_year)


def evaluate(strategy, data, overrides: dict | None = None, cost_mult: float = 1.0,
             kind: str = "explore", log: bool = True) -> tuple[Result, dict]:
    """Run one configuration, summarize it, and log it as a trial."""
    params = params_for(strategy, overrides or {})
    res = run(strategy, data, params, cost_mult)
    m = metrics.summarize(res.net, res.turnover, res.periods_per_year)
    if log:
        ledger.record(strategy, params, kind, res.cost_bps, m)
    return res, m


def hypothesis_status(strategy) -> dict:
    """Whether hypotheses/<name>.md exists and when it was first committed."""
    path = ROOT / "hypotheses" / f"{strategy.name}.md"
    if not path.exists():
        return {"path": path.relative_to(ROOT), "exists": False, "committed": None}
    out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%cI", "--", str(path)],
                         capture_output=True, text=True, cwd=ROOT)
    dates = out.stdout.split() if out.returncode == 0 else []
    return {"path": path.relative_to(ROOT), "exists": True, "committed": dates[-1] if dates else None}
