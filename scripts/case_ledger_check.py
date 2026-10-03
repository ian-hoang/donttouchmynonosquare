"""Illustration only (not a test): tell scores of a CEO's interviews in the 180 days before a later-contradicted
statement came undone, relative to that CEO's own distribution. Cases come from docs/research/case_ledger.csv,
which was compiled with hindsight, so this cannot validate the signal; it shows what the measurement looked like.

Usage (after run_all.py): python scripts/case_ledger_check.py -> results/case_ledger_check.csv
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
CASES = ["C06", "C10", "C14", "C02", "C03"]


def main() -> None:
    led = pd.read_csv(ROOT / "docs" / "research" / "case_ledger.csv")
    ev = pd.read_csv(RES / "events.csv", parse_dates=["entry"])
    uni = pd.read_csv(ROOT / "config" / "universe.csv")
    t2c = dict(zip(uni["ticker"], uni["ceo_id"]))
    rows = []
    for c in led[led["id"].isin(CASES)].itertuples():
        ceo = t2c.get(c.ticker)
        e = ev[(ev["ceo_id"] == ceo) & ev["tell"].notna()]
        if e.empty:
            continue
        end = pd.Timestamp(c.contradicting_event_date)
        win = e[(e["entry"] < end) & (e["entry"] >= end - pd.Timedelta(days=180))]
        pct = e["tell"].rank(pct=True)
        rows.append({"case": c.id, "ceo": ceo, "ticker": c.ticker, "contradicting_event_date": c.contradicting_event_date,
                     "interviews_in_window": int(len(win)),
                     "mean_tell_percentile_in_window": float(pct.loc[win.index].mean()) if len(win) else None,
                     "max_tell_percentile_in_window": float(pct.loc[win.index].max()) if len(win) else None,
                     "mean_car_20_after_those_interviews": float(win["car_20"].mean()) if len(win) and "car_20" in win else None,
                     "safe_wording": c.safe_wording})
    out = pd.DataFrame(rows)
    out.to_csv(RES / "case_ledger_check.csv", index=False)
    print(out.drop(columns=["safe_wording"]).round(3).to_string(index=False) if len(out) else "no cases matched")


if __name__ == "__main__":
    main()
