"""Financial and data-boundary invariants; no network calls."""
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import backtest as b


class BacktestChecks(unittest.TestCase):
    def make_event(self):
        days=b.CAL[(b.CAL>='2024-01-02')&(b.CAL<='2024-05-17')]
        values={'C_K':(10.,8.),'P_K':(8.,10.),'C_U0.05':(3.,1.),'P_L0.05':(2.,5.)}
        legs={}
        for name,(entry,exit) in values.items():
            closes=np.full(len(days),exit)
            closes[days<=pd.Timestamp('2024-01-04')]=entry
            frame=pd.DataFrame({'close':closes,'volume':100},index=days)
            legs[name]=b.base.Leg(name,'call' if name.startswith('C') else 'put',100.,frame)
        pe=b.base.PricedEvent('TEST',pd.Timestamp('2024-01-02'),pd.Timestamp('2023-12-29'),
             pd.Timestamp('2024-01-04'),'3-6m',pd.Timestamp('2024-05-17'),pd.Timestamp('2024-05-17'),
             100.,{'K':100.,'U0.05':105.,'L0.05':95.},legs)
        return pe

    def test_stale_marks_rejected(self):
        leg=self.make_event().legs['C_K']
        leg.bars=leg.bars.iloc[:1]
        self.assertTrue(np.isnan(leg.mark(pd.Timestamp('2024-01-03'))))

    def test_all_collar_legs_pay_costs(self):
        pe=self.make_event()
        event={'signal':'departures','ticker':'TEST','id':'test','filing_date':'2024-01-02'}
        with patch.object(b,'OTMS',[.05]):
            rows=b.evaluate_one(pe,event,'collar',None,'2024-01-02')
        r=next(x for x in rows if x['delay']==2 and x['horizon']=='1' and x['haircut']==.05)
        expected=.05*(10+8+8+10+2+5+3+1)+.0065*8
        self.assertAlmostEqual(r['costs_per_share'],expected)
        self.assertAlmostEqual((r['gross']-r['net'])*r['spot_proxy'],expected)

    def test_short_put_sign_and_actual_exit_cost(self):
        pe=self.make_event()
        event={'signal':'liquidity','ticker':'TEST','id':'test','filing_date':'2024-01-02'}
        with patch.object(b,'OTMS',[.05]):
            rows=b.evaluate_one(pe,event,'cash_secured_put',None,'2024-01-02')
        r=next(x for x in rows if x['delay']==2 and x['horizon']=='1' and x['haircut']==.05)
        self.assertAlmostEqual(r['gross']*r['spot_proxy'],-3.)
        self.assertAlmostEqual(r['costs_per_share'],.05*(2+5)+.013)

    def test_sensitivity_cost_audit_matches_returns(self):
        pe=self.make_event()
        event={'signal':'liquidity','ticker':'TEST','id':'test','filing_date':'2024-01-02'}
        with patch.object(b,'OTMS',[.05]):
            rows=b.evaluate_one(pe,event,'cash_secured_put',None,'2024-01-02')
        for r in rows:
            self.assertAlmostEqual((r['gross']-r['net'])*r['spot_proxy'],r['costs_per_share'])

    def test_oos_outcome_url_refused(self):
        with self.assertRaises(ValueError):
            b.safe_api('/v2/aggs/ticker/O:TEST/range/1/day/2025-01-01/2026-01-02')

    def test_bar_end_is_clipped_before_network(self):
        frame=pd.DataFrame({'close':[1.],'volume':[2.]},index=[pd.Timestamp('2025-12-31')])
        with patch.object(b,'OLD_BARS',return_value=frame) as f:
            b.safe_bars('TEST','2025-12-01','2026-06-01')
        self.assertEqual(f.call_args.args[-1],b.CUTOFF)

    def test_wrong_host_rejected(self):
        with self.assertRaises(ValueError):b.safe_api('https://example.com/next')

    def test_fallback_search_uses_only_prefiling_prices(self):
        day=pd.Timestamp('2024-01-02')
        chain=pd.DataFrame([{'ticker':kind+str(k),'contract_type':kind,'strike_price':float(k),
                             'expiration_date':pd.Timestamp('2024-01-12'),'dte':10}
                            for k in range(50,151) for kind in ['call','put']])
        queried=[]
        def close(ticker,date):
            queried.append(date)
            return 2. if ticker.endswith('75') else None
        with patch.object(b,'OLD_LOCATE',return_value=None),patch.object(b,'fresh_close',side_effect=close):
            result=b.locate_pre_spot(chain,day)
        self.assertIsNotNone(result)
        self.assertTrue(74<result['spot']<75)
        self.assertTrue(all(d==day for d in queried))


if __name__=='__main__':unittest.main()
