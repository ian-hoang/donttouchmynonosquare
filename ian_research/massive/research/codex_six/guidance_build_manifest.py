"""Reproduce the frozen guidance source audit without network or price data.

All 60 candidate filings were reviewed at supporting-text level. Likely range
updates were checked against SEC full filings/exhibits via the web reader.
Unverified prior ranges remain unclassified, never negative training labels.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = 'https://www.sec.gov/Archives/edgar/data/'

# accession: (metric, period, units, old lower/upper, new lower/upper, sources, note)
PAIRS = {
 '0000947871-24-000009': ('adjusted EPS','FY2023','USD/share',8.50,8.70,8.50,8.70,[], 'Explicit reaffirmation of identical FY2023 adjusted EPS range; the expectation of upper-half realization does not widen the interval.'),
 '0000050863-24-000086': ('revenue','Q2 2024','USD billion',12.5,13.5,12.5,13.5,[], 'Explicit statement that revenue remains in the original range, albeit below midpoint.'),
 '0000753308-24-000035': ('adjusted EPS','FY2024','USD/share',3.23,3.43,3.23,3.43,[], 'Explicit reaffirmation of the same FY2024 range; newly introduced FY2027 guidance cannot be compared with a different year.'),
 '0001467858-25-000093': ('adjusted EPS','FY2025','USD/share',11.00,12.00,8.25,10.00,[BASE+'1467858/000146785825000093/gm-20250501.htm'], 'Wider range, but a large midpoint reduction exceeds the frozen 1% tolerance. Old/new figures appear side-by-side in the full 8-K.'),
 '0000773840-24-000102': ('adjusted EPS','FY2024','USD/share',10.15,10.25,9.68,9.78,[BASE+'773840/000077384024000102/exhibit99-renaissance.htm'], 'Range shifts down by $0.47 with unchanged width; December agreement also changes economics.'),
 '0000066740-24-000077': ('adjusted EPS','FY2024','USD/share',6.80,7.30,7.00,7.30,[BASE+'66740/000006674024000077/q22024-8kerexx991.htm'], 'Full release states old and new ranges; lower floor increases and range narrows.'),
 '0000066740-24-000098': ('adjusted EPS','FY2024','USD/share',7.00,7.30,7.20,7.30,[BASE+'66740/000006674024000098/q32024-8kerexx991.htm'], 'Full release states old and new ranges; lower floor increases and range narrows.'),
 '0000066740-25-000061': ('adjusted EPS','FY2025','USD/share',7.60,7.90,7.75,8.00,[BASE+'66740/000006674025000061/q22025-8kerexx991.htm'], 'Full release states old and new ranges; floor increases and range narrows.'),
 '0000066740-25-000086': ('adjusted EPS','FY2025','USD/share',7.75,8.00,7.95,8.05,[BASE+'66740/000006674025000086/q32025-8kerexx991.htm'], 'Full release states old and new ranges; floor increases and range narrows.'),
 '0000796343-25-000102': ('adjusted EPS','FY2025','USD/share',20.50,20.70,20.80,20.85,[BASE+'796343/000079634325000064/adbeex991q225.htm',BASE+'796343/000079634325000102/adbeex991q325.htm'], 'June and September contemporaneous full releases supply the same-year non-GAAP EPS ranges; the September floor rises and width shrinks.'),
 '0000896878-24-000051': ('adjusted EPS','FY2025','USD/share',19.16,19.36,19.16,19.36,[BASE+'896878/000089687824000051/fy25q1earningspressrelease.htm'], 'Full release explicitly reiterates the existing full-year range; new quarterly ranges are different periods.'),
 '0000896878-25-000020': ('adjusted EPS','FY2025','USD/share',19.16,19.36,20.07,20.12,[BASE+'896878/000089687824000051/fy25q1earningspressrelease.htm',BASE+'896878/000089687825000020/fy25q3earningspressrelease.htm'], 'Full May release raises all company metrics and confirms old versus new growth bands; November release supplies prior absolute EPS range. Lower bound rises and width shrinks.'),
 '0001283699-24-000062': ('EBITDA','FY2024','USD billion',31.3,31.9,31.4,31.9,[BASE+'1283699/000128369924000062/tmus03312024ex991.htm'], 'Core Adjusted EBITDA old/new ranges explicitly stated; floor rises, width shrinks. No comparable EPS forecast provided.'),
 '0001283699-24-000109': ('EBITDA','FY2024','USD billion',31.4,31.9,31.5,31.8,[BASE+'1283699/000128369924000109/tmus06302024ex991.htm'], 'Core Adjusted EBITDA midpoint unchanged but range narrows; this is the opposite interval-shape control.'),
 '0001283699-24-000141': ('EBITDA','FY2024','USD billion',31.5,31.8,31.6,31.8,[BASE+'1283699/000128369924000141/tmus09302024ex991.htm'], 'Core Adjusted EBITDA old/new ranges explicitly stated; floor rises, width shrinks.'),
 '0001283699-25-000116': ('EBITDA','FY2025','USD billion',33.2,33.7,33.3,33.7,[BASE+'1283699/000128369925000116/tmus06302025ex991.htm'], 'Core Adjusted EBITDA old/new ranges explicitly stated; floor rises, width shrinks.'),
 '0001283699-25-000153': ('EBITDA','FY2025','USD billion',33.3,33.7,33.7,33.9,[BASE+'1283699/000128369925000153/tmus09302025ex991.htm'], 'Core Adjusted EBITDA old/new ranges explicitly stated; floor rises, width shrinks.'),
}

NOTES = {
 '0000796343-25-000064': ('full_exhibit_review', 'June full exhibit raises FY2025 targets and provides current ranges, but no auditable prior same-period numerical pair was frozen for this event.', [BASE+'796343/000079634325000064/adbeex991q225.htm']),
 '0000002488-24-000054': ('supporting_text_review', 'Initial Q2 revenue interval; no prior Q2 range in available source annotation.', []),
 '0001104659-25-084800': ('full_filing_review', 'Tariff-cost range and qualitative lower-end operating-margin statement, not a comparable numerical pair for an eligible metric.', [BASE+'18230/000110465925084800/tm2524597d1_8k.htm']),
 '0001108524-25-000168': ('supporting_text_review', 'New long-term revenue framework; supporting text has no same-period old/new interval.', []),
 '0000064803-24-000009': ('supporting_text_review', 'Reaffirmed lower-bound EPS/cash-flow point guidance; no finite two-sided interval.', []),
 '0000064803-25-000082': ('supporting_text_review', 'Press-release pointer only; prior/current same-period interval not verified. Remains unclassified, not a negative label.', []),
 '0000313616-24-000004': ('supporting_text_review', 'Anticipated prior-year performance/presentation pointer; no auditable same-period old/new interval.', []),
 '0000773840-24-000066': ('full_exhibit_review', 'Acquisition completion explicitly changes the non-GAAP EPS calculation. Old/new EPS ranges are not comparable without adjustment; other intervals do not supply a positive rule.', [BASE+'773840/000077384024000066/exhibit99-carrieracquisiti.htm']),
 '0000050863-25-000004': ('supporting_text_review', 'Initial next-quarter guidance pointer; no verified prior same-quarter interval.', []),
 '0000050863-25-000153': ('supporting_text_review', 'Operating-expense point target changes following deconsolidation; not eligible comparable range.', []),
 '0000896878-25-000031': ('full_exhibit_review', 'Release initiates FY2026 and Q1 FY2026 guidance; different periods cannot be compared with prior-year guidance.', [BASE+'896878/000089687825000031/fy25q4earningspressrelease.htm']),
 '0000936468-24-000088': ('supporting_text_review', 'Aircraft deliveries/production range, not an eligible financial metric.', []),
 '0001141391-24-000211': ('supporting_text_review', 'New 2025-2027 qualitative CAGR objectives and minimum margin; no old/new same-period numeric interval.', []),
 '0001099219-24-000028': ('supporting_text_review', 'Maintained free-cash-flow ratio/ROE ranges and qualitative rates; not an eligible same-metric cash-flow amount pair.', []),
 '0001099219-25-000039': ('supporting_text_review', 'Qualitative rates and five-year point cash-flow target; no comparable interval.', []),
 '0001099219-25-000222': ('supporting_text_review', 'Variable-investment-income quarterly point target, not a two-sided interval or eligible metric.', []),
 '0001099219-25-000239': ('supporting_text_review', 'Variable-investment-income range versus prior point target; no prior interval, and metric outside frozen priority list.', []),
 '0000066740-24-000005': ('supporting_text_review', 'Initial 2024 outlook pointer; prior same-period range not established.', []),
 '0000066740-24-000051': ('supporting_text_review', 'Initial guidance reflecting Solventum spin; changed business scope, no comparable pre/post pair verified.', []),
 '0000066740-25-000002': ('supporting_text_review', 'Initial 2025 outlook pointer; no prior same-period range established.', []),
 '0000753308-25-000064': ('supporting_text_review', 'New current ranges disclosed, but immediate prior same-period ranges not verified. Do not substitute stale 2024 guidance.', []),
 '0000077476-25-000059': ('supporting_text_review', 'Initial preliminary 2026 outlook, not verified old/new interval for the same period.', []),
 '0000078003-24-000195': ('supporting_text_review', 'Reaffirms 2024 and initiates 2025; numeric old/new pair not established in supporting text.', []),
 '0000078003-25-000167': ('supporting_text_review', 'Revises 2025 revenue and initiates 2026 guidance, but supporting text lacks numeric prior/current pair. Remains unclassified.', []),
 '0000080424-24-000015': ('supporting_text_review', 'Extracted table mixes sales/currency and EPS growth metrics without an identified prior/current pair.', []),
 '0000080424-24-000048': ('supporting_text_review', 'Extracted table mixes growth/currency columns; no verified old/new comparable interval.', []),
 '0001193125-25-034283': ('supporting_text_review', 'Reaffirms 2025 and introduces later-period outlook; no numeric comparable pair in source text.', []),
 '0000092122-24-000003': ('supporting_text_review', 'Project commissioning schedule and possible additional costs, not eligible financial guidance interval.', []),
 '0001552781-24-000039': ('supporting_text_review', 'New multi-year growth ranges/ratios; no prior interval for identical forecast period.', []),
 '0001552781-24-000318': ('supporting_text_review', 'Acquisition synergy contribution lower bound, not same-period two-sided range update.', []),
 '0000731766-24-000338': ('supporting_text_review', 'Initial next-year projections and prior-year outlook pointer; no numeric comparable pair established.', []),
 '0000731766-25-000245': ('supporting_text_review', 'Reaffirmation only, with no actual numerical two-sided range in supplied text.', []),
 '0001437749-24-029518': ('supporting_text_review', 'New multi-year qualitative growth targets; no comparable old/new same-period interval.', []),
 '0000036104-24-000028': ('supporting_text_review', 'Reaffirmed net-interest-income interval and qualitative fee/expense guidance; no eligible metric pair under frozen priority list.', []),
 '0000732712-25-000010': ('supporting_text_review', 'Churn and subscriber-addition outlook, not an eligible financial metric interval.', []),
}


def main():
    rows = json.loads((HERE / 'guidance_candidates.json').read_text())
    groups = {}
    for r in rows:
        groups.setdefault(r['accession_number'], []).append(r)
    events, controls, unclassified, audit = [], [], [], []
    for acc, g in sorted(groups.items()):
        r = g[0]
        d = {k: r[k] for k in ('ticker','filing_date','accession_number')}
        d.update(strategy='protective_put', supporting_text=[x['supporting_text'] for x in g],sources=[r['filing_url']])
        if acc in PAIRS:
            metric,period,units,lo,hi,nlo,nhi,urls,note = PAIRS[acc]
            om,nm=(lo+hi)/2,(nlo+nhi)/2
            passes = abs(nm-om)/abs(om)<=0.01 and nlo<lo and (nhi-nlo)>(hi-lo)+1e-10
            d.update(signal='unchanged_midpoint_lower_floor_wider_range' if passes else 'comparable_guidance_control',
                     metric=metric,period=period,units=units,old_range=[lo,hi],new_range=[nlo,nhi],
                     old_midpoint=om,new_midpoint=nm,relative_midpoint_change=abs(nm-om)/abs(om),
                     reason=note,source_numeric_annotation='Numeric endpoints transcribed from cited contemporaneous sources; reaffirmation implies equal old/new range only when expressly stated.')
            d['sources']+=urls
            d['review_scope']='full_exhibit_or_filing_review' if urls else 'explicit_range_reaffirmation_in_supporting_text'
            (events if passes else controls).append(d)
            classification='signal' if passes else 'control'
        else:
            if r['ticker']=='ABBV':
                scope,note,urls=('supporting_text_review','Current annual and quarterly EPS ranges include acquired R&D/milestone costs, but the immediate prior same-period range is not provided. Prior-quarter cached guidance is not assumed to remain current.',[])
            else:
                scope,note,urls=NOTES[acc]
            d.update(signal='unclassified',reason=note,review_scope=scope)
            d['sources']+=urls
            unclassified.append(d)
            classification='unclassified'
        audit.append(dict(d,classification=classification))
    result={'spec':'guidance_spec.json','status':'no_verified_positive_signals_partial_full_source_coverage',
            'events':events,'controls':controls,'unclassified':unclassified,
            'audit_counts':{'candidate_rows':len(rows),'candidate_filings':len(groups),'signals':len(events),'comparable_controls':len(controls),'unclassified':len(unclassified),'full_source_review_filings':sum('full_' in x['review_scope'] for x in audit)},
            'limitations':['Every candidate reviewed at supporting-text level; full-source numerical inspection targeted likely guidance-range updates. Missing or incomparable old/current ranges remain unclassified.',
                          'Zero verified trades does not prove the signal never occurs. The strict hypothesis is untestable on the presently verified event manifest.',
                          'No price outcomes or 2026 events used. Numerical controls do not establish the matched causal baseline by themselves.']}
    (HERE/'guidance_events.json').write_text(json.dumps(result,indent=2))
    (HERE/'guidance_audit.json').write_text(json.dumps(audit,indent=2))
    print(result['audit_counts'])


if __name__=='__main__':
    main()
