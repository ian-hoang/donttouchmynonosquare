# Frozen rule (2026-10-03 ~03:35 ET, before any 2026 data is priced)

Approved by Ian. Nothing below changes after the out-of-sample run.

## Hypothesis
- **Mechanism.** After a large US company signs an acquisition or merger agreement, its stock tends
  to lag the market for about two weeks.
- **Why options misprice it.** Option prices don't anticipate that drift. So a call sold against
  shares already held loses value faster than usual, and the seller keeps the difference.
- **Strategy.** Strategy 2 (covered call) from the challenge library, for an investor who already
  holds the acquirer. Idea F in `BRAINSTORM.md` (written before any results) named the pairing and
  the direction.
- **What was learned in-sample** (disclosed in `research/FINDINGS.md`):
  - the merger-arbitrage explanation does not hold (cash deals drift too);
  - the effect peaks around 10 sessions.

## Rule
| item | definition |
|---|---|
| universe | the notebook's static `TOP_100` |
| event | an 8-K tagged `acquisition_agreement` or `merger_agreement`, one per company per filing date |
| one per deal | a filing counts only if it is more than 60 days after the same company's last *counted* deal filing. The sequence runs continuously from 2024-01-01, exactly as in-sample |
| chain read | t_pre = the session before the filing session (the first session on or after the filing date) |
| entry | close of the session **after** the filing session (no after-the-bell look-ahead) |
| contract | sell 1 call per 100 shares held. Expiry: the 3-6m bucket (90-180 days, nearest 120 with ≥ 3 paired strikes). Strike: first listed call strike ≥ 1.05 × the parity spot on t_pre |
| exit | buy back at the close of the 10th session after entry |
| marks | last trade, at most 3 sessions old. A trade with a stale exit mark, or no parity spot at exit, is dropped (the notebook's rule) |
| costs | half the bid-ask spread to sell and again to buy back, using the last quote before 16:00 ET on the entry session, divided by the stock price at entry |
| unit | P&L per $1 of stock held at entry |

## Out-of-sample test: run once
**Window.** Filing dates 2026-01-01 to 2026-08-31 (the notebook's window). The one-per-deal
sequence carries over from the in-sample filings.

**Primary measures, both at 10 sessions:**
1. mean P&L of the sold call, net of measured costs;
2. mean gap over quiet same-day peers. Peers are 6 top-100 companies per date with no 8-K within
   ±5 days, same contract rule, same entry and exit.

**Pass:** both are positive. With ~10-15 deals this checks the sign, not significance.

**Also reported:**
- t-stats and win rate;
- every fixed horizon that has resolved;
- the gap after removing each company's usual (in-sample) gap over peers;
- the full covered call (stock + call).
