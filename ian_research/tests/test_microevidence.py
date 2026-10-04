import json

import numpy as np
import pandas as pd
import pytest

from gqh.microevidence import _bootstrap, evidence


def make_curve(daily_pnl):
    times, values, positions = [], [], []
    cumulative = 0.0
    for date, pnl in zip(pd.bdate_range("2026-01-05", periods=len(daily_pnl), tz="UTC"), daily_pnl):
        times.extend(date + pd.to_timedelta([14, 15, 16], unit="h"))
        values.extend([cumulative, cumulative, cumulative + pnl])
        positions.extend([0, 1, 0])
        cumulative += pnl
    index = pd.DatetimeIndex(times) if times else pd.DatetimeIndex([], tz="UTC")
    return pd.DataFrame({"pnl": values, "equity": np.asarray(values) + 100_000,
                         "position": positions, "valid": True}, index=index)


def test_daily_pnl_uses_cumulative_differences_including_initial_row_cost():
    curve = make_curve([10, -5, 0, 15])
    curve.loc[curve.index[0], ["pnl", "equity"]] = [-2, 99_998]
    result = evidence(curve, pd.DataFrame())
    assert [x["net_pnl"] for x in result["daily"]] == [10, -5, 0, 15]
    assert result["strategy"]["total_pnl"] == 20
    assert result["strategy"]["mean_daily_pnl"] == 5
    assert result["sessions"] == 4
    assert result["strategy"]["mean_daily_pnl_interval"] is None


def test_paired_block_interval_preserves_common_daily_shocks():
    pnl = np.linspace(-20, 30, 25)
    result = evidence(make_curve(pnl), pd.DataFrame(), make_curve(pnl - 3), repetitions=500)
    interval = result["difference_vs_baseline"]["mean_daily_pnl_interval"]
    assert result["difference_vs_baseline"]["mean_daily_pnl"] == pytest.approx(3)
    assert interval["lower"] == pytest.approx(3)
    assert interval["upper"] == pytest.approx(3)
    assert result["strategy"]["mean_daily_pnl_interval"]["lower"] < 5
    assert result["strategy"]["mean_daily_pnl_interval"]["upper"] > 5
    assert result["bootstrap"]["paired_baseline"]


def test_bootstrap_draws_whole_contiguous_session_blocks():
    values = np.arange(10, dtype=float)[:, None]
    # A circular block of length N contains each day exactly once. An iid
    # bar/day bootstrap would incorrectly have a nonzero variance here.
    samples = _bootstrap(values, seed=42, repetitions=100, block_length=10)
    np.testing.assert_array_equal(samples[:, 0], np.full(100, 4.5))


def test_reproducibility_and_strict_json_serialization():
    curve = make_curve([10, -3, 4, -20, 8] * 6)
    kwargs = {"seed": 99, "repetitions": 200}
    first = evidence(curve, pd.DataFrame(), **kwargs)
    assert first == evidence(curve, pd.DataFrame(), **kwargs)
    json.dumps(first, allow_nan=False)
    assert "sharpe" not in json.dumps(first).lower()


@pytest.mark.parametrize("count, block", [(0, 5), (1, 5), (19, 5), (20, 11)])
def test_short_samples_withhold_intervals(count, block):
    result = evidence(make_curve([1] * count), pd.DataFrame(), block_length=block)
    assert result["interval_status"] == "insufficient_sessions"
    assert result["strategy"]["mean_daily_pnl_interval"] is None
    assert result["bootstrap"]["repetitions"] == 0
    json.dumps(result, allow_nan=False)


def test_twenty_sessions_enable_exploratory_interval_but_not_alpha_claim():
    result = evidence(make_curve([1] * 20), pd.DataFrame(), repetitions=200)
    assert result["interval_status"] == "exploratory"
    assert result["strategy"]["mean_daily_pnl_interval"]["lower"] == 1
    assert any("no variation" in warning for warning in result["warnings"])
    assert any("not proof of alpha" in warning for warning in result["warnings"])


def test_flat_to_flat_episode_costs_reversals_and_open_episode():
    curve = make_curve([0, 0, 0]).iloc[:7].copy()
    curve["position"] = [0, 1, -1, 0, 1, 0, 1]
    curve["pnl"] = [0, -2, 3, 8, 6, 5, 4]
    curve["equity"] = 100_000 + curve["pnl"]
    episodes = evidence(curve, pd.DataFrame())["episodes"]
    assert episodes["closed_count"] == 2
    assert episodes["closed_net_pnl"] == 5
    assert episodes["mean_net_pnl"] == 2.5
    assert episodes["hit_ratio"] == 0.5
    assert episodes["direct_reversals"] == 1
    assert episodes["open_episode"]


def test_fill_cost_addback_is_labeled_and_aggregated_by_day():
    curve = make_curve([-5, 10])
    fills = pd.DataFrame({
        "time": curve.index[[1, 2, 4, 5]], "quantity": [1, -1, 1, -1],
        "fee": [2.5] * 4, "extra_cost": [12.5] * 4,
        "reason": ["signal", "scheduled_close", "signal", "scheduled_close"],
    })
    result = evidence(curve, fills)
    assert result["fills"]["count"] == 4
    assert result["fills"]["contracts_traded"] == 4
    assert result["fills"]["fees"] == 10
    assert result["fills"]["extra_costs"] == 50
    assert [x["pnl_before_explicit_costs"] for x in result["daily"]] == [25, 40]
    assert result["execution_pnl_before_explicit_costs"]["total_pnl"] == 65
    assert "spread remains embedded" in result["execution_pnl_before_explicit_costs"]["definition"]
    assert not result["raw_mid_markout"]["available"]


def test_unmatched_baseline_cannot_silently_compare_different_days():
    curve = make_curve([1, 2])
    baseline = curve.copy()
    baseline.index += pd.Timedelta(days=1)
    with pytest.raises(ValueError, match="same timestamps"):
        evidence(curve, pd.DataFrame(), baseline)


def test_rejects_inconsistent_or_invalid_curves_and_fills():
    curve = make_curve([1, 2])
    broken = curve.copy()
    broken.loc[broken.index[1], "equity"] += 2
    with pytest.raises(ValueError, match="initial capital"):
        evidence(broken, pd.DataFrame())
    broken = curve.copy()
    broken.loc[broken.index[1], "pnl"] = np.nan
    with pytest.raises(ValueError, match="finite"):
        evidence(broken, pd.DataFrame())
    fills = pd.DataFrame({"time": [curve.index[-1] + pd.Timedelta(days=1)],
                          "quantity": [1], "fee": [1], "extra_cost": [1]})
    with pytest.raises(ValueError, match="curve timestamp"):
        evidence(curve, fills)


@pytest.mark.parametrize("kwargs", [{"repetitions": 0}, {"block_length": 0},
                                    {"confidence": 1}, {"block_length": 2.5}])
def test_rejects_invalid_bootstrap_configuration(kwargs):
    with pytest.raises(ValueError):
        evidence(make_curve([1] * 20), pd.DataFrame(), **kwargs)
