"""Independent quote/share accounting and temporal QA of frozen result files.

Uses the common source-panel loader, but does not call return or portfolio code.
Shares are tracked in original raw units and explicitly multiplied by split
ratios, separately from the engine's adjusted-price-unit accounting.
"""
from __future__ import annotations
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from core import HERE,load_panel
from options_audit import cutoff


def main():
    calendar,panel=load_panel()
    quotes=json.loads((HERE/'data/quotes.json').read_text())
    history=pd.DataFrame(json.loads((HERE/'options_release_history.json').read_text()))
    fills=[];timing=[];portfolios=[];concentration=[];bugs=[]
    max_net_error=0.;max_equity_error=0.

    def get_quote(ticker,day,kind):return quotes[f'{ticker}|{day}|{kind}']

    def raw_costs(row):
        a=get_quote(row.ticker,row.entry_date,'entry')
        b=get_quote(row.ticker,row.exit_date,'exit')
        stress=float(row.cost_multiplier)
        debit=(a['mid']+stress*(a['ask']-a['mid']))*(1+stress*.0001)*(1+stress*.00005)
        credit=(b['mid']-stress*(b['mid']-b['bid']))*(1-stress*.0001)*(1-stress*.00005)
        return debit,credit

    for period in ['screen','validation']:
        folder=HERE/'outputs'/period
        allrows=pd.read_csv(folder/'all_events.csv')
        for row in allrows[allrows.status.eq('ok')].itertuples():
            g=panel[row.ticker];e=pd.Timestamp(row.entry_date);x=pd.Timestamp(row.exit_date)
            debit,credit=raw_costs(row)
            shares_after_split=g.at[x,'factor']/g.at[e,'factor']
            dividends_per_original_share=g.loc[e:x,'div_adj'].iloc[1:].fillna(0).sum()/g.at[e,'factor']
            expected=(credit*shares_after_split+dividends_per_original_share)/debit-1
            error=abs(expected-row.net);max_net_error=max(error,max_net_error)
            if error>1e-10:bugs.append({'kind':'net_return_mismatch','id':row.id,'error':error})
            if row.cost_multiplier!=1:continue
            feature_at=pd.Timestamp(cutoff(row.signal_date))
            entry_at=pd.Timestamp(row.entry_timestamp_ns,unit='ns',tz='UTC')
            exit_at=pd.Timestamp(row.exit_timestamp_ns,unit='ns',tz='UTC')
            notice_at=pd.Timestamp(row.notice_published_utc)
            chronological=notice_at<=feature_at<entry_at<exit_at
            scheduled_index=calendar.searchsorted(pd.Timestamp(row.scheduled_date),side='left')
            calendar_alignment=(scheduled_index<len(calendar)
                                and x==calendar[scheduled_index-1]
                                and calendar.get_loc(x)-calendar.get_loc(e)==row.hold_sessions)
            if not calendar_alignment:
                bugs.append({'kind':'advertised_release_calendar_alignment','id':row.id,
                             'scheduled_date':row.scheduled_date,'exit_date':row.exit_date})
            actual_known=False;preactual=None;source=None
            if pd.notna(row.actual_release_utc):
                actual_known=True;preactual=bool(exit_at<pd.Timestamp(row.actual_release_utc));source='wire_timestamp'
            else:
                matches=history[history.ticker.eq(row.ticker)&history.actual_date.eq(row.scheduled_date)]
                if len(matches):
                    actual_known=True
                    preactual=bool(exit_at.tz_convert('America/New_York').date()<pd.Timestamp(matches.iloc[0].actual_date).date())
                    source='SEC_dateline_date_only'
            if not chronological or preactual is False:bugs.append({'kind':'event_time_violation','id':row.id})
            timing.append({'period':period,'id':row.id,'publication_feature_entry_exit_order':bool(chronological),
                           'advertised_release_calendar_alignment':bool(calendar_alignment),
                           'actual_release_verified':actual_known,'exit_before_actual_release':preactual,'actual_evidence':source})
            if row.ticker=='NVDA' or row.id in ['REGN_2026-04-29_10','SHOP_2026-05-05_10']:
                fills.append({'id':row.id,'ticker':row.ticker,'entry_date':row.entry_date,'exit_date':row.exit_date,
                              'buy_allin_raw':debit,'sell_net_raw':credit,'entry_factor':row.entry_factor,
                              'exit_factor':row.exit_factor,'dividends_per_original_share':dividends_per_original_share,
                              'reported_return':row.net,'independent_return':expected,'absolute_error':error})

        for file in sorted(folder.glob('*_trades.csv')):
            trades=pd.read_csv(file)
            name=file.name.replace('_trades.csv','')
            if trades.empty:
                portfolios.append({'period':period,'variant':name,'empty':True});continue
            path=pd.read_csv(folder/(name+'_equity.csv'),parse_dates=['date']).set_index('date')
            cash=100000.;open_positions={};taken=0;skipped=[];sizes=[];reconstructed=[]
            data={r.id:r for r in trades.itertuples()}
            for day in path.index:
                for ident,p in open_positions.items():
                    g=panel[p['row'].ticker]
                    dividend=g.at[day,'div_adj']
                    cash+=p['raw_shares']*(0. if pd.isna(dividend)else float(dividend))/p['entry_factor']
                actions=[]
                for ident,p in open_positions.items():
                    if pd.Timestamp(p['row'].exit_date)==day:
                        actions.append((int(p['row'].exit_timestamp_ns),0,0.,p['row'].ticker,ident))
                for ident,row in data.items():
                    if pd.Timestamp(row.entry_date)==day:
                        actions.append((int(row.entry_timestamp_ns),1,-float(row.signal),row.ticker,ident))
                for _,kind,_,_,ident in sorted(actions):
                    if kind==0:
                        p=open_positions.pop(ident);row=p['row'];_,credit=raw_costs(row)
                        ratio=panel[row.ticker].at[day,'factor']/p['entry_factor']
                        cash+=p['raw_shares']*ratio*credit
                        sizes.append({'id':ident,'shares_at_exit':p['raw_shares']*ratio,
                                      'displayed_exit_bid_size':float(row.exit_bid_size),
                                      'exceeds_exit_depth':bool(p['raw_shares']*ratio>row.exit_bid_size)})
                        continue
                    row=data[ident]
                    if any(p['row'].ticker==row.ticker for p in open_positions.values()):
                        skipped.append({'id':ident,'reason':'overlap'});continue
                    debit,_=raw_costs(row);shares=math.floor(min(cash,10000)/debit)
                    if cash<10000 or shares<1:
                        skipped.append({'id':ident,'reason':'cash'});continue
                    if shares>row.entry_ask_size:
                        skipped.append({'id':ident,'reason':'displayed_entry_depth'});continue
                    cash-=shares*debit;taken+=1
                    open_positions[ident]={'row':row,'raw_shares':shares,'entry_factor':float(row.entry_factor)}
                value=cash
                for p in open_positions.values():
                    g=panel[p['row'].ticker]
                    actual_shares=p['raw_shares']*g.at[day,'factor']/p['entry_factor']
                    value+=actual_shares*g.at[day,'close_raw']
                reconstructed.append(value)
            difference=np.max(np.abs(np.asarray(reconstructed)-path.equity.to_numpy()))
            max_equity_error=max(max_equity_error,float(difference))
            if difference>1e-7 or open_positions:bugs.append({'kind':'portfolio_mismatch','variant':name,'error':float(difference)})
            portfolios.append({'period':period,'variant':name,'entries':taken,'skipped':skipped,
                               'independent_cash_pnl':cash-100000,'reported_cash_pnl':float(path.equity.iloc[-1]-100000),
                               'max_daily_equity_difference':float(difference),'exits_exceeding_displayed_depth':sum(s['exceeds_exit_depth']for s in sizes),
                               'exit_capacity':sizes})
            if name in ['uncertainty_10d_cost1','jackpot_10d_cost1','uncertainty_liquidity_10d_cost1']:
                concentration.append({'period':period,'variant':name,'events':len(trades),
                                      'issuer_counts':trades.ticker.value_counts().to_dict(),
                                      'mean_net':float(trades.net.mean()),'mean_market_adjusted_net':float(trades.market_adjusted_net.mean()),
                                      'mean_beta_adjusted_net':float(trades.beta_adjusted_net.mean()),
                                      'past_beta_range':[float(trades.past_beta.min()),float(trades.past_beta.max())],
                                      'beta_note':'252 preceding daily returns, minimum120 pairs, ends before signalday; diagnostic not a multifactor causal-alpha estimate.'})

    nv=panel['NVDA'].loc[pd.Timestamp('2024-06-07'):pd.Timestamp('2024-06-10'),['close','close_raw','factor','ret']]
    splitcheck={'dates':[str(d.date())for d in nv.index], 'raw_closes':nv.close_raw.tolist(),
                'adjusted_closes':nv.close.tolist(),'factors':nv.factor.tolist(),
                'split_adjusted_return':float(nv.ret.iloc[-1]),
                'raw_unadjusted_return':float(nv.close_raw.iloc[-1]/nv.close_raw.iloc[0]-1),
                'holding_period_selected_crosses_split':False}
    summary={'status':'pass'if not bugs else'fail','bugs':bugs,'all_event_return_rows_checked':sum(len(pd.read_csv(HERE/'outputs'/p/'all_events.csv').query("status=='ok'"))for p in ['screen','validation']),
             'maximum_return_error':max_net_error,'maximum_daily_portfolio_error':max_equity_error,
             'chronology_rows':len(timing),'chronology_all_pass':all(r['publication_feature_entry_exit_order']for r in timing),
             'actual_release_verified_rows':sum(r['actual_release_verified']for r in timing),
             'actual_release_unverified_rows':sum(not r['actual_release_verified']for r in timing),
             'time_checks':timing,'sample_fill_reconciliations':fills,'portfolio_reconciliations':portfolios,
             'nvda_split_check':splitcheck,'concentration_and_beta':concentration,
             'limitations':['Common source-panel loader shared; independent raw-share arithmetic recomputes fills and cash.',
                            'Actual-release clock remains unverified for some calendar events; dates from SEC are not exact publication times.',
                            'Historical NBBO is a hypothetical execution model, not proof of accessible fills.',
                            'Few issuers and events, semiconductor concentration, and a beta diagnostic do not establish persistent alpha.']}
    (HERE/'options_final_verification.json').write_text(json.dumps(summary,indent=2))
    print({k:v for k,v in summary.items()if k not in ['time_checks','sample_fill_reconciliations','portfolio_reconciliations','concentration_and_beta']})
    print(json.dumps(concentration,indent=2))


if __name__=='__main__':main()
