"""Pre-existing trend diagnostic; never used to retune the selected text rules."""
import json
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import numpy as np
from engine import HERE,CAL,START,quote,spot,panel,load_events,controls,save


def prior_return(job):
    ticker,date=job
    p=panel(ticker,date)
    b=p.get('buckets',{}).get('3-6m')
    if not b:return dict(ticker=ticker,date=date,prior_42_session_return=None)
    pre=pd.Timestamp(p['pre']);prior=CAL[CAL.get_loc(pre)-42]
    if prior<START:return dict(ticker=ticker,date=date,prior_42_session_return=None)
    q={leg:quote(b['contracts'][leg],str(prior.date())) for leg in ['C_K','P_K']}
    earlier=spot(b['strikes']['K'],b['expiry'],prior,q)
    current=spot(b['strikes']['K'],b['expiry'],pre,b['quotes'].get(str(pre.date()),{}))
    value=current/earlier-1 if earlier and current else None
    return dict(ticker=ticker,date=date,prior_date=str(prior.date()),prior_42_session_return=value,
                caveat='Synthetic price using identical contract pair; no corporate-action/dividend adjustment')


def main():
    events,_=load_events(['governance']);cs=controls(events)
    jobs={(e['ticker'],e['filing_date']) for e in events}
    jobs.update((c['ticker'],c['date']) for group in cs.values() for c in group)
    with ThreadPoolExecutor(8) as pool:out=list(pool.map(prior_return,sorted(jobs)))
    bykey={(x['ticker'],x['date']):x for x in out}
    comparisons=[]
    for e in events:
        ev=bykey[(e['ticker'],e['filing_date'])]
        record=dict(event_id=e['id'],event=ev,controls=[])
        for c in cs[e['id']]:record['controls'].append(dict(bykey[(c['ticker'],c['date'])],role=c['role']))
        for role in ['peer','issuer','family']:
            vals=[x['prior_42_session_return'] for x in record['controls'] if x['role']==role and x['prior_42_session_return'] is not None]
            record[role+'_mean_prior_return']=float(np.mean(vals)) if vals else None
        comparisons.append(record)
    save(HERE/'governance_prior_trend_diagnostic.json',dict(
         method='Descriptive 42-session prefiling trend; no regression or causal claim with sparse events. Planned as kill-test audit before governance returns were inspected.',
         events=comparisons))
    print('Prior-trend diagnostics complete for',len(events),'events',flush=True)


if __name__=='__main__':main()
