"""Synthetic checks of the frozen rules; no network or original implementation."""

from copy import deepcopy
from datetime import date, datetime, time, timezone
from math import exp
import unittest

from . import pricing


def raw_bar(day, close):
    timestamp = datetime.combine(day, time(0), pricing.NEW_YORK).timestamp()
    return {"t": int(timestamp * 1000), "c": close}


def metadata(expiry, strike, kind, prefix):
    return {"ticker": f"O:{prefix}{kind}{strike}", "expiration_date": expiry.isoformat(),
            "strike_price": strike, "contract_type": kind, "shares_per_contract": 100}


class FixtureClient:
    def __init__(self):
        self.pre = date(2024, 1, 2)
        self.entry = date(2024, 1, 4)
        self.exit = date(2024, 1, 19)
        self.near = date(2024, 1, 12)
        self.expiry = date(2024, 5, 3)
        self.contracts = []
        self.series = {}
        self.requests = []
        for expiry, prefix in ((self.near, "N"), (self.expiry, "F")):
            for strike in (90, 100, 110):
                for kind in ("call", "put"):
                    contract = metadata(expiry, strike, kind, prefix)
                    self.contracts.append(contract)
                    self.series[contract["ticker"]] = []
        # A listed call need not be paired to be the sold call.
        self.contracts.append(metadata(self.expiry, 105, "call", "F"))
        self.series["O:Fcall105"] = [raw_bar(self.entry, 3), raw_bar(self.exit, 2.2)]
        for day in (self.pre, self.entry, self.exit):
            difference = 100 - 100 * exp(-0.04 * (self.expiry - day).days / 365)
            self.series["O:Fcall100"].append(raw_bar(day, 8))
            self.series["O:Fput100"].append(raw_bar(day, 8 - difference))
        near_difference = 100 - 100 * exp(-0.04 * (self.near - self.pre).days / 365)
        self.series["O:Ncall100"] = [raw_bar(self.pre, 5)]
        self.series["O:Nput100"] = [raw_bar(self.pre, 5 - near_difference)]
        quoted_at = datetime.combine(self.entry, time(15, 59), pricing.NEW_YORK)
        self.quotes = [{"sip_timestamp": int(quoted_at.timestamp() * 1_000_000_000),
                        "bid_price": 2.9, "ask_price": 3.1}]

    def chain(self, ticker, as_of):
        self.requests.append(("chain", ticker, as_of))
        return deepcopy(self.contracts)

    def bars(self, contract, start, end):
        self.requests.append(("bars", contract, start, end))
        return [deepcopy(bar) for bar in self.series.get(contract, [])
                if start <= pricing.bar_date(bar) <= end]

    def get_json(self, path, params=None):
        self.requests.append(("quote", path, params))
        return {"results": deepcopy(self.quotes)}


class PricingTests(unittest.TestCase):
    def run_trade(self, client=None, completed=date(2026, 10, 2)):
        return pricing.price_trade("abc", date(2024, 1, 3), client=client or FixtureClient(),
                                   completed_session=completed)

    def test_mark_age_counts_sessions_and_preserves_close(self):
        bars = [pricing.BarMark(2, date(2024, 1, 12))]
        self.assertEqual(pricing.mark(bars, date(2024, 1, 18)).close, 2)
        self.assertIsNone(pricing.mark(bars, date(2024, 1, 19)))
        self.assertIsNone(pricing.mark(bars, date(2024, 1, 11)))

    def test_bar_utc_timestamp_is_converted_to_new_york_date(self):
        timestamp = datetime(2024, 1, 13, 0, 0, tzinfo=timezone.utc).timestamp()
        self.assertEqual(pricing.bar_date({"t": timestamp * 1000}), date(2024, 1, 12))

    def test_complete_trade_and_entry_spread_twice(self):
        client = FixtureClient()
        result = self.run_trade(client)
        self.assertEqual(result["status"], "valid", result)
        self.assertEqual(result["entry"], "2024-01-04")
        self.assertEqual(result["exit"], "2024-01-19")
        self.assertEqual(result["strike"], 105)
        self.assertEqual(result["atm_strike"], 100)
        self.assertEqual(result["expiry"], "2024-05-03")
        self.assertAlmostEqual(result["entry_spot"], 100)
        self.assertAlmostEqual(result["half_spread"], 0.1)
        self.assertAlmostEqual(result["cost"], 0.002)
        self.assertAlmostEqual(result["gross"], 0.008)
        self.assertAlmostEqual(result["net"], 0.006)
        quote_request = next(request for request in client.requests if request[0] == "quote")
        self.assertEqual(quote_request[2]["timestamp.lte"], "2024-01-04T21:00:00Z")
        self.assertEqual(quote_request[2]["limit"], 1)

    def test_initial_spot_can_use_four_session_old_bar(self):
        client = FixtureClient()
        for ticker in ("O:Ncall100", "O:Nput100"):
            close = client.series[ticker][0]["c"]
            client.series[ticker] = [raw_bar(date(2023, 12, 26), close)]
        self.assertIsNone(pricing.mark(pricing.normalize_bars(client.series["O:Ncall100"]), client.pre))
        result = self.run_trade(client)
        self.assertEqual(result["status"], "valid", result)
        self.assertAlmostEqual(result["pre_spot"], 100)
        self.assertEqual(result["spot_attempts"][0]["call_mark_date"], "2023-12-26")

    def test_nearest_expiry_pair_shortage_drops_without_skipping(self):
        client = FixtureClient()
        client.contracts = [contract for contract in client.contracts
                            if not (contract["expiration_date"] == client.near.isoformat()
                                    and contract["strike_price"] == 110)]
        result = self.run_trade(client)
        self.assertEqual(result["drop_reason"], "near_expiry_fewer_than_3_pairs")
        self.assertFalse(any(request[0] == "bars" for request in client.requests))

    def test_exit_stock_price_required_even_with_sold_call(self):
        client = FixtureClient()
        client.series["O:Fput100"] = client.series["O:Fput100"][:-1]
        result = self.run_trade(client)
        self.assertEqual(result["drop_reason"], "missing_exit_stock_price")
        self.assertEqual(result["exit_mark"], 2.2)
        self.assertIsNone(result["exit_atm_put_mark"])

    def test_pre_pair_marks_required_even_when_entry_exists(self):
        client = FixtureClient()
        client.series["O:Fput100"] = client.series["O:Fput100"][1:]
        self.assertEqual(self.run_trade(client)["drop_reason"], "missing_pre_atm_parity_mark")

    def test_invalid_last_quote_drops_without_earlier_quote_fallback(self):
        client = FixtureClient()
        client.quotes.insert(0, {**client.quotes[0], "bid_price": -0.1})
        self.assertEqual(self.run_trade(client)["drop_reason"], "invalid_entry_quote_prices")

    def test_previous_day_quote_drops(self):
        client = FixtureClient()
        client.quotes[0]["sip_timestamp"] -= 86_400 * 1_000_000_000
        self.assertEqual(self.run_trade(client)["drop_reason"], "entry_quote_not_same_day_at_or_before_close")

    def test_zero_bid_and_zero_spread_are_allowed(self):
        for bid, ask in ((0, 0.1), (3, 3)):
            with self.subTest(bid=bid, ask=ask):
                client = FixtureClient()
                client.quotes[0].update(bid_price=bid, ask_price=ask)
                self.assertEqual(self.run_trade(client)["status"], "valid")

    def test_incomplete_exit_drops(self):
        self.assertEqual(self.run_trade(completed=date(2024, 1, 18))["drop_reason"], "exit_not_completed")

    def test_sold_strike_falls_back_to_highest_call(self):
        client = FixtureClient()
        grouped = pricing._chain_by_expiry(client.contracts)
        selection = pricing.select_expiry_and_strikes(grouped, client.pre, 115)
        self.assertEqual(selection["strike"], 110)

    def test_shares_per_contract_missing_is_100_and_adjusted_contract_excluded(self):
        client = FixtureClient()
        missing = deepcopy(client.contracts[0])
        del missing["shares_per_contract"]
        excluded = {**client.contracts[1], "shares_per_contract": 150}
        grouped = pricing._chain_by_expiry([missing, excluded])
        self.assertIn(90, grouped[client.near]["call"])
        self.assertNotIn(90, grouped[client.near]["put"])


if __name__ == "__main__":
    unittest.main()
