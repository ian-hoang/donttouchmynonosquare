"""Build event windows and lagged signals without computing strategy returns."""
import json
from pathlib import Path

import pandas as pd

from core import HERE, dates_for_event, load_panel, prior_jackpot
from options_audit import cutoff


def main():
    cal,panel=load_panel()
    notices=pd.read_csv(HERE/'events_confirmed.csv')
    history=json.loads((HERE/'options_release_history.json').read_text())
    if isinstance(history,dict):
        history=history.get('releases',history.get('rows',[]))
    hist=pd.DataFrame(history)
    if 'release_date' not in hist:
        hist['release_date']=hist['actual_date']
    rows=[];excluded=[]
    for notice in notices.to_dict('records'):
        ticker=notice['ticker']
        release=notice.get('scheduled_date',notice.get('scheduled_release_date'))
        for hold in [10,5]:
            key=f'{ticker}_{release}_{hold}'
            if pd.Timestamp(release)>pd.Timestamp('2026-09-30'):
                excluded.append({'id':key,'reason':'release_after_study'});continue
            dates=dates_for_event(cal,release,hold)
            if dates is None:
                excluded.append({'id':key,'reason':'calendar_coverage'});continue
            if dates['entry_date']<pd.Timestamp('2023-01-01') or dates['exit_date']>pd.Timestamp('2026-09-30'):
                excluded.append({'id':key,'reason':'outside_study'});continue
            observed=pd.Timestamp(cutoff(str(dates['signal_date'].date())))
            if pd.Timestamp(notice['notice_published_utc'])>observed:
                excluded.append({'id':key,'reason':'notice_not_known_by_signal'});continue
            jackpot,past=prior_jackpot(ticker,dates['signal_date'],hist,panel)
            year=dates['entry_date'].year
            row=dict(notice)|{k:str(v.date()) for k,v in dates.items()}
            row.update(id=key,hold_sessions=hold,jackpot=jackpot,
                       jackpot_reactions=json.dumps(past),
                       period='calibration' if year==2023 else 'screen' if year==2024 else 'validation')
            rows.append(row)
    out=HERE/'data';out.mkdir(exist_ok=True)
    frame=pd.DataFrame(rows).drop_duplicates('id').sort_values(['entry_date','ticker','hold_sessions'])
    frame.to_csv(out/'windows.csv',index=False)
    (out/'window_exclusions.json').write_text(json.dumps(excluded,indent=2))
    inputs=frame[['ticker','signal_date']].drop_duplicates().to_dict('records')
    (out/'iv_inputs.json').write_text(json.dumps(inputs,indent=2))
    print('Prepared windows, without forward returns:',len(frame),'tickers',frame.ticker.nunique())
    print(frame.groupby(['hold_sessions','period']).agg(events=('id','size'),jackpot_valid=('jackpot','count')).to_string())
    print('Excluded:',pd.Series([x['reason'] for x in excluded]).value_counts().to_dict())


if __name__=='__main__':main()
