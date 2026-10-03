"""Independent replay/execution regression cases from implementation review."""

import numpy as np
import pandas as pd

from gqh.microdata import LAST, SNAPSHOT, BAD_RECV, mbo_features
from gqh.microengine import Execution, simulate


def _events(extra=()):
    # A complete synthetic snapshot; its additions must never count as flow.
    records = [
        (0.0, "R", "N", np.nan, 0, 0, SNAPSHOT | BAD_RECV),
        (0.0, "A", "B", 100.0, 10, 1, SNAPSHOT | BAD_RECV),
        (0.0, "A", "A", 100.25, 10, 2, SNAPSHOT | BAD_RECV | LAST),
        (0.2, "N", "N", np.nan, 0, 0, LAST),
        *extra,
        (2.1, "N", "N", np.nan, 0, 0, LAST),
    ]
    frame = pd.DataFrame(records, columns=[
        "seconds", "action", "side", "price", "size", "order_id", "flags",
    ])
    frame.index = pd.Timestamp("2026-09-01", tz="UTC") + pd.to_timedelta(frame.pop("seconds"), unit="s")
    frame.index.name = "ts_recv"
    frame["instrument_id"] = 1
    return frame


def _quotes(n=10):
    index = pd.date_range("2026-09-01 12:00", periods=n, freq="s", tz="UTC")
    return pd.DataFrame({
        "bid": 100.0, "ask": 100.25, "mid": 100.125,
        "bid_size": 10, "ask_size": 10, "instrument_id": 1,
        "session": "2026-09-01", "valid": True,
    }, index=index)


def _config():
    return Execution(latency_ms=3000, slippage_ticks=0, fee_per_side=0)


def test_bad_book_flag_cannot_create_valid_tradable_features():
    events = _events([(0.3, "N", "N", np.nan, 0, 0, LAST | 4)])
    try:
        result = mbo_features(events, max_quote_age="10s")
    except ValueError:
        return  # Rejecting the corrupt source is also an acceptable safe behavior.
    assert not result.valid.any(), "An unrecoverable feed gap must remain invalid until resnapshot"


def test_snapshot_tail_without_initial_clear_cannot_initialize_a_book():
    events = _events().iloc[1:]  # Both sides look plausible despite a missing snapshot prefix.
    try:
        result = mbo_features(events)
    except ValueError:
        return
    assert not result.valid.any(), "A partial snapshot cannot certify complete depth/queue priority"


def test_unfinished_event_at_bar_boundary_disables_old_executable_quote():
    events = _events([
        (0.8, "C", "B", 100.0, 10, 1, 0),
        (1.2, "A", "B", 99.75, 10, 3, LAST),
    ])
    result = mbo_features(events)
    assert not result.valid.iloc[0], "The old bid is already removed in an unfinished event"
    assert result.valid.iloc[1]
    assert result.bid.iloc[1] == 99.75
    assert result.bid_cancel.tolist() == [0.0, 10.0]


def test_invalid_data_discards_queued_pre_gap_entries():
    frame = _quotes()
    frame.loc[frame.index[2], "valid"] = False
    target = pd.Series([1, 1, 0, 0, 0, 0, 0, 0, 0, 0], index=frame.index)
    result = simulate(frame, target, _config())
    assert result.fills.empty, "Latency must not carry pre-gap entry signals across invalid data"


def test_invalid_data_exit_remains_pending_until_first_good_quote_after_latency():
    frame = _quotes()
    frame.loc[frame.index[4], "valid"] = False
    target = pd.Series([1, 1, 1, 1, 0, 1, 1, 1, 1, 0], index=frame.index)
    result = simulate(frame, target, _config())
    assert result.curve.position.iloc[3] == 1  # The t=0 signal became executable at t=3.
    assert result.curve.position.iloc[4] == 1  # No invented fill on the invalid quote.
    # Fault observed at t=4; recovery at t=5 cannot bypass the three-second delay.
    assert result.curve.position.iloc[5] == 1
    assert result.curve.position.iloc[6] == 1
    assert result.curve.position.iloc[7] == 0, "Invalid-data exit must latch and honor latency"
    exits = result.fills.loc[result.fills.quantity.eq(-1)]
    assert exits.iloc[0].time == frame.index[7]
    assert exits.iloc[0].decision_time == frame.index[4]


def test_fill_then_modify_and_cancel_is_not_voluntary_cancel_flow():
    events = _events([
        (0.3, "F", "A", 100.25, 4, 2, 0),
        (0.3, "M", "A", 100.25, 6, 2, LAST),
        (0.4, "F", "A", 100.25, 6, 2, 0),
        (0.4, "C", "A", 100.25, 6, 2, LAST),
        (0.5, "A", "A", 100.5, 10, 3, LAST),
    ])
    result = mbo_features(events)
    assert result.ask_cancel.sum() == 0
    assert result.ask_priority_cancel.sum() == 0
    assert result.ask.iloc[0] == 100.5
    assert result.ask_add.sum() == 10  # Snapshot adds are not liquidity replenishment.
