"""Overfitting stress test: how much Sharpe can optimization manufacture from this data, and is it real?

Grid (192 strategies): horizon {1,2,3,5,10,20,40,60} x hedge {SPY,QQQ} x signal {primary, no_incongruence,
equal_feature_weights, face_only, voice_only, text_only} x sign {+1, -1}. All evaluated IN-SAMPLE only.
Reports the best in-sample Sharpe, its Deflated Sharpe over 192 trials, the CSCV probability of backtest
overfitting, and then applies the fixed selection rule "take the in-sample winner" to the sealed window,
which tests the selection procedure itself (nothing here changes the headline strategy).

Usage: python scripts/overfit_study.py  ->  results/overfit_study.json, results/overfit_grid.csv
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pokerface import research as R  # noqa: E402
from pokerface import stats as S  # noqa: E402
from pokerface.signal import build_signals  # noqa: E402

HORIZONS = [1, 2, 3, 5, 10, 20, 40, 60]
HEDGES = ["SPY", "QQQ"]
SIGNALS = ["primary", "no_incongruence", "equal_feature_weights", "face_only", "voice_only", "text_only"]


def main() -> None:
    strat, spec = R.load_configs()
    mkt = R.load_market()
    feat, _ = R.apply_qc(R.load_features(), strat)
    p0 = R.bt_params(strat)
    s = strat["samples"]
    events = {}
    for v in SIGNALS:
        sp = R.signal_params(strat, min_modalities=1, min_features=2) if v.endswith("_only") else R.signal_params(strat)
        sg = build_signals(feat, spec if v == "primary" else R.modify_spec(spec, v), sp)
        events[v] = R.make_events(feat, sg, mkt, strat)
    rows, daily_is = [], {}
    for v in SIGNALS:
        for sign in (1, -1):
            ev = events[v].assign(signal=events[v]["signal"] * sign)
            for h in HORIZONS:
                for hd in HEDGES:
                    name = f"{v}|{'+' if sign > 0 else '-'}|h{h}|{hd}"
                    e = R.evaluate(name, ev, mkt, p0.with_(horizon=h, hedge=hd), "IS", strat, factors=False)
                    r = e.result.daily
                    daily_is[name] = r[(r.index >= pd.Timestamp(s["sample_start"])) & (r.index <= pd.Timestamp(s["is_end"]))]
                    rows.append({"variant": name, "signal": v, "sign": sign, "horizon": h, "hedge": hd,
                                 "is_sharpe": e.summary["sharpe"], "n_traded": e.summary["n_traded"]})
    grid = pd.DataFrame(rows).sort_values("is_sharpe", ascending=False)
    mat = pd.DataFrame(daily_is)
    best = grid.iloc[0]
    sr_var = float((grid["is_sharpe"] / np.sqrt(252)).var(ddof=1))
    dsr = S.deflated_sharpe(mat[best["variant"]], n_trials=len(grid), var_sr_trials_per_period=sr_var)
    pbo = S.pbo_cscv(mat, n_splits=10)
    # the fixed rule "pick the in-sample winner", applied once to the sealed window
    bv, bs = best["signal"], int(best["sign"])
    ev = events[bv].assign(signal=events[bv]["signal"] * bs)
    oos = R.evaluate("overfit_winner_OOS", ev, mkt, p0.with_(horizon=int(best["horizon"]), hedge=best["hedge"]), "OOS", strat, factors=False)
    out = {"n_strategies": int(len(grid)), "best_variant": best["variant"], "best_is_sharpe": float(best["is_sharpe"]),
           "median_is_sharpe": float(grid["is_sharpe"].median()), "share_positive_is": float((grid["is_sharpe"] > 0).mean()),
           "best_dsr": dsr, "pbo": pbo, "winner_oos_sharpe": oos.summary["sharpe"], "winner_oos_ann_return": oos.summary["ann_return"]}
    RES = ROOT / "results"
    grid.to_csv(RES / "overfit_grid.csv", index=False)
    (RES / "overfit_study.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps({k: v for k, v in out.items() if k != "best_dsr"}, indent=1, default=str))
    print("best DSR:", {k: round(v, 3) if isinstance(v, float) else v for k, v in dsr.items()})
    print(grid.head(10).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
