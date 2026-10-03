"""Reproduce every number and figure in the quant note for the FINAL strategy.

    uv run python run_all.py            # in-sample report only; out-of-sample stays locked
    uv run python run_all.py --final    # evaluate out-of-sample (do this ONCE, at the end)

Output: results/<strategy>/summary.md plus figures, laid out in the order of note/NOTE_TEMPLATE.md.

The first --final run writes results/OOS_LOCK.json (commit it). Later --final runs with the same
strategy file and params reproduce the numbers; anything else is refused unless you pass
--relock "reason", which is recorded in the lock history so you can disclose it in the note.
"""
import argparse
import json
from datetime import datetime

import pandas as pd

import strategies
from gqh import RESULTS, analysis, ledger, metrics, report, research
from gqh.checks import data_quality, lookahead_check

FINAL = {
    "strategy": "example_tsmom",
    "params": {"lookback": 60},
    # Neighbouring values to show the result isn't a lucky spike (the plateau check)
    "plateau": {"lookback": [20, 40, 60, 90, 120, 180, 250]},
    # Capacity estimate. Turnover, Sharpe, vol and costs come from the backtest; ADV comes from the
    # strategy's dollar_volume(). Set any key here to override, or set "capacity" to None to skip.
    "capacity": {"aum": 10e6},
}

LOCK = RESULTS / "OOS_LOCK.json"


def check_lock(strat, params, relock_reason):
    entry = {"strategy": strat.name, "params": params, "code": ledger.code_hash(strat)}
    history = json.loads(LOCK.read_text())["history"] if LOCK.exists() else []
    if history and {k: history[-1][k] for k in entry} == entry:
        return history, "reproduction of the locked evaluation"
    if history and not relock_reason:
        raise SystemExit(
            "Out-of-sample was already evaluated with a different strategy, params or strategy code:\n"
            f"  locked: {history[-1]}\n  now:    {entry}\n"
            "Changing things after seeing out-of-sample results is tuning on the test set. If you must "
            '(e.g. a real bug fix), rerun with --relock "reason" and disclose it in the note.')
    reason = relock_reason or "first evaluation"
    history.append({**entry, "time": datetime.now().isoformat(timespec="seconds"), "reason": reason})
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(json.dumps({"history": history}, indent=2))
    return history, reason


def capacity_inputs(strat, prep, is_run, overrides: dict) -> dict:
    net = metrics.summarize(is_run.net, is_run.turnover, is_run.periods_per_year)
    gross = metrics.summarize(is_run.gross, is_run.turnover, is_run.periods_per_year)
    returns = metrics.daily_frame(strat.asset_returns(prep.in_sample))
    inputs = {"aum": 10e6, "names": returns.shape[1], "turnover": net["turnover"],
              "gross_sharpe": gross["sharpe"], "strategy_vol": net["ann_vol"], "fixed_bps": strat.cost_bps,
              "daily_vol": float(returns.tail(252).std().mean())}
    dollar_volume = strat.dollar_volume(prep.in_sample)
    if dollar_volume is not None:
        inputs["adv_per_name"] = float(metrics.daily_frame(dollar_volume, "sum").tail(252).median().mean())
    inputs.update(overrides)
    return inputs


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--final", action="store_true", help="evaluate the out-of-sample period")
    p.add_argument("--relock", metavar="REASON", help="re-evaluate out-of-sample after a change, with a reason")
    args = p.parse_args()

    strat = strategies.get(FINAL["strategy"])
    params = research.params_for(strat, FINAL["params"])
    prep = research.prepare(strat)
    oos = prep.oos_start
    out = RESULTS / strat.name
    out.mkdir(parents=True, exist_ok=True)
    md = [f"# {strat.name}: results\n",
          f"Generated {datetime.now():%Y-%m-%d %H:%M} by `run_all.py{' --final' if args.final else ''}`. "
          f"Params: `{json.dumps(params)}`. Costs: {strat.cost_bps:g} bps per side.\n",
          f"Out-of-sample starts {oos:%Y-%m-%d} (most recent 20% or 2 years, whichever is shorter).\n"]

    if args.final:
        history, status = check_lock(strat, params, args.relock)
        md.append(f"Out-of-sample status: **{status}** (evaluations so far: {len(history)}).\n")
        data = prep.data
    else:
        md.append("Out-of-sample: **locked** (run with `--final` once, at the end).\n")
        data = prep.in_sample

    # Hypothesis came first?
    hyp = research.hypothesis_status(strat)
    first = ledger.first_run(strat.name)
    md.append("## Hypothesis timing\n")
    md.append(f"`{hyp['path']}` first committed: **{hyp['committed'] or 'NOT COMMITTED'}**. "
              f"First logged backtest on this machine: {first or 'none'}.\n")

    # Data quality
    dq = data_quality(strat.asset_returns(data))
    md.append("## Data checks\n")
    md.append(report.md_table(dq) + "\n")
    md.extend(f"- Flag: {f}\n" for f in dq.attrs["flags"])

    # Lookahead check
    look = lookahead_check(strat, data, params)
    md.append("## Lookahead check\n")
    md.append(f"Weights recomputed on truncated data match the full-data weights: "
              f"**{'PASS' if look['passed'] else 'FAIL'}** (max difference {look['max_diff']:.2e}).\n")

    # Headline performance: gross, net, costs x2; in-sample vs out-of-sample
    runs = {mult: research.run(strat, data, params, mult) for mult in (1.0, 2.0)}
    main_run = runs[1.0]
    is_run = main_run.in_sample(oos)
    columns = {"In-sample, gross": metrics.summarize(is_run.gross, is_run.turnover, is_run.periods_per_year)}
    exposures = {}
    for mult, res in runs.items():
        tag = "" if mult == 1 else ", costs x2"
        parts = [("In-sample", res.in_sample(oos))] + ([("Out-of-sample", res.out_of_sample(oos))] if args.final else [])
        for label, r in parts:
            columns[f"{label}{tag}"] = metrics.summarize(r.net, r.turnover, r.periods_per_year)
            if mult == 1:
                exposures[label] = metrics.exposure(r.positions)
    perf = metrics.table(columns)
    perf.to_csv(out / "performance.csv")
    md.append("## Performance (net of costs unless marked gross)\n")
    md.append(report.md_table(perf) + "\n")
    warns = [w for m in columns.values() for w in metrics.warnings(m)]
    md.extend(f"- Warning: {w}\n" for w in dict.fromkeys(warns))
    print(perf.to_string(), "\n")

    md.append("## Exposure (risk actually carried)\n")
    md.append(report.md_table(pd.DataFrame(exposures), fmt="{:.2f}") + "\n")

    shown = main_run if args.final else is_run
    report.equity_curve(shown.net, shown.gross, oos if args.final else None,
                        out / "equity_curve.png", f"{strat.name}: growth of $1")
    yearly = analysis.by_year(shown.net)
    report.bars_by_year(yearly, oos.year if args.final else None, out / "by_year.png",
                        f"{strat.name}: net return by year")
    md.append("![Equity curve](equity_curve.png)\n\n![By year](by_year.png)\n")
    md.append("## Net return by year\n")
    md.append(report.md_table(yearly.rename("net_return").to_frame(), fmt="{:.1%}") + "\n")

    # Parameter plateau (in-sample only)
    for param, values in (FINAL.get("plateau") or {}).items():
        sharpes = [research.evaluate(strat, prep.in_sample, {**params, param: v}, kind="sensitivity")[1]["sharpe"]
                   for v in values]
        report.plateau(values, sharpes, params[param], param, out / f"plateau_{param}.png")
        md.append(f"## Plateau: {param}\n\n![Plateau](plateau_{param}.png)\n")
        md.append(report.md_table(pd.DataFrame({param: values, "in_sample_sharpe": sharpes}).set_index(param),
                                  fmt="{:.2f}") + "\n")

    # Variants tried and the Deflated Sharpe Ratio
    st = ledger.stats()
    dsr = metrics.deflated_sharpe(is_run.net, max(st["n_trials"], 1), st["var_sharpe_pp"])
    md.append("## Variants tried\n")
    md.append(f"Distinct configurations in this machine's ledger: **{st['n_trials']}**. Add your teammates' "
              f"counts (`uv run python -m gqh.ledger`) for the total you disclose.\n")
    md.append(f"Deflated Sharpe Ratio (in-sample, {dsr['n_trials']} trials): **{dsr['dsr']:.2f}**, the probability the "
              f"true Sharpe is above what the luckiest of {dsr['n_trials']} zero-edge variants would show.\n")

    # Factor exposure
    md.append("## Factor exposure (Ken French daily factors, Newey-West t-stats)\n")
    try:
        for label, res in [("In-sample", is_run)] + ([("Out-of-sample", main_run.out_of_sample(oos))] if args.final else []):
            reg = analysis.factor_regression(res.net)
            md.append(f"**{label}** (R² {reg.attrs['r2']:.2f}, {reg.attrs['n_days']} days)\n")
            md.append(report.md_table(reg, fmt="{:.3f}") + "\n")
    except Exception as e:  # network down, or too little overlap
        md.append(f"Skipped: {e}\n")

    # Capacity
    if FINAL.get("capacity") is not None:
        md.append("## Capacity (square-root impact model)\n")
        inputs = capacity_inputs(strat, prep, is_run, FINAL["capacity"])
        if "adv_per_name" not in inputs:
            md.append("Skipped: define `dollar_volume()` in the strategy or set `adv_per_name` in FINAL['capacity'].\n")
        else:
            cap = analysis.capacity(**inputs)
            md.append("Inputs: " + ", ".join(f"{k}={v:,.4g}" for k, v in inputs.items()) + "\n")
            md.append(f"Net Sharpe at ${cap['aum']:,.0f}: **{cap['net_sharpe']:.2f}** "
                      f"(cost {cap['cost_bps']:.1f} bps/trade, {cap['participation']:.2%} of ADV). "
                      f"Edge half gone near **${cap['half_edge_aum']:,.0f}**; "
                      f"capacity (net Sharpe 0) about **${cap['capacity']:,.0f}**.\n")

    (out / "summary.md").write_text("\n".join(md))
    print(f"Lookahead check: {'PASS' if look['passed'] else 'FAIL'}")
    for w in dict.fromkeys(warns):
        print(f"WARNING: {w}")
    print(f"Wrote {out.relative_to(RESULTS.parent)}/summary.md and figures")


if __name__ == "__main__":
    main()
