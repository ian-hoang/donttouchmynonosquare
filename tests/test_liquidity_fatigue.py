"""Crafted mechanism tests only; these are not financial performance evidence."""

import numpy as np
import pandas as pd
import pytest

from microstrategies import liquidity_fatigue as fatigue


PARAMS = {"lookback": 3, "recovery_bars": 2, "history_events": 2, "hold_bars": 3}


def episodes():
    index = pd.date_range("2026-09-01 13:30", periods=20, freq="s", tz="UTC")
    frame = pd.DataFrame(index=index)
    frame["mid"] = 100.0
    frame.loc[index[3]:, "mid"] = 100.2
    frame.loc[index[7]:, "mid"] = 100.6
    frame.loc[index[11]:, "mid"] = 101.4
    frame["bid"] = frame["mid"] - 0.05
    frame["ask"] = frame["mid"] + 0.05
    frame["bid_size"] = 100.0
    frame["ask_size"] = 100.0
    frame.loc[index[[3, 7, 11]], "ask_size"] = 40.0
    frame.loc[index[4], "ask_size"] = 95.0
    frame.loc[index[8], "ask_size"] = 60.0
    frame.loc[index[9], "ask_size"] = 70.0
    frame["trade_volume"] = 1.0
    frame["signed_volume"] = 0.0
    frame.loc[index[[3, 7, 11]], ["trade_volume", "signed_volume"]] = 10.0
    frame["buy_volume"] = (frame["trade_volume"] + frame["signed_volume"]) / 2
    frame["sell_volume"] = frame["trade_volume"] - frame["buy_volume"]
    for name in ("bid_add", "ask_add", "bid_cancel", "ask_cancel",
                 "bid_priority_cancel", "ask_priority_cancel"):
        frame[name] = 0.0
    frame["session"] = "2026-09-01"
    frame["instrument_id"] = 1
    frame["valid"] = True
    return frame


def test_completed_recovery_deterioration_triggers_only_next_burst():
    frame = episodes()
    diag = fatigue.diagnostics(frame, **PARAMS)
    assert diag["completed_events"].iloc[4] == 0
    assert diag["completed_events"].iloc[5] == 1
    assert diag["completed_events"].iloc[8] == 1
    assert diag["completed_events"].iloc[9] == 2
    assert diag["components"].iloc[11] == 3
    assert diag["refill_drop"].iloc[11] == pytest.approx(0.5)
    assert diag["recovery_delay"].iloc[11] == 2
    assert diag["impact_growth"].iloc[11] == pytest.approx(1)
    result = fatigue.signal(frame, **PARAMS)
    assert result.iloc[:11].eq(0).all()
    assert result.iloc[11:14].eq(1).all()
    assert result.iloc[14:].eq(0).all()
    assert fatigue.baseline(frame, **PARAMS).iloc[3] == 1
    assert result.name == "target"
    assert result.index.equals(frame.index)
    assert np.isfinite(result).all()
    assert set(result).issubset({-1, 0, 1})


def test_sell_side_is_symmetric():
    frame = episodes()
    frame["mid"] = 200 - frame["mid"]
    frame["bid"] = frame["mid"] - 0.05
    frame["ask"] = frame["mid"] + 0.05
    frame[["bid_size", "ask_size"]] = frame[["ask_size", "bid_size"]].to_numpy()
    frame["signed_volume"] *= -1
    result = fatigue.signal(frame, **PARAMS)
    assert result.iloc[11:14].eq(-1).all()
    assert result.iloc[:11].eq(0).all()


def test_exact_prefix_invariance_at_every_bar_including_open_episode():
    frame = episodes()
    full = fatigue.diagnostics(frame, **PARAMS)
    for end in range(len(frame) + 1):
        partial = fatigue.diagnostics(frame.iloc[:end], **PARAMS)
        pd.testing.assert_frame_equal(partial, full.iloc[:end])


@pytest.mark.parametrize("reset", ["invalid", "nan", "crossed", "session", "instrument"])
def test_boundaries_clear_completed_events_and_open_positions(reset):
    frame = episodes()
    t = frame.index[12]  # An active position would otherwise persist here.
    if reset == "invalid":
        frame.loc[t, "valid"] = False
    elif reset == "nan":
        frame.loc[t, "ask_size"] = np.nan
    elif reset == "crossed":
        frame.loc[t, "ask"] = frame.loc[t, "bid"]
    elif reset == "session":
        frame.loc[t:, "session"] = "2026-09-02"
    else:
        frame.loc[t:, "instrument_id"] = 2
    diag = fatigue.diagnostics(frame, **PARAMS)
    assert diag["target"].iloc[11] == 1
    assert diag["target"].iloc[12:].eq(0).all()
    assert diag["completed_events"].iloc[12:].eq(0).all()


def test_history_before_an_invalid_row_cannot_be_reused_after_rewarming():
    frame = episodes()
    frame.loc[frame.index[6], "valid"] = False
    assert fatigue.signal(frame, **PARAMS).eq(0).all()


def test_initial_warmup_excludes_bursts_with_insufficient_reference_history():
    # First burst occurs at row 3, before four preceding valid bars exist.
    result = fatigue.signal(episodes(), **{**PARAMS, "lookback": 4})
    assert result.eq(0).all()


def test_interrupted_or_incomplete_recovery_never_enters_history():
    frame = episodes().iloc[:13]
    # Bursts arrive every four bars; none completes a five-bar observation.
    diag = fatigue.diagnostics(frame, **{**PARAMS, "recovery_bars": 5})
    assert diag["completed_events"].eq(0).all()
    assert diag["target"].eq(0).all()


def test_improving_recovery_does_not_pass_even_with_larger_price_impact():
    frame = episodes()
    frame.loc[frame.index[[4, 5, 8, 9]], "ask_size"] = [60, 70, 95, 100]
    diag = fatigue.diagnostics(frame, **PARAMS)
    assert diag["components"].iloc[11] == 1
    assert diag["target"].eq(0).all()


def test_bursts_must_be_comparable_and_recent():
    frame = episodes()
    frame.loc[frame.index[11], ["trade_volume", "signed_volume"]] = 100
    assert fatigue.signal(frame, **PARAMS).eq(0).all()
    assert fatigue.signal(episodes(), **{**PARAMS, "event_max_age": 4}).eq(0).all()


@pytest.mark.parametrize("params", [{"hold_bars": 0}, {"lookback": 2.5},
                                    {"history_events": 1}, {"min_components": 4},
                                    {"refill_drop": -0.1}, {"unknown": 2}])
def test_rejects_invalid_parameters(params):
    with pytest.raises(ValueError):
        fatigue.signal(episodes(), **params)


def test_rejects_ambiguous_index_and_missing_features():
    frame = episodes()
    with pytest.raises(ValueError, match="Missing features"):
        fatigue.signal(frame.drop(columns="ask_size"))
    with pytest.raises(ValueError, match="sorted and unique"):
        fatigue.signal(frame.iloc[::-1])
    frame.index = frame.index.tz_localize(None)
    with pytest.raises(ValueError, match="UTC"):
        fatigue.signal(frame)
