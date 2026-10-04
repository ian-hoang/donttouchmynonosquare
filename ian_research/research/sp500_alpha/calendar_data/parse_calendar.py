"""Parse saved Federal Reserve calendar pages; no market-return calculations."""
from pathlib import Path
import re, json, html, datetime as dt, hashlib
from collections import Counter
HERE=Path(__file__).resolve().parent
BASE='https://www.federalreserve.gov'
MONTHS={x.lower():i for i,x in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'],1)}
MONTHS.update({x[:3]:i for x,i in list(MONTHS.items())})

def clean(s): return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',s))).strip()
def endpoint(label,year):
    # Last month and last day handle July31-August1 and Apr/May30-1 alike.
    mons=[m for m in re.findall(r'[A-Za-z]+',label) if m.lower() in MONTHS]
    days=re.findall(r'\d+',label)
    if days and int(days[-1])==year: days=days[:-1]
    return dt.date(year,MONTHS[mons[-1].lower()],int(days[-1])).isoformat()
def classify(s):
    low=s.lower()
    if 'cancel' in low:return 'scheduled_cancelled'
    if 'unscheduled' in low or 'conference call' in low:return 'unscheduled'
    if 'notation' in low:return 'notation_vote'
    return 'scheduled'
def statement_url(s):
    links=re.findall(r'href=[\"\']([^\"\']+)[\"\']',s)
    vals=[x for x in links if re.search(r'/(?:pressreleases/monetary|press/monetary/)\d{8}[a-z]\.htm$',x)]
    return BASE+vals[0] if vals and vals[0].startswith('/') else (vals[0] if vals else None)
rows=[]
for year in range(2010,2021):
    name=f'fomchistorical{year}'; s=(HERE/(name+'.html')).read_text()
    blocks=list(re.finditer(r'<h5[^>]*>(.*?)</h5>',s,re.S))
    for i,m in enumerate(blocks):
        label=clean(m.group(1)); block=s[m.end():blocks[i+1].start() if i+1<len(blocks) else len(s)]
        cl=classify(label)
        if cl=='scheduled' and 'Meeting' not in label:raise ValueError(label)
        date=endpoint(label,year); url=statement_url(block)
        if cl=='scheduled':
            assert url is not None,label
            date_in_statement=re.search(r'monetary/?(\d{8})',url).group(1)
            assert date.replace('-','')==date_in_statement,(label,url)
        rows.append({'date':date,'source_url':BASE+'/monetarypolicy/'+name+'.htm','source_label':label,'classification':cl,'scheduled':cl=='scheduled','statement_url':url})
s=(HERE/'fomccalendars.html').read_text()
years=list(re.finditer(r'<h4>.*?(20\d\d) FOMC Meetings.*?</h4>',s,re.S))
for i,y in enumerate(years):
    year=int(y.group(1))
    if not 2021<=year<=2026:continue
    block=s[y.end():years[i+1].start() if i+1<len(years) else len(s)]
    months=list(re.finditer(r'<div[^>]*class="[^"]*fomc-meeting__month[^\"]*"[^>]*>(.*?)</div>',block,re.S))
    for j,m in enumerate(months):
        portion=block[m.end():months[j+1].start() if j+1<len(months) else len(block)]
        datebit=re.search(r'<div[^>]*class="[^"]*fomc-meeting__date[^\"]*"[^>]*>(.*?)</div>',portion,re.S)
        assert datebit is not None,(year,clean(m.group(1)))
        label=clean(m.group(1))+' '+clean(datebit.group(1));date=endpoint(label,year);cl=classify(label);url=statement_url(portion)
        if date>'2026-10-02':cl='scheduled_future' if cl=='scheduled' else cl
        if cl=='scheduled':
            assert url is not None,(year,label)
            assert date.replace('-','')==re.search(r'monetary/?(\d{8})',url).group(1),(label,url)
        row={'date':date,'source_url':BASE+'/monetarypolicy/fomccalendars.htm','source_label':str(year)+' '+label,'classification':cl,'scheduled':cl=='scheduled','statement_url':url}
        if year in [2025,2026]:
            row.update(advance_schedule_source_url=BASE+'/newsevents/pressreleases/monetary20240809a.htm',advance_schedule_release_date='2024-08-09')
        rows.append(row)
advance_releases={2019:'20180525',2020:'20190517',2021:'20200702',2022:'20210604',2023:'20220624',2024:'20230623',2025:'20240809',2026:'20240809'}
for year,release in advance_releases.items():
    src=(HERE/('monetary'+release+'a.htm')).read_text()
    if year<2025:
        labels=[clean(x) for x in re.findall(r'<p[^>]*>(.*?)</p>',src,re.S)]
        labels=[x for x in labels if re.match(r'^[A-Za-z]+ \d+-',x) and '(' in x and str(year+1) not in x]
    else:
        portion=src.split('<p>For '+str(year)+':</p>')[1].split('</ul>')[0]
        labels=[clean(x) for x in re.findall(r'<li[^>]*>(.*?)</li>',portion,re.S) if str(year+1) not in clean(x)]
    announced={endpoint(x,year) for x in labels}
    assert len(announced)==8,(year,labels)
    for row in rows:
        if row['date'][:4]==str(year) and row['classification'] in ['scheduled','scheduled_future','scheduled_cancelled']:
            assert row['date'] in announced,(year,row,announced)
            row.update(advance_schedule_source_url=BASE+'/newsevents/pressreleases/monetary'+release+'a.htm',advance_schedule_release_date=release[:4]+'-'+release[4:6]+'-'+release[6:])
rows.sort(key=lambda x:x['date'])
selected=[x for x in rows if x['scheduled']]
counts=Counter(x['date'][:4] for x in selected)
assert len(selected)==133,(len(selected),counts)
assert len(set(x['date'] for x in selected))==len(selected)
assert all(counts[str(y)]==(7 if y==2020 else (6 if y==2026 else 8)) for y in range(2010,2027)),counts
for x in selected:assert dt.date.fromisoformat(x['date']).weekday()<5,x
assert '2020-03-18' not in {x['date'] for x in selected}
assert '2020-03-15' not in {x['date'] for x in selected}
(HERE/'dates.json').write_text(json.dumps(selected,indent=2)+'\n')
(HERE/'excluded_dates.json').write_text(json.dumps([x for x in rows if not x['scheduled']],indent=2)+'\n')
manifest={'as_of':'2026-10-03','event_cutoff':'2026-10-02','selected_count':len(selected),'counts_by_year':dict(sorted(counts.items())),'source_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(HERE.iterdir()) if p.suffix in ['.html','.htm','.pdf']},'validation':'All selected dates match the date in their policy-statement URL; 8 per full year except 7 regular meetings in2020; 6 through cutoff in2026.','point_in_time_limit':'Historical calendars identify scheduled meetings retrospectively. For2019–2026 all selected dates have additionally been checked against official advance schedule press releases published before that year. Earlier calendar vintages and exact schedule-change publication times have not been individually checked; March2020 cancellation has contemporaneous public evidence.','march2020_cancellation':{'source_url':BASE+'/mediacenter/files/FOMCpresconf20200315.pdf','public_event_date':'2020-03-15','page':5,'evidence':'At the public press conference Powell said the March15 meeting replaced the coming Tuesday/Wednesday meeting. This precedes the planned March17 close entry.'}}
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'count':len(selected),'by_year':counts,'excluded':len(rows)-len(selected),'first':selected[0],'last':selected[-1]},indent=2))
