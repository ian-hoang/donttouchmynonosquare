"""Supplementary same-issuer non-trigger credit-disclosure control study."""
import concurrent.futures
import json
import pandas as pd
import backtest as b
from data import HERE


def main():
    events=[e for e in b.load_events() if e['signal']=='credit']
    audits=json.loads((HERE/'credit_audit.json').read_text())['records']
    triggers={(e['ticker'],e['filing_date']) for e in events}
    jobs=set()
    for e in events:
        pool=[]
        for r in audits:
            if r['ticker']!=e['ticker'] or r['filing_date'][:4]!=e['filing_date'][:4]:continue
            if (r['ticker'],r['filing_date']) in triggers:continue
            if r.get('raw_divergence',False):continue
            if r['ticker']=='COF':
                if r.get('portfolio_change_flags') or not r.get('eligible_legacy_series'):continue
            elif r.get('consumer_series_break'):continue
            if any(abs((pd.Timestamp(r['filing_date'])-pd.Timestamp(d)).days)<30 for t,d in triggers if t==r['ticker']):continue
            pool.append(r['filing_date'])
        e['controls']=sorted(pool,key=lambda d:(abs((pd.Timestamp(d)-pd.Timestamp(e['filing_date'])).days),d))[:5]
        jobs.update((e['ticker'],d) for d in e['controls'])
    (HERE/'credit_controls_manifest.json').write_text(json.dumps(b.clean(events),indent=2))
    prices={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(b.price_request,j):j for j in jobs}
        for f in concurrent.futures.as_completed(futures):
            j=futures[f]
            try:prices[j]=f.result()[0]
            except Exception as error:
                prices[j]=[]
                print('Pricing error',j,type(error).__name__)
    controls=[]
    for e in events:
        for d in e['controls']:
            for pe in prices.get((e['ticker'],d),[]):
                controls.extend(b.evaluate_one(pe,e,'long_call',e['id'],d))
    (b.PRIVATE/'credit_control_observations.json').write_text(json.dumps(b.clean(controls)))
    raw=pd.DataFrame(json.loads((b.PRIVATE/'observations.json').read_text()))
    ev=raw[(raw.signal=='credit')&(raw.role=='event')]
    c=pd.DataFrame(controls)
    if c.empty:
        (HERE/'credit_controls_summary.json').write_text(json.dumps({'status':'No usable supplemental controls'}))
        return
    for name in ['bucket','delay','otm','haircut']:
        target={'bucket':'3-6m','delay':2,'otm':.05,'haircut':.05}[name]
        ev=ev[ev[name]==target];c=c[c[name]==target]
    means=c.groupby(['event_id','horizon']).agg(control_net=('net','mean'),n_controls=('net','size')).reset_index()
    paired=ev.merge(means,on=['event_id','horizon'])
    paired['edge']=paired.net-paired.control_net
    result=[]
    for h,g in paired.groupby('horizon'):
        result.append(dict(horizon=h,n=len(g),issuers=g.ticker.nunique(),net_mean=g.net.mean(),
          control_mean=g.control_net.mean(),edge=g.edge.mean(),
          events=g[['ticker','filing_date','net','control_net','edge','n_controls']].to_dict('records')))
    (HERE/'credit_controls_summary.json').write_text(json.dumps(b.clean({'comparison':'non-trigger monthly disclosure days, supplementary','horizons':result}),indent=2))
    print(json.dumps(b.clean([r for r in result if r['horizon']=='21']),indent=2))


if __name__=='__main__':main()
