"""Test 2 — Gold "Asia buys, New York sells", with a China-holiday placebo (GC futures).

Pre-registered in alpha_ideas/PREREGISTRATION_ROUND2.md (Test 2). Spec choices are in results.md, written before the run.

Run from the repo root:  uv run --with exchange_calendars python alpha_ideas/gold_clock/run.py

Hypothesis: gold rises during Asian hours (Asian physical / Chinese / central-bank buying) and falls during New York hours
(Western financial selling). Both windows are 9 hours long, so a steady trend cancels out of the spread.
  Asia:     OPEN of the bar starting 18:00 ET on d-1  -> CLOSE of the bar starting 02:00 ET on d   (18:00 -> 03:00 ET)
  Europe:   OPEN of the bar starting 03:00 ET on d    -> CLOSE of the bar starting 07:00 ET on d   (03:00 -> 08:00 ET)
  New York: OPEN of the bar starting 08:00 ET on d    -> CLOSE of the bar starting 16:00 ET on d   (08:00 -> 17:00 ET)

Outputs (this folder): sessions.csv, hourly_profile.csv, run_output.txt (everything printed).
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

import exchange_calendars as xcals  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import statsmodels.api as sm  # noqa: E402
from scipy import stats  # noqa: E402

import gqh.data as gd  # noqa: E402
from gqh import CACHE  # noqa: E402

REQ = dict(dataset="GLBX.MDP3", symbols=["GC.v.0"], schema="ohlcv-1h",
           start="2010-06-06", end="2026-10-01", stype_in="continuous")
MAX_USD = 2.50
TZ = "America/New_York"
MULT, TICK, FEE_RT = 100.0, 0.10, 5.0          # 100 oz, $0.10 tick, $2.50 per side
OOS_START, OOS_END = date(2024, 10, 1), date(2026, 9, 30)
WINDOWS = {"asia": (-1, 18, 0, 2), "europe": (0, 3, 0, 7), "ny": (0, 8, 0, 16)}   # (start day offset, start hour,
                                                                                   #  end day offset, end bar hour)


# ---------------------------------------------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------------------------------------------
def _chunks(start, end):
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
        print(f"GC request price: ${p['usd']:.4f} ({p['gb']:.4f} GB)")
        if p["usd"] > MAX_USD:
            raise SystemExit(f"ABORT: GC request costs ${p['usd']:.2f} > ${MAX_USD:.2f}")
    bars = gd.databento_chunked(REQ["dataset"], REQ["symbols"], REQ["schema"], REQ["start"], REQ["end"],
                                stype_in=REQ["stype_in"])
    bars = bars[bars["symbol"] == "GC.v.0"].sort_index()
    return bars[~bars.index.duplicated(keep="last")]


def shanghai_closed_weekdays() -> set[date]:
    cal = xcals.get_calendar("XSHG", start="2010-01-01", end="2026-12-31")
    sessions = set(pd.DatetimeIndex(cal.sessions).date)
    return {d.date() for d in pd.bdate_range("2010-01-01", "2026-12-31") if d.date() not in sessions}


# ---------------------------------------------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------------------------------------------
def _et(d: date, hour: int) -> pd.Timestamp:
    return pd.Timestamp(datetime(d.year, d.month, d.day, hour)).tz_localize(TZ).tz_convert("UTC")


def build_sessions(bars: pd.DataFrame) -> pd.DataFrame:
    idx = {ts: row for ts, row in zip(bars.index, bars[["open", "close", "instrument_id"]].itertuples(index=False))}
    rows = []
    for d in pd.bdate_range("2010-06-07", "2026-09-30").date:
        rec = {"date": d, "weekday": d.weekday()}
        for name, (so, sh, eo, eh) in WINDOWS.items():
            a = idx.get(_et(d + timedelta(so), sh))
            b = idx.get(_et(d + timedelta(eo), eh))
            if a is None or b is None:
                rec[f"r_{name}"], rec[f"c_{name}"], rec[f"why_{name}"] = np.nan, np.nan, "missing bar"
            elif a.instrument_id != b.instrument_id:
                rec[f"r_{name}"], rec[f"c_{name}"], rec[f"why_{name}"] = np.nan, np.nan, "roll"
            else:
                rec[f"r_{name}"] = np.log(b.close / a.open) * 1e4
                rec[f"c_{name}"] = (TICK + FEE_RT / MULT) / a.open * 1e4
                rec[f"why_{name}"] = ""
                rec[f"px_{name}"] = a.open
        rows.append(rec)
    df = pd.DataFrame(rows)
    df["X"] = df["r_asia"] - df["r_ny"]
    df["net"] = df["X"] - df["c_asia"] - df["c_ny"]
    df["net_2x"] = df["X"] - 2 * (df["c_asia"] + df["c_ny"])
    df["asia_long_net"] = df["r_asia"] - df["c_asia"]
    return df


def hourly_profile(bars: pd.DataFrame) -> pd.DataFrame:
    b = bars[["close", "instrument_id"]].copy()
    prev_ts = b.index.to_series().shift(1)
    same = (b["instrument_id"] == b["instrument_id"].shift(1)) & ((b.index.to_series() - prev_ts)
                                                                  == pd.Timedelta(hours=1))
    ret = pd.Series(np.where(same, np.log(b["close"] / b["close"].shift(1)) * 1e4, np.nan), index=b.index)
    et_hour = b.index.tz_convert(TZ).hour
    prof = ret.groupby(et_hour).agg(["mean", "count", "std"])
    prof["t"] = prof["mean"] / (prof["std"] / np.sqrt(prof["count"]))
    prof.index.name = "et_bar_start_hour"
    return prof.reset_index()


# ---------------------------------------------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------------------------------------------
def one_sample(x: pd.Series, per_year: float = 252.0) -> dict:
    x = x.dropna()
    if len(x) < 3:
        return {"n": len(x)}
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    nw = sm.OLS(x.to_numpy(), np.ones(len(x))).fit(cov_type="HAC", cov_kwds={"maxlags": 5}).tvalues[0]
    return {"n": len(x), "mean_bp": x.mean(), "t": t, "t_nw5": nw, "hit": (x > 0).mean(),
            "sharpe_ann": x.mean() / x.std(ddof=1) * np.sqrt(per_year), "ann_bp": x.mean() * per_year}


def welch(a: pd.Series, b: pd.Series) -> dict:
    a, b = a.dropna(), b.dropna()
    if len(a) < 3 or len(b) < 3:
        return {"diff": np.nan, "t": np.nan, "n_a": len(a), "n_b": len(b)}
    t, p = stats.ttest_ind(a, b, equal_var=False)
    return {"diff": a.mean() - b.mean(), "t": t, "p_one_sided": p / 2 if t > 0 else 1 - p / 2,
            "mean_a": a.mean(), "mean_b": b.mean(), "n_a": len(a), "n_b": len(b)}


def fmt(d: dict) -> str:
    return "  ".join(f"{k}={v:.3f}" if isinstance(v, (float, np.floating)) else f"{k}={v}" for k, v in d.items())


# ---------------------------------------------------------------------------------------------------------------
def main():
    bars = load_bars()
    print(f"GC.v.0 hourly bars: {len(bars):,}  {bars.index.min()} -> {bars.index.max()}  "
          f"contracts: {bars['instrument_id'].nunique()}")
    s = build_sessions(bars)
    closed = shanghai_closed_weekdays()
    s["sh_closed"] = s["date"].isin(closed)
    s["valid"] = s["X"].notna()
    s.to_csv(HERE / "sessions.csv", index=False)
    print(f"Weekday sessions: {len(s):,}  valid (Asia and NY): {s['valid'].sum():,}")
    for name in WINDOWS:
        print(f"  {name} windows dropped: " + ", ".join(f"{k}={v}" for k, v in s[f"why_{name}"].value_counts().items()
                                                       if k))
    print(f"Average round-trip cost: Asia {s['c_asia'].mean():.2f} bp, NY {s['c_ny'].mean():.2f} bp "
          f"(range {s['c_asia'].min():.2f}-{s['c_asia'].max():.2f})")

    v = s[s["valid"]]
    print("\n=== PRIMARY: mean (r_Asia - r_NY), bp per session, full sample ===")
    prim = one_sample(v["X"])
    print("   ", fmt(prim))
    print("    legs:  Asia", fmt(one_sample(v["r_asia"])))
    print("           NY  ", fmt(one_sample(v["r_ny"])))

    print("\n=== TRADE: long GC 18:00->03:00 ET, short GC 08:00->17:00 ET (2 round trips/day) ===")
    for lab, col in (("gross", "X"), ("net (base costs)", "net"), ("net (2x costs)", "net_2x")):
        print(f"    {lab:18s}", fmt(one_sample(v[col])))
    primary_ok = prim["mean_bp"] > 0 and prim["t"] >= 2.0
    net_ok, net2_ok = v["net"].mean() > 0, v["net_2x"].mean() > 0
    verdict = "PASS" if primary_ok and net_ok and net2_ok else (
        "WEAK PASS (cost-fragile)" if primary_ok and net_ok else "FAIL")
    print(f"\nVERDICT (pre-registered rule): {verdict}   [primary t>=2: {primary_ok}, net>0: {net_ok}, "
          f"net 2x>0: {net2_ok}]")

    print("\n=== SECONDARY (mechanism, not part of the verdict): Shanghai open vs closed ===")
    o, c = v[~v["sh_closed"]], v[v["sh_closed"]]
    print("    r_Asia open - closed (pred > 0):", fmt(welch(o["r_asia"], c["r_asia"])))
    print("    X      open - closed (pred > 0):", fmt(welch(o["X"], c["X"])))
    print("    r_NY   open - closed           :", fmt(welch(o["r_ny"], c["r_ny"])))

    print("\n=== By sample ===")
    samples = [("full", date(2010, 1, 1), date(2026, 12, 31)),
               ("in-sample to 2024-09-30", date(2010, 1, 1), date(2024, 9, 30)),
               ("OOS 2024-10-01..2026-09-30", OOS_START, OOS_END),
               ("ex 2024-2026 (pre-2024)", date(2010, 1, 1), date(2023, 12, 31))]
    for lab, a, b in samples:
        x = v[(v["date"] >= a) & (v["date"] <= b)]
        p, n = one_sample(x["X"]), one_sample(x["net"])
        print(f"  {lab:28s} X mean={p['mean_bp']:+6.2f}bp t={p['t']:+5.2f} (n {p['n']})  "
              f"net mean={n['mean_bp']:+6.2f}bp t={n['t']:+5.2f} Sharpe={n['sharpe_ann']:+.2f}  "
              f"Asia={x['r_asia'].mean():+6.2f} NY={x['r_ny'].mean():+6.2f}")
    print("\n=== By calendar year ===")
    for y, x in v.groupby(pd.to_datetime(v["date"]).dt.year):
        p = one_sample(x["X"])
        print(f"  {y}: X mean={p['mean_bp']:+6.2f}bp t={p['t']:+5.2f}  Asia={x['r_asia'].mean():+6.2f} "
              f"NY={x['r_ny'].mean():+6.2f}  Europe={x['r_europe'].mean():+6.2f}  net sum={x['net'].sum():+8.1f}bp "
              f"(n {p['n']})")

    print("\n=== Robustness (reported only) ===")
    print("    long-only Asia, net:      ", fmt(one_sample(v["asia_long_net"])))
    print("    Europe window 03->08 ET:  ", fmt(one_sample(s["r_europe"])))
    lo, hi = v["X"].quantile([0.01, 0.99])
    print("    X winsorized 1%/99%:      ", fmt(one_sample(v["X"].clip(lo, hi))))

    prof = hourly_profile(bars)
    prof.to_csv(HERE / "hourly_profile.csv", index=False)
    print("\n=== Descriptive: mean GC bar return by ET bar-start hour (bp; close-to-close, same contract) ===")
    print(prof.round(3).to_string(index=False))


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
