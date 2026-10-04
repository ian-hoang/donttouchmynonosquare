"""Frozen original-nine sector ETF reversal study. No optimization or paid data."""
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib,json
import numpy as np
import pandas as pd
import statsmodels.api as sm

HERE=Path(__file__).resolve().parent
SPEC=json.loads((HERE/'PROTOCOL.json').read_text())
ASSETS=SPEC['assets'];SECTORS=ASSETS[:-1]

def clean(v):
 if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
 if isinstance(v,(list,tuple,np.ndarray)):return [clean(x) for x in v]
 if isinstance(v,np.integer):return int(v)
 if isinstance(v,(float,np.floating)):return float(v) if np.isfinite(v) else None
 if isinstance(v,(pd.Timestamp,datetime)):return v.isoformat()
 if isinstance(v,np.bool_):return bool(v)
 return v

def save(name,v): (HERE/name).write_text(json.dumps(clean(v),indent=2,allow_nan=False))

def load():
 cols={};raw={};events={};checks={}
 for a in ASSETS:
  j=json.loads((HERE/'data'/f'{a}.json').read_text())['chart']['result'][0]
  idx=pd.DatetimeIndex([datetime.fromtimestamp(t,ZoneInfo(j['meta']['exchangeTimezoneName'])).date() for t in j['timestamp']])
  assert idx.is_unique and idx.is_monotonic_increasing
  cols[a]=pd.Series(j['indicators']['adjclose'][0]['adjclose'],index=idx,dtype=float)
  raw[a]=pd.Series(j['indicators']['quote'][0]['close'],index=idx,dtype=float)
  ev=j.get('events',{});events[a]=ev
 p=pd.DataFrame(cols);raw=pd.DataFrame(raw)
 assert list(p.columns)==ASSETS and len(p)==5724
 assert not p.isna().any().any() and not raw.isna().any().any()
 assert p.index.min()==pd.Timestamp('2004-01-02') and p.index.max()==pd.Timestamp('2026-10-02')
 assert (p>0).all().all()
 rates=pd.read_csv(HERE/'data/DGS3MO.csv',parse_dates=['observation_date']).set_index('observation_date').DGS3MO
 rates=pd.to_numeric(rates,errors='coerce').dropna()/100
 # Must be strictly before current close return date. Gap carry applies only to rates.
 lag_rate=rates.reindex(rates.index.union(p.index)).sort_index().ffill().shift(1).reindex(p.index)
 assert not lag_rate.isna().any()
 days=p.index.to_series().diff().dt.days.fillna(0)
 rf=lag_rate*days/365
 for a in ASSETS:
  factor=p[a]/raw[a];fr=factor/factor.shift(1)-1
  dividends={pd.Timestamp(datetime.fromtimestamp(v['date'],ZoneInfo('America/New_York')).date()):v['amount'] for v in events[a].get('dividends',{}).values()}
  d=pd.Series(dividends).reindex(p.index,fill_value=0)
  expected=1/(1-d/raw[a].shift(1))-1
  unexpected=(fr-expected).abs()
  checks[a]={'rows':len(p),'dividend_events':len(dividends),'split_events':len(events[a].get('splits',{})),
   'max_adjustment_residual_bps':unexpected.max()*1e4,
   'worst_adjustment_dates':[{ 'date':str(t.date()),'residual_bps':unexpected.loc[t]*1e4} for t in unexpected.nlargest(3).index]}
 return p,rf,days,checks

def targets(p,horizon,residual=True):
 r=p.pct_change(fill_method=None)
 beta=pd.DataFrame({a:r[a].rolling(252,min_periods=252).cov(r.SPY)/r.SPY.rolling(252,min_periods=252).var() for a in SECTORS}).shift(1)
 observations=r[SECTORS]-beta.mul(r.SPY,axis=0) if residual else r[SECTORS]
 score=observations.rolling(horizon,min_periods=horizon).sum()
 ranks=score.rank(axis=1,method='average')
 centered=ranks.sub(ranks.mean(axis=1),axis=0)
 w=-centered.div(centered.abs().sum(axis=1),axis=0)
 w['SPY']=-(w[SECTORS]*beta).sum(axis=1,min_count=9)
 w=w.div(w.abs().sum(axis=1,min_count=10),axis=0)
 w.loc[w.isna().any(axis=1)]=0
 assert np.isfinite(w).all().all()
 # signal close t enters next close; targets are balances established at close.
 target=w.shift(1,fill_value=0)
 return target,beta,w

def account(p,rf,days,target,liquidate=True):
 r=p.pct_change(fill_method=None).fillna(0)
 target=target.copy()
 if liquidate:target.iloc[-1]=0.
 held=target.shift(1,fill_value=0)
 drift=held*(1+r)
 turnover=(target-drift).abs().sum(axis=1)
 gross=(held*r).sum(axis=1)
 financing=held.sum(axis=1)*rf
 shorts=-held.clip(upper=0).sum(axis=1)
 borrow=shorts*.02*days/365
 out=pd.DataFrame({'gross_pnl':gross,'financing_opportunity':financing,'gross_excess':gross-financing,'borrow_carry':borrow,'turnover':turnover,'short_exposure':shorts,'held_gross':held.abs().sum(axis=1),'net_exposure':held.sum(axis=1)})
 out['net_base']=out.gross_excess-borrow-turnover*.0002
 out['net_stress']=out.gross_excess-borrow-turnover*.0005
 return out

def metrics(d,key):
 a=d[key];std=a.std(ddof=1);cum=a.cumsum();draw=cum-cum.cummax().clip(lower=0)
 return {'n':len(a),'active_days':int((d.held_gross>0).sum()),'first':str(a.index[0].date()),'last':str(a.index[-1].date()),'annual_mean_pct':a.mean()*252*100,'daily_mean_bps':a.mean()*1e4,'annual_vol_pct':std*np.sqrt(252)*100,'sharpe':a.mean()/std*np.sqrt(252),'fixed_capital_max_drawdown_pct':draw.min()*100,'average_daily_one_way_turnover':d.turnover.mean(),'annual_one_way_turnover':d.turnover.mean()*252,'average_short_exposure':d.short_exposure.mean(),'break_even_one_way_bps_after_borrow':(d.gross_excess.sum()-d.borrow_carry.sum())/d.turnover.sum()*1e4,'sum_fixed_capital_pnl_pct':a.sum()*100}

def bootstrap(a,seed):
 a=np.asarray(a);n=len(a);rng=np.random.default_rng(seed);means=[];sharpes=[]
 for _ in range(40):
  st=rng.integers(0,n,size=(250,int(np.ceil(n/20))))
  ind=((st[:,:,None]+np.arange(20))%n).reshape(250,-1)[:,:n]
  x=a[ind];m=x.mean(axis=1);s=x.std(axis=1,ddof=1)
  means.extend(m*252*100);sharpes.extend(m/s*np.sqrt(252))
 return {'draws':10000,'block_days':20,'seed':seed,'annual_mean_pct_ci95':np.quantile(means,[.025,.975]),'sharpe_ci95':np.quantile(sharpes,[.025,.975]),'fraction_mean_le_zero':np.mean(np.array(means)<=0),'warning':'Conditional sampling uncertainty; no correction for prior research or testing other families.'}

def independent_check(p,rf,days,target,observed):
 prices=p.to_numpy();z=target.to_numpy().copy();z[-1]=0;prev=np.zeros(10);got=[]
 for i in range(len(p)):
  rr=prices[i]/prices[i-1]-1 if i else np.zeros(10)
  pnl=sum(prev[j]*rr[j] for j in range(10))
  fin=sum(prev)*rf.iloc[i]
  bor=sum(max(-x,0) for x in prev)*.02*days.iloc[i]/365
  turn=sum(abs(z[i,j]-prev[j]*(1+rr[j])) for j in range(10))
  got.append(pnl-fin-bor-turn*.0002);prev=z[i]
 error=float(np.max(np.abs(np.array(got)-observed.net_base)))
 assert error<1e-12
 return error

def main():
 p,rf,days,adj_checks=load();verification={'coverage':{'rows':len(p),'assets':ASSETS,'missing_prices':0,'first':str(p.index[0].date()),'last':str(p.index[-1].date())},'corporate_action_adjustments':adj_checks,'cases':{}}
 results={};daily=[]
 for i,(h,resid) in enumerate([(1,True),(5,True),(1,False),(5,False)]):
  name=('residual' if resid else 'raw')+f'_reversal_{h}day'
  target,beta,signal=targets(p,h,resid);out=account(p,rf,days,target)
  err=independent_check(p,rf,days,target,out)
  prefix=[]
  for n in [600,3000,5000]:
   tt,bb,ss=targets(p.iloc[:n],h,resid)
   assert np.allclose(tt.to_numpy(),target.iloc[:n].to_numpy(),rtol=0,atol=1e-14)
   prefix.append(n)
  neutrality=(signal[SECTORS]*beta).sum(axis=1)+signal.SPY
  gross=signal.abs().sum(axis=1)
  assert neutrality.abs().max()<1e-12
  assert ((gross<1e-12)|((gross-1).abs()<1e-12)).all()
  verification['cases'][name]={'independent_max_abs_pnl_error':err,'prefix_lengths_passed':prefix,'max_signal_model_beta':neutrality.abs().max(),'all_active_signal_gross_equal1':True,'first_entry_close':str(target.index[target.abs().sum(axis=1)>0][0].date()),'first_return_close':str(out.index[out.held_gross>0][0].date())}
  results[name]={'role':'hypothesis' if resid else 'diagnostic_not_selection_candidate','periods':{}}
  for j,(period,(start,end)) in enumerate(SPEC['periods'].items()):
   d=out.loc[start:end];stock=p.SPY.pct_change(fill_method=None).reindex(d.index)-rf.reindex(d.index)
   fit=sm.OLS(d.net_base,sm.add_constant(stock.rename('SPY_excess'))).fit(cov_type='HAC',cov_kwds={'maxlags':20})
   m={k:metrics(d,k) for k in ['gross_excess','net_base','net_stress']}
   m['base_uncertainty']=bootstrap(d.net_base,91830+i*10+j)
   m['HAC20_market_regression']={'alpha_daily_bps':fit.params['const']*1e4,'alpha_t':fit.tvalues['const'],'alpha_two_sided_p':fit.pvalues['const'],'SPY_beta':fit.params['SPY_excess']}
   results[name]['periods'][period]=m
  d=out.copy();d['date']=d.index.strftime('%Y-%m-%d');d['variant']=name;daily.extend(d.to_dict('records'))
 save('results.json',{'computed_utc':datetime.now(timezone.utc).isoformat(),'protocol_sha256':hashlib.sha256((HERE/'PROTOCOL.json').read_bytes()).hexdigest(),'method':'Fixed-capital arithmetic excess P&L, $1 gross target, next-close entry, cash benchmark plus2% short carry and all-leg turnover costs. Period slices inherit live positions; only first inception entry and final2026-10-02 liquidation are charged, without artificial liquidations at2021/2023 boundaries.','results':results})
 save('verification.json',verification);save('daily.json',daily)
 for name,v in results.items():
  print(name)
  for period,m in v['periods'].items():
   b=m['net_base'];s=m['net_stress'];print(period,'Sharpe2bp',round(b['sharpe'],3),'Sharpe5bp',round(s['sharpe'],3),'annmean%',round(b['annual_mean_pct'],3),'BEbp',round(b['break_even_one_way_bps_after_borrow'],3),'CI',m['base_uncertainty']['sharpe_ci95'])
if __name__=='__main__':main()
