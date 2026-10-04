"""Independent arithmetic and timing checks over saved replication observations."""
from collections import Counter
from datetime import date,datetime
import hashlib
import json
import math
import re
import statistics
from . import data,events,trading_calendar as cal


def close(a,b):
    assert abs(a-b)<=1e-10*max(1,abs(a),abs(b)),(a,b)


def verify():
    spec=(data.HERE/'FROZEN_SPEC.txt').read_text()
    literal=re.search(r'## Universe.*?```\s*(.*?)```',spec,re.S).group(1).split()
    assert literal==events.UNIVERSE
    assert len(literal)==len(set(literal))==99
    manifest=json.loads((data.HERE/'run_manifest.json').read_text())
    assert hashlib.sha256((data.HERE/'FROZEN_SPEC.txt').read_bytes()).hexdigest()==manifest['frozen_spec_sha256']
    completed=date.fromisoformat(manifest['completed_session'])
    seen=set();counts=Counter();checked=0
    for filename in ['event_results.json','peer_results.json']:
        path=data.CACHE/filename
        if not path.exists():continue
        seen.clear()
        for r in json.loads(path.read_text()):
            key=(r['ticker'],r['filing_date']);assert key not in seen;seen.add(key)
            assert r['status']!='error'
            counts[filename+':'+r['status']]+=1
            if r['status']!='valid':continue
            filing=date.fromisoformat(r['filing_date']);entry=date.fromisoformat(r['entry']);exit=date.fromisoformat(r['exit'])
            pre=date.fromisoformat(r['t_pre']);expiry=date.fromisoformat(r['expiry'])
            assert pre==cal.session_before(cal.session_on_or_after(filing))
            assert entry==cal.session_after(cal.session_on_or_after(filing))
            assert exit==cal.shift_session(entry,10)
            assert exit<=cal.session_on_or_before(expiry) and exit<=completed
            assert 90<=(expiry-pre).days<=180
            qt=datetime.fromisoformat(r['quote_time']);assert qt.date()==entry
            assert (qt.hour,qt.minute,qt.second)<=(16,0,0)
            assert 0<=r['bid']<=r['ask'] and r['ask']>0
            close(r['half_spread'],(r['ask']-r['bid'])/2)
            for when,markday in [('pre_atm_call_mark',pre),('pre_atm_put_mark',pre),('entry_mark',entry),
                                ('entry_atm_call_mark',entry),('entry_atm_put_mark',entry),
                                ('exit_mark',exit),('exit_atm_call_mark',exit),('exit_atm_put_mark',exit)]:
                used=date.fromisoformat(r[when+'_date']);assert used<=markday
                assert cal.sessions_between(used,markday)<=3
            for name,day in [('entry',entry),('exit',exit)]:
                stock=r['atm_strike']*math.exp(-.04*max((expiry-day).days,0)/365)+r[name+'_atm_call_mark']-r[name+'_atm_put_mark']
                close(r[name+'_spot'],stock)
            net=(r['entry_mark']-r['exit_mark']-(r['ask']-r['bid']))/r['entry_spot']
            close(net,r['net']);close(r['cost'],(r['ask']-r['bid'])/r['entry_spot'])
            close(r['gross'],(r['entry_mark']-r['exit_mark'])/r['entry_spot'])
            assert 1<=len(r['spot_attempts'])<=8
            estimates=[a['estimate'] for a in r['spot_attempts'] if 'estimate' in a]
            close(estimates[-1],r['pre_spot'])
            checked+=1
    summary_path=data.HERE/'independent_summary.json'
    if summary_path.exists():
        summary=json.loads(summary_path.read_text());all_events=json.loads((data.CACHE/'event_results.json').read_text())
        for w in ['2024-25','2026']:
            values=[r['net'] for r in all_events if r['status']=='valid' and events.window(r['filing_date'])==w]
            s=summary[w];assert len(values)==s['n']
            close(sum(values)/len(values),s['mean']);close(statistics.stdev(values),s['std'])
            close(s['mean']/s['std'],s['per_trade_sharpe'])
            assert len(s['seeds'])==20 and {x['seed'] for x in s['seeds']}==set(range(20))
            means=[x['mean_gap'] for x in s['seeds'] if x['mean_gap'] is not None]
            close(statistics.mean(means),s['peer_gap_mean_across_seeds'])
            close(min(means),s['peer_gap_min']);close(max(means),s['peer_gap_max'])
    result=dict(status='passed',valid_observations_checked=checked,counts=dict(counts),literal_universe_size=99,
         checks=['Spec literal universe','Unique issuer-date observations','Frozen filing/entry/exit timing','Completed exit cutoff',
                 'At most3session stale marks','Same-day entry quote','Required entry and exit stock parity',
                 'Twice entry halfspread cost and net arithmetic','At most8initial spot attempts','Reported per-trade statistics'])
    data.atomic_json(data.HERE/'verification.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':verify()
