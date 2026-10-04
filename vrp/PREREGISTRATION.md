# VRP short straddle — independent rebuild (pre-registered)

Written 2026-10-03, before any data for this test was pulled. The only earlier queries were 8 probe
quotes used to check data coverage. The file's mtime is the timestamp.

## Why this exists

A teammate's study (`vrp-research`, not on this machine) concluded **KILL**. Their claim: selling SPY/QQQ
straddles only when VRP_Z > 0 is not a real edge. Their headline numbers:

| Claim | Theirs |
|---|---|
| OOS Sharpe, blend SPY+QQQ, VRP_Z>0, hedged, main cost | 0.41 |
| OOS Sharpe, always short | 0.13 |
| OOS Sharpe, SPY buy & hold | 0.83 |
| Ex 2025-03-20..2025-05-15: always vs conditional | 0.66 vs 0.48 |
| Placebo p (random entries / shuffled Z) | ≈ 0.14 |

This is a rebuild from scratch, using our own Massive data and our own code. I have **not** seen their
code or their FROZEN_RULES.md. I have seen their headline numbers, so this is a replication, not a
discovery test. The rules below are my own standard choices. They are not tuned, and they are fixed now.

## Rules

**Universe and data.** SPY and QQQ, using Massive (NBBO option quotes, 1-minute and daily stock bars) and
FRED DTB3 for the risk-free rate. The window runs from the first session with option quotes (about April
2022) to 2026-10-02.

**Clock.** Every decision and mark happens 15 minutes before the session close: 15:45 ET, or 12:45 ET on
early-close days. Early-close days are detected from the data: 13:00–16:00 volume under 5% of
09:30–13:00 volume.
- S_t is the close of the 1-minute bar starting one minute before the mark (15:44). It is unadjusted,
  on the same basis as the strikes.
- An option quote is the last NBBO with sip_timestamp ≤ the mark, within 30 minutes of it.
- A quote is valid if bid > 0, ask ≥ bid, and ask − bid ≤ 25% of mid.

**Daily contract rule** (the same rule is used for the signal every day and for trades on Wednesdays):
- Expiry: the Friday closest to t + 30 calendar days. If that Friday is not a session, the session
  before it.
- Strike: the integer strike nearest S_t. If either leg has no valid quote, try the next-nearest
  integer, up to 3 strikes.

**IV.** Black-76 implied vol of the straddle mid (C + P).
- F = K + (C − P)·e^{rT}, discount e^{−rT}, r = DTB3/100 (last value on or before t).
- T = (expiry 16:00 ET − mark) / 365 days, floored at 1 hour.

**RV.** Standard deviation of 21 daily close-to-close log returns ending at t−1, annualized with √252.
Closes are split-adjusted daily bars.

**Signal.**
- VRP_t = IV_t − RV_t.
- Z_t = (VRP_t − mean) / std, where mean and std are taken over the trailing 252 sessions including t,
  with min_periods 126.

**Trades.** On every Wednesday session t (skip the week if Wednesday is a holiday), sell 1 straddle on
the daily-rule contract.
- *Conditional*: only if Z_t > 0.
- *Always*: every Wednesday with a valid contract.

**Holding.**
- **Primary (HX):** hold to the last session before expiry, exiting at that session's mark (≈29 days;
  about 4 cohorts overlap).
- **Secondary (H5):** exit 5 sessions after entry.
- Trades whose exit falls after 2026-10-02 are dropped.

**Hedge.** Every mark from entry to exit−1, hold h_t = Black-76 delta of the *long* straddle in shares.
- The delta comes from that day's IV of the held contract, solved from its mid.
- Hedge P&L for day t is h_{t−1}·(S_t − S_{t−1}).
- The hedge is set to 0 at exit.

**Marks and invalid quotes.** Daily option P&L is V_{t−1} − V_t, using mids. If a leg's quote is
invalid or missing, carry forward its last valid mid and flag the trade. If the entry quote is invalid,
there is no trade.

**Costs (main).** All amounts are in dollars per share (1 straddle = 100 shares):
- Options are filled at mid ∓ k·half-spread at entry and exit only, with k = 1 (sell at the bid, buy
  back at the ask). If the exit quote is invalid, use the last valid half-spread.
- Commission is $0.65 per contract, per leg, per side.
- The hedge pays $0.005/share × |Δh| at each rebalance, including the close.

**Units and Sharpe.**
- A trade's daily P&L is divided by S at entry.
- Each underlying's daily series is the sum over its open trades; flat days are 0. Blend = ½(SPY + QQQ).
- Sharpe = mean/std × √252 over every session in the window, with no risk-free subtraction (the
  straddle+hedge P&L is already an excess return).
- SPY buy & hold is reported as total return (dividends added), both raw and minus the T-bill rate.

**In-sample (IS) / out-of-sample (OOS).** Trades are assigned by entry date: IS if entered before
2024-07-01, OOS otherwise. A block's series runs from its first entry to its last exit, so IS spill into
July 2024 stays in IS.

## Tests (all reported, none used to pick anything)

1. OOS blend Sharpe: conditional vs always vs SPY B&H (HX primary, H5 secondary). IS shown too.
2. The same with 2025-03-20..2025-05-15 removed (sessions dropped from the series, and trades entered
   in it dropped).
3. Placebo: 5,000 draws, each picking a random subset of the always-short Wednesdays (per underlying,
   the same count as the conditional set). p = share of draws with OOS blend Sharpe ≥ the actual
   conditional value.
4. Circular block bootstrap (21-session blocks, 5,000 reps) gives 95% CIs for OOS Sharpe, conditional
   and always, and for their difference.
5. Sensitivities: k = 0.5 and k = 0; unhedged; dropping trades with a flagged (carried-forward) exit.

## Verdict rule (fixed now)

- **Breaks KILL** only if all three hold:
  - placebo p < 0.05,
  - OOS conditional Sharpe > SPY B&H Sharpe, and
  - conditional > always with 2025-03-20..2025-05-15 removed.
- Otherwise the rebuild **agrees with KILL**.

## Not covered

Single-name cross-section (their claim 3), other weekday cohorts, the 2020 crash (no quotes before
2022), and intraday hedging. American-exercise early-exercise effects are ignored (as in theirs).
This adds 1 pre-registered test to the team's 2026-10-03 tally.
