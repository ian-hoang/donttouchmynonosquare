"""Explain option-feature exclusions using the same already-cached quotes."""
import json
from collections import Counter
from datetime import date,timedelta
from zoneinfo import ZoneInfo

from options_audit import HERE,cutoff,get


def main():
    features=json.loads((HERE/'options_features.json').read_text())
    causes=Counter();details=[]
    for f in features:
        if f.get('iv30') is not None:continue
        expiry=f.get('expiry_missing')
        if not expiry:
            causes[f.get('drop_reason','unknown')]+=1
            details.append({'ticker':f['ticker'],'signal_date':f['signal_date'],
                            'reasons':[f.get('drop_reason','unknown')]})
            continue
        spot=f['stock_quote']['mid'];day=date.fromisoformat(f['signal_date']);at=cutoff(f['signal_date'])
        params={'underlying_ticker':f['ticker'],'as_of':f['signal_date'],
                'expiration_date.gte':str(day+timedelta(days=21)),
                'expiration_date.lte':str(day+timedelta(days=45)),
                'strike_price.gte':spot*.9,'strike_price.lte':spot*1.1,'limit':1000}
        payload=get('/v3/reference/options/contracts',params)
        chain=list(payload.get('results')or[])
        while payload.get('next_url'):
            payload=get(payload['next_url']);chain.extend(payload.get('results')or[])
        contracts={}
        for row in chain:
            if (row.get('expiration_date')==expiry and row.get('shares_per_contract')==100
                    and not row.get('additional_underlyings') and row.get('contract_type')in('call','put')):
                contracts.setdefault(row['strike_price'],{})[row['contract_type']]=row['ticker']
        pairs=sorted([k for k,pair in contracts.items()if len(pair)==2],key=lambda k:abs(k-spot))
        reasons=[]
        if not pairs:reasons=['no_paired_strike']
        else:
            for kind,ticker in contracts[pairs[0]].items():
                payload=get('/v3/quotes/'+ticker,{'timestamp.lte':at.astimezone(ZoneInfo('UTC')).strftime('%Y-%m-%dT%H:%M:%SZ'),
                                                'order':'desc','sort':'timestamp','limit':1})
                quotes=payload.get('results')or[]
                if not quotes:
                    reasons.append(kind+':no_quote');continue
                q=quotes[0]
                age=at.timestamp()-q['sip_timestamp']/1e9
                bid=q.get('bid_price',-1);ask=q.get('ask_price',-1)
                if age<0:reasons.append(kind+':future_quote')
                if age>60:reasons.append(kind+':stale_over60s')
                if not 0<bid<=ask:reasons.append(kind+':invalid_price')
                if q.get('bid_size',0)<=0 or q.get('ask_size',0)<=0:reasons.append(kind+':zero_size')
                if bid+ask>0 and (ask-bid)/((ask+bid)/2)>.25:reasons.append(kind+':spread_above25pct')
        causes.update(set(s.split(':')[-1]for s in reasons)or['forward_or_iv_constraint'])
        details.append({'ticker':f['ticker'],'signal_date':f['signal_date'],'expiry':expiry,'reasons':reasons})
    out={'features':len(features),'valid':sum(f.get('iv30')is not None for f in features),
         'failures':len(details),'causes_nonexclusive':dict(causes),'details':details,'thresholds_unchanged':True}
    (HERE/'options_quality_audit.json').write_text(json.dumps(out,indent=2))
    print({k:v for k,v in out.items()if k!='details'})


if __name__=='__main__':main()
