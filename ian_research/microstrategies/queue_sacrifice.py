"""Causal FIFO cancellation-priority hypothesis; no demonstrated trading edge.

Input timestamps label completed bars. The returned target is a decision made
after that bar; the execution engine must apply a later, executable quote.
The replay layer supplies voluntary at-touch cancel quantity and that quantity
weighted by 1 / (1 + quantity ahead immediately before the cancellation).
This weight is an explicit queue-position proxy, not a queue valuation model.
"""

from __future__ import annotations

import numbers

import numpy as np
import pandas as pd


DEFAULTS = {"window": 10, "threshold": 0.5, "min_cancel_qty": 20.0}
_QUANTITIES = [
    "bid_cancel", "ask_cancel", "bid_priority_cancel", "ask_priority_cancel",
]
_REQUIRED = ["bid", "ask", "valid", "session", "instrument_id", *_QUANTITIES]


def _parameters(window: int, threshold: float, min_cancel_qty: float) -> None:
    if isinstance(window, bool) or not isinstance(window, numbers.Integral) or window < 1:
        raise ValueError("window must be a positive integer")
    if not np.isfinite(threshold) or not 0 < threshold <= 1:
        raise ValueError("threshold must be finite and in (0, 1]")
    if not np.isfinite(min_cancel_qty) or min_cancel_qty < 0:
        raise ValueError("min_cancel_qty must be finite and nonnegative")


def diagnostics(
    features: pd.DataFrame,
    window: int = DEFAULTS["window"],
    threshold: float = DEFAULTS["threshold"],
    min_cancel_qty: float = DEFAULTS["min_cancel_qty"],
) -> pd.DataFrame:
    """Return trailing scores and common eligibility on the original index.

Warmup requires ``window`` consecutive usable bars in one session/instrument.
Missing, negative, or inconsistent cancel quantities fail closed and restart
warmup. A UTC calendar-date session is a research boundary, not an exchange
trading-session definition. Zero cancellation windows have zero scores.
"""
    _parameters(window, threshold, min_cancel_qty)
    idx = features.index
    if not isinstance(idx, pd.DatetimeIndex) or str(idx.tz) != "UTC":
        raise ValueError("features must have a UTC DatetimeIndex")
    if not idx.is_monotonic_increasing or not idx.is_unique:
        raise ValueError("features index must be sorted and unique")
    missing = sorted(set(_REQUIRED) - set(features.columns))
    if missing:
        raise ValueError(f"missing Queue Sacrifice features: {', '.join(missing)}")
    if features.empty:
        return pd.DataFrame({
            "score": pd.Series(index=idx, dtype=float),
            "baseline_score": pd.Series(index=idx, dtype=float),
            "cancel_qty": pd.Series(index=idx, dtype=float),
            "priority_cancel_qty": pd.Series(index=idx, dtype=float),
            "eligible": pd.Series(index=idx, dtype=bool),
        }, index=idx)

    qty = features[_QUANTITIES].apply(pd.to_numeric, errors="coerce")
    quotes = features[["bid", "ask"]].apply(pd.to_numeric, errors="coerce")
    usable = (
        features["valid"].eq(True).fillna(False)
        & np.isfinite(quotes).all(axis=1)
        & quotes["ask"].gt(quotes["bid"])
        & np.isfinite(qty).all(axis=1)
        & qty.ge(0).all(axis=1)
        & qty["bid_priority_cancel"].le(qty["bid_cancel"] + 1e-9)
        & qty["ask_priority_cancel"].le(qty["ask_cancel"] + 1e-9)
        & features["session"].notna()
        & features["instrument_id"].notna()
    )
    boundary = (
        ~usable
        | ~usable.shift(1, fill_value=False)
        | features["session"].ne(features["session"].shift(1))
        | features["instrument_id"].ne(features["instrument_id"].shift(1))
    )
    groups = boundary.cumsum()
    totals = (
        qty.where(usable, 0.0)
        .groupby(groups, sort=False)
        .rolling(window, min_periods=window)
        .sum()
        .droplevel(0)
        .reindex(idx)
    )
    raw_total = totals["ask_cancel"] + totals["bid_cancel"]
    priority_total = totals["ask_priority_cancel"] + totals["bid_priority_cancel"]
    score = (totals["ask_priority_cancel"] - totals["bid_priority_cancel"]).div(
        priority_total.where(priority_total > 0)
    )
    baseline_score = (totals["ask_cancel"] - totals["bid_cancel"]).div(
        raw_total.where(raw_total > 0)
    )
    eligible = usable & raw_total.ge(min_cancel_qty) & raw_total.gt(0)
    return pd.DataFrame({
        "score": score.fillna(0.0).clip(-1.0, 1.0),
        "baseline_score": baseline_score.fillna(0.0).clip(-1.0, 1.0),
        "cancel_qty": raw_total.fillna(0.0),
        "priority_cancel_qty": priority_total.fillna(0.0),
        "eligible": eligible,
    }, index=idx)


def _target(diag: pd.DataFrame, column: str, threshold: float) -> pd.Series:
    score = diag[column]
    target = np.where(diag["eligible"] & score.abs().ge(threshold), np.sign(score), 0)
    return pd.Series(target, index=diag.index, name="target", dtype="int8")


def signal(
    features: pd.DataFrame,
    window: int = DEFAULTS["window"],
    threshold: float = DEFAULTS["threshold"],
    min_cancel_qty: float = DEFAULTS["min_cancel_qty"],
) -> pd.Series:
    """+1 when priority-weighted ask cancels dominate, -1 for bid cancels.

The runner must verify that the selected instrument uses FIFO matching. MBO
order IDs do not identify participants or explain why an order was canceled.
Targets are recomputed every bar; execution, costs, and risk limits live in the
shared engine. There is no same-bar fill or future-return input here.
"""
    diag = diagnostics(features, window, threshold, min_cancel_qty)
    return _target(diag, "score", threshold)


def baseline(
    features: pd.DataFrame,
    window: int = DEFAULTS["window"],
    threshold: float = DEFAULTS["threshold"],
    min_cancel_qty: float = DEFAULTS["min_cancel_qty"],
) -> pd.Series:
    """Ordinary cancel imbalance with the identical raw-activity eligibility.

Both methods inspect the same valid MBO-derived sample; the only change is
whether cancellation quantities are weighted by queue position.
"""
    diag = diagnostics(features, window, threshold, min_cancel_qty)
    return _target(diag, "baseline_score", threshold)
