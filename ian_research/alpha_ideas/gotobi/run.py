"""Test 1 — Gotobi (Tokyo 9:55 JST fixing) in yen futures (6J).

Pre-registered in alpha_ideas/PREREGISTRATION_ROUND2.md (Test 1). Spec choices are in results.md, written before the run.

Run from the repo root:  uv run --with holidays python alpha_ideas/gotobi/run.py

Hypothesis: on gotobi days (5th/10th/15th/20th/25th/30th/month-end, holiday -> previous Tokyo business day) USD/JPY rises
into the 9:55 JST fix (pre-fix window 08:00->10:00 JST) and falls back after it (post-fix window 10:00->12:00 JST).
6J is quoted in USD per JPY, so a USD/JPY return is -ln(P_end / P_start).

Outputs (this folder): days.csv (one row per Tokyo business day), hourly_path.csv, run_output.txt (everything printed).
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

import holidays  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import statsmodels.api as sm  # noqa: E402
from scipy import stats  # noqa: E402

import gqh.data as gd  # noqa: E402
from gqh import CACHE  # noqa: E402

REQ = dict(dataset="GLBX.MDP3", symbols=["6J.v.0"], schema="ohlcv-1h",
           start="2010-06-06", end="2026-10-01", stype_in="continuous")
MAX_USD = 2.50                     # abort threshold from the pre-registration (both tests together)
MULT = 12_500_000                  # yen per contract
FEE_RT = 5.0                       # $2.50 per side
HALF_TICK, FULL_TICK = 5e-7, 1e-6
OOS_START, OOS_END = date(2024, 10, 1), date(2026, 9, 30)
SUBPERIODS = [("2010-2017", date(2010, 1, 1), date(2017, 12, 31)),
              ("2018-2020 (paper)", date(2018, 1, 1), date(2020, 12, 31)),
              ("2021-2026 (new)", date(2021, 1, 1), date(2026, 12, 31))]
INTERVENTIONS = [date(2010, 9, 15), date(2011, 3, 18), date(2011, 8, 4), date(2011, 10, 31), date(2022, 9, 22),
                 date(2022, 10, 21), date(2022, 10, 24), date(2024, 4, 29), date(2024, 5, 1), date(2024, 7, 11),
                 date(2024, 7, 12)]


# ---------------------------------------------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------------------------------------------
def _chunks(start, end):
    """Same calendar-year split as gqh.data.databento_chunked."""
    edges = [pd.Timestamp(start)] + [pd.Timestamp(f"{y}-01-01") for y in
                                     range(pd.Timestamp(start).year + 1, pd.Timestamp(end).year + 1)]
    edges = [e for e in edges if e < pd.Timestamp(end)] + [pd.Timestamp(end)]
    return [(a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d")) for a, b in zip(edges[:-1], edges[1:])]


def _fully_cached(req) -> bool:
    for a, b in _chunks(req["start"], req["end"]):
        r = dict(dataset=req["dataset"], symbols=list(req["symbols"]), schema=req["schema"],
                 start=a, end=b, stype_in=req["stype_in"])
        key = hashlib.sha1(json.dumps(r, sort_keys=True).encode()).hexdigest()[:12]
        if not (CACHE / f"{req['dataset']}_{req['schema']}_{key}.dbn.zst").exists():
            return False
    return True


def load_bars() -> pd.DataFrame:
    if not _fully_cached(REQ):
        p = gd.price(**REQ)
        print(f"6J request price: ${p['usd']:.4f} ({p['gb']:.4f} GB)")
        if p["usd"] > MAX_USD:
            raise SystemExit(f"ABORT: 6J request costs ${p['usd']:.2f} > ${MAX_USD:.2f}")
    bars = gd.databento_chunked(REQ["dataset"], REQ["symbols"], REQ["schema"], REQ["start"], REQ["end"],
                                stype_in=REQ["stype_in"])
    bars = bars[bars["symbol"] == "6J.v.0"].sort_index()
    return bars[~bars.index.duplicated(keep="last")]


def tick_by_year(bars: pd.DataFrame) -> dict[int, float]:
    """0.0000005 in any year whose prices include odd multiples of 0.0000005 (the half-tick grid), else 0.000001."""
    px = pd.concat([bars[c] for c in ["open", "high", "low", "close"]])
    units = np.round(px.to_numpy() / HALF_TICK).astype(np.int64)
    odd = pd.Series(units % 2 == 1, index=px.index)
    return {int(y): (HALF_TICK if g.any() else FULL_TICK) for y, g in odd.groupby(odd.index.year)}


# ---------------------------------------------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------------------------------------------
def tokyo_business_days(y0: int, y1: int) -> set[date]:
    jp = holidays.JP(years=range(y0, y1 + 1))
    out = set()
    d = date(y0, 1, 1)
    while d <= date(y1, 12, 31):
        bank_holiday = (d.month == 12 and d.day == 31) or (d.month == 1 and d.day <= 3)
        if d.weekday() < 5 and d not in jp and not bank_holiday:
            out.add(d)
        d += timedelta(1)
    return out


def gotobi_set(bdays: set[date], y0: int, y1: int, rule: str = "previous") -> set[date]:
    """rule: 'previous' (primary), 'next', or 'nominal' (only nominal dates that are business days)."""
    out = set()
    lo, hi = min(bdays), max(bdays)
    for y in range(y0, y1 + 1):
        for m in range(1, 13):
            last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(1)).day
            for dd in sorted({5, 10, 15, 20, 25, last} | ({30} if last >= 30 else set())):
                d = date(y, m, dd)
                if rule == "nominal":
                    if d in bdays:
                        out.add(d)
                    continue
                step = -1 if rule == "previous" else 1
                while d not in bdays and lo <= d <= hi:
                    d += timedelta(step)
                if d in bdays:
                    out.add(d)
    return out


def month_end_gotobi(bdays: set[date], y0: int, y1: int) -> set[date]:
    """The gotobi day produced by the last calendar day of each month (previous-business-day rule)."""
    out = set()
    for y in range(y0, y1 + 1):
        for m in range(1, 13):
            d = date(y + (m == 12), m % 12 + 1, 1) - timedelta(1)
            while d not in bdays:
                d -= timedelta(1)
            out.add(d)
    return out


# ---------------------------------------------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------------------------------------------
def build_days(bars: pd.DataFrame, bdays: set[date], ticks: dict[int, float]) -> pd.DataFrame:
    idx = {ts: row for ts, row in zip(bars.index, bars[["open", "close", "instrument_id"]].itertuples(index=False))}
    rows = []
    for d in sorted(bdays):
        if d < date(2010, 6, 8) or d > date(2026, 9, 30):
            continue
        t0 = pd.Timestamp(d, tz="UTC")
        b23, b00, b01, b02 = (idx.get(t0 - pd.Timedelta(hours=1)), idx.get(t0),
                              idx.get(t0 + pd.Timedelta(hours=1)), idx.get(t0 + pd.Timedelta(hours=2)))
        rec = {"date": d, "weekday": d.weekday()}
        tick = ticks.get(d.year, FULL_TICK)
        for name, a, b in (("pre", b23, b00), ("post", b01, b02)):
            if a is None or b is None:
                rec[f"r_{name}"], rec[f"c_{name}"], rec[f"why_{name}"] = np.nan, np.nan, "missing bar"
            elif a.instrument_id != b.instrument_id:
                rec[f"r_{name}"], rec[f"c_{name}"], rec[f"why_{name}"] = np.nan, np.nan, "roll"
            else:
                rec[f"r_{name}"] = -np.log(b.close / a.open) * 1e4          # USD/JPY return, bp
                rec[f"c_{name}"] = (tick + FEE_RT / MULT) / a.open * 1e4      # round-trip cost, bp
                rec[f"why_{name}"] = ""
        rows.append(rec)
    df = pd.DataFrame(rows)
    df["S"] = df["r_pre"] - df["r_post"]
    return df


def hourly_path(bars: pd.DataFrame, days: pd.DataFrame) -> pd.DataFrame:
    """Average USD/JPY bar return (close-to-close, same contract) by UTC hour 20:00 -> 04:00, gotobi vs control."""
    b = bars[["close", "instrument_id"]].copy()
    ts = b.index.to_series()
    # Fixed after the single run: the first version compared each bar's timestamp with itself, so this
    # descriptive table printed NaN. No primary, trade or robustness number uses this function.
    same = (b["instrument_id"] == b["instrument_id"].shift(1)) & ((ts - ts.shift(1)) == pd.Timedelta(hours=1))
    ret = pd.Series(np.where(same, -np.log(b["close"] / b["close"].shift(1)) * 1e4, np.nan), index=b.index)
    hours = [20, 21, 22, 23, 0, 1, 2, 3, 4]
    out = []
    for grp, sel in (("gotobi", days["gotobi"]), ("control", ~days["gotobi"])):
        ds = days.loc[sel, "date"]
        for h in hours:
            ts = [pd.Timestamp(d, tz="UTC") + pd.Timedelta(hours=h - 24 if h >= 20 else h) for d in ds]
            vals = ret.reindex(ts).dropna()
            out.append({"group": grp, "utc_bar_start": f"{h:02d}:00", "jst_bar_start": f"{(h + 9) % 24:02d}:00",
                        "mean_bp": vals.mean(), "n": len(vals)})
    path = pd.DataFrame(out)
    path["cum_bp"] = path.groupby("group")["mean_bp"].cumsum()
    return path


# ---------------------------------------------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------------------------------------------
def welch(a: pd.Series, b: pd.Series) -> dict:
    a, b = a.dropna(), b.dropna()
    if len(a) < 3 or len(b) < 3:
        return {"diff": np.nan, "t": np.nan, "p_one_sided": np.nan, "n_a": len(a), "n_b": len(b)}
    t, p = stats.ttest_ind(a, b, equal_var=False)
    return {"diff": a.mean() - b.mean(), "t": t, "p_one_sided": p / 2 if t > 0 else 1 - p / 2,
            "mean_a": a.mean(), "mean_b": b.mean(), "n_a": len(a), "n_b": len(b)}


def nw_diff(y: pd.Series, dummy: pd.Series, lags: int = 5) -> float:
    m = pd.concat([y, dummy.astype(float)], axis=1).dropna()
    res = sm.OLS(m.iloc[:, 0], sm.add_constant(m.iloc[:, 1])).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    return float(res.tvalues.iloc[1])


def one_sample(x: pd.Series, per_year: float) -> dict:
    x = x.dropna()
    if len(x) < 3:
        return {"n": len(x)}
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    nw = sm.OLS(x.to_numpy(), np.ones(len(x))).fit(cov_type="HAC", cov_kwds={"maxlags": 5}).tvalues[0]
    return {"n": len(x), "mean_bp": x.mean(), "t": t, "t_nw5": nw, "hit": (x > 0).mean(),
            "sharpe_ann": x.mean() / x.std(ddof=1) * np.sqrt(per_year)}


def fmt(d: dict) -> str:
    return "  ".join(f"{k}={v:.3f}" if isinstance(v, (float, np.floating)) else f"{k}={v}" for k, v in d.items())


# ---------------------------------------------------------------------------------------------------------------
def main():
    bars = load_bars()
    print(f"6J.v.0 hourly bars: {len(bars):,}  {bars.index.min()} -> {bars.index.max()}  "
          f"contracts: {bars['instrument_id'].nunique()}")
    ticks = tick_by_year(bars)
    print("Tick by year (USD per JPY):", {y: ("0.0000005" if t == HALF_TICK else "0.000001") for y, t in ticks.items()})

    bdays = tokyo_business_days(2008, 2028)            # one spare year each side so holiday shifts never run out
    g_prev = gotobi_set(bdays, 2009, 2027, "previous")
    g_next = gotobi_set(bdays, 2009, 2027, "next")
    g_nom = gotobi_set(bdays, 2009, 2027, "nominal")
    g_me = month_end_gotobi(bdays, 2009, 2027)

    days = build_days(bars, bdays, ticks)
    days["gotobi"] = days["date"].isin(g_prev)
    days["gotobi_next"] = days["date"].isin(g_next)
    days["gotobi_nominal"] = days["date"].isin(g_nom)
    days["month_end"] = days["date"].isin(g_me)
    near_iv = set()
    for d in INTERVENTIONS:
        near_iv.add(d)
        for step in (-1, 1):
            x = d + timedelta(step)
            while x not in bdays:
                x += timedelta(step)
            near_iv.add(x)
    days["intervention"] = days["date"].isin(near_iv)
    days["valid"] = days["S"].notna()
    days["net"] = days["S"] - days["c_pre"] - days["c_post"]
    days["net_2x"] = days["S"] - 2 * (days["c_pre"] + days["c_post"])
    days.to_csv(HERE / "days.csv", index=False)

    print(f"\nTokyo business days in sample: {len(days):,}  valid (both windows): {days['valid'].sum():,}")
    for name in ("pre", "post"):
        print(f"  {name}-fix windows dropped: " + ", ".join(f"{k}={v}" for k, v in
                                                         days[f"why_{name}"].value_counts().items() if k))
    tf = days[days["weekday"].between(1, 4)]                  # Tuesday-Friday (primary sample)
    years = (pd.Timestamp("2026-09-30") - pd.Timestamp("2010-06-08")).days / 365.25
    print(f"Primary sample (Tue-Fri, valid): {tf['valid'].sum():,} days, of which gotobi "
          f"{(tf['valid'] & tf['gotobi']).sum():,} and control {(tf['valid'] & ~tf['gotobi']).sum():,}")
    print(f"Average round-trip cost: {tf['c_pre'].mean():.2f} bp per leg (pre), {tf['c_post'].mean():.2f} bp (post)")

    # ---------------- PRIMARY ----------------
    print("\n=== PRIMARY: D = mean S (gotobi) - mean S (control), Tue-Fri, full sample ===")
    print("    S = USD/JPY return 08:00->10:00 JST minus USD/JPY return 10:00->12:00 JST, in bp")
    w = welch(tf.loc[tf["gotobi"], "S"], tf.loc[~tf["gotobi"], "S"])
    print("   ", fmt(w))
    print(f"    Newey-West(5) t of the gotobi dummy: {nw_diff(tf['S'], tf['gotobi']):.3f}")

    # ---------------- TRADE ----------------
    g_per_year = (tf["gotobi"] & tf["valid"]).sum() / years
    print(f"\n=== TRADE: short 6J pre-fix + long 6J post-fix, gotobi Tue-Fri only ({g_per_year:.1f} trades/yr) ===")
    for lab, col in (("gross", "S"), ("net (base costs)", "net"), ("net (2x costs)", "net_2x")):
        print(f"    {lab:18s}", fmt(one_sample(tf.loc[tf["gotobi"], col], g_per_year)))

    primary_ok = (w["diff"] > 0) and (w["t"] >= 2.0)
    net_ok = tf.loc[tf["gotobi"], "net"].mean() > 0
    net2_ok = tf.loc[tf["gotobi"], "net_2x"].mean() > 0
    verdict = "PASS" if primary_ok and net_ok and net2_ok else (
        "WEAK PASS (cost-fragile)" if primary_ok and net_ok else "FAIL")
    print(f"\nVERDICT (pre-registered rule): {verdict}   [primary t>=2: {primary_ok}, net>0: {net_ok}, "
          f"net 2x>0: {net2_ok}]")

    # ---------------- SAMPLES ----------------
    print("\n=== By sample (Tue-Fri): D (Welch) and the gotobi trade's net P&L ===")
    samples = [("full", date(2010, 1, 1), date(2026, 12, 31)), ("in-sample to 2024-09-30", date(2010, 1, 1),
               date(2024, 9, 30)), ("OOS 2024-10-01..2026-09-30", OOS_START, OOS_END)] + SUBPERIODS
    for lab, a, b in samples:
        s = tf[(tf["date"] >= a) & (tf["date"] <= b)]
        ww = welch(s.loc[s["gotobi"], "S"], s.loc[~s["gotobi"], "S"])
        tr = one_sample(s.loc[s["gotobi"], "net"], g_per_year)
        print(f"  {lab:28s} D={ww['diff']:+7.2f}bp t={ww['t']:+6.2f} (n {ww['n_a']}/{ww['n_b']})   "
              f"trade net mean={tr.get('mean_bp', np.nan):+6.2f}bp t={tr.get('t', np.nan):+5.2f} "
              f"hit={tr.get('hit', np.nan):.2f}")
    print("\n=== By calendar year (Tue-Fri) ===")
    for y, s in tf.groupby(pd.to_datetime(tf["date"]).dt.year):
        ww = welch(s.loc[s["gotobi"], "S"], s.loc[~s["gotobi"], "S"])
        tr = s.loc[s["gotobi"], "net"].dropna()
        print(f"  {y}: D={ww['diff']:+7.2f}bp t={ww['t']:+5.2f}  gotobi S mean={ww.get('mean_a', np.nan):+6.2f}  "
              f"control S mean={ww.get('mean_b', np.nan):+6.2f}  trade net sum={tr.sum():+7.1f}bp over {len(tr)}")

    # ---------------- ROBUSTNESS ----------------
    print("\n=== Robustness (reported only; cannot rescue the primary) ===")
    rb = []
    rb.append(("pre-fix leg only: r_pre gotobi - control", welch(tf.loc[tf["gotobi"], "r_pre"],
                                                                 tf.loc[~tf["gotobi"], "r_pre"])))
    rb.append(("post-fix leg only: r_post gotobi - control (pred < 0)", welch(tf.loc[tf["gotobi"], "r_post"],
                                                                              tf.loc[~tf["gotobi"], "r_post"])))
    rb.append(("month-end gotobi vs control", welch(tf.loc[tf["gotobi"] & tf["month_end"], "S"],
                                                    tf.loc[~tf["gotobi"], "S"])))
    rb.append(("5/10/15/20/25/30 gotobi vs control", welch(tf.loc[tf["gotobi"] & ~tf["month_end"], "S"],
                                                           tf.loc[~tf["gotobi"], "S"])))
    mar = tf[pd.to_datetime(tf["date"]).dt.month == 3]
    rb.append(("March only", welch(mar.loc[mar["gotobi"], "S"], mar.loc[~mar["gotobi"], "S"])))
    mon = days[days["weekday"] == 0]
    rb.append(("Mondays only", welch(mon.loc[mon["gotobi"], "S"], mon.loc[~mon["gotobi"], "S"])))
    rb.append(("next-business-day holiday rule", welch(tf.loc[tf["gotobi_next"], "S"],
                                                       tf.loc[~tf["gotobi_next"], "S"])))
    rb.append(("nominal dates only (no shift)", welch(tf.loc[tf["gotobi_nominal"], "S"],
                                                      tf.loc[~tf["gotobi_nominal"], "S"])))
    xi = tf[~tf["intervention"]]
    rb.append(("excluding intervention days +-1", welch(xi.loc[xi["gotobi"], "S"], xi.loc[~xi["gotobi"], "S"])))
    lo, hi = tf["S"].quantile([0.01, 0.99])
    sw = tf["S"].clip(lo, hi)
    rb.append(("winsorized 1%/99%", welch(sw[tf["gotobi"]], sw[~tf["gotobi"]])))
    for lab, ww in rb:
        print(f"  {lab:52s} diff={ww['diff']:+7.2f}bp t={ww['t']:+6.2f} (n {ww['n_a']}/{ww['n_b']})")

    path = hourly_path(bars, days[days["weekday"].between(1, 4)])
    path.to_csv(HERE / "hourly_path.csv", index=False)
    print("\n=== Descriptive: average USD/JPY bar return by hour (Tue-Fri), bp; JST = UTC+9 ===")
    piv = path.pivot(index=["utc_bar_start", "jst_bar_start"], columns="group", values="mean_bp")
    piv = piv.reindex([(f"{h:02d}:00", f"{(h + 9) % 24:02d}:00") for h in [20, 21, 22, 23, 0, 1, 2, 3, 4]])
    piv["gotobi - control"] = piv["gotobi"] - piv["control"]
    print(piv.round(2).to_string())


if __name__ == "__main__":
    buf = io.StringIO()

    class Tee:
        def write(self, s):
            sys.__stdout__.write(s)
            buf.write(s)

        def flush(self):
            sys.__stdout__.flush()

    with redirect_stdout(Tee()):
        main()
    (HERE / "run_output.txt").write_text(buf.getvalue())
