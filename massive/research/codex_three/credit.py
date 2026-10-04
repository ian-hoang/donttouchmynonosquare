"""Frozen credit divergence rule applied to source-verified monthly tables."""
import datetime as dt
import json
from data import HERE


def main():
    audits=[]
    selected=[]
    for issuer in ['cof','axp']:
        records=json.loads((HERE/(issuer+'_credit_metrics.json')).read_text())['records']
        bymonth={r['reported_month']:r for r in records}
        last=None
        for r in sorted(records,key=lambda r:r['filing_date']):
            if issuer=='cof':
                previous=bymonth.get(r.get('prior_reported_month'),{})
                eligible=(r.get('raw_divergence_comparable',False)
                    and not r.get('portfolio_change_flags')
                    and not previous.get('portfolio_change_flags')
                    and r.get('eligible_legacy_series',False))
            else:
                eligible=r.get('eligible_divergence',False)
            date=dt.date.fromisoformat(r['filing_date'])
            cooldown=last is not None and (date-last).days<30
            record=dict(r,eligible_before_cooldown=bool(eligible),cooldown_excluded=bool(eligible and cooldown))
            audits.append(record)
            if eligible and not cooldown:
                selected.append(dict(record,signal='credit',strategy='long_call',filing_url=r['source_url']))
                last=date
    (HERE/'credit_events.json').write_text(json.dumps(selected,indent=2))
    (HERE/'credit_audit.json').write_text(json.dumps({'screened':len(audits),'records':audits},indent=2))
    print('Credit reports screened:',len(audits),'qualifying events:',len(selected))
    for r in selected:print(r['ticker'],r['filing_date'])


if __name__=='__main__':main()
