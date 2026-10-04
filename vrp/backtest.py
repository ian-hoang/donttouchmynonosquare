"""VRP short straddle rebuild: features -> trade ledger -> stats. Rules: vrp/PREREGISTRATION.md.

Reads data/cache/vrp/*.pkl (made by vrp/data.py). Writes vrp/results.md and vrp/out/*.csv.
Run: uv run python vrp/backtest.py
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.special import ndtr

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from data import END, OUT, UNDERLYINGS, eightk, ns  # noqa: E402

YEAR_NS = 365 * 86400 * 10**9
HOUR_NS = 3600 * 10**9
END = pd.Timestamp(END)
OOS_START = pd.Timestamp("2024-07-01")
APR = (pd.Timestamp("2025-03-20"), pd.Timestamp("2025-05-15"))
COMM = 0.65 / 100        # $/share, per leg per side
HEDGE_HALF = 0.005       # $/share of hedge traded
K_MAIN = 1.0
N_PLACEBO = N_BOOT = 5000
BLOCK = 21
RES = HERE / "out"


# ---- Black-76 ---------------------------------------------------------------------------------------
def t_years(exp: pd.Timestamp, mark_ns: int) -> float:
    return max((ns(exp, "16:00") - mark_ns) / YEAR_NS, HOUR_NS / YEAR_NS)


def _d1(F, K, T, sig):
    sd = sig * math.sqrt(T)
    return (math.log(F / K) + 0.5 * sd * sd) / sd, sd


def b76_straddle(F, K, T, r, sig):
    d1, sd = _d1(F, K, T, sig)
    return math.exp(-r * T) * (F * (2 * ndtr(d1) - 1) - K * (2 * ndtr(d1 - sd) - 1))


def iv_straddle(V, F, K, T, r):
    if not (F > 0 and V > math.exp(-r * T) * abs(F - K) + 1e-9):
        return np.nan
    try:
        return brentq(lambda s: b76_straddle(F, K, T, r, s) - V, 1e-4, 5.0, xtol=1e-10)
    except ValueError:
        return np.nan


def delta_long_straddle(F, K, T, r, sig, S):
    """dV/dS of a long straddle; F = S e^{(r-q)T} so dF/dS = F/S."""
    d1, _ = _d1(F, K, T, sig)
    return math.exp(-r * T) * (2 * ndtr(d1) - 1) * F / S


def implied(C, P, K, T, r):
    F = K + (C - P) * math.exp(r * T)
    return F, iv_straddle(C + P, F, K, T, r)


# ---- features -------------------------------------------------------------------------------------
def features(u, rule, spot, daily, rates):
    sp = spot[u]
    r = rates.reindex(rates.index.union(sp.index)).ffill().reindex(sp.index)
    g = rule[rule.und == u].set_index("date").reindex(sp.index)
    iv = pd.Series(np.nan, index=sp.index)
    for d, x in g.dropna(subset=["K"]).iterrows():
        T = t_years(x.exp, sp.at[d, "mark_ns"])
        iv[d] = implied((x.c_bid + x.c_ask) / 2, (x.p_bid + x.p_ask) / 2, x.K, T, r[d])[1]
    ret = np.log(daily[u]["c"]).diff()
    rv = (ret.rolling(21).std() * math.sqrt(252)).shift(1).reindex(sp.index)   # closes through t-1
    vrp = iv - rv
    roll = vrp.rolling(252, min_periods=126)
    z = (vrp - roll.mean()) / roll.std()
    return pd.DataFrame({"S": sp.S, "r": r, "iv": iv, "rv": rv, "vrp": vrp, "z": z,
                         "exp": g.exp, "K": g.K, "c_bid": g.c_bid, "c_ask": g.c_ask,
                         "p_bid": g.p_bid, "p_ask": g.p_ask})


# ---- trade ledger -----------------------------------------------------------------------------------
def mark_ok(q, leg, mark_rule):
    """'prereg': the 25%-of-mid spread rule. 'fixed' (POST-HOC, added after the first run): any sane NBBO.

    The 25% rule rejects far-OTM legs quoted 0.02/0.03 near expiry, and carrying the stale, higher mid
    forward overstates the buy-back cost. 'fixed' keeps those quotes; the entry contract still uses 25%.
    """
    if q is None:
        return False
    if mark_rule == "prereg":
        return bool(q[f"{leg}_ok"])
    b, a = q[f"{leg}_bid"], q[f"{leg}_ask"]
    return bool(a > 0 and b >= 0 and a >= b)


def build_trades(u, feat, marks, spot, hold, mark_rule="prereg"):
    """Long-format daily components for every eligible Wednesday entry (the 'always' set)."""
    sessions = spot[u].index
    mk = marks[marks.und == u].set_index(["entry", "date"]).sort_index()
    elig = feat[(feat.index.weekday == 2) & feat.K.notna() & feat.z.notna()]
    rows, meta = [], []
    for t0, x in elig.iterrows():
        exit_ = eightk.session_before(x.exp) if hold == "HX" else sessions[sessions.get_loc(t0) + 5] \
            if sessions.get_loc(t0) + 5 < len(sessions) else END + pd.Timedelta(days=1)
        if exit_ > END:
            continue
        path = sessions[(sessions >= t0) & (sessions <= exit_)]
        m = mk.loc[t0] if t0 in mk.index.get_level_values(0) else pd.DataFrame()
        C, P = [(x.c_bid + x.c_ask) / 2], [(x.p_bid + x.p_ask) / 2]
        hc, hp = [(x.c_ask - x.c_bid) / 2], [(x.p_ask - x.p_bid) / 2]
        n_bad, exit_bad = 0, False
        for d in path[1:]:
            q = m.loc[d] if d in m.index else None
            for leg, mids, halves in (("c", C, hc), ("p", P, hp)):
                if mark_ok(q, leg, mark_rule):
                    mids.append((q[f"{leg}_bid"] + q[f"{leg}_ask"]) / 2)
                    halves.append((q[f"{leg}_ask"] - q[f"{leg}_bid"]) / 2)
                else:                                       # carry last valid mid and half-spread
                    mids.append(mids[-1]); halves.append(halves[-1])
                    n_bad += 1
                    exit_bad |= d == path[-1]
        C, P, hc, hp = map(np.array, (C, P, hc, hp))
        S = feat.S.reindex(path).to_numpy()
        r = feat.r.reindex(path).to_numpy()
        S0 = S[0]
        h = np.zeros(len(path))
        for i in range(len(path) - 1):
            T = t_years(x.exp, int(spot[u].at[path[i], "mark_ns"]))
            F, sig = implied(C[i], P[i], x.K, T, r[i])
            h[i] = delta_long_straddle(F, x.K, T, r[i], sig, S[i]) if np.isfinite(sig) else (h[i - 1] if i else 0.0)
        V = C + P
        opt = np.r_[0.0, V[:-1] - V[1:]]
        hedge = np.r_[0.0, h[:-1] * np.diff(S)]
        hcost = HEDGE_HALF * np.abs(np.diff(np.r_[0.0, h]))
        spread = np.zeros(len(path)); spread[0] = hc[0] + hp[0]; spread[-1] += hc[-1] + hp[-1]
        comm = np.zeros(len(path)); comm[0] += 2 * COMM; comm[-1] += 2 * COMM
        block = "IS" if t0 < OOS_START else "OOS"
        cond = bool(x.z > 0)
        rows.append(pd.DataFrame({"und": u, "entry": t0, "date": path, "opt": opt / S0, "hedge": hedge / S0,
                                  "hcost": hcost / S0, "spread": spread / S0, "comm": comm / S0}))
        meta.append({"und": u, "entry": t0, "exit": exit_, "exp": x.exp, "K": x.K, "S0": S0, "z": x.z,
                     "iv": x.iv, "rv": x.rv, "cond": cond, "block": block, "n_days": len(path) - 1,
                     "n_bad_marks": n_bad, "exit_bad": exit_bad})
    return pd.concat(rows, ignore_index=True), pd.DataFrame(meta)


def pnl(daily, k=K_MAIN, hedged=True):
    out = daily.opt - k * daily.spread - daily.comm
    return out + (daily.hedge - daily.hcost if hedged else 0.0)


def blend_series(daily, meta, select, k=K_MAIN, hedged=True, window=None):
    keep = meta[select][["und", "entry"]]
    d = daily.merge(keep, on=["und", "entry"])
    s = d.assign(p=pnl(d, k, hedged)).groupby(["date", "und"]).p.sum().unstack().reindex(columns=UNDERLYINGS)
    s = s.reindex(window).fillna(0.0)
    return 0.5 * s.sum(axis=1), s


def sharpe(s):
    s = pd.Series(s).dropna()
    return float(s.mean() / s.std(ddof=1) * math.sqrt(252)) if s.std(ddof=1) > 0 else np.nan


# ---- stats ----------------------------------------------------------------------------------------
def windows(meta, sessions):
    w = {}
    for b in ("IS", "OOS"):
        mb = meta[meta.block == b]
        w[b] = sessions[(sessions >= mb.entry.min()) & (sessions <= mb.exit.max())]
    return w


def placebo(daily, meta, win, cond_sharpe, rng, k=K_MAIN):
    mats, n_pick = {}, {}
    for u in UNDERLYINGS:
        mu = meta[(meta.und == u) & (meta.block == "OOS")].reset_index(drop=True)
        d = daily[daily.und == u].merge(mu[["entry"]].reset_index(), on="entry")
        mat = d.assign(p=pnl(d, k)).pivot_table(index="index", columns="date", values="p", aggfunc="sum")
        mats[u] = mat.reindex(columns=win).fillna(0.0).to_numpy()
        n_pick[u] = int(mu.cond.sum())
    draws = np.empty(N_PLACEBO)
    for i in range(N_PLACEBO):
        parts = [mats[u][rng.choice(len(mats[u]), n_pick[u], replace=False)].sum(0) for u in UNDERLYINGS]
        draws[i] = sharpe(0.5 * (parts[0] + parts[1]))
    return float((draws >= cond_sharpe).mean()), draws


def block_boot(a, b, rng):
    a, b = np.asarray(a), np.asarray(b)
    n = len(a)
    out = np.empty((N_BOOT, 3))
    for i in range(N_BOOT):
        starts = rng.integers(0, n, math.ceil(n / BLOCK))
        idx = ((starts[:, None] + np.arange(BLOCK)) % n).ravel()[:n]
        sa, sb = sharpe(a[idx]), sharpe(b[idx])
        out[i] = sa, sb, sa - sb
    return np.percentile(out, [2.5, 97.5], axis=0)


def spy_bh(stock, win):
    c = stock["daily"]["SPY"]["c"]
    div = stock["divs"]["SPY"].reindex(c.index).fillna(0.0)
    tr = (c + div) / c.shift(1) - 1
    rf = stock["rates"].reindex(stock["rates"].index.union(c.index)).ffill().reindex(c.index).shift(1) / 252
    tr = tr.reindex(win)
    return sharpe(tr), sharpe(tr - rf.reindex(win))


# ---- main -----------------------------------------------------------------------------------------
def run_hold(hold, feats, rule, marks, spot, stock, rng, mark_rule="prereg"):
    parts = [build_trades(u, feats[u], marks, spot, hold, mark_rule) for u in UNDERLYINGS]
    daily = pd.concat([p[0] for p in parts], ignore_index=True)
    meta = pd.concat([p[1] for p in parts], ignore_index=True)
    sessions = spot["SPY"].index
    win = windows(meta, sessions)
    res = {"hold": hold, "meta": meta, "daily": daily, "win": win}

    def sh(select, w, **kw):
        return sharpe(blend_series(daily, meta, select, window=w, **kw)[0])

    always = meta.entry.notna()
    cond = meta.cond
    tab = {}
    for b in ("IS", "OOS"):
        blk = meta.block == b
        tab[b] = {"cond": sh(cond & blk, win[b]), "always": sh(always & blk, win[b]), "spy": spy_bh(stock, win[b])}
    # ex Mar20-May15 2025 (OOS)
    w_ex = win["OOS"][(win["OOS"] < APR[0]) | (win["OOS"] > APR[1])]
    not_apr = ~meta.entry.between(*APR)
    oos = meta.block == "OOS"
    tab["OOS_exApr"] = {"cond": sh(cond & oos & not_apr, w_ex), "always": sh(oos & not_apr, w_ex),
                        "spy": spy_bh(stock, w_ex)}
    # sensitivities (OOS)
    sens = {}
    for name, kw in {"k=0.5": {"k": 0.5}, "k=0": {"k": 0.0}, "unhedged": {"hedged": False}}.items():
        sens[name] = (sh(cond & oos, win["OOS"], **kw), sh(oos, win["OOS"], **kw))
    clean = ~meta.exit_bad
    sens["drop flagged exits"] = (sh(cond & oos & clean, win["OOS"]), sh(oos & clean, win["OOS"]))
    res.update(tab=tab, sens=sens)
    # placebo + bootstrap on OOS
    p, draws = placebo(daily, meta, win["OOS"], tab["OOS"]["cond"], rng)
    a = blend_series(daily, meta, cond & oos, window=win["OOS"])[0]
    b = blend_series(daily, meta, oos, window=win["OOS"])[0]
    res.update(placebo_p=p, placebo_draws=draws, boot=block_boot(a, b, rng), series={"cond": a, "always": b})
    return res


def per_trade(meta, daily, k=K_MAIN):
    tot = daily.assign(p=pnl(daily, k)).groupby(["und", "entry"]).p.sum().rename("pnl")
    return meta.merge(tot.reset_index(), on=["und", "entry"])


def main():
    RES.mkdir(exist_ok=True)
    stock = pd.read_pickle(OUT / "stock.pkl")
    spot = pd.read_pickle(OUT / "spot.pkl")
    rule = pd.read_pickle(OUT / "rule.pkl")
    marks = pd.read_pickle(OUT / "marks.pkl")
    feats = {u: features(u, rule, spot, stock["daily"], stock["rates"]) for u in UNDERLYINGS}
    for u in UNDERLYINGS:
        feats[u].to_csv(RES / f"features_{u}.csv")
    results = {f"{h} ({mr} marks)": run_hold(h, feats, rule, marks, spot, stock, np.random.default_rng(20261003), mr)
               for mr in ("prereg", "fixed") for h in ("HX", "H5")}
    for h, res in results.items():
        tag = h.replace(" (", "_").replace(" marks)", "")
        per_trade(res["meta"], res["daily"]).to_csv(RES / f"trades_{tag}.csv", index=False)
        pd.DataFrame(res["series"]).to_csv(RES / f"oos_blend_daily_{tag}.csv")
    pd.to_pickle({"feats": feats, "results": {h: {k: v for k, v in r.items() if k != "daily"}
                                               for h, r in results.items()}}, RES / "results.pkl")
    report(feats, results, rule, marks, spot)


def fmt(x, nd=2):
    return "n/a" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


def report(feats, results, rule, marks, spot):
    L = []
    for h, res in results.items():
        t, s = res["tab"], res["sens"]
        pt = per_trade(res["meta"], res["daily"])
        L.append(f"## {h}\n")
        L.append("| Block | Conditional (Z>0) | Always short | SPY B&H (raw / minus T-bill) |\n|---|---|---|---|")
        for b in ("IS", "OOS", "OOS_exApr"):
            spy = t[b]["spy"]
            L.append(f"| {b} | {fmt(t[b]['cond'])} | {fmt(t[b]['always'])} | {fmt(spy[0])} / {fmt(spy[1])} |")
        lo, hi = res["boot"]
        L.append(f"\nOOS bootstrap 95% CI: cond [{fmt(lo[0])}, {fmt(hi[0])}], always [{fmt(lo[1])}, {fmt(hi[1])}], "
                 f"cond−always [{fmt(lo[2])}, {fmt(hi[2])}]. Placebo p = {fmt(res['placebo_p'], 3)} "
                 f"(median random-subset Sharpe {fmt(float(np.median(res['placebo_draws'])))}).\n")
        L.append("| OOS sensitivity | Conditional | Always |\n|---|---|---|")
        for k, (a, b) in s.items():
            L.append(f"| {k} | {fmt(a)} | {fmt(b)} |")
        L.append("\n| Trades | Block | Set | N | Mean P&L (bp of S0) | Hit rate | Worst (bp) |\n|---|---|---|---|---|---|---|")
        for u in UNDERLYINGS:
            for b in ("IS", "OOS"):
                for name, sel in (("cond", pt.cond), ("always", pt.entry.notna())):
                    x = pt[(pt.und == u) & (pt.block == b) & sel].pnl * 1e4
                    L.append(f"| {u} | {b} | {name} | {len(x)} | {fmt(x.mean(), 1)} | {fmt((x > 0).mean(), 2)} | {fmt(x.min(), 0)} |")
        L.append(f"\nFlagged trades (any carried-forward mark): {(res['meta'].n_bad_marks > 0).sum()} of {len(res['meta'])}; "
                 f"flagged exits: {res['meta'].exit_bad.sum()}.\n")
    diag = []
    for u in UNDERLYINGS:
        f = feats[u]
        diag.append(f"- {u}: IV median {fmt(f.iv.median())}, RV median {fmt(f.rv.median())}, VRP>0 on "
                    f"{fmt((f.vrp > 0).mean())} of days; Z defined from {f.z.first_valid_index():%Y-%m-%d}; "
                    f"share of Wednesdays with Z>0: {fmt((f.z[f.index.weekday == 2] > 0).mean())}.")
    ok = rule.dropna(subset=["K"])
    diag.append(f"- Daily rule valid on {len(ok)}/{len(rule)} underlying-days (2nd/3rd strike used {(ok.tries > 1).sum()} times).")
    diag.append(f"- Leg marks fetched: {len(marks)}; invalid call {(~marks.c_ok).sum()}, put {(~marks.p_ok).sum()}.")
    (HERE / "out" / "summary.md").write_text("\n".join(L + ["\n## Diagnostics\n"] + diag) + "\n")
    print("\n".join(L + ["", "Diagnostics"] + diag))


if __name__ == "__main__":
    main()
