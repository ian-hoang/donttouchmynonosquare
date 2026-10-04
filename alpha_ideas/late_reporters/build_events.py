"""Step 1 — late-report signals and release delays (PREREGISTRATION.md). Uses filing dates only, no returns.

Run from the repo root:  uv run python alpha_ideas/late_reporters/build_events.py
Writes data/cache/late_reporters/{signals,releases}.parquet and prints an audit.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
AIW = ROOT / "data" / "cache" / "ai_washing"
OUT = ROOT / "data" / "cache" / "late_reporters"
OUT.mkdir(parents=True, exist_ok=True)
EPISODE_GAP = 21          # days: a longer gap between 2.02 filings starts a new reporting episode
LOOKBACK = 30             # days before E that still count as "reported"
O_START, O_END = "2021-07-01", "2026-03-31"
HOLD_MAX = 60             # trading days


def day0_index(accepted_et: pd.Series, cal: np.ndarray) -> np.ndarray:
    """Acceptance day if a trading day and accepted <= 16:00 ET, else the next trading day (same rule as AI-washing)."""
    d = accepted_et.dt.normalize().to_numpy()
    pos = np.searchsorted(cal, d, side="left")
    is_td = (pos < len(cal)) & (cal[np.minimum(pos, len(cal) - 1)] == d)
    late = ((accepted_et - accepted_et.dt.normalize()) > pd.Timedelta(hours=16)).to_numpy()
    return np.where(is_td & late, pos + 1, pos)


def kth_trading_day_after(cal: np.ndarray, date: np.datetime64, k: int) -> int:
    """Index of the k-th trading day strictly after `date`."""
    return int(np.searchsorted(cal, date, side="right") + k - 1)


def main():
    cal = pd.to_datetime(pd.read_parquet(AIW / "calendar.parquet")["date"]).to_numpy(dtype="datetime64[ns]")
    rel = pd.read_parquet(AIW / "sec" / "earnings_8k.parquet")
    rel["cik"] = rel["cik"].astype(str).str.zfill(10)
    rel["accepted_et"] = pd.to_datetime(rel["accepted_et"]).astype("datetime64[ns]")
    rel = rel.sort_values(["cik", "accepted_et"]).reset_index(drop=True)
    rel["i0"] = day0_index(rel["accepted_et"], cal)
    rel = rel[rel["i0"] < len(cal)].copy()

    signals, releases, n_anchor = [], [], 0
    for cik, g in rel.groupby("cik", sort=False):
        acc = g["accepted_et"].to_numpy()
        i0 = g["i0"].to_numpy()
        gaps = np.diff(acc).astype("timedelta64[D]").astype(int)
        episode = np.concatenate([[0], np.cumsum(gaps > EPISODE_GAP)])
        last_in_ep = np.r_[episode[1:] != episode[:-1], True]
        for j in np.where(last_in_ep)[0]:
            anchor = cal[i0[j]]                                   # day 0 of the episode's last filing
            E = anchor + np.timedelta64(364, "D")
            for k_obs, tag in [(3, "k3"), (5, "k5")]:
                o = kth_trading_day_after(cal, E, k_obs)
                if o >= len(cal):
                    continue
                O = cal[o]
                if not (np.datetime64(O_START) <= O <= np.datetime64(O_END)):
                    continue
                if tag == "k3":
                    n_anchor += 1
                o_close = O + np.timedelta64(16, "h")
                window_lo = E - np.timedelta64(LOOKBACK, "D")
                reported = ((acc >= window_lo) & (acc <= o_close)).any()
                if reported:
                    continue
                after = np.where(acc > o_close)[0]
                nxt = after[0] if len(after) else None
                if nxt is not None and i0[nxt] + 1 <= o + HOLD_MAX:
                    exit_i, released, rel_i0 = i0[nxt] + 1, True, i0[nxt]
                    delay = int((cal[i0[nxt]] - E).astype("timedelta64[D]").astype(int))
                    rel_acc = g["accessionNumber"].iloc[nxt]
                else:
                    exit_i, released, rel_i0, delay, rel_acc = min(o + HOLD_MAX, len(cal) - 1), False, -1, None, None
                signals.append({"cik": cik, "rule": tag, "anchor": anchor, "E": E, "O": O, "o_idx": o,
                                "exit_idx": exit_i, "released": released, "release_i0": rel_i0,
                                "delay_days": delay, "release_acc": rel_acc})
            # release delay relative to E (robustness 1 and 4): first 2.02 filing in [E - 30d, E + 90d]
            in_win = np.where((acc >= E - np.timedelta64(LOOKBACK, "D")) & (acc <= E + np.timedelta64(90, "D")))[0]
            if len(in_win):
                r = in_win[0]
                d0 = cal[i0[r]]
                nxt_later = np.where(i0 > i0[r])[0]
                releases.append({"cik": cik, "E": E, "release_i0": int(i0[r]), "release_date": d0,
                                 "delay_days": int((d0 - E).astype("timedelta64[D]").astype(int)),
                                 "next_i0": int(i0[nxt_later[0]]) if len(nxt_later) else 10**9,
                                 "acc": g["accessionNumber"].iloc[r]})
    sig = pd.DataFrame(signals)
    reldf = pd.DataFrame(releases)
    sig.to_parquet(OUT / "signals.parquet", index=False)
    reldf.to_parquet(OUT / "releases.parquet", index=False)

    # ---------------------------------------------------------------- audit (no returns)
    s3 = sig[sig["rule"] == "k3"]
    print(f"anchors with O in {O_START}..{O_END}: {n_anchor:,}; late signals (E+3): {len(s3):,} "
          f"({len(s3) / max(n_anchor, 1):.1%}); late signals (E+5): {(sig['rule'] == 'k5').sum():,}")
    print(f"late signals released within {HOLD_MAX} trading days: {s3['released'].mean():.1%}; "
          f"median holding days {np.median(s3['exit_idx'] - s3['o_idx']):.0f}")
    print("delay of the eventual release (days after E) for E+3 signals:")
    print(s3["delay_days"].describe(percentiles=[.1, .25, .5, .75, .9]).round(1).to_string())
    print("\nall releases vs E (days): share early<=-7 {:.1%}, on-time |d|<=3 {:.1%}, late>=7 {:.1%}; N {:,}".format(
        (reldf["delay_days"] <= -7).mean(), (reldf["delay_days"].abs() <= 3).mean(), (reldf["delay_days"] >= 7).mean(),
        len(reldf)))
    print("signals by year of O:", s3.groupby(pd.to_datetime(s3["O"]).dt.year).size().to_dict())
    tick = pd.read_parquet(AIW / "prices.parquet", columns=["date", "cik", "ticker"]).sort_values("date") \
             .groupby("cik")["ticker"].last()
    print("\nrandom late signals:")
    for r in s3.sample(15, random_state=2).itertuples():
        print(f"  {tick.get(r.cik, '?'):6s} anchor {pd.Timestamp(r.anchor):%Y-%m-%d} E {pd.Timestamp(r.E):%a %Y-%m-%d} "
              f"O {pd.Timestamp(r.O):%a %m-%d} -> released {r.released} "
              f"{'' if not r.released else pd.Timestamp(cal[r.release_i0]).strftime('%Y-%m-%d')} delay {r.delay_days}")


if __name__ == "__main__":
    main()
