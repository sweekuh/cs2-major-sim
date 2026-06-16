# Status

**v4 shipped — the project is complete: Swiss Stages 1–3 + the Playoffs.** Stage 3 is over;
its real results are committed and the single-elimination playoff bracket is simulated end-to-end.

Last updated: 2026-06-16

## Working now

- Swiss engine, backtest-gated against Budapest 2025 (reproduces R1–R5 pairings exactly).
- Per-team P(3-0)/P(advance)/P(0-3) with two-tone confidence bands (sampling + source-disagreement).
- 2/6/2 Pick'Em optimizer with correct 3-1/3-2 advance scoring and the P(≥5/10) coin number.
- **Stages 1–3 via one engine**: per-stage fixtures + selector; Stage 3 runs **all-Bo3**
  (`stage.all_bo3`, byte-identical engine output when off); MC/optimizer cache is stage-keyed.
- **Inter-stage seeding chain wired end-to-end** (`stage1 → stage2 → stage3`): a fully-locked,
  complete stage auto-derives the next stage's seeds (invited 1-8 by VRS from the next fixture,
  advancers 9-16 by final Buchholz) into an editable [INFERRED] overlay — one derivation path,
  validated on the real Cologne Stage-1 → Stage-2 result and reused unchanged for 2 → 3.
- **Stage-scoped odds + results pipeline**: both fetchers take `--stage`, join the active stage's
  teams, and stamp `_meta.stage`; the app refuses a cross-stage cache on BOTH seams (blended/result
  keys are engine-ids, and the same id is a different team each stage).
- **The real Cologne Stage-3 field committed** (verified by source 2026-06-09): invited 8 in VRS
  order (Vitality, NaVi, Falcons, MongolZ, PARIVISION, Aurora, FURIA, MOUZ) + the 8 real Stage-2
  advancers (Spirit, FUT 3-0; BetBoom, G2, 9z 3-1; Monte, Legacy, B8 3-2). `seeds_confirmed`
  stays false until eyeballed vs the official bracket (Liquipedia 403s automated fetch).
- Live odds from OddsPapi (Pinnacle) + Kalshi, back-solved into market-anchored ratings.
- **Qualify-market calibration (QFIT)**: `scripts/fit_qualify.py` fits ratings offline so the
  simulated P(qualify) matches the market's qualify prices — the rounds-2-5 view an R1 back-solve
  structurally can't see (R1 stays market-priced inside the fit, so the two are orthogonal). The
  app prefers a well-formed `fitted_ratings` cache block, fail-soft to the back-solve.
- **Per-stage calibration scorecard**: `scripts/score_stage.py` audits the prior against real
  results after each stage (log-loss/Brier/favorite-accuracy + S-sweep). On the real Stage-1 data:
  33 matches, 24/33 favorites, log-loss 0.5785 vs 0.6931 coinflip, S=40 the sweep argmin — the
  shipped spread is measured, not guessed.
- Conditional re-sim / live mode (lock results, re-sim from here).
- **Playoffs (v4) — the 8-team single-elimination bracket, simulated end-to-end.** The REAL
  Cologne Stage-3 finish is committed (`data/playoffs.json`, seeds confirmed vs the official
  bracket 2026-06-16): seeds 1–8 = Spirit, FURIA, Aurora, Falcons, Vitality, BetBoom, 9z, G2,
  with the standard Major seeding (1v8, 4v5, 2v7, 3v6), Bo3 quarters/semis, Bo5 grand final.
  `engine/bracket.py` runs the bracket MC (per-team P(reach SF)/P(reach final)/P(champion) with
  Wilson bands); `engine/seeding.py:seed_playoffs` derives the 8 bracket seeds from a locked
  Stage-3 finish (the PLAY-03 chain, separate from the Swiss `_NEXT_STAGE`); `engine/probs.py`
  grew the Bo5 closed form `series_best_of` (the frozen `series` untouched). The app's Playoffs
  stage renders the bracket forecast and a live lock seam (lock QF/SF/GF winners, re-sim from here).
- **Playoff Pick'Em optimizer (v4)** — the 7-pick round-weighted ballot (4 QF + 2 SF + 1
  champion), a DIFFERENT scoring model from the Swiss 2/6/2: `engine/playoff_optimizer.py`
  enumerates all 128 bracket-consistent ballots and returns the E[points]-optimal recommendation
  (round weights QF=1/SF=2/GF=3, editable) plus the P(coin)-optimal alternative, sample-only.
- **Champion-futures calibration (PLAY-04)** — `engine/playoff_fit.py` + `scripts/fit_champion.py`
  fit the 8 playoff ratings so the bracket sim's P(champion) reproduces the market's tournament-winner
  futures THROUGH the real bracket draw (the playoffs' QFIT analog). The shipped `data/playoffs.json`
  ratings are now champion-calibrated, so the title race is market-anchored, not carried-forward map
  priors — and ranked by PATH not just strength (FURIA's rating < G2's, but its easier draw gives it
  higher title odds). Resulting forecast: **Vitality ~53%, Spirit ~26%, Falcons ~10%**, robust in
  ordering across the spread sweep (S=30→50 moves Vitality 47–63%). Re-run with live futures to
  supersede the [ESTIMATED] longshots + form prior.
- **260 tests passing**, including the real-data Stage-1→Stage-2 seeding backtest, a deterministic
  Stage-2→Stage-3 chain gate, the playoff bracket-MC invariants / 7-pick optimizer / `seed_playoffs`
  derivation, the committed-bracket guard, and revert-proof guards on the new wiring (the
  `_NEXT_STAGE` entry, the Stage-3 banner, the cross-stage odds refusal, the `_meta.stage` stamp,
  and the Playoffs stage selector + bracket render + live-lock re-sim).

## Recently fixed

- **Cross-stage odds mis-join (latent P0, would have shown wrong numbers on Stage 2/3)** — the
  odds fetcher always joined Stage-1 teams (`load_teams()`) and the cache carried no stage tag, so
  a cache fetched on one stage would silently price another stage's run: blended keys are
  engine-id strings, and id 5 is a different team each stage. Same class as the LESSONS Bug-1
  inflation: invisible in rating-only mode, latent until live odds turn on. Fixed on both the
  write side (`load_stage(stage_id)` + `_meta.stage`) and the read side
  (`_odds_cache_for_active_stage` mirrors the results cache's stage filter), with tests that fail
  on revert.

## Known limitations

- It's a model, not an oracle: Round 1 is anchored to live market prices; later rounds are
  projected from back-solved ratings, so deeper-round numbers are softer.
- Stage-3 seeds 9-16's within-loss-bucket order is [INFERRED] until reconciled vs the official
  bracket; the authoritative path is the auto-derive from your locked Stage-2 finals.
- No real-data Stage-2→Stage-3 backtest yet: the full per-round Stage-2 match list wasn't
  automatable on 2026-06-09 (providers 403 automated fetch). Add it once the rounds are locked
  in-app — the deterministic chain gate covers the structure meanwhile.
- Practical N is ~100k–200k (the optimizer retains the full per-sim sample, so memory grows with
  K·N). Probabilities converge well before that.
- Playoff per-match market odds aren't wired (no live playoff-series provider was reachable from
  the build host); the bracket runs on the carried-forward Stage-3 ratings until odds post. The
  playoff Pick'Em point weights / achievement tiers are [INFERRED] editable defaults (QF=1, SF=2,
  GF=3; tiers 2/1/1) — the relative ordering matches the documented in-game achievements.

## Next

The project is complete (Swiss Stages 1–3 + Playoffs). Remaining items are optional polish, all
captured in [TODOS.md](TODOS.md): a live playoff-odds feed, a cron-fed odds cache, a streaming
high-N sample path, and optional Numba acceleration.
