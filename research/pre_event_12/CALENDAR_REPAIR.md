# Calendar-boundary repair after first evaluation

The independent final audit found that `searchsorted` returned `len(calendar)` for a future advertised earnings date. Subtracting one incorrectly mapped the exit to the final available session. A future CSX release (2026-10-21) thereby entered the five-session validation baseline.

The repair explicitly rejects releases outside calendar coverage and beyond the completed-event study cutoff of 2026-09-30. Trading rules, thresholds, prices, costs and selection parameters are unchanged. A regression test covers future dates and the valid final covered session. Both evaluation periods are rerun; this is a correctness repair after observing initial results, not a new untouched holdout.

The original code, windows, report, frozen manifest and outputs are preserved in `data/audit_pre_calendar_repair/`. A new manifest hashes the repaired implementation before rerunning. Selected-trade and threshold differences are recorded after rerunning.

The corrected preparation removed only `CSX_2026-10-21_5` (192 to 191 event/window rows). All 24 selected-trade output files are byte-identical to the original evaluation, and both periods’ threshold files are unchanged. No headline selected-trade, portfolio or baseline-with-valid-feature statistic changed. The future event had neither usable IV nor a usable jackpot signal.
