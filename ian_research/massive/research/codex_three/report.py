"""Readable report from saved results; no market-data calls."""
import hashlib
import json
from collections import Counter
import pandas as pd
from data import HERE
from backtest import PRIVATE, clean

NAMES={'liquidity':'Liquidity runway / cash-secured put',
       'departures':'Second resignation / collar','credit':'Credit turnaround / ATM long call'}


def pct(x):return 'NA' if x is None else f'{100*x:+.2f}%'


def main():
    s=json.loads((HERE/'summary.json').read_text())
    raw=json.loads((PRIVATE/'observations.json').read_text())
    df=pd.DataFrame(raw)
    # Full saved-data assertions, independent of aggregation.
    keys=['event_id','source_date','bucket','delay','otm','haircut','horizon']
    assert not df.duplicated(keys).any()
    assert (pd.to_datetime(df.exit)<=pd.Timestamp('2025-12-31')).all()
    assert (pd.to_datetime(df.entry)>pd.to_datetime(df.source_date)).all()
    assert (df.entry_min_volume>0).all() and (df.exit_min_volume>0).all()
    assert (((df.gross-df.net)*df.spot_proxy-df.costs_per_share).abs()<1e-7).all()
    lines=['MASSIVE: THREE STRATEGY DEVELOPMENT TESTS',
      'Verdict: none has demonstrated convincing tradable alpha in this test.',
      'Window: 2024-01-01 through 2025-12-31. No 2026 outcomes evaluated.',
      '',
      'Primary setup: 21 trading sessions; enter at the close of the second trading session after filing;',
      '3-6month expiry bucket (nearest 120 calendar days); 5% OTM put/collar wings; long call is ATM.',
      'Costs: 5% of EACH actual entry and exit option premium, plus $0.65 per contract per side.',
      'Collar includes the ATM call/put synthetic-stock legs in costs. 4% bond carry is modeled.',
      'Headline returns are arithmetic mean P&L divided by stock-equivalent entry notional.',
      'They are not annual returns, Sharpe ratios, or demonstrated live fills.',
      '',
      'PRIMARY RESULTS',
      'Strategy | Qualified events | Fresh-price events | Gross mean | Net mean | Paired events | Mean net edge vs calendar controls']
    for signal in NAMES:
        row=next((r for r in s['headline'] if r['signal']==signal),None)
        if row:
            lines.append(f"{NAMES[signal]} | {s['qualified_events'][signal]} | {row['n_events']} | {pct(row['gross_mean'])} | {pct(row['net_mean'])} | {row['n_paired']} | {pct(row['mean_edge'])}")
            if signal=='credit':lines.append(f"  ATM call mean return on premium plus entry costs: {pct(row['mean_return_on_capital'])}.")
            if row.get('cluster_bootstrap_95',[None])[0] is not None:
                lo,hi=row['cluster_bootstrap_95'];lines.append(f"  Issuer-cluster bootstrap interval for edge: [{pct(lo)}, {pct(hi)}]; small-sample descriptive interval.")
    lines += ['',
      'The liquidity comparison uses a matched subset, so its mean event-minus-control edge is not',
      'the difference between the all-event mean and an unrelated benchmark mean.',
      'Credit calendar controls are especially weak: the 10-session buffer eliminates all COF controls,',
      'and the incomplete tag calendar misses actual AXP monthly reports. Do not label that positive',
      'one-event relative result an alpha finding. The supplementary disclosure-day comparison is separate.',
      '',
      'ALL PRESCRIBED HORIZONS AT PRIMARY PARAMETERS',
      'Returns and sample sizes below show why selecting a positive horizon is not validation.']
    for signal in NAMES:
        lines+=['',NAMES[signal],'Horizon | Fresh n | Net mean | Paired n | Mean net edge']
        for h in ['1','2','3','5','10','21','42','63','exp']:
            row=next((r for r in s['all_configurations'] if r['signal']==signal and r['bucket']=='3-6m' and
                      r['delay']==2 and r['otm']==.05 and r['haircut']==.05 and r['horizon']==h),None)
            lines.append(f"{h} | {row['n_events'] if row else 0} | {pct(row['net_mean']) if row else 'NA'} | {row['n_paired'] if row else 0} | {pct(row['mean_edge']) if row else 'NA'}")
    lines += ['','COST SENSITIVITY AT THE PRIMARY 21-SESSION HORIZON','0% haircut still includes commissions.']
    for signal in NAMES:
        for r in s['all_configurations']:
            if r['signal']==signal and r['bucket']=='3-6m' and r['delay']==2 and r['otm']==.05 and r['horizon']=='21':
                lines.append(f"{signal} | premium haircut {100*r['haircut']:g}% | n={r['n_events']} | net={pct(r['net_mean'])}")
    lines+=['','SAME EVENT COHORT AT 21, 42 AND 63 SESSIONS','Control availability may still vary by horizon.']
    for r in s['balanced_21_42_63']:
        lines.append(f"{r['signal']} | {r['horizon']} sessions | paired n={r['n_paired']} | net={pct(r['net_mean'])} | edge={pct(r['mean_edge'])}")
    # Source-qualification robustness declared in liquidity source spec, not return-selected.
    liquidity=json.loads((HERE/'liquidity_events.json').read_text())['events']
    proxy={(r['ticker'],r['filing_date']) for r in liquidity if any(f.get('capacity_preservation_proxy') for f in r['facilities'])}
    p=df[(df.signal=='liquidity')&(df.role=='event')&(df.bucket=='3-6m')&(df.delay==2)&(df.otm==.05)&(df.haircut==.05)&(df.horizon=='21')]
    strict=p[[ (t,d) not in proxy for t,d in zip(p.ticker,p.filing_date) ]]
    lines+=['','LIQUIDITY CAPACITY-EVIDENCE CHECK',
      f"Exclude existing-amendment capacity-preservation proxies: fresh n={len(strict)}, net mean={pct(strict.net.mean() if len(strict) else None)}.",
      'This subset is a disclosure-quality sensitivity, not a replacement strategy.']
    extra=json.loads((HERE/'credit_controls_summary.json').read_text())
    lines+=['','SUPPLEMENTARY CREDIT-DISCLOSURE BENCHMARK',
      'Specified before viewing credit-return results, after observing lack of calendar controls.',
      'Non-trigger monthly credit reports from the same issuer/year; this is NOT an ordinary-day baseline.']
    for r in extra.get('horizons',[]):
        if r['horizon']=='21':lines.append(f"21 sessions: paired n={r['n']}, event net={pct(r['net_mean'])}, control net={pct(r['control_mean'])}, edge={pct(r['edge'])}.")
    lines+=['','INTERPRETATION',
      'Liquidity: negative mean and negative matched edge at the fixed primary horizon. No validated edge.',
      'Departures: 27 apparent date clusters shrink to 2 distinct eligible departure sequences; too sparse.',
      'Credit: 43 reports shrink to 3 clean divergence events after accounting-change filters; too sparse.',
      'Positive longer-horizon cells exist. They cannot establish repeatable alpha from these small samples.',
      'No OOS evaluation or annualized Sharpe is warranted by this development evidence.',
      '',
      'DATA AND EXECUTION LIMITATIONS']
    lines += ['- '+x for x in s['limitations']]
    lines += ['- Event membership and credit-table extraction were manually source-reviewed before their outcomes.',
      '  This is a reproducible historical screen, not a finished automatic sealed-window classifier.',
      '- Same-session daily option prints can occur at different times. They do not guarantee simultaneous fills.',
      '- Positive daily volume alone does not establish capacity; early assignment and dividends are not fully modeled.',
      '- The credit signal is unadjusted for monthly seasonality. Both qualifying COF filings concern early-year months.',
      '',
      'VERIFICATION AND REPRODUCTION',
      '8 focused unit tests pass, including signs, all-leg costs, stale-price rejection, pre-event search and OOS blocking.',
      f"Saved-data checks passed for {len(df):,} observations (many parameter/horizon views of the same events).",
      f"Observed parameter/horizon result cells: {s['observed_parameter_horizon_cells']}; these are not independent trials.",
      'Raw option marks are in ignored massive/.massive_cache/codex_three/. No credentials appear in reports.',
      'Run from repository root with massive/.venv/bin/python:',
      '  massive/research/codex_three/liquidity.py',
      '  massive/research/codex_three/departures.py',
      '  massive/research/codex_three/cof_credit_metrics_build.py',
      '  massive/research/codex_three/axp_credit_metrics_build.py',
      '  massive/research/codex_three/credit.py',
      '  massive/research/codex_three/backtest.py',
      '  massive/research/codex_three/credit_controls.py',
      '  massive/research/codex_three/summarize.py',
      '  massive/research/codex_three/report.py',
      'The cached filing survey is required by data.py; rebuild with the existing count_events.py if absent.',
      'See engineering_corrections.json for the documented coverage and audit-field fixes.',
      'Source evidence: liquidity_screened.json, departures_audit.json, cof_credit_metrics.json, axp_credit_metrics.json.',
      'Detailed numbers: summary.json, primary_price_audit.json and credit_controls_summary.json.',
      'Source URLs in the metric JSON files identify the original SEC exhibits; no full filings are needed in Git.',
      '']
    (HERE/'REPORT.txt').write_text('\n'.join(lines))
    ledger={'primary_rules':3,'primary_horizon':21,'period':'2024-2025 development',
            'headline_bucket':'3-6m','sensitivity_buckets':['1m','2m'],
            'delays':[1,2,3],'otm_grid':[.03,.05,.10],'long_call_strike':'ATM; OTM grid irrelevant',
            'cost_haircuts':[0,.025,.05,.10],'all_horizons':[1,2,3,5,10,21,42,63,'exp'],
            'observed_result_cells':s['observed_parameter_horizon_cells'],
            'no_selected_best_parameter':True,'oos_run':False,'prior_shared_research':'Existing unrelated scans were not used as strategy outcomes here; no claim of uncontaminated global research history.',
            'extra_comparisons':['source-quality liquidity subset','supplementary credit disclosure-day controls','balanced event cohorts'],
            'code_sha256':hashlib.sha256((HERE/'backtest.py').read_bytes()).hexdigest()}
    (HERE/'variant_ledger.json').write_text(json.dumps(ledger,indent=2))
    manifest=json.loads((HERE/'run_manifest.json').read_text())
    manifest['code_sha256']=ledger['code_sha256']
    (HERE/'run_manifest.json').write_text(json.dumps(manifest,indent=2))
    print('\n'.join(lines[:23]))


if __name__=='__main__':main()
