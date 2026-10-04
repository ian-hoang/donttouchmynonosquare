"""Independent execution/cash-dividend sensitivity; frozen signals unchanged."""
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import numpy as np
import pandas as pd
from study import HERE,ASSETS,SECTORS,SPEC,load,targets,account,metrics,save
p,rf,days,checks=load();raw={};div={}
for a in ASSETS:
 j=json.loads((HERE/'data'/f'{a}.json').read_text())['chart']['result'][0]
 idx=pd.DatetimeIndex([datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date() for t in j['timestamp']])
 raw[a]=pd.Series(j['indicators']['quote'][0]['close'],index=idx)
 div[a]=pd.Series({pd.Timestamp(datetime.fromtimestamp(x['date'],ZoneInfo('America/New_York')).date()):x['amount'] for x in j.get('events',{}).get('dividends',{}).values()}).reindex(p.index,fill_value=0)
raw=pd.DataFrame(raw);div=pd.DataFrame(div)
price_return=raw.pct_change(fill_method=None).fillna(0)
dividend_return=(div/raw.shift(1)).fillna(0)
actual_return=price_return+dividend_return
checks_out={'description':'Audit of frozen adjusted-close implementation. Exact cash distribution sensitivity holds same signals, computes P&L from split-adjusted raw price changes plus distribution, and turnover drift from price changes only; dividends are cash. Ex-date recognition of dividend receivable; payment-date financing not modeled.', 'variants':{}}
for h in [1,5]:
 target,beta,signal=targets(p,h,True)
 expected=signal.shift(2,fill_value=0)
 assert np.allclose(target.shift(1,fill_value=0),expected)
 # First beta manually uses precisely preceding252 returns, independent covariance call.
 k=1000;rr=p.pct_change(fill_method=None)
 for a in SECTORS:
  prior=rr.iloc[k-252:k][[a,'SPY']].to_numpy()
  manual=np.cov(prior[:,0],prior[:,1],ddof=1)[0,1]/np.var(prior[:,1],ddof=1)
  assert abs(manual-beta.iloc[k][a])<1e-12
 original=account(p,rf,days,target)
 target.iloc[-1]=0.;held=target.shift(1,fill_value=0)
 exact=original.copy()
 exact['gross_pnl']=(held*actual_return).sum(axis=1)
 exact['gross_excess']=exact.gross_pnl-exact.financing_opportunity
 exact['turnover']=(target-held*(1+price_return)).abs().sum(axis=1)
 exact['net_base']=exact.gross_excess-exact.borrow_carry-exact.turnover*.0002
 exact['net_stress']=exact.gross_excess-exact.borrow_carry-exact.turnover*.0005
 delta=exact.net_base-original.net_base
 checks_out['variants'][f'residual_reversal_{h}day']={'timing_delay_assertion':True,'manual_beta_error_below1e-12':True,'max_abs_daily_pnl_difference_bps':delta.abs().max()*1e4,'periods':{period:{'exact_cash_dividend_metrics':metrics(exact.loc[start:end],'net_base'),'annual_mean_change_bps':delta.loc[start:end].mean()*252*1e4} for period,(start,end) in SPEC['periods'].items()}}
save('accounting_sensitivity.json',checks_out)
print(json.dumps(checks_out,indent=2))
