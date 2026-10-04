"""Audit saved data timing, executable sides, commissions and reported arithmetic."""
import json
import math
from pathlib import Path
import pandas as pd
from engine import CACHE,HERE,END,CAL,cutoff,save


def main():
    count=0;files=[]
    for path in sorted(CACHE.glob('observations_*.json')):
        rows=json.loads(path.read_text());seen=set()
        for r in rows:
            key=tuple(r[k] for k in ['event_id','ticker','source_date','role','bucket','delay','otm','horizon'])
            assert key not in seen,(path.name,'duplicate',key)
            seen.add(key)
            entry,leave=pd.Timestamp(r['entry']),pd.Timestamp(r['exit'])
            assert entry<=leave<=END
            expected=CAL[CAL.searchsorted(pd.Timestamp(r['source_date']),side='right')+r['delay']-1]
            assert entry==expected
            if r['horizon']!='exp':assert CAL.get_loc(leave)-CAL.get_loc(entry)==int(r['horizon'])
            else:assert leave<=pd.Timestamp(r['expiry']) and (pd.Timestamp(r['expiry'])-leave).days<=3
            w={}
            for leg in r['contracts']:
                w[leg]=-1 if leg=='P_K' or leg.startswith('C_U') or r['strategy']=='cash_secured_put' else 1
            value=0.;overlay=0.;stress=0.;mid=0.
            for leg,n in w.items():
                qe,qx=r['entry_quotes'][leg],r['exit_quotes'][leg]
                for day,q in [(entry,qe),(leave,qx)]:
                    age=(cutoff(day)-pd.Timestamp(q['timestamp'],unit='ns',tz='UTC')).total_seconds()
                    assert 0<=age<=300 and q['bid_size']>=1 and q['ask_size']>=1
                    assert 0<=q['bid']<=q['ask'] and q['ask']>0
                en=qe['ask'] if n>0 else qe['bid'];ex=qx['bid'] if n>0 else qx['ask']
                pnl=n*(ex-en)-.013
                value+=pnl;mid+=n*(qx['mid']-qe['mid']);stress+=pnl-.025*(abs(en)+abs(ex))
                if leg not in {'C_K','P_K'}:overlay+=pnl
            if r['strategy']!='cash_secured_put':
                atm=r['contracts']['C_K'];strike=int(atm[-8:])/1000
                exp=pd.Timestamp(r['expiry'])
                carry=strike*(math.exp(-.04*max((exp-leave).days,0)/365)-math.exp(-.04*(exp-entry).days/365))
                value+=carry;mid+=carry;stress+=carry
            assert abs(value/r['spot_proxy']-r['net'])<1e-10
            assert abs(overlay/r['spot_proxy']-r['overlay_net'])<1e-10
            assert abs(mid/r['spot_proxy']-r['mid'])<1e-10
            assert abs(stress/r['spot_proxy']-r['stress_net'])<1e-10
            count+=1
        files.append(dict(file=path.name,rows=len(rows)))
    result=dict(status='passed',rows_checked=count,files=files,checks=[
        'No 2026 outcomes','No duplicate configurations','Correct postfiling entry and horizon dates',
        'Fresh positive-size NBBO quotes','Buy ask and sell bid on correct sides',
        'All synthetic option legs charged commissions','P&L and overlay/stress arithmetic reconstructed'])
    save(HERE/'verification.json',result)
    print('Saved-output audit passed:',count,'rows across',len(files),'files')


if __name__=='__main__':main()
