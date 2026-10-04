"""Idempotent audit-field correction; leaves all net/gross results unchanged."""
import json
from backtest import PRIVATE


def main():
    for name in ['observations.json','credit_control_observations.json']:
        p=PRIVATE/name
        if not p.exists():continue
        rows=json.loads(p.read_text())
        for r in rows:
            premium=sum(abs(r['entry_marks'][k])+abs(r['exit_marks'][k]) for k in r['entry_marks'])
            costs=premium*r['haircut']+.0065*2*len(r['entry_marks'])
            assert abs((r['gross']-r['net'])*r['spot_proxy']-costs)<1e-7
            r['costs_per_share']=costs
            r['capital_basis']='option premium plus entry costs' if r['strategy']=='long_call' else \
                               'strike collateral' if r['strategy']=='cash_secured_put' else 'stock-equivalent notional'
        p.write_text(json.dumps(rows))
        print(name,len(rows),'audit fields verified')


if __name__=='__main__':main()
