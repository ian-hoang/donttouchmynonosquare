import numpy as np
import pandas as pd
import pytest

from microstrategies import missing_beat as mb


def features(n=34, *, direction=1, starts=(3, 9, 15)):
    index = pd.date_range("2026-09-01 14:00", periods=n, freq="s", tz="UTC")
    flow = np.zeros(n)
    price = np.full(n, 100.0)
    for start in starts:
        flow[start:start + 2] = 20 * direction
        price[start:] += 0.5 * direction
        price[start + 1:] += 0.5 * direction
    return pd.DataFrame({"mid": price, "buy_volume": np.maximum(flow, 0), "sell_volume": np.maximum(-flow, 0),
                         "trade_volume": abs(flow), "signed_volume": flow, "valid": True,
                         "session": "2026-09-01", "instrument_id": 123}, index=index)


@pytest.mark.parametrize("direction", [1, -1])
def test_repeated_flow_missing_after_full_deadline(direction):
    data = features(direction=direction)
    result = mb.signal(data)
    assert result.name == "target"
    assert result.index.equals(data.index)
    assert set(result.unique()) <= {-1.0, 0.0, 1.0}
    # Burst windows: 3:4, 9:10, 15:16. Missing window: 21:22.
    assert result.iloc[:22].eq(0).all()
    assert result.iloc[22:25].eq(-direction).all()
    assert result.iloc[25:].eq(0).all()
    diag = mb.diagnostics(data)
    assert not diag["observation_complete"].iloc[21]
    assert diag["observation_complete"].iloc[22]
    assert diag["missing_beat"].sum() == 1


def test_late_on_schedule_burst_is_observed_before_claiming_absence():
    data = features(n=25)
    # The fourth burst arrives in the last allowed bar, with a comparable total.
    for col in ("signed_volume", "buy_volume", "trade_volume"):
        data.iloc[22, data.columns.get_loc(col)] = 40
    assert mb.signal(data).eq(0).all()


def test_ordinary_flow_drop_is_not_enough_for_cadence_signal():
    data = features(starts=(3,))
    assert mb.signal(data).eq(0).all()
    ordinary = mb.baseline(data)
    assert ordinary.iloc[:6].eq(0).all()
    assert ordinary.iloc[6] == -1


def test_unexpected_extra_burst_falsifies_schedule():
    data = features(starts=(3, 6, 9, 15))
    assert mb.signal(data).eq(0).all()


def test_wrong_sign_repetition_does_not_establish_a_cadence():
    data = features()
    for i in (9, 10):
        data.iloc[i, data.columns.get_loc("signed_volume")] = -20
        data.iloc[i, data.columns.get_loc("buy_volume")] = 0
        data.iloc[i, data.columns.get_loc("sell_volume")] = 20
    assert mb.signal(data).eq(0).all()


def test_equal_buy_and_sell_volume_is_not_missing_expected_buying():
    data = features()
    data.loc[data.index[21:23], ["buy_volume", "sell_volume"]] = 20
    data.loc[data.index[21:23], "trade_volume"] = 40
    assert mb.signal(data).eq(0).all()


def test_requires_retained_displacement():
    data = features()
    data.loc[data.index[21:], "mid"] = 100
    assert mb.signal(data).eq(0).all()


@pytest.mark.parametrize("reset", ["invalid", "nan", "session", "instrument"])
def test_resets_during_cadence_warmup(reset):
    data = features()
    if reset == "invalid":
        data.iloc[12, data.columns.get_loc("valid")] = False
    elif reset == "nan":
        data.iloc[12, data.columns.get_loc("mid")] = np.nan
    elif reset == "session":
        data.loc[data.index[12:], "session"] = "2026-09-02"
    else:
        data.loc[data.index[12:], "instrument_id"] = 456
    assert mb.signal(data).eq(0).all()


def test_invalid_quote_clears_active_target():
    data = features()
    data.iloc[23, data.columns.get_loc("valid")] = False
    result = mb.signal(data)
    assert result.iloc[22] == -1
    assert result.iloc[23:].eq(0).all()


@pytest.mark.parametrize("fn", [mb.signal, mb.baseline])
def test_exact_prefix_invariance_including_short_warmup(fn):
    data = features(starts=(3, 9, 15, 28))
    complete = fn(data)
    for stop in range(len(data) + 1):
        pd.testing.assert_series_equal(fn(data.iloc[:stop]), complete.iloc[:stop])


def test_future_mutation_cannot_change_past_signal():
    data = features()
    prefix = mb.signal(data).iloc[:23]
    data.loc[data.index[23:], "mid"] = 500
    data.loc[data.index[23:], "signed_volume"] = 10000
    pd.testing.assert_series_equal(mb.signal(data).iloc[:23], prefix)


@pytest.mark.parametrize("params", [{"window_bars": 0}, {"cadence_bars": 2}, {"cycles": 1},
                                  {"hold_bars": 1.5}, {"tick_size": 0}, {"missing_fraction": 1},
                                  {"retention_fraction": np.nan}, {"typo": 1}])
def test_invalid_parameters_rejected(params):
    with pytest.raises(ValueError):
        mb.signal(features(), **params)
