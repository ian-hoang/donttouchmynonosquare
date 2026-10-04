# Round 3: profits the filing itself causes (written 2026-10-03 ~03:05 ET, before running)

Ian's question: can we find something where the **filing** is the reason for the profit?

Same data as V005/V007:
- 2024-25 company-days and quiet same-day peers
- 3-6m options, 5% OTM
- entry at the close of the session after the filing date
- costs measured from quotes

"Because of the filing" means the trade beats both:
- quiet same-day peers, and
- the same company's usual result against peers on quiet days.

## S · Sell into a filing-driven option-price spike
- **Measure.** On t_pre and on the entry session, take the 3-6m ATM straddle's time value.
  - By put-call parity that time value is 2 × min(call, put) at the same strike, ÷ the stock price.
  - Spike = log change from t_pre to entry, minus the same-day peers' average change.
- **Groups (non-earnings company-days).**
  - Top quintile of spike = "options got pricier because of the filing".
  - Everyone else is the comparison.
- **Trade.** Sell premium into the spike: cash-secured put, or covered call.
- **Story.** After unsettling news, traders rush for protection and dealers widen. Implied volatility
  overshoots, then relaxes as the news is digested. Literature on option-market overreaction:
  Stein (1989).
- **Prediction (5-21 sessions).** For the spike group:
  - cash-secured put and covered call P&L beat peers and the company's usual by more than for
    others;
  - the straddle's time value falls back relative to peers.
- **Fails if** the spike group does no better or worse, i.e. the higher implied volatility was
  justified.

## F-overlay · Deal signed, for someone who already holds the acquirer
- Round 1's rule (BRAINSTORM.md) already said every strategy is also reported as its option overlay.
- **Idea F (written before results)** paired deal signings with the covered call, on the thesis that
  big acquirers drift flat or down. For a holder, the decision at the filing is whether to add options.
- **Trades:** the money made by the added options only.
  - Covered-call overlay: sell the 5% OTM call.
  - Collar overlay: buy the 5% OTM put, sell the 5% OTM call.
- **Measured:** absolute net of measured costs, against peers, and against the company's usual.
  - Repeated filings per company are collapsed to the first one per 60 days, so each deal counts once.
- **Prediction:** both overlays make money net of costs at 5-21 sessions and beat both controls.
- **Fails if** either control removes it, or it comes from one company.
