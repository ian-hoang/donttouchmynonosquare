"""Fixed calendar-premium screen. Does not place orders or download data."""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np
import pandas as pd
import statsmodels.api as sm

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
TZ = 'America/New_York'
SPLITS = {'development': ('2010-01-01', '2021-12-31'),
          'validation': ('2022-01-01', '2023-12-31'),
          'holdout': ('2024-01-01', '2026-10-02')}


def load_prices():
    src = HERE.parent / 'sectors/data/SPY.json'
    j = json.loads(src.read_text())['chart']['result'][0]
    assert not j.get('events', {}).get('splits'), 'Split handling required'
    dates = pd.to_datetime(j['timestamp'], unit='s', utc=True).tz_convert(TZ).tz_localize(None).normalize()
    df = pd.DataFrame(j['indicators']['quote'][0], index=dates).sort_index()
    assert not df.index.duplicated().any()
    assert df[['open','close']].notna().all().all()
    assert (df[['open','close']] > 0).all().all()
    div = {}
    for v in j.get('events', {}).get('dividends', {}).values():
        day = pd.Timestamp(v['date'], unit='s', tz='UTC').tz_convert(TZ).tz_localize(None).normalize()
        div[day] = div.get(day, 0) + v['amount']
    df['dividend'] = pd.Series(div).reindex(df.index).fillna(0)
    df['prev_close'] = df['close'].shift(1)
    df['gross_overnight'] = (df['open'] + df['dividend']) / df['prev_close'] - 1
    df['gross_daily'] = (df['close'] + df['dividend']) / df['prev_close'] - 1
    return df


def features(df, fomc_dates):
    idx = df.index
    month = idx.to_period('M')
    rank = pd.Series(np.arange(len(idx)), index=idx).groupby(month).cumcount() + 1
    remaining = pd.Series(np.arange(len(idx)), index=idx).groupby(month).cumcount(ascending=False)
    df = df.copy()
    df['pre_fomc_overnight'] = idx.isin(pd.to_datetime(fomc_dates)).astype(int)
    df['turn_month_overnight'] = ((rank <= 3) | (remaining == 0)).astype(int)
    # The final partial month must not masquerade as a known month end.
    if idx[-1].day < 25:
        df.loc[idx[-1], 'turn_month_overnight'] = int(rank.iloc[-1] <= 3)
    df['all_overnight'] = 1
    return df


def early_close(day):
    return ((day.month == 11 and day.weekday() == 4 and 23 <= day.day <= 29)
            or (day.month == 7 and day.day == 3)
            or (day.month == 12 and day.day == 24))


def funding(df):
    y = pd.read_csv(HERE.parent/'sectors/data/DGS3MO.csv')
    y = pd.Series(pd.to_numeric(y['DGS3MO'], errors='coerce').to_numpy()/100,
                  index=pd.to_datetime(y.iloc[:, 0])).dropna().sort_index()
    days = df.index
    rates, hours, day_rates = [], [], []
    for i, day in enumerate(days):
        prev = days[i-1] if i else day-pd.Timedelta(days=1)
        known = y.loc[y.index < prev]
        rate = known.iloc[-1] if len(known) else np.nan
        close_hour = 13 if early_close(prev) else 16
        a = (prev+pd.Timedelta(hours=close_hour)).tz_localize(TZ)
        b = (day+pd.Timedelta(hours=9,minutes=30)).tz_localize(TZ)
        h = (b-a).total_seconds()/3600
        rates.append(rate); hours.append(h)
        day_rates.append(rate*(day-prev).days/365)
    df = df.copy()
    df['known_cash_yield'] = rates
    df['holding_hours'] = hours
    df['funding_overnight'] = df['known_cash_yield']*df['holding_hours']/(365*24)
    df['cash_daily'] = day_rates
    return df


def metrics(r, active, gross, costweight, seed):
    r = r.astype(float)
    n = len(r); sd = r.std(ddof=1)
    sharpe = r.mean()/sd*np.sqrt(252) if sd > 0 else None
    fit = sm.OLS(r.to_numpy(), np.ones((n,1))).fit(cov_type='HAC',cov_kwds={'maxlags':5})
    rng = np.random.default_rng(seed)
    boot = []
    v = r.to_numpy(); blocks = int(np.ceil(n/20))
    for _ in range(2000):
        pos = ((rng.integers(0,n,size=blocks)[:,None]+np.arange(20))%n).ravel()[:n]
        z=v[pos]; s=z.std(ddof=1)
        if s>0: boot.append(z.mean()/s*np.sqrt(252))
    wealth = np.r_[0,np.cumsum(v)]
    count=int(active.sum())
    return {'days': n, 'trades': count, 'sharpe':sharpe,
            'annual_mean_excess':float(252*r.mean()),
            'annual_vol':float(sd*np.sqrt(252)),
            'net_bps_per_trade':float(r.sum()/count*1e4) if count else None,
            'max_drawdown_allocated_capital':float((wealth-np.maximum.accumulate(wealth)).min()),
            'hac_t':float(fit.tvalues[0]), 'hac_p_two_sided':float(fit.pvalues[0]),
            'sharpe_ci95':list(np.quantile(boot,[.025,.975])) if boot else None,
            'break_even_per_side_bps':float(gross.sum()/costweight.sum()*1e4) if costweight.sum() else None}


def main():
    spec = json.loads((HERE/'PROTOCOL.json').read_text())
    event_path = HERE.parent/'calendar_data/dates.json'
    obj = json.loads(event_path.read_text())
    events = obj['events'] if isinstance(obj,dict) else obj
    dates = [v['date'] for v in events if v.get('scheduled', True)]
    full = funding(features(load_prices(), dates))
    df = full.loc['2010-01-01':'2026-10-02'].copy()
    assert df[['gross_overnight','funding_overnight','cash_daily']].notna().all().all()
    result = {'status':'historical_assumed_execution_screen', 'spec':spec,
              'source_hashes':{}, 'results':{}, 'calendar_diagnostics':{}}
    for p in [HERE/'PROTOCOL.json',event_path,HERE.parent/'sectors/data/SPY.json',HERE.parent/'sectors/data/DGS3MO.csv']:
        result['source_hashes'][str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    df['overnight_excess'] = df['gross_overnight']-df['funding_overnight']
    df['spy_excess'] = df['gross_daily']-df['cash_daily']
    for strategy in ['pre_fomc_overnight','turn_month_overnight','all_overnight']:
        active=df[strategy]
        costweight=active*(1+df['open']/df['prev_close'])
        gross=active*df['overnight_excess']
        df[strategy+'_gross_excess']=gross
        for bps in [1,3]:
            name=strategy+f'_cost{bps}'
            df[name]=gross-bps/1e4*costweight
            result['results'][name]={}
            for k,(a,b) in SPLITS.items():
                cut=df.loc[a:b].index
                m=metrics(df.loc[cut,name],active.loc[cut],gross.loc[cut],costweight.loc[cut],420077)
                spy=sm.OLS(df.loc[cut,name],sm.add_constant(df.loc[cut,'spy_excess'])).fit(cov_type='HAC',cov_kwds={'maxlags':5})
                m.update({'market_beta':float(spy.params['spy_excess']),
                          'market_adjusted_alpha_annual':float(spy.params['const']*252),
                          'market_adjusted_alpha_hac_t':float(spy.tvalues['const'])})
                result['results'][name][k]=m
        # Annual rows include all session/flat days.
    for k,(a,b) in SPLITS.items():
        d=df.loc[a:b]
        X=d[['pre_fomc_overnight','turn_month_overnight']].astype(float)
        for wd in range(1,5): X[f'weekday_{wd}']=(d.index.weekday==wd).astype(float)
        fit=sm.OLS(d['overnight_excess'],sm.add_constant(X)).fit(cov_type='HAC',cov_kwds={'maxlags':5})
        result['calendar_diagnostics'][k]={'coef':fit.params.to_dict(),'hac_t':fit.tvalues.to_dict()}
    result['spy_buy_hold_diagnostic'] = {}
    result['paired_net_vs_all_overnight'] = {}
    for k,(a,b) in SPLITS.items():
        d=df.loc[a:b]
        z=d['spy_excess']
        f=sm.OLS(z, np.ones((len(z),1))).fit(cov_type='HAC',cov_kwds={'maxlags':5})
        result['spy_buy_hold_diagnostic'][k]={'sharpe':float(z.mean()/z.std(ddof=1)*np.sqrt(252)),
            'annual_mean_excess':float(z.mean()*252),'hac_t':float(f.tvalues.iloc[0]),
            'note':'Buy-and-hold ignores initial/final commissions; total-return daily risk differs from sparse overnight exposure.'}
        result['paired_net_vs_all_overnight'][k]={}
        for strategy in ['pre_fomc_overnight','turn_month_overnight']:
            z=d[strategy+'_cost1']-d['all_overnight_cost1']
            f=sm.OLS(z,np.ones((len(z),1))).fit(cov_type='HAC',cov_kwds={'maxlags':5})
            result['paired_net_vs_all_overnight'][k][strategy]={'annual_mean_difference':float(z.mean()*252),
                'hac_t':float(f.tvalues.iloc[0]),'note':'Difference includes less market exposure and fewer trading costs; calendar regression is the incremental signal diagnostic.'}
    columns=[x for x in df if '_cost' in x]
    result['annual_pnl_fixed_capital']=df[columns].groupby(df.index.year).sum().to_dict()
    # Cross-provider raw prices are only a diagnostic, not an alternate selected backtest.
    massive=pd.DataFrame(json.loads((ROOT/'data/cache/world_cup/aggs_SPY.json').read_text()))
    massive.index=pd.to_datetime(massive['t'],unit='ms',utc=True).dt.tz_convert(TZ).dt.tz_localize(None).dt.normalize()
    joined=df[['open','close']].join(massive[['o','c']],how='inner')
    dif=np.maximum(abs(joined['open']/joined['o']-1),abs(joined['close']/joined['c']-1))*1e4
    result['cross_provider']={'sessions':len(joined),'median_max_ohlc_difference_bps':float(dif.median()),
                              'max_difference_bps':float(dif.max()),'sessions_above_1bp':int((dif>1).sum())}
    result['limits']=['Auction prices plus assumed slippage, not actual fills or capacity.',
                      'Historical meeting calendars lack original publication vintages.',
                      'DGS3MO is a cash proxy; dividend pay-date financing omitted.',
                      'Calendar is reconstructed, including special closures; no claim of perfect historical calendar knowledge.',
                      'These two rules and four other batch candidates count as multiple trials.']
    rows=df.reset_index(names='date'); rows['date']=rows['date'].dt.strftime('%Y-%m-%d')
    (HERE/'daily.json').write_text(rows.to_json(orient='records'))
    (HERE/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    for name, periods in result['results'].items():
        print(name,{k:{'sharpe':round(v['sharpe'],3),'trades':v['trades'],'net_bps_per_trade':round(v['net_bps_per_trade'],2)} for k,v in periods.items()})


if __name__=='__main__': main()
