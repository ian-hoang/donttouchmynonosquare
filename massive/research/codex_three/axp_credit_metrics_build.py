"""Reproduce price-blind AXP U.S. Consumer statistics from 19 verified SEC filings.
Each comparison uses current and prior month in the SAME contemporaneous filing.
This deliberately does not use Small Business, Lending Trust, or future revisions.
"""
import calendar
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
# filing date, accession suffix, current reported month, current delinquency,
# prior delinquency, current principal-only NWO rate, prior NWO rate.
FACTS=[
 ('2024-02-15','24-000015','2024-01',1.5,1.4,2.1,2.5),
 ('2024-03-15','24-000019','2024-02',1.5,1.5,2.4,2.1),
 ('2024-04-15','24-000023','2024-03',1.4,1.5,2.3,2.4),
 ('2024-05-15','24-000044','2024-04',1.4,1.4,2.5,2.3),
 ('2024-06-17','24-000046','2024-05',1.3,1.4,2.4,2.5),
 ('2024-07-15','24-000049','2024-06',1.3,1.3,2.3,2.4),
 ('2024-08-15','24-000059','2024-07',1.3,1.3,2.1,2.3),
 ('2024-09-16','24-000061','2024-08',1.3,1.3,2.2,2.1),
 ('2024-11-15','24-000072','2024-10',1.4,1.4,2.4,1.9),
 ('2024-12-16','24-000074','2024-11',1.4,1.4,2.0,2.4),
 ('2025-02-18','25-000020','2025-01',1.4,1.4,2.3,2.1),
 ('2025-03-17','25-000024','2025-02',1.4,1.4,2.5,2.3),
 ('2025-05-15','25-000060','2025-04',1.4,1.4,2.0,2.4),
 ('2025-06-16','25-000068','2025-05',1.3,1.4,2.1,2.0),
 ('2025-07-15','25-000078','2025-06',1.3,1.3,2.1,2.1),
 ('2025-08-15','25-000157','2025-07',1.3,1.3,2.0,2.1),
 ('2025-09-15','25-000172','2025-08',1.3,1.3,2.0,2.0),
 ('2025-11-17','25-000259','2025-10',1.4,1.4,2.2,1.9),
 ('2025-12-15','25-000265','2025-11',1.4,1.4,2.1,2.2),
]

def build(input_path=Path('/tmp/gqh_massive_2024_2025_disclosures.json')):
    raw=json.loads(input_path.read_text())
    filings={r['accession_number']:r for r in raw if r.get('universe_ticker')=='AXP' and r.get('tertiary_category')=='business_update' and '2024-01-01' <= r['filing_date'] <= '2025-12-31'}
    records=[]
    for date,suffix,month,d,pd,n,pn in FACTS:
        acc='0000004962-'+suffix
        assert filings[acc]['filing_date']==date
        y,m=map(int,month.split('-')); prev=f'{y-1}-12' if m==1 else f'{y}-{m-1:02d}'
        source=f'https://www.sec.gov/Archives/edgar/data/4962/{acc.replace("-", "")}/axp-{date.replace("-", "")}.htm'
        flags=[]; consumer_break=False
        if date in ('2024-02-15','2024-03-15'):
            flags.append('Thanksgiving2023 timing shifted certain Consumer writeoffs from Nov to Dec2023. Only Feb2024 filing comparison uses Dec2023 as its immediate prior month.')
            consumer_break=date=='2024-02-15'
        if date in ('2025-02-18','2025-03-17','2025-05-15'):
            flags.append('Lowes Small Business portfolio reclassified held-for-sale effective Dec1,2024. This is NOT the selected U.S. Consumer series.')
        if date in ('2025-06-16','2025-07-15'):
            flags.append('Amazon Small Business portfolio reclassified held-for-sale effective June1,2025. This is NOT the selected U.S. Consumer series.')
        if date>='2025-08-15':
            flags.append('Tables exclude loans held-for-sale; no new U.S. Consumer portfolio reclassification identified in this filing.')
        if m in (3,6,9):flags.append('Current quarter-end monthly data marked preliminary; use value as published without later revisions.')
        signal=d<pd and n>pn
        row={'ticker':'AXP','filing_date':date,'accession_number':acc,'reported_month':month,
             'reported_month_end':f'{month}-{calendar.monthrange(y,m)[1]:02d}',
             'prior_reported_month':prev,'source_url':source,'source_verified':True,
             'source_type':'Contemporaneous SEC8-K inline table read using web tool',
             'series':'us_consumer_card_member_loans',
             'delinquency_30days_past_due_pct':d,'prior_delinquency_pct':pd,
             'net_writeoff_principal_only_pct':n,'prior_net_writeoff_principal_only_pct':pn,
             'comparison_source':'Both current and prior values appear in this same filing; missing sponsor-tag months do not require future information.',
             'portfolio_change_flags':flags,'consumer_series_break':consumer_break,
             'raw_divergence':signal,'eligible_divergence':signal and not consumer_break,
             'rounding_note':'Published rates rounded to0.1 percentage point. Equality is not a trigger.'}
        records.append(row)
    assert len(records)==len(filings)
    return {'metadata':{'ticker':'AXP','candidate_filing_count':len(filings),'verified_report_count':len(records),
            'filing_window':['2024-01-01','2025-12-31'],'raw_divergence_events':sum(r['raw_divergence'] for r in records),
            'eligible_divergence_events':sum(r['eligible_divergence'] for r in records),
            'source_reading':'All19 U.S.Consumer current/prior pairs verified against contemporaneous SEC8-K tables.',
            'rate_units':'Percent, not decimal fractions. Writeoff rate is principal-only; delinquency is a point-in-time share.',
            'no_2026_filings_used':True,'no_option_price_data_read':True,
            'selection_limit':'Only19 sponsor-tagged monthly filings; not all monthly filings exist in the cached tag survey.'},'records':records}
if __name__=='__main__':
    out=build();(HERE/'axp_credit_metrics.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out['metadata'],indent=2));print('Signals',[(r['filing_date'],r['reported_month']) for r in out['records'] if r['eligible_divergence']])
