"""Aggregate all exact-hypothesis outcomes, including zero-event feasibility failures."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from engine import HERE,CACHE,SIGNALS,save


def ci(values,issuers):
    values=np.array(values,float);issuers=np.array(issuers)
    mask=np.isfinite(values);values=values[mask];issuers=issuers[mask]
    names=sorted(set(issuers))
    result=dict(n=len(values),issuers=len(names),mean=float(values.mean()) if len(values) else None)
    if len(names)>=3:
        sums=np.array([values[issuers==k].sum() for k in names]);ns=np.array([(issuers==k).sum() for k in names])
        rng=np.random.default_rng(61731);draws=rng.integers(0,len(names),size=(10000,len(names)))
        boot=sums[draws].sum(1)/ns[draws].sum(1)
        result['cluster_bootstrap_95']=np.quantile(boot,[.025,.975]).tolist()
        result['leave_one_issuer_out']=[float(values[issuers!=k].mean()) for k in names]
    else:result['cluster_bootstrap_95']=None
    return result


def table(x):
    ev=x[x.role=='event'].drop_duplicates('event_id').copy()
    out={}
    for m in ['net','mid','stress_net','overlay_net','stock_net','collateral_return']:
        if m in ev:out[m]=ci(ev[m],ev.event_ticker)
    for role in ['peer','issuer','family']:
        ctrl=x[x.role==role]
        for metric in ['net','overlay_net']:
            if ctrl.empty or metric not in ctrl or metric not in ev:continue
            c=ctrl.groupby('event_id')[metric].agg(['mean','count'])
            min_n=1 if role=='family' else 2
            c=c[c['count']>=min_n]
            paired=ev.set_index('event_id').join(c.rename(columns={'mean':'control_mean','count':'control_n'}))
            paired=paired[paired.control_mean.notna()]
            out[role+'_'+metric+'_edge']=ci(paired[metric]-paired.control_mean,paired.event_ticker)
    out['years']={str(y):ci(g.net,g.event_ticker) for y,g in ev.groupby(ev.entry.str[:4])}
    out['events']=ev[['event_id','ticker','filing_date','entry','exit','net','overlay_net']].to_dict('records')
    return out


def fmt(v):return 'n/a' if v is None else f'{v*100:+.2f}%'


def current_output(signal,sensitivity=False):
    paths=[]
    spec_hash=hashlib.sha256((HERE/'spec.json').read_bytes()).hexdigest()
    engine_hash=hashlib.sha256((HERE/'engine.py').read_bytes()).hexdigest()
    for p in CACHE.glob('observations_*.json'):
        parts=p.stem.removeprefix('observations_').split('_')
        manifest=HERE/p.name.replace('observations_','manifest_')
        if signal not in parts or ('sensitivity' in parts)!=sensitivity or not manifest.exists():continue
        m=json.loads(manifest.read_text())
        if m.get('spec_sha256')!=spec_hash or m.get('engine_sha256')!=engine_hash:continue
        if not {signal+'_events.json',signal+'_spec.json'}<=set(m.get('text_source_sha256',{})):continue
        if any(not (HERE/name).exists() or hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=digest
               for name,digest in m.get('text_source_sha256',{}).items()):continue
        receipt=HERE/p.name.replace('observations_','complete_');gates=HERE/p.name.replace('observations_','gates_')
        if not receipt.exists() or not gates.exists():continue
        r=json.loads(receipt.read_text())
        if r.get('status')!='complete':continue
        if r.get('manifest_sha256')!=hashlib.sha256(manifest.read_bytes()).hexdigest():continue
        if r.get('observations_sha256')!=hashlib.sha256(p.read_bytes()).hexdigest():continue
        if r.get('gates_sha256')!=hashlib.sha256(gates.read_bytes()).hexdigest():continue
        paths.append(p)
    return max(paths,key=lambda p:p.stat().st_mtime_ns) if paths else None


def main():
    result={};lines=['SIX FILING IDEAS: DEVELOPMENT TEST','',
        'Window: 2024-2025 only. No 2026 outcome requests or holdout evaluation.',
        'Primary: 3-6 month options, 5% OTM, second-session entry, 21-session exit.',
        'Buy ask/sell bid at entry and reverse at exit, plus $0.65 per contract per side.',
        'Five minutes before exchange close; quotes no more than five minutes old with positive displayed sizes.',
        'Results are per-trade stock-equivalent notional returns, not annualized Sharpe or a funded portfolio.',
        'Long-stock strategies use a paid synthetic-stock approximation. Overlay P&L is shown separately.',
        'Zero qualifying events means not testable under this exact rule, not evidence the idea loses money.','']
    for signal in SIGNALS:
        file=HERE/(signal+'_events.json')
        payload=json.loads(file.read_text()) if file.exists() else None
        r=dict(manifest_available=payload is not None)
        if payload is not None:
            ev=payload.get('events',[]) if isinstance(payload,dict) else payload
            r['text_candidates']=len(ev)
            r['text_metadata']={k:v for k,v in payload.items() if k not in {'events','controls'}} if isinstance(payload,dict) else {}
            r['coverage']=payload.get('audit_counts',payload.get('counts',payload.get('metadata',{}))) if isinstance(payload,dict) else {}
        path=current_output(signal)
        data=[x for x in json.loads(path.read_text()) if x['signal']==signal] if path else []
        gatepath=HERE/(path.name.replace('observations_','gates_')) if path else None
        gates=[x for x in json.loads(gatepath.read_text()) if x['signal']==signal] if gatepath and gatepath.exists() else []
        r['authoritative_observations']=path.name if path else None
        r['authoritative_gates']=gatepath.name if gatepath else None
        r['gates']=gates;r['gate_passing']=sum(g['passed'] for g in gates)
        df=pd.DataFrame(data)
        if not df.empty:
            df=df.drop_duplicates(['event_id','ticker','source_date','role','bucket','otm','delay','horizon'],keep='last')
            primary=df[(df.bucket=='3-6m')&(df.otm==.05)&(df.delay==2)]
            r['horizons']={h:table(g) for h,g in primary.groupby('horizon')}
            r['primary']=r['horizons'].get('21',{})
            # All available horizons on the intersection of event IDs, avoiding
            # interpreting changing cohorts as a holding-period improvement.
            groups={h:g for h,g in primary.groupby('horizon') if h in {'5','10','21','42'}}
            sets=[set(g[g.role=='event'].event_id) for g in groups.values()]
            common=set.intersection(*sets) if sets else set()
            r['common_cohort_event_ids']=sorted(common)
            r['common_cohort_horizons']={h:table(g[g.event_id.isin(common)]) for h,g in groups.items()} if common else {}
        else:r['primary']={};r['horizons']={}
        path=current_output(signal,True)
        sensitivity=[x for x in json.loads(path.read_text()) if x['signal']==signal] if path else []
        r['authoritative_sensitivity']=path.name if path else None
        if sensitivity:
            sdf=pd.DataFrame(sensitivity).drop_duplicates(['event_id','ticker','source_date','role','bucket','otm','delay','horizon'],keep='last')
            r['sensitivity']={f'{b}|{o}|{d}|{h}':table(g) for (b,o,d,h),g in sdf.groupby(['bucket','otm','delay','horizon'])}
        result[signal]=r
        p=r['primary'];net=p.get('net',{});edge=p.get('peer_net_edge',{})
        lines += [signal.upper(),f"  Text-qualified candidates: {r.get('text_candidates','pending')}; gate-passing: {r['gate_passing']}",
                  f"  Primary usable trades: {net.get('n',0)} across {net.get('issuers',0)} issuers",
                  f"  Net full-strategy return: {fmt(net.get('mean'))}; option overlay: {fmt(p.get('overlay_net',{}).get('mean'))}",
                  f"  Same-date peer edge: {fmt(edge.get('mean'))} (paired n={edge.get('n',0)})",
                  f"  Same-issuer ordinary-date edge: {fmt(p.get('issuer_net_edge',{}).get('mean'))}",
                  f"  Comparable filing-family edge: {fmt(p.get('family_net_edge',{}).get('mean'))}"]
        if payload:
            if signal=='governance':lines.append('  Source coverage: 58 comparable issuer pairs; 7 triggers and 51 verified nontriggers. Four other issuers excluded for missing pay votes or an incomparable contested election, plus one duplicate filing.')
            elif signal=='compensation':lines.append('  Source coverage: 174 candidate excerpts screened; 22 primary documents across 18 filings reviewed; seven recurring-program cases remain unclassified. No comparable verified relaxation; full-source coverage is partial.')
            elif signal=='guidance':lines.append('  Source coverage: 60 candidate filings; 18 full sources reviewed; 17 comparable controls and 43 unclassified. No verified positive is not proof of nonoccurrence.')
            elif signal in {'duration','buried'}:lines.append('  Source coverage: 110 adverse candidate excerpts screened; 24 full main filings plus supporting release/exhibits reviewed. Not exhaustive full-text parsing of the whole universe.')
            elif signal=='noncash':lines.append('  Source coverage: 42 candidate filings; two source-confirmed mechanical noncash events. Both failed the original price-richness gate.')
            if r.get('text_candidates')==0:lines.append('  Verdict: no verified qualifying events; exact trading hypothesis not backtestable from this verified manifest.')
        for g in gates:lines.append(f"  {g['event_id']}: {g['reason']}; primary usable={g['primary_usable']}; drops={g['pricing_drops']}; attrition={g.get('primary_attrition',[])}")
        if p.get('net',{}).get('cluster_bootstrap_95'):
            lo,hi=p['net']['cluster_bootstrap_95'];lines.append(f'  Descriptive issuer-bootstrap 95% interval for full net mean: [{fmt(lo)}, {fmt(hi)}]. Small sample; not search-adjusted.')
        if r.get('sensitivity'):
            cells=[v for k,v in r['sensitivity'].items() if k.endswith('|21') and v.get('net',{}).get('n',0)]
            vals=[v['net']['mean'] for v in cells]
            ovs=[v['overlay_net']['mean'] for v in cells if v.get('overlay_net',{}).get('n',0)]
            lines.append(f'  Fixed 21-session sensitivity cells: {len(cells)}; full mean range [{fmt(min(vals) if vals else None)}, {fmt(max(vals) if vals else None)}]; overlay range [{fmt(min(ovs) if ovs else None)}, {fmt(max(ovs) if ovs else None)}]. Cohorts differ; no winner selected.')
        if r['horizons']:
            lines.append('  All horizons: sessions | usable | full net | option overlay | peer edge')
            for h in ['1','2','3','5','10','21','42','63','exp']:
                if h not in r['horizons']:
                    lines.append(f'    {h:>3} |   0 | unavailable under date/expiry/fresh-quote filters')
                    continue
                z=r['horizons'][h]
                lines.append(f"    {h:>3} | {z.get('net',{}).get('n',0):>3} | {fmt(z.get('net',{}).get('mean'))} | {fmt(z.get('overlay_net',{}).get('mean'))} | {fmt(z.get('peer_net_edge',{}).get('mean'))}")
        lines.append('')
    lines += ['INTERPRETATION LIMITS',
        'All six are exploratory additions to prior research; the shared project has already examined roughly 2,000 cells.',
        'The text review is source-based but screening depends on sponsor excerpts; missed untagged content cannot be ruled out.',
        'Current/backfilled tags lack historical availability timestamps. A two-session delay does not prove point-in-time label availability.',
        'Controls exclude known nearby filings; missing earnings and news coverage means quiet is only a proxy.',
        'Quote crossing is a simulation for small size, not a guaranteed fill. No assignment, early exercise, exact dividends, stock borrow or endogenous funding model.',
        'IV features are European model proxies on American options; conclusions require validation with appropriate dividends and exercise modeling.',
        'For any future gate-passing event, controls would also need matching IV conditions to isolate text-specific alpha; here both gated ideas have zero trades.',
        'Overlapping events and small samples prevent interpreting event-average returns as portfolio Sharpe or validated alpha.',
        'No optional parameter is selected as a winner, and the 2026 holdout remains unopened.','',
        'Engineering audit: removed future filings from price-gate peer selection and reran final results; summaries require current spec, code and source hashes and never pool outdated partial runs.',
        'Reproduction from repo root:',
        '  massive/.venv/bin/python massive/research/codex_six/engine.py',
        '  massive/.venv/bin/python massive/research/codex_six/engine.py --signals governance buried --sensitivity',
        '  massive/.venv/bin/python massive/research/codex_six/confounds.py',
        '  massive/.venv/bin/python massive/research/codex_six/summarize.py',
        '  massive/.venv/bin/python massive/research/codex_six/verify_outputs.py',
        'Full source/exclusion audits are in the corresponding *_audit.json and *_spec.json files.']
    trend=HERE/'governance_prior_trend_diagnostic.json'
    if trend.exists():
        evidence=json.loads(trend.read_text());result['governance']['prior_trend_diagnostic']=evidence
        vals=[e['event']['prior_42_session_return'] for e in evidence['events'] if e['event']['prior_42_session_return'] is not None]
        if vals:
            lines += ['',f"Prefiling trend diagnostic: {sum(v<0 for v in vals)}/{len(vals)} measured governance issuers had already fallen over the preceding 42 sessions; mean {fmt(float(np.mean(vals)))}. This is descriptive, not a causal regression or a retuned signal."]
    save(HERE/'summary.json',result)
    (HERE/'REPORT.txt').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))


if __name__=='__main__':main()
