"""The track's out-of-sample rule: hold out the most recent 20% of history or 2 years, whichever is shorter."""
from __future__ import annotations

import pandas as pd

OOS_FRACTION = 0.20
OOS_MAX_YEARS = 2


def oos_start(index: pd.DatetimeIndex) -> pd.Timestamp:
    """First timestamp of the out-of-sample period for a history spanning `index`."""
    start, end = index.min(), index.max()
    by_fraction = end - (end - start) * OOS_FRACTION
    by_cap = end - pd.DateOffset(years=OOS_MAX_YEARS)
    return max(by_fraction, by_cap)  # the later start is the shorter holdout


def truncate(data, end):
    """Cut a DataFrame/Series (or a dict of them) to rows at or before `end`."""
    if isinstance(data, (pd.DataFrame, pd.Series)):
        return data.loc[:end]
    if isinstance(data, dict):
        return {k: truncate(v, end) for k, v in data.items()}
    raise TypeError(f"Don't know how to truncate {type(data).__name__}; return a DataFrame or a dict of them from load().")
