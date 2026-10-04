"""Same fixed rule, same dates and dividends, second OHLC vendor. No fitting."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
import study

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
MASSIVE=ROOT/'data'/'cache'/'world_cup'/'aggs_SPY.json'

def adjusted_signal_index(df):
    """Causal counterpart of cash-dividend price back-adjustment.

    Yahoo-style historical adjustment applies the factor 1-D_t/C_(t-1)
    to older prices. The causal relative change is C_t/(C_(t-1)-D_t).
    Preserve native Yahoo adjusted levels during2004 warmup; future
    multiplicative rescalings do not affect any of this rule's signals.
    The cash ledger still credits actual recorded dividend cash separately.
    """
    z=df.copy();values=z.adjusted.copy()
    for i in np.flatnonzero(z.index>=pd.Timestamp('2005-01-01')):
        prev=z.close.iloc[i-1];div=z.dividend.iloc[i]
        if prev-div<=0:raise ValueError('Invalid dividend adjustment')
        values.iloc[i]=values.iloc[i-1]*z.close.iloc[i]/(prev-div)
    z['adjusted']=values
    z['underlying_total_return']=(z.close+z.dividend)/z.close.shift(1)-1
    return z

def trade_compare(a,b):
    aa={(x['entry_date'],x['exit_date'],x['exit_reason']) for x in a}
    bb={(x['entry_date'],x['exit_date'],x['exit_reason']) for x in b}
    return {'same_closed_trade_timings':len(aa&bb),'only_first':sorted(aa-bb),'only_second':sorted(bb-aa)}

def main():
    original=study.load()
    raw=pd.DataFrame(json.loads(MASSIVE.read_text()))
    raw.index=pd.to_datetime(raw.t,unit='ms',utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None).dt.normalize()
    raw=raw.rename(columns={'o':'open','h':'high','l':'low','c':'close','v':'volume'}).sort_index()
    if raw.index.has_duplicates:raise ValueError('Duplicate Massive dates')
    start=raw.index.min();end=raw.index.max()
    yahoo=original.loc[:end].copy();match=yahoo.loc[start:end].index
    if not match.equals(raw.index):raise ValueError('Provider session dates differ; refusing silent intersection selection')
    massive=yahoo.copy();massive['volume']=massive.volume.astype(float)
    massive.loc[match,['open','high','low','close','volume']]=raw[['open','high','low','close','volume']].to_numpy()
    inputs={'yahoo_native_adjustment':yahoo,'yahoo_causal_adjustment':adjusted_signal_index(yahoo),'massive_causal_adjustment':adjusted_signal_index(massive)}
    periods={'development':['2005-01-01','2021-12-31'],'validation':['2022-01-01','2023-12-31'],'holdout_overlap':['2024-01-01',str(end.date())]}
    runs={};results={}
    for name,frame in inputs.items():
        base,trades,opened=study.simulate(frame,1);stress,_,_=study.simulate(frame,3)
        runs[name]=(base,trades,opened)
        results[name]={'periods':{p:{'base':study.stats(base.loc[a:b]),'stress':study.stats(stress.loc[a:b])} for p,(a,b) in periods.items()},'closed_trades':len(trades),'final_open_trade':opened,'final_pending_action':base.pending_next_open.iloc[-1]}
    comparisons={}
    for a,b in [('yahoo_native_adjustment','yahoo_causal_adjustment'),('yahoo_causal_adjustment','massive_causal_adjustment'),('yahoo_native_adjustment','massive_causal_adjustment')]:
        x=runs[a][0];y=runs[b][0]
        p=trade_compare(runs[a][1],runs[b][1]);p['holdout_closed_trade_timings']=trade_compare([t for t in runs[a][1] if t['entry_date']>='2024-01-01'],[t for t in runs[b][1] if t['entry_date']>='2024-01-01'])
        p['all_session_action_differences']=int((x.action!=y.action).sum())
        p['holdout_action_differences']=int((x.loc['2024-01-01':].action!=y.loc['2024-01-01':].action).sum())
        p['holdout_excess_sharpe_difference_second_minus_first']=results[b]['periods']['holdout_overlap']['base']['excess_sharpe']-results[a]['periods']['holdout_overlap']['base']['excess_sharpe']
        comparisons[a+'_versus_'+b]=p
    prices={k:{'median_absolute_difference_bps':float(((raw[k]/yahoo.loc[match,k]-1).abs()*10000).median()),'max_absolute_difference_bps':float(((raw[k]/yahoo.loc[match,k]-1).abs()*10000).max())} for k in ['open','close']}
    result={'purpose':'Cross-provider sensitivity of the already frozen eighth hypothesis; no new rules or parameter selection. All feeds reported without choosing the better result.','overlap':{'start':str(start.date()),'end':str(end.date()),'sessions':len(match),'holdout_start':'2024-01-01','holdout_sessions':len(match[match>=pd.Timestamp('2024-01-01')])},'signal_adjustment':'Native Yahoo retained as reference. Both causal indexes use adjusted_index[t]=adjusted_index[t-1]*close[t]/(close[t-1]-recorded_ex_date_dividend[t]), the forward-recursive counterpart of dividend price adjustment. Actual P&L always uses raw prices and separate dividend cash; indicators never use future prices.','warmup':'Yahoo2004 raw/adjusted history retained in both feeds; fromJan3,2005 onward each reconstructed index uses its own OHLC with the same recorded Yahoo dividend events.','limitations':['Massive cache is a raw daily OHLC aggregate list, without a retained response envelope documenting original adjusted flag; SPY has no recorded splits over this period.','This isolates OHLC-vendor sensitivity, not fully independent dividend or risk-free-rate provenance.','Yahoo2004 warmup makes the Massive test hybrid for early2005 signals.','Ex-date dividend cash-credit and assumed1bp/3bp fills remain the original approximations; this is not an executable auction-fill/capacity test.','Both price histories are current downloads or caches, not preserved contemporaneous vintages.','Original selected candidate failedvalidation; cross-provider agreement does not cure research selection, insignificant alpha, or failed frozen gate.'],'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [MASSIVE,study.SOURCE/'SPY.json',study.SOURCE/'DGS3MO.csv',HERE/'PROTOCOL.json',HERE/'study.py',HERE/'price_source_sensitivity.py']},'price_comparison':prices,'results':results,'trade_comparisons':comparisons}
    (HERE/'price_source_sensitivity.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    for n,r in results.items():
        h=r['periods']['holdout_overlap'];v=r['periods']['validation']
        print(n,'validation Sharpe',v['base']['excess_sharpe'],'holdout Sharpe',h['base']['excess_sharpe'],'stress',h['stress']['excess_sharpe'],'holdout entries',h['base']['entry_count'],'alpha p',h['base']['market_alpha_hac_p'])
    print('Comparisons',json.dumps(comparisons))

if __name__=='__main__':main()
