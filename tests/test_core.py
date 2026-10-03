import numpy as np
import pandas as pd
import pytest

from gqh import analysis, risk
from gqh.checks import data_quality, lookahead_check
from gqh.data import futures_cost_bps, roll_safe_returns, session_daily, synthetic_prices
from gqh.engine import backtest
from gqh.metrics import to_daily
from gqh.split import oos_start


def test_oos_rule_two_year_cap_binds_on_long_history():
    idx = pd.bdate_range("2012-01-02", "2026-10-01")
    start = oos_start(idx)
    assert start == pd.Timestamp("2024-10-01")
    assert (idx < start).sum() > 0 and (idx >= start).sum() == pytest.approx(523, abs=5)


def test_oos_rule_twenty_percent_binds_on_short_history():
    idx = pd.bdate_range("2021-10-01", "2026-10-01")
    assert oos_start(idx) == idx.max() - (idx.max() - idx.min()) * 0.2


def test_engine_lags_weights_one_bar():
    prices = synthetic_prices(n_assets=2)
    r = prices.pct_change()
    peek = np.sign(r)  # "knows" today's return
    res = backtest(peek, r, cost_bps=0)
    pd.testing.assert_frame_equal(res.positions, peek.shift(1).fillna(0.0), check_freq=False)
    assert abs(res.net.mean() * 252) < 0.05  # no free money once lagged


def test_costs_charged_per_unit_traded():
    idx = pd.bdate_range("2024-01-01", periods=4)
    r = pd.DataFrame({"A": 0.0}, index=idx)
    w = pd.DataFrame({"A": [1.0, 1.0, -1.0, -1.0]}, index=idx)
    res = backtest(w, r, cost_bps=10)
    # position 0 -> 1 on day 2 (1 unit), 1 -> -1 on day 4 (2 units)
    assert res.turnover.tolist() == [0.0, 1.0, 0.0, 2.0]
    assert res.net.sum() == pytest.approx(-3 * 10 / 1e4)


class _Peeking:
    def weights(self, prices):
        return (prices - prices.mean()) / prices.std()  # full-sample normalization


class _Causal:
    def weights(self, prices):
        return (prices - prices.rolling(20).mean()) / prices.rolling(20).std()


def test_lookahead_check_catches_full_sample_normalization():
    prices = synthetic_prices(n_assets=2)
    assert not lookahead_check(_Peeking(), prices, {})["passed"]
    assert lookahead_check(_Causal(), prices, {})["passed"]


def test_capacity_matches_track_brief_dial():
    c = analysis.capacity(aum=10e6, names=100, adv_per_name=5.01e6, turnover=20, gross_sharpe=1.5,
                          strategy_vol=0.10, fixed_bps=15, daily_vol=0.035)
    assert c["cost_bps"] == pytest.approx(28.9, abs=0.05)
    assert c["yearly_drag"] == pytest.approx(0.0579, abs=0.0005)
    assert c["net_sharpe"] == pytest.approx(0.92, abs=0.01)
    assert c["half_edge_aum"] == pytest.approx(26.1e6, rel=0.01)
    assert c["capacity"] == pytest.approx(186e6, rel=0.01)


class _Overlaid:
    def __init__(self, overlay):
        self.overlay = overlay

    def weights(self, prices):
        r = prices.pct_change()
        return self.overlay(np.sign(np.log(prices).diff(20)), r)


@pytest.mark.parametrize("overlay", [
    lambda w, r: risk.vol_target(w, r, target=0.1),
    lambda w, r: risk.inverse_vol(w, r),
    lambda w, r: risk.cap_weights(w, 0.3),
    lambda w, r: risk.cap_gross(w, 1.0),
    lambda w, r: risk.drawdown_brake(w, r, max_dd=0.05),
])
def test_risk_overlays_are_lookahead_safe(overlay):
    assert lookahead_check(_Overlaid(overlay), synthetic_prices(n_assets=3), {})["passed"]


def test_cap_gross_limits_leverage():
    w = pd.DataFrame({"A": [2.0, 0.5], "B": [-2.0, 0.2]})
    capped = risk.cap_gross(w, 1.0)
    assert capped.abs().sum(axis=1).tolist() == pytest.approx([1.0, 0.7])


def test_session_daily_uses_the_4pm_close_not_after_hours():
    times = pd.to_datetime(["2026-09-30 09:29", "2026-09-30 09:30", "2026-09-30 15:59", "2026-09-30 16:30"]
                           ).tz_localize("America/New_York").tz_convert("UTC")
    bars = pd.DataFrame({"ts_event": times, "symbol": "SPY", "instrument_id": 1,
                         "open": [1.0, 2.0, 3.0, 4.0], "high": [1.0, 2.5, 3.5, 4.0],
                         "low": [1.0, 1.5, 2.5, 4.0], "close": [1.0, 2.2, 3.3, 9.9],
                         "volume": [10, 20, 30, 40]}).set_index("ts_event")
    day = session_daily(bars)
    row = day.iloc[0]
    assert (row["open"], row["close"], row["high"], row["volume"]) == (2.0, 3.3, 3.5, 50)
    assert day.index[0] == pd.Timestamp("2026-09-30 16:00", tz="America/New_York")


def test_intraday_results_are_compounded_to_daily():
    idx = pd.to_datetime(["2026-09-29 15:00", "2026-09-29 16:00", "2026-09-30 15:00"]).tz_localize("America/New_York")
    net = pd.Series([0.01, 0.02, -0.01], index=idx)
    daily_net, daily_turn = to_daily(net, pd.Series([1.0, 0.0, 2.0], index=idx))
    assert daily_net.tolist() == pytest.approx([1.01 * 1.02 - 1, -0.01])
    assert daily_turn.tolist() == [1.0, 2.0]


def test_futures_cost_bps_for_es():
    # half a tick + half a tick slippage = $12.50, plus $2.50 fees, on $325,000 notional
    assert futures_cost_bps(6500, 0.25, 50, fee_per_contract=2.5) == pytest.approx(15 / 325000 * 1e4)


def test_data_quality_flags_an_unadjusted_split():
    r = synthetic_prices(n_assets=1).pct_change()
    r.iloc[100, 0] = -0.5  # a 2-for-1 split in unadjusted data
    assert data_quality(r).attrs["flags"]


def test_sweep_builds_every_combination():
    from run import build_grid
    assert build_grid(["a=1,2", "b=x,y"]) == [{"a": 1, "b": "x"}, {"a": 1, "b": "y"},
                                              {"a": 2, "b": "x"}, {"a": 2, "b": "y"}]


def test_roll_safe_returns_bridge_the_roll():
    ts = pd.to_datetime(["2024-03-13", "2024-03-14", "2024-03-15"], utc=True)
    # Old contract (id 1) trades at 100 then 101; new contract (id 2) is c.1 then becomes c.0 on the 15th.
    bars = pd.DataFrame({
        "ts_event": list(ts) * 2,
        "symbol": ["ES.c.0"] * 3 + ["ES.c.1"] * 3,
        "instrument_id": [1, 1, 2, 2, 2, 3],
        "close": [100.0, 101.0, 112.2, 110.0, 111.0, 120.0],
    }).set_index("ts_event")
    r = roll_safe_returns(bars)
    assert r["ES.c.0"].iloc[1] == pytest.approx(0.01)
    assert r["ES.c.0"].iloc[2] == pytest.approx(112.2 / 111.0 - 1)  # new contract vs its own prior close
