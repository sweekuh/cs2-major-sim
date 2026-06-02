# Roadmap

The build is one strict dependency chain, not a feature menu. A faithful Swiss engine is worthless
unless its pairing logic is provably correct, so a round-by-round backtest against a real past
Major was a hard blocking gate before any UI, optimizer, or odds work began. Each layer rides on
the one below.

## Shipped — v1.0 (Cologne Swiss stage)

- **Swiss engine + backtest gate** — round-by-round pairing with Buchholz difficulty and the Valve
  rematch-avoidance table; reproduces StarLadder Budapest 2025 Stage 1 pairings exactly (the gate).
- **Monte-Carlo + Streamlit app** — per-team P(3-0)/P(advance)/P(0-3) with Wilson CI bands,
  zero-config first run, two-mode (pre-stage / live) layout.
- **Pick'Em optimizer** — the 2/6/2 ballot with correct 3-1/3-2 advance scoring, E[correct] and
  P(≥5/10) ballots, and a correlated-pick warning.
- **Conditional re-sim / live mode** — lock results round by round, watch each pick go
  live/dead/secured with a P(≥5)-from-here delta, record-bucket bracket.
- **Live odds ensemble** — OddsPapi (Pinnacle, de-vigged) + Kalshi (keyless), log-opinion pooled,
  back-solved into market-anchored ratings; two-tone CI bands show source disagreement. Fails soft
  to rating-only, never gates the first run.

## Next — v3 (Full Major)

- Stages 2 and 3 Swiss via the same validated engine.
- A **playoff Pick'Em optimizer** — a 7-pick round-weighted ballot (2 Quarterfinal + 1 Semifinal +
  1 Grand Final), which is a different scoring model from the Swiss 2/6/2 and is not yet built.

## Deferred

See [TODOS.md](TODOS.md): a cron-fed odds cache (so fetch runs outside the app), a streaming
sample path for arbitrarily high N, and optional Numba acceleration.
