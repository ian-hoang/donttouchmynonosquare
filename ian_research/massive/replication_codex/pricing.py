"""Independent implementation of the frozen replication specification, steps 3–14.

Only raw responses cached by ``data`` are persisted.  This module deliberately
keeps the calendar-day lookup for the initial spot estimate separate from the
three-session freshness rule used by all later contract marks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from math import exp, isfinite
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from . import trading_calendar as sessions


NEW_YORK = ZoneInfo("America/New_York")
RATE = 0.04


@dataclass(frozen=True)
class BarMark:
    close: float
    day: date


def bar_date(bar: dict[str, Any]) -> date:
    """The API's daily bar timestamp is milliseconds since the UTC epoch."""
    return datetime.fromtimestamp(float(bar["t"]) / 1000, timezone.utc).astimezone(NEW_YORK).date()


def normalize_bars(bars: Iterable[dict[str, Any]]) -> list[BarMark]:
    result = []
    for bar in bars:
        if bar.get("c") is None:
            continue
        close = float(bar["c"])
        if isfinite(close):
            result.append(BarMark(close, bar_date(bar)))
    return sorted(result, key=lambda item: item.day)


def mark(bars: Iterable[BarMark], day: date) -> BarMark | None:
    """Last close on/before day, provided <=3 sessions follow the bar date."""
    eligible = [bar for bar in bars if bar.day <= day]
    if not eligible:
        return None
    latest = max(eligible, key=lambda item: item.day)
    age = sessions.sessions_between(latest.day, day)
    return latest if age <= 3 else None


def _nearest(strikes: Iterable[float], target: float) -> float:
    # Frozen spec does not specify ties: use the lower strike deterministically.
    return min(strikes, key=lambda strike: (abs(strike - target), strike))


def _chain_by_expiry(contracts: Iterable[dict[str, Any]]) -> dict[date, dict[str, dict[float, str]]]:
    by_expiry: dict[date, dict[str, dict[float, str]]] = {}
    for contract in contracts:
        if contract.get("shares_per_contract", 100) != 100:
            continue
        kind = contract.get("contract_type")
        if kind not in ("call", "put"):
            continue
        expiration = date.fromisoformat(contract["expiration_date"])
        strike = float(contract["strike_price"])
        sides = by_expiry.setdefault(expiration, {"call": {}, "put": {}})
        sides[kind][strike] = contract["ticker"]
    return by_expiry


def _pairs(sides: dict[str, dict[float, str]]) -> list[float]:
    return sorted(sides["call"].keys() & sides["put"].keys())


def estimate_spot(
    by_expiry: dict[date, dict[str, dict[float, str]]], t_pre: date, client: Any
) -> dict[str, Any]:
    """Step 6: at most eight parity attempts, with a seven-day bar lookup.

    The interval is [t_pre - 7 calendar days, t_pre], inclusive.  This is
    intentionally NOT ``mark``: initial spot bars have no session-age filter.
    The nearest expiry is fixed before checking its number of paired strikes.
    """
    expirations = sorted(expiry for expiry in by_expiry if (expiry - t_pre).days >= 3)
    if not expirations:
        return {"spot": None, "drop_reason": "no_near_expiry", "attempts": []}
    expiry = expirations[0]
    sides = by_expiry[expiry]
    paired = _pairs(sides)
    base = {"spot_expiry": expiry.isoformat(), "attempts": []}
    if len(paired) < 3:
        return {**base, "spot": None, "drop_reason": "near_expiry_fewer_than_3_pairs"}
    count = len(paired)
    median = paired[count // 2] if count % 2 else (paired[count // 2 - 1] + paired[count // 2]) / 2
    strike = _nearest(paired, median)
    tried: set[float] = set()
    last_estimate = None
    start = t_pre - timedelta(days=7)
    discount = exp(-RATE * (expiry - t_pre).days / 365)
    for _ in range(8):
        tried.add(strike)
        closes: dict[str, BarMark | None] = {}
        for kind in ("call", "put"):
            bars = normalize_bars(client.bars(sides[kind][strike], start, t_pre))
            eligible = [bar for bar in bars if start <= bar.day <= t_pre]
            closes[kind] = max(eligible, key=lambda bar: bar.day) if eligible else None
        call, put = closes["call"], closes["put"]
        attempt = {
            "strike": strike,
            "call_mark": call.close if call else None,
            "call_mark_date": call.day.isoformat() if call else None,
            "put_mark": put.close if put else None,
            "put_mark_date": put.day.isoformat() if put else None,
        }
        base["attempts"].append(attempt)
        if call is None or put is None:
            untried = [candidate for candidate in paired if candidate not in tried]
            if not untried:
                break
            strike = _nearest(untried, strike)
            continue
        last_estimate = strike * discount + call.close - put.close
        attempt["estimate"] = last_estimate
        next_strike = _nearest(paired, last_estimate)
        if next_strike == strike or next_strike in tried:
            break
        strike = next_strike
    return {**base, "spot": last_estimate,
            "drop_reason": None if last_estimate is not None else "missing_initial_parity_marks"}


def select_expiry_and_strikes(
    by_expiry: dict[date, dict[str, dict[float, str]]], t_pre: date, spot: float
) -> dict[str, Any]:
    candidates = [expiry for expiry, sides in by_expiry.items()
                  if 90 <= (expiry - t_pre).days <= 180 and len(_pairs(sides)) >= 3]
    if not candidates:
        return {"drop_reason": "no_90_180_day_expiry_with_3_pairs"}
    # Earlier expiry resolves a tie around the 120-day target.
    expiry = min(candidates, key=lambda expiry: (abs((expiry - t_pre).days - 120), expiry))
    sides = by_expiry[expiry]
    nearby = [strike for strike in _pairs(sides) if 0.75 * spot <= strike <= 1.25 * spot]
    if not nearby:
        return {"expiry": expiry.isoformat(), "drop_reason": "no_pair_within_25_percent_of_spot"}
    atm = _nearest(nearby, spot)
    listed_calls = sorted(sides["call"])
    above = [strike for strike in listed_calls if strike >= 1.05 * spot]
    sold = above[0] if above else listed_calls[-1]
    return {
        "expiry": expiry.isoformat(), "atm_strike": atm, "strike": sold,
        "atm_call": sides["call"][atm], "atm_put": sides["put"][atm],
        "sold_call": sides["call"][sold], "drop_reason": None,
    }


def _stock_price(strike: float, expiry: date, day: date, call: BarMark, put: BarMark) -> float:
    return strike * exp(-RATE * max((expiry - day).days, 0) / 365) + call.close - put.close


def _quote_time(quote: dict[str, Any]) -> datetime | None:
    """Quotes expose nanosecond SIP timestamps (participant is a fallback)."""
    timestamp = quote.get("sip_timestamp")
    if timestamp is None:
        timestamp = quote.get("participant_timestamp", quote.get("timestamp"))
    if timestamp is None:
        return None
    try:
        if isinstance(timestamp, str) and not timestamp.isdigit():
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return parsed.astimezone(NEW_YORK) if parsed.tzinfo else None
        return datetime.fromtimestamp(int(timestamp) / 1_000_000_000, timezone.utc).astimezone(NEW_YORK)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def price_trade(
    ticker: str, filing_date: date, *, client: Any = None, completed_session: date | None = None
) -> dict[str, Any]:
    """Price one event (or a peer assigned that event's filing date).

    ``client`` provides chain(ticker, as_of), bars(contract, start, end), and
    get_json(path, params).  Dates passed to that client are ``datetime.date``.
    The returned dictionary contains only JSON-compatible values and preserves
    diagnostics accumulated before a drop.
    """
    if client is None:
        from . import data as client
    if isinstance(filing_date, str):
        filing_date = date.fromisoformat(filing_date)
    ticker = ticker.upper().replace("/", ".")
    filing_session = sessions.session_on_or_after(filing_date)
    t_pre = sessions.session_before(filing_session)
    entry = sessions.session_after(filing_session)
    exit_day = sessions.shift_session(entry, 10)
    result: dict[str, Any] = {
        "ticker": ticker, "filing_date": filing_date.isoformat(),
        "filing_session": filing_session.isoformat(), "t_pre": t_pre.isoformat(),
        "entry": entry.isoformat(), "exit": exit_day.isoformat(),
        "status": "dropped", "drop_reason": None,
    }

    def drop(reason: str) -> dict[str, Any]:
        result["drop_reason"] = reason
        return result

    chain = _chain_by_expiry(client.chain(ticker, t_pre))
    initial = estimate_spot(chain, t_pre, client)
    result.update({"pre_spot": initial["spot"], "spot_expiry": initial.get("spot_expiry"),
                   "spot_attempts": initial["attempts"]})
    if initial["spot"] is None:
        return drop(initial["drop_reason"])
    choice = select_expiry_and_strikes(chain, t_pre, initial["spot"])
    result.update(choice)
    if choice["drop_reason"]:
        return result
    expiry = date.fromisoformat(choice["expiry"])
    atm = choice["atm_strike"]
    start = t_pre - timedelta(days=10)
    # Fetch each distinct contract only once; U is permitted to equal K.
    bars = {contract: normalize_bars(client.bars(contract, start, expiry))
            for contract in dict.fromkeys((choice["atm_call"], choice["atm_put"], choice["sold_call"]))}

    def get_mark(label: str, day: date, output_name: str) -> BarMark | None:
        value = mark(bars[choice[label]], day)
        result[output_name] = value.close if value else None
        result[output_name + "_date"] = value.day.isoformat() if value else None
        return value

    pre_call = get_mark("atm_call", t_pre, "pre_atm_call_mark")
    pre_put = get_mark("atm_put", t_pre, "pre_atm_put_mark")
    if pre_call is None or pre_put is None:
        return drop("missing_pre_atm_parity_mark")
    result["parity_pre_spot"] = _stock_price(atm, expiry, t_pre, pre_call, pre_put)
    expiry_session = sessions.session_on_or_before(expiry)
    result["expiry_session"] = expiry_session.isoformat()
    entry_call = get_mark("atm_call", entry, "entry_atm_call_mark")
    entry_put = get_mark("atm_put", entry, "entry_atm_put_mark")
    sold_entry = get_mark("sold_call", entry, "entry_mark")
    if entry_call is None or entry_put is None:
        return drop("missing_entry_stock_price")
    result["entry_spot"] = _stock_price(atm, expiry, entry, entry_call, entry_put)
    if sold_entry is None:
        return drop("missing_entry_sold_call_mark")
    if exit_day > expiry_session:
        return drop("exit_after_expiry_session")
    completed_session = completed_session if completed_session is not None else sessions.last_completed_session()
    if exit_day > completed_session:
        return drop("exit_not_completed")
    sold_exit = get_mark("sold_call", exit_day, "exit_mark")
    exit_call = get_mark("atm_call", exit_day, "exit_atm_call_mark")
    exit_put = get_mark("atm_put", exit_day, "exit_atm_put_mark")
    if sold_exit is None:
        return drop("missing_exit_sold_call_mark")
    if exit_call is None or exit_put is None:
        return drop("missing_exit_stock_price")
    result["exit_spot"] = _stock_price(atm, expiry, exit_day, exit_call, exit_put)
    cutoff = datetime.combine(entry, time(16), NEW_YORK)
    payload = client.get_json(f"/v3/quotes/{choice['sold_call']}", {
        "timestamp.lte": cutoff.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "order": "desc", "sort": "timestamp", "limit": 1,
    })
    quotes = payload.get("results", [])
    if not quotes:
        return drop("missing_entry_quote")
    quote = quotes[0]
    quoted_at = _quote_time(quote)
    result["quote_time"] = quoted_at.isoformat() if quoted_at else None
    result["bid"] = quote.get("bid_price")
    result["ask"] = quote.get("ask_price")
    if quoted_at is None or quoted_at.date() != entry or quoted_at > cutoff:
        return drop("entry_quote_not_same_day_at_or_before_close")
    try:
        bid, ask = float(quote["bid_price"]), float(quote["ask_price"])
    except (KeyError, ValueError, TypeError):
        return drop("invalid_entry_quote_prices")
    if not (isfinite(bid) and isfinite(ask) and bid >= 0 and ask > 0 and ask >= bid):
        return drop("invalid_entry_quote_prices")
    half_spread = (ask - bid) / 2
    result["half_spread"] = half_spread
    if result["entry_spot"] == 0:
        return drop("zero_entry_stock_price")
    result["cost"] = 2 * half_spread / result["entry_spot"]
    result["gross"] = -(sold_exit.close - sold_entry.close) / result["entry_spot"]
    result["net"] = result["gross"] - result["cost"]
    result["status"] = "valid"
    result["drop_reason"] = None
    return result
