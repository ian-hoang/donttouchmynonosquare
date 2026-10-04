"""Timing/cash-cost audit requested by independent root review; no new signals."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
from statsmodels.stats.multitest import multipletests
import run

HERE=Path(__file__).resolve().parent

def main():
    df=pd.read_json(HERE/'daily.json').set_index('date');df.index=pd.to_datetime(df.index)
    frozen=json.loads((HERE/'results.json').read_text())
    protocol=json.loads((HERE/'PROTOCOL.json').read_text())
    # Archive actual first-pass results unchanged before any audit sensitivities.
    for name in ['daily.json','results.json','REPORT.txt']:
        dest=HERE/('frozen_'+name)
        if not dest.exists():dest.write_bytes((HERE/name).read_bytes())
    noncal=~df.calendar_excluded.astype(bool)
    needs=['open','signal_close']
    signal_valid=df[needs].notna().all(axis=1)&(df[needs]>0).all(axis=1)&noncal
    momentum_valid=df[['first_close','prior_close']].notna().all(axis=1)&(df[['first_close','prior_close']]>0).all(axis=1)&noncal
    moves=(df.signal_close/df.open-1).loc[signal_valid]
    df['prior60_vol_corrected']=moves.shift(1).rolling(60,min_periods=60).std().reindex(df.index)
    oldpos={s:df[s].copy() for s in ['momentum','extreme_reversal','always_long']}
    df['momentum']=np.sign(df.first_return).where(momentum_valid,0).fillna(0)
    df['extreme_reversal']=(-np.sign(df.day_move)).where(signal_valid&(df.day_move.abs()>2*df.prior60_vol_corrected),0).fillna(0)
    df['always_long']=noncal.astype(float)
    price_missing=df[['entry','entry_delay','exit']].isna().any(axis=1)| (df[['entry','entry_delay','exit']]<=0).any(axis=1)
    unresolved={s:[str(x.date()) for x in df.index[(df[s]!=0)&price_missing]] for s in ['momentum','extreme_reversal','always_long']}
    if any(unresolved.values()):
        (HERE/'unresolved_execution.json').write_text(json.dumps(unresolved,indent=2))
        raise ValueError('Unknown execution outcomes: refusing to mark positioned sessions flat')
    rate_path=HERE.parent/'sectors'/'data'/'DGS3MO.csv'
    rf=pd.read_csv(rate_path,index_col=0,parse_dates=True).iloc[:,0]
    rf=pd.to_numeric(rf,errors='coerce').sort_index()/100
    # The published observation from the previous calendar day or earlier only.
    grid=pd.date_range(df.index.min()-pd.Timedelta(days=7),df.index.max(),freq='D')
    rf=rf.reindex(rf.index.union(grid)).sort_index().ffill().reindex(grid).shift(1).reindex(df.index)
    if rf.isna().any():raise ValueError('Missing lagged cash opportunity rate')
    df['lagged_rf']=rf
    # Match hand-computed round trips, zero exposure, and minimum borrow-day cost.
    positions=pd.Series([1.,-1.,0.]);entry=pd.Series([100.,100.,np.nan]);exit=pd.Series([110.,90.,np.nan])
    actual=run.pnl(positions,entry,exit,1).to_numpy()
    expected=np.array([.1-.00021,.1-.00019-.01/360,0.])
    assert np.allclose(actual,expected,atol=1e-14)
    audit={'unresolved_execution_dates':unresolved,'noncalendar_original_invalid_dates':[str(x.date()) for x in df.index[noncal&~df.data_valid.astype(bool)]], 'position_changes':{s:int((df[s]!=oldpos[s]).sum()) for s in oldpos},'cash_source_sha256':hashlib.sha256(rate_path.read_bytes()).hexdigest(),'cash_rule':'Lagged DGS3MO annual yield *28/(1440*365) on all active notional;27minutes in delayed-entry sensitivity. Original cash-zero P&L Sharpe is not an excess-return Sharpe.','bootstrap_implementation':'Original first run used fixed circular10-day blocks despite protocol saying stationary; corrected results use stationary geometric blocks mean10, matching protocol. No signal/configuration changed on outcomes.','accounting_assertions':'long,short,flat hand-calculated cashflows passed'}
    results={'audit':audit,'strategies':{}}
    for s in ['momentum','extreme_reversal','always_long']:
        pos=df[s];cash=pos.abs()*rf*28/(1440*365)
        df[s+'_corrected_net']=run.pnl(pos,df.entry,df.exit,1)-cash
        df[s+'_corrected_stress']=run.pnl(pos,df.entry,df.exit,3)-cash
        df[s+'_corrected_delay']=run.pnl(pos,df.entry_delay,df.exit,1)-pos.abs()*rf*27/(1440*365)
        df[s+'_borrow2pct']=df[s+'_corrected_net']-(pos<0).astype(float)*.01/360
        sr={}
        for period,(a,b) in protocol['periods'].items():
            z=df.loc[a:b];sr[period]={}
            for kind in ['corrected_net','corrected_stress','corrected_delay','borrow2pct']:
                sr[period][kind]=run.metrics(z[s+'_'+kind],z.market_ret,z[s],boot=(kind=='corrected_net'))
        sr['years']={str(y):run.metrics(g[s+'_corrected_net'],g.market_ret,g[s]) for y,g in df.groupby(df.index.year)}
        results['strategies'][s]=sr
    for period in protocol['periods']:
        ps=[results['strategies'][s][period]['corrected_net']['hac_mean_p'] for s in ['momentum','extreme_reversal']]
        for s,p in zip(['momentum','extreme_reversal'],multipletests(ps,method='holm')[1]):results['strategies'][s][period]['corrected_net']['holm_two_hypothesis_p']=float(p)
    for s in ['momentum','extreme_reversal']:
        r=results['strategies'][s];h=r['holdout']
        r['passes_frozen_gate_on_corrected_returns']=bool(r['validation']['corrected_net']['mean_bps_daily']>0 and h['corrected_net']['sharpe']>=.75 and h['corrected_stress']['mean_bps_daily']>0 and h['corrected_delay']['mean_bps_daily']>0 and h['corrected_net']['holm_two_hypothesis_p']<.05)
    (HERE/'verification.json').write_text(json.dumps(audit,indent=2)+'\n')
    (HERE/'results_corrected.json').write_text(json.dumps(results,indent=2,allow_nan=False)+'\n')
    z=df.reset_index();z['date']=z.date.dt.strftime('%Y-%m-%d');(HERE/'daily_corrected.json').write_text(z.to_json(orient='records',double_precision=12))
    lines=['SPY INTRADAY: INDEPENDENT TIMING/CASH AUDIT',json.dumps(audit,indent=2),'']
    for s,r in results['strategies'].items():
        lines.append(s.upper())
        for period in protocol['periods']:
            h=r[period];n=h['corrected_net']
            lines.append(f"{period}: corrected base excess-P&L Sharpe {n['sharpe']:.4f}; stress {h['corrected_stress']['sharpe']:.4f}; delayed {h['corrected_delay']['sharpe']:.4f}; borrow2% {h['borrow2pct']['sharpe']:.4f}; annual arithmetic excess P&L {n['arithmetic_annual_return']:.3%}; compounded excess P&L annualized {n['cagr']:.3%}; excess-P&L drawdown {n['max_drawdown']:.3%}; active {n['active_days']}/{n['days']}")
        lines.append('Holdout stationary-bootstrap95%SharpeCI '+str(r['holdout']['corrected_net']['block_bootstrap_sharpe_95ci']))
        if s!='always_long':lines.append('Passes frozen gate on corrected returns: '+str(r['passes_frozen_gate_on_corrected_returns']))
    lines+=['','No quotation-based fill/capacity validation. Fixed return signs/windows/thresholds; no search after outcomes.','Compounded excess P&L is a statistic of the trading overlay, not actual total portfolio wealth including idle cash yield.','Borrow2% sensitivity is an additional assumption, not a repair of the frozen1% assumption.']
    (HERE/'REPORT_corrected.txt').write_text('\n'.join(lines)+'\n');print('\n'.join(lines))
if __name__=='__main__':main()
