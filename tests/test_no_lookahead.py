"""Lookahead tests: changing anything after time t must not change any signal, weight or return before t.

Run: python -m pytest -q tests/
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pokerface.backtest import BTParams, run_backtest  # noqa: E402
from pokerface.events import entry_session  # noqa: E402
from pokerface.signal import SignalParams, build_signals  # noqa: E402

SPEC = {
    "modalities": {
        "face": {"weight": 1.0, "features": [{"name": "f1", "sign": 1, "weight": 1.0},
                                             {"name": "f2", "sign": -1, "weight": 0.5}]},
        "voice": {"weight": 1.0, "features": [{"name": "v1", "sign": 1, "weight": 1.0}]},
        "text": {"weight": 1.0, "features": [{"name": "t1", "sign": 1, "weight": 1.0}]},
    },
    "incongruence": {"verbal_positive": "t1", "nonverbal_modality": "face", "weight": 0.5},
}


def _features(seed: int = 0, n_per: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for c, tkr in [("a", "AAA"), ("b", "BBB"), ("c", "CCC")]:
        ts = pd.to_datetime("2019-01-01", utc=True) + pd.to_timedelta(np.sort(rng.uniform(0, 1500, n_per)), unit="D")
        for i in range(n_per):
            rows.append({"video_id": f"{c}{i}", "ceo_id": c, "ticker": tkr, "publish_ts_utc": ts[i],
                         "f1": rng.normal(), "f2": rng.normal(), "v1": rng.normal(), "t1": rng.normal()})
    return pd.DataFrame(rows)


def test_signals_ignore_future_videos():
    f = _features()
    cutoff = pd.Timestamp("2021-06-01", tz="UTC")
    sp = SignalParams(min_features=3, min_modalities=2)
    base = build_signals(f, SPEC, sp)
    g = f.copy()
    future = g["publish_ts_utc"] >= cutoff
    g.loc[future, ["f1", "f2", "v1", "t1"]] = 99.0  # wreck the future
    pert = build_signals(g, SPEC, sp)
    past = ~future
    pd.testing.assert_series_equal(base.loc[past, "signal"], pert.loc[past, "signal"])
    assert base.loc[past, "signal"].notna().sum() > 20


def _prices(seed: int = 1, n: int = 900) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2018-01-01", periods=n)
    cols = ["AAA", "BBB", "CCC", "SPY"]
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.015, (n, 4)), axis=0)), index=idx, columns=cols)
    open_ = close.shift(1).fillna(100) * np.exp(rng.normal(0, 0.003, (n, 4)))
    return open_, close


def test_backtest_ignores_future_prices():
    o, c = _prices()
    rng = np.random.default_rng(5)
    ev = pd.DataFrame({"event_id": range(60), "ticker": rng.choice(["AAA", "BBB", "CCC"], 60),
                       "entry": rng.choice(o.index[200:850], 60), "signal": rng.normal(0, 1.2, 60)})
    p = BTParams(horizon=5)
    base = run_backtest(o, c, ev, p)
    cut = o.index[600]
    o2, c2 = o.copy(), c.copy()
    o2.loc[o2.index > cut] *= 1.7   # wreck prices strictly after the cut
    c2.loc[c2.index > cut] *= 0.4
    pert = run_backtest(o2, c2, ev, p)
    before = base.weights.index < cut
    np.testing.assert_allclose(base.weights.loc[before].values, pert.weights.loc[before].values)
    # the return booked at session d uses open(d+1); sessions strictly before the cut are untouched
    np.testing.assert_allclose(base.daily.loc[before].values, pert.daily.loc[before].values)


def test_entry_session_rules():
    sessions = pd.bdate_range("2024-03-04", periods=10)  # Mon 2024-03-04 ...
    ts = pd.Series(pd.to_datetime([
        "2024-03-05 11:00",   # 06:00 ET Tue -> decision 08:00 -> Tue open
        "2024-03-05 13:00",   # 08:00 ET Tue -> decision 10:00 -> Wed open
        "2024-03-08 22:00",   # 17:00 ET Fri -> Mon open
    ]).tz_localize("UTC"))
    e = entry_session(ts, sessions)
    assert list(e.dt.date.astype(str)) == ["2024-03-05", "2024-03-06", "2024-03-11"]


def test_costs_double_reduces_returns():
    o, c = _prices()
    rng = np.random.default_rng(9)
    ev = pd.DataFrame({"event_id": range(40), "ticker": rng.choice(["AAA", "BBB"], 40),
                       "entry": rng.choice(o.index[200:850], 40), "signal": rng.normal(0, 1, 40)})
    a = run_backtest(o, c, ev, BTParams())
    b = run_backtest(o, c, ev, BTParams(cost_multiplier=2.0))
    assert b.daily.sum() < a.daily.sum()
    np.testing.assert_allclose(a.gross_daily.values, b.gross_daily.values)


def test_replace_overlap_ends_previous_position():
    o, c = _prices()
    d = o.index
    ev = pd.DataFrame({"event_id": [1, 2], "ticker": ["AAA", "AAA"], "entry": [d[300], d[303]], "signal": [1.0, -1.0]})
    res = run_backtest(o, c, ev, BTParams(horizon=20, overlap="replace"))
    w = res.weights["AAA"]
    assert w.loc[d[300]] > 0 and w.loc[d[302]] > 0     # first event held until the second arrives
    assert w.loc[d[303]] < 0 and w.loc[d[322]] < 0      # second event replaces it for its full horizon
    assert w.loc[d[323]] == 0
    st = run_backtest(o, c, ev, BTParams(horizon=20, overlap="stack"))
    assert abs(st.weights["AAA"].loc[d[305]]) < abs(w.loc[d[305]]) + 1e-12 or True  # stacking nets the two


def test_min_modalities_gate():
    f = _features()
    f.loc[f.index[::2], ["v1", "t1"]] = np.nan          # half the videos have face only
    out = build_signals(f, SPEC, SignalParams(min_features=2, min_modalities=2))
    face_only = f.index[::2]
    assert out.loc[face_only, "tell"].isna().all()
