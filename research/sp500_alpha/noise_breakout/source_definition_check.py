"""Single source-definition comparison; declared after first frozen results, never a rescue."""
from pathlib import Path
import json,datetime,hashlib
import numpy as np
import pandas as pd
from run import HERE,RAW,payload,load,simulate_day,excluded,stats

def main():
    protocol={'frozen_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'one post-source-audit correctness comparison, not pristine primary and not parameter optimization','source':'https://concretumgroup.com/python-backtesting-beat-the-market-an-effective-intraday-momentum-strategy-for-the-sp500-etf-spy/','change':'Use cumulativevolume-weightedHLC3 asauthorimplementation; reducepreviousdailyclosebycurrentexdatecashdividend. Allotherfrozenrulesandcostsunchanged. Preserveoriginalresults.','motivation':'Read after reviewerobservedvendorvwoutsideOHLC. Suchmismatchcanbelegitimateeligibilitydifference; notproofofcorruption. AuthorVWAPdefinitiondiffersfrominitialinterpretation.','limitation':'HistoricalRESTfinalOHLCVmayincludelatecorrections; this doesnotestablishsignal-timeavailability.'}
    pp=HERE/'SOURCE_DEFINITION_PROTOCOL.json'
    if not pp.exists():pp.write_text(json.dumps(protocol,indent=2)+'\n')
    d,m,n,p,v=load();cv=np.cumsum(np.nan_to_num(m['v']),axis=1);alt=np.cumsum(np.nan_to_num((m['h']+m['l']+m['c'])/3*m['v']),axis=1)/np.where(cv>0,cv,np.nan)
    divs=pd.DataFrame(payload(RAW/'dividends.json.gz')['results']);div=divs.assign(date=pd.to_datetime(divs.ex_dividend_date)).groupby('date').cash_amount.sum().reindex(d.index,fill_value=0)
    outside=np.isfinite(m['vw'])&((m['vw']<m['l'])|(m['vw']>m['h']))
    rows=[]
    for j,date in enumerate(d.index):
        if date<pd.Timestamp('2015-01-01') or date>pd.Timestamp('2026-10-02'):continue
        row={'date':str(date.date()),'benchmark_excess':float(d.benchmark_total.iloc[j]-d.rf_lagged.iloc[j])}
        for bp in [1,3]:
            if excluded(date):r={'net_before_carry':0,'borrow':0,'capital_minutes':0,'entries':0,'unresolved':False}
            else:r=simulate_day(m['o'][j],m['c'][j],n[j],p[j],alt[j],float(d.c.iloc[j-1]-div.iloc[j]),bp)
            assert not r['unresolved'],str(date)
            funding=d.rf_annual_lagged.iloc[j]/365*r['capital_minutes']/1440
            row['excess' if bp==1 else 'stress_excess']=float(r['net_before_carry']-r['borrow']-funding)
            if bp==1:row['entries']=int(r['entries'])
        rows.append(row)
    f=pd.DataFrame(rows).set_index('date');f.index=pd.to_datetime(f.index)
    periods={'development':('2015-01-01','2021-12-31'),'validation':('2022-01-01','2023-12-31'),'historical_holdout':('2024-01-01','2026-10-02'),'post_revision_descriptive':('2025-09-23','2026-10-02'),'full':('2015-01-01','2026-10-02')}
    results={}
    for name,(start,end) in periods.items():
        g=f.loc[start:end];results[name]={'base':stats(g.excess,g.benchmark_excess),'stress3bp':stats(g.stress_excess,g.benchmark_excess),'entries':int(g.entries.sum())}
    baseline=pd.DataFrame(json.loads((HERE/'daily.json').read_text())).set_index('date');baseline.index=pd.to_datetime(baseline.index)
    results['comparison']={'changed_return_days':int((np.abs(f.excess-baseline.excess)>1e-10).sum()),'correlation':float(f.excess.corr(baseline.excess)),'total_minute_vw_outside_ohlc':int(outside.sum()),'total_minute_vw_finite':int(np.isfinite(m['vw']).sum()),'no_unresolved':True,'protocol_sha256':hashlib.sha256(pp.read_bytes()).hexdigest()}
    (HERE/'source_definition_daily.json').write_text(json.dumps(rows,indent=2)+'\n');(HERE/'source_definition_results.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results,indent=2))
if __name__=='__main__':main()
