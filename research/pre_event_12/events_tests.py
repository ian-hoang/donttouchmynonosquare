"""Regression checks for calendar leakage and issuer collisions."""
import events_news as m

def row(ticker,title,body,pub='2023-01-11T15:30:00Z'):
 return {'title':title,'description':body,'published_utc':pub,'article_url':'https://example.invalid/regression','id':'regression','publisher':{'name':'GlobeNewswire'}}

def main():
 tests=[
 ('DVN','Devon Energy Schedules Earnings Release', 'Devon (NYSE: DVN) announced it will report fourth-quarter results on Tuesday, Feb. 14, after market close. On Wednesday, Feb. 15, the company will hold a conference call.','2023-02-14'),
 ('AMD','AMD to Report Financial Results', 'AMD (NASDAQ: AMD) will report results on February 14, 2023 after market close. The conference call is on February 15, 2023.','2023-02-14'),
 ('AMD','AMD Announces Earnings Conference Call', 'AMD (NASDAQ: AMD) will host a conference call to discuss results on February 14, 2023.',None),
 ('CVX','CEMATRIX To Report Financial Results', 'CEMATRIX (TSXV: CVX) will report results on February 14, 2023.',None),
 ('TSLA','Encore to Report Financial Results', 'Encore will report financial results on February 14, 2023.',None),
 ('AMD','AMD to Report Financial Results', 'AMD (NASDAQ: AMD) will report financial results for the period ending February 1, 2023, on February 14, 2023.','2023-02-14'),
 ('NVDA','NVIDIA Sets Conference Call for Financial Results', 'NVIDIA will host a conference call on February 22, 2023 to discuss financial results. Ahead of the call, results are publicly announced at approximately 1:20 p.m. PT.','2023-02-22'),
 ]
 for ticker,title,body,expected in tests:
  got=m.extract(ticker,row(ticker,title,body));actual=got.get('scheduled_date') if got else None
  assert actual==expected,(title,actual,expected)
 assert m.actual('COST',row('COST','Costco Reports January Sales Results','')) is None
 assert m.actual('ISRG',row('ISRG','Intuitive Announces Preliminary Fourth Quarter Results','')) is None
 print(f'{len(tests)+2} event-parser regression checks passed')
if __name__=='__main__':main()
