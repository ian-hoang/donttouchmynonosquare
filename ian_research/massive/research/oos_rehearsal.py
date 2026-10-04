"""Rehearsal of oos_deal.py's code path on the in-sample window (2024-2025), to catch bugs before the
one-shot out-of-sample run. Must reproduce the in-sample numbers in FINDINGS.md section 7. Touches no 2026 data."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import eightk as K  # noqa: E402
from ideas2 import OTM, all_filings, pick_peers  # noqa: E402
from oos_deal import DEALS, H, PRIMARY, entry_half_spreads, insample_company_usual, one_per_deal, sold_call_tables, vs_peers  # noqa: E402

ev = one_per_deal(K.build_events(DEALS, K.STUDY_START, K.STUDY_END, timing="next_session")).reset_index(drop=True)
peers = pick_peers(ev, all_filings())
keys = sorted({(r.ticker, r.t_pre, r.t_0, r.event_date) for r in ev.itertuples()} |
              {(r.ticker, r.t_pre, r.t_0, r.event_date) for r in peers.itertuples()}, key=lambda k: (k[0], k[3]))
priced, _ = K.price_many(keys, {"3-6m": K.EXPIRY_BUCKETS["3-6m"]}, [OTM], workers=16, label="rehearsal")
res = K.evaluate([pe for v in priced.values() for pe in v], [OTM])
sold, full = sold_call_tables(res, entry_half_spreads(priced))
E, D = vs_peers(sold, ev, peers)
DD = D - insample_company_usual().reindex(ev.ticker.to_numpy()).to_numpy()
j = H.index(PRIMARY)
print(f"in-sample rehearsal: {len(ev)} deals, valid at h=10: {int((~np.isnan(E[:, j])).sum())}; "
      f"sold call net {np.nanmean(E[:, j]):+.2%}; vs peers {np.nanmean(D[:, j]):+.2%}; vs peers and usual {np.nanmean(DD[:, j]):+.2%}")
print("expected from FINDINGS section 7: 40 deals, 30 valid, net +0.64%, vs peers ≈ +0.96% (different peer draw), vs usual ≈ +0.63%")
