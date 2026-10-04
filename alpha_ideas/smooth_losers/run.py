"""Idea 4 — Smooth losers at month-end (pre-registered in alpha_ideas/PREREGISTRATION.md).

Hypothesis: month-end "dash for cash" sellers dump *obvious* (smooth-trend) losers, so the PreTOM loser effect of
Nathan, Suominen & Tasa (2026) should be concentrated in high trend-clarity (Cai, Li & Keasey 2026) losers.

Primary test: per holding month, DiD = mean daily (smooth losers − rough losers) inside PreTOM minus the same outside
PreTOM. Mean over 2007-01..2026-09, month-level t. Prediction < 0. Spec choices are listed in results.md.

Needs the cache written by fetch_data.py. Run:  uv run python alpha_ideas/smooth_losers/run.py
Outputs (this folder): monthly_primary.csv, monthly_trades.csv, daily_profile.csv, robustness.csv, placebo.csv,
replication.csv, yearly.csv, cumulative_in_window.png. Summary tables are printed to stdout.
"""
from __future__ import annotations

import io
import time
import warnings
import zipfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CACHE = ROOT / "data" / "cache" / "massive_grouped"
FF_ZIP = ROOT / "data" / "cache" / "F-F_Momentum_Factor_daily_CSV.zip"

# ---- Pre-registered parameters (do not change after seeing results) -----------------------------
FIRST_MONTH, LAST_MONTH = pd.Period("2007-01", "M"), pd.Period("2026-09", "M")
DATA_END = pd.Timestamp("2026-09-30")
T1_FROM = pd.Period("2024-06", "M")       # [L-8, L-3] from June 2024 on, [L-9, L-4] before
PRICE_MIN = 5.0                            # on the unadjusted close at formation
ADV_DAYS = 63
TOP_N = 1000
N_BINS = 10
MIN_TC_OBS = 200
MAX_GAP = 5                                # max missing trading days bridged by a daily return
MAX_ABS_RET = 1.0                          # drop daily returns with |r| > 100%
MIN_NAMES = 5                              # a month needs >= 5 names in every portfolio a test uses
COST_SIDE = 0.0010                         # 10 bps per side per $ traded per leg (20 bps round trip per leg)
COST_SIDE_STRICT = 0.0020                  # sensitivity: 20 bps per side per leg (80 bps / month in-window)

PORTS = ["W", "Lo", "SW", "SL", "RW", "RL", "U"]   # winners, losers, smooth/rough of each, universe


# ---- Data ---------------------------------------------------------------------------------------
def load_panel():
    t0 = time.time()
    tick_ref = pd.read_parquet(CACHE / "tickers_cs.parquet")
    cs = set(tick_ref["ticker"])
    frames, all_dates = [], set()
    for f in sorted(CACHE.glob("grouped_*.parquet")):
        g = pd.read_parquet(f, columns=["date", "ticker", "close", "volume", "close_raw"])
        all_dates.update(pd.DatetimeIndex(g["date"].unique()))
        frames.append(g[g["ticker"].isin(cs)])
    df = pd.concat(frames, ignore_index=True)
    dates = pd.DatetimeIndex(sorted(all_dates)).astype("datetime64[ns]")
    dates = dates[dates <= DATA_END]
    df["date"] = df["date"].astype("datetime64[ns]")
    df = df[df["date"] <= DATA_END]
    tick = pd.Index(sorted(df["ticker"].unique()))
    ri, ci = dates.get_indexer(df["date"]), tick.get_indexer(df["ticker"])
    T, N = len(dates), len(tick)
    close = np.full((T, N), np.nan)
    close[ri, ci] = df["close"].to_numpy(float)
    raw = np.full((T, N), np.nan, dtype=np.float32)
    raw[ri, ci] = df["close_raw"].to_numpy(float)
    dv = np.zeros((T, N), dtype=np.float32)
    dv[ri, ci] = (df["close"] * df["volume"]).to_numpy(float)
    per_day = pd.Series(np.bincount(ri, minlength=T), index=dates)
    info = {
        "cs_ref_rows": len(tick_ref), "cs_ref_unique": tick_ref["ticker"].nunique(),
        "cs_ref_active": int(tick_ref["active"].sum()), "cs_ref_inactive": int((~tick_ref["active"]).sum()),
        "cs_tickers_seen": N, "trading_days": T, "first_day": dates[0].date(), "last_day": dates[-1].date(),
        "rows": len(df), "raw_close_missing": float(df["close_raw"].isna().mean()),
    }
    roll_med = per_day.rolling(21, center=True, min_periods=5).median()
    info["thin_days"] = per_day[per_day < 0.8 * roll_med]
    info["per_year_cs_per_day"] = per_day.groupby(per_day.index.year).mean().round(0)
    print(f"loaded {len(df):,} CS rows, {N:,} tickers, {T:,} days in {time.time() - t0:.0f}s")
    return dates, tick, close, raw, dv, info


def daily_returns(close):
    prev = np.vstack([np.full((1, close.shape[1]), np.nan), close[:-1]])
    prev = pd.DataFrame(prev).ffill(limit=MAX_GAP).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        R = close / prev - 1.0
    has_close = ~np.isnan(close)
    seen_before = np.vstack([np.zeros((1, close.shape[1]), bool),
                             np.maximum.accumulate(has_close, axis=0)[:-1]])
    stats = {"gap_dropped": int((has_close & seen_before & np.isnan(prev)).sum()),
             "big_dropped": int((np.abs(R) > MAX_ABS_RET).sum()),
             "returns_total": int(np.isfinite(R).sum())}
    R[np.abs(R) > MAX_ABS_RET] = np.nan
    return R, stats


def last_valid(mat, row, lookback=MAX_GAP):
    out = mat[row].copy()
    for j in range(1, lookback + 1):
        miss = np.isnan(out)
        if not miss.any():
            break
        out[miss] = mat[row - j][miss]
    return out


def trend_r2(Y):
    """R^2 of OLS of each column of Y on the row index, skipping NaNs. Returns (r2, n_obs)."""
    mask = ~np.isnan(Y)
    n = mask.sum(0)
    x = np.arange(Y.shape[0], dtype=float)[:, None] * mask
    with np.errstate(invalid="ignore", divide="ignore"):
        xbar = x.sum(0) / n
        ybar = np.nansum(Y, 0) / n
        xc = np.where(mask, x - xbar, 0.0)
        yc = np.where(mask, Y - ybar, 0.0)
        sxy, sxx, syy = (xc * yc).sum(0), (xc * xc).sum(0), (yc * yc).sum(0)
        r2 = sxy ** 2 / (sxx * syy)
    return r2, n


# ---- Formation ----------------------------------------------------------------------------------
def form(close, raw, dv, mend, mi, top_n, n_bins):
    """Portfolios for holding month index mi (formation at the end of month mi-1)."""
    F, a, b = mend[mi - 1], mend[mi - 13], mend[mi - 2]
    ok = ~np.isnan(close[F]) & (raw[F] >= PRICE_MIN)
    adv = dv[F - ADV_DAYS + 1:F + 1].sum(0, dtype=np.float64) / ADV_DAYS
    cand = np.where(ok)[0]
    top = cand[np.argsort(-adv[cand], kind="stable")[:top_n]]
    pa, pb = last_valid(close, a)[top], last_valid(close, b)[top]
    with np.errstate(invalid="ignore", divide="ignore"):
        mom = pb / pa - 1.0
    tc, nobs = trend_r2(close[a:b + 1, top])
    valid = np.isfinite(mom) & (nobs >= MIN_TC_OBS) & np.isfinite(tc)
    u, mom, tc = top[valid], mom[valid], tc[valid]
    bins = pd.qcut(pd.Series(mom).rank(method="first"), n_bins, labels=False).to_numpy()
    smooth = tc > np.median(tc)
    hi, lo = bins == n_bins - 1, bins == 0
    members = {"W": u[hi], "Lo": u[lo], "SW": u[hi & smooth], "SL": u[lo & smooth],
               "RW": u[hi & ~smooth], "RL": u[lo & ~smooth], "U": u}
    meta = {"n_top": len(top), "n_univ": len(u), "med_tc": float(np.median(tc)),
            "tc_losers": float(np.mean(tc[lo])), "tc_winners": float(np.mean(tc[hi]))}
    return members, adv, meta


def port_returns(R, rows, members, w=None):
    sub = R[rows][:, members]
    if w is None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.nanmean(sub, axis=1)
    valid = ~np.isnan(sub)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.nansum(sub * w, axis=1) / (valid * w).sum(1)


def build(R, close, raw, dv, dates, mstart, mend, months, top_n, n_bins, weighting):
    """Daily panel of portfolio returns for every holding month + formation stats."""
    out_rows, meta_rows, members_by_month = [], [], {}
    for mi, m in enumerate(months):
        if m < FIRST_MONTH or m > LAST_MONTH:
            continue
        members, adv, meta = form(close, raw, dv, mend, mi, top_n, n_bins)
        rows = np.arange(mstart[mi], mend[mi] + 1)
        rec = {"date": dates[rows], "month": m, "k": mend[mi] - rows}
        for p in PORTS:
            idx = members[p]
            w = adv[idx] if weighting == "dv" else None
            rec[p] = port_returns(R, rows, idx, w) if len(idx) else np.full(len(rows), np.nan)
        out_rows.append(pd.DataFrame(rec))
        meta.update({f"n_{p}": len(members[p]) for p in PORTS})
        meta["month"] = m
        meta_rows.append(meta)
        members_by_month[m] = members
    panel = pd.concat(out_rows, ignore_index=True)
    meta = pd.DataFrame(meta_rows).set_index("month")
    return panel, meta, members_by_month


# ---- Windows, tests, performance ----------------------------------------------------------------
def pretom_flag(panel, t1_shift=True):
    k = panel["k"].to_numpy()
    old = (k >= 4) & (k <= 9)
    if not t1_shift:
        return old
    new = (k >= 3) & (k <= 8)
    return np.where((panel["month"] >= T1_FROM).to_numpy(), new, old)


def tstat(x):
    x = pd.Series(x).dropna()
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x))), len(x)


def did_test(panel, meta, flag, a, b=None, need=()):
    s = panel[a] - panel[b] if b else panel[a]
    good = pd.Series(True, index=meta.index)
    for p in need:
        good &= meta[f"n_{p}"] >= MIN_NAMES
    df = pd.DataFrame({"s": s, "in": flag, "month": panel["month"]})
    inn = df[df["in"]].groupby("month")["s"].mean()
    out = df[~df["in"]].groupby("month")["s"].mean()
    res = pd.DataFrame({"in": inn, "out": out})
    res = res[res.index.isin(good[good].index)]
    res["did"] = res["in"] - res["out"]
    t, n = tstat(res["did"])
    return res, {"mean_did": res["did"].mean(), "t": t, "N": n, "mean_in": res["in"].mean(),
                 "mean_out": res["out"].mean()}


def window_trade(panel, flag, long, short):
    df = pd.DataFrame({"month": panel["month"], "L": panel[long].fillna(0.0), "S": panel[short].fillna(0.0)})[flag]
    g = df.groupby("month")
    return (g["L"].apply(lambda r: np.prod(1 + r)) - 1) - (g["S"].apply(lambda r: np.prod(1 + r)) - 1)


def leg_turnover(members_by_month, leg):
    to, prev = {}, None
    for m, mem in members_by_month.items():
        new = set(mem[leg])
        if prev is None:
            to[m] = 1.0
        else:
            wn, wo = 1 / len(new), 1 / len(prev)
            both = new & prev
            to[m] = len(both) * abs(wn - wo) + len(new - prev) * wn + len(prev - new) * wo
        prev = new
    return pd.Series(to)


def perf(r):
    r = pd.Series(r).dropna()
    mu, sd, n = r.mean(), r.std(ddof=1), len(r)
    eq = (1 + r).cumprod()
    return {"ann_ret": 12 * mu, "ann_vol": np.sqrt(12) * sd, "sharpe": (12 * mu) / (np.sqrt(12) * sd),
            "t": mu / (sd / np.sqrt(n)), "max_dd": float((eq / eq.cummax() - 1).min()), "N": n,
            "hit": float((r > 0).mean())}


def fmt_perf(name, p):
    return (f"| {name} | {p['ann_ret']:+.2%} | {p['ann_vol']:.2%} | {p['sharpe']:+.2f} | {p['t']:+.2f} | "
            f"{p['max_dd']:.1%} | {p['hit']:.0%} | {p['N']} |")


def load_ff():
    with zipfile.ZipFile(FF_ZIP) as z:
        txt = z.read(z.namelist()[0]).decode("latin-1")
    rows = []
    for line in txt.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 2 and parts[0].isdigit() and len(parts[0]) == 8:
            try:
                rows.append((pd.Timestamp(parts[0]), float(parts[1]) / 100))
            except ValueError:
                pass
    return pd.Series(dict(rows)).sort_index()


# ---- Main ---------------------------------------------------------------------------------------
def main():
    dates, tick, close, raw, dv, info = load_panel()
    R, rstats = daily_returns(close)
    months = dates.to_period("M")
    um = months.unique()
    pos = pd.Series(np.arange(len(dates)), index=months)
    mstart = np.array([pos[m].min() for m in um])
    mend = np.array([pos[m].max() for m in um])
    months = pd.PeriodIndex(um)

    print("\n## Data")
    for k_, v in info.items():
        if k_ not in ("thin_days", "per_year_cs_per_day"):
            print(f"- {k_}: {v}")
    print(f"- daily returns kept: {rstats['returns_total'] - rstats['big_dropped']:,}; dropped |r|>100%: "
          f"{rstats['big_dropped']:,}; dropped (previous close > {MAX_GAP} trading days old): "
          f"{rstats['gap_dropped']:,}")
    print(f"- thin days (CS ticker count < 80% of 21-day median): {len(info['thin_days'])} "
          f"{[str(d.date()) for d in info['thin_days'].index[:20]]}")
    print("- average CS tickers per day by year:", info["per_year_cs_per_day"].to_dict())

    configs = {
        "base": dict(top_n=TOP_N, n_bins=N_BINS, weighting="ew"),
        "dv_weights": dict(top_n=TOP_N, n_bins=N_BINS, weighting="dv"),
        "top500": dict(top_n=500, n_bins=N_BINS, weighting="ew"),
        "quintiles": dict(top_n=TOP_N, n_bins=5, weighting="ew"),
    }
    built = {}
    for name, cfg in configs.items():
        t0 = time.time()
        built[name] = build(R, close, raw, dv, dates, mstart, mend, months, **cfg)
        print(f"built {name} in {time.time() - t0:.0f}s")

    panel, meta, members = built["base"]
    flag = pretom_flag(panel)

    # Universe diagnostics
    print("\n## Formation diagnostics (base)")
    print(f"- holding months: {len(meta)} ({meta.index[0]} .. {meta.index[-1]})")
    print(f"- names after price+ADV screen: mean {meta['n_top'].mean():.0f}; after momentum/TC data requirement: "
          f"mean {meta['n_univ'].mean():.0f} (min {meta['n_univ'].min()}, max {meta['n_univ'].max()})")
    for p in ["W", "Lo", "SW", "SL", "RW", "RL"]:
        print(f"- n_{p}: mean {meta[f'n_{p}'].mean():.1f}, min {meta[f'n_{p}'].min()}")
    print(f"- median TC (universe): mean {meta['med_tc'].mean():.3f}; mean TC losers {meta['tc_losers'].mean():.3f},"
          f" winners {meta['tc_winners'].mean():.3f}")
    extreme = int((panel[["W", "Lo", "SW", "SL", "RW", "RL"]].abs() > 0.2).sum().sum())
    print(f"- portfolio-days with |return| > 20%: {extreme}")

    # ---- Replication of the published PreTOM concentration (plain WML) ----
    panel["WML"] = panel["W"] - panel["Lo"]
    panel["Lo_U"] = panel["Lo"] - panel["U"]
    panel["W_U"] = panel["W"] - panel["U"]
    rep_rows = []
    for nm, a in [("WML (winners - losers)", "WML"), ("Losers (raw)", "Lo"), ("Winners (raw)", "W"),
                  ("Losers - universe", "Lo_U"), ("Winners - universe", "W_U"), ("Universe EW", "U")]:
        _, st = did_test(panel, meta, flag, a, need=("W", "Lo"))
        share = None
        if a == "WML":
            ok = panel["WML"].notna()
            share = panel.loc[ok & flag, "WML"].sum() / panel.loc[ok, "WML"].sum()
        rep_rows.append({"series": nm, "in_bp_day": 1e4 * st["mean_in"], "out_bp_day": 1e4 * st["mean_out"],
                         "diff_bp_day": 1e4 * st["mean_did"], "t": st["t"], "N": st["N"],
                         "share_of_total_in_window": share, "source": "Massive (ours)"})

    # Ken French daily momentum (CRSP, value-weighted, daily-rebalanced) as a reference point
    ff = load_ff()
    ffp = panel[["date", "month", "k", "WML"]].copy()
    ffp["FF"] = ffp["date"].map(ff)
    ffp = ffp[ffp["FF"].notna()]
    corr = ffp[["WML", "FF"]].corr().iloc[0, 1]
    ff_flag = pretom_flag(ffp)
    df_ff = pd.DataFrame({"s": ffp["FF"].to_numpy(), "in": ff_flag, "month": ffp["month"].to_numpy()})
    ff_in = df_ff[df_ff["in"]].groupby("month")["s"].mean()
    ff_out = df_ff[~df_ff["in"]].groupby("month")["s"].mean()
    ff_d = (ff_in - ff_out).dropna()
    t_ff, n_ff = tstat(ff_d)
    rep_rows.append({"series": "Ken French Mom factor (CRSP)", "in_bp_day": 1e4 * ff_in.mean(),
                     "out_bp_day": 1e4 * ff_out.mean(), "diff_bp_day": 1e4 * ff_d.mean(), "t": t_ff, "N": n_ff,
                     "share_of_total_in_window": df_ff.loc[df_ff["in"], "s"].sum() / df_ff["s"].sum(),
                     "source": "Ken French library"})
    rep = pd.DataFrame(rep_rows)
    rep.to_csv(HERE / "replication.csv", index=False, float_format="%.4f")
    print(f"\n## Replication: PreTOM concentration (daily returns, bp/day; month-level paired t)\n"
          f"corr(our daily WML, Ken French daily Mom) = {corr:.3f} over {len(ffp):,} days "
          f"({ffp['date'].min().date()}..{ffp['date'].max().date()})")
    print("| series | in PreTOM | outside | in − out | t | N | share of total in window |")
    print("|---|---|---|---|---|---|---|")
    for r in rep_rows:
        sh = "" if r["share_of_total_in_window"] is None else f"{r['share_of_total_in_window']:.0%}"
        print(f"| {r['series']} | {r['in_bp_day']:+.1f} | {r['out_bp_day']:+.1f} | {r['diff_bp_day']:+.1f} | "
              f"{r['t']:+.2f} | {r['N']} | {sh} |")

    # ---- PRIMARY TEST ----
    prim, pst = did_test(panel, meta, flag, "SL", "RL", need=("SL", "RL"))
    print("\n## PRIMARY TEST: DiD = (smooth losers − rough losers) in PreTOM − same outside; prediction < 0")
    print(f"N months = {pst['N']}, mean in-window spread = {1e4 * pst['mean_in']:+.2f} bp/day, "
          f"mean out-of-window spread = {1e4 * pst['mean_out']:+.2f} bp/day, "
          f"mean DiD = {1e4 * pst['mean_did']:+.2f} bp/day, t = {pst['t']:+.2f}")

    # ---- TRADE ----
    tr = pd.DataFrame({
        "SWML_in_gross": window_trade(panel, flag, "SW", "SL"),
        "WML_in_gross": window_trade(panel, flag, "W", "Lo"),
        "WML_all_gross": window_trade(panel, np.ones(len(panel), bool), "W", "Lo"),
    })
    to = leg_turnover(members, "W") + leg_turnover(members, "Lo")
    tr["WML_all_turnover"] = to
    tr["SWML_in_net"] = tr["SWML_in_gross"] - 4 * COST_SIDE
    tr["WML_in_net"] = tr["WML_in_gross"] - 4 * COST_SIDE
    tr["WML_all_net"] = tr["WML_all_gross"] - COST_SIDE * tr["WML_all_turnover"]
    tr["SWML_in_net_strict"] = tr["SWML_in_gross"] - 4 * COST_SIDE_STRICT
    tr["WML_in_net_strict"] = tr["WML_in_gross"] - 4 * COST_SIDE_STRICT
    tr["WML_all_net_strict"] = tr["WML_all_gross"] - COST_SIDE_STRICT * tr["WML_all_turnover"]
    # Each strategy is dropped only in months where a portfolio *it* uses has < MIN_NAMES names
    # (bug fix after run 1: plain WML had also been dropped in months with few smooth names).
    ok_smooth = (meta[["n_SW", "n_SL"]] >= MIN_NAMES).all(axis=1).reindex(tr.index)
    ok_plain = (meta[["n_W", "n_Lo"]] >= MIN_NAMES).all(axis=1).reindex(tr.index)
    for c in [c for c in tr.columns if c.startswith("SWML")]:
        tr.loc[~ok_smooth, c] = np.nan
    for c in [c for c in tr.columns if c.startswith("WML")]:
        tr.loc[~ok_plain, c] = np.nan
    tr.index.name = "month"
    tr.to_csv(HERE / "monthly_trades.csv", float_format="%.6f")
    print(f"\n## TRADE (monthly returns per $1 long + $1 short; in-window cost {4 * COST_SIDE:.2%}/month; "
          f"WML-all cost on turnover, mean turnover {tr['WML_all_turnover'].mean():.2f} legs-$/month)")
    print("| strategy | ann. return | ann. vol | Sharpe | t | max DD | % months > 0 | N |")
    print("|---|---|---|---|---|---|---|---|")
    perfs = {}
    for c in ["SWML_in_gross", "SWML_in_net", "WML_in_gross", "WML_in_net", "WML_all_gross", "WML_all_net",
              "SWML_in_net_strict", "WML_in_net_strict", "WML_all_net_strict"]:
        perfs[c] = perf(tr[c])
        print(fmt_perf(c, perfs[c]))

    yearly = tr[["SWML_in_gross", "SWML_in_net", "WML_in_gross", "WML_in_net", "WML_all_gross", "WML_all_net"]]
    yearly = yearly.groupby(yearly.index.year).apply(lambda d: (1 + d.fillna(0)).prod() - 1)  # skipped month = cash
    yearly.index.name = "year"
    yearly.to_csv(HERE / "yearly.csv", float_format="%.4f")
    print("\n## Per-year (compounded) returns")
    print("| year | smooth WML in-window gross | net | plain WML in-window gross | net | WML all month gross | net |")
    print("|---|---|---|---|---|---|---|")
    for y, r in yearly.iterrows():
        print(f"| {y} | " + " | ".join(f"{v:+.1%}" for v in r.to_numpy()) + " |")

    # ---- ROBUSTNESS ----
    rob = []

    def add(name, pnl, mt, flg, b_mem=None):
        _, st = did_test(pnl, mt, flg, "SL", "RL", need=("SL", "RL"))
        g = window_trade(pnl, flg, "SW", "SL")
        g = g[g.index.isin(mt.index[(mt[["n_SW", "n_SL"]] >= MIN_NAMES).all(axis=1)])]
        pg, pn = perf(g), perf(g - 4 * COST_SIDE)
        rob.append({"variant": name, "N": st["N"], "did_bp_day": 1e4 * st["mean_did"], "t_did": st["t"],
                    "in_bp_day": 1e4 * st["mean_in"], "out_bp_day": 1e4 * st["mean_out"],
                    "trade_gross_ann": pg["ann_ret"], "trade_net_ann": pn["ann_ret"], "trade_net_sharpe": pn["sharpe"],
                    "trade_net_t": pn["t"]})

    add("base (pre-registered)", panel, meta, flag)
    add("dollar-volume weights", built["dv_weights"][0], built["dv_weights"][1], pretom_flag(built["dv_weights"][0]))
    add("no T+1 shift", panel, meta, pretom_flag(panel, t1_shift=False))
    add("top-500 universe", built["top500"][0], built["top500"][1], pretom_flag(built["top500"][0]))
    add("momentum quintiles", built["quintiles"][0], built["quintiles"][1], pretom_flag(built["quintiles"][0]))
    pre = panel["month"] < T1_FROM
    add("descriptive: months before Jun-2024", panel[pre].reset_index(drop=True), meta[meta.index < T1_FROM],
        flag[pre.to_numpy()])
    add("descriptive: months from Jun-2024 (T+1)", panel[~pre].reset_index(drop=True), meta[meta.index >= T1_FROM],
        flag[~pre.to_numpy()])
    rob = pd.DataFrame(rob)
    rob.to_csv(HERE / "robustness.csv", index=False, float_format="%.4f")
    print("\n## Robustness (primary DiD and the smooth-WML in-window trade, net = 40 bps/month)")
    print("| variant | N | DiD bp/day | t | in bp/day | out bp/day | trade gross ann. | trade net ann. | net Sharpe |"
          " net t |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for _, r in rob.iterrows():
        print(f"| {r['variant']} | {r['N']} | {r['did_bp_day']:+.2f} | {r['t_did']:+.2f} | {r['in_bp_day']:+.2f} | "
              f"{r['out_bp_day']:+.2f} | {r['trade_gross_ann']:+.2%} | {r['trade_net_ann']:+.2%} | "
              f"{r['trade_net_sharpe']:+.2f} | {r['trade_net_t']:+.2f} |")

    # ---- PLACEBO: every 6-day clock window [L-k-5, L-k] ----
    pl = []
    k = panel["k"].to_numpy()
    for kk in range(0, 13):
        f_ = (k >= kk) & (k <= kk + 5)
        _, st = did_test(panel, meta, f_, "SL", "RL", need=("SL", "RL"))
        _, sw = did_test(panel, meta, f_, "WML", need=("W", "Lo"))
        pl.append({"window": f"[L-{kk + 5}, L-{kk}]", "k": kk, "did_SL_RL_bp_day": 1e4 * st["mean_did"],
                   "t_SL_RL": st["t"], "did_WML_bp_day": 1e4 * sw["mean_did"], "t_WML": sw["t"], "N": st["N"]})
    pl = pd.DataFrame(pl)
    pl.to_csv(HERE / "placebo.csv", index=False, float_format="%.4f")
    print("\n## Placebo scan: same DiD for every 6-day window (k = 4 is the pre-T+1 PreTOM)")
    print("| window | smooth−rough losers DiD bp/day | t | WML DiD bp/day | t |")
    print("|---|---|---|---|---|")
    for _, r in pl.iterrows():
        print(f"| {r['window']} | {r['did_SL_RL_bp_day']:+.2f} | {r['t_SL_RL']:+.2f} | {r['did_WML_bp_day']:+.2f} | "
              f"{r['t_WML']:+.2f} |")

    # ---- Day-by-day profile ----
    panel["SL_RL"] = panel["SL"] - panel["RL"]
    panel["SWML"] = panel["SW"] - panel["SL"]
    prof = panel[panel["k"] <= 22].groupby("k")[["WML", "Lo_U", "W_U", "SL_RL", "SWML", "SL", "RL", "U"]].mean() * 1e4
    prof["n_months"] = panel[panel["k"] <= 22].groupby("k").size()
    prof.to_csv(HERE / "daily_profile.csv", float_format="%.3f")

    # ---- Monthly primary series ----
    mp = meta[["n_top", "n_univ", "n_W", "n_Lo", "n_SW", "n_SL", "n_RL", "med_tc"]].join(
        prim.rename(columns={"in": "SL_RL_in", "out": "SL_RL_out", "did": "SL_RL_did"}))
    mp.index.name = "month"
    mp.to_csv(HERE / "monthly_primary.csv", float_format="%.6f")

    # ---- Chart ----
    plot_cumulative(tr)

    # ---- Verdict ----
    net_ok = perfs["SWML_in_net"]["ann_ret"] > 0
    t = pst["t"]
    if t <= -3 and net_ok:
        verdict = "PASS (convincing: t <= -3 and net > 0)"
    elif t <= -2 and net_ok:
        verdict = "WORTH A SECOND LOOK (t between -3 and -2, net > 0)"
    else:
        verdict = "FAIL"
    print(f"\n## VERDICT: {verdict}  (primary t = {t:+.2f}; trade net ann = {perfs['SWML_in_net']['ann_ret']:+.2%})")


def plot_cumulative(tr):
    ink, ink2, grid, surf = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
    blue, orange, aqua = "#2a78d6", "#eb6834", "#1baf7a"
    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=150, facecolor=surf)
    ax.set_facecolor(surf)
    x = tr.index.to_timestamp(how="end")
    lines = [("SWML_in_net", blue, "-", "Smooth WML, PreTOM only (net)"),
             ("SWML_in_gross", blue, "--", "Smooth WML, PreTOM only (gross)"),
             ("WML_in_net", orange, "-", "Plain WML, PreTOM only (net)"),
             ("WML_all_net", aqua, "-", "Plain WML, all month (net)")]
    for col, c, ls, lab in lines:
        eq = (1 + tr[col].fillna(0)).cumprod()
        ax.plot(x, eq, color=c, ls=ls, lw=2 if ls == "-" else 1.4, label=lab)
        ax.annotate(f"{eq.iloc[-1]:.2f}", (x[-1], eq.iloc[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=8, color=ink2)
    ax.set_yscale("log")
    ticks = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 6]
    ax.yaxis.set_major_locator(matplotlib.ticker.FixedLocator(ticks))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.axhline(1, color=ink2, lw=0.8)
    ax.grid(True, color=grid, lw=0.6)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    for s in ["left", "bottom"]:
        ax.spines[s].set_color(grid)
    ax.tick_params(colors=ink2, labelsize=9)
    ax.set_ylabel(r"Growth of \$1 (log scale)", color=ink2)
    ax.set_title(r"Momentum strategies, 2007-01 to 2026-09: \$1 long + \$1 short, monthly compounding"
                 "\n(months a strategy skips for lack of names are shown as cash)",
                 color=ink, fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=9, labelcolor=ink, loc="upper left")
    fig.text(0.01, 0.01, "Net = after 40 bps/month (PreTOM trades) or 10 bps per side on actual turnover (all month). "
             "Price returns only; Massive data, CS tickers.", fontsize=7.5, color=ink2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(HERE / "cumulative_in_window.png", facecolor=surf)
    plt.close(fig)


if __name__ == "__main__":
    main()
