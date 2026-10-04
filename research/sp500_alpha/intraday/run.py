"""Two frozen SPY intraday hypotheses; no parameter search or network requests."""
from pathlib import Path
import gzip, hashlib, json, math
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

HERE=Path(__file__).resolve().parent
TZ='America/New_York'
TIMES={'09:30':'open','09:59':'first_close','15:29':'signal_close','15:31':'entry','15:32':'entry_delay','15:59':'exit'}

def load(name):
    with gzip.open(HERE/'raw'/(name+'.json.gz'),'rt') as f:return json.load(f)['results']

def calendar_excluded(idx):
    # Deliberately conservative calendar rule frozen before return outcomes.
    out=(idx.month==7)&np.isin(idx.day,[2,3]) | ((idx.month==12)&(idx.day==24))
    for year in set(idx.year):
        thanksgiving=pd.date_range(f'{year}-11-01',f'{year}-11-30',freq='W-THU')[3]
        out|=(idx==thanksgiving+pd.Timedelta(days=1))
    return out

def prepare():
    daily=pd.DataFrame(load('daily'))
    daily['date']=pd.to_datetime(daily.t,unit='ms',utc=True).dt.tz_convert(TZ).dt.tz_localize(None).dt.normalize()
    daily=daily.set_index('date').sort_index()
    if daily.index.has_duplicates:raise ValueError('Duplicate daily bars')
    divs=load('dividends');splits=load('splits')
    if splits:raise ValueError('SPY split needs explicit dividend unit adjustment')
    div=pd.Series({pd.Timestamp(r['ex_dividend_date']):float(r['cash_amount']) for r in divs},dtype=float)
    daily['dividend']=div.reindex(daily.index).fillna(0)
    daily['prior_close']=daily.c.shift(1)
    daily['market_ret']=(daily.c+daily.dividend)/daily.prior_close-1
    out=[];rows=0
    for p in sorted((HERE/'raw').glob('minute_*.json.gz')):
        with gzip.open(p,'rt') as f:j=json.load(f)
        b=pd.DataFrame(j['results']);rows+=len(b)
        if not len(b):continue
        dt=pd.to_datetime(b.t,unit='ms',utc=True).dt.tz_convert(TZ)
        b['date']=dt.dt.tz_localize(None).dt.normalize();b['hhmm']=dt.dt.strftime('%H:%M')
        if b.t.duplicated().any():raise ValueError('Duplicate minute timestamp')
        b=b.loc[(b.hhmm>='09:30')&(b.hhmm<='15:59')]
        counts=b.groupby('date').size().rename('minute_count')
        z=pd.DataFrame(index=counts.index);z['minute_count']=counts
        for t,col in TIMES.items():
            key='c' if col.endswith('close') else 'o'
            z[col]=b.loc[b.hhmm==t].set_index('date')[key]
        out.append(z)
    bars=pd.concat(out).sort_index()
    if bars.index.has_duplicates:raise ValueError('Duplicate session')
    df=daily.join(bars,how='left').loc['2015-01-01':'2026-10-02'].copy()
    df['calendar_excluded']=calendar_excluded(df.index)
    df['data_valid']=(df[list(TIMES.values())].notna().all(axis=1)&(df[list(TIMES.values())]>0).all(axis=1)&(df.minute_count==390))
    df['eligible']=df.data_valid&~df.calendar_excluded
    df['first_return']=(df.first_close+df.dividend)/df.prior_close-1
    df['day_move']=df.signal_close/df.open-1
    valid_moves=df.loc[df.eligible,'day_move']
    df['prior60_vol']=valid_moves.shift(1).rolling(60,min_periods=60).std().reindex(df.index)
    df['momentum']=np.sign(df.first_return).where(df.eligible,0).fillna(0)
    df['extreme_reversal']=(-np.sign(df.day_move)).where(df.eligible&(df.day_move.abs()>2*df.prior60_vol),0).fillna(0)
    df['always_long']=df.eligible.astype(int)
    audit={'minute_rows':rows,'daily_sessions':len(df),'first_session':str(df.index.min().date()),'last_session':str(df.index.max().date()),'dividend_records':len(divs),'split_records':len(splits),'calendar_excluded_count':int(df.calendar_excluded.sum()),'data_invalid_count':int((~df.data_valid).sum()),'eligible_count':int(df.eligible.sum()),'missing_sessions':[str(d.date()) for d in df.index[~df.data_valid]],'excluded_dates':[str(d.date()) for d in df.index[df.calendar_excluded]],'protocol_sha256':hashlib.sha256((HERE/'PROTOCOL.json').read_bytes()).hexdigest()}
    return df,audit

def pnl(position,entry,exit,cost_bps):
    rel=(exit/entry-1).where(position!=0,0).fillna(0)
    gross=position*rel
    # Fees on opening and closing marked notional; one minimum borrow day per short.
    costs=(position.abs()*cost_bps/1e4*(2+rel)).fillna(0)+(position<0).astype(float)*0.01/360
    return gross-costs

def metrics(r,market,position,boot=False):
    r=np.asarray(r,dtype=float);market=np.asarray(market,dtype=float);position=np.asarray(position,dtype=float)
    n=len(r);std=np.std(r,ddof=1);sh=float(np.mean(r)/std*np.sqrt(252)) if std>0 else None
    equity=np.cumprod(1+r);peaks=np.maximum.accumulate(np.r_[1.,equity])[1:]
    fit=sm.OLS(r,np.ones((n,1))).fit(cov_type='HAC',cov_kwds={'maxlags':5})
    good=np.isfinite(market);reg=sm.OLS(r[good],sm.add_constant(market[good])).fit(cov_type='HAC',cov_kwds={'maxlags':5})
    d={'days':n,'active_days':int(np.count_nonzero(position)),'long_days':int(np.sum(position>0)),'short_days':int(np.sum(position<0)),'mean_bps_daily':float(np.mean(r)*1e4),'arithmetic_annual_return':float(np.mean(r)*252),'cagr':float(equity[-1]**(252/n)-1),'annual_vol':float(std*np.sqrt(252)),'sharpe':sh,'max_drawdown':float(np.min(equity/peaks-1)),'hac_mean_t':float(fit.tvalues[0]),'hac_mean_p':float(fit.pvalues[0]),'market_beta':float(reg.params[1]),'market_alpha_ann':float(reg.params[0]*252),'market_alpha_hac_t':float(reg.tvalues[0]),'net_position_mean':float(np.mean(position))}
    if boot:
        rng=np.random.default_rng(731);sharpes=[]
        for _ in range(2000):
            # Stationary bootstrap: geometric block lengths with mean 10 sessions.
            inds=[]
            while len(inds)<n:
                start=rng.integers(0,n);length=int(rng.geometric(.1))
                inds.extend(((start+np.arange(length))%n).tolist())
            inds=np.asarray(inds[:n])
            rr=r[inds];sd=np.std(rr,ddof=1)
            if sd>0:sharpes.append(np.mean(rr)/sd*np.sqrt(252))
        d['block_bootstrap_sharpe_95ci']=np.quantile(sharpes,[.025,.975]).tolist()
    return d

def main():
    protocol=json.loads((HERE/'PROTOCOL.json').read_text());df,audit=prepare();result={'audit':audit,'strategies':{}}
    for strategy in ['momentum','extreme_reversal','always_long']:
        pos=df[strategy]
        df[strategy+'_gross']=pnl(pos,df.entry,df.exit,0)+(pos<0).astype(float)*0.01/360
        df[strategy+'_net']=pnl(pos,df.entry,df.exit,1)
        df[strategy+'_stress']=pnl(pos,df.entry,df.exit,3)
        df[strategy+'_delay']=pnl(pos,df.entry_delay,df.exit,1)
        rs={}
        for period,(a,b) in protocol['periods'].items():
            part=df.loc[a:b];rs[period]={}
            for kind in ['gross','net','stress','delay']:
                rs[period][kind]=metrics(part[strategy+'_'+kind],part.market_ret,part[strategy],boot=(kind=='net'))
        rs['years']={str(y):metrics(g[strategy+'_net'],g.market_ret,g[strategy]) for y,g in df.groupby(df.index.year)}
        result['strategies'][strategy]=rs
    for period in protocol['periods']:
        adj=multipletests([result['strategies'][s][period]['net']['hac_mean_p'] for s in ['momentum','extreme_reversal']],method='holm')[1]
        for s,p in zip(['momentum','extreme_reversal'],adj):result['strategies'][s][period]['net']['holm_two_hypothesis_p']=float(p)
    for s in ['momentum','extreme_reversal']:
        res=result['strategies'][s];h=res['holdout']
        result['strategies'][s]['passes_frozen_gate']=bool(res['validation']['net']['mean_bps_daily']>0 and h['net']['sharpe']>=.75 and h['stress']['mean_bps_daily']>0 and h['delay']['mean_bps_daily']>0 and h['net']['holm_two_hypothesis_p']<.05)
    (HERE/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    z=df.reset_index().rename(columns={'index':'date'});z['date']=z['date'].dt.strftime('%Y-%m-%d')
    (HERE/'daily.json').write_text(z.to_json(orient='records',double_precision=12))
    lines=['SPY INTRADAY: TWO FROZEN SIGNALS','Source: Massive split-adjusted one-minute trade aggregates, 2015-01-02 to 2026-10-02.', 'Entry 15:31 minute open; exit 15:59 minute open. These are price proxies with assumed costs, not verified quote fills.', 'Net: 1bp per side plus one minimum day of 1% annualized borrow when short. Stress: 3bp per side. Cash yield excluded.','Every SPY daily session retained, including flat, excluded and missing-data days.','',json.dumps(audit,indent=2),'']
    for s in ['momentum','extreme_reversal','always_long']:
        lines.append(s.upper())
        for period in protocol['periods']:
            r=result['strategies'][s][period]
            lines.append(f"{period}: gross Sharpe {r['gross']['sharpe']:.3f}; base Sharpe {r['net']['sharpe']:.3f}; stress Sharpe {r['stress']['sharpe']:.3f}; +1min entry Sharpe {r['delay']['sharpe']:.3f}; base annual mean {r['net']['arithmetic_annual_return']:.2%}; active {r['net']['active_days']}/{r['net']['days']}; HAC p {r['net']['hac_mean_p']:.4f}")
        if s!='always_long':lines.append('Passes frozen research gate: '+str(result['strategies'][s]['passes_frozen_gate']))
        lines.append('Holdout base uncertainty: '+str(result['strategies'][s]['holdout']['net']['block_bootstrap_sharpe_95ci']))
        lines.append('')
    lines+=['No parameter fitting or selection performed. Both hypotheses reported irrespective of result.','Neither a replication of exact close-auction fills nor an institutional capacity study.','Late-session strategies at 1x have low absolute volatility and returns; leverage scales execution, financing, drawdown and tail risk.','Source paper: https://www.sciencedirect.com/science/article/pii/S0304405X18301351','Source data conventions: https://www.massive.com/docs/rest/stocks/aggregates/custom-bars']
    (HERE/'REPORT.txt').write_text('\n'.join(lines)+'\n');print('\n'.join(lines[-21:]))

if __name__=='__main__':main()
