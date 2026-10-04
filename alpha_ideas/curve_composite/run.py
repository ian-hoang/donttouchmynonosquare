"""Test 3 — commodity curve composite: relative basis + basis-momentum + skewness (18 CME commodities, monthly).

Pre-registered in alpha_ideas/PREREGISTRATION_ROUND3.md (Test 3). Spec choices are in results.md, written before the run.

Run from the repo root:  uv run python alpha_ideas/curve_composite/run.py

Signals at D_t (the trading day before month-end M_t), positions from the M_t close to the M_{t+1} close in the nearest
contract that is safe to hold through month t+1:
  RB   = [ln F(N1) - ln F(N2)] / (tau2 - tau1) - [ln F(N2) - ln F(N3)] / (tau3 - tau2)   (Gu, Kang, Lou & Tang)
  BM   = 12-month cumulative return of the N1 chain minus that of the N2 chain             (Boons & Prado 2019)
  Skew = skewness of the N1 chain's daily log returns, last 252 trading days               (Fernandez-Perez et al. 2018)
  Composite = (z_RB + z_BM - z_Skew) / 3; long the top 4, short the bottom 4, inverse-vol weights per leg.

Outputs (this folder): monthly.csv, signals.csv, run_output.txt (everything printed).
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
from calendar import monthrange
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import statsmodels.api as sm  # noqa: E402
from scipy import stats  # noqa: E402

import gqh.data as gd  # noqa: E402
from gqh import CACHE  # noqa: E402

ROOTS = ["CL", "HO", "RB", "NG", "GC", "SI", "HG", "PL", "PA", "ZC", "ZW", "KE", "ZS", "ZM", "ZL", "LE", "GF", "HE"]
REQS = [dict(dataset="GLBX.MDP3", symbols=[f"{r}.c.{k}" for r in ROOTS for k in range(4)], schema="ohlcv-1d",
             start="2010-06-06", end="2026-10-01", stype_in="continuous"),
        # Added before the run (results.md, choice 10): with only c.0-c.3, HO/RB and the metals never had three
        # contracts eligible to hold, so relative basis could not be computed for them.
        dict(dataset="GLBX.MDP3", symbols=[f"{r}.c.{k}" for r in ROOTS for k in (4, 5)], schema="ohlcv-1d",
             start="2010-06-06", end="2026-10-01", stype_in="continuous")]
MAX_USD = 4.00
PHYSICAL = {"ZC", "ZW", "KE", "ZS", "ZM", "ZL", "GC", "SI", "HG", "PL", "PA", "LE"}   # notices before expiry
LIVESTOCK = {"LE", "GF", "HE"}
TICK = {"CL": .01, "HO": .0001, "RB": .0001, "NG": .001, "GC": .10, "SI": .005, "HG": .0005, "PL": .10, "PA": .05,
        "ZC": .25, "ZW": .25, "KE": .25, "ZS": .25, "ZM": .10, "ZL": .01, "LE": .025, "GF": .025, "HE": .025}
PV = {"CL": 1000, "HO": 42000, "RB": 42000, "NG": 10000, "GC": 100, "SI": 5000, "HG": 25000, "PL": 50, "PA": 100,
      "ZC": 50, "ZW": 50, "KE": 50, "ZS": 50, "ZM": 100, "ZL": 600, "LE": 400, "GF": 500, "HE": 400}
FEE_SIDE = 2.50
# Approximate expiry: (month offset from the delivery month, day of month or "last")
EXPIRY = {"CL": (-1, 20), "HO": (-1, "last"), "RB": (-1, "last"), "NG": (-1, 27),
          **{r: (0, 27) for r in ("GC", "SI", "HG", "PL", "PA")},
          **{r: (0, 14) for r in ("ZC", "ZW", "KE", "ZS", "ZM", "ZL")},
          "LE": (0, "last"), "HE": (0, 14), "GF": (0, 25)}
MONTH_CODES = "FGHJKMNQUVXZ"
STALE_DAYS = 5
MIN_ROOTS = 10
N_LEG = 4
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


def load_closes() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(closes: one row per contract per date, c0: which contract is c.0 per root per date).

    Contracts are keyed "ROOT:instrument_id" because Databento reuses instrument ids across products over time
    (e.g. id 497 was GCV6 in 2016 and another product's contract in 2020)."""
    frames = []
    for req in REQS:
        if not _fully_cached(req):
            p = gd.price(**req)
            print(f"Commodity request price: ${p['usd']:.4f}")
            if p["usd"] > MAX_USD:
                raise SystemExit(f"ABORT: request costs ${p['usd']:.2f} > ${MAX_USD:.2f}")
        frames.append(gd.databento_chunked(req["dataset"], req["symbols"], req["schema"], req["start"], req["end"],
                                           stype_in=req["stype_in"]).reset_index())
    bars = pd.concat(frames, ignore_index=True)
    bars["root"] = bars["symbol"].str.split(".").str[0]
    bars["rank"] = bars["symbol"].str.split(".").str[2].astype(int)
    bars["date"] = bars["ts_event"].dt.tz_convert("UTC").dt.date
    bars["key"] = bars["root"] + ":" + bars["instrument_id"].astype(str)
    closes = (bars[["root", "instrument_id", "key", "date", "close"]].drop_duplicates(["key", "date"])
              .sort_values(["key", "date"]))
    c0 = bars.loc[bars["rank"] == 0, ["root", "date", "instrument_id", "key"]]
    return closes, c0


def contract_info(closes: pd.DataFrame, c0: pd.DataFrame) -> pd.DataFrame:
    """key -> root, delivery month index (year*12 + month - 1) and approximate expiry date.

    A contract is dropped if its name-based expiry contradicts its own data: it traded more than 7 days after
    that expiry, or its last day as c.0 is more than 20 days away from it."""
    first_seen = closes.groupby("key")["date"].min()
    last_seen = closes.groupby("key")["date"].max()
    last_c0 = c0.groupby("key")["date"].max()
    rows, unknown, inconsistent = [], 0, []
    for root in ROOTS:
        start = "2013-01-01" if root == "KE" else "2010-06-06"     # KE.FUT only resolves on GLBX from 2013
        names = gd.instrument_symbols("GLBX.MDP3", f"{root}.FUT", start, "2026-10-01")
        pat = re.compile(rf"^{root}([FGHJKMNQUVXZ])(\d{{1,2}})$")
        for key in closes.loc[closes["root"] == root, "key"].unique():
            iid = int(key.split(":")[1])
            m = pat.match(names.get(iid, ""))
            if not m:
                unknown += 1
                continue
            month = MONTH_CODES.index(m.group(1)) + 1
            digits = m.group(2)
            seen = first_seen[key]
            if len(digits) == 2:
                year = 2000 + int(digits)
            else:
                year = seen.year + ((int(digits) - seen.year % 10) % 10)
            off, day = EXPIRY[root]
            ey, em = (year, month + off) if month + off >= 1 else (year - 1, month + off + 12)
            eday = monthrange(ey, em)[1] if day == "last" else min(day, monthrange(ey, em)[1])
            expiry = date(ey, em, eday)
            lc0 = last_c0.get(key)
            if (last_seen[key] - expiry).days > 7 or (lc0 is not None and abs((expiry - lc0).days) > 20
                                                       and lc0 < date(2026, 9, 1)):
                inconsistent.append(f"{key}={names[iid]}")
                continue
            rows.append({"key": key, "root": root, "raw": names[iid], "dm_idx": year * 12 + month - 1,
                         "expiry": expiry})
    info = pd.DataFrame(rows).set_index("key")
    if unknown:
        print(f"Dropped {unknown} contracts without an outright contract name")
    print(f"Dropped {len(inconsistent)} contracts whose name-based expiry contradicts their data"
          + (f": {', '.join(inconsistent[:12])}{' ...' if len(inconsistent) > 12 else ''}" if inconsistent else ""))
    return info


# ---------------------------------------------------------------------------------------------------------------
# Calendar, prices and ladders
# ---------------------------------------------------------------------------------------------------------------
def month_ends(c0: pd.DataFrame) -> list[tuple[date, date]]:
    """[(D_t, M_t)] per month: M_t = last date with >= 12 roots' c.0 bar, D_t = the previous such date."""
    counts = c0.groupby("date")["root"].nunique()
    days = sorted(counts[counts >= 12].index)
    by_month: dict[tuple[int, int], list[date]] = {}
    for d in days:
        by_month.setdefault((d.year, d.month), []).append(d)
    out = []
    for key in sorted(by_month):
        ds = by_month[key]
        if len(ds) >= 2:
            out.append((ds[-2], ds[-1]))
    return out


class Prices:
    def __init__(self, closes: pd.DataFrame):
        self.series = {iid: pd.Series(g["close"].to_numpy(), index=pd.DatetimeIndex(pd.to_datetime(g["date"])))
                       for iid, g in closes.groupby("key")}

    def at(self, iid, d: date, stale: int = STALE_DAYS):
        s = self.series.get(iid)
        if s is None:
            return np.nan
        ts = pd.Timestamp(d)
        i = s.index.searchsorted(ts, side="right") - 1
        if i < 0 or (ts - s.index[i]).days > stale:
            return np.nan
        return float(s.iloc[i])

    def daily_logrets(self, iid, a: date, b: date) -> np.ndarray:
        s = self.series.get(iid)
        if s is None:
            return np.array([])
        x = s[(s.index >= pd.Timestamp(a)) & (s.index <= pd.Timestamp(b))]
        return np.diff(np.log(x.to_numpy()))


def eligible(info_row, hold_year: int, hold_month: int) -> bool:
    h_idx = hold_year * 12 + hold_month - 1
    if info_row.root in PHYSICAL:
        return info_row.dm_idx >= h_idx + 2
    end_h = date(hold_year, hold_month, monthrange(hold_year, hold_month)[1])
    return info_row.expiry > end_h + timedelta(days=5)


def ladder(root: str, d: date, hold: tuple[int, int], info: pd.DataFrame, px: Prices) -> list[str]:
    cands = info[info["root"] == root]
    out = []
    for iid, row in cands.iterrows():
        if eligible(row, *hold) and not np.isnan(px.at(iid, d)) and row.expiry > d:
            out.append((row.expiry, iid))
    return [iid for _, iid in sorted(out)]


def side_cost(root: str, price: float) -> float:
    return TICK[root] / price + FEE_SIDE / (price * PV[root])


# ---------------------------------------------------------------------------------------------------------------
# Signals and portfolios
# ---------------------------------------------------------------------------------------------------------------
def build_panel(info, px, ends):
    """One row per (formation month t, root) with signals and the next month's holding return."""
    # Contracts selected for each holding month h (indexed by the formation index t = h - 1)
    sel = {}   # (t, root) -> (n1, n2, n3)
    for t, (dt, mt) in enumerate(ends):
        nxt = (mt.year + (mt.month == 12), mt.month % 12 + 1)
        for root in ROOTS:
            lad = ladder(root, dt, nxt, info, px)
            sel[(t, root)] = tuple(lad[:3])
    rows = []
    for t, (dt, mt) in enumerate(ends):
        if t < 12 or t + 1 >= len(ends):
            continue
        m_next = ends[t + 1][1]
        for root in ROOTS:
            lad = sel[(t, root)]
            rec = {"t": t, "D": dt, "M": mt, "M_next": m_next, "root": root}
            # Relative basis at D_t
            if len(lad) == 3:
                f = [px.at(i, dt) for i in lad]
                e = [info.loc[i, "expiry"] for i in lad]
                tau = [(x - dt).days / 365.25 for x in e]
                if all(np.isfinite(f)) and tau[1] > tau[0] and tau[2] > tau[1]:
                    rec["RB"] = ((np.log(f[0]) - np.log(f[1])) / (tau[1] - tau[0])
                                 - (np.log(f[1]) - np.log(f[2])) / (tau[2] - tau[1]))
            # Basis-momentum: 11 full holding months (M_j -> M_{j+1}, j = t-12..t-2) + the partial current month
            # (M_{t-1} -> D_t). sel[(j, root)] holds the contracts chosen at D_j for the month M_j -> M_{j+1}.
            g1, g2, ok = 1.0, 1.0, True
            daily = []
            for j in range(t - 12, t):
                c = sel.get((j, root), ())
                if len(c) < 2:
                    ok = False
                    break
                a = ends[j][1]
                b = dt if j == t - 1 else ends[j + 1][1]
                p1a, p1b, p2a, p2b = px.at(c[0], a), px.at(c[0], b), px.at(c[1], a), px.at(c[1], b)
                if not all(np.isfinite([p1a, p1b, p2a, p2b])):
                    ok = False
                    break
                g1 *= p1b / p1a
                g2 *= p2b / p2a
            if ok:
                rec["BM"] = g1 - g2
            # Daily N1-chain returns for skew (252) and vol (63): walk back month by month
            for h in range(t, -1, -1):
                c = sel.get((h - 1, root), ()) if h >= 1 else ()
                if not c:
                    break
                a = ends[h - 1][1]
                b = dt if h == t else ends[h][1]
                daily = list(px.daily_logrets(c[0], a, b)) + daily
                if len(daily) >= 260:
                    break
            if len(daily) >= 200:
                last = np.array(daily[-252:])
                rec["Skew"] = stats.skew(last, bias=False)
            if len(daily) >= 63:
                rec["vol"] = np.std(daily[-63:], ddof=1)
            # Holding contract and return for month t+1
            if lad:
                hold = lad[0]
                pa, pb = px.at(hold, mt), px.at(hold, m_next, stale=10)
                rec["hold"] = hold
                rec["p_entry"] = pa
                rec["ret"] = pb / pa - 1 if np.isfinite(pa) and np.isfinite(pb) else np.nan
            rows.append(rec)
    return pd.DataFrame(rows)


def portfolio(panel: pd.DataFrame, score_fn, label: str, roots=None, n_leg=N_LEG, weighting="invvol"):
    """Monthly long-short returns with turnover costs. score_fn(df) -> Series of scores (higher = long)."""
    out, prev = [], {}
    for t, g in panel.groupby("t"):
        g = g if roots is None else g[g["root"].isin(roots)]
        g = g.dropna(subset=["p_entry", "vol"])
        s = score_fn(g)
        g = g.assign(score=s).dropna(subset=["score"])
        if len(g) < MIN_ROOTS:
            prev = {}
            continue
        g = g.sort_values("score")
        if n_leg == "tercile":
            k = len(g) // 3
            short, long_ = g.iloc[:k], g.iloc[-k:]
        else:
            short, long_ = g.iloc[:n_leg], g.iloc[-n_leg:]
        w = {}
        for leg, sign in ((long_, 1.0), (short, -1.0)):
            raw = (1 / leg["vol"]) if weighting == "invvol" else pd.Series(1.0, index=leg.index)
            for (_, row), wi in zip(leg.iterrows(), raw / raw.sum()):
                w[row["root"]] = (sign * wi, row["hold"], row["p_entry"], row["ret"])
        gross = sum(wi * (0.0 if np.isnan(r) else r) for wi, _, _, r in w.values())
        n_missing = sum(np.isnan(r) for _, _, _, r in w.values())
        cost = 0.0
        for root in set(w) | set(prev):
            wn, cn, pn, _ = w.get(root, (0.0, None, np.nan, 0))
            wo, co, po, _ = prev.get(root, (0.0, None, np.nan, 0))
            price = pn if np.isfinite(pn) else po
            c = side_cost(root, price)
            cost += (abs(wn - wo) if cn == co else abs(wo) + abs(wn)) * c
        out.append({"t": t, "M": g["M"].iloc[0], "hold_month": g["M_next"].iloc[0], "gross": gross, "cost": cost,
                    "net": gross - cost, "net_2x": gross - 2 * cost, "n_roots": len(g), "missing_exit": n_missing,
                    "long": " ".join(long_["root"]), "short": " ".join(short["root"])})
        prev = w
    df = pd.DataFrame(out)
    df.attrs["label"] = label
    return df


def zscore(x: pd.Series) -> pd.Series:
    return (x - x.mean()) / x.std(ddof=1)


def composite(g):
    ok = g[["RB", "BM", "Skew"]].notna().all(axis=1)
    sc = pd.Series(np.nan, index=g.index)
    gg = g[ok]
    sc[ok] = (zscore(gg["RB"]) + zscore(gg["BM"]) - zscore(gg["Skew"])) / 3
    return sc


def stats_line(x: pd.Series, lags: int = 3) -> dict:
    x = x.dropna()
    if len(x) < 6:
        return {"n": len(x)}
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    nw = sm.OLS(x.to_numpy(), np.ones(len(x))).fit(cov_type="HAC", cov_kwds={"maxlags": lags}).tvalues[0]
    return {"n": len(x), "mean_%": 100 * x.mean(), "t": t, "t_nw3": nw, "hit": (x > 0).mean(),
            "sharpe_ann": x.mean() / x.std(ddof=1) * np.sqrt(12), "ann_%": 1200 * x.mean()}


def fmt(d: dict) -> str:
    return "  ".join(f"{k}={v:.3f}" if isinstance(v, (float, np.floating)) else f"{k}={v}" for k, v in d.items())


# ---------------------------------------------------------------------------------------------------------------
def main():
    closes, c0 = load_closes()
    print(f"Daily closes: {len(closes):,} rows, {closes['key'].nunique()} contracts, "
          f"{closes['date'].min()} -> {closes['date'].max()}")
    info = contract_info(closes, c0)
    print(f"Contracts with names: {len(info)}; per root: " + ", ".join(f"{r}={n}" for r, n in
                                                                     info['root'].value_counts().items()))
    px = Prices(closes)
    ends = month_ends(c0)
    print(f"Month-ends: {len(ends)} ({ends[0][1]} -> {ends[-1][1]})")
    panel = build_panel(info, px, ends)
    panel.to_csv(HERE / "signals.csv", index=False)
    avail = panel.groupby("t")[["RB", "BM", "Skew", "ret"]].count().mean()
    print("Average roots per month with each field: " + ", ".join(f"{k}={v:.1f}" for k, v in avail.items()))

    comp = portfolio(panel, composite, "composite")
    comp.to_csv(HERE / "monthly.csv", index=False)
    print(f"\nHolding months: {len(comp)} ({comp['hold_month'].min()} -> {comp['hold_month'].max()}); "
          f"exits with no price (return set to 0): {int(comp['missing_exit'].sum())}")
    print(f"Average monthly cost: {100 * comp['cost'].mean():.3f}%")

    print("\n=== PRIMARY: composite long-short (top 4 / bottom 4, inverse-vol), mean monthly GROSS return ===")
    prim = stats_line(comp["gross"])
    print("   ", fmt(prim))
    print("\n=== TRADE ===")
    for col in ("gross", "net", "net_2x"):
        print(f"    {col:7s}", fmt(stats_line(comp[col])))
    primary_ok = prim["mean_%"] > 0 and prim["t_nw3"] >= 2.0
    net_ok, net2_ok = comp["net"].mean() > 0, comp["net_2x"].mean() > 0
    verdict = "PASS" if primary_ok and net_ok and net2_ok else (
        "WEAK PASS (cost-fragile)" if primary_ok and net_ok else "FAIL")
    print(f"\nVERDICT (pre-registered rule): {verdict}   [primary NW t>=2: {primary_ok}, net>0: {net_ok}, "
          f"net 2x>0: {net2_ok}]")

    print("\n=== By sample (composite) ===")
    hm = pd.to_datetime(comp["hold_month"]).dt.date
    for lab, sel in (("in-sample (held before 2024-10)", hm < OOS_START), ("OOS (held from 2024-10)", hm >= OOS_START),
                     ("2011-2019", hm < date(2020, 1, 1)), ("2020-2026", hm >= date(2020, 1, 1))):
        print(f"  {lab:34s} gross {fmt(stats_line(comp.loc[sel, 'gross']))}")
        print(f"  {'':34s} net   {fmt(stats_line(comp.loc[sel, 'net']))}")
    print("\n=== By calendar year (composite, % per year: gross / net) ===")
    for y, g in comp.groupby(pd.to_datetime(comp["hold_month"]).dt.year):
        print(f"  {y}: gross {100 * g['gross'].sum():+6.1f}%  net {100 * g['net'].sum():+6.1f}%  (n {len(g)})")

    print("\n=== Robustness (reported only) ===")
    rb = portfolio(panel, lambda g: g["RB"], "RB")
    bm = portfolio(panel, lambda g: g["BM"], "BM")
    sk = portfolio(panel, lambda g: -g["Skew"], "-Skew")
    rb_terc = portfolio(panel, lambda g: g["RB"], "RB tercile EW", n_leg="tercile", weighting="equal")
    nolive = portfolio(panel, composite, "composite ex-livestock", roots=[r for r in ROOTS if r not in LIVESTOCK])
    for df in (rb, bm, sk, rb_terc, nolive):
        print(f"  {df.attrs['label']:24s} gross {fmt(stats_line(df['gross']))}")
        print(f"  {'':24s} net   {fmt(stats_line(df['net']))}")
    for lab, df in (("RB top/bottom 4", rb), ("RB tercile EW", rb_terc)):
        sel = pd.to_datetime(df["hold_month"]).dt.date >= date(2020, 1, 1)
        print(f"  {lab + ' 2020-2026 (fresh OOS)':40s} gross {fmt(stats_line(df.loc[sel, 'gross']))}")
    ew = panel.dropna(subset=["ret"]).groupby("t")["ret"].mean()
    print(f"  {'long-only EW all roots':24s} gross {fmt(stats_line(ew))}")
    corr = pd.concat([rb.set_index("t")["gross"], bm.set_index("t")["gross"], sk.set_index("t")["gross"]], axis=1,
                     keys=["RB", "BM", "-Skew"]).corr()
    print("\n  Correlation of the single-signal long-short returns:\n" + corr.round(2).to_string())


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
