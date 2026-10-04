"""Synthetic accounting and eligibility tests; none are market observations."""
from dataclasses import replace
import pytest
from cashflow import (Quote, Contract, Package, validate_package,
                      opening_credit, closing_debit, matched_close_trading_pnl,
                      accrued_loan_cashflow, net_pnl)


def package(t=1_000_000_000):
    return Package("TEST", Quote(99.99, 100.01, 500, 500, t),
                   Quote(2.00, 2.10, 5, 5, t), Quote(2.00, 2.10, 5, 5, t),
                   Contract("TEST", "call", 100, "2030-06-21"),
                   Contract("TEST", "put", 100, "2030-06-21"), 1)


def test_unchanged_midpoint_package_loses_all_six_half_spreads():
    p = package()
    q = package(2_000_000_000)
    result = matched_close_trading_pnl(p, q, 1_000_000_000, 2_000_000_000,
                                     lifecycle_events=[])
    assert result == pytest.approx(-22)


def test_correct_sign_when_synthetic_long_price_rises():
    p = package()
    q = package(2_000_000_000)
    q = replace(q, call=replace(q.call, bid=2.50, ask=2.60))
    result = matched_close_trading_pnl(p, q, 1_000_000_000, 2_000_000_000,
                                     lifecycle_events=[])
    assert result == pytest.approx(28)


@pytest.mark.parametrize("terminal_stock", [50, 100, 150])
def test_ideal_expiry_cash_identity_only(terminal_stock):
    # This payoff identity does not simulate early exercise / expiry assignment.
    call = max(terminal_stock-100, 0)
    put = max(100-terminal_stock, 0)
    assert call - put - terminal_stock == -100


def test_fee_and_net_rebate_conventions_agree():
    a = accrued_loan_cashflow(collateral_dollars=10200, accrual_days=3, day_basis=360,
                             convention="separate_fee", gross_fee_rate=.12,
                             proceeds_interest_rate=.04)
    b = accrued_loan_cashflow(collateral_dollars=10200, accrual_days=3, day_basis=360,
                             convention="net_rebate", net_rebate_rate=-.08)
    assert a == pytest.approx(-6.8)
    assert a == pytest.approx(b)


def test_no_double_subtraction_of_borrow_fee():
    with pytest.raises(ValueError, match="do not count twice"):
        accrued_loan_cashflow(collateral_dollars=10000, accrual_days=1, day_basis=360,
                             convention="net_rebate", net_rebate_rate=-.02,
                             gross_fee_rate=.03)


@pytest.mark.parametrize("time", [0, 2_000_000_001])
def test_no_stale_or_future_quote(time):
    p = package(2_000_000_000)
    with pytest.raises(ValueError, match="Future or stale"):
        validate_package(replace(p, put=replace(p.put, received_ns=time)),
                         2_000_000_000, "open")


def test_no_unsynchronized_quote():
    p = package()
    with pytest.raises(ValueError, match="Unsynchronized"):
        validate_package(replace(p, put=replace(p.put, received_ns=800_000_000)),
                         1_000_000_000, "open")


def test_required_side_size_and_stock_share_multiplier():
    p = package()
    with pytest.raises(ValueError, match="size"):
        validate_package(replace(p, stock=replace(p.stock, bid_size=99)),
                         1_000_000_000, "open")
    with pytest.raises(ValueError, match="size"):
        validate_package(replace(p, call=replace(p.call, ask_size=0)),
                         1_000_000_000, "open")


@pytest.mark.parametrize("change", [{"strike": 101}, {"expiry": "2030-07-19"},
                                   {"underlying": "OTHER"}, {"multiplier": 10}])
def test_mismatched_contracts_rejected(change):
    p = package()
    with pytest.raises(ValueError, match="Mismatched"):
        validate_package(replace(p, put_contract=replace(p.put_contract, **change)),
                         1_000_000_000, "open")


def test_assignment_requires_new_cash_ledger():
    with pytest.raises(ValueError, match="Lifecycle"):
        matched_close_trading_pnl(package(), package(2_000_000_000),
                                 1_000_000_000, 2_000_000_000,
                                 lifecycle_events=["put_assignment"])


def test_all_carry_and_costs_have_correct_sign():
    result = net_pnl(trading_pnl=28, net_loan_cashflow=-6.8,
                     other_incremental_cash_interest=1, funding_cost=2,
                     substitute_dividends=10, trading_fees=4, event_costs=3)
    assert result == pytest.approx(3.2)


def test_size_scales_cash_not_premium_denominator():
    p = package()
    assert opening_credit(replace(p, contracts=3)) == pytest.approx(3*opening_credit(p))
    assert closing_debit(replace(p, contracts=3)) == pytest.approx(3*closing_debit(p))


def test_nonfinite_quote_rejected():
    with pytest.raises(ValueError, match="finite"):
        Quote(float("nan"), 1, 1, 1, 0)


@pytest.mark.parametrize("time", [float("nan"), float("inf"), -1, 1.5])
def test_invalid_timestamps_cannot_bypass_availability_checks(time):
    with pytest.raises(ValueError, match="timestamp"):
        package(time)
    with pytest.raises(ValueError, match="timestamp"):
        validate_package(package(), time, "open")


def test_unknown_lifecycle_is_not_known_empty():
    with pytest.raises(ValueError, match="Lifecycle"):
        matched_close_trading_pnl(package(), package(2_000_000_000),
                                 1_000_000_000, 2_000_000_000,
                                 lifecycle_events=None)
