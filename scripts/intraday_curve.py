"""Intraday absorption curve (descriptive, uses the H4 + H5 events after their evaluation).

For each event: beta-hedged cumulative return from the entry minute to each later minute of the session (5-minute
grid), from the cached Databento 1-minute bars. Averages by TELL tercile (high tell = stressed vs. own baseline).

Usage: python scripts/intraday_curve.py -> results/figures/intraday_curve.png, results/intraday_curve.csv
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache" / "databento"
ET = "America/New_York"
GRID = np.arange(0, 391, 5)


def path(ev, f, tk, hedge, beta):
    bars = pd.read_parquet(f)
    bars["ts"] = pd.to_datetime(bars["ts_event"], utc=True).dt.tz_convert(ET)
    a = bars[bars["symbol"] == tk].set_index("ts")["close"].sort_index()
    h = bars[bars["symbol"] == hedge].set_index("ts")["close"].sort_index()
    t0 = pd.Timestamp(ev["entry_ts"]).tz_convert(ET) if pd.Timestamp(ev["entry_ts"]).tzinfo else pd.Timestamp(ev["entry_ts"]).tz_localize(ET)
    a, h = a[a.index >= t0], h[h.index >= t0]
    if len(a) < 2 or len(h) < 2:
        return None
    mins_a = ((a.index - t0).total_seconds() / 60).values
    mins_h = ((h.index - t0).total_seconds() / 60).values
    ra = np.interp(GRID, mins_a, a.values / a.values[0] - 1, right=np.nan)
    rh = np.interp(GRID, mins_h, h.values / h.values[0] - 1, right=np.nan)
    return ra - beta * rh


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    frames = []
    for fname, hedge in (("h4_intraday_events.csv", "QQQ"), ("h5_intraday_events.csv", "SPY")):
        p = ROOT / "results" / fname
        if p.exists():
            frames.append(pd.read_csv(p, parse_dates=["day"]).assign(hedge=hedge))
    ev = pd.concat(frames, ignore_index=True)
    if "ticker" not in ev:
        tick = {"musk": "TSLA", "karp": "PLTR"}
        man = pd.concat([pd.read_csv(ROOT / "data/manifest/videos.csv"), pd.read_csv(ROOT / "data/manifest/videos_h2.csv")])
        ev = ev.merge(man[["video_id", "ticker"]].drop_duplicates("video_id"), on="video_id", how="left")
    # entry timestamps and betas are recomputed the same way as in the H4/H5 scripts
    vids = pd.concat([pd.read_csv(ROOT / "data/manifest/videos.csv"), pd.read_csv(ROOT / "data/manifest/videos_h2.csv")])
    ev = ev.merge(vids[["video_id", "publish_ts_utc"]].drop_duplicates("video_id"), on="video_id", how="left")
    dec = pd.to_datetime(ev["publish_ts_utc"], utc=True).dt.tz_convert(ET) + pd.Timedelta(minutes=30)
    open_ = pd.to_datetime(ev["day"]).dt.tz_localize(ET) + pd.Timedelta(hours=9, minutes=30)
    same_day = dec.dt.tz_localize(None).dt.normalize() == pd.to_datetime(ev["day"])
    ev["entry_ts"] = np.where(same_day & (dec > open_), dec, open_)
    rows = []
    for e in ev.to_dict("records"):
        f = CACHE / f"xnas_1m_{pd.Timestamp(e['day']).date()}_{e['ticker']}_{e['hedge']}.parquet"
        if not f.exists():
            continue
        pth = path(e, f, e["ticker"], e["hedge"], 1.0)
        if pth is not None:
            rows.append((e["S"], pth))
    S = np.array([r[0] for r in rows])
    P = np.vstack([r[1] for r in rows])
    q = pd.qcut(pd.Series(S).rank(method="first"), 3, labels=["high tell (stressed)", "mid", "low tell (calm)"])
    out = pd.DataFrame({"minutes": GRID})
    fig, ax = plt.subplots(figsize=(6.6, 3.0))
    colors = {"high tell (stressed)": "#c0392b", "mid": "#9ca3af", "low tell (calm)": "#1d7a63"}
    for lab in ["low tell (calm)", "mid", "high tell (stressed)"]:
        m = (q == lab).values
        mean = np.nanmean(P[m], axis=0) * 1e4
        se = np.nanstd(P[m], axis=0) / np.sqrt(np.sum(np.isfinite(P[m]), axis=0)) * 1e4
        out[lab] = mean
        ax.plot(GRID, mean, color=colors[lab], lw=1.8 if lab != "mid" else 1, label=f"{lab} (n={m.sum()})")
        if lab != "mid":
            ax.fill_between(GRID, mean - 1.96 * se, mean + 1.96 * se, color=colors[lab], alpha=0.12, lw=0)
    ax.axhline(0, color="#9ca3af", lw=0.6)
    ax.set_xlabel("minutes after entry (entry = upload + 30 min, or next open)")
    ax.set_ylabel("market-hedged return (bps)")
    ax.legend(frameon=False, fontsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.savefig(ROOT / "results" / "figures" / "intraday_curve.png", dpi=150, bbox_inches="tight")
    out.to_csv(ROOT / "results" / "intraday_curve.csv", index=False)
    print(f"{len(rows)} event paths; close-of-day mean (bps):", {k: round(float(out[k].dropna().iloc[-1]), 1) for k in out.columns if k != "minutes"})


if __name__ == "__main__":
    main()
