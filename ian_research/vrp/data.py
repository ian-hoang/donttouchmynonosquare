"""Pull everything the VRP rebuild needs from Massive (+ FRED DTB3) into data/cache/vrp/.

Rules are in vrp/PREREGISTRATION.md. Every HTTP response is cached on disk by URL, so reruns are free.
Run: uv run python vrp/data.py
"""
import io
import math
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "massive"))
import eightk  # noqa: E402  (API client + NYSE calendar)

OUT = ROOT / "data" / "cache" / "vrp"
eightk.CACHE_DIR = OUT / "http"          # keep our responses out of the 8-K cache
UNDERLYINGS = ["SPY", "QQQ"]
START, END = "2022-03-01", "2026-10-02"  # option quotes begin ~2022-04; END = last complete session
DAILY_START = "2021-01-01"               # extra history for RV
NY = "America/New_York"
WORKERS = 16


def ns(day: pd.Timestamp, hhmm: str) -> int:
    return pd.Timestamp(f"{day:%Y-%m-%d} {hhmm}", tz=NY).value


# ---- stock data ----------------------------------------------------------------------------------
def daily_bars(tk: str) -> pd.DataFrame:
    rows = eightk.api_get_all(f"/v2/aggs/ticker/{tk}/range/1/day/{DAILY_START}/{END}",
                              {"adjusted": "true", "sort": "asc", "limit": 50000})
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert(NY).dt.normalize().dt.tz_localize(None)
    return df.set_index("date")[["o", "h", "l", "c", "v"]]


def dividends(tk: str) -> pd.Series:
    rows = eightk.api_get_all("/v3/reference/dividends",
                              {"ticker": tk, "ex_dividend_date.gte": DAILY_START, "limit": 1000})
    df = pd.DataFrame(rows)
    df = df[df.get("dividend_type", "CD").eq("CD")] if "dividend_type" in df else df
    s = df.groupby(pd.to_datetime(df["ex_dividend_date"]))["cash_amount"].sum()
    return s.sort_index()


def minute_bars(tk: str) -> pd.DataFrame:
    months = pd.date_range(START, END, freq="MS")
    frames = []
    for m in months:
        a, b = m, min(m + pd.offsets.MonthEnd(0), pd.Timestamp(END))
        rows = eightk.api_get_all(f"/v2/aggs/ticker/{tk}/range/1/minute/{a:%Y-%m-%d}/{b:%Y-%m-%d}",
                                  {"adjusted": "false", "sort": "asc", "limit": 50000})
        frames.append(pd.DataFrame(rows))
    df = pd.concat(frames, ignore_index=True).drop_duplicates("t")
    df["ts"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert(NY)
    return df[["ts", "c", "v"]]


def regular_minutes(tk: str) -> pd.DataFrame:
    mb = minute_bars(tk)
    mb["date"] = mb["ts"].dt.tz_localize(None).dt.normalize()
    mb["hm"] = mb["ts"].dt.hour * 60 + mb["ts"].dt.minute
    return mb[(mb.hm >= 570) & (mb.hm < 960)]


def detect_early(reg: pd.DataFrame) -> set:
    """Early close: 13:00-16:00 volume under 5% of 09:30-13:00 volume."""
    am = reg[reg.hm < 780].groupby("date").v.sum()
    pm = reg[reg.hm >= 780].groupby("date").v.sum().reindex(am.index, fill_value=0)
    return set(am.index[(am > 0) & (pm < 0.05 * am)])


def spot_panel(reg: pd.DataFrame, sessions: pd.DatetimeIndex, early_days: set) -> pd.DataFrame:
    """Mark time (15:45, or 12:45 on early closes) and S = close of the bar starting 1 minute before it.

    DEVIATION from the pre-registration (bug fix, made before any P&L existed): early-close days are the
    union of both tickers' detections. SPY's after-hours volume on Black Friday 2024/2025 is above 5%, so
    per-ticker detection missed 2 of the 9 exchange early closes that QQQ's data finds.
    """
    out = []
    for day, g in reg.groupby("date"):
        if day not in sessions:
            continue
        early = day in early_days
        mark_hm = 12 * 60 + 45 if early else 15 * 60 + 45
        before = g[g.hm <= mark_hm - 1]
        if before.empty:
            continue
        bar = before.iloc[-1]
        out.append({"date": day, "early": early, "mark_hm": mark_hm, "S": float(bar.c),
                    "S_bar_hm": int(bar.hm), "mark_ns": ns(day, f"{mark_hm // 60:02d}:{mark_hm % 60:02d}")})
    return pd.DataFrame(out).set_index("date")


# ---- options ---------------------------------------------------------------------------------------
def opt_ticker(und: str, exp: pd.Timestamp, cp: str, k: float) -> str:
    return f"O:{und}{exp:%y%m%d}{cp}{int(round(k * 1000)):08d}"


def expiry_for(day: pd.Timestamp) -> pd.Timestamp:
    """Friday closest to day + 30 calendar days; if not a session, the session before it."""
    target = day + pd.Timedelta(days=30)
    fwd = (4 - target.weekday()) % 7
    fri = target + pd.Timedelta(days=fwd) if fwd <= 3 else target - pd.Timedelta(days=7 - fwd)
    return fri if fri in eightk.CAL else eightk.session_before(fri)


def quote(tkr: str, mark_ns: int) -> dict | None:
    p = eightk.api_get(f"/v3/quotes/{tkr}", {"timestamp.lte": mark_ns, "timestamp.gte": mark_ns - 30 * 60 * 10**9,
                                             "order": "desc", "sort": "timestamp", "limit": 1})
    r = (p.get("results") or [None])[0]
    if not r:
        return None
    return {"bid": float(r.get("bid_price") or 0), "ask": float(r.get("ask_price") or 0), "qts": int(r["sip_timestamp"])}


def valid(q: dict | None) -> bool:
    if not q:
        return False
    b, a = q["bid"], q["ask"]
    return b > 0 and a >= b and (a - b) <= 0.25 * (a + b) / 2


def daily_rule(und: str, day: pd.Timestamp, S: float, mark_ns: int) -> dict:
    exp = expiry_for(day)
    cands = sorted(range(math.floor(S) - 2, math.ceil(S) + 3), key=lambda k: (abs(k - S), k))[:3]
    for i, k in enumerate(cands):
        c = quote(opt_ticker(und, exp, "C", k), mark_ns)
        p = quote(opt_ticker(und, exp, "P", k), mark_ns)
        if valid(c) and valid(p):
            return {"und": und, "date": day, "exp": exp, "K": float(k), "tries": i + 1,
                    "c_bid": c["bid"], "c_ask": c["ask"], "p_bid": p["bid"], "p_ask": p["ask"]}
    return {"und": und, "date": day, "exp": exp, "K": np.nan, "tries": len(cands)}


def leg_marks(und: str, entry: pd.Timestamp, exp: pd.Timestamp, k: float, day: pd.Timestamp, mark_ns: int) -> dict:
    c = quote(opt_ticker(und, exp, "C", k), mark_ns)
    p = quote(opt_ticker(und, exp, "P", k), mark_ns)
    row = {"und": und, "entry": entry, "date": day}
    for leg, q in (("c", c), ("p", p)):
        row[f"{leg}_bid"] = q["bid"] if q else np.nan
        row[f"{leg}_ask"] = q["ask"] if q else np.nan
        row[f"{leg}_ok"] = valid(q)
    return row


# ---- rates -----------------------------------------------------------------------------------------
def dtb3() -> pd.Series:
    f = OUT / "DTB3.csv"
    if not f.exists():
        r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3", timeout=60)
        r.raise_for_status()
        f.write_text(r.text)
    df = pd.read_csv(f)
    df.columns = ["date", "rate"]
    s = pd.to_numeric(df["rate"], errors="coerce")
    s.index = pd.to_datetime(df["date"])
    return (s / 100).dropna()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rates = dtb3()
    print(f"DTB3 {rates.index[0]:%Y-%m-%d}..{rates.index[-1]:%Y-%m-%d}")

    daily = {u: daily_bars(u) for u in UNDERLYINGS}
    divs = {u: dividends(u) for u in UNDERLYINGS}
    pd.to_pickle({"daily": daily, "divs": divs, "rates": rates}, OUT / "stock.pkl")
    sessions = daily["SPY"].loc[START:END].index
    cal = eightk.CAL[(eightk.CAL >= START) & (eightk.CAL <= END)]
    print(f"sessions {len(sessions)}; calendar mismatch: {sorted(set(cal) ^ set(sessions))}")

    reg = {u: regular_minutes(u) for u in UNDERLYINGS}
    early_days = set().union(*(detect_early(reg[u]) for u in UNDERLYINGS))
    spot = {}
    for u in UNDERLYINGS:
        spot[u] = spot_panel(reg[u], sessions, early_days)
        print(f"{u}: spot rows {len(spot[u])}, early closes {list(spot[u].index[spot[u].early].strftime('%Y-%m-%d'))}")
    pd.to_pickle(spot, OUT / "spot.pkl")

    # daily contract rule, every session
    jobs = [(u, d, r.S, r.mark_ns) for u in UNDERLYINGS for d, r in spot[u].iterrows()]
    with ThreadPoolExecutor(WORKERS) as ex:
        rule = pd.DataFrame(list(ex.map(lambda j: daily_rule(*j), jobs)))
    rule.to_pickle(OUT / "rule.pkl")
    ok = rule.dropna(subset=["K"])
    print(f"daily rule: {len(ok)}/{len(rule)} valid; first valid {ok.date.min():%Y-%m-%d}; "
          f"tries>1: {(ok.tries > 1).sum()}")

    # marks for every Wednesday entry, entry+1 .. last session before expiry (covers H5 too)
    wed = ok[ok.date.dt.weekday == 2]
    mjobs = []
    for r in wed.itertuples():
        last = min(eightk.session_before(r.exp), pd.Timestamp(END))
        for d in spot[r.und].loc[r.date + pd.Timedelta(days=1):last].index:
            mjobs.append((r.und, r.date, r.exp, r.K, d, int(spot[r.und].at[d, "mark_ns"])))
    print(f"mark jobs: {len(mjobs)} ({len(wed)} Wednesday entries)")
    with ThreadPoolExecutor(WORKERS) as ex:
        marks = pd.DataFrame(list(ex.map(lambda j: leg_marks(*j), mjobs)))
    marks.to_pickle(OUT / "marks.pkl")
    print(f"marks: {len(marks)} rows; invalid leg-marks: c {(~marks.c_ok).sum()}, p {(~marks.p_ok).sum()}")


if __name__ == "__main__":
    main()
