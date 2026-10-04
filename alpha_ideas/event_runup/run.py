"""Step 2 — Earnings Eve (idea 1A) backtest, exactly as PREREGISTRATION.md.

Run from the repo root:
  uv run python alpha_ideas/event_runup/run.py          # in-sample (entries 2021-01-01 .. 2025-12-31)
  uv run python alpha_ideas/event_runup/run.py --oos    # 2026 hold-out, ONCE, after the IS verdict (writes OOS_LOCK.json)
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
AIW = ROOT / "data" / "cache" / "ai_washing"
CACHE = ROOT / "data" / "cache" / "event_runup"

HOLD = 5
COST_STOCK = 8e-4          # per side
COST_SPY = 1e-4            # per side, per unit beta
CARRY = 0.5e-4             # per session, per unit beta (SPY dividends owed on the short hedge)
IS_START, IS_END = "2021-01-01", "2025-12-31"
OOS_START = "2026-01-01"
PLACEBO_SHIFT = 30


# ------------------------------------------------------------------------------------------------ data
def load():
    cal = pd.DatetimeIndex(pd.to_datetime(pd.read_parquet(AIW / "calendar.parquet")["date"]).astype("datetime64[ns]"))
    px = pd.read_parquet(AIW / "prices.parquet", columns=["date", "cik", "ret"])
    px["cik"] = px["cik"].astype(str).str.zfill(10)
    px["date"] = px["date"].astype("datetime64[ns]")
    R = px.pivot_table(index="date", columns="cik", values="ret", aggfunc="first").reindex(cal)
    spy = []
    for y in range(2019, 2027):
        g = pd.read_parquet(ROOT / "data" / "cache" / "massive_grouped" / f"grouped_{y}.parquet")
        spy.append(g[g["ticker"] == "SPY"][["date", "close"]])
    spy = pd.concat(spy)
    spy["date"] = pd.to_datetime(spy["date"]).astype("datetime64[ns]")
    s = spy.drop_duplicates("date").set_index("date")["close"].sort_index()
    m = s.pct_change().reindex(cal)
    assert m.iloc[1:].notna().all(), "SPY return missing on a calendar day"
    uni = pd.read_parquet(AIW / "universe.parquet")
    uni["cik"] = uni["cik"].astype(str).str.zfill(10)
    uni["month_end"] = pd.to_datetime(uni["month_end"]).astype("datetime64[ns]")
    ev = pd.read_parquet(CACHE / "events.parquet")
    ep = pd.read_parquet(CACHE / "episodes.parquet")
    return cal, R, m, uni, ev, ep


def membership(cal, R, uni) -> pd.DataFrame:
    """True where the CIK is in the universe of the last month-end strictly before the date."""
    ends = np.sort(uni["month_end"].unique())
    idx = np.searchsorted(ends, cal.to_numpy(), side="left") - 1          # strictly before
    sets = {e: set(g["cik"]) for e, g in uni.groupby("month_end")}
    M = np.zeros(R.shape, dtype=bool)
    cols = {c: j for j, c in enumerate(R.columns)}
    for i, k in enumerate(idx):
        if k < 0:
            continue
        for c in sets[ends[k]]:
            j = cols.get(c)
            if j is not None:
                M[i, j] = True
    return pd.DataFrame(M, index=cal, columns=R.columns)


# -------------------------------------------------------------------------------------------- features
def features(cal, R, m, ep):
    valid = R.notna()
    lr = np.log1p(R.fillna(0.0))
    r12 = np.expm1(lr.rolling(252, min_periods=1).sum())
    r12 = r12.where(valid.rolling(252, min_periods=1).sum() >= 200)

    ex = R.sub(m, axis=0)
    ivol = ex.rolling(60, min_periods=40).std()

    x, y = R, pd.DataFrame(np.repeat(m.to_numpy()[:, None], R.shape[1], axis=1), index=cal, columns=R.columns)
    y = y.where(valid)
    n = valid.rolling(252, min_periods=1).sum()
    sx, sy = x.fillna(0).rolling(252, min_periods=1).sum(), y.fillna(0).rolling(252, min_periods=1).sum()
    sxy = (x * y).fillna(0).rolling(252, min_periods=1).sum()
    syy = (y * y).fillna(0).rolling(252, min_periods=1).sum()
    cov = sxy / n - (sx / n) * (sy / n)
    var = syy / n - (sy / n) ** 2
    beta = (cov / var).where(n >= 120).clip(0.2, 3.0)

    # PREAC: SPY-adjusted return from the session before F to the session after F, mean of last 4 (min 2)
    ep = ep.copy()
    ep["F"] = ep["accepted_et"].dt.normalize().astype("datetime64[ns]")
    calv = cal.to_numpy()
    ep["i_before"] = np.searchsorted(calv, ep["F"].to_numpy(), side="left") - 1
    ep["i_after"] = np.searchsorted(calv, ep["F"].to_numpy(), side="right")
    ep = ep[(ep["i_before"] >= 0) & (ep["i_after"] < len(cal)) & ep["cik"].isin(R.columns)]
    cum = (1 + R.fillna(0.0)).cumprod()
    cum_m = (1 + m.fillna(0.0)).cumprod().to_numpy()
    reac = []
    for r in ep.itertuples():
        win = R[r.cik].iloc[r.i_before + 1:r.i_after + 1]
        if win.isna().any():
            continue
        rs = cum[r.cik].iat[r.i_after] / cum[r.cik].iat[r.i_before] - 1
        rm = cum_m[r.i_after] / cum_m[r.i_before] - 1
        reac.append((r.cik, r.i_after, rs - rm))
    reac = pd.DataFrame(reac, columns=["cik", "i_after", "reaction"]).sort_values(["cik", "i_after"])
    g = reac.groupby("cik")["reaction"]
    reac["preac"] = g.transform(lambda s: s.rolling(4, min_periods=2).mean())
    reac = reac.dropna(subset=["preac"]).drop_duplicates(["cik", "i_after"], keep="last")
    P = pd.DataFrame(np.nan, index=cal, columns=R.columns)
    for cik, gg in reac.groupby("cik"):
        P.iloc[gg["i_after"].to_numpy(), P.columns.get_loc(cik)] = gg["preac"].to_numpy()
    preac = P.ffill()
    return r12, ivol, beta, preac


def scores(M, r12, ivol, preac):
    ok = M & r12.notna() & ivol.notna() & preac.notna()
    ranks = {k: v.where(ok).rank(axis=1, pct=True) for k, v in {"r12": r12, "preac": preac, "ivol": ivol}.items()}
    comp = (ranks["r12"] + ranks["preac"] + ranks["ivol"]) / 3
    ranks["score"] = comp.rank(axis=1, pct=True)
    return ranks


# ---------------------------------------------------------------------------------------------- events
def window_returns(R, m, cik, i_e, i_x):
    w = R[cik].iloc[i_e + 1:i_x + 1]
    if len(w) != i_x - i_e or w.isna().any():
        return np.nan, np.nan
    return float(np.prod(1 + w.to_numpy()) - 1), float(np.prod(1 + m.iloc[i_e + 1:i_x + 1].to_numpy()) - 1)


def event_table(cal, R, m, M, ev, ranks, beta, ep, hold=HOLD, xcol="i_X", shift=0):
    rows = []
    col = {c: j for j, c in enumerate(R.columns)}
    ix_col = xcol
    for r in ev.itertuples():
        j = col.get(r.cik)
        i_x = int(getattr(r, ix_col)) - shift
        i_e = i_x - hold
        if j is None or i_e < 1 or i_x >= len(cal):
            continue
        i_e0 = int(getattr(r, ix_col)) - hold          # signal date is always the real entry date
        if not M.iat[i_e0, j]:
            continue
        rs, rm = window_returns(R, m, r.cik, i_e, i_x)
        b = beta.iat[i_e0, j]
        rows.append({"cik": r.cik, "acc": r.accessionNumber, "ticker": r.ticker, "E": cal[i_e0], "X": cal[i_x],
                     "case": r.case, "timing": r.timing, "score": ranks["score"].iat[i_e0, j],
                     "rk_r12": ranks["r12"].iat[i_e0, j], "rk_preac": ranks["preac"].iat[i_e0, j],
                     "rk_ivol": ranks["ivol"].iat[i_e0, j], "beta": 1.0 if np.isnan(b) else float(b),
                     "r_stock": rs, "r_spy": rm, "F": r.F})
    t = pd.DataFrame(rows)
    return t


def pnl(t, hedge="beta", cost_mult=1.0, hold=HOLD):
    b = t["beta"] if hedge == "beta" else 1.0
    gross = t["r_stock"] - b * t["r_spy"]
    cost = cost_mult * (2 * COST_STOCK + 2 * COST_SPY * b + CARRY * hold * b)
    return gross, gross - cost


def cluster_t(x: pd.Series, groups: pd.Series):
    x = x.dropna()
    g = groups.loc[x.index]
    n, mu = len(x), x.mean()
    if n < 3:
        return mu, np.nan, n
    s = (x - mu).groupby(g).sum()
    G = len(s)
    var = (s ** 2).sum() / n ** 2 * G / max(G - 1, 1)
    return mu, mu / np.sqrt(var), n


def line(name, x, groups):
    mu, tt, n = cluster_t(x, groups)
    hit = (x.dropna() > 0).mean()
    return f"  {name:<44s} N {n:6,d}   mean {mu * 100:+7.3f}%   t {tt:+6.2f}   hit {hit:5.1%}"


def calendar_portfolio(cal, R, m, t, hold=HOLD):
    """Equal-weight open positions each day on daily hedged returns; entry/exit costs on E+1 / X."""
    pos = {}
    for r in t.itertuples():
        i_e = cal.get_loc(r.E)
        for k in range(1, hold + 1):
            i = i_e + k
            rd = R.at[cal[i], r.cik] - r.beta * m.iat[i] - CARRY * r.beta
            if k == 1:
                rd -= COST_STOCK + COST_SPY * r.beta
            if k == hold:
                rd -= COST_STOCK + COST_SPY * r.beta
            pos.setdefault(i, []).append(rd)
    lo, hi = cal.get_loc(t["E"].min()) + 1, cal.get_loc(t["X"].max())
    daily = pd.Series({cal[i]: (np.mean(pos[i]) if i in pos else 0.0) for i in range(lo, hi + 1)})
    ann, vol = daily.mean() * 252, daily.std() * np.sqrt(252)
    eq = (1 + daily).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    busy = (daily != 0).mean()
    return ann, vol, ann / vol if vol > 0 else np.nan, dd, busy, daily


def report(cal, R, m, M, ev, ranks, beta, ep, start, end, label):
    out = []
    p = out.append
    sel = ev[(ev["E"] >= start) & (ev["E"] <= end)]
    t = event_table(cal, R, m, M, sel, ranks, beta, ep)
    n_all = len(t)
    t = t[t["X"] <= pd.Timestamp(end) + pd.Timedelta(days=40)]
    miss = t["r_stock"].isna().sum()
    t = t.dropna(subset=["r_stock"])
    scored = t.dropna(subset=["score"])
    hot, cold = scored[scored["score"] >= 0.8], scored[scored["score"] <= 0.2]
    wk = lambda d: d["E"].dt.isocalendar().year.astype(str) + "-" + d["E"].dt.isocalendar().week.astype(str)
    p(f"=== {label}: entries {start} .. {end} ===")
    p(f"universe events {n_all:,}; dropped for missing returns {miss:,}; scored {len(scored):,} "
      f"(no score {len(t) - len(scored):,}); hot {len(hot):,}; cold {len(cold):,}")
    p(f"timing of scored events: {scored['timing'].value_counts().to_dict()}")

    g_hot, n_hot = pnl(hot)
    p("\nPRIMARY — hot events (score ≥ 0.8), beta-hedged, 5 sessions, net of costs")
    p(line("hot NET", n_hot, wk(hot)))
    p(line("hot gross", g_hot, wk(hot)))
    mu, tt, n = cluster_t(n_hot, wk(hot))
    verdict = "PASS (convincing)" if (mu > 0 and tt >= 3) else "PASS" if (mu > 0 and tt >= 2) else "FAIL"
    p(f"  VERDICT: {verdict}")

    p("\nS1 — placebo: same hot events, window 30 sessions earlier")
    pl = event_table(cal, R, m, M, sel, ranks, beta, ep, shift=PLACEBO_SHIFT)
    pl = pl.merge(hot[["acc"]], on="acc").dropna(subset=["r_stock"])
    _, n_pl = pnl(pl)
    p(line("placebo NET", n_pl, wk(pl)))
    both = hot[["acc", "E"]].assign(ev_net=n_hot.values).merge(pl[["acc"]].assign(pl_net=n_pl.values), on="acc")
    p(line("event − placebo (paired)", both["ev_net"] - both["pl_net"], wk(both)))

    p("\nS2/S3 — all scored events and cold events")
    p(line("all scored NET", pnl(scored)[1], wk(scored)))
    p(line("all scored gross", pnl(scored)[0], wk(scored)))
    p(line("cold NET", pnl(cold)[1], wk(cold)))
    p(f"  hot − cold gross (difference of means): {(g_hot.mean() - pnl(cold)[0].mean()) * 100:+.3f}%")

    p("\nS4 — single measures, top quintile (net)")
    for k in ["rk_r12", "rk_preac", "rk_ivol"]:
        s = scored[scored[k] >= 0.8]
        p(line(f"{k} ≥ 0.8", pnl(s)[1], wk(s)))

    p("\nS5 — conservative timing (exit at the session before the filing date for every event)")
    tc = event_table(cal, R, m, M, sel, ranks, beta, ep, xcol="i_X_conservative").dropna(subset=["r_stock", "score"])
    hc = tc[tc["score"] >= 0.8]
    p(line("hot NET, conservative exit", pnl(hc)[1], wk(hc)))
    t1 = event_table(cal, R, m, M, sel, ranks, beta, ep, xcol="i_X_v1").dropna(subset=["r_stock", "score"])
    h1 = t1[t1["score"] >= 0.8]
    p(line("hot NET, pre-registered v1 timing rule", pnl(h1)[1], wk(h1)))

    p("\nS6 — 10-session window")
    t10 = event_table(cal, R, m, M, sel, ranks, beta, ep, hold=10).dropna(subset=["r_stock", "score"])
    h10 = t10[t10["score"] >= 0.8]
    p(line("hot NET, 10 sessions", pnl(h10, hold=10)[1], wk(h10)))

    p("\nS7/S8 — market-adjusted hedge (beta = 1); doubled costs")
    p(line("hot NET, beta = 1", pnl(hot, hedge="one")[1], wk(hot)))
    p(line("hot NET, 2x costs", pnl(hot, cost_mult=2.0)[1], wk(hot)))

    p("\nS9 — by calendar year of entry (hot, net)")
    for y, d in hot.assign(net=n_hot).groupby(hot["E"].dt.year):
        p(line(str(y), d["net"], wk(d)))

    p("\nS10 — predictable-schedule subset (an episode start 357–371 days before F)")
    starts = ep.assign(F=ep["accepted_et"].dt.normalize()).groupby("cik")["F"].apply(lambda s: np.sort(s.to_numpy()))
    def predictable(r):
        s = starts.get(r.cik)
        if s is None:
            return False
        d = (np.datetime64(r.F) - s).astype("timedelta64[D]").astype(int)
        return bool(((d >= 357) & (d <= 371)).any())
    hp = hot[hot.apply(predictable, axis=1)]
    p(line("hot NET, predictable dates", pnl(hp)[1], wk(hp)))

    p("\nS11 — calendar-time portfolio of hot positions (net)")
    ann, vol, sh, dd, busy, daily = calendar_portfolio(cal, R, m, hot)
    p(f"  annual mean {ann * 100:+.2f}%   vol {vol * 100:.2f}%   Sharpe {sh:+.2f}   max DD {dd * 100:.1f}%   "
      f"days with positions {busy:.0%}   avg positions/day "
      f"{hot.shape[0] * HOLD / max((daily != 0).sum(), 1):.1f}")
    return "\n".join(out), hot.assign(gross=g_hot, net=n_hot), verdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oos", action="store_true")
    a = ap.parse_args()
    cal, R, m, uni, ev, ep = load()
    M = membership(cal, R, uni)
    r12, ivol, beta, preac = features(cal, R, m, ep)
    ranks = scores(M, r12, ivol, preac)
    ev = ev.dropna(subset=["E"])
    ev = ev[ev["cik"].isin(R.columns)]
    if not a.oos:
        txt, hot, verdict = report(cal, R, m, M, ev, ranks, beta, ep, IS_START, IS_END, "IN-SAMPLE")
        print(txt)
        (HERE / "run_output_is.txt").write_text(txt + "\n")
        hot.to_csv(HERE / "hot_events_is.csv", index=False)
        return
    lock = HERE / "OOS_LOCK.json"
    if lock.exists():
        raise SystemExit(f"{lock} exists: the hold-out was already opened. Not rerunning.")
    last_x = cal[-1]
    end = cal[cal.get_loc(last_x) - HOLD].strftime("%Y-%m-%d")
    txt, hot, verdict = report(cal, R, m, M, ev, ranks, beta, ep, OOS_START, end, "OUT-OF-SAMPLE 2026")
    print(txt)
    (HERE / "run_output_oos.txt").write_text(txt + "\n")
    hot.to_csv(HERE / "hot_events_oos.csv", index=False)
    code = hashlib.sha256((HERE / "run.py").read_bytes() + (HERE / "build_events.py").read_bytes()).hexdigest()
    prereg = hashlib.sha256((HERE / "PREREGISTRATION.md").read_bytes()).hexdigest()
    lock.write_text(json.dumps({"run_at": datetime.now().isoformat(timespec="seconds"), "code_sha256": code,
                                "prereg_sha256": prereg, "oos_entries": [OOS_START, end],
                                "n_hot": int(len(hot)), "mean_net": float(hot["net"].mean()),
                                "verdict_rule_applied_to_oos": verdict}, indent=2))


if __name__ == "__main__":
    main()
