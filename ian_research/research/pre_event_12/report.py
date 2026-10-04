"""Render frozen outputs; no strategy or selection changes."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

from core import HERE,file_hash


def pct(v):return '—' if v is None or pd.isna(v) else f'{v*100:+.2f}%'
def money(v):return '—' if v is None else f'-${abs(v):,.0f}' if v < 0 else f'${v:,.0f}'
NAMES={'uncertainty':'High implied uncertainty','uncertainty_liquidity':'High uncertainty + liquidity recovery','jackpot':'Past earnings jackpot'}


def main():
    studies={p:json.loads((HERE/'outputs'/p/'summary.json').read_text()) for p in ['screen','validation']}
    rows=[]
    for period,j in studies.items():
        for r in j['results']:
            s=r['selected_net'];a=r['selected_market_adjusted'];b=r['selected_beta_adjusted'];p=r['portfolio']
            rows.append({'period':period,'strategy':r['strategy'],'hold_sessions':r['hold_sessions'],
                         'cost_multiplier':r['cost_multiplier'],'events':s['n'],'issuers':r['tickers'],
                         'mean_net':s.get('mean'),'mean_vs_SPY':a.get('mean'),'mean_beta_adjusted':b.get('mean'),
                         'win_rate':s.get('win_rate'),'median_net':s.get('median'),
                         'net_ci_low':s.get('ci95_week_cluster',[None,None])[0],
                         'net_ci_high':s.get('ci95_week_cluster',[None,None])[1],
                         'cash_pnl':p.get('pnl',0.),'cash_return':p.get('total_return',0.),
                         'max_drawdown':p.get('max_drawdown',0.),'sharpe':p.get('daily_sharpe_zero_cash_rate'),
                         'deployment':p.get('mean_deployed_fraction',0.),
                         'baseline_mean_net':r['baseline_net'].get('mean'),
                         'baseline_events':r['baseline_net']['n']})
    table=pd.DataFrame(rows);table.to_csv(HERE/'outputs/comparison.csv',index=False)
    lines=['# Pre-earnings ideas 1 and 2: backtest pilot',
           '', '**Result: no convincing alpha demonstrated.** The ten-session high-IV and earnings-jackpot base rules lost money in the later evaluation. The additional liquidity-recovery rule made money on only two later Nvidia trades. This is a small, coverage-selected pilot, not a broad-universe replication or proof that the underlying hypotheses cannot work.',
           '', '## Primary results', '',
           'Each event return is on the stock position, net of observed bid/ask spread, 1 bp adverse slippage per side and 0.5 bp fees per side. Cash P&L is a separate $100,000 unlevered portfolio with maximum $10,000 per position, whole shares and idle cash earning zero.',
           '', '| Evaluation | Rule | Trades / issuers | Mean net / trade | Mean net less SPY | Mean beta-adjusted | Cash P&L |',
           '|---|---|---:|---:|---:|---:|---:|']
    for r in rows:
        if r['hold_sessions']==10 and r['cost_multiplier']==1:
            period='2024' if r['period']=='screen' else '2025–Sep 2026'
            lines.append(f"| {period} | {NAMES[r['strategy']]} | {r['events']} / {r['issuers']} | {pct(r['mean_net'])} | {pct(r['mean_vs_SPY'])} | {pct(r['mean_beta_adjusted'])} | {money(r['cash_pnl'])} |")
    lines += ['', '2023 observations set feature thresholds only. No 2023 strategy P&L was evaluated. Code, inputs and parameters were hashed before the first 2024 result. Final audit found and repaired one calendar-boundary bug after the initial evaluations; both periods were rerun with the same trading rules and parameters. See [CALENDAR_REPAIR.md](CALENDAR_REPAIR.md) for the preserved originals and comparison. These years have been used elsewhere in this workspace, so the later period is temporal validation, not a pristine research holdout.',
              '', '![Validation cash portfolio P&L](outputs/validation_equity.png)',
              '', '## All declared variants', '',
              '| Period | Rule | Hold | Costs | Trades | Mean net | Cash P&L |',
              '|---|---|---:|---:|---:|---:|---:|']
    for r in rows:
        lines.append(f"| {r['period']} | {NAMES[r['strategy']]} | {r['hold_sessions']} | {r['cost_multiplier']:.0f}× | {r['events']} | {pct(r['mean_net'])} | {money(r['cash_pnl'])} |")
    lines += ['', 'The positive five-session jackpot result is one Shopify trade. It cannot rescue the negative ten-session primary result. The liquidity-recovery variant has three trades across both evaluation periods, all Nvidia. No parameter was changed to increase activity or improve these results.',
              '', '## Uncertainty and comparison', '',
              '| Later-period primary rule | Net mean 95% interval | Median net | Win rate | Cash max drawdown | Mean capital deployed | All eligible baseline net / trade |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        if r['period']=='validation' and r['hold_sessions']==10 and r['cost_multiplier']==1:
            lines.append(f"| {NAMES[r['strategy']]} | {pct(r['net_ci_low'])} to {pct(r['net_ci_high'])} | {pct(r['median_net'])} | {pct(r['win_rate'])} | {pct(r['max_drawdown'])} | {pct(r['deployment'])} | {pct(r['baseline_mean_net'])} ({r['baseline_events']} events) |")
    lines += ['', 'Intervals resample whole entry weeks, using 3,000 fixed-seed draws. They are not reliable evidence with one or two trades, and do not remove issuer/sector dependence. Market-adjusted returns subtract matched-window SPY total returns. Beta-adjusted returns subtract lagged OLS beta times SPY returns; this is a risk diagnostic, not a traded hedge or complete factor model.',
              '', '## Data and exclusions', '',
              '- The starting universe was the 150 most liquid names at December 2022, selected before the study. Original issuer announcements produced 110 completed scheduled earnings events across 14 issuers in 2023–September 2026. This is an archive-coverage sample; inaccessible archives and missing provider coverage materially limit representativeness.',
              '- Every accepted calendar notice was checked against its original body. 73 completed events also have exact-date matches to results press releases. A separate SEC earnings-exhibit dateline history supplies prior quarterly earnings dates. No filing-acceptance timestamp is treated as the earnings release timestamp.',
              '- After advance-notice timing and study-date filters, there are 191 event/window rows across 13 issuers: 89 ten-session and 102 five-session. The ten-session split is 28 calibration, 26 screen and 35 validation events. A notice must exist by the lagged signal time.',
              '- Of 192 retrieved option feature observations, 114 passed the fixed freshness/spread/maturity rules; one failed-IV observation belongs to the subsequently excluded future event. Quote coverage varies strongly by issuer. Missing IV was never replaced with realized volatility. All 3,165 stock quote inputs were retrieved successfully.',
              '- Actual market data came from the existing Massive subscription and cached stock data, not a new Databento purchase. No paid data credits were consumed.',
              '- Price data include splits and available dividends. The inherited company panel has retrospective entity/share-class mapping limitations and lacks a complete delisting-payment history. Present-day archived publication timestamps do not fully establish historical vendor ingestion or revision history.',
              '- No nearby contradictory release datelines were found in the independent schedule check. Unmatched releases are not proven free from early publication. Unscheduled news remains a risk.',
              '', '## Exact implementation', '',
              'See [SPECIFICATION.md](SPECIFICATION.md) for the rules frozen before outcomes. For an advertised release on session D, exit at D−1 15:55 ET; enter ten sessions earlier at 15:56 ET. The five-session secondary rule uses the same exit. Features are observed one session before entry. Early-close clocks are adjusted. Orders use the first valid subsequent NBBO, with whole-share capacity and actual fill timestamps.',
              '', 'The high-IV signal is an approximate constant-30-day ATM volatility reconstructed from historical call/put NBBOs and put-call parity. American exercise and a fixed 4% rate are approximations. The jackpot signal is the maximum market-adjusted three-session reaction among four prior verified releases, with availability and quarterly-cadence checks. Thresholds are fixed percentiles of 2023 calibration events, an adaptation of published cross-sectional sorts rather than an exact paper replication.',
              '', 'The liquidity extension uses only information available a minute before entry: spread must improve from the prior session and be no greater than its prior-20-session same-clock median; bid dollar depth must recover relative to both comparisons. No extended-hours execution was simulated. Therefore these results do not test whether premarket or after-hours trading offers an advantage.',
              '', '## Verification and reproducibility', '',
              '- Ten financial/timing regression tests and nine calendar-parser regression checks passed.',
              '- Tests cover bid/ask losses, split/dividend accounting, future-information exclusion, missing recent earnings, missing exits, future dates outside calendar coverage and delayed exits that cannot fund earlier entries.',
              '- No chosen trade was dropped for a bad realized return or unfavorable exit spread. Unresolved exits would stop evaluation. All simulated positions fit displayed entry size; selected exits also fit displayed bid size.',
              '- Independent QA reconciled all 256 return rows and 20 nonempty cash portfolios. All 22 unique selected event/window trades across variants exit before a verified actual release date; 14 of 128 unselected/selected evaluation baseline windows lack independently verified actual releases. See `options_final_verification.json`.',
              '- Inputs and implementation are recorded in `data/frozen_manifest.json`; all trade-level rows, equity paths, thresholds, counts and summaries are in `outputs/`.',
              '', '```sh', '.venv/bin/python research/pre_event_12/run.py --period screen', '.venv/bin/python research/pre_event_12/run.py --period validation', '.venv/bin/python research/pre_event_12/report.py', '```',
              '', 'The cached licensed inputs are required for reproduction and remain excluded from Git. Results do not justify live deployment. A broader historical announcement calendar, more issuers and a fresh validation period are needed before estimating a dependable edge.']
    (HERE/'REPORT.md').write_text('\n'.join(lines)+'\n')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,ax=plt.subplots(figsize=(10,4.8),layout='constrained')
    colors={'uncertainty':'#225ea8','uncertainty_liquidity':'#238b45','jackpot':'#cb181d'}
    for name in NAMES:
        p=HERE/f'outputs/validation/{name}_10d_cost1_equity.csv'
        d=pd.read_csv(p,parse_dates=['date']).set_index('date')
        ax.plot(d.index,d.equity-100000,label=NAMES[name],color=colors[name],linewidth=1.8)
    ax.axhline(0,color='#777777',linewidth=.7)
    ax.set_title('Pre-earnings pilot: later-period cash portfolio P&L',loc='left',fontweight='bold')
    ax.set_ylabel('P&L, USD');ax.grid(alpha=.18);ax.legend(loc='lower left',frameon=False)
    fig.text(.5,-.025,'2025–September 2026 · 100,000 USD cash · max 10,000 USD per position · ten-session holds · net of trading costs',ha='center',fontsize=8,color='#555555')
    fig.savefig(HERE/'outputs/validation_equity.png',dpi=160,bbox_inches='tight')
    plt.close(fig)
    print('Wrote REPORT.md, outputs/comparison.csv and outputs/validation_equity.png')


if __name__=='__main__':main()
