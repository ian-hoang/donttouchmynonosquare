"""Residual vs classical momentum, independent rebuild. Rules: resmom/PREREGISTRATION.md.

Reads data/cache/resmom/panel.pkl (resmom/panel.py). Writes resmom/out/.
Run: uv run python resmom/backtest.py
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
MIN_PRICE, MIN_DV, MIN_VALID = 5.0, 25e6, 400
BETA_WIN, FORM_START, FORM_END = 504, 251, 21      # formation = sessions i-251 .. i-21
COSTS = [0, 5, 10, 20, 30]
MAIN_BPS = 10
N_PLACEBO = 2000
DELIST_RET = -0.30
PERIODS = {"IS 2012-16": ("2012-01-01", "2016-12-31"), "VAL 2017-21": ("2017-01-01", "2021-12-31"),
           "TEST 2022-26": ("2022-01-01", "2026-09-30"), "2017+": ("2017-01-01", "2026-09-30")}


# ---- signals --------------------------------------------------------------------------------------
def resid_scores(R: np.ndarray, X: np.ndarray, end: int, i: int) -> np.ndarray:
    """Residual momentum for columns of R; betas fit on the 504 rows ending at `end` (i, or i-21 for attack B)."""
    w0 = end - BETA_WIN + 1
    Y, Xw = R[w0:end + 1], X[w0:end + 1]
    valid = ~np.isnan(Y) & ~np.isnan(Xw).any(1)[:, None]
    E = np.full(Y.shape, np.nan)
    full = valid.all(0)
    if full.any():
        B, *_ = np.linalg.lstsq(Xw, Y[:, full], rcond=None)
        E[:, full] = Y[:, full] - Xw @ B
    for j in np.where(~full & (valid.sum(0) >= MIN_VALID))[0]:
        v = valid[:, j]
        b, *_ = np.linalg.lstsq(Xw[v], Y[v, j], rcond=None)
        E[v, j] = Y[v, j] - Xw[v] @ b
    F = E[(i - FORM_START) - w0:(i - FORM_END) - w0 + 1]
    n = (~np.isnan(F)).sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.nansum(F, 0) / np.nanstd(F, 0, ddof=1)
    s[n < 200] = np.nan
    return s


def build_signals(P, ret, rebal_pos):
    close, raw, dv = P["close"], P["close_raw"], P["dv"]
    cols = [c for c in close.columns if c != "SPY"]
    ff = P["ff"].reindex(close.index)
    X = np.column_stack([np.ones(len(ff)), ff.mkt, ff.smb, ff.hml])
    R = (ret[cols].to_numpy() - ff.rf.to_numpy()[:, None])
    C = close[cols].to_numpy()
    dv63 = dv[cols].rolling(63, min_periods=50).mean().to_numpy()
    nval = ret[cols].notna().rolling(BETA_WIN).sum().to_numpy()
    rawv = raw[cols].to_numpy()
    out = {}
    for i in rebal_pos:
        cand = np.where((rawv[i] >= MIN_PRICE) & (dv63[i] >= MIN_DV) & (nval[i] >= MIN_VALID))[0]
        mom = C[i - 21, cand] / C[i - 252, cand] - 1
        res = resid_scores(R[:, cand], X, i, i)
        res_b = resid_scores(R[:, cand], X, i - 21, i)
        rev = C[i, cand] / C[i - 21, cand] - 1
        df = pd.DataFrame({"mom": mom, "resid": res, "resid_b": res_b, "rev21": rev}, index=np.array(cols)[cand])
        out[close.index[i]] = df.dropna(subset=["mom", "resid"])
    return out


# ---- portfolio simulation -------------------------------------------------------------------------
def deciles(sig: pd.Series):
    s = sig.dropna().sort_values()
    n = len(s) // 10
    return list(s.index[-n:]), list(s.index[:n])


def simulate(legs, ret, sessions, delist_last=None):
    """legs: {rebalance date: (long tickers, short tickers)}. Returns daily gross L/S, turnover per rebalance."""
    dates = sorted(legs)
    pos = {d: sessions.get_loc(d) for d in dates}
    last = len(sessions) - 1
    gross = pd.Series(0.0, index=sessions)
    turn = {}
    held = [pd.Series(dtype=float), pd.Series(dtype=float)]
    hpr = {}
    for k, d in enumerate(dates):
        t = pos[d] + 1                               # trade at close i+1
        if t > last:
            break
        t_next = pos[dates[k + 1]] + 1 if k + 1 < len(dates) else last
        t_next = min(t_next, last)
        new = [pd.Series(1.0 / len(x), index=x) for x in legs[d]]
        to = 0.0
        for j in (0, 1):
            u = new[j].index.union(held[j].index)
            to += (new[j].reindex(u, fill_value=0) - held[j].reindex(u, fill_value=0)).abs().sum()
        turn[sessions[t + 1] if t + 1 <= last else sessions[t]] = to
        leg_r, leg_w = [], []
        for j in (0, 1):
            names = new[j].index
            r = ret[names].iloc[t + 1:t_next + 1].copy()
            if delist_last is not None:              # attack D: -30% on the session after the last bar
                for nme in names:
                    lb = delist_last.get(nme)
                    if lb is not None and t < lb < t_next:
                        r.iloc[lb + 1 - (t + 1), r.columns.get_loc(nme)] = DELIST_RET
                        r.iloc[lb + 2 - (t + 1):, r.columns.get_loc(nme)] = 0.0
            r = r.fillna(0.0).to_numpy()
            growth = np.cumprod(1 + r, axis=0)
            v = growth.mean(1)                        # EW buy-and-hold leg value
            leg_r.append(np.diff(np.r_[1.0, v]) / np.r_[1.0, v[:-1]])
            leg_w.append(pd.Series(growth[-1] / growth[-1].sum(), index=names) if len(r) else new[j])
            hpr.setdefault(d, []).append(v[-1] - 1 if len(v) else 0.0)
        gross.iloc[t + 1:t_next + 1] = leg_r[0] - leg_r[1]
        held = leg_w
    first = sessions[pos[dates[0]] + 2]
    return gross.loc[first:], pd.Series(turn), pd.Series({d: h[0] - h[1] for d, h in hpr.items()})


def net(gross, turn, bps):
    c = (turn * bps / 1e4).reindex(gross.index, fill_value=0.0)
    return gross - c


def sharpe(x, ann=252):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std(ddof=1) * math.sqrt(ann))


def maxdd(x):
    nav = (1 + x).cumprod()
    return float((nav / nav.cummax() - 1).min())


def stats(gross, turn, years):
    n = net(gross, turn, MAIN_BPS)
    return {"sharpe_gross": sharpe(gross), "sharpe_net": sharpe(n), "turnover_yr": turn.iloc[1:].sum() / years,
            "turnover_yr_incl_first": turn.sum() / years, "maxdd_net": maxdd(n),
            "ann_ret_net": float(n.mean() * 252), "ann_vol": float(n.std() * math.sqrt(252))}


# ---- diagnostics ----------------------------------------------------------------------------------
def rank_autocorr(sigs, col):
    ds = sorted(sigs)
    out = []
    for a, b in zip(ds[:-1], ds[1:]):
        x = pd.concat([sigs[a][col], sigs[b][col]], axis=1, join="inner").dropna()
        out.append(x.iloc[:, 0].rank().corr(x.iloc[:, 1].rank()))
    return float(np.mean(out))


def xs_corr(sigs, a, b):
    return float(np.mean([s[a].rank().corr(s[b].rank()) for s in sigs.values() if s[[a, b]].dropna().shape[0] > 50]))


def placebo(sigs, ret, sessions, real, rng):
    """Random rankings each month, same decile size, gross monthly HPR (EW buy-and-hold)."""
    dates = sorted(sigs)
    pos = [sessions.get_loc(d) for d in dates]
    last = len(sessions) - 1
    blocks = []
    for k, d in enumerate(dates[:-1]):
        t, t_next = pos[k] + 1, min(pos[k + 1] + 1, last)
        names = sigs[d].index
        r = ret[names].iloc[t + 1:t_next + 1].fillna(0.0).to_numpy()
        blocks.append((np.prod(1 + r, axis=0) - 1, len(names) // 10))
    sims = np.zeros((N_PLACEBO, len(blocks)))
    for m, (h, n) in enumerate(blocks):
        keys = rng.random((N_PLACEBO, len(h)))
        order = np.argsort(keys, axis=1)
        sims[:, m] = h[order[:, :n]].mean(1) - h[order[:, n:2 * n]].mean(1)
    sh = sims.mean(1) / sims.std(1, ddof=1) * math.sqrt(12)
    return float((sh >= real).mean()), float(sh.mean()), float(sh.std(ddof=1))


# ---- main -----------------------------------------------------------------------------------------
def run_variant(sigs, ret, sessions, col, delist_last=None, universe_drop=None):
    legs = {}
    for d, s in sigs.items():
        x = s[col]
        if universe_drop is not None:
            x = x.drop(universe_drop.get(d, []), errors="ignore")
        legs[d] = deciles(x)
    return simulate(legs, ret, sessions, delist_last)


def main():
    OUT.mkdir(exist_ok=True)
    P = pd.read_pickle(ROOT / "data" / "cache" / "resmom" / "panel.pkl")
    ret, ret_unf = P["ret"], P["ret_unfiltered"]
    sessions = ret.index
    me = sessions.to_series().groupby(sessions.to_period("M")).max()
    ff_end = P["ff"].index.max()
    rebal = [d for d in me if sessions.get_loc(d) >= BETA_WIN + 21 + 1 and d <= ff_end]
    rebal_pos = [sessions.get_loc(d) for d in rebal]
    sigs = build_signals(P, ret, rebal_pos)
    sigs = {d: s for d, s in sigs.items() if len(s) >= 100}
    years = (len(sigs) - 1) / 12
    print(f"rebalances {len(sigs)}: {min(sigs):%Y-%m-%d}..{max(sigs):%Y-%m-%d}; universe "
          f"{len(sigs[min(sigs)])} -> {len(sigs[max(sigs)])}")

    res = {}
    for col in ("mom", "resid", "resid_b"):
        g, t, h = run_variant(sigs, ret, sessions, col)
        res[col] = {"gross": g, "turn": t, "hpr": h, **stats(g, t, years)}
    # attack C1: no bad-return filter (signals and holding returns)
    sigs_unf = build_signals(P, ret_unf, rebal_pos)
    sigs_unf = {d: s for d, s in sigs_unf.items() if d in sigs}
    for col in ("mom", "resid"):
        g, t, h = run_variant(sigs_unf, ret_unf, sessions, col)
        res[f"{col} | unfiltered returns"] = {"gross": g, "turn": t, **stats(g, t, years)}
    # attack C2: drop stocks with any filtered return in their 504-day window
    bad = ((ret_unf.notna() & ret.isna()).astype(int).rolling(BETA_WIN).sum() > 0)
    drop = {d: list(bad.columns[bad.loc[d].to_numpy()]) for d in sigs}
    for col in ("mom", "resid"):
        g, t, h = run_variant(sigs, ret, sessions, col, universe_drop=drop)
        res[f"{col} | drop flagged stocks"] = {"gross": g, "turn": t, **stats(g, t, years)}
    # attack D: -30% after the last bar for stocks whose bars end mid-holding
    lastbar = ret.notna()[::-1].idxmax()
    lastpos = {c: sessions.get_loc(d) for c, d in lastbar.items() if d < sessions[-1]}
    for col in ("mom", "resid"):
        g, t, h = run_variant(sigs, ret, sessions, col, delist_last=lastpos)
        res[f"{col} | delist -30%"] = {"gross": g, "turn": t, **stats(g, t, years)}

    rng = np.random.default_rng(20261003)
    real_m = sharpe(res["resid"]["hpr"].iloc[:-1], 12)
    p, mu, sd = placebo(sigs, ret, sessions, real_m, rng)
    diag = {
        "rank autocorr mom": rank_autocorr(sigs, "mom"), "rank autocorr resid": rank_autocorr(sigs, "resid"),
        "rank autocorr resid_b": rank_autocorr(sigs, "resid_b"),
        "xs corr resid vs last-21d return": xs_corr(sigs, "resid", "rev21"),
        "xs corr resid_b vs last-21d return": xs_corr(sigs, "resid_b", "rev21"),
        "xs corr mom vs last-21d return": xs_corr(sigs, "mom", "rev21"),
        "xs corr resid vs mom": xs_corr(sigs, "resid", "mom"),
        "placebo real monthly gross Sharpe": real_m, "placebo p": p, "placebo null mean": mu, "placebo null sd": sd,
        "bad returns filtered": int((ret_unf.notna() & ret.isna()).sum().sum()),
    }
    pd.to_pickle({"res": res, "diag": diag, "sigs": sigs}, OUT / "results.pkl")
    report(res, diag, sigs)


def report(res, diag, sigs):
    f = lambda x, n=2: f"{x:.{n}f}"
    L = ["| Variant | Sharpe gross | Sharpe net 10bp | Turnover/yr (excl. first) | MaxDD net | Ann. ret net | Ann. vol |",
         "|---|---|---|---|---|---|---|"]
    for k, v in res.items():
        L.append(f"| {k} | {f(v['sharpe_gross'])} | {f(v['sharpe_net'])} | {f(v['turnover_yr'], 1)} | "
                 f"{v['maxdd_net']:.0%} | {v['ann_ret_net']:.1%} | {v['ann_vol']:.1%} |")
    L += ["", "| Net Sharpe by cost (bps) | " + " | ".join(map(str, COSTS)) + " |", "|---|" + "---|" * len(COSTS)]
    for col in ("mom", "resid", "resid_b"):
        g, t = res[col]["gross"], res[col]["turn"]
        L.append(f"| {col} | " + " | ".join(f(sharpe(net(g, t, c))) for c in COSTS) + " |")
    L += ["", "| Net Sharpe (10 bp) by period | " + " | ".join(PERIODS) + " |", "|---|" + "---|" * len(PERIODS)]
    for col in ("mom", "resid", "resid_b"):
        n = net(res[col]["gross"], res[col]["turn"], MAIN_BPS)
        L.append(f"| {col} | " + " | ".join(f(sharpe(n.loc[a:b])) for a, b in PERIODS.values()) + " |")
    L += ["", "| Diagnostic | Value |", "|---|---|"] + [f"| {k} | {f(v, 3) if isinstance(v, float) else v} |" for k, v in diag.items()]
    sizes = pd.Series({d: len(s) for d, s in sigs.items()})
    L.append(f"\nUniverse: {sizes.iloc[0]} ({sizes.index[0]:%Y-%m}) -> {sizes.iloc[-1]} ({sizes.index[-1]:%Y-%m}); "
             f"{len(sizes)} rebalances; median {int(sizes.median())}.")
    (OUT / "summary.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
