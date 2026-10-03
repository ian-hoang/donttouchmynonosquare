"""Write the headline results table into README.md between the RESULTS markers, from results/summary.json."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
s = json.loads((ROOT / "results" / "summary.json").read_text())
p, o = s["primary_IS"], s.get("oos") or {}
f = lambda v, pct=False: "n/a" if v is None else (f"{100 * v:.1f}%" if pct else f"{v:.2f}")
rows = [("Events traded", p.get("n_traded"), o.get("n_traded")),
        ("Annualized return (net)", f(p.get("ann_return"), True), f(o.get("ann_return"), True)),
        ("Volatility", f(p.get("ann_vol"), True), f(o.get("ann_vol"), True)),
        ("Sharpe, net (gross)", f"{f(p.get('sharpe'))} ({f(p.get('gross_sharpe'))})", f"{f(o.get('sharpe'))} ({f(o.get('gross_sharpe'))})" if o else "sealed"),
        ("Sharpe, costs ×2", f(s["costs_x2_IS"].get("sharpe")), f(o.get("sharpe_costs_x2"))),
        ("Max drawdown", f(p.get("max_drawdown"), True), f(o.get("max_drawdown"), True)),
        ("Turnover (× capital / yr)", f(p.get("turnover_x_per_year")), f(o.get("turnover_x_per_year")))]
tbl = ["| | In-sample (2016-01 – 2024-09) | Out-of-sample (2024-10 – 2026-09, evaluated once) |", "|---|---|---|"]
tbl += [f"| {a} | {b} | {c} |" for a, b, c in rows]
dsr = s.get("dsr", {})
tbl += ["", f"Deflated Sharpe {f(dsr.get('dsr'))} over {dsr.get('n_trials')} logged trials · FOLK placebo Sharpe "
        f"{f(s['folk_placebo']['summary'].get('sharpe'))} · config `{s['config_hash']}` · full report: `results/summary.md`"]
block = "<!-- RESULTS:START -->\n" + "\n".join(tbl) + "\n<!-- RESULTS:END -->"
r = (ROOT / "README.md").read_text()
if "<!-- RESULTS:START -->" in r:
    r = re.sub(r"<!-- RESULTS:START -->.*<!-- RESULTS:END -->", block, r, flags=re.S)
else:
    r = r.replace("## Reproduce the headline numbers", "## Headline results\n\n" + block + "\n\n## Reproduce the headline numbers", 1)
(ROOT / "README.md").write_text(r)
print("README results updated")
