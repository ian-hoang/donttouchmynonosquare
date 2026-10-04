"""Step 1 — earnings events and their timing (PREREGISTRATION.md). Filing dates and volumes only, no returns.

Run from the repo root:  uv run python alpha_ideas/event_runup/build_events.py
  1. 8-K item 2.02 filings from the cached SEC submissions -> episodes -> quarterly events
  2. Case-2 events (accepted >= 16:00 ET on a trading day): Massive hourly bars decide after-close vs earlier
Writes data/cache/event_runup/{episodes,events}.parquet and prints an audit.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
AIW = ROOT / "data" / "cache" / "ai_washing"
OUT = ROOT / "data" / "cache" / "event_runup"
BARS = OUT / "hourly"
BARS.mkdir(parents=True, exist_ok=True)

EPISODE_GAP = 22            # filings less than this many calendar days apart are one episode
CADENCE = (50, 130)         # previous episode start must be this many days earlier (quarterly reporter)
HOLD = 5                    # sessions
FETCH_FROM, FETCH_TO = "2020-11-01", "2026-09-30"   # case-2 events whose F falls here get bars


def load_filings() -> pd.DataFrame:
    rows = []
    for f in sorted(glob.glob(str(AIW / "sec" / "submissions" / "*.json"))):
        j = json.load(open(f))
        if j.get("missing"):
            continue
        d = pd.DataFrame(j["filings"])
        d["cik"] = str(j["cik"]).zfill(10)
        rows.append(d)
    d = pd.concat(rows, ignore_index=True)
    d = d[(d["form"] == "8-K") & d["items"].astype(str).str.split(",").apply(lambda xs: "2.02" in [x.strip() for x in xs])]
    d["accepted_et"] = (pd.to_datetime(d["acceptanceDateTime"], utc=True).dt.tz_convert("America/New_York")
                        .dt.tz_localize(None))
    return d.drop_duplicates("accessionNumber").sort_values(["cik", "accepted_et"]).reset_index(drop=True)


def episodes(d: pd.DataFrame) -> pd.DataFrame:
    out = []
    for cik, g in d.groupby("cik", sort=False):
        acc = g["accepted_et"].to_numpy()
        gaps = np.diff(acc).astype("timedelta64[D]").astype(int)
        ep = np.concatenate([[0], np.cumsum(gaps >= EPISODE_GAP)])
        first = np.r_[True, ep[1:] != ep[:-1]]
        e = g.loc[first, ["cik", "accessionNumber", "accepted_et"]].copy()
        e["n_in_episode"] = np.bincount(ep)
        prev = e["accepted_et"].shift(1)
        e["days_since_prev"] = (e["accepted_et"] - prev).dt.days
        out.append(e)
    return pd.concat(out, ignore_index=True)


# ----------------------------------------------------------------------------------------- Massive bars
_local = threading.local()


def _key() -> str:
    for line in (ROOT / "massive" / ".env").read_text().splitlines():
        if line.startswith("MASSIVE_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("No MASSIVE_API_KEY in massive/.env")


def _session() -> requests.Session:
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers["Authorization"] = f"Bearer {_key()}"
        _local.s = s
    return s


def hourly(ticker: str, start: str, end: str) -> list[dict]:
    path = BARS / (hashlib.sha1(f"{ticker}|{start}|{end}".encode()).hexdigest() + ".json")
    if path.exists():
        return json.loads(path.read_text())
    url = f"https://api.massive.com/v2/aggs/ticker/{ticker}/range/1/hour/{start}/{end}"
    for attempt in range(8):
        try:
            r = _session().get(url, params={"adjusted": "true", "sort": "asc", "limit": 50000}, timeout=60)
        except requests.RequestException:
            time.sleep(min(2 ** attempt, 30))
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(2 ** attempt, 30))
            continue
        if r.status_code != 200:
            raise RuntimeError(f"{ticker} {start}..{end}: HTTP {r.status_code}")
        res = r.json().get("results") or []
        tmp = path.with_suffix(f".{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(res))
        os.replace(tmp, path)          # only successful answers are cached
        return res
    raise RuntimeError(f"{ticker} {start}..{end}: gave up after retries")


def classify(ticker: str, F: pd.Timestamp, prev_sessions: list[pd.Timestamp]):
    """Release session on F: 'amc' (after the close) or 'earlier'.

    v2 (used): extra after-hours vs extra pre-market volume on F, each as a share of the median daily volume.
    v1 (pre-registered ratio rule, kept for the audit): rAH = AH/median AH vs rPM = PM/median PM, floors 100 shares.
    v1 was found biased toward 'earlier' before any return was computed (see results.md).
    """
    start = (prev_sessions[0] - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        res = hourly(ticker, start, F.strftime("%Y-%m-%d"))
    except RuntimeError:
        return "error", "error", np.nan, np.nan, np.nan, np.nan
    if not res:
        return "nobars", "nobars", np.nan, np.nan, np.nan, np.nan
    b = pd.DataFrame(res)
    t = pd.to_datetime(b["t"], unit="ms", utc=True).dt.tz_convert("America/New_York")
    b["day"] = t.dt.tz_localize(None).dt.normalize()
    h = t.dt.hour
    b["pm"] = np.where((h >= 4) & (h <= 8), b["v"], 0.0)
    b["ah"] = np.where((h >= 16) & (h <= 19), b["v"], 0.0)
    daily = b.groupby("day")[["pm", "ah", "v"]].sum()
    if F not in daily.index:
        return "nobars", "nobars", np.nan, np.nan, np.nan, np.nan
    base = daily.reindex(prev_sessions).fillna(0.0)
    rpm = daily.at[F, "pm"] / max(base["pm"].median(), 100.0)
    rah = daily.at[F, "ah"] / max(base["ah"].median(), 100.0)
    v1 = "amc" if rah >= rpm else "earlier"
    adv = max(base["v"].median(), 1000.0)
    xpm = (daily.at[F, "pm"] - base["pm"].median()) / adv
    xah = (daily.at[F, "ah"] - base["ah"].median()) / adv
    # 'earlier' needs positive evidence of a pre-market release; otherwise trust the after-close acceptance stamp
    v2 = "earlier" if (xpm > xah and xpm >= 0.01) else "amc"
    return v2, v1, float(rah), float(rpm), float(xah), float(xpm)


def main():
    cal = pd.DatetimeIndex(pd.to_datetime(pd.read_parquet(AIW / "calendar.parquet")["date"]))
    calset = set(cal)
    fil = load_filings()
    ep = episodes(fil)
    ep.to_parquet(OUT / "episodes.parquet", index=False)
    print(f"8-K 2.02 filings {len(fil):,} ({fil['accepted_et'].min():%Y-%m-%d} → {fil['accepted_et'].max():%Y-%m-%d}); "
          f"episodes {len(ep):,}; multi-filing episodes {(ep['n_in_episode'] > 1).mean():.1%}")

    ev = ep[ep["days_since_prev"].between(*CADENCE)].copy()
    print(f"quarterly events (prev episode {CADENCE[0]}–{CADENCE[1]} days earlier): {len(ev):,} "
          f"(dropped {len(ep) - len(ev):,}: first-in-data {ep['days_since_prev'].isna().sum():,}, "
          f"off-cadence {(~ep['days_since_prev'].between(*CADENCE) & ep['days_since_prev'].notna()).sum():,})")

    ev["F"] = ev["accepted_et"].dt.normalize().astype("datetime64[ns]")
    after_close = (ev["accepted_et"] - ev["F"]) >= pd.Timedelta(hours=16)
    ev["F_is_session"] = ev["F"].isin(list(calset))
    ev["case"] = np.where(after_close & ev["F_is_session"], 2, 1)
    pos = cal.searchsorted(ev["F"], side="left")              # index of first session >= F
    ev["i_prev"] = pos - 1                                    # last session strictly before F
    ev["i_F"] = np.where(ev["F_is_session"], pos, -1)

    # ticker on F for the bars request (latest ticker the CIK traded under on or before F)
    px = pd.read_parquet(AIW / "prices.parquet", columns=["date", "cik", "ticker"]).sort_values("date")
    px["cik"] = px["cik"].astype(str).str.zfill(10)
    px["date"] = px["date"].astype("datetime64[ns]")
    tick = pd.merge_asof(ev.sort_values("F")[["F", "cik", "accessionNumber"]], px.rename(columns={"date": "F"}),
                         on="F", by="cik", direction="backward")
    ev = ev.merge(tick[["accessionNumber", "ticker"]], on="accessionNumber", how="left")

    # rough universe pre-filter for fetching (the run applies the exact point-in-time rule)
    uni = pd.read_parquet(AIW / "universe.parquet")
    uni["cik"] = uni["cik"].astype(str).str.zfill(10)
    ever = set(uni["cik"])
    c2 = ev[(ev["case"] == 2) & ev["cik"].isin(ever) & ev["ticker"].notna()
            & ev["F"].between(FETCH_FROM, FETCH_TO)].copy()
    print(f"case-2 events to classify with hourly bars: {len(c2):,} (case-1 events: {(ev['case'] == 1).sum():,})")

    jobs = []
    for r in c2.itertuples():
        i = int(r.i_F)
        if i < 21:
            continue
        jobs.append((r.accessionNumber, r.ticker, cal[i], list(cal[i - 20:i])))
    t0 = time.time()
    with ThreadPoolExecutor(12) as pool:
        out = list(pool.map(lambda j: (j[0], *classify(j[1], j[2], j[3])), jobs))
    print(f"classified {len(out):,} in {time.time() - t0:.0f}s")
    cls = pd.DataFrame(out, columns=["accessionNumber", "timing", "timing_v1", "r_ah", "r_pm", "x_ah", "x_pm"])
    ev = ev.merge(cls, on="accessionNumber", how="left")
    ev.loc[ev["case"] == 1, ["timing", "timing_v1"]] = "case1"

    # X = last clean close; case 2 'amc' or 'nobars' -> F, otherwise the session before F
    x_on_F = (ev["case"] == 2) & ev["timing"].isin(["amc", "nobars"])
    ev["i_X"] = np.where(x_on_F, ev["i_F"], ev["i_prev"])
    x_on_F1 = (ev["case"] == 2) & ev["timing_v1"].isin(["amc", "nobars"])
    ev["i_X_v1"] = np.where(x_on_F1, ev["i_F"], ev["i_prev"])
    ev["i_X_conservative"] = ev["i_prev"]
    ev = ev[ev["i_X"] >= 0].copy()
    ev["X"] = cal[ev["i_X"].to_numpy()]
    ev["E"] = [cal[i - HOLD] if i - HOLD >= 0 else pd.NaT for i in ev["i_X"]]
    ev.to_parquet(OUT / "events.parquet", index=False)

    # ------------------------------------------------------------------------------ audit (no returns)
    c2a = ev[ev["case"] == 2]
    print("\ncase-2 timing v2 (used):", c2a["timing"].value_counts(dropna=False).to_dict())
    print("case-2 timing v1 (pre-registered ratio rule):", c2a["timing_v1"].value_counts(dropna=False).to_dict())
    hh = c2a["accepted_et"].dt.hour
    for col in ["timing", "timing_v1"]:
        print(f"'earlier' share by acceptance hour ({col}):",
              c2a.assign(hh=hh).groupby("hh")[col].apply(lambda s: f"{(s == 'earlier').mean():.0%} of {len(s)}").to_dict())
    print("events by year of X:", ev.groupby(ev["X"].dt.year).size().to_dict())
    print("\nspot checks (case 2, v1 and v2 disagree):")
    dis = c2a[(c2a["timing"] != c2a["timing_v1"]) & c2a["x_ah"].notna()]
    print(f"  disagreements: {len(dis):,}")
    for r in dis.sample(min(10, len(dis)), random_state=7).itertuples():
        print(f"  {r.ticker:6s} accepted {r.accepted_et:%Y-%m-%d %H:%M}  rAH {r.r_ah:6.1f} rPM {r.r_pm:6.1f}  "
              f"xAH {r.x_ah:+.3f} xPM {r.x_pm:+.3f}  v1 {r.timing_v1} -> v2 {r.timing}")
    print("\nspot checks (case 2, labelled 'earlier' by v2):")
    for r in c2a[c2a["timing"] == "earlier"].sample(10, random_state=3).itertuples():
        print(f"  {r.ticker:6s} accepted {r.accepted_et:%Y-%m-%d %H:%M}  xAH {r.x_ah:+.3f} xPM {r.x_pm:+.3f}")


if __name__ == "__main__":
    main()
