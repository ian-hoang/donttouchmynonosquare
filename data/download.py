"""Download every market input the research layer needs. No licensed data is committed; this script
recreates it. Sources (all cited in the note):

  prices   yfinance (Yahoo Finance) daily OHLCV, split- and dividend-adjusted     [default, free]
           Databento EQUS.SUMMARY / XNAS.ITCH ohlcv-1d (sponsor)                  [--source databento]
  factors  Kenneth R. French Data Library: FF5 (2x3) daily + Momentum daily
  earnings SEC EDGAR submissions API: 8-K filings with Item 2.02 (results of operations)

Usage:  python data/download.py            # prices (yfinance) + factors + earnings dates
        python data/download.py --source databento
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "market"
UA = {"User-Agent": "PokerFace research ojasvamishra@ufl.edu", "Accept-Encoding": "gzip, deflate"}
HEDGES = ["SPY", "QQQ"]
START = "2015-01-01"   # one year of pre-sample history for betas/vols before the 2016 sample start


def universe() -> pd.DataFrame:
    return pd.read_csv(ROOT / "config" / "universe.csv", dtype=str)


def all_tickers() -> list[str]:
    return sorted(set(universe()["ticker"]) | set(HEDGES))


# ----------------------------------------------------------------------------- prices

def prices_yfinance(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, actions=False,
                      progress=False, group_by="column", threads=False)
    fields = ["Open", "High", "Low", "Close", "Volume"]
    df = raw[fields].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df.sort_index()


def prices_databento(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Raw (unadjusted) consolidated daily bars; split/dividend adjustment uses Yahoo's ratio of
    adjusted to unadjusted close, documented in the note."""
    import databento as db
    import yfinance as yf

    key = os.environ.get("DATABENTO_API_KEY") or _env("DATABENTO_API_KEY")
    if not key:
        sys.exit("DATABENTO_API_KEY missing in .env")
    client = db.Historical(key=key)
    rng = client.metadata.get_dataset_range(dataset="EQUS.SUMMARY")
    ds_start = max(pd.Timestamp(start), pd.Timestamp(rng["start"]).tz_localize(None).normalize())
    cost = client.metadata.get_cost(dataset="EQUS.SUMMARY", symbols=tickers, schema="ohlcv-1d",
                                    stype_in="raw_symbol", start=ds_start.date().isoformat(), end=end)
    print(f"Databento EQUS.SUMMARY ohlcv-1d {ds_start.date()}..{end}: est. cost ${cost:.2f}")
    store = client.timeseries.get_range(dataset="EQUS.SUMMARY", schema="ohlcv-1d", symbols=tickers,
                                        stype_in="raw_symbol", start=ds_start.date().isoformat(), end=end)
    bars = store.to_df().reset_index()
    bars["date"] = pd.to_datetime(bars["ts_event"]).dt.tz_convert(None).dt.normalize()
    piv = {f.capitalize(): bars.pivot_table(index="date", columns="symbol", values=f) for f in
           ["open", "high", "low", "close", "volume"]}
    # adjustment factor = Yahoo adjusted close / Yahoo raw close (captures splits + dividends)
    yr = yf.download(tickers, start=start, end=end, auto_adjust=False, progress=False, group_by="column", threads=False)
    yr.index = pd.to_datetime(yr.index).tz_localize(None).normalize()
    factor = (yr["Adj Close"] / yr["Close"]).reindex(piv["Close"].index).ffill()
    for f in ["Open", "High", "Low", "Close"]:
        piv[f] = piv[f] * factor.reindex(columns=piv[f].columns)
    return pd.concat(piv, axis=1).sort_index()


def fingerprint(px: pd.DataFrame) -> str:
    """Hash of open-to-open returns rounded to 1e-6, so a judge can confirm they downloaded the same data."""
    r = (px["Open"].shift(-1) / px["Open"] - 1).round(6).fillna(0.0)
    return hashlib.sha256(r.to_csv().encode()).hexdigest()[:16]


# ----------------------------------------------------------------------------- factors

FRENCH = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"


def _french(url: str) -> pd.DataFrame:
    r = requests.get(url, timeout=60, headers=UA)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    lines = z.read(z.namelist()[0]).decode("latin-1").splitlines()
    hdr = next(i for i, l in enumerate(lines) if l.strip().startswith(","))
    rows = []
    for l in lines[hdr + 1:]:
        p = [x.strip() for x in l.split(",")]
        if len(p) < 2 or not (p[0].isdigit() and len(p[0]) == 8):
            if rows:
                break
            continue
        rows.append(p)
    cols = ["date"] + [c.strip() for c in lines[hdr].split(",")[1:]]
    df = pd.DataFrame(rows, columns=cols)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    return df.set_index("date").astype(float) / 100.0


def factors() -> pd.DataFrame:
    ff5 = _french(FRENCH + "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip")
    mom = _french(FRENCH + "F-F_Momentum_Factor_daily_CSV.zip")
    mom.columns = ["Mom"]
    return ff5.join(mom, how="inner")


# ----------------------------------------------------------------------------- earnings dates

def earnings_dates(tickers: list[str], start: str = START) -> pd.DataFrame:
    cikmap = {v["ticker"]: int(v["cik_str"]) for v in
              requests.get("https://www.sec.gov/files/company_tickers.json", headers=UA, timeout=30).json().values()}
    out = []
    for t in tickers:
        if t not in cikmap:
            continue
        j = requests.get(f"https://data.sec.gov/submissions/CIK{cikmap[t]:010d}.json", headers=UA, timeout=30).json()
        frames = [pd.DataFrame(j["filings"]["recent"])]
        for f in j["filings"].get("files", []):
            time.sleep(0.12)
            frames.append(pd.DataFrame(requests.get("https://data.sec.gov/submissions/" + f["name"],
                                                    headers=UA, timeout=30).json()))
        df = pd.concat(frames, ignore_index=True)
        items = df["items"].fillna("").astype(str).str.split(",").apply(lambda xs: [x.strip() for x in xs])
        m = df["form"].isin(["8-K", "8-K/A"]) & items.apply(lambda xs: "2.02" in xs)
        e = df.loc[m, ["filingDate", "acceptanceDateTime"]].copy()
        e["ticker"] = t
        out.append(e)
        time.sleep(0.15)
    e = pd.concat(out, ignore_index=True)
    e["date"] = pd.to_datetime(e["filingDate"])
    e = e[e["date"] >= start].drop_duplicates(["ticker", "date"]).sort_values(["ticker", "date"])
    return e[["ticker", "date", "acceptanceDateTime"]].reset_index(drop=True)


def _env(key: str) -> str | None:
    f = ROOT / ".env"
    if not f.exists():
        return None
    for line in f.read_text().splitlines():
        if line.startswith(key + "="):
            v = line.split("=", 1)[1].split("#")[0].strip()
            return v or None
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["yfinance", "databento"], default="yfinance")
    ap.add_argument("--end", default=pd.Timestamp.today().normalize().date().isoformat())
    ap.add_argument("--skip", nargs="*", default=[], help="any of: prices factors earnings")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    tick = all_tickers()
    meta = {}
    if "prices" not in a.skip:
        px = prices_yfinance(tick, START, a.end) if a.source == "yfinance" else prices_databento(tick, START, a.end)
        px.to_parquet(OUT / f"prices_{a.source}.parquet")
        meta["prices"] = {"source": a.source, "rows": len(px), "start": str(px.index.min().date()),
                          "end": str(px.index.max().date()), "fingerprint": fingerprint(px)}
        print("prices", meta["prices"])
    if "factors" not in a.skip:
        ff = factors()
        ff.to_parquet(OUT / "ff_factors.parquet")
        meta["factors"] = {"rows": len(ff), "end": str(ff.index.max().date())}
        print("factors", meta["factors"])
    if "earnings" not in a.skip:
        er = earnings_dates(sorted(set(universe()["ticker"])))
        er.to_parquet(OUT / "earnings_dates.parquet")
        meta["earnings"] = {"rows": len(er)}
        print("earnings", meta["earnings"])
    (OUT / "download_meta.json").write_text(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
