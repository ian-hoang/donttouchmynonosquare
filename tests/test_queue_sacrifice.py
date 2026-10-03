import numpy as np
import pandas as pd
import pytest

from microstrategies import queue_sacrifice as qs


def features(n=12):
    idx = pd.date_range("2026-09-01 12:00", periods=n, freq="s", tz="UTC")
    return pd.DataFrame({
        "bid": 100.0, "ask": 100.25, "valid": True,
        "session": "2026-09-01", "instrument_id": 1,
        "bid_cancel": 10.0, "ask_cancel": 10.0,
        "bid_priority_cancel": 1.0, "ask_priority_cancel": 9.0,
    }, index=idx)


def test_equal_raw_cancels_distinguished_by_queue_position():
    f = features(6)
    params = dict(window=3, threshold=0.5, min_cancel_qty=50)
    assert qs.signal(f, **params).tolist() == [0, 0, 1, 1, 1, 1]
    assert qs.baseline(f, **params).tolist() == [0] * 6
    f[["bid_priority_cancel", "ask_priority_cancel"]] = [9.0, 1.0]
    assert qs.signal(f, **params).tolist() == [0, 0, -1, -1, -1, -1]


def test_all_front_cancels_reduce_to_ordinary_cancellation_baseline():
    f = features()
    f["bid_cancel"] = 2.0
    f["ask_cancel"] = 10.0
    f["bid_priority_cancel"] = f["bid_cancel"]
    f["ask_priority_cancel"] = f["ask_cancel"]
    pd.testing.assert_series_equal(qs.signal(f, window=3), qs.baseline(f, window=3))
    assert qs.signal(f, window=3).iloc[-1] == 1


@pytest.mark.parametrize("method", [qs.signal, qs.baseline])
def test_exact_prefix_invariance_and_future_perturbation(method):
    f = features(60)
    rng = np.random.default_rng(19)
    for side in ["bid", "ask"]:
        f[f"{side}_cancel"] = rng.integers(0, 40, len(f)).astype(float)
        f[f"{side}_priority_cancel"] = f[f"{side}_cancel"] * rng.uniform(0.05, 1, len(f))
    f.loc[f.index[21], "valid"] = False
    f.loc[f.index[40]:, "session"] = "2026-09-02"
    expected = method(f, window=5)
    for stop in range(1, len(f) + 1):
        pd.testing.assert_series_equal(method(f.iloc[:stop], window=5), expected.iloc[:stop])
    changed = f.copy()
    changed.loc[changed.index[30]:, "bid_cancel"] = 1_000_000.0
    changed.loc[changed.index[30]:, "bid_priority_cancel"] = 1_000_000.0
    pd.testing.assert_series_equal(method(changed, window=5).iloc[:30], expected.iloc[:30])


@pytest.mark.parametrize("column,value", [
    ("valid", False), ("bid_cancel", np.nan), ("ask_priority_cancel", -1.0),
    ("bid_priority_cancel", 11.0), ("ask", 99.0), ("bid", np.inf),
])
def test_invalid_observation_flattens_and_restarts_warmup(column, value):
    f = features(9)
    f.loc[f.index[4], column] = value
    assert qs.signal(f, window=3).tolist() == [0, 0, 1, 1, 0, 0, 0, 1, 1]
    assert not qs.diagnostics(f, window=3).loc[f.index[4], "eligible"]


@pytest.mark.parametrize("column,value", [("session", "2026-09-02"), ("instrument_id", 2)])
def test_session_and_instrument_change_restart_warmup(column, value):
    f = features(8)
    f.loc[f.index[4]:, column] = value
    assert qs.signal(f, window=3).tolist() == [0, 0, 1, 1, 0, 0, 1, 1]


def test_activity_gate_is_shared_and_zero_cancels_never_trade():
    f = features(5)
    assert not qs.signal(f, window=2, min_cancel_qty=41).any()
    assert not qs.baseline(f, window=2, min_cancel_qty=41).any()
    f[["bid_cancel", "ask_cancel", "bid_priority_cancel", "ask_priority_cancel"]] = 0.0
    result = qs.signal(f, window=2, min_cancel_qty=0)
    assert not result.any()
    assert np.isfinite(result).all()
    assert result.index.equals(f.index)
    assert result.name == "target"


def test_completed_current_bar_can_decide_but_future_bar_is_not_required():
    f = features(3)
    assert qs.signal(f, window=3).iloc[-1] == 1
    f.loc[f.index[-1], "ask_priority_cancel"] = 0.0
    f.loc[f.index[-1], "bid_priority_cancel"] = 10.0
    assert qs.signal(f, window=3).iloc[-1] == 0


@pytest.mark.parametrize("params", [
    {"window": 0}, {"window": 1.5}, {"window": True}, {"threshold": 0},
    {"threshold": 1.1}, {"threshold": np.nan}, {"min_cancel_qty": -1},
])
def test_invalid_parameters_raise(params):
    with pytest.raises(ValueError):
        qs.signal(features(), **params)


def test_empty_input_and_invalid_schema():
    empty = qs.signal(features(0))
    assert empty.empty and empty.name == "target"
    f = features()
    with pytest.raises(ValueError, match="sorted and unique"):
        qs.signal(f.iloc[::-1])
    with pytest.raises(ValueError, match="sorted and unique"):
        qs.signal(pd.concat([f.iloc[:1], f.iloc[:1]]))
    with pytest.raises(ValueError, match="UTC"):
        qs.signal(f.tz_localize(None))
    with pytest.raises(ValueError, match="missing"):
        qs.signal(f.drop(columns="bid_priority_cancel"))
