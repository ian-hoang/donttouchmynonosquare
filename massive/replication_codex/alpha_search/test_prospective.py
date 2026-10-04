"""Checks for forward-information leaks and execution eligibility."""
from datetime import timedelta,timezone
import unittest
from . import prospective as p

class Quotes(unittest.TestCase):
    def setUp(self):
        self.at=p.cutoff('2025-07-03')
        self.q=dict(sip_timestamp=int(self.at.timestamp()*1e9),bid_price=2.,ask_price=2.2,bid_size=1,ask_size=1)
    def test_early_close_dst(self):
        self.assertEqual(self.at.isoformat(),'2025-07-03T12:55:00-04:00')
        self.assertEqual(self.at.astimezone(timezone.utc).hour,16)
        self.assertEqual(p.cutoff('2025-01-03').astimezone(timezone.utc).hour,20)
    def test_age_boundary_and_future(self):
        for seconds,expected in [(300,True),(301,False),(-1,False),(0,True)]:
            q={**self.q,'sip_timestamp':int((self.at-timedelta(seconds=seconds)).timestamp()*1e9)}
            self.assertEqual(p.valid_quote(q,self.at) is not None,expected)
    def test_invalid_and_unavailable_size(self):
        for field,value in [('bid_price',-1),('ask_price',1),('ask_price',0),('bid_size',0),('ask_size',0),('bid_price',float('nan')),('ask_price',float('inf'))]:
            with self.subTest(field=field,value=value):
                self.assertIsNone(p.valid_quote({**self.q,field:value},self.at))
    def test_nanosecond_boundary(self):
        at_ns=int(self.at.timestamp())*1_000_000_000
        for ts in (at_ns+1,at_ns-300_000_000_001):
            self.assertIsNone(p.valid_quote({**self.q,'sip_timestamp':ts},self.at))

class Controls(unittest.TestCase):
    def test_eligibility_uses_no_future_filings(self):
        e=[dict(ticker='COP',filing_date='2025-02-10')]
        history={t:[] for t in p.events.UNIVERSE}
        history['CVX']=['2025-02-11'];history['XOM']=['2025-02-06']
        draw=p.draw_controls(e,history)[0]
        self.assertEqual(draw['eligible'],['CVX'])
        self.assertEqual(draw['peers'],['CVX'])
        history['XOM']=['2025-02-04']
        self.assertEqual(set(p.draw_controls(e,history)[0]['peers']),{'CVX','XOM'})
    def test_same_day_known_before_next_session_entry_excluded(self):
        history={t:[] for t in p.events.UNIVERSE};history['CVX']=['2025-02-10']
        draw=p.draw_controls([dict(ticker='COP',filing_date='2025-02-10')],history)[0]
        self.assertEqual(draw['peers'],['XOM'])
    def test_draws_fixed_before_returns(self):
        e=[dict(ticker='AMD',filing_date='2025-02-10'),dict(ticker='COF',filing_date='2024-02-20')]
        h={t:[] for t in p.events.UNIVERSE}
        self.assertEqual(p.draw_controls(e,h),p.draw_controls(list(reversed(e)),h))
        for d in p.draw_controls(e,h):
            self.assertEqual(len(d['peers']),3)
            self.assertNotIn(d['ticker'],d['peers'])
            self.assertTrue(all(p.SECTORS[t]==d['sector'] for t in d['peers']))

class Baskets(unittest.TestCase):
    def setUp(self):
        self.draws=[dict(ticker='COP',filing_date='2025-02-10',peers=['CVX','XOM'])]
        self.rows=[dict(ticker='COP',filing_date='2025-02-10',status='valid',short_net=.02,long_net=-.03),
                   dict(ticker='CVX',filing_date='2025-02-10',status='valid',short_net=-.01,long_net=.005),
                   dict(ticker='XOM',filing_date='2025-02-10',status='valid',short_net=-.02,long_net=.01)]
    def test_comparison_and_actual_pair_distinct(self):
        r=p.assemble(self.draws,self.rows)[0]
        self.assertAlmostEqual(r['sector_gap'],.035)
        self.assertAlmostEqual(r['pair_net'],.0275)
        self.assertAlmostEqual(r['pair_per_gross_reference'],.01375)
    def test_missing_exit_does_not_silently_drop_admitted_peer(self):
        self.rows[2]['status']='exit_unavailable'
        r=p.assemble(self.draws,self.rows)[0]
        self.assertEqual(r['entry_admitted_peers'],['CVX','XOM'])
        self.assertNotIn('sector_gap',r)
    def test_missing_entry_is_known_when_basket_is_formed(self):
        self.rows[2]['status']='entry_unavailable'
        r=p.assemble(self.draws,self.rows)[0]
        self.assertEqual(r['entry_admitted_peers'],['CVX'])
        self.assertAlmostEqual(r['pair_net'],.025)
    def test_missing_event_exit_retained_as_unpriced(self):
        self.rows[0]['status']='exit_unavailable';self.rows[0].pop('short_net')
        r=p.assemble(self.draws,self.rows)[0]
        self.assertIsNone(r['event_short_net'])
        self.assertNotIn('sector_gap',r)

if __name__=='__main__':unittest.main()
