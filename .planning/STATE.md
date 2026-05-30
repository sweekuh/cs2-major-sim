---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 05 (odds-ensemble) — ALL 3 PLANS EXECUTED (05-01/02/03 done)
status: executing
stopped_at: Completed 05-03-PLAN.md
last_updated: "2026-05-30T07:16:23.672Z"
last_activity: 2026-05-30
progress:
  total_phases: 6
  completed_phases: 5
  total_plans: 14
  completed_plans: 14
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-28)

**Core value:** Honestly-calibrated probabilities for the exact quantities Pick'Em scores on — P(3-0)/P(advance)/P(0-3) per team and P(≥5/10) per ballot — including conditional re-sim, without laundering guesses into false precision.
**Current focus:** Phase 5 — Odds Ensemble (ALL 3 PLANS EXECUTED on branch phase-5-odds). Next: `/gsd-verify-work 5`.

## Current Position

Phase: 5 (odds-ensemble) — ALL 3 PLANS EXECUTED (05-01 + 05-02 + 05-03 done)
Plan: 05-01 (pure odds core) DONE ∥ 05-02 (back-solve + epistemic fill) DONE ∥ 05-03 (fetch script + read-only cache seam + app wiring + fetch-now button) DONE
Status: Phase 5 plans complete — next is `/gsd-verify-work 5` (DEFERRED Task-3 live-slug /browse checkpoint pending markets posting)
Last activity: 2026-05-30

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 7
- Average duration: — min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 4 | - | - |
| 02 | 3 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01 P01 | 25 | 3 tasks | 12 files |
| Phase 01 P02 | 20 | 2 tasks | 3 files |
| Phase 01 P03 | 20 | 2 tasks | 3 files |
| Phase 01 P04 | 25 | DEFERRED-GATE | 3 files |
| Phase 02 P01 | 8 | 3 tasks | 10 files |
| Phase 02 P02 | 8 | 2 tasks | 4 files |
| Phase 02 P03 | 12 | 3 tasks | 5 files |
| Phase 04 P01 | 12 min | 3 tasks | 2 files |
| Phase 04 P02 | 22 min | 2 tasks | 4 files |
| Phase 05 P01 | 25 min | 3 tasks | 10 files |
| Phase 05 P02 | 75 min | 3 tasks | 6 files |
| Phase 05 P03 | 75 min | 2 tasks | 8 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Phase 1]: Backtest is a slice-1 HARD GATE, not post-hoc validation — only check proving greedy rematch resolution matches Valve's priority table.
- [Phase 1]: Buchholz = `Σ(opp.wins − opp.losses)`, single seeding code path (eng-review P0).
- [Phase 1]: Three cross-phase seams honored now — `locked` in swiss.py (Phase 4), generator-first MC + per-sim sample (Phases 2/3), epistemic outer loop stubbed (Phase 5).
- [Phase 5]: Odds placed last — fails soft, never gates; first run needs no API key.
- [Phase 1]: Pinned pytest 9.x (live pip index showed 9.0.3 current); supersedes RESEARCH assumption A1 (8.x [ASSUMED]). numpy confirmed 2.4.6.
- [Phase 1]: difficulty() canonical Buchholz lives in engine/probs.py; swiss.py imports it in wave 2 (no second copy).
- [Phase 1]: Team is @dataclass(eq=False) so opponent OBJECTS live in opps (difficulty() reads o.wins-o.losses); identity equality is correct per distinct stage entity.
- [Phase 1]: simulate_stage(teams, ratings, S, rng, locked); ratings is optional {id:rating} override (None->team.rating), the Phase-5/MC seam.
- [Phase 1, 2026-05-29 USER DECISION]: DEFER the full Budapest pairing-reproduction backtest (GATE-01). Budapest Stage 1 RESULTS reconciled + frozen, but the authoritative Valve 1-16 seed integers could not be sourced (HLTV Cloudflare-walled; Liquipedia/Wikipedia publish no seed integers) and the VRS world-rank order does NOT reproduce the actual R1/R2 pairings. Asserting a green backtest on guessed seeds = false pass/fail (T-04-01). Phase 1 gated on the green rulebook unit tests instead; Phase 2 unblocked WITH caveat (trust badge: "validated vs rulebook unit tests — full Budapest backtest pending seed data").
- [Phase 2 P01]: Pattern 2 option B — session_state mc_cache keyed on (ratings_key,S,N,locked_key) gives single in-session compute + a real progress bar; run_mc_cached also primed for cross-session memo.
- [Phase 2 P01]: locked_key is a REAL @st.cache_data key arg via freeze_locked (NOT the _locked escape) so Phase 4 locking moves >=1 P(advance) (RESIM-01 / Pitfall 13).
- [Phase 2 P01]: Fixed seed 20260528; Live toggle deferred to plan 02 (this slice = Pre-stage controls+Run+probs); streamlit pin 1.57.* resolves 1.57.0 though 1.58.0 now current.
- Phase 2 plan 02: STATUS palette locked colorblind-safe (advanced/live blue #3B82F6, eliminated amber #F59E0B); colour always paired with ASCII glyph + text label, never red/green (UI-06)
- Phase 2 plan 02: hero number renders a placeholder stand-in (top-team P(advance)) so the 28px monospace accent slot is real now; Phase 3/4 fill the optimal-ballot P(>=5)
- Phase 2 plan 03: BACKTEST_PASSED=False explicit constant gates the trust badge — it cannot drift to a green validated claim while GATE-01 is deferred; trust_badge_state validates only when BOTH BACKTEST_PASSED AND seeds_confirmed (Pitfall 6)
- [Phase 3 PLANNED 2026-05-29]: optimizer is a pure, RNG-free layer over `Result.sample` — Ballot A greedy is the EXACT E[correct] maximizer (no enumeration), Ballot B hill-climbs P(≥5) from the A seed (no ~10M brute force); P(≥5) vectorized via precomputed boolean outcome matrices so it never re-runs the MC (ROADMAP SC4).
- [Phase 3 PLANNED 2026-05-29]: correlated-0-3-in-R1 detection REUSES `engine.swiss.build_round1_pairs` — no seed re-derivation (sidesteps the GATE-01 seed blocker); warning is reported for Ballot A (correlation-blind), Ballot B avoids the trap for free via the joint sample.
- [Phase 3 PLANNED 2026-05-29]: pre-stage hero = recommended (Ballot B) P(≥5), filling the Phase-2 `_hero_slot` placeholder; Live-mode "P(≥5)-from-here" delta stays Phase 4. `optimize_cached` memoized on the SAME (ratings_key,S,N,locked_key) MC cache tuple (no recompute per rerun).
- [Phase 3 NOTE]: `/gsd-plan-phase` slash command is not installed in the web session (no .claude/commands/, GSD framework not cloned into the container); Phase 3 planning AND execution were done by hand following GSD conventions on branch `phase-3-optimizer`.
- [Phase 3 EXECUTED 2026-05-29]: `engine/optimizer.py` shipped — Ballot A greedy, Ballot B hill-climb, vectorized `p_ge5` over `Result.sample`, `correlated_03_in_r1`, `optimize()` facade. 12 new tests (7 optimizer + 3 render + 2 AppTest); full suite 63 passed, 1 skipped. No engine mutation.
- [Phase 3 EXECUTED 2026-05-29]: `optimize_cached(_result, ratings_key, S, N, locked_key)` memoizes on the MC cache tuple with `_result` underscore-EXCLUDED (correct here — Result is a pure function of the key, reused without re-running the MC; the deliberate inverse of the locked-in-key rule). `_hero_slot` kept for the LIVE Phase-4 placeholder; PRE-STAGE hero is the real recommended P(≥5).
- [Phase 3 V&V 2026-05-29]: verdict PASS (66 passed, 1 skipped; see 03-VERIFICATION.md). Fixed a latent warning id/seed lookup. Key finding: the bucket-wise greedy is NOT the global E[correct] maximizer (brute-force-confirmed +0.86 case) and Ballot B couldn't re-bucket to escape it. Resolved (user: "you choose" → option 2): broadened Ballot B's hill-climb with re-bucketing moves (`_neighbors`/`_rebucket`) and softened OPT-01 / `ballot_a` wording from "E[correct]-optimal" to "greedy per-bucket marginal baseline". Ballot A stays the literal greedy; Ballot B is the real P(≥5) recommendation.
- Phase 2 plan 03: INFERRED-seed banner + seed->team reconcile expander persists until the seeds_confirmed toggle (positive confirmation, no red) dismisses it; fail-soft odds-off banner uses os.environ only (no httpx/dotenv import — preserves zero-config first run)
- [Phase 4 P01 EXECUTED 2026-05-29]: `engine/live.py` shipped — pure, streamlit-free live-mode core over the FROZEN engine (no engine mutation; GATE-01 Budapest backtest still green). `locked_dict_from_results` (D1), `validate_lock` with 5 EXACT reason strings keyed on id (D3/RESIM-03), `classify_pick` secured/dead/live via exact P==1/P==0 against the conditional `build_outcome_matrices` (D4/RESIM-02), `pge5_delta` as two `p_ge5` calls on ONE fixed anchor ballot (D5/RESIM-02), `derive_bracket`/`legal_pairings_for_round` replaying `simulate_stage(..., pairings_out=[])` (D6/RESIM-04).
- [Phase 4 P01 EXECUTED 2026-05-29]: BLOCKER-2 rng-invariance guard — `legal_pairings_for_round` REQUIRES a fully-locked prefix (compares each prior round's locked set to the engine's `pairings_out[r]`) and raises `LivePrefixIncomplete` rather than return a single-RNG-draw artifact; `test_legal_pairings_requires_full_prefix` proves the returned set is invariant across two differently-seeded replays. 11 new tests (incl. 3 CRITICALs); full suite 79 passed.
- [Phase 4 P02 EXECUTED 2026-05-29]: LIVE-mode UI wired into `app.py` — the `locked={}` fill point in `_run_or_serve` became `locked_dict(st.session_state[KEY_LOCKED])` flowing through the EXISTING `freeze_locked`→`cache_key` path (no new key, no `_locked` escape), so a non-empty lock re-sims for free and ≥1 P(advance) moves (RESIM-01). New `ui/state.py` keys `KEY_LOCKED`/`KEY_LIVE_ANCHOR`/`KEY_PENDING_LOCK` + pure list-in/list-out helpers (`add_lock`/`remove_last_lock`/`locks_for_round`/`locked_dict`). `ui/render.py` `bracket_columns_html` = record-bucket flex columns, solid-locked/faint-simulated, escaped names, never a tree (RESIM-04).
- [Phase 5 P01 EXECUTED 2026-05-29]: `odds/` package shipped (TDD) — `base.py` PURE numpy (OddsQuote/BlendedProb, `devig_fixed_two_way` two-way overround for vig_type=fixed, `normalize_market_price` for vig_type=market NEVER two-way de-vigged [Pitfall 8], `pool()` originate/liquidity-weighted log-opinion geometric-mean-in-logit + delta-method cross-source var). `oddspapi.py` pre-pools the soft-book bundle to ONE Pinnacle-anchored opinion (originate Pinnacle=1.0/soft=0.3) so `pool()` never headcounts [Pitfall 7]. `polymarket.py`/`kalshi.py` keyless; empty market -> []. httpx LAZY-imported inside `fetch()` only — verified NOT in sys.modules after import+parse (D1/DX-01). Added `odds/_match.py` (Rule-3 structural) to isolate the lone `engine.teams` import and keep base.py engine-free. 10 new odds tests; full suite 99 passed; GATE-01 green; zero engine/app/ui mutation. ODDS-01/02/03/05 complete.
- [Phase 5 P02 EXECUTED 2026-05-30]: `engine/backsolve.py` shipped (TDD) — `invert_series` exact Bo3 inverse by bisection (identity Bo1, `0.648→0.6`, round-trips 1e-6) + `fit_ratings` hand-rolled numpy Gauss-Newton logistic LS, gauge-anchored, NO scipy (recovers known ratings up to the gauge, reprices targets). FILLED `engine/probs.py:epistemic_draws(blend, var, *, k=1, rng=None)` — K Beta draws via the EXISTING `beta_moment_fit` clamp; `var=0`/`rng=None`/`k=1` is the exact Phase-1 single-point no-op (byte-identical). Threaded keyword-only `market_overrides` `simulate_stage→_play`, oriented to LOWER-id (`p_a = p if a.id<b.id else 1-p`, since pairs arrive difficulty-ranked high/low NOT id-sorted) and routed via `series_prob` (Bo3 NOT re-applied, PROB-02). Added `market_blend` `{"lo-hi":(p,var)}` seam on `run_mc`/`run_mc_progressive`; var>0 drives K=DEFAULT_EPISTEMIC_DRAWS(12) outer draws (distinct child SeedSequence each), reported band = across-draw UNION of Wilson intervals (⊋ inner Wilson, N-invariant on disagreement), var=0 collapses to one draw. 8 new tests (5 backsolve + 3 epistemic incl. orientation guard + band-wider [CRITICAL]); full suite 107 passed; GATE-01 green; rating-only path byte-identical (additive defaults None). ODDS-04/PROB-03/04/05 complete.
- [Phase 5 P03 EXECUTED 2026-05-30]: read-only odds-cache seam wired (branch phase-5-odds). `scripts/fetch_odds.py` is the ONE entry (UI "fetch now" button AND v2-cron `python -m scripts.fetch_odds`) — `load_dotenv` (keys live HERE, never in the app), `discover_fixtures` reuses `build_round1_pairs` (NEVER re-derives seeds), per-provider try/except fail-soft, `pool()` per match, writes the FROZEN `data/odds_cache.json` `{_meta:{fetched_at ISO-8601 UTC,version,providers_present,round_hint}, blended:{"lo-hi":{p,var,n_sources,bo3}}}` (gitignored). `ui/odds_loader.load_odds_cache` is json+pathlib ONLY (no httpx/dotenv/provider/engine), version-gated, fail-soft None → rating-only + existing banner. app.py: `_odds_from_cache` back-solves ratings (`invert_series` series→map per Pitfall 9, then `fit_ratings` gauge-anchored on the top seed) + feeds `market_blend (p,var)` into the epistemic outer loop via the EXISTING `run_mc_progressive(...,market_blend=)`; scripts.fetch_odds LAZY-imported inside the button click ONLY (httpx/dotenv NEVER in the app import path — verified). STALE-BAND guard: `_cache_key_for(ratings,locked,fetched_at)` folds in `_meta.fetched_at` (clean 1-line; `optimize_cached` extended to match) so a var-only refetch invalidates the memoized Result — NO documented limitation. Rule-1 fix: clamp the progress fraction into [0,1] (the engine's running done-tally overshoots N*k under the epistemic loop; st.progress raises on >1; engine NOT modified). 6 new tests (loader unit + 5 AppTest incl. no-network-on-rerun via httpx-raise monkeypatch + fresh-fetch-invalidates); full suite 113 passed; GATE-01 green; zero engine/odds mutation. ODDS-05/06/07/08 complete. DEFERRED Task-3 human-verify (live Cologne slugs/tickers via gstack /browse) recorded as OUTSTANDING — markets not posted 2026-05-30 (expected), NOT a build blocker.
- [Phase 4 P02 EXECUTED 2026-05-29]: BLOCKER-1 anchor flow — `_compute_or_serve` extracted as the shared get-or-compute; the delta anchor (Ballot B) is captured ONCE from the EMPTY-locked `pre_key=(ratings_key,S,int(N),freeze_locked({}))` Result via `optimize_cached(pre_lock_result,*pre_key).recommended`, stored in `KEY_LIVE_ANCHOR`, never re-optimized; `pge5_delta`'s `before` reads the pre_key Result's OWN sample. The empty-locked pre_key is a DISTINCT key from the locked run, so CR-01 single-compute stays green. Round-R controls gated on R-1 fully entered (BLOCKER-2 in the UI). +5 live AppTests +1 pure bracket assertion; full suite 85 passed, GATE-01 green, no engine mutation. Phase 4 COMPLETE.

### Pending Todos

[From .planning/todos/pending/ — ideas captured during sessions]

- **Complete Budapest 2025 backtest gate (GATE-01) once authoritative seeds sourced** — `.planning/todos/pending/2026-05-29-budapest-backtest-gate-gate01.md`. Captures the seed blocker, the VRS-vs-actual-pairing divergence finding (possible engine within-group-pairing nuance, not just a data gap — worth root-causing before trusting Cologne), and the resume path (obtain seeded bracket → freeze seeds → unskip backtest → apply GATE-04 fork on divergence).

### Blockers/Concerns

[Issues that affect future work]

- **GATE-01/04 DEFERRED (2026-05-29 user decision):** The round-by-round backtest is BLOCKED on the authoritative Valve seed bracket (HLTV Cloudflare-walled). Phase 1 is gated on the green rulebook unit tests instead; Phase 2 proceeds WITH the caveat in the trust badge. The deferred backtest carries a real open question: the VRS order does not reproduce Budapest's R1/R2 pairings — this may be a seed-data gap OR an engine within-group-pairing nuance that must be root-caused before Cologne output is fully trusted. Tracked in .planning/todos/pending.
- **Phase 1×2 seam:** SeedSequence.spawn over pinned chunk count must survive Phase 2 chunked progress yielding.
- **Phase 2×4 seam:** `@st.cache_data` key must include `locked` from Phase 2 or Phase 4 becomes a re-architecture.
- **Phase 5×v2 seam (SATISFIED 2026-05-30):** the read-only `data/odds_cache.json` contract (ODDS-07) is written + frozen by `scripts/fetch_odds.py`; the app's only odds contact is `ui/odds_loader.load_odds_cache` reading it. The deferred v2 cron (OPS-01) is now a ONE-crontab-line drop-in with zero app change.
- **Phase 5 DEFERRED Task-3 (live-slug confirmation):** the OddsPapi/Polymarket/Kalshi live Cologne slugs/tickers/field-names (A2–A5) are a `checkpoint:human-verify` the user runs via gstack `/browse` ONCE markets post (not posted 2026-05-30 — expected). The build + tests are complete against recorded fixtures; `discover_fixtures` returns `{}` until then (a no-fixtures fetch writes a valid empty cache). NOT a build blocker.
- **Requirement count note:** REQUIREMENTS.md header says 48 v1 requirements; the enumerated REQ-IDs total 58. All 58 enumerated IDs are mapped — flag the header discrepancy to the user.

## Deferred Items

Items acknowledged and carried forward:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Operations | OPS-01 cron-fed odds cache (zero app change if ODDS-07 honored) | v2 | roadmap |
| Operations | OPS-02 Numba JIT of Swiss hot loop (only if pure-Python latency annoys) | v2 | roadmap |

## Session Continuity

Last session: 2026-05-30T07:16:23.665Z
Stopped at: Completed 05-03-PLAN.md
Resume file: None
Resume path: Phase 5 ALL 3 PLANS EXECUTED — next is `/gsd-verify-work 5` (then `/gsd-complete-milestone` if Phase 5 is the last phase, or `/gsd-plan-phase 6`). DEFERRED: confirm live Cologne slugs/tickers via gstack `/browse` once markets post (Task-3 human-verify, not a build blocker).

**Completed Phase:** 04 (conditional-re-sim-live-mode) — 2 plans — 2026-05-29
**Current Phase:** 05 (odds-ensemble) — ALL 3 PLANS EXECUTED (05-01/02/03 done) — 2026-05-30

Next: `/gsd-verify-work 5` to validate the odds ensemble (fail-soft no-key/no-cache → rating-only +
banner; a fetched cache feeds the back-solve + epistemic so probs move; no network on rerun; fresh
fetch invalidates the band). The live-slug confirmation (OddsPapi/Polymarket/Kalshi Cologne
fixtures) is a DEFERRED gstack `/browse` checkpoint gated on markets posting — the record-fixture
build is complete and fully functional rating-only/keyless meanwhile.
