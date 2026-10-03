# PokerFace: CEO behavioral tells as an event-driven equity signal

Gator Quant Hacks 2026, Systematic Trading track. Work in progress during the event.

We extract facial (MediaPipe blendshapes and pose), vocal (eGeMAPS prosody) and verbal (Loughran-McDonald,
Larcker-Zakolyukina-style deception categories) features from hundreds of public interviews of mega-cap CEOs,
score each interview against that CEO's own trailing baseline, and test whether pre-specified, literature-
weighted "tell" scores predict post-interview abnormal returns in a market-hedged event strategy with realistic
costs and a sealed out-of-sample period.

- Rules and rubric we optimize for: `docs/GQH_RULES.md`
- Research rulebook (how we avoid fooling ourselves): `docs/RULEBOOK.md`
- Architecture: `docs/ARCHITECTURE.md`
- Hypothesis, committed before any backtest: `HYPOTHESIS.md`

Reproduction instructions (`python run_all.py`) land here before the deadline.
