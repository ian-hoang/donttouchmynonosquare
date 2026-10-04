import numpy as np
import pandas as pd
from run import simulate_day

def fixtures():
    return np.ones(390)*100,np.ones(390)*100,np.ones(390)*.01,np.ones(390,dtype=bool),np.ones(390)*100

def test_flat():
    a=fixtures();r=simulate_day(*a,100,1,True)
    assert r['net_before_carry']==0 and r['entries']==0 and not r['unresolved']

def test_long_exact_cashflow():
    o,c,n,p,v=fixtures();c[:]=103;o[31:]=110;o[389]=121
    r=simulate_day(o,c,n,p,v,100,1,True)
    q=1/(110*1.0001)
    expected=q*(121-110)-q*(110+121)*.0001
    assert np.isclose(r['net_before_carry'],expected)
    assert [t['i'] for t in r['trades']]==[31,389]
    assert np.isclose(r['capital_minutes'],q*110*(389-31))
    assert r['max_entry_gross']<=1 and not r['unresolved']

def test_reverse_and_short_fee():
    o,c,n,p,v=fixtures();c[:]=103;c[59:]=97;o[31:]=101;o[61:]=99;o[389]=90
    r=simulate_day(o,c,n,p,v,100,1,True)
    assert [t['kind'] for t in r['trades']]==['entry','exit','entry','exit']
    assert [t['i'] for t in r['trades']]==[31,61,61,389]
    assert r['borrow']>0 and r['max_entry_gross']<=1 and not r['unresolved']

def test_data_gap_after_entry_closes_causally():
    o,c,n,p,v=fixtures();c[:]=103;p[40:]=False;o[61]=np.nan
    r=simulate_day(o,c,n,p,v,100,1,True)
    assert r['trades'][0]['i']==31 and r['trades'][1]['i']==62
    assert r['quality_events']==1 and r['delayed_fills']==1

def test_missing_close_not_hidden():
    o,c,n,p,v=fixtures();c[:]=103;o[389]=np.nan
    r=simulate_day(o,c,n,p,v,100,1,True)
    assert r['unresolved'] and np.isnan(r['net_before_carry'])

def test_future_changes_do_not_change_earlier_trades():
    o,c,n,p,v=fixtures();c[:]=103
    first=simulate_day(o,c,n,p,v,100,1,True)['trades']
    o[120:]=90;c[120:]=90;p[120:]=False
    second=simulate_day(o,c,n,p,v,100,1,True)['trades']
    assert [t for t in first if t['i']<120]==[t for t in second if t['i']<120]

def test_noise_uses_previous14_not_current():
    f=pd.DataFrame(np.arange(60).reshape(20,3))
    a=f.rolling(14,min_periods=14).mean().shift(1)
    f.iloc[14:]+=1000
    b=f.rolling(14,min_periods=14).mean().shift(1)
    np.testing.assert_allclose(a.iloc[14],b.iloc[14])
