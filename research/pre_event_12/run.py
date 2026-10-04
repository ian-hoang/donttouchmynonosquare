"""Frozen evaluation of two pre-event hypotheses and their declared variants."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from core import HERE,ROOT,event_return,file_hash,load_panel,portfolio,summarize
from collect import quote_key


def valid(q):
    return isinstance(q,dict) and 'error' not in q and q.get('bid',0)>0 and q.get('ask',0)>=q.get('bid',0)


def liquidity(row,quotes,cal):
    current=quotes.get(quote_key(row.ticker,row.entry_date,'signal'))
    lag=quotes.get(quote_key(row.ticker,row.signal_date,'signal'))
    i=cal.searchsorted(pd.Timestamp(row.entry_date))
    history=[quotes.get(quote_key(row.ticker,str(d.date()),'signal')) for d in cal[i-20:i]]
    history=[q for q in history if valid(q)]
    if not valid(current) or not valid(lag) or len(history)<15:return False
    depth=lambda q:q['bid']*q['bid_size']
    return (current['spread_fraction']<lag['spread_fraction'] and depth(current)>=depth(lag)
            and current['spread_fraction']<=np.median([q['spread_fraction'] for q in history])
            and depth(current)>=np.median([depth(q) for q in history]))


def freeze():
    files=[HERE/'SPECIFICATION.md',HERE/'core.py',HERE/'run.py',HERE/'prepare.py',
           HERE/'collect.py',HERE/'options_audit.py',HERE/'data/windows.csv',
           HERE/'data/quotes.json',HERE/'options_features.json',HERE/'events_confirmed.csv',
           HERE/'options_release_history.json']
    files += [ROOT/'data/cache/ai_washing/prices.parquet',ROOT/'data/cache/ai_washing/calendar.parquet',
              ROOT/'data/cache/world_cup/dividends_SPY.json']
    files += sorted(p for p in (ROOT/'data/cache/massive_grouped').glob('grouped_*.parquet') if int(p.stem.split('_')[-1])>=2020)
    manifest={str(p.relative_to(ROOT)):file_hash(p) for p in files}
    path=HERE/'data/frozen_manifest.json'
    if path.exists():
        existing=json.loads(path.read_text())
        if existing['sha256']!=manifest:raise RuntimeError('Frozen inputs/code changed; document repair before rerun')
    else:
        path.write_text(json.dumps({'created_utc':datetime.now(timezone.utc).isoformat(),'sha256':manifest},indent=2))
    return file_hash(path)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--period',choices=['screen','validation'],required=True);args=ap.parse_args()
    frozen_hash=freeze()
    cal,panel=load_panel()
    w=pd.read_csv(HERE/'data/windows.csv')
    features=pd.DataFrame(json.loads((HERE/'options_features.json').read_text()))
    features=features[['ticker','signal_date','iv30']].drop_duplicates(['ticker','signal_date'])
    w=w.merge(features,on=['ticker','signal_date'],how='left')
    quotes=json.loads((HERE/'data/quotes.json').read_text())
    w['liquidity_recovery']=[liquidity(r,quotes,cal) for r in w.itertuples()]
    thresholds={}
    for hold in [10,5]:
        a=w[w.hold_sessions.eq(hold)&w.period.eq('calibration')]
        thresholds[str(hold)]={}
        for signal,q in [('iv30',.8),('jackpot',.9)]:
            v=a[signal].dropna()
            thresholds[str(hold)][signal]={'n':len(v),'quantile':q,'value':float(v.quantile(q)) if len(v)>=10 else None}
    out=HERE/'outputs'/args.period;out.mkdir(parents=True,exist_ok=True)
    (out/'thresholds.json').write_text(json.dumps(thresholds,indent=2))
    outcomes=[]
    for row in w[w.period.eq(args.period)].itertuples():
        r=row._asdict()
        e=quotes.get(quote_key(row.ticker,row.entry_date,'entry'))
        x=quotes.get(quote_key(row.ticker,row.exit_date,'exit'))
        se=quotes.get(quote_key('SPY',row.entry_date,'entry'))
        sx=quotes.get(quote_key('SPY',row.exit_date,'exit'))
        if not valid(e):
            outcomes.append(r|{'status':'no_entry_quote'});continue
        if e['spread_fraction']>.002:
            outcomes.append(r|{'status':'entry_spread_above_20bp'});continue
        for mult in [1.,2.]:
            result=event_return(r,e,x if valid(x) else None,se if valid(se) else None,
                                sx if valid(sx) else None,panel,cost_multiplier=mult)
            result.update(cost_multiplier=mult,entry_ask_size=e['ask_size'],entry_timestamp_ns=e['timestamp_ns'],
                          exit_timestamp_ns=x['timestamp_ns'] if valid(x) else None,
                          exit_bid_size=x['bid_size'] if valid(x) else None)
            outcomes.append(r|result)
    allrows=pd.DataFrame(outcomes)
    allrows.to_csv(out/'all_events.csv',index=False)
    if allrows.status.str.startswith('unresolved').any():
        raise RuntimeError('Unresolved event exits/prices: see all_events.csv; no complete-case performance claim allowed')
    summary={'period':args.period,'frozen_manifest_sha256':frozen_hash,'thresholds':thresholds,
             'input_counts':w[w.period.eq(args.period)].groupby('hold_sessions').size().to_dict(),
             'status_counts':allrows.groupby(['hold_sessions','status']).size().astype(int).to_dict()}
    summary['status_counts']={str(k):v for k,v in summary['status_counts'].items()}
    tables=[]
    for hold in [10,5]:
        for strategy,feature in [('uncertainty','iv30'),('uncertainty_liquidity','iv30'),('jackpot','jackpot')]:
            threshold=thresholds[str(hold)][feature]['value']
            for mult in [1.,2.]:
                base=allrows[allrows.hold_sessions.eq(hold)&allrows.status.eq('ok')&allrows.cost_multiplier.eq(mult)].copy()
                base=base[base[feature].notna()]
                selected=base.iloc[:0].copy() if threshold is None else base[base[feature]>=threshold].copy()
                if strategy=='uncertainty_liquidity':selected=selected[selected.liquidity_recovery]
                selected['signal']=selected[feature]
                selected.to_csv(out/f'{strategy}_{hold}d_cost{int(mult)}_trades.csv',index=False)
                start='2024-01-01' if args.period=='screen' else '2025-01-01'
                end='2024-12-31' if args.period=='screen' else '2026-09-30'
                if not selected.empty:
                    end=str(max(pd.Timestamp(end),pd.to_datetime(selected.exit_date).max()).date())
                path,pstats=portfolio(selected,panel,start=start,end=end)
                path.to_csv(out/f'{strategy}_{hold}d_cost{int(mult)}_equity.csv')
                item={'strategy':strategy,'hold_sessions':hold,'cost_multiplier':mult,
                      'selected_net':summarize(selected),'selected_market_adjusted':summarize(selected,'market_adjusted_net'),
                      'selected_gross':summarize(selected,'gross'),'baseline_net':summarize(base),
                      'selected_beta_adjusted':summarize(selected.dropna(subset=['beta_adjusted_net']),'beta_adjusted_net'),
                      'baseline_market_adjusted':summarize(base,'market_adjusted_net'),
                      'tickers':int(selected.ticker.nunique()),'portfolio':pstats,
                      'years':{str(y):summarize(g) for y,g in selected.groupby(pd.to_datetime(selected.entry_date).dt.year)}}
                tables.append(item)
    summary['results']=tables
    (out/'summary.json').write_text(json.dumps(summary,indent=2,default=str,allow_nan=True))
    for r in tables:
        s=r['selected_net'];a=r['selected_market_adjusted'];p=r['portfolio']
        print(r['strategy'],r['hold_sessions'],'days','cost',r['cost_multiplier'],
              'N',s['n'],'net mean',round(s.get('mean',float('nan'))*100,3),
              'marketadj',round(a.get('mean',float('nan'))*100,3),'cashP&L',round(p.get('pnl',0),2))


if __name__=='__main__':main()
