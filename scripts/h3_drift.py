"""H3 (HYPOTHESIS_2.md): unconditional post-interview drift versus the same stocks on matched random days.

Excess_i = CAR_20(interview i) - mean over 100 random sessions in the same year for the same ticker of CAR_20.
Reports the mean excess with a CEO-clustered bootstrap CI for the requested sample.

Usage: python scripts/h3_drift.py --sample OOS            (original universe, sealed window)
       PF_UNIVERSE=_h2 python scripts/h3_drift.py --sample ALL
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pokerface import research as R  # noqa: E402
from pokerface.signal import build_signals  # noqa: E402


def car20(mkt, tkr: str, i0: int, beta: float, r_oo: pd.DataFrame, h: int = 20) -> float:
    ar = r_oo[tkr].values[i0:i0 + h] - beta * r_oo["SPY"].values[i0:i0 + h]
    return float(np.nansum(ar)) if len(ar) == h else np.nan


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", choices=["IS", "OOS", "ALL"], required=True)
    ap.add_argument("--draws", type=int, default=100)
    a = ap.parse_args()
    strat, spec = R.load_configs()
    mkt = R.load_market()
    feat, _ = R.apply_qc(R.load_features(), strat)
    ev = R.make_events(feat, build_signals(feat, spec, R.signal_params(strat)), mkt, strat)
    ev = ev if a.sample == "ALL" else ev[ev["sample"] == a.sample]
    ev = ev[ev["sample"] != "gap"]
    o, c = mkt.open, mkt.close
    r_oo = o.shift(-1) / o - 1
    r_cc = c.pct_change()
    sess = o.dropna(how="all").index
    pos = {d: i for i, d in enumerate(sess)}
    rng = np.random.default_rng(20261003)
    rows = []
    for e in ev.itertuples(index=False):
        i0 = pos.get(e.entry)
        if i0 is None or i0 < 260 or i0 + 20 >= len(sess):
            continue
        y, x = r_cc[e.ticker].values[i0 - 252:i0], r_cc["SPY"].values[i0 - 252:i0]
        m = np.isfinite(y) & np.isfinite(x)
        beta = float(np.clip(np.cov(y[m], x[m])[0, 1] / np.var(x[m], ddof=1), 0.3, 2.5)) if m.sum() > 60 else 1.0
        ev_car = car20(mkt, e.ticker, i0, beta, r_oo)
        same_year = np.flatnonzero((sess.year == e.entry.year) & (np.arange(len(sess)) + 20 < len(sess)))
        draws = rng.choice(same_year, size=min(a.draws, len(same_year)), replace=False)
        base = np.nanmean([car20(mkt, e.ticker, j, beta, r_oo) for j in draws])
        rows.append({"ceo_id": e.ceo_id, "entry": e.entry, "car": ev_car, "base": base, "excess": ev_car - base})
    d = pd.DataFrame(rows).dropna()
    groups = [g["excess"].values for _, g in d.groupby("ceo_id")]
    boots = [np.concatenate([groups[k] for k in rng.integers(len(groups), size=len(groups))]).mean() for _ in range(5000)]
    out = {"universe": R.UNIVERSE or "original", "sample": a.sample, "n_events": int(len(d)), "n_ceos": int(d["ceo_id"].nunique()),
           "mean_event_car": float(d["car"].mean()), "mean_random_day_car": float(d["base"].mean()),
           "mean_excess": float(d["excess"].mean()), "ci95": [float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))],
           "supports_h3_here": bool(np.quantile(boots, 0.025) > 0)}
    R.RESULTS.mkdir(exist_ok=True)
    (R.RESULTS / f"h3_drift_{a.sample}.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
