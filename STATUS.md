# Status

**v1.0 shipped — Cologne Swiss-stage Pick'Em.** Live, validated, and event-ready.

Last updated: 2026-06-02

## Working now

- Swiss engine, backtest-gated against Budapest 2025 (reproduces R1–R5 pairings exactly).
- Per-team P(3-0)/P(advance)/P(0-3) with two-tone confidence bands (sampling + source-disagreement).
- 2/6/2 Pick'Em optimizer with correct 3-1/3-2 advance scoring and the P(≥5/10) coin number.
- Live odds from OddsPapi (Pinnacle) + Kalshi, back-solved into market-anchored ratings.
- Conditional re-sim / live mode (lock results, re-sim from here).
- Cologne seeds confirmed against the official bracket; trust badge reads validated.
- **128 tests passing**, including regression guards for both probability fixes below.

## Recently fixed (both would have shown wrong numbers publicly)

- **Odds-fed probability inflation** — point probabilities were normalized by N instead of K·N
  under the epistemic loop, inflating everything ~12×. Now `n = len(sample)`.
- **Advance-pick scoring** — an advance pick was scored on `wins >= 3`, counting 3-0 finishes.
  Corrected to 3-1/3-2 only, which dropped the true coin odds from ~90% to ~59%.

See [docs/LESSONS.md](docs/LESSONS.md) for how these were caught.

## Known limitations

- It's a model, not an oracle: Round 1 is anchored to live market prices; later rounds are
  projected from back-solved ratings, so deeper-round numbers are softer.
- Practical N is ~100k–200k (the optimizer retains the full per-sim sample, so memory grows with
  K·N). Probabilities converge well before that.
- The playoff Pick'Em (7-pick round-weighted) is not built yet — Swiss only.

## Next

v3 (Full Major): Stages 2–3 + the playoff optimizer. See [ROADMAP.md](ROADMAP.md).
