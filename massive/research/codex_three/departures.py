"""Source-reviewed departure sequences, frozen before option-price evaluation.

The review concerns only 27 candidate filing-date clusters in the cached 2024-25
survey. Missing facts are not imputed. These are sample-specific annotations,
not a claim that this is a general automated NLP model.
"""
import collections
import datetime as dt
import hashlib
import json
from data import HERE, disclosures

DECISIONS = {
 ('AIG','2025-11-14'): 'exclude: current appointee never joined; not a second incumbent departure',
 ('AMT','2025-11-07'): 'exclude: planned retirements',
 ('BA','2024-09-20'): 'exclude: prior transition expressly refers to retirement; noisy excerpt also misstates successor identity',
 ('BK','2025-01-08'): 'exclude: current planned retirement',
 ('BRK.B','2025-12-11'): 'exclude: planned retirement and executive-chair succession',
 ('COST','2025-08-07'): 'exclude: planned retirements',
 ('CSCO','2024-07-19'): 'exclude: repeated Jeff Sharritts departure',
 ('DHR','2025-07-31'): 'exclude: prior internal role continuation and current planned retirement',
 ('GD','2024-03-07'): 'exclude: repeated Mark Roualet retirement',
 ('INTC','2025-04-30'): 'exclude: prior interim co-CEOs retain their other executive positions',
 ('LIN','2024-12-02'): 'exclude: repeated John Panikar retirement',
 ('LLY','2024-07-10'): 'exclude: repeated Anat Ashkenazi resignation',
 ('MDT','2024-06-26'): 'exclude: prior planned retirement',
 ('MDT','2025-05-21'): 'include: Jennifer Kirk controller resignation followed by Sean Salmon cardiovascular-head departure',
 ('MMM','2024-08-01'): 'exclude: repeated Monish Patolawala departure',
 ('MO','2024-02-28'): 'exclude: repeated Murray Garnick retirement',
 ('PG','2025-08-14'): 'exclude: prior internal executive-chair transfer and current planned retirement',
 ('PYPL','2024-02-12'): 'include: Peggy Alford sales departure followed by Aaron Karczmer enterprise-services departure',
 ('SBUX','2024-09-16'): 'exclude: current planned retirement',
 ('SCHW','2024-07-25'): 'exclude: repeated Peter Crawford planned retirement',
 ('SCHW','2024-10-01'): 'exclude: current planned retirement',
 ('TMUS','2025-09-22'): 'exclude: current internal transfer to executive vice-chair role',
 ('UNH','2025-05-14'): 'exclude: prior executive remains in management through internal transfer',
 ('UNH','2025-06-04'): 'exclude: repeated Andrew Witty departure; compensation update',
 ('UNH','2025-07-31'): 'exclude: ambiguous contractual advisor transition; no clear unplanned second management exit',
 ('USB','2024-08-21'): 'exclude: current planned retirement',
 ('USB','2025-04-16'): 'exclude: repeated Andrew Cecere internal executive-chair transfer',
}


def main():
    groups = collections.defaultdict(list)
    for r in disclosures():
        if r['tertiary_category'] in {'ceo_departure','cfo_departure','executive_officer_departure'}:
            groups[(r['ticker'],r['filing_date'])].append(r)
    seen, audit, events, fired = collections.defaultdict(list), [], [], {}
    for (ticker,date), rs in sorted(groups.items()):
        day=dt.date.fromisoformat(date)
        prior=[(d,v) for d,v in seen[ticker] if 0 < (day-d).days <=90]
        if prior:
            key=(ticker,date)
            if key not in DECISIONS:
                raise RuntimeError('Unreviewed cluster ' + str(key))
            decision=DECISIONS[key]
            record={'ticker':ticker,'filing_date':date,'decision':decision,
                    'accession_number':rs[0]['accession_number'],'filing_url':rs[0]['filing_url'],
                    'prior_filing_dates':[str(d) for d,_ in prior],
                    'prior_sources':[r['filing_url'] for _,v in prior for r in v],
                    'source_text_sha256':hashlib.sha256(' '.join(r['supporting_text'] for r in rs).encode()).hexdigest()}
            audit.append(record)
            if decision.startswith('include') and (ticker not in fired or (day-fired[ticker]).days>90):
                events.append(dict(record,strategy='collar',signal='departures'))
                fired[ticker]=day
        seen[ticker].append((day,rs))
    (HERE/'departures_audit.json').write_text(json.dumps({'departure_issuer_days':len(groups),'clusters':audit},indent=2))
    (HERE/'departures_events.json').write_text(json.dumps(events,indent=2))
    print('Departure candidates:',len(audit),'qualifying:',len(events))


if __name__=='__main__':main()
