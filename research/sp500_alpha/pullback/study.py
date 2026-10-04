"""One predeclared SPY pullback rule; actual fixed-share cash accounting."""
from pathlib import Path
import hashlib,json,math
import numpy as np
import pandas as pd
import statsmodels.api as sm

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'sectors'/'data'
TZ='America/New_York'

def early_close(d):
    if (d.month,d.day) in [(7,3),(12,24)]:return True
    return d.month==11 and d.weekday()==4 and 23<=d.day<=29

def load():
    j=json.loads((SOURCE/'SPY.json').read_text())['chart']['result'][0]
    if j.get('events',{}).get('splits'):raise ValueError('SPY split requires extra ledger logic')
    df=pd.DataFrame(j['indicators']['quote'][0])
    df['date']=pd.to_datetime(j['timestamp'],unit='s',utc=True).tz_convert(TZ).tz_localize(None).normalize()
    df['adjusted']=j['indicators']['adjclose'][0]['adjclose'];df=df.set_index('date').sort_index()
    div={pd.Timestamp(v['date'],unit='s',tz='UTC').tz_convert(TZ).tz_localize(None).normalize():v['amount'] for v in j.get('events',{}).get('dividends',{}).values()}
    df['dividend']=pd.Series(div).reindex(df.index).fillna(0)
    if df.index.has_duplicates or df[['open','close','adjusted']].isna().any().any():raise ValueError('Missing/duplicate required price')
    if (df[['open','close','adjusted']]<=0).any().any():raise ValueError('Nonpositive price')
    df['underlying_total_return']=(df.close+df.dividend)/df.close.shift(1)-1
    rate=pd.read_csv(SOURCE/'DGS3MO.csv',index_col=0,parse_dates=True).iloc[:,0]
    rate=pd.to_numeric(rate,errors='coerce').dropna()/100
    prev=df.index.to_series().shift(1)
    df['previous_date']=prev
    cut=prev-pd.Timedelta(days=1)
    df['rf']=[float(rate.loc[:c].iloc[-1]) if pd.notna(c) and len(rate.loc[:c]) else np.nan for c in cut]
    opens=pd.DatetimeIndex(df.index+pd.Timedelta(hours=9,minutes=30)).tz_localize(TZ).tz_convert('UTC')
    closes=pd.DatetimeIndex([d+pd.Timedelta(hours=13 if early_close(d) else 16) for d in df.index]).tz_localize(TZ).tz_convert('UTC')
    prevcloses=pd.Series(closes,index=df.index).shift(1)
    df['overnight_days']=[(a-b).total_seconds()/86400 if pd.notna(b) else np.nan for a,b in zip(opens,prevcloses)]
    df['intraday_days']=(closes-opens).total_seconds()/86400
    df['full_days']=df.overnight_days+df.intraday_days
    return df

def indicators(df):
    z=df.copy();ret=z.adjusted.pct_change()
    z['three_return']=z.adjusted/z.adjusted.shift(3)-1
    z['vol20']=ret.shift(1).rolling(20,min_periods=20).std()
    z['sma200']=z.adjusted.rolling(200,min_periods=200).mean()
    z['sma5']=z.adjusted.rolling(5,min_periods=5).mean()
    z['entry_signal']=(z.three_return < -1.5*z.vol20)&(z.adjusted>z.sma200)
    z['exit_signal']=z.adjusted>=z.sma5
    return z

def simulate(full,cost_bps=1,buyhold=False):
    df=indicators(full).loc['2005-01-01':].copy();cash=1.;q=0.;prevnav=1.;pending=None;held=0;trades=[];active_trade=None;rows=[]
    c=cost_bps/10000
    for i,(d,r) in enumerate(df.iterrows()):
        prev_cash=cash;prevq=q;fee=0.;action='none';div_credit=prevq*r.dividend
        cash*=math.exp(r.rf*r.overnight_days/365)
        overnight_interest=cash-prev_cash
        cash+=div_credit
        if (buyhold and i==0) or pending=='entry':
            if q!=0:raise AssertionError('Overlapping position')
            q=cash/(r.open*(1+c));fee=q*r.open*c;cash-=q*r.open+fee;held=0;action='entry'
            active_trade={'entry_date':str(d.date()),'entry_open':float(r.open),'shares':float(q),'entry_fee':float(fee),'dividends':0.,'held_sessions':0}
            pending=None
        elif pending=='exit':
            fee=q*r.open*c;cash+=q*r.open-fee;action='exit'
            active_trade.update({'exit_date':str(d.date()),'exit_open':float(r.open),'exit_fee':float(fee),'exit_reason':exit_reason})
            active_trade['dividends']+=float(div_credit)
            active_trade['security_net_pnl']=q*(r.open-active_trade['entry_open'])+active_trade['dividends']-active_trade['entry_fee']-fee
            trades.append(active_trade);active_trade=None;q=0.;pending=None;held=0
        if q>0:
            held+=1;active_trade['held_sessions']=held
            # Entry at an ex-date open is not dividend entitled.
            active_trade['dividends']+=float(div_credit)
        midcash=cash;cash*=math.exp(r.rf*r.intraday_days/365);intraday_interest=cash-midcash
        nav=cash+q*r.close
        total=nav/prevnav-1;cashret=math.expm1(r.rf*r.full_days/365);excess=total-cashret
        if abs(excess)<1e-14:excess=0.
        if not buyhold:
            if q>0 and (r.exit_signal or held>=5):
                pending='exit';exit_reason='sma5' if r.exit_signal else 'max5'
            elif q==0 and r.entry_signal:pending='entry'
        if cash < -1e-10:raise AssertionError('Negative cash/leverage')
        rows.append({'date':str(d.date()),'nav':nav,'cash':cash,'shares':q,'previous_shares':prevq,'position_fraction_close':q*r.close/nav,'return':total,'cash_return':cashret,'excess':excess,'fees':fee,'dividend_cash':div_credit,'overnight_cash_interest':overnight_interest,'intraday_cash_interest':intraday_interest,'held_sessions':held,'action':action,'pending_next_open':pending,'underlying_excess':r.underlying_total_return-cashret,'open':float(r.open),'close':float(r.close),'rf':float(r.rf),'overnight_days':float(r.overnight_days),'intraday_days':float(r.intraday_days),'entry_signal':bool(r.entry_signal),'exit_signal':bool(r.exit_signal)})
        prevnav=nav
    if active_trade:
        active_trade.update({'status':'open_marked_at_final_close','mark_date':str(df.index[-1].date()),'mark_close':float(df.close.iloc[-1]),'pending_next_open':pending,'security_net_pnl_marked':q*(df.close.iloc[-1]-active_trade['entry_open'])+active_trade['dividends']-active_trade['entry_fee']})
    return pd.DataFrame(rows).set_index('date'),trades,active_trade

def stationary_ci(a):
    rng=np.random.default_rng(731);a=np.asarray(a);n=len(a);vals=[]
    for _ in range(2000):
        inds=[]
        while len(inds)<n:
            start=int(rng.integers(n));length=int(rng.geometric(.1));inds.extend(((start+np.arange(length))%n).tolist())
        b=a[np.asarray(inds[:n])];sd=np.std(b,ddof=1)
        if sd>0:vals.append(float(np.mean(b)/sd*np.sqrt(252)))
    return np.quantile(vals,[.025,.975]).tolist()

def stats(df,bootstrap=False):
    x=df.excess.to_numpy();n=len(x);vol=np.std(x,ddof=1);fit=sm.OLS(x,np.ones((n,1))).fit(cov_type='HAC',cov_kwds={'maxlags':5})
    regression=sm.OLS(x,sm.add_constant(df.underlying_excess)).fit(cov_type='HAC',cov_kwds={'maxlags':5})
    wealth=np.cumprod(1+df['return'].to_numpy());peaks=np.maximum.accumulate(np.r_[1,wealth])[1:]
    out={'days':n,'entry_count':int((df.action=='entry').sum()),'closed_trade_count':int((df.action=='exit').sum()),'invested_close_sessions':int((df.shares>0).sum()),'mean_close_exposure':float(df.position_fraction_close.mean()),'mean_daily_excess_bps':float(np.mean(x)*10000),'arithmetic_annual_excess':float(np.mean(x)*252),'annual_excess_vol':float(vol*np.sqrt(252)),'excess_sharpe':float(np.mean(x)/vol*np.sqrt(252)) if vol>0 else None,'total_wealth_cagr':float(wealth[-1]**(252/n)-1),'total_wealth_max_drawdown':float(np.min(wealth/peaks-1)),'hac_mean_t':float(fit.tvalues[0]),'hac_mean_p':float(fit.pvalues[0]),'market_beta':float(regression.params.iloc[1]),'market_alpha_annual':float(regression.params.iloc[0]*252),'market_alpha_hac_t':float(regression.tvalues.iloc[0]),'market_alpha_hac_p':float(regression.pvalues.iloc[0]),'total_fees_initial_capital_units':float(df.fees.sum())}
    if bootstrap:out['stationary_block_sharpe_95ci']=stationary_ci(x)
    # Fully flat years have undefined t-statistics and Sharpe, not zero-risk alpha.
    out={k:(None if isinstance(v,float) and not math.isfinite(v) else v) for k,v in out.items()}
    return out

def verify(full,base,trades,open_trade):
    # Independent dollar ledger using recorded positions and actions, not trading signals.
    wealth=1.;q=0.;cash=1.;errors=[];flatmax=0.;maxlever=0.;closedpnl=[]
    for d,r in base.iterrows():
        qprev=q;navprev=wealth
        cash*=math.exp(r.rf*r.overnight_days/365)
        cash+=r.dividend_cash
        change=r.shares-q
        cash-=change*r.open+r.fees
        q=r.shares
        cash*=math.exp(r.rf*r.intraday_days/365)
        wealth=cash+q*r.close
        errors.append(abs(wealth-r.nav))
        if qprev==0 and q==0:flatmax=max(flatmax,abs(r.excess))
        if r.action=='entry':maxlever=max(maxlever,q*r.open/(navprev*math.exp(r.rf*r.overnight_days/365)))
    for t in trades:
        entry=pd.Timestamp(t['entry_date']);exit=pd.Timestamp(t['exit_date'])
        div=full.loc[(full.index>entry)&(full.index<=exit),'dividend'].sum()*t['shares']
        independent=t['shares']*(t['exit_open']-t['entry_open'])+div-t['entry_fee']-t['exit_fee']
        closedpnl.append(abs(independent-t['security_net_pnl']))
        assert 1<=t['held_sessions']<=5
    assert max(errors)<1e-10 and max(closedpnl,default=0)<1e-10 and flatmax<1e-12 and maxlever<=1+1e-10
    prefix=[]
    for cutoff in ['2011-12-30','2016-12-30','2021-12-31','2023-12-29','2025-12-31']:
        trial,_,_=simulate(full.loc[:cutoff],1)
        reference=base.loc[:cutoff]
        assert len(trial)==len(reference)
        err=float(np.max(np.abs(trial[['nav','shares','excess']].to_numpy()-reference[['nav','shares','excess']].to_numpy())))
        assert err<1e-12
        prefix.append({'cutoff':cutoff,'max_difference':err})
    return {'independent_ledger_max_nav_difference':max(errors),'independent_completed_trade_cashflow_max_difference':max(closedpnl,default=0),'fully_flat_day_max_absolute_excess':flatmax,'max_entry_notional_fraction':maxlever,'prefix_replay':prefix,'held_session_count_range':[min([t['held_sessions'] for t in trades],default=0),max([t['held_sessions'] for t in trades],default=0)],'completed_trades':len(trades),'final_open_trade':open_trade,'dividend_approximation':'Cash credited ex-date instead of later actual payment date; no dividend paid to openingex-datebuyers; dividendpaid to pre-ex-date holders exitingex-dateopen.'}

def main():
    protocol=json.loads((HERE/'PROTOCOL.json').read_text());full=load();base,trades,opened=simulate(full,1);stress,_,_=simulate(full,3);benchmark,_,_=simulate(full,1,buyhold=True)
    audit=verify(full,base,trades,opened)
    result={'selection_context':protocol['selection_context'],'audit':audit,'final_pending_next_open':base.pending_next_open.iloc[-1],'periods':{},'years':{}}
    for period,(a,b) in protocol['periods'].items():
        result['periods'][period]={'base':stats(base.loc[a:b],True),'stress':stats(stress.loc[a:b]),'buyhold':stats(benchmark.loc[a:b])}
    for y in range(2005,2027):result['years'][str(y)]=stats(base.loc[f'{y}-01-01':f'{y}-12-31'])
    h=result['periods']['holdout'];v=result['periods']['validation']
    result['passes_single_hypothesis_gate']=bool(v['base']['arithmetic_annual_excess']>0 and h['base']['excess_sharpe']>=.75 and h['stress']['arithmetic_annual_excess']>0 and h['base']['hac_mean_p']<.05)
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [SOURCE/'SPY.json',SOURCE/'DGS3MO.csv',HERE/'PROTOCOL.json',HERE/'study.py']}
    (HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');(HERE/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');(HERE/'verification.json').write_text(json.dumps(audit,indent=2)+'\n');(HERE/'trades.json').write_text(json.dumps({'closed':trades,'open':opened},indent=2)+'\n')
    daily=base.copy();daily['stress_excess']=stress.excess;daily['buyhold_excess']=benchmark.excess;daily['buyhold_return']=benchmark['return'];(HERE/'daily.json').write_text(daily.reset_index().to_json(orient='records',double_precision=12))
    lines=['ONE FIXED SPY PULLBACK IN UPTREND',protocol['selection_context'],'Data: Yahoo SPY daily unadjusted OHLC and dividend cashflows; adjusted close used only for causal signals. Lagged DGS3MO cash benchmark.','Base 1 bp per side; stress 3 bp per side. No shorts or leverage. All flat sessions retained.','Entry at the next open; fixed shares; ex-date holders get dividend cash. Exit at the next open after SMA5 recovery or the fifth held close. No forced final liquidation.','']
    for p,r in result['periods'].items():
        b=r['base'];lines.append(f"{p}: excess Sharpe {b['excess_sharpe']:.4f}; stress {r['stress']['excess_sharpe']:.4f}; annual excess {b['arithmetic_annual_excess']:.3%}; actual wealth CAGR {b['total_wealth_cagr']:.3%}; max drawdown {b['total_wealth_max_drawdown']:.3%}; invested {b['invested_close_sessions']}/{b['days']}; entries {b['entry_count']}; exits {b['closed_trade_count']}; HAC mean p {b['hac_mean_p']:.4f}; beta {b['market_beta']:.4f}; annual alpha {b['market_alpha_annual']:.3%}; alpha HAC p {b['market_alpha_hac_p']:.4f}; SPY buy-hold excess Sharpe {r['buyhold']['excess_sharpe']:.4f}")
        lines.append('Stationary bootstrap 95% Sharpe CI '+str(b['stationary_block_sharpe_95ci']))
    lines+=['','Passes single-hypothesis gate: '+str(result['passes_single_hypothesis_gate']),'Broader search multiplicity correction still required; result is not independent of selection of this eighth family.','Final open position: '+str(opened),'Final pending next-open action: '+str(result['final_pending_next_open']),'Independent cash ledger max difference '+str(audit['independent_ledger_max_nav_difference']),'Prefix causality replay passed five fixed dates with zero difference.','Dividends credited ex-date instead of actual payment date, so this remains a standard total-return accounting approximation.','Daily open prices plus costs are modeled execution, not NBBO-confirmed institutional fills or capacity.']
    (HERE/'REPORT.txt').write_text('\n'.join(lines)+'\n');print('\n'.join(lines))
if __name__=='__main__':main()
