"""G-1m follow-up (hypotheses/BRAINSTORM2.md): resolved vs created 8-Ks with 1-month options. In-sample only."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import eightk as K  # noqa: E402
from ideas2 import (CREATED, OTM, RESOLVED, all_filings, company_days, contrast_table, has_any,  # noqa: E402
                    metric_tables, pick_peers, vs_peers)


def main():
    counts = pd.read_csv(HERE / "event_counts.csv", index_col=0)
    raw = all_filings()
    cd = company_days(raw, set(counts.index[counts.primary_category == "financial_results"]))
    peers = pick_peers(cd, raw)                                   # same seed, same peers as ideas2.py
    gA = cd.tags.map(lambda s: has_any(s, RESOLVED)) & ~cd.tags.map(lambda s: has_any(s, CREATED))
    gB = cd.tags.map(lambda s: has_any(s, CREATED)) & ~cd.tags.map(lambda s: has_any(s, RESOLVED))
    ev = cd[gA | gB]
    pe = peers[peers.event_date.isin(ev.event_date)]
    keys = sorted({(r.ticker, r.t_pre, r.t_0, r.event_date) for r in ev.itertuples()} |
                  {(r.ticker, r.t_pre, r.t_0, r.event_date) for r in pe.itertuples()}, key=lambda k: (k[0], k[3]))
    buckets = {"1m": K.EXPIRY_BUCKETS["1m"], "3-6m": K.EXPIRY_BUCKETS["3-6m"]}   # dte_hi 180: same cached chains
    priced, _ = K.price_many(keys, buckets, [OTM], workers=16, label="G-1m")
    T = metric_tables(K.evaluate([p for v in priced.values() for p in v], [OTM]), bucket="1m")
    cl = cd.ticker.to_numpy()
    out = []
    for m, lab in [("bought_put", "1m bought put vs peers"), ("cash_secured_put", "1m cash-secured put vs peers"),
                   ("ratio", "1m |realized| ÷ implied vs peers")]:
        V = vs_peers(T[m], cd, peers)
        out.append(f"## G-1m · Resolved vs created · {lab}\n\n" +
                   contrast_table(V[gA], cl[gA], V[gB], cl[gB], "RESOLVED", "CREATED", pct=(m != "ratio")))
    text = "\n\n".join(out)
    print(text)
    with open(HERE / "ideas2" / "results.md", "a") as f:
        f.write("\n" + text + "\n")


if __name__ == "__main__":
    main()
