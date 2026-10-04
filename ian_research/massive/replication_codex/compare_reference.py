"""Read-only comparison of frozen independent results with saved old artifacts.

This script neither imports nor executes the original pricing/research scripts.
It reads original DataFrame caches through an explicit pickle type whitelist.
No original files are written; all output stays in this replication folder.
"""
from datetime import datetime, timezone
from collections import Counter
import hashlib
import json
from math import isfinite
from pathlib import Path
import pickle
import re
import statistics


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


class DataOnlyUnpickler(pickle.Unpickler):
    ALLOWED = {
        ("pandas", "DataFrame"), ("pandas.core.internals.managers", "BlockManager"),
        ("pandas._libs.internals", "_unpickle_block"),
        ("pandas._libs.arrays", "__pyx_unpickle_NDArrayBacked"),
        ("pandas.arrays", "StringArray"), ("pandas", "StringDtype"),
        ("pandas.core.arrays.string_", "StringDtype"),
        ("numpy._core.multiarray", "_reconstruct"), ("numpy", "ndarray"),
        ("numpy", "dtype"), ("numpy._core.multiarray", "scalar"), ("builtins", "slice"),
        ("pandas.arrays", "DatetimeArray"), ("numpy._core.numeric", "_frombuffer"),
        ("pandas.core.indexes.base", "_new_Index"), ("pandas", "Index"),
        ("pandas", "RangeIndex"), ("pandas.core.indexes.base", "Index"),
        ("pandas.core.indexes.range", "RangeIndex"),
    }

    def find_class(self, module, name):
        if (module, name) not in self.ALLOWED:
            raise ValueError("Unapproved pickle type " + module + "." + name)
        return super().find_class(module, name)


def load_dataframe(path):
    with path.open("rb") as stream:
        return DataOnlyUnpickler(stream).load()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row):
    return row["ticker"], row["filing_date"]


def finite_or_none(value):
    value = float(value)
    return value if isfinite(value) else None


def date_text(value):
    return value.strftime("%Y-%m-%d")


def main():
    frozen = json.loads((HERE / "before_original_review.json").read_text())
    unchanged = {name: file_hash(HERE / name) == digest for name, digest in frozen["sha256"].items()}
    if not all(unchanged.values()):
        raise ValueError("Frozen independent results changed")
    own = json.loads((HERE / "cache/event_results.json").read_text())
    insample = [row for row in own if row["filing_date"] < "2026-01-01"]
    oos = [row for row in own if row["filing_date"] >= "2026-01-01"]
    result_path = ROOT / ".massive_cache/derived/ideas2_results.pkl"
    quote_path = ROOT / ".massive_cache/derived/entry_quotes.pkl"
    results = load_dataframe(result_path)
    quotes = load_dataframe(quote_path)
    selected = results[(results.bucket == "3-6m") & (results.otm == 0.05)
                       & (results.entry == "post") & (results.horizon == 10)]
    old_rows = {(row.ticker, date_text(row.event_date)): row
                for row in selected.drop_duplicates(["ticker", "event_date"]).itertuples()}
    old_quotes = {(row.ticker, date_text(row.event_date), row.leg): row
                  for row in quotes.drop_duplicates(["ticker", "event_date", "leg"]).itertuples()}
    comparisons = []
    for trade in insample:
        old = old_rows.get(key(trade))
        q = old_quotes.get((*key(trade), "C_U0.05"))
        qk = old_quotes.get((*key(trade), "C_K"))
        original = {}
        if old is not None:
            original = {"entry": date_text(old.entry_date), "exit": date_text(old.exit_date),
                        "expiry": date_text(old.expiry), "entry_spot": finite_or_none(old.S_entry),
                        "exit_spot": finite_or_none(old.S_exit),
                        "entry_mark": finite_or_none(old.prem_CU * old.S_entry),
                        "gross": finite_or_none(old.covered_call - old.stock)}
            original["exit_mark"] = finite_or_none(old.prem_CU * old.S_entry - (old.covered_call - old.stock) * old.S_entry)
            if q is not None:
                original.update({"sold_call": q.contract, "strike": int(q.contract[-8:]) / 1000,
                                 "bid": finite_or_none(q.bid), "ask": finite_or_none(q.ask),
                                 "half_spread": finite_or_none(q.half_spread),
                                 "cost": finite_or_none(2 * q.half_spread / old.S_entry),
                                 "net": finite_or_none((old.covered_call - old.stock) - 2 * q.half_spread / old.S_entry)})
            if qk is not None:
                original["atm_strike"] = int(qk.contract[-8:]) / 1000
        original_valid = original.get("net") is not None
        comparison = {"ticker": trade["ticker"], "filing_date": trade["filing_date"],
                      "independent_status": trade["status"], "original_valid": original_valid,
                      "independent_drop_reason": trade["drop_reason"], "original": original,
                      "differences": {}, "numeric_deltas": {}}
        if original_valid != (trade["status"] == "valid"):
            comparison["differences"]["status"] = {"independent": trade["status"], "original_valid": original_valid}
        for field, value in original.items():
            if field not in trade or value is None or trade[field] is None:
                continue
            actual = trade[field]
            if isinstance(value, (int, float)):
                delta = actual - value
                comparison["numeric_deltas"][field] = delta
                if abs(delta) > 1e-10:
                    comparison["differences"][field] = {"independent": actual, "original": value}
            elif actual != value:
                comparison["differences"][field] = {"independent": actual, "original": value}
        comparisons.append(comparison)
    # The original OOS script persists only its rounded per-trade table plus
    # exact mean in the lock.  Do not manufacture unavailable exact references.
    report_path = ROOT / "research/oos/results.md"
    rounded = {}
    for line in report_path.read_text().splitlines():
        match = re.match(r"\| ([A-Z.]+) \| (2026-\d{2}-\d{2}) \| (.*?) \|", line)
        if match:
            rounded[(match[1], match[2])] = match[3]
    oos_comparisons = []
    for trade in oos:
        published = rounded.get(key(trade))
        own_published = f"{trade['net'] * 100:+.2f}%" if trade["status"] == "valid" else ""
        oos_comparisons.append({"ticker": trade["ticker"], "filing_date": trade["filing_date"],
                               "independent_status": trade["status"], "independent_drop_reason": trade["drop_reason"],
                               "independent_net": trade.get("net"), "original_net_published": published,
                               "matches_published_precision": own_published == published})
    lock_path = ROOT / "research/OOS_LOCK.json"
    lock = json.loads(lock_path.read_text())
    i_old = [row["original"]["net"] for row in comparisons if row["original_valid"]]
    i_own = [row["net"] for row in insample if row["status"] == "valid"]
    o_own = [row["net"] for row in oos if row["status"] == "valid"]
    max_deltas = {}
    for row in comparisons:
        for field, delta in row["numeric_deltas"].items():
            max_deltas[field] = max(max_deltas.get(field, 0), abs(delta))
    sources = [result_path, quote_path, report_path, lock_path,
               ROOT / "research/round3.py", ROOT / "research/sharpe_deal.py", ROOT / "research/oos_deal.py", ROOT / "eightk.py"]
    output = {
        "comparison_completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "own_numbers_frozen_before_original_review_at_utc": frozen["recorded_at_utc"],
        "frozen_artifacts_unchanged": unchanged,
        "original_harness_executed_or_imported": False,
        "network_requests": 0,
        "sources_sha256": {str(path.relative_to(ROOT)): file_hash(path) for path in sources},
        "in_sample": {
            "events_compared": len(comparisons), "independent_valid": len(i_own), "original_valid": len(i_old),
            "independent_mean_net": statistics.mean(i_own), "original_mean_net": statistics.mean(i_old),
            "mean_net_delta": statistics.mean(i_own) - statistics.mean(i_old),
            "original_std_sample": statistics.stdev(i_old),
            "original_win_rate": sum(net > 0 for net in i_old) / len(i_old),
            "material_differences_at_absolute_tolerance_1e_10": [row for row in comparisons if row["differences"]],
            "max_absolute_deltas": max_deltas,
            "reference_field_coverage_on_valid_trades": dict(Counter(
                field for row in comparisons if row["original_valid"]
                for field, value in row["original"].items() if value is not None)),
            "comparisons": comparisons,
        },
        "2026": {
            "events_compared": len(oos_comparisons), "independent_valid": len(o_own),
            "original_valid": lock["primary"]["n"], "independent_mean_net": statistics.mean(o_own),
            "original_mean_net": lock["primary"]["sold_call_net_mean"],
            "mean_net_delta": statistics.mean(o_own) - lock["primary"]["sold_call_net_mean"],
            "all_statuses_and_per_trade_nets_match_at_published_precision": all(row["matches_published_precision"] for row in oos_comparisons),
            "reference_limitations": "Original 2026 harness saved per-trade returns only at 0.01 percentage-point precision, and saved an exact aggregate mean. It did not persist exact per-trade strike, expiry, spots, premiums, or costs. Those fields cannot be independently compared with a saved original result without rerunning original code; no such rerun was performed.",
            "comparisons": oos_comparisons,
        },
        "scope_note": "In-sample full-resolution comparison is conditional on independently identified 40 kept event keys; no original event/pricing harness was run. Initial spot estimates are not present in the original derived result cache and cannot be compared directly. Exact spot comparisons refer to target-expiry entry and exit parity spots.",
    }
    (HERE / "reference_comparison.json").write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"in_sample": {k: v for k, v in output["in_sample"].items() if k != "comparisons"},
                      "2026": {k: v for k, v in output["2026"].items() if k != "comparisons"}}, indent=2))


if __name__ == "__main__":
    main()
