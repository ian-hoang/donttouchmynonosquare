"""Reconcile the new experiments, without altering their rules or observations."""
from collections import Counter
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import statistics
from .. import data,events
from . import prospective as p

HERE=Path(__file__).resolve().parent

def same(a,b):
    assert math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12),(a,b)

def run():
    frozen=json.loads((data.HERE/'before_original_review.json').read_text())
    assert all(hashlib.sha256((data.HERE/name).read_bytes()).hexdigest()==digest
               for name,digest in frozen['sha256'].items())
    manifest=json.loads((HERE/'prospective_manifest.json').read_text())
    assert hashlib.sha256((HERE/'PROSPECTIVE_SPEC.txt').read_bytes()).hexdigest()==manifest['spec_sha256']
    assert hashlib.sha256((HERE/'prospective.py').read_bytes()).hexdigest()==manifest['code_sha256']
    for name,digest in manifest['source_sha256'].items():
        assert hashlib.sha256((data.CACHE/name).read_bytes()).hexdigest()==digest
    cohort=json.loads((data.CACHE/'cohort.json').read_text())['kept']
    history=json.loads((data.CACHE/'histories.json').read_text())
    draws=json.loads((HERE/'prospective_draws.json').read_text())
    assert draws==p.draw_controls(cohort,history)
    prices=json.loads((HERE/'prospective_prices.json').read_text())
    rows=json.loads((HERE/'prospective_rows.json').read_text())
    assert rows==p.assemble(draws,prices)
    assert len(draws)==59 and len(prices)==227
    assert not any(r['status']=='error' for r in prices)
    checked=0
    for r in prices:
        for day,qs in [(r.get('entry'),list(r.get('entry_quotes',{}).values())),(r.get('exit'),[r.get('exit_quote')])]:
            for q in qs:
                if not q:continue
                age_ns=int(p.cutoff(day).timestamp())*1_000_000_000-q['timestamp']
                assert 0<=age_ns<=300_000_000_000
                assert 0<=q['bid']<=q['ask'] and q['ask']>0
                assert q['bid_size']>=1 and q['ask_size']>=1
        if r['status']!='valid':continue
        qe=r['entry_quotes']['sold_call'];qx=r['exit_quote']
        expiry=date.fromisoformat(r['expiry']);entry=date.fromisoformat(r['entry'])
        proxy=r['atm_strike']*math.exp(-.04*(expiry-entry).days/365)+r['entry_quotes']['atm_call']['mid']-r['entry_quotes']['atm_put']['mid']
        same(proxy,r['entry_spot'])
        same(r['short_net'],(qe['bid']-qx['ask']-.013)/proxy)
        same(r['long_net'],(qx['bid']-qe['ask']-.013)/proxy)
        same(r['short_net']+r['long_net'],-2*r['roundtrip_cost'])
        checked+=1
    old={(r['ticker'],r['filing_date']):r for r in json.loads((data.CACHE/'event_results.json').read_text())}
    summary=json.loads((HERE/'prospective_summary.json').read_text())
    for window in ('2024-25','2026'):
        sub=[r for r in rows if events.window(r['filing_date'])==window]
        for field in ('event_short_net','sector_gap','pair_net','pair_per_gross_reference'):
            xs=[r[field] for r in sub if r.get(field) is not None]
            assert len(xs)==summary[window][field]['n']
            same(statistics.mean(xs),summary[window][field]['mean'])
    comparison={}
    for window in ('2024-25','2026'):
        sub=[r for r in rows if events.window(r['filing_date'])==window]
        comparison[window]={}
        # These decompositions were requested after the broader result appeared.
        # They diagnose the change; they do not select a new winning strategy.
        for label,gate in [
            ('original_valid_cohort',lambda r:old[(r['ticker'],r['filing_date'])]['status']=='valid'),
            ('original_pre_event_mark_eligibility',lambda r:old[(r['ticker'],r['filing_date'])].get('drop_reason')
                not in ('missing_pre_atm_parity_mark','missing_initial_parity_marks','no_pair_within_25_percent_of_spot'))]:
            chosen=[r for r in sub if gate(r)]
            out={}
            for field in ('event_short_net','sector_gap','pair_net'):
                xs=[r[field] for r in chosen if r.get(field) is not None]
                out[field]={**p.summarize(xs),'issuer_cluster_95':p.interval(chosen,field,'issuer')}
            comparison[window][label]=out
    recovered=[]
    bykey={(r['ticker'],r['filing_date']):r for r in prices}
    for key,before in old.items():
        after=bykey[key]
        if before['status']!='valid' and after['status']=='valid':
            recovered.append({k:after[k] for k in ('ticker','filing_date','entry','exit','sold_call','strike','expiry','short_net','entry_spot')}
                             |{'original_drop_reason':before['drop_reason']})
    output=dict(status='passed',frozen_replication_unchanged=True,prospective_spec_and_source_unchanged=True,
        observations=len(prices),valid_observations_checked=checked,status_counts=dict(Counter(r['status'] for r in prices)),
        post_result_cohort_diagnostics=True,cohort_comparison=comparison,recovered_trades=recovered,
        conclusion='No new independently validated alpha. Original eligible overlay survives quote costs; broader cohort is fragile, and matched 2026 uncertainty is wide.')
    data.atomic_json(HERE/'assessment.json',output)
    print(json.dumps({k:v for k,v in output.items() if k not in ('cohort_comparison','recovered_trades')},indent=2))

if __name__=='__main__':run()
