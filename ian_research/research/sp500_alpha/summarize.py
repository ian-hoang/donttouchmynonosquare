"""Compare every primary candidate. No winner fitting or portfolio optimization."""
from pathlib import Path
import json
import hashlib
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent


def read(rel):
    df=pd.read_json(HERE/rel)
    df['date']=pd.to_datetime(df['date'])
    return df.set_index('date').sort_index()


def collect():
    rows=[]
    sector=read('sectors/daily.json')
    for n in [1,5]:
        z=sector.loc[sector.variant==f'residual_reversal_{n}day']
        rows.append((f'Sector reversal: {n} day',z.net_base,z.net_stress,'2 / 5 bp per side'))
    intra=read('intraday/daily_corrected.json')
    for name,key in [('Late-session momentum','momentum'),('Late-session reversal','extreme_reversal')]:
        rows.append((name,intra[key+'_corrected_net'],intra[key+'_corrected_stress'],'1 / 3 bp per side'))
    calendar=read('calendar/daily.json')
    for name,key in [('Before Fed: overnight','pre_fomc_overnight'),('Month-turn: overnight','turn_month_overnight')]:
        rows.append((name,calendar[key+'_cost1'],calendar[key+'_cost3'],'1 / 3 bp per side'))
    noise=read('noise_breakout/daily.json')
    rows.append(('Noise-band breakout',noise.excess,noise.stress_excess,'1 / 3 bp per side'))
    pullback=read('pullback/daily.json')
    rows.append(('Pullback within uptrend',pullback.excess,pullback.stress_excess,'1 / 3 bp per side'))
    return rows


def stats(r, seed=20261003):
    v=np.asarray(r,dtype=float);n=len(v);sd=v.std(ddof=1)
    assert np.isfinite(v).all() and sd>0
    f=sm.OLS(v,np.ones((n,1))).fit(cov_type='HAC',cov_kwds={'maxlags':5})
    rng=np.random.default_rng(seed);boot=[]
    for _ in range(2000):
        idx=((rng.integers(n,size=(n+19)//20)[:,None]+np.arange(20))%n).ravel()[:n]
        z=v[idx];s=z.std(ddof=1)
        if s:boot.append(np.sqrt(252)*z.mean()/s)
    t=float(f.tvalues[0]);p2=float(f.pvalues[0]);p=p2/2 if t>=0 else 1-p2/2
    return dict(sessions=n,sharpe=float(v.mean()/sd*np.sqrt(252)),
                annual_mean_excess=float(v.mean()*252),annual_vol=float(sd*np.sqrt(252)),
                mean_hac_t=t,positive_mean_one_sided_p=p,
                sharpe_ci95=list(np.quantile(boot,[.025,.975])))


def main():
    rows=collect()
    results=[];daily={}
    for name,base,stress,cost in rows:
        z=base.loc['2024-01-01':'2026-10-02'];s=stress.reindex(z.index)
        result={'name':name,'cost_base_stress':cost,'base':stats(z),'stress':stats(s)}
        results.append(result);daily[name]=z
    panel=pd.DataFrame(daily)
    assert len(panel)==691 and panel.notna().all().all()
    # Family correction is only conditional on this observed batch, not all prior
    # author/research choices. Never call it proof of a discovered live strategy.
    adjusted=multipletests([x['base']['positive_mean_one_sided_p'] for x in results],method='holm')[1]
    for r,p in zip(results,adjusted):r['base']['holm_positive_mean_p']=float(p)
    output={'as_of':'2026-10-03','period':['2024-01-02','2026-10-02'],
        'primary_hypotheses_in_table':len(results),'results':results,
        'conventions':'Daily excess trading P&L, flat days retained;1xETF gross/entry exposure. Costs, funding and borrow conventions differ by family and remain in their protocols.',
        'inference_limit':'Conditional batch Holm correction and bootstrap do not fix source-author selection, prior research, or reuse of historical periods. No annualized Sharpe promise.',
        'source_hashes':{str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [HERE/'sectors/daily.json',HERE/'intraday/daily_corrected.json',HERE/'calendar/daily.json',HERE/'noise_breakout/daily.json',HERE/'pullback/daily.json']}}
    (HERE/'comparison.json').write_text(json.dumps(output,indent=2)+'\n')
    plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    fig,ax=plt.subplots(figsize=(11,6.5));fig.set_facecolor('#fafaf8');ax.set_facecolor('#fafaf8')
    for i,r in enumerate(results):
        b=r['base'];ci=b['sharpe_ci95'];s=r['stress']['sharpe']
        ax.plot(ci,[i,i],color='#b9bec7',lw=3,zorder=1)
        ax.scatter(b['sharpe'],i,color='#15607a',s=65,zorder=3)
        ax.scatter(s,i,color='#b85a41',s=50,marker='x',zorder=3)
        ax.annotate(f" {b['sharpe']:.2f}",(b['sharpe'],i),xytext=(4,7),textcoords='offset points',fontsize=10,color='#15607a')
    ax.axvline(0,color='#333333',lw=1);ax.set_yticks(range(len(results)),[r['name'] for r in results]);ax.invert_yaxis()
    ax.set_xlabel('Annualized net excess Sharpe — all 691 trading sessions')
    ax.set_title('S&P 500 research screen: costs and uncertainty matter',loc='left',fontweight='bold',pad=28)
    ax.text(0,1.025,'Jan 2024 – Oct 2, 2026  |  blue: base   ×: stress   gray: unadjusted 95% interval (20-day blocks)',transform=ax.transAxes,fontsize=9,color='#555555')
    ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    fig.text(.02,.02,'Historical screens, not validated live alphas. Sectors: 2/5 bp per side; other families: 1/3 bp. See reports for financing and borrow.',fontsize=9,color='#555555')
    fig.tight_layout(rect=(0,.05,1,1));fig.savefig(HERE/'comparison.png',dpi=170);plt.close(fig)
    print(json.dumps([{'name':r['name'],'sharpe':round(r['base']['sharpe'],3),'stress':round(r['stress']['sharpe'],3),'holm_p':round(r['base']['holm_positive_mean_p'],4)} for r in results],indent=2))


if __name__=='__main__':main()
