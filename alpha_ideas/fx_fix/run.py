"""Test 4 — month-end WM/R 4pm London fix, signed by the month's US equity move (CME FX futures).

Pre-registered in alpha_ideas/PREREGISTRATION_ROUND3.md (Test 4). Spec choices are in results.md, written before the run.

Run from the repo root:  uv run --with holidays python alpha_ideas/fx_fix/run.py

On the last London business day L of each month: s = sign(ES month-to-date return) when |MTD| > 1%.
Hold s x (six-currency basket) over the 15:00->16:00 London bar, then -s x basket over the 16:00->17:00 London bar.
Per-event statistic G = s x (r_pre - r_post) in bp of the basket (long a CME FX future = long that currency vs USD).

Outputs (this folder): events.csv, run_output.txt (everything printed).
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

import holidays  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import statsmodels.api as sm  # noqa: E402

import gqh.data as gd  # noqa: E402
from gqh import CACHE  # noqa: E402

FX_REQ = dict(dataset="GLBX.MDP3", symbols=["6E.v.0", "6B.v.0", "6A.v.0", "6C.v.0", "6S.v.0"], schema="ohlcv-1h",
              start="2010-06-06", end="2026-10-01", stype_in="continuous")
JPY_REQ = dict(dataset="GLBX.MDP3", symbols=["6J.v.0"], schema="ohlcv-1h",
               start="2010-06-06", end="2026-10-01", stype_in="continuous")              # bought in round 2
ES_REQ = dict(dataset="GLBX.MDP3", symbols=["ES.v.0", "ES.v.1"], schema="ohlcv-1h",
              start="2010-06-07", end="2026-10-01", stype_in="continuous")              # bought for t1_shift
MAX_USD = 6.00
CCY = {"6E": (125_000, 5e-5, 1e-4), "6J": (12_500_000, 5e-7, 1e-6), "6B": (62_500, 5e-5, 1e-4),
       "6A": (100_000, 5e-5, 1e-4), "6C": (100_000, 5e-5, 1e-4), "6S": (125_000, 5e-5, 1e-4)}
FEE_RT = 5.0
THRESH = 0.01
LONDON, NY = "Europe/London", "America/New_York"
OOS_START = date(2024, 10, 1)


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


def _load(req, allow_buy: bool) -> pd.DataFrame:
    if not _fully_cached(req):
        if not allow_buy:
            raise SystemExit(f"ABORT: {req['symbols']} is expected to be cached; refusing to buy it again")
        p = gd.price(**req)
        print(f"Request price: ${p['usd']:.4f}")
        if p["usd"] > MAX_USD:
            raise SystemExit(f"ABORT: request costs ${p['usd']:.2f} > ${MAX_USD:.2f}")
    return gd.databento_chunked(req["dataset"], req["symbols"], req["schema"], req["start"], req["end"],
                                stype_in=req["stype_in"])


def tick_by_year(bars: pd.DataFrame, small: float, large: float) -> dict[int, float]:
    px = pd.concat([bars[c] for c in ["open", "high", "low", "close"]])
    units = np.round(px.to_numpy() / small)
    on_grid = np.abs(units * small - px.to_numpy()) < small / 10
    odd = pd.Series(on_grid & (units.astype(np.int64) % 2 == 1), index=px.index)
    return {int(y): (small if g.any() else large) for y, g in odd.groupby(odd.index.year)}


# ---------------------------------------------------------------------------------------------------------------
# Calendar and signal
# ---------------------------------------------------------------------------------------------------------------
def london_business_days(y0: int, y1: int) -> list[date]:
    hol = holidays.country_holidays("GB", subdiv="ENG", years=range(y0, y1 + 1))
    return [d.date() for d in pd.bdate_range(f"{y0}-01-01", f"{y1}-12-31") if d.date() not in hol]


def es_daily(es: pd.DataFrame) -> pd.DataFrame:
    """16:00 ET closes of ES.v.0 with roll-safe daily log returns (previous close of the same contract)."""
    b = es.reset_index()
    b["et"] = b["ts_event"].dt.tz_convert(NY)
    b = b[b["et"].dt.hour == 15]                                 # bar starting 15:00 ET -> its close is 16:00 ET
    b["date"] = b["et"].dt.date
    v0 = b[b["symbol"] == "ES.v.0"].drop_duplicates("date", keep="last").sort_values("date")
    look = {(r.instrument_id, r.date): r.close for r in b.itertuples()}
    dates = list(v0["date"])
    rets = []
    for i, r in enumerate(v0.itertuples()):
        prev = look.get((r.instrument_id, dates[i - 1])) if i > 0 else None
        rets.append(np.log(r.close / prev) if prev else np.nan)
    return pd.DataFrame({"date": dates, "ret": rets}).set_index("date")


def mtd_before(esd: pd.DataFrame, day: date) -> float:
    """Sum of ES daily returns after the last ES date of the previous month, through the last ES date before `day`."""
    first_of_month = day.replace(day=1)
    sel = esd[(esd.index >= first_of_month) & (esd.index < day)]
    if sel["ret"].isna().any() or len(sel) == 0:
        return np.nan
    return float(sel["ret"].sum())


def window(bars_by_ccy: dict, ticks: dict, day: date, hour: int) -> dict:
    """Per-currency log return (bp) and round-trip cost (bp) over the bar starting `hour`:00 London on `day`."""
    ts = pd.Timestamp(datetime(day.year, day.month, day.day, hour)).tz_localize(LONDON).tz_convert("UTC")
    out = {}
    for ccy, (size, _, _) in CCY.items():
        row = bars_by_ccy[ccy].get(ts)
        if row is None:
            continue
        tick = ticks[ccy].get(day.year, CCY[ccy][2])
        out[ccy] = (np.log(row.close / row.open) * 1e4, (tick + FEE_RT / size) / row.open * 1e4)
    return out


def stats_line(x: pd.Series, lags: int = 3) -> dict:
    x = x.dropna()
    if len(x) < 6:
        return {"n": len(x)}
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    nw = sm.OLS(x.to_numpy(), np.ones(len(x))).fit(cov_type="HAC", cov_kwds={"maxlags": lags}).tvalues[0]
    return {"n": len(x), "mean_bp": x.mean(), "t": t, "t_nw3": nw, "hit": (x > 0).mean(),
            "sharpe_ann": x.mean() / x.std(ddof=1) * np.sqrt(12)}


def fmt(d: dict) -> str:
    return "  ".join(f"{k}={v:.3f}" if isinstance(v, (float, np.floating)) else f"{k}={v}" for k, v in d.items())


def build_events(bars_by_ccy, ticks, esd, days: list[date], basket=tuple(CCY)) -> pd.DataFrame:
    rows = []
    for d in days:
        mtd = mtd_before(esd, d)
        pre, post = window(bars_by_ccy, ticks, d, 15), window(bars_by_ccy, ticks, d, 16)
        rec = {"date": d, "mtd": mtd}
        for ccy in CCY:
            rec[f"pre_{ccy}"] = pre.get(ccy, (np.nan, np.nan))[0]
            rec[f"post_{ccy}"] = post.get(ccy, (np.nan, np.nan))[0]
        both = [c for c in basket if c in pre and c in post]
        if len(both) >= min(4, len(basket)):
            rec["r_pre"] = np.mean([pre[c][0] for c in both])
            rec["r_post"] = np.mean([post[c][0] for c in both])
            rec["c_pre"] = np.mean([pre[c][1] for c in both])
            rec["c_post"] = np.mean([post[c][1] for c in both])
            rec["n_ccy"] = len(both)
        rows.append(rec)
    return pd.DataFrame(rows)


def signed(ev: pd.DataFrame, thresh: float = THRESH) -> pd.DataFrame:
    ev = ev.dropna(subset=["mtd", "r_pre"]).copy()
    ev = ev[ev["mtd"].abs() > thresh] if thresh > 0 else ev[ev["mtd"] != 0]
    ev["s"] = np.sign(ev["mtd"])
    ev["G"] = ev["s"] * (ev["r_pre"] - ev["r_post"])
    ev["pre_leg"] = ev["s"] * ev["r_pre"]
    ev["post_leg"] = ev["s"] * ev["r_post"]
    ev["net"] = ev["G"] - ev["c_pre"] - ev["c_post"]
    ev["net_2x"] = ev["G"] - 2 * (ev["c_pre"] + ev["c_post"])
    return ev


# ---------------------------------------------------------------------------------------------------------------
def main():
    fx = _load(FX_REQ, allow_buy=True)
    jpy = _load(JPY_REQ, allow_buy=False)
    es = _load(ES_REQ, allow_buy=False)
    bars = pd.concat([fx, jpy])
    bars_by_ccy, ticks = {}, {}
    for ccy, (_, small, large) in CCY.items():
        b = bars[bars["symbol"] == f"{ccy}.v.0"].sort_index()
        b = b[~b.index.duplicated(keep="last")]
        bars_by_ccy[ccy] = {ts: row for ts, row in zip(b.index, b[["open", "close"]].itertuples(index=False))}
        ticks[ccy] = tick_by_year(b, small, large)
        print(f"{ccy}: {len(b):,} hourly bars; tick by year: "
              + ", ".join(f"{y}:{'small' if t == small else 'LARGE'}" for y, t in ticks[ccy].items()))
    esd = es_daily(es)
    print(f"ES daily closes: {len(esd):,} ({esd.index.min()} -> {esd.index.max()}), "
          f"roll-safe returns missing: {int(esd['ret'].isna().sum())}")

    lbd = london_business_days(2010, 2026)
    by_month: dict[tuple[int, int], list[date]] = {}
    for d in lbd:
        by_month.setdefault((d.year, d.month), []).append(d)
    months = [k for k in sorted(by_month) if (2010, 7) <= k <= (2026, 9)]
    last_days = [by_month[k][-1] for k in months]
    second_last = [by_month[k][-2] for k in months]

    allm = build_events(bars_by_ccy, ticks, esd, last_days)
    allm.to_csv(HERE / "events.csv", index=False)
    print(f"Months: {len(allm)}; with a valid basket and MTD: {allm.dropna(subset=['mtd', 'r_pre']).shape[0]}; "
          f"average currencies in basket: {allm['n_ccy'].mean():.2f}; avg round-trip cost "
          f"{allm['c_pre'].mean():.2f} bp per window")
    ev = signed(allm)
    print(f"Events with |MTD| > 1%: {len(ev)} (up {int((ev['s'] > 0).sum())}, down {int((ev['s'] < 0).sum())})")

    print("\n=== PRIMARY: mean G = s x (r_pre - r_post), six-currency basket, bp per event ===")
    prim = stats_line(ev["G"])
    print("   ", fmt(prim))
    print("\n=== TRADE (2 round trips per currency per event) ===")
    for col in ("G", "net", "net_2x"):
        print(f"    {col:7s}", fmt(stats_line(ev[col])))
    primary_ok = prim["mean_bp"] > 0 and prim["t"] >= 2.0
    net_ok, net2_ok = ev["net"].mean() > 0, ev["net_2x"].mean() > 0
    verdict = "PASS" if primary_ok and net_ok and net2_ok else (
        "WEAK PASS (cost-fragile)" if primary_ok and net_ok else "FAIL")
    print(f"\nVERDICT (pre-registered rule): {verdict}   [primary t>=2: {primary_ok}, net>0: {net_ok}, "
          f"net 2x>0: {net2_ok}]")

    print("\n=== By sample ===")
    d = pd.to_datetime(ev["date"]).dt.date
    for lab, sel in (("in-sample (before 2024-10)", d < OOS_START), ("OOS (from 2024-10)", d >= OOS_START),
                     ("2010-07..2015-02 (1-min fix)", d < date(2015, 3, 1)),
                     ("2015-03..2020-12", (d >= date(2015, 3, 1)) & (d < date(2021, 1, 1))),
                     ("2021..2026", d >= date(2021, 1, 1)),
                     ("quarter-end months", pd.to_datetime(ev["date"]).dt.month.isin([3, 6, 9, 12]))):
        print(f"  {lab:30s} G {fmt(stats_line(ev.loc[sel, 'G']))}")

    print("\n=== Robustness (reported only) ===")
    print("  pre-fix leg s*r_pre (pred > 0):  ", fmt(stats_line(ev["pre_leg"])))
    print("  post-fix leg s*r_post (pred < 0):", fmt(stats_line(ev["post_leg"])))
    for ccy in CCY:
        g = ev["s"] * (ev[f"pre_{ccy}"] - ev[f"post_{ccy}"])
        print(f"  {ccy} alone G:                    ", fmt(stats_line(g)))
    sub = signed(build_events(bars_by_ccy, ticks, esd, last_days, basket=("6B", "6A", "6S")))
    print("  GBP/AUD/CHF basket G:            ", fmt(stats_line(sub["G"])))
    for th in (0.0, 0.02):
        print(f"  threshold {th:.0%} G:                 ", fmt(stats_line(signed(allm, th)["G"])))
    plc = signed(build_events(bars_by_ccy, ticks, esd, second_last))
    print("  placebo: 2nd-to-last London day G:", fmt(stats_line(plc["G"])))
    reg = allm.dropna(subset=["mtd", "r_pre"])
    res = sm.OLS(reg["r_pre"], sm.add_constant(100 * reg["mtd"])).fit(cov_type="HC1")
    print(f"  regression r_pre (bp) on MTD (%), all months: slope={res.params.iloc[1]:+.3f} bp per 1% "
          f"(t={res.tvalues.iloc[1]:+.2f}), n={int(res.nobs)}")
    res2 = sm.OLS(reg["r_post"], sm.add_constant(100 * reg["mtd"])).fit(cov_type="HC1")
    print(f"  regression r_post (bp) on MTD (%), all months: slope={res2.params.iloc[1]:+.3f} bp per 1% "
          f"(t={res2.tvalues.iloc[1]:+.2f})")


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
