"""Auditable reversal cash accounting; not a strategy backtest or fill simulator.

Rates are decimals; premiums are dollars per share; option sizes are contracts.
Quotes use receive timestamps in integer nanoseconds. Actual assignments, exercises,
recalls, dividends, funding and failed executions need separate historical records.
This intentionally refuses to value a three-leg close after a lifecycle event.
"""
from dataclasses import dataclass
from math import isfinite
from numbers import Integral


def finite(*values):
    if not all(isfinite(x) for x in values):
        raise ValueError("Inputs must be finite")


def nonnegative_integer(value, name):
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


@dataclass(frozen=True)
class Quote:
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    received_ns: int

    def __post_init__(self):
        finite(self.bid, self.ask)
        nonnegative_integer(self.received_ns, "received timestamp")
        nonnegative_integer(self.bid_size, "bid size")
        nonnegative_integer(self.ask_size, "ask size")
        if self.bid < 0 or self.ask < self.bid:
            raise ValueError("Negative or crossed quote")
        if min(self.bid_size, self.ask_size) < 0:
            raise ValueError("Negative size")


@dataclass(frozen=True)
class Contract:
    underlying: str
    kind: str
    strike: float
    expiry: str
    multiplier: int = 100
    style: str = "american"
    standard_deliverable: bool = True


@dataclass(frozen=True)
class Package:
    underlying: str
    stock: Quote
    call: Quote
    put: Quote
    call_contract: Contract
    put_contract: Contract
    contracts: int

    @property
    def shares(self):
        return self.contracts * self.call_contract.multiplier


def validate_package(p, decision_ns, side, max_age_ns=1_000_000_000,
                     max_skew_ns=100_000_000):
    """Top-of-book eligibility only. Does not assert a package can be filled."""
    nonnegative_integer(decision_ns, "decision timestamp")
    nonnegative_integer(max_age_ns, "maximum quote age")
    nonnegative_integer(max_skew_ns, "maximum timestamp skew")
    c, q = p.call_contract, p.put_contract
    nonnegative_integer(p.contracts, "contract quantity")
    if p.contracts <= 0:
        raise ValueError("Positive integer contract quantity required")
    if c.kind != "call" or q.kind != "put":
        raise ValueError("Incorrect option sides")
    if (c.underlying, c.strike, c.expiry, c.multiplier, c.style) != (
        q.underlying, q.strike, q.expiry, q.multiplier, q.style
    ) or c.underlying != p.underlying:
        raise ValueError("Mismatched option pair / stock")
    if not c.standard_deliverable or not q.standard_deliverable or c.multiplier != 100:
        raise ValueError("Pilot accepts standard 100-share contracts only")
    finite(c.strike)
    if c.strike <= 0 or c.style not in ("american", "european"):
        raise ValueError("Invalid contract metadata")
    times = [p.stock.received_ns, p.call.received_ns, p.put.received_ns]
    if any(t > decision_ns or decision_ns - t > max_age_ns for t in times):
        raise ValueError("Future or stale received quote")
    if max(times) - min(times) > max_skew_ns:
        raise ValueError("Unsynchronized quote legs")
    if side == "open":
        available = (p.stock.bid_size >= p.shares and
                     p.call.ask_size >= p.contracts and p.put.bid_size >= p.contracts)
    elif side == "close":
        available = (p.stock.ask_size >= p.shares and
                     p.call.bid_size >= p.contracts and p.put.ask_size >= p.contracts)
    else:
        raise ValueError("side must be open or close")
    if not available:
        raise ValueError("Insufficient displayed size")


def opening_credit(p):
    return p.shares * (p.stock.bid + p.put.bid - p.call.ask)


def closing_debit(p):
    return p.shares * (p.stock.ask + p.put.ask - p.call.bid)


def matched_close_trading_pnl(entry, exit, entry_decision_ns, exit_decision_ns,
                             *, lifecycle_events):
    """Both timestamps must be historically available; cash carry is separate.

    Empty lifecycle_events must be established from data, not assumed. Assignment,
    buy-in, exercise or a deliverable change requires an event-specific cash ledger.
    """
    if not isinstance(lifecycle_events, (list, tuple)) or lifecycle_events:
        raise ValueError("Lifecycle event requires an event-specific cash ledger")
    nonnegative_integer(entry_decision_ns, "entry timestamp")
    nonnegative_integer(exit_decision_ns, "exit timestamp")
    if exit_decision_ns <= entry_decision_ns:
        raise ValueError("Exit must follow entry")
    if (entry.call_contract, entry.put_contract, entry.contracts) != (
        exit.call_contract, exit.put_contract, exit.contracts
    ):
        raise ValueError("Exit does not close the original package")
    validate_package(entry, entry_decision_ns, "open")
    validate_package(exit, exit_decision_ns, "close")
    return opening_credit(entry) - closing_debit(exit)


def accrued_loan_cashflow(*, collateral_dollars, accrual_days, day_basis,
                         convention, gross_fee_rate=None, proceeds_interest_rate=None,
                         net_rebate_rate=None):
    """One constant-base accrual interval using the actual contract's convention.

    Split intervals whenever base/rate/settled quantity changes. For this helper,
    both component rates must apply to the given common base; otherwise book actual
    separate dollar amounts via net_pnl. Interest tiers need their own intervals.
    """
    finite(collateral_dollars, accrual_days, day_basis)
    if collateral_dollars < 0 or accrual_days < 0 or day_basis not in (360, 365, 366):
        raise ValueError("Invalid accrual base")
    if convention == "separate_fee":
        if gross_fee_rate is None or proceeds_interest_rate is None or net_rebate_rate is not None:
            raise ValueError("Provide fee and proceeds interest only")
        finite(gross_fee_rate, proceeds_interest_rate)
        rate = proceeds_interest_rate - gross_fee_rate
    elif convention == "net_rebate":
        if net_rebate_rate is None or gross_fee_rate is not None or proceeds_interest_rate is not None:
            raise ValueError("Net rebate already includes lending fee: do not count twice")
        finite(net_rebate_rate)
        rate = net_rebate_rate
    else:
        raise ValueError("Unknown cash-flow convention")
    return collateral_dollars * rate * accrual_days / day_basis


def net_pnl(*, trading_pnl, net_loan_cashflow, other_incremental_cash_interest,
            funding_cost, substitute_dividends, trading_fees, event_costs):
    """All arguments are dollar cash flows. Positive cost arguments reduce P&L.

    net_loan_cashflow includes proceeds credit less borrow fees exactly once.
    other_incremental_cash_interest excludes that same proceeds credit. Collateral
    transfers are not expenses. Funding here excludes interest already in either
    interest argument. Event-specific trading cash must be in trading_pnl.
    """
    finite(trading_pnl, net_loan_cashflow, other_incremental_cash_interest,
           funding_cost, substitute_dividends, trading_fees, event_costs)
    if min(funding_cost, substitute_dividends, trading_fees, event_costs) < 0:
        raise ValueError("Costs must be nonnegative")
    return (trading_pnl + net_loan_cashflow + other_incremental_cash_interest -
            funding_cost - substitute_dividends - trading_fees - event_costs)
