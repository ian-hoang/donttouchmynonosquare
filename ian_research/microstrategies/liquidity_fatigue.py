"""Causal prototype: trade a new burst after earlier recovery episodes worsen.

The output is a decision after each completed bar, never an executable fill.
No episode contributes until its fixed recovery window has finished. See the
preregistered hypothesis for limitations of best-quote recovery measurements.
"""

from collections import deque

import numpy as np
import pandas as pd


DEFAULTS = {
    "lookback": 60,
    "burst_multiple": 2.5,
    "imbalance_threshold": 0.6,
    "min_volume": 1.0,
    "min_depth_drop": 0.1,
    "recovery_bars": 5,
    "recovery_fraction": 0.9,
    "history_events": 3,
    "comparable_ratio": 2.0,
    "event_max_age": 600,
    "refill_drop": 0.2,
    "recovery_delay": 1.0,
    "impact_growth": 0.25,
    "min_components": 2,
    "hold_bars": 10,
}

_NUMERIC = (
    "bid", "ask", "mid", "bid_size", "ask_size", "trade_volume", "signed_volume"
)


def _parameters(params):
    unknown = set(params) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown Liquidity Fatigue parameters: {sorted(unknown)}")
    p = {**DEFAULTS, **params}
    for name, value in p.items():
        if isinstance(value, (bool, np.bool_)) or not np.isfinite(float(value)):
            raise ValueError(f"{name} must be a finite number")
    for name in ("lookback", "recovery_bars", "history_events", "event_max_age",
                 "min_components", "hold_bars"):
        if float(p[name]) != int(p[name]) or p[name] < 1:
            raise ValueError(f"{name} must be a positive integer")
        p[name] = int(p[name])
    if p["history_events"] < 2 or p["min_components"] > 3:
        raise ValueError("history_events must be >= 2 and min_components <= 3")
    for name in ("burst_multiple", "min_volume", "refill_drop", "recovery_delay", "impact_growth"):
        if p[name] <= 0:
            raise ValueError(f"{name} must be positive")
    for name in ("imbalance_threshold", "min_depth_drop", "recovery_fraction"):
        if not 0 < p[name] <= 1:
            raise ValueError(f"{name} must be in (0, 1]")
    if p["comparable_ratio"] < 1:
        raise ValueError("comparable_ratio must be >= 1")
    return p


def _input(features):
    if not isinstance(features.index, pd.DatetimeIndex):
        raise ValueError("features must have a UTC DatetimeIndex")
    if features.index.tz is None or str(features.index.tz) != "UTC":
        raise ValueError("features must have a UTC DatetimeIndex")
    if not features.index.is_unique or not features.index.is_monotonic_increasing:
        raise ValueError("features index must be sorted and unique")
    missing = set((*_NUMERIC, "valid", "session", "instrument_id")) - set(features)
    if missing:
        raise ValueError(f"Missing features: {sorted(missing)}")
    values = features.loc[:, _NUMERIC].to_numpy(dtype=float)
    good = np.isfinite(values).all(axis=1)
    good &= features["valid"].fillna(False).to_numpy(dtype=bool)
    good &= features["session"].notna().to_numpy()
    good &= features["instrument_id"].notna().to_numpy()
    bid, ask, mid, bids, asks, volume, signed = values.T
    good &= (ask > bid) & (mid >= bid) & (mid <= ask)
    good &= (bids > 0) & (asks > 0) & (volume >= 0)
    good &= np.abs(signed) <= volume + 1e-10
    return values, good


def _deterioration(events, p):
    """Require monotone deterioration, using only already completed events."""
    refill = np.array([e["refill"] for e in events])
    delay = np.array([e["delay"] for e in events])
    impact = np.array([e["impact"] for e in events])
    refill_drop = refill[0] - refill[-1]
    delay_increase = delay[-1] - delay[0]
    impact_increase = impact[-1] / impact[0] - 1 if impact[0] > 0 else np.nan
    worsening = (
        refill_drop >= p["refill_drop"] and np.all(np.diff(refill) <= 1e-12),
        delay_increase >= p["recovery_delay"] and np.all(np.diff(delay) >= 0),
        impact_increase >= p["impact_growth"] and np.all(np.diff(impact) >= -1e-12),
    )
    return sum(worsening), refill_drop, delay_increase, impact_increase


def diagnostics(features: pd.DataFrame, **params) -> pd.DataFrame:
    """Return causal decisions and event diagnostics on the unchanged index.

    NaN diagnostic changes mean there is insufficient comparable history.
    ``completed_events`` counts retained completed observations in either
    direction. ``components`` is evaluated only at a subsequent burst.
    """
    p = _parameters(params)
    values, good = _input(features)
    n = len(features)
    out = pd.DataFrame({
        "target": np.zeros(n, dtype=float),
        "baseline": np.zeros(n, dtype=float),
        "burst": np.zeros(n, dtype=float),
        "completed_events": np.zeros(n, dtype=int),
        "comparable_events": np.zeros(n, dtype=int),
        "components": np.zeros(n, dtype=int),
        "refill_drop": np.full(n, np.nan),
        "recovery_delay": np.full(n, np.nan),
        "impact_growth": np.full(n, np.nan),
    }, index=features.index)
    columns = {name: j for j, name in enumerate(out.columns)}
    # A single loop makes the information clock explicit. No full-sample
    # normalization, centered windows, or backfilling is used.
    results = out.to_numpy()
    sessions = features["session"].to_numpy()
    instruments = features["instrument_id"].to_numpy()
    past_volume = deque(maxlen=p["lookback"])
    completed = []
    pending = None
    previous = None
    previous_key = None
    position = base_position = remaining = base_remaining = 0

    for i, row in enumerate(values):
        key = (sessions[i], instruments[i])
        if not good[i] or key != previous_key:
            past_volume.clear()
            completed.clear()
            pending = previous = None
            position = base_position = remaining = base_remaining = 0
        previous_key = key
        if not good[i]:
            continue
        bid, ask, mid, bid_size, ask_size, volume, signed = row
        direction = 0
        if len(past_volume) == p["lookback"] and previous is not None:
            reference = max(float(np.median(past_volume)), p["min_volume"])
            if (volume > 0 and abs(signed) >= p["burst_multiple"] * reference
                    and abs(signed) / volume >= p["imbalance_threshold"]):
                direction = int(np.sign(signed))
        results[i, columns["burst"]] = direction

        # Another large flow burst makes the recovery window ambiguous. It
        # cannot become an observation of the original isolated shock.
        if pending is not None:
            if direction:
                pending = None
            else:
                depth = ask_size if pending["direction"] > 0 else bid_size
                elapsed = i - pending["origin"]
                if pending["delay"] is None and depth >= p["recovery_fraction"] * pending["pre_depth"]:
                    pending["delay"] = elapsed
                if elapsed == p["recovery_bars"]:
                    refill = (depth - pending["shock_depth"]) / (
                        pending["pre_depth"] - pending["shock_depth"]
                    )
                    completed.append({
                        "origin": pending["origin"], "direction": pending["direction"],
                        "volume": pending["volume"], "impact": pending["impact"],
                        "refill": float(np.clip(refill, 0, 2)),
                        "delay": pending["delay"] or p["recovery_bars"] + 1,
                    })
                    pending = None

        completed = [e for e in completed if i - e["origin"] <= p["event_max_age"]]
        results[i, columns["completed_events"]] = len(completed)
        trigger = 0
        if direction:
            events = [e for e in completed if e["direction"] == direction][-p["history_events"]:]
            volumes = [e["volume"] for e in events] + [abs(signed)]
            comparable = max(volumes) / min(volumes) <= p["comparable_ratio"]
            results[i, columns["comparable_events"]] = len(events) if comparable else 0
            if len(events) == p["history_events"] and comparable:
                score, refill_drop, delay_increase, impact_growth = _deterioration(events, p)
                for name, value in (("components", score), ("refill_drop", refill_drop),
                                    ("recovery_delay", delay_increase), ("impact_growth", impact_growth)):
                    results[i, columns[name]] = value
                if score >= p["min_components"]:
                    trigger = direction

            pre_depth = previous[4] if direction > 0 else previous[3]
            shock_depth = ask_size if direction > 0 else bid_size
            if (pre_depth - shock_depth) / pre_depth >= p["min_depth_drop"]:
                pending = {
                    "origin": i, "direction": direction, "volume": abs(signed),
                    "pre_depth": pre_depth, "shock_depth": shock_depth,
                    "impact": max(0.0, direction * (mid - previous[2])) / abs(signed),
                    "delay": None,
                }

        if remaining == 0 and trigger:
            position, remaining = trigger, p["hold_bars"]
        if base_remaining == 0 and direction:
            base_position, base_remaining = direction, p["hold_bars"]
        results[i, columns["target"]] = position if remaining else 0
        results[i, columns["baseline"]] = base_position if base_remaining else 0
        remaining = max(0, remaining - 1)
        base_remaining = max(0, base_remaining - 1)
        past_volume.append(volume)
        previous = row

    # to_numpy may be a copy because diagnostic columns have mixed dtypes.
    return pd.DataFrame(results, index=features.index, columns=out.columns)


def signal(features: pd.DataFrame, **params) -> pd.Series:
    """Desired one-contract direction, decided after each completed bar."""
    return diagnostics(features, **params)["target"].rename("target")


def baseline(features: pd.DataFrame, **params) -> pd.Series:
    """Ordinary signed-burst continuation, with the same clock and holding time."""
    return diagnostics(features, **params)["baseline"].rename("target")
