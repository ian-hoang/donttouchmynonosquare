"""Paired event-versus-placebo summaries; no parameter selection or OOS."""
import json
import numpy as np
import pandas as pd
from data import HERE
from backtest import clean, PRIVATE

PARAMS=['signal','strategy','bucket','delay','otm','haircut','horizon']


def cluster_interval(frame,seed=2817):
    groups=[g['edge'].to_numpy() for _,g in frame.groupby('ticker')]
    if len(groups)<2:return [None,None]
    rng=np.random.default_rng(seed)
    estimates=[]
    for _ in range(4000):
        ix=rng.integers(0,len(groups),len(groups))
        estimates.append(np.concatenate([groups[i] for i in ix]).mean())
    return np.quantile(estimates,[.025,.975]).tolist()


def main():
    p=PRIVATE/'observations.json'
    if not p.exists():p=HERE/'observations.json'
    raw=json.loads(p.read_text())
    df=pd.DataFrame(raw)
    if df.empty:
        (HERE/'summary.json').write_text(json.dumps({'status':'no usable option marks'}))
        return
    # ATM long-call OTM sensitivity is irrelevant: avoid reporting duplicates.
    df=df[(df.strategy!='long_call')|(df.otm==.05)]
    ev=df[df.role=='event'].copy()
    controls=(df[df.role=='control'].groupby(PARAMS+['event_id'],dropna=False)
              .agg(control_net=('net','mean'),control_gross=('gross','mean'),n_controls=('net','size')).reset_index())
    paired=ev.merge(controls,on=PARAMS+['event_id'],how='inner')
    paired['edge']=paired.net-paired.control_net
    paired['gross_edge']=paired.gross-paired.control_gross
    summaries=[]
    for key,g in ev.groupby(PARAMS):
        params=dict(zip(PARAMS,key))
        match=paired.copy()
        for p,v in params.items():match=match[match[p]==v]
        result=dict(params,n_events=len(g),n_issuers=g.ticker.nunique(),net_mean=g.net.mean(),gross_mean=g.gross.mean(),
            net_median=g.net.median(),win_rate=(g.net>0).mean(),min_event=g.net.min(),max_event=g.net.max(),
            mean_return_on_capital=g.return_on_capital.mean(),n_paired=len(match),
            paired_issuers=match.ticker.nunique(),mean_edge=match.edge.mean(),gross_edge=match.gross_edge.mean(),
            control_net_mean=match.control_net.mean(),paired_event_net_mean=match.net.mean(),
            min_controls=int(match.n_controls.min()) if len(match) else 0)
        is_base=params['bucket']=='3-6m' and params['delay']==2 and params['otm']==.05 and params['haircut']==.05
        if is_base and len(match):
            result['cluster_bootstrap_95']=cluster_interval(match)
            result['event_details']=match[['ticker','filing_date','net','control_net','edge','n_controls']].to_dict('records')
            result['leave_one_issuer_out_edge_range']=[
                min(match[match.ticker!=t].edge.mean() for t in match.ticker.unique()),
                max(match[match.ticker!=t].edge.mean() for t in match.ticker.unique())] if match.ticker.nunique()>1 else [None,None]
        summaries.append(result)
    manifest=json.loads((HERE/'run_manifest.json').read_text())
    headline=[s for s in summaries if s['bucket']=='3-6m' and s['delay']==2 and s['otm']==.05 and s['haircut']==.05 and s['horizon']=='21']
    base=paired[(paired.bucket=='3-6m')&(paired.delay==2)&(paired.otm==.05)&(paired.haircut==.05)]
    balanced=[]
    for signal,g in base.groupby('signal'):
        sets=[set(g[g.horizon==h].event_id) for h in ['21','42','63']]
        ids=set.intersection(*sets)
        for horizon in ['21','42','63']:
            gg=g[(g.horizon==horizon)&g.event_id.isin(ids)]
            balanced.append(dict(signal=signal,horizon=horizon,n_paired=len(gg),
                                 mean_edge=gg.edge.mean(),net_mean=gg.net.mean()))
    result={'method':'development-only matched event study; no OOS, no annualized Sharpe',
            'qualified_events':{signal:sum(e['signal']==signal for e in manifest['events']) for signal in ['liquidity','departures','credit']},
            'headline':headline,'balanced_21_42_63':balanced,'all_configurations':summaries,
            'observed_parameter_horizon_cells':len(summaries),
            'limitations':['Option trade closes are not executable bid/ask quotes',
                'Strict freshness causes selection and missingness; n varies by horizon and parameters',
                'Different ordinary dates have different market/earnings conditions',
                'AI tags are retrospective and exact historical vendor availability is unknown',
                'Synthetic-stock parity assumes fixed 4% rate, no dividends, no early assignment',
                'Expiry results use fresh last-trade marks on expiry session, not independently observed settlement',
                'No outcomes after 2025-12-31; late events are censored',
                'Small issuer counts make confidence intervals unreliable, particularly one-issuer credit signal',
                'No multiplicity-adjusted significance claim; shared repo contains prior unrelated scans']}
    (HERE/'summary.json').write_text(json.dumps(clean(result),indent=2))
    print(json.dumps(clean({'qualified_events':result['qualified_events'],'headline':headline}),indent=2))


if __name__=='__main__':main()
