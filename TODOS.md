# TODOS — swiss-mc

Deferred work captured during `/plan-eng-review` (2026-05-28). Each item has enough
context to pick up cold in 3 months.

---

## 1. Decouple odds fetch from the Streamlit app (cron-fed cache)

- **Status (2026-06-09):** Seam DONE and now STAGE-AWARE — the "Fetch odds now" button passes the
  active stage, and both `python -m scripts.fetch_odds --stage stageN` and
  `python -m scripts.fetch_results --stage stageN` join that stage's teams + stamp `_meta.stage`
  (the app refuses a cross-stage cache). The cron line is now per-stage; what's left is the v2
  *cron trigger* itself so it auto-fetches per round.
- **What:** Move the per-round odds fetch out of the Streamlit process. A small
  standalone job (cron on the Ubuntu host) calls the providers and writes a
  `data/odds_cache.json` (or sqlite); the app only ever *reads* that cache.
- **Why:** PRD F1f wants "auto-fetch once per round after pairings post." Streamlit
  is not a scheduler, and Community Cloud sleeps between requests, so a fetch loop
  cannot live inside the app. Inline keyed cross-origin calls also fight the UI rerun
  model.
- **Pros:** Auto-fetch works without a rewrite; app stays fast (no blocking API calls
  on rerun); keys live only in the fetch job's env, not the UI session.
- **Cons:** One more moving part (the cron job) + a cache file contract to keep stable.
- **Context:** Respect the seam from v1 even though auto-fetch is v2. The v1 manual
  "fetch now" button should write to the *same* cache the app reads, so the only thing
  v2 adds is the cron trigger. Do NOT let the app call `OddsProvider.get_quotes()`
  directly on rerun.
- **Depends on:** Odds layer (slice 5). Blocked by nothing for the seam itself.

## 2. Numba acceleration for the Swiss engine (deferred perf lever)

- **What:** JIT-compile the hot Swiss-stage loop (pairing + match sampling) with Numba
  to bring a full 100k-sim run under ~2s.
- **Why:** v0/v1 accept ~10-30s pure-Python runs with a spinner (correct call). But
  during the live event you may re-run constantly as results lock, and the latency
  could get annoying.
- **Pros:** ~10-50x on the branchy core; keeps the interactive loop snappy on event day.
- **Cons:** Numba doesn't love Python objects/dicts — the engine state (`opps: set`,
  team objects) would need restructuring into numeric arrays. Real refactor, spends
  an innovation token.
- **Context:** **Trigger condition:** only do this if full-run latency actually annoys
  you during live use. Pure Python is fine for pre-stage planning. If triggered, the
  refactor is to array-of-structs (team_id, wins, losses, seed, opp-bitmask) so Numba
  can `@njit` the loop. The closed-form Bo3 (no per-map sampling) helps here.
- **Depends on:** Engine complete + backtest passing (don't optimize an unverified sim).

## 3. Playoff Pick'Em optimizer (7-pick round-weighted ballot) — DONE (2026-06-16, v4)

- **Status:** SHIPPED. `engine/playoff_optimizer.py` enumerates all 128 bracket-consistent ballots
  (4 QF + 2 SF + 1 champion) and returns both the E[points]-greedy ballot and the
  P(achievement-coin)-optimal recommendation (≥2 QF + ≥1 SF + champion correct), scored sample-only
  against `engine/bracket.py`'s retained per-sim bracket sample. Round weights (QF=1/SF=2/GF=3) and
  achievement tiers (2/1/1) are [INFERRED] editable defaults. NOT the Swiss optimizer (kept
  separate per REQUIREMENTS V3-03). See the Completed section below. Original context retained:
- **What:** A separate optimizer for the playoff Pick'Em, which is NOT the Swiss 2/6/2 scheme.
  It's a 7-prediction round-weighted ballot (2 Quarterfinal + 1 Semifinal + 1 Grand Final
  correct picks, per the in-game achievements).
- **Why:** The current optimizer only handles the Swiss 2/6/2 coin. Playoffs are a different
  scoring model and must NOT reuse the Swiss optimizer (REQUIREMENTS.md V3-03, Phase 6).
- **Context:** Confirmed from the live in-game Pick'Em UI. Model it as its own round-weighted
  ballot type. Not needed for Stage 1 (Swiss); becomes relevant once playoffs are set.
- **Depends on:** Swiss optimizer (done). Independent otherwise.

## 4. Streaming / aggregate sample path for high N (memory)

- **What:** The optimizer scores `Result.sample` (the full per-sim record list), so memory grows
  with K·N. A 1M odds-fed run (K=12 → 12M records) needs ~11 GB and OOMs.
- **Why:** Probabilities converge by ~100k so this never bites in practice, but it's a footgun:
  someone cranks N to 1M and the machine swaps/dies.
- **Pros:** Removes the only hard memory ceiling; lets N be arbitrary.
- **Cons:** The optimizer needs per-sim outcomes for the P(≥5) joint, so a streaming design has to
  keep the bucket-matrices (per-team boolean arrays) without retaining the raw dict records, or
  compute ballot scores online. Real refactor.
- **Context:** Cap N in the UI (already 100k default) and document the limit (done in README) as
  the cheap mitigation; do the streaming refactor only if a high-N use case appears.

## 5. Real-data Stage-2 → Stage-3 seeding backtest (once the rounds are locked)

- **What:** The Stage-2→3 analog of `tests/test_stage2_seeding.py`: freeze the authoritative
  round-by-round Stage-2 results as a fixture, replay through
  `final_standings_from_locked -> seed_next_stage`, assert the derived Stage-3 seed order against
  the official bracket.
- **Why:** The deterministic chain gate (`tests/test_stage3_seeding.py`) proves the structure;
  only real data proves the within-bucket Buchholz order (the part that bit us hardest in seeding).
- **Context (2026-06-09):** the full per-round Stage-2 match list wasn't automatable (Liquipedia /
  HLTV / bo3.gg all 403 automated fetch; news snippets give finals records only). Lock the rounds
  in-app (or hand-build the fixture from Liquipedia) and tighten
  `test_stage3_seeding.EXPECTED_ADVANCERS` from a set to an exact seed order at the same time —
  that is a data reconciliation, not a code change.
- **Depends on:** the locked Stage-2 results. Blocked only on data entry.

## 6. Feed the qualify-market calibration from a live source

- **What:** `scripts/fit_qualify.py` calibrates ratings to the market's QUALIFY probabilities (the
  rounds-2-5 view an R1 back-solve can't see), but the `"qualify"` block in `data/odds_cache.json`
  is operator-supplied today. Wire a fetcher for it: Polymarket runs per-event qualify markets
  (e.g. "Qualify to Stage 3"), and Kalshi may list equivalents.
- **Why:** the fit is only as good as its targets; hand-typed qualify probs are the weakest link.
- **Context:** Polymarket was dropped as a per-match provider (novelty futures, ODDS notes) but its
  EVENT markets (winner / qualify) are real and liquid — a separate, narrower parser than the
  match-quotes path. Respect the additive-within-v1 schema (`qualify` key) the loader documents.
- **Depends on:** nothing structural; blocked on provider access from the runtime host.

---

## Completed

- **Playoffs (v4) — DONE (2026-06-16).** The 8-team single-elimination Champions bracket, simulated
  end-to-end on the REAL Stage-3 finish (committed to `data/playoffs.json`, seeds confirmed vs the
  official bracket): `engine/bracket.py` (single-elim sim + chunked-RNG MC, Bo3 quarters/semis + Bo5
  grand final via the new `engine.probs.series_best_of`), `engine/seeding.py:seed_playoffs` (bracket
  seeds from a locked Stage-3 finish — the PLAY-03 chain, separate from the Swiss `_NEXT_STAGE`),
  `engine/playoff_optimizer.py` (the 7-pick round-weighted optimizer — item 3 above), and the
  app's Playoffs stage (bracket forecast + recommended ballot + coin hero + live lock seam). 29
  revert-proof tests (bracket invariants, the 128-ballot optimizer, `seed_playoffs` ordering, the
  committed-bracket guard, and the AppTest wiring guards).

- **Round-by-round backtest GATE — DONE.** Engine reproduces StarLadder Budapest 2025 Stage 1
  pairings exactly (`tests/test_backtest_budapest_2025.py`, green). The only check that proves the
  greedy rematch-resolution matches Valve's literal 15-row priority table.
- **Live odds ensemble — DONE.** OddsPapi (Pinnacle, de-vigged) + Kalshi (KXCS2GAME, keyless)
  fetch implemented and verified against live Cologne markets; log-opinion pooled; back-solved to
  ratings. Polymarket dropped (novelty futures only).
- **Cologne seeds confirmed — DONE.** Seed order verified vs Liquipedia + live Kalshi bracket +
  the R1 pairing rule; trust badge now reads validated.
- **Two P0 probability fixes — DONE.** Odds-fed normalization (`n=len(sample)`, was ~12× inflated)
  and advance-pick scoring (3-1/3-2, was `wins>=3`, dropped P(≥5) ~90%→~59%). Both with regression
  tests that fail on revert. See `docs/LESSONS.md`.
- **Qualify-market calibration (QFIT) — DONE (2026-06-09).** `engine/qualifyfit.py` fits ratings
  so simulated P(qualify) matches market qualify probs (R1 stays market-priced inside the fit, so
  the two calibrations are orthogonal; deterministic common-random-numbers stepper with gauge
  anchor + fail-loud target validation). `scripts/fit_qualify.py` runs it offline and writes the
  additive `fitted_ratings` block; `app._odds_from_cache` prefers a well-formed block over the R1
  back-solve, fail-soft on any defect. 20 revert-proof tests.
- **Per-stage calibration scorecard — DONE (2026-06-09).** `scripts/score_stage.py` scores the
  stage prior against real results (log-loss/Brier/favorite-accuracy + S-sweep, Bo3 inferred by
  replay, cross-stage guard). Golden-pinned to the real Stage-1 data: n=33, 24/33 favorites,
  log-loss 0.5785 @ S=40 (the sweep argmin) — run it after every stage.
- **Stage-3 pipeline — DONE (2026-06-09).** The `stage2 -> stage3` derive wired through the SAME
  validated chain (one `_NEXT_STAGE` entry — no second seeding path), the per-stage [INFERRED]
  banner, the real verified Stage-3 field committed, and the cross-stage odds cache mis-join
  closed on both seams (`load_stage(stage_id)` + `_meta.stage` + read-side refusal). All with
  revert-proof regression tests, per the LESSONS rule.
