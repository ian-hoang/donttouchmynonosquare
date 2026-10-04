"""Trading sessions implemented only from the holidays in FROZEN_SPEC.txt."""
from bisect import bisect_left, bisect_right
from datetime import date, datetime, timedelta, time
from functools import lru_cache
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')


def as_date(value):
    if isinstance(value,datetime):return value.date()
    if isinstance(value,date):return value
    return date.fromisoformat(str(value)[:10])


def easter(year):
    # Gregorian computus; Good Friday is two calendar days earlier.
    a=year%19;b=year//100;c=year%100;d=b//4;e=b%4
    f=(b+8)//25;g=(b-f+1)//3;h=(19*a+b-d-g+15)%30
    i=c//4;k=c%4;l=(32+2*e+2*i-h-k)%7;m=(a+11*h+22*l)//451
    q=h+l-7*m+114
    return date(year,q//31,q%31+1)


def nth_weekday(year,month,weekday,n):
    first=date(year,month,1)
    return first+timedelta(days=(weekday-first.weekday())%7+7*(n-1))


def nearest_weekday(day):
    return day+timedelta(days=-1 if day.weekday()==5 else 1 if day.weekday()==6 else 0)


@lru_cache(None)
def holidays(year):
    new_year=date(year,1,1)
    jan_observed=new_year+timedelta(days=1) if new_year.weekday()==6 else new_year
    # A Saturday Jan1 remains Saturday; Dec31 is explicitly not observed.
    memorial=date(year,5,31)
    memorial-=timedelta(days=memorial.weekday())
    result={jan_observed,nth_weekday(year,1,0,3),nth_weekday(year,2,0,3),easter(year)-timedelta(days=2),
            memorial,nearest_weekday(date(year,7,4)),nth_weekday(year,9,0,1),
            nth_weekday(year,11,3,4),nearest_weekday(date(year,12,25))}
    if year>=2022:result.add(nearest_weekday(date(year,6,19)))
    if year==2025:result.add(date(2025,1,9))
    return frozenset(result)


def is_session(day):
    d=as_date(day)
    return d.weekday()<5 and d not in holidays(d.year)


def session_on_or_after(day):
    d=as_date(day)
    while not is_session(d):d+=timedelta(days=1)
    return d


def session_on_or_before(day):
    d=as_date(day)
    while not is_session(d):d-=timedelta(days=1)
    return d


def session_before(day):return session_on_or_before(as_date(day)-timedelta(days=1))
def session_after(day):return session_on_or_after(as_date(day)+timedelta(days=1))
before=session_before
after=session_after


def shift_session(day,offset):
    d=as_date(day)
    if not is_session(d):raise ValueError('shift_session requires a session')
    move=session_after if offset>=0 else session_before
    for _ in range(abs(offset)):d=move(d)
    return d


@lru_cache(None)
def sessions_between(start,end):
    """Number of sessions strictly after start, through and including end."""
    a,b=as_date(start),as_date(end)
    if b<a:return -sessions_between(b,a)
    n=0;day=a+timedelta(days=1)
    while day<=b:
        n+=is_session(day);day+=timedelta(days=1)
    return n


def last_completed_session(now=None):
    now=now or datetime.now(NY)
    now=now.replace(tzinfo=NY) if now.tzinfo is None else now.astimezone(NY)
    if is_session(now.date()) and now.time()>=time(16):return now.date()
    return session_before(now.date())
