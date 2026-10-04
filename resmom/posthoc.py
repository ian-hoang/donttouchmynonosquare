"""POST-HOC (not pre-registered): is RESID's net Sharpe edge over MOM bigger than noise?

Paired circular block bootstrap (21-session blocks, 2,000 reps) of daily net (10 bp) L/S returns.
Run after resmom/backtest.py: uv run python resmom/posthoc.py
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

from backtest import MAIN_BPS, net, sharpe

HERE = Path(__file__).resolve().parent
res = pd.read_pickle(HERE / "out" / "results.pkl")["res"]
S = pd.DataFrame({k: net(res[k]["gross"], res[k]["turn"], MAIN_BPS) for k in ("mom", "resid", "resid_b")}).dropna()
rng = np.random.default_rng(7)
n, B = len(S), 21
A = S.to_numpy()
draws = []
for _ in range(2000):
    st = rng.integers(0, n, math.ceil(n / B))
    idx = ((st[:, None] + np.arange(B)) % n).ravel()[:n]
    x = A[idx]
    draws.append(x.mean(0) / x.std(0, ddof=1) * math.sqrt(252))
D = np.array(draws)
lines = [f"daily corr: {S.corr().round(2).to_dict()}"]
for j, k in ((1, "resid"), (2, "resid_b")):
    d = D[:, j] - D[:, 0]
    lines.append(f"{k} - mom net Sharpe: {sharpe(S[k]) - sharpe(S['mom']):+.2f}, 95% CI [{np.percentile(d, 2.5):+.2f}, "
                 f"{np.percentile(d, 97.5):+.2f}], share of draws <= 0: {(d <= 0).mean():.2f}")
# vol-matched view: scale MOM to RESID's vol, compare annual return
lines.append(f"annual net return at RESID's vol: mom {S.mom.mean() / S.mom.std() * S.resid.std() * 252:.1%}, "
             f"resid {S.resid.mean() * 252:.1%}")
(HERE / "out" / "posthoc.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
