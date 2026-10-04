"""Reactive exits use their actual trigger clock; planned deadlines are explicit."""

import numpy as np
import pandas as pd
import pytest

from gqh.microengine import Execution, simulate


def quotes(prices):
    index = pd.date_range("2026-09-01 12:00", periods=len(prices), freq="s", tz="UTC")
    bid = np.asarray(prices, dtype=float)
    return pd.DataFrame({
        "bid": bid, "ask": bid + 0.25, "mid": bid + 0.125,
        "bid_size": 10, "ask_size": 10, "valid": True,
        "session": "2026-09-01", "instrument_id": 1,
    }, index=index)


def config(**settings):
    return Execution(**{
        "slippage_ticks": 0, "fee_per_side": 0,
        "stop_loss_dollars": 50, "daily_loss_dollars": 1000,
        **settings,
    })


@pytest.mark.parametrize("latency", [0, 100])
def test_stop_observation_cannot_fill_at_the_observed_quote(latency):
    frame = quotes([100, 100, 98, 97, 97, 97])
    result = simulate(frame, pd.Series(1, index=frame.index), config(latency_ms=latency))
    entry, exit_ = result.fills.iloc[0], result.fills.iloc[1]
    assert entry.time == frame.index[1]
    assert exit_.reason == "stop_loss"
    assert exit_.decision_time == frame.index[2]
    assert exit_.time == frame.index[3]
    assert exit_.price == 97
    assert result.curve.position.iloc[2] == 1
    assert result.curve.pnl.iloc[2] == pytest.approx((98.125 - 100.25) * 50)
    assert result.summary["net_pnl"] == pytest.approx((97 - 100.25) * 50)


def test_stop_latches_through_price_recovery_and_later_signal_reversal():
    frame = quotes([100, 100, 100, 100, 98, 102, 103, 104, 104, 104])
    # Entry t=3, stop observed t=4, due t=7. Price recovery cannot cancel it.
    target = pd.Series([1, 1, -1, -1, -1, -1, 0, 0, 0, 0], index=frame.index)
    result = simulate(frame, target, config(latency_ms=2500))
    assert result.curve.position.iloc[3:7].tolist() == [1, 1, 1, 1]
    exit_ = result.fills.iloc[1]
    assert exit_.quantity == -1
    assert exit_.time == frame.index[7]
    assert exit_.decision_time == frame.index[4]
    assert exit_.price == 104
    assert exit_.reason == "stop_loss"


def test_daily_loss_latches_until_delayed_exit_and_blocks_reentry_after_recovery():
    frame = quotes([100, 100, 100, 100, 98, 102, 103, 104, 104, 104])
    result = simulate(frame, pd.Series(1, index=frame.index), config(
        latency_ms=2500, stop_loss_dollars=1000, daily_loss_dollars=50,
    ))
    assert result.fills.quantity.tolist() == [1, -1]
    exit_ = result.fills.iloc[1]
    assert exit_.reason == "daily_loss"
    assert exit_.decision_time == frame.index[4]
    assert exit_.time == frame.index[7]
    assert result.curve.position.iloc[8] == 0


def test_repeated_invalid_rows_do_not_postpone_request_and_real_exit_waits_for_quote():
    frame = quotes([100] * 12)
    frame.loc[frame.index[4:9], "valid"] = False
    target = pd.Series(1, index=frame.index)
    target.loc[frame.index[4:9]] = 0
    result = simulate(frame, target, config(latency_ms=2500))
    exit_ = result.fills.iloc[1]
    assert exit_.reason == "invalid_data_exit"
    assert exit_.decision_time == frame.index[4]
    assert exit_.time == frame.index[9]  # Due at t=6.5, first valid quote at t=9.
    assert result.curve.position.iloc[4:9].eq(1).all()


def test_risk_exit_waits_for_executable_depth_without_losing_trigger_time():
    frame = quotes([100, 100, 98, 97, 96, 96, 96])
    frame.loc[frame.index[3], "bid_size"] = 0
    result = simulate(frame, pd.Series(1, index=frame.index), config(latency_ms=100))
    exit_ = result.fills.iloc[1]
    assert exit_.time == frame.index[4]
    assert exit_.decision_time == frame.index[2]
    assert exit_.price == 96


def test_known_holding_deadline_may_preempt_later_reactive_exit():
    frame = quotes([100, 100, 100, 100, 98, 97, 96, 96, 96])
    result = simulate(frame, pd.Series(1, index=frame.index), config(
        latency_ms=2500, max_hold_seconds=2,
    ))
    exit_ = result.fills.iloc[1]
    assert result.fills.iloc[0].time == frame.index[3]
    assert exit_.time == frame.index[5]
    assert exit_.decision_time == frame.index[3]  # Scheduled when the entry filled.
    assert exit_.reason == "time_limit"


def test_known_session_close_may_preempt_later_reactive_exit():
    frame = quotes([100, 100, 100, 100, 98, 97])
    result = simulate(frame, pd.Series(1, index=frame.index), config(latency_ms=2500))
    exit_ = result.fills.iloc[1]
    assert exit_.time == frame.index[5]
    assert exit_.reason == "scheduled_close"
    assert exit_.decision_time == frame.index[0]
