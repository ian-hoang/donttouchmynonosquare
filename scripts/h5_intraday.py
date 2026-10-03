"""H5 (HYPOTHESIS_2.md): the intraday tell on the other 39 CEO stints (original universe minus Musk/Karp + H2).

Per video: decision = upload + 30 min; enter at the first regular-session 1-minute bar at/after decision (else the next
open); exit at that session's close; hedge with SPY at the 252-day daily beta; costs 3 bps/side stock, 0.5 bp SPY.
Primary: Spearman IC of S vs hedged entry-to-close return, one-sided p from 2,000 within-CEO permutations.

Usage: python scripts/h5_intraday.py   (DATABENTO_API_KEY in .env; minute windows cached in data/cache/databento/)
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pokerface import research as R  # noqa: E402
from pokerface import stats as S  # noqa: E402
from pokerface.signal import build_signals  # noqa: E402

ET = "America/New_York"
CACHE = ROOT / "data" / "cache" / "databento"
NATIVE = {"podcast_interview", "fireside_or_conference_qa", "panel"}
MAX_USD = float(os.environ.get("DBN_MAX_USD", "10"))
COST_STOCK, COST_SPY = 3.0, 0.5


def key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("DATABENTO_API_KEY="):
            return line.split("=", 1)[1].split("#")[0].strip()
    return ""


def window(day):
    s = pd.Timestamp.combine(day.date(), time(9, 30)).tz_localize(ET).tz_convert("UTC").isoformat()
    e = pd.Timestamp.combine(day.date(), time(16, 0)).tz_localize(ET).tz_convert("UTC").isoformat()
    return s, e


def cache_file(day, tk):
    return CACHE / f"xnas_1m_{day.date()}_{tk}_SPY.parquet"


def fetch(args):
    import databento as db

    day, tk = args
    f = cache_file(day, tk)
    if f.exists():
        return True
    s, e = window(day)
    try:
        df = db.Historical(key=key()).timeseries.get_range(dataset="XNAS.ITCH", schema="ohlcv-1m", symbols=[tk, "SPY"],
                                                           stype_in="raw_symbol", start=s, end=e).to_df()
        df.reset_index()[["ts_event", "symbol", "open", "close"]].to_parquet(f)
        return True
    except Exception as ex:
        print("fetch failed", day.date(), tk, str(ex)[:80], flush=True)
        return False


def videos_for(universe: str, mkt) -> pd.DataFrame:
    os.environ["PF_UNIVERSE"] = universe
    strat, spec = R.load_configs()
    f = pd.read_csv(ROOT / "data" / "features" / f"video_features{universe}.csv", dtype={"video_id": str})
    f["publish_ts_utc"] = pd.to_datetime(f["publish_ts_utc"], utc=True)
    feat, _ = R.apply_qc(f, strat)
    sig = build_signals(feat, spec, R.signal_params(strat))
    man = pd.read_csv(ROOT / "data" / "manifest" / f"videos{universe}.csv", dtype={"video_id": str})[["video_id", "content_type"]]
    v = sig[sig["signal"].notna() & ~sig["ceo_id"].isin(["musk", "karp"])].merge(man, on="video_id")
    return v[v["content_type"] != "earnings_call"].assign(universe=universe or "original")


def main() -> None:
    import databento as db

    if not key():
        sys.exit("DATABENTO_API_KEY is empty in .env")
    mkt = R.load_market()
    v = pd.concat([videos_for("", mkt), videos_for("_h2", mkt)], ignore_index=True)
    v["kind"] = np.where(v["content_type"].isin(NATIVE), "native", "tv")
    v["decision"] = pd.to_datetime(v["publish_ts_utc"], utc=True).dt.tz_convert(ET) + pd.Timedelta(minutes=30)
    v = v[v["decision"].dt.tz_localize(None) >= pd.Timestamp("2018-05-02")]
    v = v[v["ticker"].isin(mkt.close.columns)]
    sessions = mkt.open.dropna(how="all").index

    def session_for(d):
        day = pd.Timestamp(d.date())
        if day in sessions and d.time() < time(15, 55):
            return day, max(d, pd.Timestamp.combine(d.date(), time(9, 30)).tz_localize(ET))
        i = sessions.searchsorted(day, side="right")
        if i >= len(sessions):
            return pd.NaT, pd.NaT
        nxt = sessions[i]
        return nxt, pd.Timestamp.combine(nxt.date(), time(9, 30)).tz_localize(ET)

    v[["day", "entry_ts"]] = v["decision"].apply(lambda d: pd.Series(session_for(d)))
    v = v.dropna(subset=["day"])
    v = v[v["day"] <= pd.Timestamp("2026-09-30")]
    reqs = sorted({(d, t) for d, t in zip(v["day"], v["ticker"])})
    todo = [r for r in reqs if not cache_file(*r).exists()]
    client = db.Historical(key=key())
    rng = np.random.default_rng(1)
    sample = [todo[i] for i in rng.choice(len(todo), size=min(40, len(todo)), replace=False)] if todo else []
    est = sum(client.metadata.get_cost(dataset="XNAS.ITCH", schema="ohlcv-1m", symbols=[t, "SPY"], stype_in="raw_symbol",
                                       start=window(d)[0], end=window(d)[1]) for d, t in sample)
    est_total = est / max(len(sample), 1) * len(todo)
    print(f"{len(v)} videos, {len(reqs)} (session, ticker) windows, {len(todo)} to fetch; est. cost ${est_total:.2f} (cap ${MAX_USD:.0f})", flush=True)
    if est_total > MAX_USD:
        sys.exit("estimated cost above cap; nothing fetched")
    CACHE.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=8) as ex:
        ok = sum(ex.map(fetch, todo))
    print(f"fetched {ok}/{len(todo)}", flush=True)

    r_cc = mkt.close.pct_change()
    rows = []
    for r in v.itertuples(index=False):
        f = cache_file(r.day, r.ticker)
        if not f.exists():
            continue
        bars = pd.read_parquet(f)
        bars["ts"] = pd.to_datetime(bars["ts_event"], utc=True).dt.tz_convert(ET)
        a = bars[bars["symbol"] == r.ticker].set_index("ts").sort_index()
        q = bars[bars["symbol"] == "SPY"].set_index("ts").sort_index()
        a_in, q_in = a[a.index >= r.entry_ts], q[q.index >= r.entry_ts]
        if len(a_in) < 2 or len(q_in) < 2:
            continue
        i0 = r_cc.index.searchsorted(r.day)
        y, x = r_cc[r.ticker].values[max(0, i0 - 252):i0], r_cc["SPY"].values[max(0, i0 - 252):i0]
        m = np.isfinite(y) & np.isfinite(x)
        beta = float(np.clip(np.cov(y[m], x[m])[0, 1] / np.var(x[m], ddof=1), 0.3, 2.5)) if m.sum() > 60 else 1.0
        hedged = (a["close"].iloc[-1] / a_in["open"].iloc[0] - 1) - beta * (q["close"].iloc[-1] / q_in["open"].iloc[0] - 1)
        cost = 2 * (COST_STOCK + COST_SPY * beta) / 1e4
        rows.append({"video_id": r.video_id, "ceo": r.ceo_id, "universe": r.universe, "kind": r.kind, "day": r.day,
                     "S": r.signal, "hedged_ret": hedged, "signed_net": np.sign(r.signal) * hedged - cost,
                     "sample": "IS" if r.day <= pd.Timestamp("2024-09-30") else "OOS"})
    d = pd.DataFrame(rows)

    def ic_perm(g, n=2000, seed=7):
        ic = float(sps.spearmanr(g["S"], g["hedged_ret"]).statistic)
        rr = np.random.default_rng(seed)
        perm = []
        for _ in range(n):
            s2 = g.groupby("ceo")["S"].transform(lambda x: rr.permutation(x.values))
            perm.append(sps.spearmanr(s2, g["hedged_ret"]).statistic)
        return ic, float((np.array(perm) >= ic).mean())

    def trade(g):
        per_day = g.groupby("day")["signed_net"].mean()
        daily = per_day.reindex(pd.DatetimeIndex(sessions[(sessions >= g["day"].min()) & (sessions <= g["day"].max())]), fill_value=0.0)
        return {"n": int(len(g)), "mean_signed_net_bps": float(g["signed_net"].mean() * 1e4),
                "t_date_clustered": float(per_day.mean() / (per_day.std(ddof=1) / np.sqrt(len(per_day)))) if len(per_day) > 2 else None,
                "hit_rate": float((g["signed_net"] > 0).mean()), "daily_sharpe": S.sharpe(daily),
                "max_drawdown": S.max_drawdown(daily)}

    ic, p = ic_perm(d)
    out = {"primary": {"n": int(len(d)), "ic": ic, "perm_p_one_sided": p, **trade(d)}, "supports_H5": bool(ic > 0 and p < 0.05)}
    for name, g in [("native", d[d["kind"] == "native"]), ("tv", d[d["kind"] == "tv"]), ("original_18", d[d["universe"] == "original"]),
                    ("h2", d[d["universe"] == "_h2"]), ("IS", d[d["sample"] == "IS"]), ("OOS", d[d["sample"] == "OOS"])]:
        if len(g) >= 20:
            out[name] = {"ic": float(sps.spearmanr(g["S"], g["hedged_ret"]).statistic), **trade(g)}
    (ROOT / "results" / "h5_intraday.json").write_text(json.dumps(out, indent=2, default=str))
    d.to_csv(ROOT / "results" / "h5_intraday_events.csv", index=False)
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
