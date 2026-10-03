"""H4 (HYPOTHESIS_2.md): does TELL predict the intraday reaction to Musk (TSLA) and Karp (PLTR) videos?

Per video: decision = upload + 30 min; enter at the first regular-session 1-minute bar at/after decision (else the next
session's open); exit at that session's close; hedge with QQQ at the 252-day daily beta; costs 2 bps per side on the
stock, 0.5 bp on QQQ. Release types: (a) YouTube-native (podcast, fireside/conference, panel), (b) TV clips.
Data: Databento XNAS.ITCH ohlcv-1m, priced with metadata.get_cost first (cap $10), cached in data/cache/databento/.

Usage: python scripts/h4_intraday.py   (needs DATABENTO_API_KEY in .env)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pokerface import research as R  # noqa: E402
from pokerface.signal import build_signals  # noqa: E402

ET = "America/New_York"
CACHE = ROOT / "data" / "cache" / "databento"
NATIVE = {"podcast_interview", "fireside_or_conference_qa", "panel"}
TICK = {"musk": "TSLA", "karp": "PLTR"}
MAX_USD = float(os.environ.get("DBN_MAX_USD", "10"))


def key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("DATABENTO_API_KEY="):
            return line.split("=", 1)[1].split("#")[0].strip()
    return ""


def minute_bars(client, day: pd.Timestamp, symbols: list[str]) -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"xnas_1m_{day.date()}_{'_'.join(symbols)}.parquet"
    if f.exists():
        return pd.read_parquet(f)
    start = pd.Timestamp.combine(day.date(), time(9, 30)).tz_localize(ET).tz_convert("UTC")
    end = pd.Timestamp.combine(day.date(), time(16, 0)).tz_localize(ET).tz_convert("UTC")
    df = client.timeseries.get_range(dataset="XNAS.ITCH", schema="ohlcv-1m", symbols=symbols, stype_in="raw_symbol",
                                     start=start.isoformat(), end=end.isoformat()).to_df()
    df = df.reset_index()[["ts_event", "symbol", "open", "close"]]
    df.to_parquet(f)
    return df


def main() -> None:
    import databento as db

    k = key()
    if not k:
        sys.exit("DATABENTO_API_KEY is empty in .env")
    client = db.Historical(key=k)
    strat, spec = R.load_configs()
    mkt = R.load_market()
    feat, _ = R.apply_qc(R.load_features(), strat)
    sig = build_signals(feat, spec, R.signal_params(strat))
    man = pd.read_csv(ROOT / "data" / "manifest" / "videos.csv", dtype={"video_id": str})[["video_id", "content_type"]]
    v = sig[sig["ceo_id"].isin(TICK) & sig["signal"].notna()].merge(man, on="video_id")
    v = v[v["content_type"] != "earnings_call"].copy()
    v["kind"] = np.where(v["content_type"].isin(NATIVE), "a_native", "b_tv")
    v["decision"] = pd.to_datetime(v["publish_ts_utc"], utc=True).dt.tz_convert(ET) + pd.Timedelta(minutes=30)
    sessions = mkt.open.dropna(how="all").index
    v = v[v["decision"].dt.tz_localize(None) >= pd.Timestamp("2018-05-02")]

    def session_for(d):
        day = pd.Timestamp(d.date())
        if day in sessions and d.time() < time(15, 55):
            return day, max(d, pd.Timestamp.combine(d.date(), time(9, 30)).tz_localize(ET))
        nxt = sessions[sessions.searchsorted(day, side="right")]
        return nxt, pd.Timestamp.combine(nxt.date(), time(9, 30)).tz_localize(ET)

    v[["day", "entry_ts"]] = v["decision"].apply(lambda d: pd.Series(session_for(d)))
    days = sorted(set(zip(v["day"], v["ceo_id"])))
    # price every needed request before fetching anything
    total = 0.0
    for day, ceo in days:
        if (CACHE / f"xnas_1m_{day.date()}_{TICK[ceo]}_QQQ.parquet").exists():
            continue
        s = pd.Timestamp.combine(day.date(), time(9, 30)).tz_localize(ET).tz_convert("UTC").isoformat()
        e = pd.Timestamp.combine(day.date(), time(16, 0)).tz_localize(ET).tz_convert("UTC").isoformat()
        total += client.metadata.get_cost(dataset="XNAS.ITCH", schema="ohlcv-1m", symbols=[TICK[ceo], "QQQ"],
                                          stype_in="raw_symbol", start=s, end=e)
    print(f"{len(v)} videos on {len(days)} sessions; estimated Databento cost ${total:.2f} (cap ${MAX_USD:.0f})")
    if total > MAX_USD:
        sys.exit("estimated cost above cap; nothing fetched")
    r_cc = mkt.close.pct_change()
    rows = []
    for r in v.itertuples(index=False):
        tk = TICK[r.ceo_id]
        bars = minute_bars(client, r.day, [tk, "QQQ"])
        bars["ts"] = pd.to_datetime(bars["ts_event"], utc=True).dt.tz_convert(ET)
        a, q = bars[bars["symbol"] == tk].set_index("ts").sort_index(), bars[bars["symbol"] == "QQQ"].set_index("ts").sort_index()
        a_in, q_in = a[a.index >= r.entry_ts], q[q.index >= r.entry_ts]
        if a_in.empty or q_in.empty:
            continue
        i0 = r_cc.index.searchsorted(r.day)
        y, x = r_cc[tk].values[max(0, i0 - 252):i0], r_cc["QQQ"].values[max(0, i0 - 252):i0]
        m = np.isfinite(y) & np.isfinite(x)
        beta = float(np.clip(np.cov(y[m], x[m])[0, 1] / np.var(x[m], ddof=1), 0.3, 2.5)) if m.sum() > 60 else 1.0
        ra = a["close"].iloc[-1] / a_in["open"].iloc[0] - 1
        rq = q["close"].iloc[-1] / q_in["open"].iloc[0] - 1
        gross = ra - beta * rq
        rows.append({"video_id": r.video_id, "ceo": r.ceo_id, "kind": r.kind, "day": r.day, "S": r.signal,
                     "hedged_ret": gross, "signed_net": np.sign(r.signal) * gross - 2 * (2.0 + 0.5 * beta) / 1e4,
                     "sample": "IS" if r.day <= pd.Timestamp("2024-09-30") else "OOS"})
    d = pd.DataFrame(rows)
    out = {}
    for name, g in [("a_native", d[d["kind"] == "a_native"]), ("b_tv", d[d["kind"] == "b_tv"]),
                    ("a_native_IS", d[(d["kind"] == "a_native") & (d["sample"] == "IS")]),
                    ("a_native_OOS", d[(d["kind"] == "a_native") & (d["sample"] == "OOS")]),
                    ("musk_a", d[(d["kind"] == "a_native") & (d["ceo"] == "musk")]),
                    ("karp_a", d[(d["kind"] == "a_native") & (d["ceo"] == "karp")])]:
        if len(g) < 5:
            out[name] = {"n": int(len(g))}
            continue
        per_day = g.groupby("day")["signed_net"].mean()
        out[name] = {"n": int(len(g)), "ic": float(sps.spearmanr(g["S"], g["hedged_ret"]).statistic),
                     "mean_signed_net_bps": float(g["signed_net"].mean() * 1e4),
                     "t_date_clustered": float(per_day.mean() / (per_day.std(ddof=1) / np.sqrt(len(per_day)))) if len(per_day) > 2 else None}
    out["supports_H4"] = bool(out.get("a_native", {}).get("ic", -1) > 0 and (out.get("a_native", {}).get("t_date_clustered") or 0) > 2)
    (ROOT / "results" / "h4_intraday.json").write_text(json.dumps(out, indent=2, default=str))
    d.to_csv(ROOT / "results" / "h4_intraday_events.csv", index=False)
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
