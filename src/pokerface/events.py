"""Map video publish timestamps to tradeable entry sessions.

Rule (pre-registered in HYPOTHESIS.md):
    decision_time = publish_time + PROCESSING_BUFFER
    entry session = first regular session whose 09:30 ET open is strictly after decision_time
    exit          = the open `H` sessions after entry; P&L is marked open-to-open.

So a video uploaded at 08:00 ET is traded at that day's open (decision 10:00 ET is after the open, so it
rolls to the next session), and one uploaded at 06:00 ET is traded at 09:30 ET the same day. The buffer
covers download + feature extraction and makes the rule conservative.
"""
from __future__ import annotations

from datetime import time, timedelta

import numpy as np
import pandas as pd

ET = "America/New_York"
OPEN_TIME = time(9, 30)
PROCESSING_BUFFER = timedelta(hours=2)


def entry_session(publish_ts_utc: pd.Series, sessions: pd.DatetimeIndex,
                  buffer: timedelta = PROCESSING_BUFFER) -> pd.Series:
    """Return the entry session date (tz-naive midnight Timestamp, aligned to `sessions`) per event.

    `sessions` is the sorted index of trading dates (tz-naive dates) for which we have open prices.
    Events whose entry would fall after the last session get NaT.
    """
    ts = pd.to_datetime(publish_ts_utc, utc=True)
    decision = (ts + buffer).dt.tz_convert(ET)
    sess = pd.DatetimeIndex(sorted(pd.to_datetime(sessions).normalize().unique()))
    # open timestamp of every session in ET
    opens = pd.DatetimeIndex([pd.Timestamp.combine(d.date(), OPEN_TIME) for d in sess]).tz_localize(ET)
    out = []
    for d in decision:
        if pd.isna(d):
            out.append(pd.NaT)
            continue
        i = opens.searchsorted(d, side="right")  # first open strictly after decision time
        out.append(sess[i] if i < len(sess) else pd.NaT)
    return pd.Series(out, index=publish_ts_utc.index, dtype="datetime64[ns]")


def near_earnings(entry: pd.Series, tickers: pd.Series, earnings: pd.DataFrame,
                  sessions: pd.DatetimeIndex, window: int = 2) -> pd.Series:
    """True if an earnings release (8-K Item 2.02 filing date) is within +/- `window` sessions of entry.

    `earnings` has columns [ticker, date]. Used as a confound flag (pre-registered exclusion).
    """
    sess = pd.DatetimeIndex(sorted(pd.to_datetime(sessions).normalize().unique()))
    pos = {d: i for i, d in enumerate(sess)}
    by_tkr: dict[str, np.ndarray] = {}
    for tkr, g in earnings.groupby("ticker"):
        idx = [sess.searchsorted(pd.Timestamp(d).normalize()) for d in g["date"]]
        by_tkr[tkr] = np.array(sorted(idx))
    flags = []
    for e, t in zip(pd.to_datetime(entry), tickers):
        if pd.isna(e) or t not in by_tkr or e not in pos:
            flags.append(False)
            continue
        i = pos[e]
        arr = by_tkr[t]
        j = arr.searchsorted(i - window)
        flags.append(bool(j < len(arr) and arr[j] <= i + window))
    return pd.Series(flags, index=entry.index)
