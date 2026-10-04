"""One fixed, causal SPY noise-band adaptation. Protocol frozen before results."""
from pathlib import Path
import sys, json, gzip, hashlib
import numpy as np
import pandas as pd
from scipy.stats import norm
import statsmodels.api as sm
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
RAW=HERE.parent/'intraday'/'raw'
CLOCK=np.arange(390)+570
DECISIONS=np.arange(29,360,30)

def payload(path): return json.loads(gzip.decompress(path.read_bytes()))
def load():
    daily=pd.DataFrame(payload(RAW/'daily.json.gz')['results'])
    daily.index=pd.to_datetime(daily.t,unit='ms',utc=True).dt.tz_convert('America/New_York').dt.normalize().dt.tz_localize(None)
    daily=daily.sort_index();daily=daily.loc[~daily.index.duplicated()]
    dates=daily.index
    mats={k:np.full((len(dates),390),np.nan) for k in ['o','h','l','c','v','vw']}
    duplicate=0
    for p in sorted(RAW.glob('minute_*.json.gz')):
        d=pd.DataFrame(payload(p)['results'])
        ts=pd.to_datetime(d.t,unit='ms',utc=True).dt.tz_convert('America/New_York')
        mins=ts.dt.hour*60+ts.dt.minute-570
        day=ts.dt.normalize().dt.tz_localize(None)
        ii=dates.get_indexer(day);keep=(ii>=0)&(mins>=0)&(mins<390)
        idx=ii[keep];mm=mins[keep].to_numpy();d=d.loc[keep]
        duplicate+=int(np.isfinite(mats['o'][idx,mm]).sum())
        for k in mats:mats[k][idx,mm]=d[k].to_numpy()
    assert duplicate==0,duplicate
    moves=np.abs(mats['c']/mats['o'][:,[0]]-1)
    noise=pd.DataFrame(moves,index=dates).rolling(14,min_periods=14).mean().shift(1).to_numpy()
    valid=np.ones((len(dates),390),dtype=bool)
    for k in mats:valid&=np.isfinite(mats[k])&(mats[k]>0)
    valid&=(mats['h']>=mats['l'])&(mats['h']>=mats['o'])&(mats['h']>=mats['c'])&(mats['l']<=mats['o'])&(mats['l']<=mats['c'])
    prefix=np.logical_and.accumulate(valid,axis=1)
    cv=np.cumsum(np.nan_to_num(mats['v']),axis=1)
    vwap=np.cumsum(np.nan_to_num(mats['vw']*mats['v']),axis=1)/np.where(cv>0,cv,np.nan)
    yields=pd.read_csv(HERE.parent/'sectors'/'data'/'DGS3MO.csv',parse_dates=['observation_date'],na_values='.')
    annual=yields.set_index('observation_date').DGS3MO.astype(float).reindex(dates).ffill().shift(1)/100
    assert annual.iloc[1:].notna().all()
    annual=annual.ffill().bfill()
    elapsed=dates.to_series().diff().dt.days.fillna(1)
    rf=(1+annual)**(elapsed/365)-1
    daily['rf_annual_lagged']=annual
    divs=pd.DataFrame(payload(RAW/'dividends.json.gz')['results'])
    div=divs.assign(date=pd.to_datetime(divs.ex_dividend_date)).groupby('date').cash_amount.sum().reindex(dates,fill_value=0)
    daily['benchmark_total']=((daily.c+div)/daily.c.shift(1)-1).fillna(0)
    daily['rf_lagged']=rf
    return daily,mats,noise,prefix,vwap

def excluded(d):
    thanksgiving=pd.Timestamp(year=d.year,month=11,day=1)
    thanksgiving+=pd.Timedelta(days=(3-thanksgiving.weekday())%7+21)
    return (d.month==7 and d.day in [2,3]) or (d.month==12 and d.day==24) or d==thanksgiving+pd.Timedelta(days=1)

def simulate_day(o,c,noise,prefix,vwap,prevclose,cost_bps=1.,record=False):
    # $1 day-start NAV, fixed fractional shares between actual state changes.
    cash=1.;q=0.;fees=0.;turnover=0.;gross_pnl=0.;max_short=0.;capital_minutes=0.;lastmark=np.nan
    pending=None;locked=False;quality_events=0;delayed_fills=0;unresolved=False
    trades=[];entered=0;max_entry_gross=0.;last_signal=None
    upper=np.maximum(o[0],prevclose)*(1+noise)
    lower=np.minimum(o[0],prevclose)*(1-noise)
    targets=np.zeros(390,dtype=int)
    for i in range(390):
        px=o[i]
        if i==389:pending=(i,0,'scheduled_flatten',None)
        if pending is not None and i>=pending[0] and np.isfinite(px) and px>0:
            due,target,reason,signal_i=pending
            pending=None
            current=int(np.sign(q))
            if current!=target:
                if i>due:delayed_fills+=1
                # Close first, preserving cashflow exactly through a reversal.
                if q:
                    dq=-q;fee=abs(dq)*px*cost_bps/1e4
                    cash-=dq*px+fee;fees+=fee;turnover+=abs(dq)*px
                    trades.append({'i':i,'dq':float(dq),'price':float(px),'fee':float(fee),'kind':'exit','signal_i':signal_i,'reason':reason})
                    q=0.
                if target:
                    equity=cash;budget=max(0.,min(1.,equity));q=target*budget/(px*(1+cost_bps/1e4))
                    fee=abs(q)*px*cost_bps/1e4
                    cash-=q*px+fee;fees+=fee;turnover+=abs(q)*px;entered+=1
                    max_entry_gross=max(max_entry_gross,abs(q)*px/max(equity,1e-12))
                    trades.append({'i':i,'dq':float(q),'price':float(px),'fee':float(fee),'kind':'entry','signal_i':signal_i,'reason':reason})
                    if q<0:max_short=max(max_short,abs(q)*px)
        # Opportunity cost uses observable opening notional held for this minute.
        if np.isfinite(px) and px>0:lastmark=px
        if q and np.isfinite(lastmark):capital_minutes+=abs(q)*lastmark
        if q<0 and np.isfinite(lastmark):max_short=max(max_short,abs(q)*lastmark)
        if i in DECISIONS:
            if not prefix[i]:
                if not locked:quality_events+=1
                locked=True;target=0;reason='observed_data_gap_exit'
            elif locked or not np.isfinite(noise[i]) or not np.isfinite(prevclose):
                target=0;reason='unavailable_prior_history'
            else:
                target=1 if c[i]>max(upper[i],vwap[i]) else (-1 if c[i]<min(lower[i],vwap[i]) else 0)
                reason='halfhour_signal'
            targets[i]=target
            pending=(i+2,target,reason,i)
    if q:unresolved=True
    net_before_carry=cash-1 if not unresolved else np.nan
    # Independent cashflow identity: round-trip ledger cash versus holdings mark-to-market at every fill.
    independent_gross=0.;qh=0.;last=None
    for t in trades:
        if last is not None:independent_gross+=qh*(t['price']-last)
        qh+=t['dq'];last=t['price']
    if not unresolved:
        assert abs(qh)<1e-12
        assert np.isclose(net_before_carry,independent_gross-fees,atol=2e-12),(net_before_carry,independent_gross,fees)
    borrow=max_short*.02/365
    return {'net_before_carry':float(net_before_carry),'gross':float(net_before_carry+fees),'fees':fees,'borrow':borrow,'turnover':turnover,'capital_minutes':capital_minutes,'max_short':max_short,'entries':entered,'quality_events':quality_events,'delayed_fills':delayed_fills,'unresolved':unresolved,'max_entry_gross':max_entry_gross,'trades':trades if record else []}

def stats(s,benchmark=None):
    s=pd.Series(s).astype(float);a=s.to_numpy();n=len(a)
    if n<2 or not np.isfinite(a).all():return {'n':n,'invalid':True}
    sd=a.std(ddof=1);fit=sm.OLS(a,np.ones((n,1))).fit(cov_type='HAC',cov_kwds={'maxlags':5})
    wealth=np.r_[1,np.cumprod(1+a)];dd=wealth/np.maximum.accumulate(wealth)-1
    z=float(fit.tvalues[0]);p=float(norm.sf(z));out={'n':n,'annual_mean':float(a.mean()*252),'annual_vol':float(sd*np.sqrt(252)),'sharpe':float(a.mean()/sd*np.sqrt(252)) if sd else None,'cagr':float(wealth[-1]**(252/n)-1),'max_drawdown':float(dd.min()),'worst_day':float(a.min()),'best_day':float(a.max()),'hac_t':z,'one_sided_p':p,'bonferroni7_p':min(1,7*p)}
    rng=np.random.default_rng(20261003);ss=[];block=5
    for _ in range(2000):
        ii=(rng.integers(0,n,size=(n+block-1)//block)[:,None]+np.arange(block))%n;b=a[ii.ravel()[:n]]
        if b.std(ddof=1)>0:ss.append(b.mean()/b.std(ddof=1)*np.sqrt(252))
    out['sharpe_ci95']=np.quantile(ss,[.025,.975]).tolist()
    if benchmark is not None:
        x=np.asarray(benchmark,float);f=sm.OLS(a,sm.add_constant(x)).fit(cov_type='HAC',cov_kwds={'maxlags':5})
        out.update(alpha_ann=float(f.params[0]*252),alpha_hac_t=float(f.tvalues[0]),beta=float(f.params[1]))
    return out

def main():
    assert hashlib.sha256((HERE/'PROTOCOL.json').read_bytes()).hexdigest()==(HERE/'PROTOCOL.sha256').read_text().strip()
    daily,mats,noise,prefix,vwap=load();dates=daily.index
    output=[];ledger=[]
    for j,date in enumerate(dates):
        if date<pd.Timestamp('2015-01-01') or date>pd.Timestamp('2026-10-02'):continue
        common={'date':str(date.date()),'calendar_excluded':excluded(date),'rf_lagged':float(daily.rf_lagged.iloc[j]),'benchmark_total':float(daily.benchmark_total.iloc[j]),'missing_minutes':int((~np.isfinite(mats['o'][j])).sum())}
        for bp in [1,3]:
            r=simulate_day(mats['o'][j],mats['c'][j],noise[j],prefix[j],vwap[j],float(daily.c.iloc[j-1]),bp,record=bp==1) if not excluded(date) else {'net_before_carry':0.,'gross':0.,'fees':0.,'borrow':0.,'turnover':0.,'capital_minutes':0.,'max_short':0.,'entries':0,'quality_events':0,'delayed_fills':0,'unresolved':False,'max_entry_gross':0.,'trades':[]}
            funding=daily.rf_annual_lagged.iloc[j]/365*r['capital_minutes']/1440
            r.update(funding=float(funding),excess=float(r['net_before_carry']-r['borrow']-funding))
            if bp==1:
                ledger.extend([dict(date=str(date.date()),**t) for t in r.pop('trades')]);common.update(r)
            else:
                r.pop('trades');common.update(stress_excess=r['excess'],stress_fees=r['fees'])
        common['zero_interest_excess']=common['net_before_carry']-common['borrow']-common['rf_lagged']
        output.append(common)
    frame=pd.DataFrame(output).set_index('date');frame.index=pd.to_datetime(frame.index)
    (HERE/'daily.json').write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    (HERE/'ledger.json').write_text(json.dumps(ledger,indent=2,allow_nan=False)+'\n')
    periods={'development':('2015-01-01','2021-12-31'),'validation':('2022-01-01','2023-12-31'),'historical_holdout':('2024-01-01','2026-10-02'),'post_revision_descriptive':('2025-09-23','2026-10-02'),'full':('2015-01-01','2026-10-02')}
    results={}
    for name,(start,end) in periods.items():
        f=frame.loc[start:end];b=f.benchmark_total-f.rf_lagged
        results[name]={'base':stats(f.excess,b),'stress3bp':stats(f.stress_excess,b),'zero_interest_account':stats(f.zero_interest_excess,b),'trading_days':int((f.entries>0).sum()),'entries':int(f.entries.sum()),'turnover_per_year':float(f.turnover.mean()*252),'mean_borrow_bp':float(f.borrow.mean()*1e4),'mean_funding_bp':float(f.funding.mean()*1e4),'calendar_excluded':int(f.calendar_excluded.sum()),'quality_events':int(f.quality_events.sum()),'unresolved':int(f.unresolved.sum())}
    results['by_year']={str(y):stats(g.excess) for y,g in frame.groupby(frame.index.year)}
    results['verification']={'cashflow_vs_holdings_identity':'PASS every resolved day','max_entry_gross':float(frame.max_entry_gross.max()),'unresolved_sessions':frame.index[frame.unresolved].strftime('%Y-%m-%d').tolist(),'delayed_fill_count':int(frame.delayed_fills.sum()),'quality_events':int(frame.quality_events.sum()),'missing_minute_sessions':int((frame.missing_minutes>0).sum()),'protocol_sha256':(HERE/'PROTOCOL.sha256').read_text().strip(),'source_data_last':'2026-10-02','rf_source':'../sectors/data/DGS3MO.csv','rf_convention':'lagged annualyield; timeweightedcapital opportunitycost'}
    (HERE/'results.json').write_text(json.dumps(results,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in results.items() if k not in ['by_year']},indent=2))
if __name__=='__main__':main()
