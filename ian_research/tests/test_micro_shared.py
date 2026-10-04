"""Execution economics, replay ordering, research freeze, and CLI integration."""
import json

import numpy as np
import pandas as pd
import pytest

from gqh.microdata import Book, LAST, SNAPSHOT, mbo_features
from gqh.microengine import Execution, check_causality, simulate
from run_micro import lock_final, main, parameters


def quotes(prices=(100, 100, 100, 100, 100)):
    idx = pd.date_range("2026-09-01T14:00:00Z", periods=len(prices), freq="1s")
    bid = np.array(prices, dtype=float)
    return pd.DataFrame(dict(bid=bid, ask=bid + .25, mid=bid + .125,
                             bid_size=10., ask_size=10., valid=True,
                             instrument_id=1, session="2026-09-01"), index=idx)


def events(rows):
    start = [(0, "R", "N", np.nan, 0, 0, SNAPSHOT),
             (0, "A", "B", 100, 10, 1, SNAPSHOT),
             (0, "A", "A", 100.25, 10, 2, SNAPSHOT | LAST)]
    frame = pd.DataFrame(start + rows, columns=["seconds", "action", "side", "price", "size", "order_id", "flags"])
    frame.index = pd.Timestamp("2026-09-01T00:00:00Z") + pd.to_timedelta(frame.pop("seconds"), unit="s")
    frame["instrument_id"] = 1
    return frame


def test_next_quote_fill_does_not_earn_gap_before_entry():
    frame = quotes([100, 110, 110, 110])
    result = simulate(frame, pd.Series([1, 1, 0, 0], index=frame.index),
                      Execution(slippage_ticks=0, fee_per_side=0, latency_ms=0))
    assert result.fills.iloc[0].time == frame.index[1]
    assert result.fills.iloc[0].price == 110.25
    assert result.summary["net_pnl"] == pytest.approx(-.25 * 50)


def test_round_trip_charges_spread_fees_slippage_and_doubles_all_costs():
    frame = quotes()
    target = pd.Series([1, 1, 0, 0, 0], index=frame.index)
    config = Execution(slippage_ticks=1, fee_per_side=2.5)
    base = simulate(frame, target, config)
    stress = simulate(frame, target, config, cost_mult=2)
    assert base.summary["net_pnl"] == pytest.approx(-12.5 - 25 - 5)
    assert stress.summary["net_pnl"] == pytest.approx(base.summary["net_pnl"] * 2)


def test_reversal_charges_two_contract_sides():
    frame = quotes()
    result = simulate(frame, pd.Series([1, -1, -1, 0, 0], index=frame.index), Execution())
    assert result.fills.quantity.tolist() == [1, -2, 1]
    assert result.fills.fee.sum() == 4 * 2.5


def test_latency_rounds_up_to_next_grid_and_end_is_flat():
    frame = quotes([100] * 8)
    result = simulate(frame, pd.Series(1, index=frame.index), Execution(latency_ms=2500))
    assert result.fills.iloc[0].time == frame.index[3]
    assert result.curve.position.iloc[-1] == 0
    assert result.fills.iloc[-1].reason == "scheduled_close"


def test_cannot_fabricate_terminal_exit_or_fill_with_insufficient_depth():
    frame = quotes()
    target = pd.Series(1, index=frame.index)
    frame.iloc[-1, frame.columns.get_loc("valid")] = False
    with pytest.raises(ValueError, match="liquidate"):
        simulate(frame, target)
    frame["valid"] = True
    frame["ask_size"] = .5
    assert simulate(frame, target).fills.empty


def test_loss_and_holding_limits_exit_and_block_repeat_entry():
    frame = quotes([100] * 10)
    config = Execution(max_hold_seconds=2, fee_per_side=0, slippage_ticks=0)
    result = simulate(frame, pd.Series(1, index=frame.index), config)
    assert result.fills.reason.tolist() == ["signal", "time_limit"]
    config = Execution(daily_loss_dollars=1, fee_per_side=0, slippage_ticks=0)
    result = simulate(frame, pd.Series(1, index=frame.index), config)
    assert result.fills.reason.tolist() == ["signal", "daily_loss"]


def test_prefix_check_rejects_future_shift_even_when_strategy_drops_row():
    frame = quotes([100, 101, 100, 101, 100, 101, 100, 101])
    with pytest.raises(ValueError, match="EXACT"):
        check_causality(lambda x: np.sign(x.mid.diff().shift(-1)).dropna(), frame)
    with pytest.raises(ValueError, match="future"):
        check_causality(lambda x: np.sign(x.mid.diff().shift(-1)).fillna(0), frame)


def test_priority_cancel_is_quantity_ahead_and_size_increase_loses_priority():
    book = Book()
    book.apply("A", "B", 100, 10, 1)
    book.apply("A", "B", 100, 10, 2)
    assert book.apply("C", "B", 100, 2, 2)["bid_priority_cancel"] == pytest.approx(2 / 11)
    book.apply("M", "B", 100, 11, 1)
    assert book.apply("C", "B", 100, 2, 2)["bid_priority_cancel"] == 2


def test_nondisplayed_fill_never_creates_an_order_but_unknown_cancel_fails():
    book = Book()
    flow = book.apply("F", "A", 100, 1, 123)
    assert flow["unattributed_fill_volume"] == 1
    assert not book.orders
    frame = events([(1.1, "C", "B", 100, 1, 999, LAST),
                    (2.1, "N", "N", np.nan, 0, 0, LAST)])
    with pytest.raises(ValueError, match="unknown"):
        mbo_features(frame)


def test_transient_trade_fill_pair_is_logged_without_phantom_order_or_double_volume():
    frame = events([(1.1, "T", "A", 100, 1, 123, 0),
                    (1.1, "F", "B", 100, 1, 1, 0),
                    (1.1, "T", "B", 100, 1, 456, 0),
                    (1.1, "F", "A", 100, 1, 123, 0),
                    (1.1, "C", "B", 100, 1, 1, LAST),
                    (2.1, "N", "N", np.nan, 0, 0, LAST),
                    (3.1, "N", "N", np.nan, 0, 0, LAST)])
    features = mbo_features(frame)
    assert features.trade_volume.iloc[1] == 2
    assert features.signed_volume.iloc[1] == 0
    assert features.unattributed_fill_volume.iloc[1] == 1
    assert not features.valid.iloc[1]
    assert features.valid.iloc[2]
    assert features.ask.iloc[2] == 100.25
    assert features.bid_size.iloc[2] == 9
    assert features.bid_cancel.sum() == 0


def test_unseen_fill_does_not_suppress_later_visible_cancel_for_reused_id():
    book = Book()
    book.apply("F", "A", 100.25, 5, 123)
    book.apply("A", "A", 100.25, 5, 123)
    assert book.apply("C", "A", 100.25, 5, 123)["ask_cancel"] == 5


def test_reset_discards_flows_and_invalidates_whole_reset_bar():
    frame = events([(1.1, "T", "B", 100.25, 5, 0, LAST),
                    (1.2, "R", "N", np.nan, 0, 0, 0),
                    (1.3, "A", "B", 200, 10, 3, 0),
                    (1.3, "A", "A", 200.25, 10, 4, LAST),
                    (2.1, "N", "N", np.nan, 0, 0, LAST)])
    features = mbo_features(frame)
    assert not features.valid.iloc[1]
    assert features.trade_volume.iloc[1] == 0


def test_receive_clock_bar_edges_and_unknown_side_volume_are_causal():
    frame = events([(1.0, "T", "N", 100.25, 5, 0, LAST),
                    (1.2, "T", "B", 100.25, 3, 0, LAST),
                    (2.1, "T", "A", 100, 99, 0, LAST),
                    (3.1, "N", "N", np.nan, 0, 0, LAST)])
    full = mbo_features(frame)
    part = mbo_features(frame.iloc[:-1])
    pd.testing.assert_frame_equal(full.iloc[:len(part)], part)
    assert full.trade_volume.tolist() == [0, 8, 99]
    assert full.signed_volume.tolist() == [0, 3, -99]


def test_final_lock_covers_any_manifest_change(tmp_path):
    path = tmp_path / "lock.json"
    base = {"source": "abc", "data": "def", "costs": 1}
    lock_final(path, base)
    lock_final(path, base)
    for key in base:
        with pytest.raises(ValueError, match="OOS already locked"):
            lock_final(path, {**base, key: "changed"})
    assert json.loads(path.read_text()) == base


def test_parameter_overrides_are_explicit_and_validate_names():
    assert parameters(["queue_sacrifice"], ["queue_sacrifice.window=20"])["queue_sacrifice"]["window"] == 20
    with pytest.raises(ValueError, match="Unknown"):
        parameters(["queue_sacrifice"], ["queue_sacrifice.widow=20"])


def test_market_cli_requires_contract_specs_before_accessing_data(capsys):
    with pytest.raises(SystemExit):
        main(["all", "--dbn", "does-not-exist.dbn"])
    assert "explicit --tick-size" in capsys.readouterr().err


def test_demo_cannot_unlock_holdout(capsys):
    with pytest.raises(SystemExit):
        main(["all", "--demo", "--final"])
    assert "cannot be final" in capsys.readouterr().err
