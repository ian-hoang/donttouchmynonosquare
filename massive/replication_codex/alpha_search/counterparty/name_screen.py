"""Recall-oriented alias screen of all fetched excerpts, without price information."""
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ALIASES = {
'AAPL':['Apple'], 'ABBV':['AbbVie'], 'ABT':['Abbott'], 'ACN':['Accenture'],
'ADBE':['Adobe'], 'AIG':['American International Group','AIG'],
'AMD':['Advanced Micro Devices','AMD'], 'AMGN':['Amgen'],
'AMT':['American Tower'], 'AMZN':['Amazon'], 'AVGO':['Broadcom'],
'AXP':['American Express'], 'BA':['Boeing'], 'BAC':['Bank of America'],
'BK':['Bank of New York','BNY'], 'BKNG':['Booking Holdings','Booking.com'],
'BLK':['BlackRock'], 'BMY':['Bristol-Myers','Bristol Myers'],
'BRK.B':['Berkshire Hathaway'], 'C':['Citigroup','Citibank'],
'CAT':['Caterpillar'], 'CHTR':['Charter Communications'], 'CL':['Colgate'],
'CMCSA':['Comcast'], 'COF':['Capital One'], 'COP':['ConocoPhillips'],
'COST':['Costco'], 'CRM':['Salesforce'], 'CSCO':['Cisco'], 'CVS':['CVS','Aetna'],
'CVX':['Chevron'], 'DE':['Deere'], 'DHR':['Danaher'], 'DIS':['Disney'],
'DUK':['Duke Energy'], 'EMR':['Emerson'], 'FDX':['FedEx'],
'GD':['General Dynamics'], 'GE':['General Electric','GE Aerospace'],
'GILD':['Gilead'], 'GM':['General Motors'], 'GOOGL':['Alphabet','Google'],
'GS':['Goldman Sachs'], 'HD':['Home Depot'], 'HON':['Honeywell'],
'IBM':['International Business Machines','IBM'], 'INTC':['Intel'],
'INTU':['Intuit'], 'ISRG':['Intuitive Surgical'], 'JNJ':['Johnson & Johnson'],
'JPM':['JPMorgan','J.P. Morgan','JP Morgan'], 'KO':['Coca-Cola','Coca Cola'],
'LIN':['Linde'], 'LLY':['Eli Lilly','Lilly'], 'LMT':['Lockheed'], 'LOW':["Lowe's"],
'MA':['Mastercard','MasterCard'], 'MCD':["McDonald's"], 'MDLZ':['Mondelez'],
'MDT':['Medtronic'], 'MET':['MetLife'], 'META':['Meta Platforms','Facebook'],
'MMM':['3M'], 'MO':['Altria'], 'MRK':['Merck'], 'MS':['Morgan Stanley'],
'MSFT':['Microsoft'], 'NEE':['NextEra'], 'NFLX':['Netflix'], 'NKE':['Nike'],
'NOW':['ServiceNow'], 'NVDA':['Nvidia','NVIDIA'], 'ORCL':['Oracle'],
'PEP':['PepsiCo','Pepsi'], 'PFE':['Pfizer'], 'PG':['Procter & Gamble'],
'PLTR':['Palantir'], 'PM':['Philip Morris'], 'PYPL':['PayPal'],
'QCOM':['Qualcomm'], 'RTX':['Raytheon','RTX Corporation'], 'SBUX':['Starbucks'],
'SCHW':['Charles Schwab'], 'SO':['Southern Company'], 'T':['AT&T'],
'TGT':['Target Corporation'], 'TMO':['Thermo Fisher'], 'TMUS':['T-Mobile'],
'TSLA':['Tesla'], 'TXN':['Texas Instruments'], 'UBER':['Uber'],
'UNP':['Union Pacific'], 'UPS':['United Parcel Service','UPS'],
'USB':['U.S. Bancorp','US Bancorp','U.S. Bank'], 'V':['Visa'],
'VZ':['Verizon'], 'WFC':['Wells Fargo'], 'WMT':['Walmart','Wal-Mart'],
'XOM':['Exxon','ExxonMobil']}


def main():
    rules = {ticker: re.compile(r'(?<!\w)(?:'+'|'.join(re.escape(a) for a in aliases)+r')(?!\w)', re.I)
             for ticker, aliases in ALIASES.items()}
    candidates = []
    no_match = []
    issuer_only = []
    tags = ['deal_termination', 'deal_breach_default', 'cybersecurity_incident',
            'natural_disaster_impact', 'facility_closure']
    for path in sorted((HERE/'cache'/(tag+'.json') for tag in tags)):
        for row in json.loads(path.read_text()):
            text = str(row.get('supporting_text') or '')
            matched = [ticker for ticker, rule in rules.items() if rule.search(text)]
            issuers = {str(t).replace('/','.').upper() for t in row.get('tickers',[])}
            other = sorted(set(matched) - issuers)
            base = dict(row, alias_hits=matched, potential_counterparties=other)
            if other:
                candidates.append(base)
            elif matched:
                issuer_only.append(base)
            else:
                no_match.append({k:row.get(k) for k in ['accession_number','cik','filing_date','filing_url','tertiary_category']})
    for filename, rows in [('candidate_excerpts.json',candidates),('issuer_only.json',issuer_only),('no_alias_match.json',no_match)]:
        (HERE/'cache'/filename).write_text(json.dumps(rows,indent=2))
    (HERE/'aliases.json').write_text(json.dumps(ALIASES,indent=2))
    print(json.dumps({'candidate_rows':len(candidates),'issuer_only_rows':len(issuer_only),'no_alias_match_rows':len(no_match)}))
    for n,row in enumerate(candidates):
        print(json.dumps({'i':n, **row}))


if __name__ == '__main__':
    main()
