"""Independent event cash ledger and second-provider sensitivity, no new signals."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def main():
    df=pd.read_json(HERE/'daily.json').set_index('date')
    df.index=pd.to_datetime(df.index)
    errors=[]
    for name in ['pre_fomc_overnight','turn_month_overnight','all_overnight']:
        for bps in [1,3]:
            actual=[]
            for day,row in df.iterrows():
                if not row[name]:
                    actual.append(0.0);continue
                shares=1/row['prev_close']
                opening_cash=-1-bps/1e4
                ending_cash=shares*row['open']*(1-bps/1e4)
                dividend_cash=shares*row['dividend']
                carry=row['known_cash_yield']*row['holding_hours']/(365*24)
                actual.append(opening_cash+ending_cash+dividend_cash-carry)
            error=float(np.max(abs(np.array(actual)-df[f'{name}_cost{bps}'].to_numpy())))
            errors.append(error)
            assert error < 3e-9, (name,bps,error)
    dates=json.loads((HERE.parent/'calendar_data/dates.json').read_text())
    eligible=[x['date'] for x in dates if x.get('scheduled',True)]
    assert int(df['pre_fomc_overnight'].sum())==len(eligible)==133
    assert not df.loc['2020-03-18','pre_fomc_overnight']
    assert all(df.index[df.pre_fomc_overnight.astype(bool)].isin(pd.to_datetime(eligible)))
    assert (df['holding_hours']>0).all()
    # Sparse return panels and JSON rounding are checked against direct cash, never mids.
    alt=pd.DataFrame(json.loads((ROOT/'data/cache/world_cup/aggs_SPY.json').read_text()))
    alt.index=pd.to_datetime(alt['t'],unit='ms',utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None).dt.normalize()
    alt['prev_c']=alt.c.shift(1)
    d=df.join(alt[['o','c','prev_c']],how='inner')
    sensitivity={}
    for name in ['pre_fomc_overnight','turn_month_overnight']:
        net=d[name]*((d.o+d.dividend)/d.prev_c-1-d.funding_overnight-0.0001*(1+d.o/d.prev_c))
        original=d[name+'_cost1']
        sensitivity[name]={}
        for part,a,b in [('development','2010-01-01','2021-12-31'),('validation','2022-01-01','2023-12-31'),('holdout','2024-01-01','2026-10-02')]:
            x=net.loc[a:b];y=original.loc[a:b]
            sensitivity[name][part]={'sessions':len(x),'net_sharpe_massive':float(x.mean()/x.std(ddof=1)*np.sqrt(252)),
                'net_sharpe_yahoo_same_dates':float(y.mean()/y.std(ddof=1)*np.sqrt(252)),
                'net_pnl_difference_bps_allocated_capital':float((x-y).sum()*1e4)}
    out={'status':'passed','independent_max_cash_reconciliation_error':max(errors),'scheduled_event_count':len(eligible),
        'cancelled_March2020_excluded':True,'cross_provider_sensitivity':sensitivity,
        'limits':['Does not verify auction fills, quote capacity, or historical calendar announcement vintages.',
                  'Both provider OHLC sets may use differing opening/closing trade definitions; no price source selected by profitability.']}
    (HERE/'verification.json').write_text(json.dumps(out,indent=2))
    print(json.dumps(out,indent=2))


if __name__=='__main__':main()
