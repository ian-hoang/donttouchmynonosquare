import unittest

import numpy as np
import pandas as pd

from core import dates_for_event, event_return, portfolio, prior_jackpot


def q(bid,ask,size=10000):
    mid=(bid+ask)/2
    return {"bid":bid,"ask":ask,"mid":mid,"spread_fraction":(ask-bid)/mid,
            "ask_size":size,"bid_size":size}


class BacktestTests(unittest.TestCase):
    def setUp(self):
        self.cal=pd.bdate_range("2024-01-02",periods=20)
        self.g=pd.DataFrame({"close":100.,"close_raw":100.,"factor":1.,"div_adj":0.,"ret":0.},index=self.cal)
        self.panel={"TEST":self.g.copy(),"SPY":self.g.copy()}

    def test_window_and_feature_lag(self):
        d=dates_for_event(self.cal,self.cal[15],10)
        self.assertEqual(d["entry_date"],self.cal[4])
        self.assertEqual(d["exit_date"],self.cal[14])
        self.assertLess(d["signal_date"],d["entry_date"])

    def test_roundtrip_spread_is_loss(self):
        row={"ticker":"TEST","entry_date":self.cal[1],"exit_date":self.cal[6]}
        r=event_return(row,q(99,101),q(99,101),q(100,100),q(100,100),self.panel,0,0)
        self.assertAlmostEqual(r["gross"],0)
        self.assertAlmostEqual(r["net"],99/101-1)

    def test_future_event_cannot_use_last_available_session(self):
        self.assertIsNone(dates_for_event(self.cal,self.cal[-1]+pd.Timedelta(days=21),5))
        d=dates_for_event(self.cal,self.cal[-1],5)
        self.assertEqual(d['exit_date'],self.cal[-2])
        self.assertEqual(d['entry_date'],self.cal[-7])

    def test_split_and_dividend(self):
        g=self.panel["TEST"]
        g.loc[:self.cal[4],"factor"]=.5
        g.loc[self.cal[5],"div_adj"]=1
        row={"ticker":"TEST","entry_date":self.cal[1],"exit_date":self.cal[6]}
        r=event_return(row,q(100,100),q(50,50),q(100,100),q(100,100),self.panel,0,0)
        self.assertAlmostEqual(r["net"],.02)

    def test_missing_exit_not_silent_drop(self):
        row={"ticker":"TEST","entry_date":self.cal[1],"exit_date":self.cal[6]}
        self.assertIn("unresolved",event_return(row,q(100,100),None,q(100,100),q(100,100),self.panel)["status"])

    def test_actual_cash_sizing_and_zero_return_cash_days(self):
        r={"ticker":"TEST","entry_date":self.cal[1],"exit_date":self.cal[6],
           "buy_adj_including_fee":100.,"sell_adj_net_fee":110.,"entry_factor":1.,
           "entry_ask_size":1000,"signal":1.}
        path,s=portfolio(pd.DataFrame([r]),self.panel,start=self.cal[0],end=self.cal[-1])
        self.assertEqual(len(path),20)
        self.assertAlmostEqual(s["pnl"],1000)
        self.assertAlmostEqual(s["total_return"],.01)
        self.assertEqual(path.iloc[-1].positions,0)

    def test_future_earnings_cannot_enter_feature(self):
        cal=pd.bdate_range('2022-01-03',periods=400)
        panel={k:pd.DataFrame({'ret':0.},index=cal) for k in ['TEST','SPY']}
        hist=pd.DataFrame({"ticker":["TEST"]*5,"release_date":cal[[40,100,160,220,380]]})
        result,past=prior_jackpot("TEST",cal[300],hist,panel)
        self.assertEqual(len(past),4)
        self.assertEqual(result,0.)
        panel["TEST"].loc[cal[380],"ret"]=1.
        again,_=prior_jackpot("TEST",cal[300],hist,panel)
        self.assertEqual(result,again)

    def test_no_same_day_closing_information(self):
        cal=pd.bdate_range('2022-01-03',periods=400)
        panel={k:pd.DataFrame({'ret':0.},index=cal) for k in ['TEST','SPY']}
        hist=pd.DataFrame({'ticker':['TEST']*4,'release_date':cal[[40,100,160,219]]})
        result,_=prior_jackpot('TEST',cal[220],hist,panel)
        self.assertIsNone(result)

    def test_missing_recent_reaction_not_replaced_with_older_one(self):
        cal=pd.bdate_range('2022-01-03',periods=400)
        panel={k:pd.DataFrame({'ret':0.},index=cal) for k in ['TEST','SPY']}
        hist=pd.DataFrame({'ticker':['TEST']*5,'release_date':cal[[40,100,160,220,280]]})
        panel['TEST'].loc[cal[280],'ret']=np.nan
        result,_=prior_jackpot('TEST',cal[320],hist,panel)
        self.assertIsNone(result)

    def test_delayed_exit_does_not_fund_earlier_entry(self):
        self.panel['OTHER']=self.g.copy()
        common={'buy_adj_including_fee':100.,'sell_adj_net_fee':100.,'entry_factor':1.,
                'entry_ask_size':1000,'signal':1.}
        a=common|{'ticker':'TEST','entry_date':self.cal[1],'exit_date':self.cal[6],
                  'entry_timestamp_ns':10,'exit_timestamp_ns':30}
        b=common|{'ticker':'OTHER','entry_date':self.cal[6],'exit_date':self.cal[10],
                  'entry_timestamp_ns':20,'exit_timestamp_ns':40}
        _,s=portfolio(pd.DataFrame([a,b]),self.panel,initial_cash=10000,ticket=10000)
        self.assertEqual(s['trades'],1)
        self.assertEqual(s['skipped'][0][1],'capital')


if __name__=="__main__":
    unittest.main()
