"""Extract earnings release datelines from cached SEC EX-99; no acceptance-date fallback.

Only existing local files are read. This creates event provenance, never returns.
Quarterly earnings releases with a dateline within four business days before SEC
acceptance are eligible. Preliminary updates, monthly sales, slides and forecasts
without quarterly earnings results are excluded. The actual publication *time*
is unknown; the SEC acceptance timestamp is retained solely as availability bound.
"""
from __future__ import annotations
import gzip
import html
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
SEC=ROOT/'data/cache/ai_washing/sec'
MONTH=r'January|February|March|April|May|June|July|August|September|October|November|December|Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?'
DATE=re.compile(r'\b('+MONTH+r')\s+(\d{1,2})\s*,?\s*(20\d{2})\b',re.I)
MONTHS={k[:3].lower():i for i,k in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'],1)}


def flatten(raw):
    raw=re.sub(r'<(script|style)\b[^>]*>.*?</\1>',' ',raw,flags=re.S|re.I)
    raw=html.unescape(re.sub(r'<[^>]+>',' ',raw))
    raw=re.sub(r'[\u200b\ufeff]','',raw)
    raw=re.sub(r'\s+',' ',raw).strip()
    # Word processor styling can split years and day digits across tags.
    raw=re.sub(r'\b20\s+(\d)\s*(\d)\b',r'20\1\2',raw)
    raw=re.sub(r'\b(20\d)\s+(\d)\b',r'\1\2',raw)
    raw=re.sub(r'('+MONTH+r')\s+(\d)\s+(\d)\s*,',r'\1 \2\3,',raw,flags=re.I)
    return raw


def parse(text,accepted):
    head=text[:6000]
    # The event must be actual quarterly/year earnings, not a call invitation.
    quarter=re.search(r'\b(quarter|quarterly|q[1-4]|full.year|fiscal.year|year.ended|year.end|half.year)\b',head,re.I)
    results=re.search(r'\b(results|earnings|net income|financial performance)\b',head,re.I)
    if not quarter or not results:
        return None,'not_quarterly_earnings'
    if re.search(r'\bpreliminary\b',head[:800],re.I) or re.search(r'\bannounces\b[^•]{0,80}\bperformance highlights\b',head[:500],re.I):
        return None,'preliminary_results'
    # Item 2.02 also covers acquisitions, management changes and guidance. A
    # passing mention of earnings later in such a release is not an earnings
    # announcement. Require a present/past actual-results sentence near its top.
    reporting=re.compile(r'\b(?:reports|reported|announces|announced|releases|released|delivers|delivered)\b[^.!?•–—]{0,180}\b(?:results|earnings|net income)\b',re.I)
    qualified=False
    for match in reporting.finditer(head[:1600]):
        context=head[max(0,match.start()-120):min(1600,match.end()+100)]
        prefix=head[max(0,match.start()-60):match.start()]
        future=bool(re.search(r'\b(?:when it|will|plans? to|expects? to)\b',prefix,re.I))
        if re.search(r'\b(?:quarter|quarterly|q[1-4]|full.year|fiscal.year|year.ended|year.end)\b',context,re.I) and not future and not re.search(r'\b(?:will|expects? to|date of|date for|plans to|scheduled|preliminary|guidance|outlook|conference|webcast|leadership|transition|chief|board|appoints|acquires|acquisition)\b',match[0],re.I):
            qualified=True
            break
    if not qualified:
        # Berkshire's consistent release format has no report/announce verb.
        berkshire=bool(re.search(r'BERKSHIRE HATHAWAY INC.{0,80}NEWS RELEASE',head[:250],re.I)
                       and re.search(r"Berkshire[’']s operating results for the (?:first|second|third|fourth) quarter",head[:700],re.I))
        if not berkshire:
            return None,'no_actual_quarterly_results_heading'
    # Restrict to beginning of release. Quarter-end dates in tables cannot match
    # the tight acceptance proximity unless they happened just before filing.
    candidates=[]
    for match in DATE.finditer(head):
        try:
            day=pd.Timestamp(year=int(match[3]),month=MONTHS[match[1][:3].lower()],day=int(match[2]))
        except ValueError:
            continue
        if day>accepted.normalize() or (accepted.normalize()-day).days>8:
            continue
        lag=int(np.busday_count(day.date(),accepted.date()))
        if lag>4:
            continue
        before=head[max(0,match.start()-160):match.start()]
        after=head[match.end():match.end()+300]
        # Concrete dateline forms: immediate-release date; city,date -- company;
        # date followed by period/ellipsis, wire marker, dash, or company heading.
        immediate=bool(re.search(r'(immediate release|for release|news release|press release)',before,re.I))
        punctuation=bool(re.match(r'\s*(?:\)|\.|[-–—]|\(|/)',after))
        today=bool(re.search(r'\btoday\b.{0,80}\b(announc|report|releas)',after,re.I))
        before_period=bool(re.search(r'(quarter|months?|year)\s+(ended|ending)\s*$',before,re.I))
        if before_period or not (immediate or punctuation or today):
            continue
        candidates.append({'actual_date':str(day.date()),'dateline':match[0],
                           'dateline_position':match.start(),'acceptance_lag_business_days':lag,
                           'evidence':head[max(0,match.start()-180):match.end()+400]})
    if not candidates:
        return None,'no_verified_dateline'
    dates={x['actual_date'] for x in candidates}
    if len(dates)>1:
        return None,'ambiguous_multiple_recent_datelines'
    return candidates[0],None


def main():
    uni=pd.read_csv(HERE/'events_universe.csv')
    ticker_of=dict(zip(uni.cik.astype(int),uni.ticker))
    filings=pd.read_parquet(SEC/'earnings_8k.parquet')
    meta=pd.read_parquet(SEC/'ex99_meta.parquet').set_index('acc')
    filings=filings[filings.cik.astype(int).isin(ticker_of)&filings.filingDate.between('2021-01-01','2026-09-30')]
    rows=[];drops=[]
    for filing in filings.itertuples():
        accession=filing.accessionNumber
        base={'ticker':ticker_of[int(filing.cik)],'cik':str(filing.cik).zfill(10),'accession':accession,
              'sec_accepted_utc':filing.acceptanceDateTime,'actual_time_known':False,
              'date_source':'SEC earnings exhibit release dateline','dateline_verified':True}
        path=SEC/'ex99'/(accession+'.txt.gz')
        if not path.exists():
            drops.append(base|{'reason':'no_cached_exhibit'});continue
        text=flatten(gzip.open(path,'rt').read())
        accepted=pd.Timestamp(filing.acceptanceDateTime).tz_convert('America/New_York').tz_localize(None)
        result,reason=parse(text,accepted)
        if reason:
            drops.append(base|{'reason':reason,'header':text[:400]});continue
        filename=meta.loc[accession,'filename'] if accession in meta.index else None
        if not isinstance(filename,str):
            drops.append(base|{'reason':'missing_exhibit_filename'});continue
        url=f"https://www.sec.gov/Archives/edgar/data/{int(filing.cik)}/{accession.replace('-','')}/{filename}"
        rows.append(base|result|{'source_url':url,'header':text[:500]})
    frame=pd.DataFrame(rows).sort_values(['ticker','actual_date','sec_accepted_utc']).drop_duplicates(['ticker','actual_date'])
    clean=frame.to_dict(orient='records')
    (HERE/'options_release_history.json').write_text(json.dumps(clean,indent=2))
    (HERE/'options_release_history_drops.json').write_text(json.dumps(drops,indent=2))
    summary={'input_filings':len(filings),'release_dates':len(frame),'tickers':frame.ticker.nunique(),
             'years':frame.actual_date.str[:4].value_counts().sort_index().to_dict(),
             'drop_reasons':pd.Series([x['reason'] for x in drops]).value_counts().to_dict(),
             'date_only':True,'acceptance_date_fallback':False,
             'limitation':'Exact time unavailable; cached first EX99 may omit a later earnings exhibit; datelines parsed with strict proximity and textual pattern filters.'}
    (HERE/'options_release_history_audit.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
