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

## Shipped — v3 (Full Major Swiss chain)

- **Stages 2 and 3 via the same validated engine** — per-stage fixtures + selector, Stage 3
  all-Bo3 (`stage.all_bo3` threaded engine-deep, byte-identical off), and the inter-stage seeding
  chain (`stage1 → stage2 → stage3`): a fully-locked complete stage auto-derives the next stage's
  seeds (invited 1-8 by VRS from the next fixture, advancers 9-16 by final Buchholz) as an
  editable [INFERRED] overlay — one derivation path, validated on the real Cologne Stage-1 → 2
  data and reused unchanged for 2 → 3.
- **Stage-scoped data pipeline** — both fetchers (`fetch_odds` / `fetch_results`) take
  `--stage`, join the active stage's teams, and stamp `_meta.stage`; the app refuses a
  cross-stage cache (engine-id keys name different teams per stage — the LESSONS-Bug-1 class,
  closed on both cache seams).
- **The real Cologne Stage-3 field committed** — invited 8 verified by source in VRS order,
  the 8 real Stage-2 advancers, `seeds_confirmed=false` until reconciled vs the official bracket.

## Shipped — v4 (Playoffs)

The final layer: the 8-team single-elimination Champions bracket, simulated end-to-end on the REAL
Stage-3 finish (confirmed vs the official bracket 2026-06-16).

- **Playoff bracket simulator** — `engine/bracket.py`: the canonical Major seeding (1v8, 4v5, 2v7,
  3v6 from ONE structure table, no second matchup copy), Bo3 quarters/semis and a Bo5 grand final
  via the new closed form `engine.probs.series_best_of` (the frozen Bo1/Bo3 `series` untouched),
  one Bernoulli per series (never per-map sampling), a `locked` live seam, and a chunked-RNG MC
  giving per-team P(reach SF)/P(reach final)/P(champion) with Wilson bands.
- **Playoff bracket seeding from the Stage-3 finish** — `engine/seeding.py:seed_playoffs`: the 8
  advancers seeded 1–8 by the literal final-standings chain (losses asc, Buchholz desc, prior seed
  asc), a SEPARATE derivation from the Swiss `seed_next_stage` (a bracket, not a Swiss — deliberately
  NOT another `_NEXT_STAGE` entry). Wired in-app as the PLAY-03 chain off a locked, complete Stage 3.
- **Playoff Pick'Em optimizer** — `engine/playoff_optimizer.py`: the 7-pick round-weighted ballot
  (4 QF + 2 SF + 1 champion), a different scoring model from the Swiss 2/6/2. It enumerates all 128
  bracket-consistent ballots (no hill-climb needed) and returns the E[points]-greedy ballot AND the
  P(achievement-coin)-optimal recommendation (≥2 QF + ≥1 SF + champion correct), sample-only.
- **App integration** — a Playoffs stage with the bracket forecast, the recommended 7-pick ballot +
  coin hero, and a live lock seam (lock QF/SF/GF winners, re-sim from here).
- **Live-champion-market calibration (PLAY-04)** — `engine/playoff_fit.py` + `scripts/fit_champion.py`
  fit the 8 bracket ratings so P(champion) reproduces the live tournament-winner book through the real
  draw (the playoffs' QFIT analog); re-run on market moves via the `_LIVE_FUTURES` dict.
- **Playoff per-match market odds (v4.0)** — the bracket grew the same `market_overrides` PROB-02 seam
  as the Swiss `_play`: known QF/SF series lines are priced directly (best-of not re-applied), the
  champion-fit ratings drive the unpriced later rounds, and the app's Playoffs stage feeds a
  `--stage playoffs` odds cache through the cross-stage guard. Empty/absent → champion-fit-ratings-only,
  byte-identical. `overrides_from_named_lines` builds the seam from human-entered lines.

## Deferred

See [TODOS.md](TODOS.md): a cron-fed odds cache (so fetch runs outside the app), a streaming
sample path for arbitrarily high N, and optional Numba acceleration.
