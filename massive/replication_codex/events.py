"""Frozen universe, event cohort and random quiet-peer sampling from the spec."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import date,timedelta
import random
from . import data

UNIVERSE='''AAPL ABBV ABT ACN ADBE AIG AMD AMGN AMT AMZN AVGO AXP BA BAC BK BKNG BLK BMY BRK.B C
CAT CHTR CL CMCSA COF COP COST CRM CSCO CVS CVX DE DHR DIS DUK EMR FDX GD GE GILD
GM GOOGL GS HD HON IBM INTC INTU ISRG JNJ JPM KO LIN LLY LMT LOW MA MCD MDLZ MDT
MET META MMM MO MRK MS MSFT NEE NFLX NKE NOW NVDA ORCL PEP PFE PG PLTR PM PYPL QCOM
RTX SBUX SCHW SO T TGT TMO TMUS TSLA TXN UBER UNP UPS USB V VZ WFC WMT XOM'''.split()
UNIVERSE_SET=set(UNIVERSE)
ENDPOINT='/stocks/filings/8-K/vX/disclosures'
START=date(2024,1,1);END=date(2026,8,31)


def normalize_ticker(ticker):return str(ticker).strip().upper().replace('/','.')


def window(day):return '2024-25' if str(day)[:4] in ['2024','2025'] else '2026'


def form_events(tag_rows):
    """Union tag rows, explode tickers and deduplicate by (CIK, filing date)."""
    grouped={};ambiguous=[]
    for tag,rows in tag_rows.items():
        for r in rows:
            day=str(r.get('filing_date',''))[:10]
            if not str(START)<=day<=str(END):continue
            tickers=r.get('tickers') or []
            if isinstance(tickers,str):tickers=[tickers]
            tickers=sorted({normalize_ticker(t) for t in tickers}&UNIVERSE_SET)
            if not tickers:continue
            cik=str(r.get('cik','')).zfill(10)
            key=(cik,day)
            event=grouped.setdefault(key,dict(cik=cik,filing_date=day,tickers=set(),tags=set(),accessions=set()))
            event['tickers'].update(tickers);event['tags'].add(tag)
            if r.get('accession_number'):event['accessions'].add(r['accession_number'])
    out=[]
    for event in grouped.values():
        tickers=sorted(event.pop('tickers'))
        if len(tickers)>1:ambiguous.append(dict(cik=event['cik'],filing_date=event['filing_date'],tickers=tickers))
        out.append(dict(event,ticker=tickers[0],tags=sorted(event['tags']),accessions=sorted(event['accessions']),window=window(event['filing_date'])))
    return sorted(out,key=lambda e:(e['ticker'],e['filing_date'],e['cik'])),ambiguous


def cooldown(events):
    last={};kept=[];dropped=[]
    for e in sorted(events,key=lambda e:(e['ticker'],e['filing_date'],e['cik'])):
        day=date.fromisoformat(e['filing_date']);previous=last.get(e['ticker'])
        if previous is None or (day-previous).days>60:
            kept.append(e);last[e['ticker']]=day
        else:dropped.append(dict(e,drop_reason='within_60_calendar_days_of_last_kept',last_kept=str(previous)))
    return kept,dropped


def fetch_events():
    tags=['acquisition_agreement','merger_agreement'];raw={}
    with ThreadPoolExecutor(2) as pool:
        fs={pool.submit(data.get_all,ENDPOINT,{'tertiary_category':tag,'filing_date.gte':str(START),
            'filing_date.lte':str(END),'limit':1000,'sort':'filing_date.asc'}):tag for tag in tags}
        for f in as_completed(fs):raw[fs[f]]=f.result()
    all_events,ambiguous=form_events(raw);kept,dropped=cooldown(all_events)
    return dict(before=all_events,kept=kept,cooldown_drops=dropped,ambiguous_cik_days=ambiguous,
                raw_counts={k:len(v) for k,v in raw.items()})


def fetch_one_history(ticker):
    dates=set()
    spellings=[ticker,ticker.replace('.','/')] if '.' in ticker else [ticker]
    for spelling in spellings:
        rows=data.get_all(ENDPOINT,{'tickers':spelling,'filing_date.gte':str(START-timedelta(days=5)),
            'filing_date.lte':str(END+timedelta(days=5)),'limit':1000,'sort':'filing_date.asc'})
        for r in rows:
            day=str(r.get('filing_date',''))[:10]
            if day:dates.add(day)
    return ticker,sorted(dates)


def fetch_histories(workers=10):
    result={}
    with ThreadPoolExecutor(workers) as pool:
        fs=[pool.submit(fetch_one_history,t) for t in UNIVERSE]
        for n,f in enumerate(as_completed(fs),1):
            ticker,days=f.result();result[ticker]=days
            if n%20==0:print('Peer filing histories',n,'/',len(UNIVERSE),flush=True)
    return result


def draw_peers(events,histories,seeds=range(20)):
    dates=sorted({e['filing_date'] for e in events})
    eligible={}
    for day in dates:
        d=date.fromisoformat(day)
        eligible[day]=[t for t in sorted(UNIVERSE) if not any(abs((date.fromisoformat(f)-d).days)<=5 for f in histories[t])]
        if len(eligible[day])<6:raise RuntimeError('Fewer than six quiet universe peers')
    draws=[]
    for seed in seeds:
        rng=random.Random(seed)
        for day in dates:draws.append(dict(seed=seed,filing_date=day,tickers=rng.sample(eligible[day],6)))
    return draws,eligible
