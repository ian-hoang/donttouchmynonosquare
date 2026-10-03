"""Local trial log, so the note can state honestly how many variants were tried.

Each run appends one row to results/ledger.csv (gitignored). Rerunning an unchanged config doesn't
count as a new trial; editing the strategy file does.

    uv run python -m gqh.ledger      # print the counts for the note
"""
from __future__ import annotations

import csv
import hashlib
import inspect
import json
from datetime import datetime

import pandas as pd

from gqh import RESULTS

LEDGER = RESULTS / "ledger.csv"
FIELDS = ["time", "strategy", "code", "kind", "params", "cost_bps", "n_obs", "sharpe", "sharpe_pp"]
CONFIG = ["strategy", "code", "params", "cost_bps"]


def code_hash(strategy) -> str:
    source = inspect.getsourcefile(type(strategy))
    with open(source, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()[:10]


def record(strategy, params: dict, kind: str, cost_bps: float, m: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    new = not LEDGER.exists()
    with open(LEDGER, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({
            "time": datetime.now().isoformat(timespec="seconds"),
            "strategy": strategy.name,
            "code": code_hash(strategy),
            "kind": kind,
            "params": json.dumps(params, sort_keys=True),
            "cost_bps": cost_bps,
            "n_obs": m["n_obs"],
            "sharpe": round(m["sharpe"], 6),
            "sharpe_pp": m["sharpe_pp"],
        })


def trials() -> pd.DataFrame:
    """One row per distinct configuration tried."""
    if not LEDGER.exists():
        return pd.DataFrame(columns=FIELDS)
    return pd.read_csv(LEDGER).drop_duplicates(CONFIG, keep="last")


def first_run(strategy_name: str) -> str | None:
    """Time of the first logged backtest of a strategy on this machine."""
    if not LEDGER.exists():
        return None
    times = pd.read_csv(LEDGER).query("strategy == @strategy_name")["time"]
    return times.min() if len(times) else None


def stats() -> dict:
    t = trials()
    return {"n_trials": len(t), "var_sharpe_pp": float(t["sharpe_pp"].var()) if len(t) > 1 else None}


if __name__ == "__main__":
    t = trials()
    if t.empty:
        print("No trials logged yet.")
    else:
        print(f"Distinct configurations tried: {len(t)}\n")
        print(t.groupby(["strategy", "kind"]).size().rename("configs").to_string())
