"""Causal, fixed-cadence missing-flow hypothesis; no market results are implied.

Rows are completed bars. A target is decided at that row's end and must be
executed later by the shared simulator. Parameters are engineering placeholders.
"""

from collections import deque

import numpy as np
import pandas as pd


DEFAULTS = {
    "cadence_bars": 6,
    "window_bars": 2,
    "cycles": 3,
    "min_burst_volume": 20.0,
    "min_directional_share": 0.8,
    "repeat_min_ratio": 0.5,
    "missing_fraction": 0.2,
    "retention_fraction": 0.5,
    "min_displacement_ticks": 1.0,
    "tick_size": 0.25,
    "hold_bars": 3,
}


def _parameters(overrides):
    unknown = set(overrides) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown Missing Beat parameters: {sorted(unknown)}")
    p = DEFAULTS | overrides
    for key in ("cadence_bars", "window_bars", "cycles", "hold_bars"):
        value = p[key]
        if isinstance(value, (bool, np.bool_)) or not np.isfinite(value) or int(value) != value or value < 1:
            raise ValueError(f"{key} must be a positive integer")
        p[key] = int(value)
    if p["cadence_bars"] <= p["window_bars"] or p["cycles"] < 2:
        raise ValueError("cadence_bars must exceed window_bars, and cycles must be at least 2")
    for key in ("min_burst_volume", "tick_size", "min_displacement_ticks"):
        if not np.isfinite(p[key]) or p[key] <= 0:
            raise ValueError(f"{key} must be finite and positive")
    for key in ("min_directional_share", "repeat_min_ratio", "retention_fraction"):
        if not np.isfinite(p[key]) or not 0 < p[key] <= 1:
            raise ValueError(f"{key} must lie in (0, 1]")
    if not np.isfinite(p["missing_fraction"]) or not 0 <= p["missing_fraction"] < 1:
        raise ValueError("missing_fraction must lie in [0, 1)")
    return p


def _validate(features):
    columns = ("mid", "buy_volume", "sell_volume", "trade_volume", "signed_volume", "valid", "session", "instrument_id")
    missing = set(columns) - set(features.columns)
    if missing:
        raise ValueError(f"Missing feature columns: {sorted(missing)}")
    if not isinstance(features.index, pd.DatetimeIndex) or features.index.tz is None:
        raise ValueError("Features require a timezone-aware DatetimeIndex")
    if not features.index.is_monotonic_increasing or not features.index.is_unique:
        raise ValueError("Feature timestamps must be increasing and unique")
    return features.loc[:, list(columns)]


def _run(features, p, *, use_cadence):
    frame = _validate(features)
    targets = np.zeros(len(frame), dtype=float)
    counts = np.zeros(len(frame), dtype=int)
    due = np.zeros(len(frame), dtype=bool)
    missing = np.zeros(len(frame), dtype=bool)
    retained = np.full(len(frame), np.nan)
    # Keep only a bounded completed-bar window, never future rows.
    bars = deque(maxlen=p["window_bars"])
    events = deque(maxlen=p["cycles"])
    seed = None
    expected_end = None
    last_end = None
    previous_mid = None
    previous_key = None
    remaining = 0
    active_target = 0.0

    def clear():
        nonlocal seed, expected_end, last_end, remaining, active_target, previous_mid
        bars.clear()
        events.clear()
        seed = expected_end = last_end = previous_mid = None
        remaining = 0
        active_target = 0.0

    def window(direction):
        flow = sum(b[1] for b in bars)
        volume = sum(b[2] for b in bars)
        side = sum(b[3] if direction > 0 else b[4] for b in bars)
        extreme = max(b[0] for b in bars) if direction > 0 else min(b[0] for b in bars)
        return flow, volume, side, extreme

    def is_burst(flow, volume, direction):
        return direction * flow >= p["min_burst_volume"] and direction * flow >= p["min_directional_share"] * volume

    def event(before, direction):
        flow, volume, side, extreme = window(direction)
        return {"flow": abs(flow), "side": side, "extreme": extreme, "before": before, "direction": direction}

    for i, row in enumerate(frame.itertuples(index=False, name=None)):
        mid, buy, sell, volume, flow, valid, session, instrument = row
        key_ok = pd.notna(session) and pd.notna(instrument)
        values_ok = np.isfinite([mid, buy, sell, volume, flow]).all() and min(buy, sell, volume) >= 0
        row_ok = pd.notna(valid) and bool(valid) and key_ok and values_ok
        key = (session, instrument)
        if not row_ok:
            clear()
            previous_key = None
            continue
        if key != previous_key:
            clear()
        previous_key = key
        before_row = previous_mid
        previous_mid = mid
        bars.append((mid, flow, volume, buy, sell, before_row))

        if remaining:
            targets[i] = active_target
            remaining -= 1
            continue

        # Observe the entire first burst window after its first large bar.
        # This pins the phase causally, without selecting a phase after the fact.
        if not events and seed is None:
            if before_row is not None and abs(flow) >= p["min_burst_volume"] / p["window_bars"] and abs(flow) >= p["min_directional_share"] * volume:
                seed = {"end": i + p["window_bars"] - 1, "before": before_row, "direction": 1 if flow > 0 else -1}
        if seed is not None:
            if i == seed["end"]:
                direction = seed["direction"]
                signed, total, _, _ = window(direction)
                if len(bars) == p["window_bars"] and is_burst(signed, total, direction):
                    events.append(event(seed["before"], direction))
                    last_end = i
                    expected_end = i + (p["cadence_bars"] if use_cadence else p["window_bars"])
                seed = None
            counts[i] = len(events)
            continue

        if not events:
            continue
        counts[i] = len(events)
        direction = events[-1]["direction"]
        signed, total, side, extreme = window(direction)

        if i < expected_end:
            # A complete extra burst in the gap falsifies this cadence.
            # Windows overlapping either expected burst are not gap windows.
            if use_cadence and i >= last_end + p["window_bars"] and i <= expected_end - p["window_bars"]:
                if is_burst(abs(signed), total, 1):
                    events.clear()
                    expected_end = last_end = None
                    counts[i] = 0
            continue

        due[i] = True
        reference_flow = float(np.median([e["flow"] for e in events]))
        reference_side = float(np.median([e["side"] for e in events]))
        comparable = reference_flow * p["repeat_min_ratio"] <= direction * signed <= reference_flow / p["repeat_min_ratio"]
        if is_burst(signed, total, direction) and comparable:
            # In the baseline these are adjacent high-flow windows, not a clock.
            events.append(event(bars[0][5], direction))
            last_end = i
            expected_end = i + (p["cadence_bars"] if use_cadence else p["window_bars"])
            counts[i] = len(events)
            continue

        enough_history = len(events) >= p["cycles"] if use_cadence else True
        absent = side <= p["missing_fraction"] * reference_side and abs(signed) <= p["missing_fraction"] * reference_flow
        base = events[0]["before"]
        displacement = direction * (mid - base)
        peak = max(direction * (e["extreme"] - base) for e in events)
        retained[i] = displacement / p["tick_size"]
        price_still_displaced = displacement >= p["min_displacement_ticks"] * p["tick_size"] and displacement >= p["retention_fraction"] * peak
        if enough_history and absent and price_still_displaced:
            missing[i] = True
            active_target = float(-direction)
            targets[i] = active_target
            remaining = p["hold_bars"] - 1
        # One opportunity per identified sequence, followed by a fresh warmup.
        events.clear()
        expected_end = last_end = None

    return pd.DataFrame({"target": targets, "confirmed_bursts": counts, "observation_complete": due,
                         "missing_beat": missing, "retained_ticks": retained}, index=features.index)


def signal(features: pd.DataFrame, **params) -> pd.Series:
    """Fade an absent scheduled burst after its entire observation window closes."""
    return _run(features, _parameters(params), use_cadence=True)["target"]


def baseline(features: pd.DataFrame, **params) -> pd.Series:
    """Ordinary flow-drop comparator: fade the next quiet window after a burst.

    Uses identical flow, displacement, and holding rules but needs neither a
    repeated cadence nor multiple confirmations. Cadence/cycles are ignored.
    """
    return _run(features, _parameters(params), use_cadence=False)["target"]


def diagnostics(features: pd.DataFrame, **params) -> pd.DataFrame:
    """Return causal observation deadlines and triggers alongside desired targets."""
    return _run(features, _parameters(params), use_cadence=True)
