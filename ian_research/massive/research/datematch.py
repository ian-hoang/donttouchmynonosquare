"""Same-day control: compare each event with other top-100 companies on the same dates.

The scan's placebo matches the ticker mix but not the calendar. Categories that cluster in time (annual
meetings in April-June, for example) can then look special just because of what the whole market did
that season. Here every event gets K control companies (no event of the same category within ±30 days),
entered and exited on exactly the same sessions. The finding is the paired difference
event − mean(controls), so anything every company experienced that week cancels out.

In-sample only. Same settings as the scan (3-6m, 5% OTM, next-session entry).

Run from massive/:   .venv/bin/python research/datematch.py <category> [<category> ...]
Writes:              research/datematch/<category>.csv (aggregates only)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import eightk as K  # noqa: E402
from scan import BUCKET, CELLS, COMBOS, HORIZONS, OTM, STRATS, TIMING, event_side, week_ids  # noqa: E402

OUT = HERE / "datematch"
N_CONTROLS = 4
GAP_DAYS = 30


def controls_for(ev: pd.DataFrame, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = ev.groupby("ticker")["event_date"].apply(lambda s: s.to_numpy(dtype="datetime64[D]")).to_dict()
    rows = []
    for r in ev.itertuples():
        d = np.datetime64(r.event_date, "D")
        cands = [t for t in K.TOP_100 if t != r.ticker and
                 (t not in days or np.all(np.abs((days[t] - d).astype(int)) > GAP_DAYS))]
        for t in rng.choice(cands, N_CONTROLS, replace=False):
            rows.append({"ticker": t, "event_date": r.event_date, "t_pre": r.t_pre, "t_0": r.t_0,
                         "of_ticker": r.ticker})
    return pd.DataFrame(rows)


def wide(res: pd.DataFrame, net: bool) -> pd.DataFrame:
    r = res[(res.entry == "post") & (res.otm == OTM) & (res.bucket == "3-6m")].copy()
    r0 = r[r.horizon == 0].drop_duplicates(["ticker", "event_date"]).set_index(["ticker", "event_date"])
    r = r[r.horizon != 0]
    r["h"] = r.horizon.astype(str)
    cols = STRATS + ["stock"]
    g = r.pivot_table(index=["ticker", "event_date"], columns="h", values=cols, aggfunc="first")
    g = g.reindex(columns=pd.MultiIndex.from_tuples([(s, str(h)) for s in cols for h in HORIZONS]))
    if net:
        for s in cols:
            g[s] = g[s].sub(K.round_trip_cost(r0, s).reindex(g.index), axis=0)
    # The option part alone (strategy minus the stock it owns): what the 8-K changes if you hold the name anyway.
    for s, label in (("protective_put", "overlay_bought_put"), ("covered_call", "overlay_sold_call"), ("collar", "overlay_collar")):
        for h in HORIZONS:
            g[(label, str(h))] = g[(s, str(h))] - g[("stock", str(h))]
    return g


def run(category: str) -> pd.DataFrame:
    tags = COMBOS.get(category, [category])
    ev = K.build_events(tags, K.STUDY_START, K.STUDY_END, timing=TIMING)
    ctl = controls_for(ev)
    keys = sorted({(r.ticker, r.t_pre, r.t_0, r.event_date) for r in ev.itertuples()} |
                  {(r.ticker, r.t_pre, r.t_0, r.event_date) for r in ctl.itertuples()}, key=lambda k: (k[0], k[3]))
    priced, _ = K.price_many(keys, BUCKET, [OTM], workers=16, label=category)
    res = K.evaluate([pe for v in priced.values() for pe in v], [OTM])
    rows = []
    for net in (False, True):
        g = wide(res, net)
        E = g.reindex(pd.MultiIndex.from_frame(ev[["ticker", "event_date"]]))
        C = g.reindex(pd.MultiIndex.from_frame(ctl[["ticker", "event_date"]]))
        C.index = pd.MultiIndex.from_arrays([ctl.of_ticker, ctl.event_date])
        Cm = C.groupby(level=[0, 1]).mean().reindex(E.index)          # mean of each event's controls
        D = E - Cm
        wk = week_ids(ev.t_0)
        years = ev.event_date.dt.year.to_numpy()
        for subset, mask in {"all": np.ones(len(ev), bool), "2024": years == 2024, "2025": years == 2025}.items():
            mD, seD, n = event_side(D.to_numpy()[mask], wk[mask])
            mE, _, _ = event_side(E.to_numpy()[mask], wk[mask])
            mC, _, _ = event_side(Cm.to_numpy()[mask], wk[mask])
            for j, (s, h) in enumerate(D.columns):
                rows.append({"category": category, "basis": "net" if net else "gross", "subset": subset,
                             "strategy": s, "horizon": h, "n": int(n[j]), "event": mE[j], "same_day_controls": mC[j],
                             "diff": mD[j], "t": mD[j] / seD[j] if seD[j] else np.nan})
    out = pd.DataFrame(rows)
    OUT.mkdir(exist_ok=True)
    out.to_csv(OUT / f"{category.replace(':', '_')}.csv", index=False)
    months = ev.event_date.dt.to_period("M").value_counts().sort_index()
    print(f"\n{category}: {len(ev)} events; busiest months: " +
          ", ".join(f"{p} ({n})" for p, n in months.sort_values(ascending=False).head(5).items()))
    return out


if __name__ == "__main__":
    for cat in sys.argv[1:]:
        run(cat)
