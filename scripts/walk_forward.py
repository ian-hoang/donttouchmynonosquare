"""Walk-forward optimization: the honest way to "find the strategy on the data".

Each calendar year Y, choose the best of the same 192-strategy grid by Sharpe over all years BEFORE Y (expanding
window, minimum 2 years of history), then trade that choice during year Y. The concatenated year-Y returns are an
unbiased estimate of what data-driven optimization delivers on future interviews, because every return comes from
a year the optimizer had not seen when it chose. Procedure fixed before running; the grid is the one in
scripts/overfit_study.py.

Usage: python scripts/walk_forward.py -> results/walk_forward.json, results/walk_forward_daily.csv
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
from pokerface.backtest import run_backtest  # noqa: E402
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
    lo, hi = pd.Timestamp(s["sample_start"]), pd.Timestamp(s["oos_end"])
    daily = {}
    for v in SIGNALS:
        sp = R.signal_params(strat, min_modalities=1, min_features=2) if v.endswith("_only") else R.signal_params(strat)
        ev = R.make_events(feat, build_signals(feat, spec if v == "primary" else R.modify_spec(spec, v), sp), mkt, strat)
        ev = ev[ev["sample"] != "gap"]
        for sign in (1, -1):
            e = ev.assign(signal=ev["signal"] * sign)[["event_id", "ticker", "entry", "signal"]]
            for h in HORIZONS:
                for hd in HEDGES:
                    r = run_backtest(mkt.open, mkt.close, e, p0.with_(horizon=h, hedge=hd)).daily
                    daily[f"{v}|{'+' if sign > 0 else '-'}|h{h}|{hd}"] = r[(r.index >= lo) & (r.index <= hi)]
    M = pd.DataFrame(daily).fillna(0.0)
    years = sorted(set(M.index.year))
    picks, wf = [], []
    for y in years:
        past = M[M.index.year < y]
        if past.index.year.nunique() < 2:
            continue
        sr = past.mean() / past.std(ddof=1).replace(0, np.nan)
        choice = sr.idxmax()
        cur = M.loc[M.index.year == y, choice]
        wf.append(cur)
        picks.append({"year": y, "choice": choice, "past_sharpe": float(sr.max() * np.sqrt(252)),
                      "year_return": float((1 + cur).prod() - 1)})
    wf = pd.concat(wf)
    is_part = wf[wf.index <= pd.Timestamp(s["is_end"])]
    oos_part = wf[wf.index >= pd.Timestamp(s["oos_start"])]
    out = {"walk_forward_all": S.summarize(wf, label="walk-forward"), "walk_forward_through_2024_09": S.summarize(is_part),
           "walk_forward_2024_10_onward": S.summarize(oos_part), "picks": picks,
           "factor": S.factor_regression(wf, mkt.factors), "bootstrap": S.stationary_bootstrap_sharpe(wf)}
    RES = ROOT / "results"
    wf.to_frame("walk_forward").to_csv(RES / "walk_forward_daily.csv")
    (RES / "walk_forward.json").write_text(json.dumps(out, indent=2, default=str))
    print(pd.DataFrame(picks).round(3).to_string(index=False))
    for k in ("walk_forward_all", "walk_forward_through_2024_09", "walk_forward_2024_10_onward"):
        v = out[k]
        print(f"{k}: Sharpe {v['sharpe']:.2f} | ann {100*v['ann_return']:.2f}% | vol {100*v['ann_vol']:.2f}% | maxDD {100*v['max_drawdown']:.1f}%")
    print("bootstrap Sharpe CI:", {k: round(x, 2) for k, x in out["bootstrap"].items()})


if __name__ == "__main__":
    main()
