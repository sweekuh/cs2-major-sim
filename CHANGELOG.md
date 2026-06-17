# Changelog

Release history for swiss-mc (IEM Cologne 2026 Swiss MC & Pick'Em optimizer). Versions track the
`ROADMAP.md` phase vocabulary and the annotated git tags. Dates are UTC.

The build is one strict dependency chain (engine → MC → optimizer → odds → multi-stage → playoffs),
each layer backtest- or test-gated before the next, so every release below is "shippable", not a
checkpoint.

## [v4.0] — 2026-06-17 — Playoffs + live-market wiring

The final layer: the 8-team single-elimination Champions bracket, plus the playoff odds wiring.

### Added
- **Playoff bracket simulator** (`engine/bracket.py`) — canonical Major seeding (1v8, 4v5, 2v7, 3v6
  from one structure table), Bo3 quarters/semis + Bo5 grand final via the new closed form
  `engine.probs.series_best_of` (the frozen Bo1/Bo3 `series` untouched), one Bernoulli per series, a
  chunked-RNG MC giving per-team P(reach SF)/P(reach final)/P(champion) with Wilson bands, and a
  `locked` live seam.
- **Playoff bracket seeding** (`engine/seeding.py:seed_playoffs`) — the 8 advancers seeded 1–8 by the
  literal final-standings chain (losses asc, Buchholz desc, prior seed asc), a separate derivation
  from the Swiss `seed_next_stage`, wired in-app as the PLAY-03 chain off a locked, complete Stage 3.
- **Playoff Pick'Em optimizer** (`engine/playoff_optimizer.py`) — the 7-pick round-weighted ballot
  (4 QF + 2 SF + 1 champion): enumerates all 128 bracket-consistent ballots and returns the
  E[points]-optimal recommendation (weights QF=1/SF=2/GF=3) plus the P(achievement-coin)-optimal
  alternative, sample-only.
- **Live-champion-market calibration** (`engine/playoff_fit.py`, `scripts/fit_champion.py`) — fit the
  8 bracket ratings so P(champion) reproduces the live tournament-winner book (Polymarket + Kalshi)
  through the real draw; re-run on market moves via the `_LIVE_FUTURES` dict.
- **Playoff per-match market odds** — the bracket grew the same `market_overrides` (PROB-02) seam as
  the Swiss `_play`: known QF/SF series lines are priced directly (best-of not re-applied) while the
  champion-fit ratings drive the unpriced later rounds; `overrides_from_named_lines` builds the seam
  from human-entered lines; the app's Playoffs stage feeds a `--stage playoffs` odds cache through the
  cross-stage guard (caption shows "N matchups market-priced"). Empty/absent → champion-fit-ratings-
  only, byte-identical.
- **App Playoffs stage** — bracket forecast, recommended 7-pick ballot + coin hero, live lock seam.

### Notes
- The real Cologne Stage-3 finish is committed (`data/playoffs.json`, seeds confirmed vs the official
  bracket). Forecast at release: Vitality ~45%, Spirit ~30%, FURIA ~9%, Falcons ~7%, then the field.
- 268 tests passing.

## [v3] — Full Major Swiss chain (Stages 2 & 3)

> Phase shipped between v1.0 and v4.0 (not separately tagged).

### Added
- **Stages 2 and 3 via the same validated engine** — per-stage fixtures + selector; Stage 3 runs
  all-Bo3 (`stage.all_bo3`, byte-identical when off); MC/optimizer cache is stage-keyed.
- **Inter-stage seeding chain** (`stage1 → stage2 → stage3`) — a fully-locked complete stage
  auto-derives the next stage's seeds (invited 1-8 by VRS, advancers 9-16 by final Buchholz) as an
  editable [INFERRED] overlay; one derivation path, validated on the real Cologne Stage-1 → 2 data.
- **Stage-scoped data pipeline** — `fetch_odds` / `fetch_results` take `--stage`, join the active
  stage's teams, and stamp `_meta.stage`; the app refuses a cross-stage cache on both seams.
- **Qualify-market calibration (QFIT)** (`scripts/fit_qualify.py`) — fit ratings offline so simulated
  P(qualify) matches the market's qualify prices (the rounds-2-5 view an R1 back-solve can't see).
- **Per-stage calibration scorecard** (`scripts/score_stage.py`) — log-loss/Brier/favorite-accuracy
  + S-sweep against real results.

### Fixed
- **Cross-stage odds mis-join (latent P0)** — the fetcher always joined Stage-1 teams and the cache
  carried no stage tag, so a cache fetched on one stage could silently price another's run (engine-id
  keys name different teams per stage). Closed on both write and read seams, with revert-proof tests.

## [v1.0] — 2026-05-30 — Cologne Swiss stage (calibrated)

Initial tagged release.

### Added
- **Swiss engine + backtest gate** — round-by-round pairing with Buchholz difficulty and the Valve
  15-row rematch-avoidance table; reproduces StarLadder Budapest 2025 Stage 1 pairings exactly.
- **Monte Carlo + Streamlit app** — per-team P(3-0)/P(advance)/P(0-3) with Wilson CI bands,
  zero-config first run, two-mode (pre-stage / live) layout.
- **Pick'Em optimizer** — the 2/6/2 ballot with correct 3-1/3-2 advance scoring, E[correct] and
  P(≥5/10) ballots, and a correlated-pick warning.
- **Conditional re-sim / live mode** — lock results round by round, watch each pick go
  live/dead/secured with a P(≥5)-from-here delta.
- **Live odds ensemble** — OddsPapi (Pinnacle, de-vigged) + Kalshi (keyless), log-opinion pooled,
  back-solved into market-anchored ratings; two-tone CI bands show source disagreement; fail-soft.

### Fixed
- **12× normalization inflation** and the **advance-pick scoring rule** (3-1/3-2 only, not `wins>=3`)
  — two real probability bugs caught during the live-odds work; see `docs/LESSONS.md`.

[v4.0]: https://github.com/sweekuh/cs2-major-sim/releases/tag/v4.0
[v1.0]: https://github.com/sweekuh/cs2-major-sim/releases/tag/v1.0
