"""Independent per-trade and 20-seed summaries of the frozen replication."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import statistics
from . import data,events

HERE=Path(__file__).resolve().parent


def metrics(values):
    if not values:return dict(n=0,mean=None,median=None,win_rate=None,std=None,per_trade_sharpe=None)
    mean=statistics.mean(values);std=statistics.stdev(values) if len(values)>1 else None
    return dict(n=len(values),mean=mean,median=statistics.median(values),win_rate=sum(v>0 for v in values)/len(values),
                std=std,per_trade_sharpe=mean/std if std and std>0 else None)


def pct(x):return 'n/a' if x is None else f'{100*x:+.4f}%'
def number(x,places=4):return 'n/a' if x is None else f'{x:.{places}f}'


def export_csv(path,rows,fields):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)


def report():
    cohort=json.loads((data.CACHE/'cohort.json').read_text())
    event_results=json.loads((data.CACHE/'event_results.json').read_text())
    peer_results=json.loads((data.CACHE/'peer_results.json').read_text())
    draws=json.loads((data.CACHE/'peer_draws.json').read_text())
    lookup={(r['ticker'],r['filing_date']):r for r in peer_results}
    draw_lookup={(d['seed'],d['filing_date']):d for d in draws}
    summary={};gap_rows=[];valid=[r for r in event_results if r['status']=='valid']
    text=['INDEPENDENT REPLICATION: CALL OVERLAY AFTER DEAL-SIGNING 8-K','',
          'Implemented from the user-supplied frozen spec; existing harness/research not read for this implementation.',
          'Coordinator had prior project context; pricing implementation and audit agents started without it.',
          'Important input discrepancy: heading says100tickers; literal frozen list has99. Literal list used, without UNH.',
          'No parameter tuning.2026 is replication of an already-tested frozen rule, not another independent holdout.',
          'Returns measure only the covered-call option overlay per $1of parity stock, not the full stock+call investment.',
          'Costs exactly follow the spec: twice entryhalfspread; not actual entrybid-to-exitask fills. No commissions.',
          'Marks may be three sessions stale. Initialspot uses the separate7calendar-day lookup.',
          'Std is sample standarddeviation (ddof1); Sharpe is pertrade mean/std, not annualized.',
          'Twenty fixed Python random seeds0..19; six peers sampled before pricing, never replaced after missing prices.',
          'Mean peer profit uses available valid members of each6-name draw. See per-seed coverage.','']
    for window in ['2024-25','2026']:
        before=[e for e in cohort['before'] if e['window']==window]
        kept=[e for e in cohort['kept'] if e['window']==window]
        all_trades=[r for r in event_results if events.window(r['filing_date'])==window]
        trades=[r for r in valid if events.window(r['filing_date'])==window]
        stats=metrics([r['net'] for r in trades]);seeds=[]
        for seed in range(20):
            gaps=[];counts=[]
            for trade in trades:
                basket=draw_lookup[(seed,trade['filing_date'])]['tickers']
                prices=[lookup[(t,trade['filing_date'])] for t in basket]
                good=[p for p in prices if p['status']=='valid'];counts.append(len(good))
                peer_mean=statistics.mean(p['net'] for p in good) if good else None
                gap=trade['net']-peer_mean if peer_mean is not None else None
                if gap is not None:gaps.append(gap)
                gap_rows.append(dict(window=window,seed=seed,ticker=trade['ticker'],filing_date=trade['filing_date'],
                    event_net=trade['net'],peer_mean=peer_mean,gap=gap,valid_peers=len(good),drawn_peers=' '.join(basket)))
            seeds.append(dict(seed=seed,mean_gap=statistics.mean(gaps) if gaps else None,paired_events=len(gaps),
                              missing_events=len(trades)-len(gaps),mean_valid_peers=statistics.mean(counts) if counts else None,
                              min_valid_peers=min(counts) if counts else None,max_valid_peers=max(counts) if counts else None))
        means=[s['mean_gap'] for s in seeds if s['mean_gap'] is not None]
        row=dict(events_before_cooldown=len(before),events_after_cooldown=len(kept),
                 companies_after_cooldown=len({e['ticker'] for e in kept}),**stats,
                 drop_reasons=dict(Counter(r['drop_reason'] for r in all_trades if r['status']!='valid')),
                 peer_gap_mean_across_seeds=statistics.mean(means) if means else None,
                 peer_gap_min=min(means) if means else None,peer_gap_max=max(means) if means else None,seeds=seeds)
        summary[window]=row
        text += [window,f"  Events: {len(before)} before -> {len(kept)} after continuous >60day cooldown ({row['companies_after_cooldown']} companies)",
                 f"  Valid trades: {stats['n']}",f"  Mean net: {pct(stats['mean'])}; median net: {pct(stats['median'])}",
                 f"  Win rate: {100*stats['win_rate']:.2f}%; std: {pct(stats['std'])}; per-trade Sharpe: {number(stats['per_trade_sharpe'])}" if stats['n'] else '  No valid trades',
                 f"  Peer gap: {pct(row['peer_gap_mean_across_seeds'])} mean over20seeds; range [{pct(row['peer_gap_min'])}, {pct(row['peer_gap_max'])}]",
                 '  Drop reasons: '+json.dumps(row['drop_reasons'],sort_keys=True),
                 '  seed | mean gap | paired events | average valid peers of6']
        text.extend(f"    {s['seed']:2d} | {pct(s['mean_gap'])} | {s['paired_events']} | {number(s['mean_valid_peers'],2)}" for s in seeds)
        text+=['','  PER-TRADE TABLE','  ticker | filing | entry | exit | strike | expiry | net']
        text.extend(f"  {r['ticker']} | {r['filing_date']} | {r['entry']} | {r['exit']} | {r['strike']:g} | {r['expiry']} | {pct(r['net'])}" for r in trades)
        text+=['']
    summary['methodology']=dict(literal_universe_size=len(events.UNIVERSE),ambiguous_cik_days=cohort['ambiguous_cik_days'],
        raw_tag_record_counts=cohort['raw_counts'],peer_jobs=len(peer_results),
        peer_status_counts=dict(Counter(r['status'] for r in peer_results)),
        independent_numbers_before_original_code_review=True)
    fields=['ticker','filing_date','entry','exit','strike','expiry','net']
    export_csv(HERE/'trades.csv',valid,fields)
    export_csv(HERE/'trade_diagnostics.csv',event_results,fields+['status','drop_reason','t_pre','pre_spot','parity_pre_spot',
        'atm_strike','entry_spot','exit_spot','entry_mark','exit_mark','entry_mark_date','exit_mark_date','bid','ask','half_spread','gross','cost','sold_call'])
    export_csv(HERE/'peer_gaps_20_seeds.csv',gap_rows,['window','seed','ticker','filing_date','event_net','peer_mean','gap','valid_peers','drawn_peers'])
    export_csv(HERE/'cohort.csv',cohort['before'],['window','ticker','cik','filing_date'])
    export_csv(HERE/'cooldown_exclusions.csv',cohort['cooldown_drops'],['window','ticker','cik','filing_date','last_kept','drop_reason'])
    data.atomic_json(HERE/'independent_summary.json',summary)
    (HERE/'INDEPENDENT_REPORT.txt').write_text('\n'.join(text)+'\n')
    data.atomic_json(HERE/'independent_completion.json',dict(status='complete',
         manifest_sha256=hashlib.sha256((HERE/'run_manifest.json').read_bytes()).hexdigest(),
         event_results_sha256=hashlib.sha256((data.CACHE/'event_results.json').read_bytes()).hexdigest(),
         peer_results_sha256=hashlib.sha256((data.CACHE/'peer_results.json').read_bytes()).hexdigest(),
         summary_sha256=hashlib.sha256((HERE/'independent_summary.json').read_bytes()).hexdigest()))
    print('\n'.join(text))


if __name__=='__main__':report()
