"""Build the results dashboard (single self-contained HTML) from run_all.py outputs.

Usage: python scripts/build_dashboard.py  ->  results/dashboard.html
Every number shown is read from results/ files, so the page cannot disagree with the note or the code.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"


def safe(x):
    if isinstance(x, (float, np.floating)):
        return None if not np.isfinite(x) else round(float(x), 6)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, dict):
        return {str(k): safe(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [safe(v) for v in x]
    return x


def followups() -> list:
    """Every test registered after the primary failed, read from its own result file."""
    rows = []
    j = lambda p: json.loads(p.read_text()) if p.exists() else None
    o = j(RES / "overfit_study.json")
    if o:
        rows.append(["Best of 192 optimized variants", f"in-sample {o['best_is_sharpe']:.2f} vs {o['best_dsr']['sr_star_annual']:.2f} expected from luck; PBO {100*o['pbo']['pbo']:.0f}%", f"{o['winner_oos_sharpe']:.2f} out-of-sample", "fail"])
    w = j(RES / "walk_forward.json")
    if w:
        rows.append(["Walk-forward optimization", "each year trades the best variant of all prior years", f"Sharpe {w['walk_forward_all']['sharpe']:.2f}", "fail"])
    h2 = j(ROOT / "results_h2" / "summary.json")
    if h2 and h2.get("oos"):
        rows.append(["H2: same signal, 20 less-watched CEOs", f"{h2['primary_IS']['n_traded']}+{h2['oos']['n_traded']} trades; IC {h2['event_tests_IS'].get('ic_ic', 0):.3f} / {h2['oos']['event_tests'].get('ic_ic', 0):.3f}", f"Sharpe {h2['primary_IS']['sharpe']:.2f} / {h2['oos']['sharpe']:.2f}", "fail"])
    for f, lab in ((RES / "h3_drift_OOS.json", "H3: post-interview drift (original, sealed window)"), (ROOT / "results_h2" / "h3_drift_ALL.json", "H3: post-interview drift (H2 universe)")):
        h = j(f)
        if h:
            rows.append([lab, f"excess 20d CAR vs same stocks on random days, CI [{100*h['ci95'][0]:.1f}%, {100*h['ci95'][1]:.1f}%]", f"{100*h['mean_excess']:.2f}%", "pass" if h["supports_h3_here"] else "fail"])
    h4 = j(RES / "h4_intraday.json")
    if h4 and h4.get("a_native", {}).get("n", 0) >= 5:
        a = h4["a_native"]
        rows.append(["H4: intraday reaction, Musk + Karp (1-min bars)", f"{a['n']} YouTube-native videos; IC {a['ic']:.3f}, t {a['t_date_clustered']:.2f}", f"{a['mean_signed_net_bps']:.1f} bps/trade", "pass" if h4.get("supports_H4") else "fail"])
    return rows


def main() -> None:
    s = json.loads((RES / "summary.json").read_text())
    daily = pd.read_csv(RES / "daily_returns_IS.csv", index_col=0, parse_dates=True)
    eq = (1 + daily.fillna(0)).cumprod()
    weekly = eq.resample("W").last()
    oos = None
    if (RES / "oos_daily.csv").exists():
        od = pd.read_csv(RES / "oos_daily.csv", index_col=0, parse_dates=True).iloc[:, 0]
        oos = ((1 + od.fillna(0)).cumprod() * float(eq["net"].iloc[-1])).resample("W").last()
    ev = pd.read_csv(RES / "events.csv", parse_dates=["entry"])
    uni = pd.read_csv(ROOT / "config" / "universe.csv")
    names = dict(zip(uni["ceo_id"], uni["name"]))
    ceos = {}
    for c, g in ev.groupby("ceo_id"):
        g = g.sort_values("entry")
        ceos[c] = {"name": names.get(c, c), "ticker": g["ticker"].iloc[0],
                   "points": [[d.strftime("%Y-%m-%d"), safe(t), safe(car)] for d, t, car in
                              zip(g["entry"], g["tell"], g.get("car_20", pd.Series(np.nan, index=g.index)))]}
    data = {
        "summary": safe(s),
        "equity": {"dates": [d.strftime("%Y-%m-%d") for d in weekly.index],
                   "net": safe(weekly["net"].tolist()), "gross": safe(weekly["gross"].tolist()),
                   "x2": safe(weekly["net_costs_x2"].tolist()),
                   "oos_dates": [d.strftime("%Y-%m-%d") for d in oos.index] if oos is not None else [],
                   "oos": safe(oos.tolist()) if oos is not None else []},
        "robust": safe(pd.read_csv(RES / "robustness.csv").to_dict("records")),
        "decay": safe(pd.read_csv(RES / "alpha_decay.csv").to_dict("records")),
        "per_ceo": safe(pd.read_csv(RES / "per_ceo.csv").to_dict("records")),
        "ceos": ceos,
        "followups": followups(),
    }
    tpl = (ROOT / "scripts" / "dashboard_template.html").read_text()
    out = RES / "dashboard.html"
    out.write_text(tpl.replace("/*__DATA__*/null", json.dumps(data)))
    print("wrote", out, f"({out.stat().st_size / 1e3:.0f} KB)")


if __name__ == "__main__":
    main()
