"""Reproduce price-blind COF facts transcribed from verified SEC Exhibit 99.1 pages.
No network calls and no price data. Percent values are percentage points (5.95 = 5.95%).
"""
import calendar
import datetime as dt
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
# month, accession suffix, NCO %, 30+ performing delinquency %, source filename,
# and issuer-disclosed adjustment to NCO in basis points (not an estimated adjustment).
FACTS=[
 ('2023-12','24-000009',5.78,4.61,'ex991december2023creditmet.htm',15),
 ('2024-01','24-000054',5.71,4.78,'ex991january2024creditmetr.htm',0),
 ('2024-02','24-000140',5.95,4.72,'ex991february2024creditmet.htm',0),
 ('2024-03','24-000159',6.15,4.48,'ex991march2024creditmetrics.htm',0),
 ('2024-04','24-000219',6.07,4.23,'ex991april2024creditmetrics.htm',0),
 ('2024-05','24-000228',6.13,4.13,'ex991may2024creditmetrics.htm',17),
 ('2024-06','24-000254',5.93,4.14,'ex991june2024creditmetrics.htm',39),
 ('2024-07','24-000272',5.79,4.28,'ex991july2024creditmetrics.htm',40),
 ('2024-08','24-000284',5.82,4.35,'ex991august2024creditmetri.htm',39),
 ('2024-09','24-000297',5.23,4.53,'ex991september2024creditme.htm',36),
 ('2024-10','24-000326',5.82,4.61,'ex991october2024creditmetr.htm',39),
 ('2024-11','24-000331',6.08,4.57,'ex991november2024creditmet.htm',40),
 ('2024-12','25-000009',6.28,4.53,'ex991december2024creditmet.htm',42),
 ('2025-01','25-000052',6.12,4.61,'ex991january2025creditmetr.htm',0),
 ('2025-02','25-000120',6.35,4.52,'ex991february2025creditmet.htm',0),
 ('2025-03','25-000131',6.09,4.25,'ex991march2025creditmetrics.htm',0),
 ('2025-04','25-000167',5.66,3.95,'ex991april2025creditmetrics.htm',0),
 ('2025-05','25-000226',5.57,3.85,'ex991may2025creditmetrics.htm',0),
 ('2025-06','25-000241',5.29,3.92,'ex991june2025creditmetrics.htm',0),
 ('2025-07','25-000252',4.83,3.67,'ex991july2025creditmetrics.htm',0),
 ('2025-08','25-000258',4.70,3.73,'ex991august2025creditmetri.htm',0),
 ('2025-09','25-000268',4.35,3.89,'ex991september2025creditme.htm',0),
 ('2025-10','25-000283',4.77,3.99,'ex991october2025creditmetr.htm',0),
 ('2025-11','25-000288',5.02,4.01,'ex991november2025creditmet.htm',0),
]

def build(input_path=Path('/tmp/gqh_massive_2024_2025_disclosures.json')):
    raw=json.loads(input_path.read_text())
    filings={r['accession_number']:r for r in raw if r.get('universe_ticker')=='COF' and r.get('tertiary_category')=='business_update' and '2024-01-01' <= r['filing_date'] <= '2025-12-31'}
    records=[]
    for month,suffix,nco,delinq,name,adj in FACTS:
        acc='0000927628-'+suffix
        f=filings[acc]
        y,m=map(int,month.split('-'))
        last=calendar.monthrange(y,m)[1]
        flags=[]
        break_now=False
        segment='legacy_capital_one_domestic_card'
        if month=='2023-12':
            flags.append('One-time operational delay on hardship-program loans adds 15bp to NCO; issuer-adjusted NCO5.63%.')
        if '2024-05'<=month<='2024-12':
            flags.append(f'Walmart loss-sharing termination effective May21,2024 adds {adj}bp to reported NCO; issuer publishes ex-impact rate.')
        if month=='2024-05':
            break_now=True
            flags.append('First month of Walmart loss-sharing termination: raw NCO rise is not deterioration in underlying loan performance.')
        if month=='2025-01':
            flags.append('Prior-month Walmart add-back is no longer separately disclosed; adjusted pre-termination comparison is unavailable.')
        if month in ('2025-05','2025-06'):
            flags.append('Discover acquisition completed May18,2025. Selected rate is explicitly legacy Capital One Domestic, excluding Discover.')
        if month>='2025-07':
            segment='combined_capital_one_discover_domestic_card'
            flags.append('Domestic row is combined acquired portfolio; no separate legacy Capital One row available. Excluded from legacy-series signals.')
            break_now=month=='2025-07'
        row={'ticker':'COF','reported_month':month,'reported_month_end':f'{month}-{last:02d}',
             'filing_date':f['filing_date'],'accession_number':acc,
             'source_url':f'https://www.sec.gov/Archives/edgar/data/927628/{acc.replace("-", "")}/{name}',
             'source_verified':True,'source_type':'SEC filing Exhibit99.1 read using web tool',
             'series':segment,'net_chargeoff_annualized_pct':nco,'delinquency_30plus_performing_pct':delinq,
             'issuer_disclosed_nco_adjustment_bps':adj,
             'nco_ex_disclosed_impact_pct':round(nco-adj/100,2),
             'nco_adjustment_note':'When adjustment is zero this is reported NCO, not a counterfactual estimate.',
             'portfolio_change_flags':flags,'break_from_prior_month':break_now,
             'eligible_legacy_series':segment=='legacy_capital_one_domestic_card',
             'raw_divergence':False,'raw_divergence_comparable':False,'unflagged_divergence':False}
        if month=='2025-06':
            row['unused_combined_domestic_rates']={'nco_pct':4.96,'delinquency_pct':3.60}
            row['unused_discover_rates']={'nco_pct':4.47,'delinquency_pct':3.11}
            row['portfolio_change_flags'].append('Acquisition-related accelerated writeoffs and delinquency-method alignment affect Discover and combined numbers; those rates are not used.')
        if records:
            prev=records[-1]
            py,pm=map(int,prev['reported_month'].split('-'))
            adjacent=(y*12+m)-(py*12+pm)==1
            assert adjacent and prev['filing_date']<row['filing_date']
            raw_sig=delinq<prev['delinquency_30plus_performing_pct'] and nco>prev['net_chargeoff_annualized_pct']
            comparable=adjacent and not break_now and row['eligible_legacy_series'] and prev['eligible_legacy_series']
            row.update(prior_reported_month=prev['reported_month'],prior_filing_date=prev['filing_date'],
                       prior_source_url=prev['source_url'],prior_nco_pct=prev['net_chargeoff_annualized_pct'],
                       prior_delinquency_pct=prev['delinquency_30plus_performing_pct'],
                       raw_divergence=raw_sig,raw_divergence_comparable=raw_sig and comparable,
                       unflagged_divergence=raw_sig and comparable and not adj and not prev['issuer_disclosed_nco_adjustment_bps'])
        records.append(row)
    meta={'ticker':'COF','filing_window':['2024-01-01','2025-12-31'],'reported_month_window':['2023-12','2025-11'],
          'candidate_filing_count':len(filings),'verified_report_count':len(records),
          'source_reading':'All 24 rate pairs verified against issuer SEC Exhibit99.1 pages, without reading option prices.',
          'rate_units':'Percent, not decimal fractions. NCO rate is annualized; delinquency is a point-in-time fraction.',
          'raw_divergence_events':sum(r['raw_divergence'] for r in records),
          'comparable_legacy_raw_divergence_events':sum(r['raw_divergence_comparable'] for r in records),
          'unflagged_divergence_events':sum(r['unflagged_divergence'] for r in records),
          'signal_note':'These booleans are accounting comparisons only. Root frozen study specification governs whether to exclude all adjustment-flagged months.',
          'no_2026_filings_used':True,'no_option_price_data_read':True}
    return {'metadata':meta,'records':records}
if __name__=='__main__':
    payload=build()
    (HERE/'cof_credit_metrics.json').write_text(json.dumps(payload,indent=2)+'\n')
    print(json.dumps(payload['metadata'],indent=2))
    print('Signals',[(r['filing_date'],r['reported_month'],r['raw_divergence_comparable'],r['unflagged_divergence']) for r in payload['records'] if r['raw_divergence']])
