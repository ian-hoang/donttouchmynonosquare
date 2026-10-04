"""Replay frozen, outcome-blind compensation source annotations.

This script does not fetch prices or infer that missing terms are unchanged.
Run from any directory with the repository's Python interpreter.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE.parents[1] / ".massive_cache/codex_six/compensation_candidates_raw.json"


def main() -> None:
    raw_bytes = RAW.read_bytes()
    raw = json.loads(raw_bytes)
    annotations = json.loads((HERE / "compensation_annotations.json").read_text())
    spec = json.loads((HERE / "compensation_spec.json").read_text())
    assert hashlib.sha256(raw_bytes).hexdigest() == annotations["raw_sha256"]
    rows = annotations["filings"]
    identity = lambda r: (r["ticker"], r["filing_date"], r["accession_number"])
    assert len(rows) == len(raw) == len({identity(r) for r in rows})
    assert {identity(r) for r in rows} == {identity(r) for r in raw}
    assert all("2024-01-01" <= r["filing_date"] <= "2025-12-31" for r in rows)
    assert annotations["outcomes_seen"] is False
    events, controls = [], []
    for row in rows:
        if row["classification"] not in {"event", "control"}:
            continue
        assert row["review_scope"] == "primary_source_terms"
        assert row.get("comparison_verified") and row.get("sources")
        if row["classification"] == "event":
            assert row.get("same_metric_duration_units")
            assert row.get("hurdle_reduction_percent", 0) > 0 or row.get("explicit_hurdle_removal")
            events.append(row)
        else:
            assert row.get("all_relevant_hurdles_verified")
            assert not row.get("unverified_material_hurdle", True)
            controls.append(row)
    counts = Counter(r["classification"] for r in rows)
    source_urls = {u for r in rows if r["review_scope"] == "primary_source_terms"
                   for u in r["sources"]}
    manifest = {
        "spec": "compensation_spec.json",
        "signal": spec["signal"],
        "strategy": spec["strategy"],
        "status": "no_verified_positive_signals_partial_full_source_coverage" if not events else "economic_signal_audit",
        "events": events,
        "controls": controls,
        "unclassified": [r for r in rows if r["classification"] == "unclassified"],
        "audit_counts": {
            "candidate_filings": len(rows),
            "supporting_text_screened": len(rows),
            "filings_with_primary_source_terms_reviewed": sum(r["review_scope"] == "primary_source_terms" for r in rows),
            "unique_primary_documents_reviewed": len(source_urls),
            "events": len(events), "controls": len(controls),
            "by_classification": dict(sorted(counts.items())),
        },
        "limitations": annotations["limitations"],
    }
    (HERE / "compensation_events.json").write_text(json.dumps(manifest, indent=2) + "\n")
    audit = {"spec": manifest["spec"], "status": manifest["status"],
             "audit_counts": manifest["audit_counts"], "outcomes_seen": False,
             "interpretation": "No verified qualifying trades. This is an untestable verified manifest, not evidence that the signal never occurs or has zero alpha.",
             "filings": rows, "limitations": annotations["limitations"]}
    (HERE / "compensation_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(manifest["audit_counts"], indent=2))


if __name__ == "__main__":
    main()
