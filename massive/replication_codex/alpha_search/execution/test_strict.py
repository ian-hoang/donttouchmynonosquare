from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from massive.replication_codex.alpha_search.execution.strict import cutoff, evaluate, validate_quote


class QuoteTests(unittest.TestCase):
    def setUp(self):
        self.at = datetime(2024, 2, 21, 20, 55, tzinfo=timezone.utc)
        self.quote = dict(sip_timestamp=int(self.at.timestamp())*10**9,
                          bid_price=1., ask_price=1.2, bid_size=1, ask_size=1)

    def test_regular_est(self):
        self.assertEqual(cutoff('2024-02-21'), self.at)

    def test_regular_edt(self):
        self.assertEqual(cutoff('2024-06-21').hour, 19)

    def test_early_est(self):
        self.assertEqual(cutoff('2024-11-29').hour, 17)
        self.assertEqual(cutoff('2025-12-24').hour, 17)

    def test_early_edt(self):
        self.assertEqual(cutoff('2024-07-03').hour, 16)

    def test_valid_latest(self):
        self.assertIsNone(validate_quote(self.quote, self.at)[1])

    def test_age_boundary(self):
        self.quote['sip_timestamp'] -= 300*10**9
        self.assertIsNone(validate_quote(self.quote, self.at)[1])
        self.quote['sip_timestamp'] -= 1
        self.assertEqual(validate_quote(self.quote, self.at)[1], 'quote_stale_or_future')

    def test_future_rejected(self):
        self.quote['sip_timestamp'] += 1
        self.assertEqual(validate_quote(self.quote, self.at)[1], 'quote_stale_or_future')

    def test_invalid_latest(self):
        for change, reason in [({'bid_price':2},'invalid_market'),
             ({'ask_price':0},'invalid_market'), ({'bid_size':0},'no_displayed_size'),
             ({'ask_size':0},'no_displayed_size'), ({'bid_price':float('nan')},'nonfinite_quote')]:
            self.assertEqual(validate_quote({**self.quote, **change}, self.at)[1], reason)

    def test_zero_bid_allowed(self):
        self.assertIsNone(validate_quote({**self.quote, 'bid_price':0}, self.at)[1])

    def test_missing(self):
        self.assertEqual(validate_quote(None,self.at)[1], 'no_quote')
        self.assertEqual(validate_quote({'bid_price':1},self.at)[1], 'missing_or_invalid_fields')

    def test_bid_ask_arithmetic_and_two_commissions(self):
        row = dict(ticker='TEST', filing_date='2024-02-20', entry='2024-02-21',
                   exit='2024-03-06', sold_call='O:TEST', strike=105,
                   expiry='2024-06-21', entry_spot=100, net=.01)
        entry = {'bid':5., 'ask':5.2}
        leave = {'bid':3.8, 'ask':4.}
        with patch('massive.replication_codex.alpha_search.execution.strict.fetch_quote',
                   side_effect=[(entry,None), (leave,None)]):
            result = evaluate(row)
        self.assertAlmostEqual(result['short_net'], (5.-4.-.013)/100)
        self.assertAlmostEqual(result['long_net'], (3.8-5.2-.013)/100)
        self.assertAlmostEqual(result['short_net'], result['mid_gross']-result['cost'])
        self.assertAlmostEqual(result['short_net']+result['long_net'], -.00426)

    def test_invalid_entry_still_checks_exit_then_drops(self):
        row = dict(ticker='TEST', filing_date='2024-02-20', entry='2024-02-21',
                   exit='2024-03-06', sold_call='O:TEST', strike=105,
                   expiry='2024-06-21', entry_spot=100, net=.01)
        with patch('massive.replication_codex.alpha_search.execution.strict.fetch_quote',
                   side_effect=[(None,'invalid_market'), ({'bid':3.8,'ask':4.},None)]) as fetch:
            result = evaluate(row)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(result['status'], 'dropped')
        self.assertNotIn('short_net', result)


if __name__ == '__main__':
    unittest.main()
