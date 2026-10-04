"""Idea 5 — Kalshi CPI crowd vs. Cleveland Fed nowcast (pre-registered in alpha_ideas/PREREGISTRATION.md).

Run:  uv run python alpha_ideas/kalshi_cpi/run.py

1. Crowd forecast per CPI release: last Kalshi trade of every "CPI m/m above X%" strike at or before 07:55 ET on
   release day -> P(CPI > X), made non-increasing (isotonic) -> median (interpolated 0.5 crossing) and mean.
2. Model forecast: Cleveland Fed nowcast, latest vintage strictly before release day.
3. Primary test: OLS slope of (actual - nowcast) on d = crowd median - nowcast (prediction: slope > 0).
4. Trade: ZN position -sign(d) from the bar ending 08:00 ET to the bar ending 10:00 ET on release day.
See results.md for every spec choice (written before the first run).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from gqh import data as gd  # noqa: E402
import fetch  # noqa: E402

ET = "America/New_York"
TODAY = "2026-10-03"
CORRECTION = 0.05  # label strike X -> CPI-scale threshold X + 0.05 (markets settle on the single-decimal print)
ZN_COST_BPS = gd.futures_cost_bps(111, 1 / 64, 1000, fee_per_contract=1.5)  # per side
MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV",
                                      "DEC"], start=1)}


# ----------------------------------------------------------------------------------------------- Kalshi ladder
def target_month(event_ticker: str) -> pd.Period:
    code = event_ticker.split("-")[-1]  # e.g. 21OCT (one core event is "25DECT", a re-listed December 2025)
    return pd.Period(year=2000 + int(code[:2]), month=MONTHS[code[2:5]], freq="M")


def strike(m: dict) -> float:
    if m.get("floor_strike") is not None:
        return float(m["floor_strike"])
    s = m["ticker"][len(m["event_ticker"]) + 1:]  # "T0.6", "TN0.1", "T-0.2"
    assert s.startswith("T"), m["ticker"]
    s = s[1:]
    return -float(s[1:]) if s.startswith("N") else float(s)


def check_rules(m: dict, core: bool) -> None:
    """Headline: "If the CPI increases by more than X% in <month>". Core: "...All Items less Food and Energy for
    <month> ... increases by more than / above X%" or "signed one-month percent change ... is greater than X%"."""
    r = m["rules_primary"]
    assert "CPI" in r or "Consumer Price Index" in r, r
    assert any(k in r for k in ("increases by more than", "increases by above", "is greater than")), r
    assert "year" not in r.lower() and "annual" not in r.lower(), r  # month-over-month only
    assert ("less Food and Energy" in r) == core, r
    yes = m.get("yes_sub_title", "")
    assert yes.startswith(f"Above {strike(m):.1f}%") or yes.startswith(f"Above {strike(m)}%"), (m["ticker"], yes)


def actual_value(ms: list) -> float:
    """Settlement value (one decimal). Checked against every strike's Yes/No result; where the field is not a
    number (one core event reads "Above 0.2%") it is inferred from the results: (highest Yes, lowest No]."""
    vals = set()
    for m in ms:
        try:
            vals.add(round(float(str(m["expiration_value"]).replace("%", "")), 2))
        except ValueError:
            pass
    yes = [strike(m) for m in ms if m["result"] == "yes"]
    no = [strike(m) for m in ms if m["result"] == "no"]
    if vals:
        assert len(vals) == 1, (ms[0]["event_ticker"], vals)
        v = vals.pop()
    else:
        assert yes and no and abs(min(no) - max(yes) - 0.1) < 1e-9, ms[0]["event_ticker"]
        v = round(min(no), 2)
    assert all(v > x + 1e-9 for x in yes) and all(v <= x + 1e-9 for x in no), (ms[0]["event_ticker"], v)
    return v


def last_trade(ticker: str, cutoff: pd.Timestamp):
    """(price, time) of the last trade at/before cutoff; fills sharing that timestamp -> contract-weighted mean."""
    snap = json.loads((fetch.RAW / "trades" / f"{ticker}.json").read_text())
    trades = {t["trade_id"]: t for t in snap["live"] + snap["historical"]}
    if not trades:
        return None
    df = pd.DataFrame(trades.values())
    df["t"] = pd.to_datetime(df["created_time"], utc=True, format="ISO8601")
    df = df[df["t"] <= cutoff]
    if df.empty:
        return None
    last = df[df["t"] == df["t"].max()]
    px, n = last["yes_price_dollars"].astype(float), last["count_fp"].astype(float)
    return float((px * n).sum() / n.sum()), last["t"].iloc[0]


def pava_decreasing(y: np.ndarray) -> np.ndarray:
    """Isotonic (non-increasing) least-squares fit, equal weights (pool adjacent violators)."""
    blocks = []  # [value, weight]
    for v in y:
        blocks.append([float(v), 1.0])
        while len(blocks) > 1 and blocks[-2][0] < blocks[-1][0]:  # violation: later value is higher
            v2, w2 = blocks.pop()
            v1, w1 = blocks.pop()
            blocks.append([(v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2])
    return np.concatenate([[v] * int(w) for v, w in blocks])


def ladder_stats(x: np.ndarray, p: np.ndarray) -> dict:
    """x: strikes ascending (label scale), p: last-trade P(CPI > x). Median/mean on the CPI scale."""
    s = pava_decreasing(p)
    out = {"n_strikes": len(x), "n_monotone_fixes": int((np.abs(s - p) > 1e-12).sum()),
           "p_lowest": s[0], "p_highest": s[-1], "median_label": np.nan, "median": np.nan, "ladder": "ok"}
    below = np.nonzero(s < 0.5)[0]
    if len(below) == 0:
        out["ladder"] = "median above top strike"
    elif below[0] == 0:
        out["ladder"] = "median below bottom strike"
    else:
        k = below[0]
        xs = x[k - 1] + (s[k - 1] - 0.5) / (s[k - 1] - s[k]) * (x[k] - x[k - 1])
        out["median_label"] = xs
        out["median"] = xs + CORRECTION
    # mean: mass between strikes at the published-grid midpoint of (x_k, x_k+1]; tails at the nearest grid value
    vals = [x[0]] + [(x[k] + 0.1 + x[k + 1]) / 2 for k in range(len(x) - 1)] + [x[-1] + 0.1]
    mass = [1 - s[0]] + [s[k] - s[k + 1] for k in range(len(x) - 1)] + [s[-1]]
    out["mean"] = float(np.dot(vals, mass))
    return out


def crowd_table(series: str, core: bool) -> tuple[pd.DataFrame, list]:
    ms = fetch.markets(series)
    by_event: dict[str, list] = {}
    for m in ms:
        by_event.setdefault(m["event_ticker"], []).append(m)
    rows, log = [], []
    for ev, group in sorted(by_event.items(), key=lambda kv: target_month(kv[0])):
        tm = target_month(ev)
        day = fetch.release_day(ev, group)
        if day is None:
            log.append((ev, "excluded: BLS never published this month (2025 shutdown)"))
            continue
        if day >= pd.Timestamp(TODAY) or not all(m.get("expiration_value") for m in group):
            continue  # not yet released
        for m in group:
            check_rules(m, core)
        cutoff = fetch.cutoff_ts(day)
        pts = []
        for m in group:
            lt = last_trade(m["ticker"], cutoff)
            if lt is not None:
                pts.append((strike(m), lt[0], lt[1]))
        row = {"event": ev, "target_month": str(tm), "release_date": day.date(), "actual": actual_value(group),
               "n_markets": len(group), "n_strikes_traded": len(pts)}
        if len(pts) < 2:
            log.append((ev, f"excluded: {len(pts)} strike(s) with a trade before the cut-off "
                            f"({len(group)} market(s) listed)"))
            rows.append(row | {"ladder": "fewer than 2 traded strikes"})
            continue
        pts.sort()
        x = np.array([p[0] for p in pts])
        assert len(set(x)) == len(x), ev
        st = ladder_stats(x, np.array([p[1] for p in pts]))
        times = [p[2] for p in pts]
        row |= st | {"strikes": " ".join(f"{a:g}:{b:.2f}" for a, b, _ in pts),
                     "last_trade_newest_h": (cutoff - max(times)).total_seconds() / 3600,
                     "last_trade_oldest_h": (cutoff - min(times)).total_seconds() / 3600}
        if st["ladder"] != "ok":
            log.append((ev, f"excluded: {st['ladder']}"))
        rows.append(row)
    return pd.DataFrame(rows), log


# ---------------------------------------------------------------------------------------------------- nowcast
def nowcast_table(series_name: str) -> pd.DataFrame:
    rows = []
    for chart in fetch.nowcast():
        y, m = map(int, chart["chart"]["subcaption"].split("-"))
        start = pd.Timestamp(year=y, month=m, day=1)
        ds = [d for d in chart["dataset"] if d["seriesname"] == series_name]
        assert len(ds) == 1
        for pt in ds[0]["data"]:
            parts = pt.get("tooltext", "").split("{br}")
            if len(parts) < 2 or pt.get("value") in (None, ""):
                continue
            lab = parts[1]
            if len(lab) != 5 or lab[2] != "/" or not (lab[:2] + lab[3:]).isdigit():
                continue  # vertical-line markers etc.
            mm, dd = int(lab[:2]), int(lab[3:])
            cands = []
            for yy in (y - 1, y, y + 1):
                try:  # "02/29" only exists in leap years
                    cands.append(pd.Timestamp(year=yy, month=mm, day=dd))
                except ValueError:
                    pass
            cands = [c for c in cands if start - pd.Timedelta(days=62) <= c <= start + pd.Timedelta(days=200)]
            assert len(cands) == 1, (chart["chart"]["subcaption"], lab)
            rows.append({"target_month": f"{y}-{m:02d}", "vintage": cands[0], "value": float(pt["value"])})
    return pd.DataFrame(rows)


def attach_nowcast(df: pd.DataFrame, nc: pd.DataFrame) -> pd.DataFrame:
    out = []
    for _, r in df.iterrows():
        g = nc[(nc["target_month"] == r["target_month"]) & (nc["vintage"] < pd.Timestamp(r["release_date"]))]
        if g.empty:
            out.append({"nowcast": np.nan, "nowcast_vintage": pd.NaT})
        else:
            last = g.loc[g["vintage"].idxmax()]
            out.append({"nowcast": last["value"], "nowcast_vintage": last["vintage"].date()})
    return pd.concat([df.reset_index(drop=True), pd.DataFrame(out)], axis=1)


# ------------------------------------------------------------------------------------------------------- ZN
def zn_windows() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per ET calendar day: ZN.v.0 return from the bar ending 08:00 to the bar ending 10:00 (roll-safe), and the
    08:00-09:00 bar volume (for the release-day sanity check)."""
    bars = gd.databento_chunked("GLBX.MDP3", [f"{c}.v.{k}" for c in ["ZT", "ZF", "ZN", "ZB", "UB"] for k in (0, 1)],
                                "ohlcv-1h", "2010-07-01", "2026-10-01", stype_in="continuous")
    bars = gd.stamp_bar_end(bars, "1h")
    r = gd.roll_safe_returns(bars)["ZN.v.0"].dropna()
    loc = r.index.tz_convert(ET)
    hour = loc.hour + loc.minute / 60
    w = pd.DataFrame({"r": r.to_numpy(), "day": loc.normalize().tz_localize(None), "hour": hour})
    w = w[(w["hour"] > 8) & (w["hour"] <= 10)]
    win = w.groupby("day").agg(ret=("r", lambda s: float(np.prod(1 + s) - 1)), n_bars=("r", "size"),
                               last_hour=("hour", "max"))
    win = win[(win["n_bars"] == 2) & (win["last_hour"] == 10)]
    zn = bars[bars["symbol"] == "ZN.v.0"]
    zl = zn.index.tz_convert(ET)
    vol = pd.DataFrame({"day": zl.normalize().tz_localize(None), "hour": zl.hour, "volume": zn["volume"].to_numpy()})
    vol9 = vol[vol["hour"] == 9].groupby("day")["volume"].sum()
    return win, vol9


# ----------------------------------------------------------------------------------------------- statistics
def ols(y: pd.Series, x: pd.Series) -> dict:
    X = sm.add_constant(x.astype(float))
    fit = sm.OLS(y.astype(float), X).fit()
    rob = sm.OLS(y.astype(float), X).fit(cov_type="HC1")
    return {"n": int(fit.nobs), "slope": fit.params.iloc[1], "slope_se": fit.bse.iloc[1], "t": fit.tvalues.iloc[1],
            "t_hc1": rob.tvalues.iloc[1], "intercept": fit.params.iloc[0], "r2": fit.rsquared}


def trade(pos: pd.Series, ret_bp: pd.Series) -> dict:
    gross = pos * ret_bp
    net = gross - (pos != 0) * 2 * ZN_COST_BPS
    n = int(len(gross))
    t = lambda s: s.mean() / (s.std(ddof=1) / np.sqrt(len(s))) if len(s) > 1 and s.std() > 0 else np.nan
    return {"n": n, "gross_mean_bp": gross.mean(), "gross_t": t(gross), "net_mean_bp": net.mean(), "net_t": t(net),
            "hit_rate": float((gross > 0).mean()), "net_total_bp": net.sum(), "long_share": float((pos > 0).mean())}


def analyse(df: pd.DataFrame, win: pd.DataFrame, label: str) -> pd.DataFrame:
    df = df.copy()
    df["zn_ret_bp"] = [win["ret"].get(pd.Timestamp(d), np.nan) * 1e4 for d in df["release_date"]]
    df["d"] = df["median"] - df["nowcast"]
    df["d_mean"] = df["mean"] - df["nowcast"]
    df["d_label"] = df["median_label"] - df["nowcast"]
    df["err_nowcast"] = df["actual"] - df["nowcast"]
    df["position"] = -np.sign(df["d"])
    df["trade_gross_bp"] = df["position"] * df["zn_ret_bp"]
    df["trade_net_bp"] = df["trade_gross_bp"] - (df["position"] != 0) * 2 * ZN_COST_BPS
    return df


def placebo(sample: pd.DataFrame, win: pd.DataFrame, all_release_days: set) -> dict:
    days = win.index[(win.index.dayofweek < 5) & ~win.index.isin(list(all_release_days))]
    lo, hi = pd.Timestamp(min(sample["release_date"])), pd.Timestamp(max(sample["release_date"]))
    span = days[(days >= lo - pd.Timedelta(days=10)) & (days <= hi)]
    ev_ret = sample["zn_ret_bp"]
    pl_ret = win.loc[span, "ret"] * 1e4
    per_event = []
    for _, r in sample.iterrows():
        prev = days[days < pd.Timestamp(r["release_date"])][-5:]
        per_event.append((r["position"] * win.loc[prev, "ret"] * 1e4).mean())
    pe = pd.Series(per_event)
    return {"event_days_mean_abs_bp": ev_ret.abs().mean(), "event_days_std_bp": ev_ret.std(),
            "placebo_days_n": len(pl_ret), "placebo_days_mean_bp": pl_ret.mean(),
            "placebo_days_mean_abs_bp": pl_ret.abs().mean(), "placebo_days_std_bp": pl_ret.std(),
            "placebo_trade_mean_bp": pe.mean(), "placebo_trade_t": pe.mean() / (pe.std() / np.sqrt(len(pe)))}


def accuracy(df: pd.DataFrame) -> dict:
    out = {}
    for name, col in [("crowd_median", "median"), ("crowd_mean", "mean"), ("nowcast", "nowcast"),
                      ("crowd_median_label_scale", "median_label")]:
        e = df["actual"] - df[col]
        out[name] = {"mae": e.abs().mean(), "rmse": float(np.sqrt((e ** 2).mean())), "bias": e.mean(),
                     "exact_after_rounding": float((np.round(df[col] + 1e-9, 1) == df["actual"]).mean())}
    return out


def verdict(t: float, net: float) -> str:
    if t >= 3 and net > 0:
        return "PASS"
    if t >= 2 and net > 0:
        return "WORTH A SECOND LOOK"
    return "FAIL"


def main() -> None:
    fetch.fetch_all(TODAY)
    win, vol9 = zn_windows()
    summary = {"zn_cost_bp_per_side": ZN_COST_BPS}
    tables = {}
    for series, core, nc_name in [("KXCPI", False, "CPI Inflation"), ("KXCPICORE", True, "Core CPI Inflation")]:
        crowd, log = crowd_table(series, core)
        df = attach_nowcast(crowd, nowcast_table(nc_name))
        # release-day sanity check: 08:00-09:00 ET ZN volume vs median of the prior 20 sessions' same bar
        ratios = []
        for d in df["release_date"]:
            d = pd.Timestamp(d)
            prior = vol9[vol9.index < d].iloc[-20:]
            ratios.append(vol9.get(d, np.nan) / prior.median())
        df["zn_0809_volume_ratio"] = ratios
        df = analyse(df, win, series)
        tables[series] = (df, log)

    # ------------------------------------------------------------------ headline (primary)
    df, log = tables["KXCPI"]
    all_days = {pd.Timestamp(d) for d in df["release_date"]}
    ok = df[(df["ladder"] == "ok") & df["nowcast"].notna() & df["zn_ret_bp"].notna()].copy()
    no_zn = df[(df["ladder"] == "ok") & df["nowcast"].notna() & df["zn_ret_bp"].isna()]
    assert no_zn.empty, no_zn[["event", "release_date"]]
    shutdown = ok["event"].str[-5:].isin(fetch.SHUTDOWN_AFFECTED)

    prim = ols(ok["err_nowcast"], ok["d"])
    tr = trade(ok["position"], ok["zn_ret_bp"])
    summary["coverage"] = {"events_listed": int(len(df) + sum(1 for e, s in log if "never published" in s)),
                           "events_used": int(len(ok)), "exclusions": log,
                           "first_release": str(ok["release_date"].min()), "last_release": str(ok["release_date"].max()),
                           "strikes_used_median": float(ok["n_strikes_traded"].median()),
                           "monotone_fixes_total": int(ok["n_monotone_fixes"].sum()),
                           "events_with_monotone_fix": int((ok["n_monotone_fixes"] > 0).sum()),
                           "newest_strike_trade_age_h_median": float(ok["last_trade_newest_h"].median()),
                           "oldest_strike_trade_age_h_median": float(ok["last_trade_oldest_h"].median()),
                           "release_day_volume_ratio_min": float(ok["zn_0809_volume_ratio"].min()),
                           "release_day_volume_ratio_median": float(ok["zn_0809_volume_ratio"].median()),
                           "release_days_with_volume_ratio_below_1.5": ok.loc[ok["zn_0809_volume_ratio"] < 1.5,
                                                                               "event"].tolist()}
    summary["primary"] = prim
    summary["trade"] = tr
    summary["verdict"] = verdict(prim["t"], tr["net_mean_bp"])
    summary["placebo"] = placebo(ok, win, all_days)
    summary["accuracy"] = accuracy(ok)
    rb = {}
    rb["mean_instead_of_median"] = {"ols": ols(ok["err_nowcast"], ok["d_mean"]),
                                    "trade": trade(-np.sign(ok["d_mean"]), ok["zn_ret_bp"])}
    rb["label_scale_median_no_correction"] = {"ols": ols(ok["err_nowcast"], ok["d_label"]),
                                              "trade": trade(-np.sign(ok["d_label"]), ok["zn_ret_bp"])}
    s = ok[~shutdown]
    rb["drop_shutdown_delayed"] = {"dropped": ok.loc[shutdown, "event"].tolist(),
                                   "ols": ols(s["err_nowcast"], s["d"]), "trade": trade(s["position"], s["zn_ret_bp"])}
    # core
    cdf, clog = tables["KXCPICORE"]
    cok = cdf[(cdf["ladder"] == "ok") & cdf["nowcast"].notna() & cdf["zn_ret_bp"].notna()].copy()
    rb["core_cpi"] = {"n_events_listed": int(len(cdf)), "exclusions": clog,
                      "first_release": str(cok["release_date"].min()), "last_release": str(cok["release_date"].max()),
                      "ols": ols(cok["err_nowcast"], cok["d"]), "trade": trade(cok["position"], cok["zn_ret_bp"]),
                      "accuracy": accuracy(cok)}
    summary["robustness"] = rb

    # Post-hoc diagnostics, added AFTER the first run to explain the results. Not pre-registered; they cannot
    # change the verdict.
    from scipy.stats import spearmanr
    early = ok[pd.to_datetime(ok["release_date"]) < "2024-01-01"]
    late = ok[pd.to_datetime(ok["release_date"]) >= "2024-01-01"]
    ok["surprise_vs_crowd"] = ok["actual"] - ok["median"]
    always_long = ok["zn_ret_bp"]
    summary["post_hoc_diagnostics_not_preregistered"] = {
        "primary_slope_2021_2023": ols(early["err_nowcast"], early["d"]),
        "primary_slope_2024_2026": ols(late["err_nowcast"], late["d"]),
        "spearman_d_vs_nowcast_error": spearmanr(ok["d"], ok["err_nowcast"]).statistic,
        "always_long_zn_on_release_days": {"gross_mean_bp": always_long.mean(),
                                           "net_mean_bp": always_long.mean() - 2 * ZN_COST_BPS,
                                           "t": always_long.mean() / (always_long.std() / np.sqrt(len(always_long)))},
        "zn_ret_bp_on_surprise_vs_crowd": ols(ok["zn_ret_bp"], ok["surprise_vs_crowd"]),
        "zn_ret_bp_on_d": ols(ok["zn_ret_bp"], ok["d"]),
    }

    cols = ["event", "target_month", "release_date", "median", "mean", "median_label", "nowcast", "nowcast_vintage",
            "actual", "d", "err_nowcast", "zn_ret_bp", "position", "trade_gross_bp", "trade_net_bp",
            "n_strikes_traded", "n_monotone_fixes", "p_lowest", "p_highest", "last_trade_newest_h",
            "last_trade_oldest_h", "zn_0809_volume_ratio", "ladder", "strikes"]
    out = df[cols].rename(columns={"median": "crowd_median", "mean": "crowd_mean",
                                   "median_label": "crowd_median_label_scale", "zn_ret_bp": "zn_ret_0800_1000_bp"})
    out["used_in_primary"] = out["event"].isin(ok["event"])
    out.to_csv(HERE / "per_release.csv", index=False, float_format="%.4f")
    cout = cdf[cols].rename(columns={"median": "crowd_median", "mean": "crowd_mean",
                                     "median_label": "crowd_median_label_scale", "zn_ret_bp": "zn_ret_0800_1000_bp"})
    cout["used"] = cout["event"].isin(cok["event"])
    cout.to_csv(HERE / "per_release_core.csv", index=False, float_format="%.4f")
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=lambda v: round(v, 4) if isinstance(v, float) else str(v)))


if __name__ == "__main__":
    main()
