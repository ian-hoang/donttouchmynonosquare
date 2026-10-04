import math
import unittest
import json
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import engine as e


class FinancialChecks(unittest.TestCase):
    def test_quotes_reject_future_stale_crossed_or_empty_size(self):
        at=e.cutoff('2024-05-02')
        q=dict(sip_timestamp=at.value,bid_price=2.,ask_price=2.1,bid_size=1,ask_size=2)
        self.assertIsNotNone(e.validate_quote(q,at))
        for change in [dict(sip_timestamp=at.value+1),dict(sip_timestamp=at.value-301*10**9),
                       dict(bid_price=3.),dict(ask_size=0)]:
            self.assertIsNone(e.validate_quote(dict(q,**change),at))

    def test_half_days_and_holdout_guard(self):
        self.assertEqual(e.cutoff('2024-11-29').tz_convert('America/New_York').strftime('%H:%M'),'12:55')
        self.assertEqual(e.cutoff('2025-06-12').tz_convert('America/New_York').strftime('%H:%M'),'15:55')
        with self.assertRaises(ValueError):e.cutoff('2026-01-02')

    def test_round_trip_crosses_both_spreads_and_pays_commission(self):
        q={'p':dict(bid=1.,ask=1.2,mid=1.1)}
        self.assertAlmostEqual(e.leg_pnl({'p':1},q,q),-.213)
        self.assertAlmostEqual(e.leg_pnl({'p':-1},q,q),-.213)
        self.assertAlmostEqual(e.leg_pnl({'p':1},q,q,.025),-.268)

    def test_cash_secured_put_gain_and_loss(self):
        entry={'p':dict(bid=2.,ask=2.2)}
        self.assertAlmostEqual(e.leg_pnl({'p':-1},entry,{'p':dict(bid=.2,ask=.3)}),1.687)
        self.assertAlmostEqual(e.leg_pnl({'p':-1},entry,{'p':dict(bid=5.,ask=5.2)}),-3.213)

    def test_put_call_parity_and_iv_recovery(self):
        s,k,t,v=102.,100.,.25,.3
        c=e.bs_price(s,k,t,v,'call');p=e.bs_price(s,k,t,v,'put')
        self.assertAlmostEqual(c-p,s-k*math.exp(-.04*t))
        self.assertAlmostEqual(e.iv(p,s,k,t,'put'),v,places=8)
        self.assertIsNone(e.iv(200,s,k,t,'put'))

    def test_protective_put_and_collar_hedge_different_upside(self):
        qe={k:dict(bid=v,ask=v) for k,v in {'C_K':7.,'P_K':5.,'P_L0.05':2.,'C_U0.05':3.}.items()}
        qx={k:dict(bid=v,ask=v) for k,v in {'C_K':20.,'P_K':0.,'P_L0.05':0.,'C_U0.05':12.}.items()}
        pp=e.leg_pnl(e.weights('protective_put',.05),qe,qx)
        collar=e.leg_pnl(e.weights('collar',.05),qe,qx)
        self.assertAlmostEqual(pp-collar,9.013)

    def test_future_filings_cannot_change_gate_peer_eligibility(self):
        self.assertTrue(e.quiet_before([94,101,105],100))
        self.assertTrue(e.quiet_before([94],100))
        self.assertFalse(e.quiet_before([95,101],100))
        self.assertFalse(e.quiet_before([100],100))

    def test_price_conditioned_event_never_uses_first_session_entry(self):
        start=pd.Timestamp('2024-05-01');expiry=pd.Timestamp('2024-06-21')
        dates=e.CAL[(e.CAL>start)&(e.CAL<=expiry)]
        quotes={}
        for d in dates:
            q=dict(bid=3.,ask=3.1,mid=3.05,timestamp=e.cutoff(d).value,bid_size=1,ask_size=1)
            quotes[str(d.date())]={k:dict(q) for k in ['C_K','P_K','P_L0.05','C_U0.05']}
        b=dict(expiry=str(expiry.date()),expiry_session=str(expiry.date()),strikes={'K':100.,'L0.05':95.,'U0.05':105.},
               contracts={k:k for k in ['C_K','P_K','P_L0.05','C_U0.05']},quotes=quotes)
        p=dict(ticker='TEST',date=str(start.date()),spot_pre=100.,buckets={'3-6m':b})
        event=dict(signal='duration',strategy='protective_put',id='test',ticker='TEST',filing_date=str(start.date()))
        rows=e.evaluate(p,event,'event',True)
        self.assertTrue(rows)
        self.assertEqual({r['delay'] for r in rows},{2,3})

    def test_summary_excludes_old_spec_and_old_code_runs(self):
        import summarize
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cache=root/'cache';cache.mkdir()
            (root/'spec.json').write_text('{}');(root/'engine.py').write_text('current')
            for name in ['governance_events.json','governance_spec.json']:(root/name).write_text('{}')
            good=dict(spec_sha256=hashlib.sha256(b'{}').hexdigest(),engine_sha256=hashlib.sha256(b'current').hexdigest(),
                      text_source_sha256={name:hashlib.sha256(b'{}').hexdigest() for name in ['governance_events.json','governance_spec.json']})
            for name,manifest in [('governance',good),('governance_buried',dict(good,spec_sha256='old')),
                                  ('governance_duration',dict(good,engine_sha256='old'))]:
                (cache/f'observations_{name}.json').write_text('[]')
                (root/f'manifest_{name}.json').write_text(json.dumps(manifest))
                (root/f'gates_{name}.json').write_text('[]')
                (root/f'complete_{name}.json').write_text(json.dumps(dict(status='complete',
                    manifest_sha256=hashlib.sha256(json.dumps(manifest).encode()).hexdigest(),
                    observations_sha256=hashlib.sha256(b'[]').hexdigest(),gates_sha256=hashlib.sha256(b'[]').hexdigest())))
            with patch.object(summarize,'HERE',root),patch.object(summarize,'CACHE',cache):
                self.assertEqual(summarize.current_output('governance').name,'observations_governance.json')
                # A rerun that overwrote observations but did not complete must
                # never borrow the prior completion receipt.
                (cache/'observations_governance.json').write_text('[1]')
                self.assertIsNone(summarize.current_output('governance'))


if __name__=='__main__':unittest.main()
