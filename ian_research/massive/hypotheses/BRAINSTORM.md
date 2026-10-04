# Massive "Trade the 8-K": candidate pairings (draft, written before any results)

Status: draft for Ian to pick from. No option prices or returns have been looked at for any of these.
The one exception, disclosed: the challenge page already showed the starter's CFO-appointment result
(collar best, +0.42% gross, −0.18% net, no interval excluding zero). Any idea that reuses
`cfo_appointment` carries that small data-snoop and must say so.

Tag names below are guesses until the taxonomy is pulled (`research/count_events.py`). Event counts
are filled in from that script: in-sample (2024–2025) events at the top 100. They're counts only, no returns.

## One idea that applies to every pairing: split the strategy into "stock" and "option overlay"

Three of the five strategies own the (synthetic) stock, so their P&L is mostly the stock's own move,
and that noise swamps everything (21-session stock moves are about ±6%). The challenge's real question
("was the event priced in?") is about the **option part** only. We report each strategy two ways:

- the full strategy against ordinary days (what the rubric asks for), and
- the **overlay alone** (strategy minus stock: the sold call, the bought or sold put) against ordinary days.

The overlay is much less noisy, so it can give us tighter intervals on the same events. It also shows
whether an "edge" is really option mispricing or just the stock drifting.

## Rigor upgrades we plan regardless of the pairing

1. **Fix the filing-time look-ahead before pricing.** The starter enters at the close of the filing
   date, but a filing accepted after 4 pm can't be traded that day. The starter's fix runs *after*
   pricing (so as shipped, the default run has this look-ahead). We move it before pricing.
2. **Placebo days matched on the earnings cycle.** The challenge has no earnings calendar, but
   earnings releases are themselves 8-Ks (the `financial_results` family). We use them as a calendar
   and draw placebo days that sit at the same point in the quarter as the events. Without this, any
   category that clusters right after earnings will look special just because of *when* it happens.
3. **A negative-control category.** A tag that should carry no information (bylaw amendments or
   shareholder-vote results). If our method finds an "edge" there, the method is broken.
4. **OOS gated off** until the final rule is frozen. The starter's "Run All" runs the OOS section
   every time, so we add a `RUN_OOS = False` switch.

## Candidate pairings

| # | Category (tag guess) | Strategy | Who's wrong, and which way | Novelty | In-sample events |
|---|---|---|---|---|---|
| A | New leadership: `ceo_appointment` (+ `cfo_appointment`) | 3 · Protective put, held through the first earnings | Options price the new boss's first earnings like any other. New executives tend to take write-offs and reset guidance early (the "big bath"), so that earnings move is bigger and more often down: **puts too cheap** | High | TBD |
| B | Securities offering: debt / notes issuance | 5 · Cash-secured put | A company can't sell bonds while hiding bad news (prospectus liability, underwriter due diligence), so an offering certifies "no hidden bad news right now". Put prices still carry the usual crash premium: **puts too expensive** | High | TBD |
| C | Uncertainty resolved: litigation / regulatory settlement | 5 · Cash-secured put | A pending lawsuit fattens the put side of the chain. After the settlement that tail risk is gone, but put prices adjust slowly: **puts too expensive** | High | TBD |
| D | Buyback execution: accelerated share repurchase / repurchase agreement | 2 · Covered call | A bank buying shares steadily for weeks props up the price and calms day-to-day swings. The chain doesn't price that steady buyer: **calls too expensive** | Medium-high | TBD |
| E | Equity grants to executives (comp award 8-Ks) | 5 · Cash-secured put | Boards tend to time grants before good news ("spring-loading"). Comp filings are treated as governance noise: **puts too expensive**, mild upward drift | Medium | TBD |
| F | Large acquisition signed (acquirer side) | 2 · Covered call | Deal uncertainty lifts implied vol, but big acquirers tend to drift flat or down afterwards. Selling the upside is well paid: **calls too expensive** | Medium | TBD |

### A · New leadership → protective put through the first earnings ("big bath")
- **Who's on the other side:** dealers and vol sellers pricing the next earnings from the stock's own
  history, which doesn't include this boss.
- **Why it persists:** few events per year per name, and the effect lands one to three months later,
  not on the filing day, so a filing-day event study misses it.
- **Testable prediction (a decay *shape*, not just a sign):** little or no edge at horizons 1–10;
  the edge appears at 42–63 sessions and at expiry, when the first earnings under the new executive
  falls inside the window. The 3–6 month bucket is the right one because it spans that earnings.
- **IV-crush side:** hurt by it on the hedge leg. We're betting the realized move beats the implied move.
- **Fails if:** the edge shows up at short horizons (that would just be the announcement), or it's
  absent at 42–63 sessions.
- **Literature:** Pourciau (1993), Murphy & Zimmerman (1993): new executives' write-downs.

### B · Debt offering → cash-secured put ("clean hands")
- **Who's on the other side:** generic put buyers and hedgers. Dealers price put skew from the
  calendar and market, not from the issuer's legal position.
- **Why it persists:** equity-options desks don't read debt 8-Ks, and the edge per trade is small.
- **Testable prediction:** realized ÷ implied below the placebo at 1–21 sessions; the cash-secured
  put beats ordinary days *after* earnings-cycle matching. Expected to fade by 63 sessions, once the
  next earnings is inside the window.
- **IV-crush side:** paid by it (short vol).
- **Fails if:** the edge disappears once placebo days are matched on the earnings cycle (it was only
  timing), or it comes entirely from banks, which issue all the time.
- **Literature:** Korajczyk, Lucas & McDonald (1991): issues cluster right after earnings, when
  information asymmetry is lowest.

### C · Settlement → cash-secured put ("tail removed")
- **Prediction:** the sold put's overlay beats ordinary days at 5–42 sessions. Probably a small sample.

### D · Accelerated buyback → covered call ("steady buyer")
- **Prediction:** realized ÷ implied below placebo across 5–63 sessions (ASRs run 2–6 months).
  Depends on the taxonomy having a tag specific enough for ASRs.

### E, F: kept as backups. E has a built-in fragility story: the SEC's 2022 rule (Reg S-K Item 402(x))
forces disclosure of grants made near material news, so any spring-loading edge should be weaker after 2023.

## How we'd rank them once counts are in
1. In-sample events ≥ ~60 (fewer than that and every interval spans zero; the CFO example had 70).
2. Expected OOS events ≥ ~15 (8 months of 2026).
3. Low share filed on an earnings day (otherwise it's an earnings study).
4. Novelty and a falsifiable *shape* across horizons, not only a sign.

## Prediction for the sealed window (to refine)
The starter's placeholder sealed window is 2023-06-01..2023-08-31, and the notebook notes that
contestant keys only carry options history from 2024. So the judges' window may sit **before** our
in-sample period, in a different regime: 2022's bear market with high implied vol, and 2023's
banking stress. A static 2026 top-100 list is also more wrong further back (e.g. PLTR and UBER weren't
top-100 then). Short-vol ideas (B, C, D, E) should look *better* gross in a high-IV regime but have
worse tails. Idea A is about one company's own earnings, so it should depend less on the regime.
