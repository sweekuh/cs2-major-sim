---
phase: 01-engine-backtest-gate
verified: 2026-05-29T00:00:00Z
status: passed
score: 22/22 must-haves verified
overrides_applied: 0
overrides: []
re_verification: null
gaps: []
deferred:
  - truth: "Round-by-round backtest feeds a completed past Major stage (Budapest 2025) seeds + forced results and asserts the engine reproduces the actual round-by-round pairings exactly (GATE-01)"
    addressed_in: "tracked TODO (.planning/todos/pending/2026-05-29-budapest-backtest-gate-gate01.md)"
    evidence: "User decision 2026-05-29: authoritative Valve 1-16 seed integers unsourceable; VRS world-rank order does not reproduce actual R1/R2 pairings; asserting a green backtest on guessed seeds is a false pass/fail (T-04-01). Engine is gated on rulebook unit tests instead. Deferral recorded in STATE.md, REQUIREMENTS.md (GATE-01 left unchecked with deferral note), and a tracked TODO."
  - truth: "Greedy fold replaced by literal verbatim priority-table lookup if any backtest pairing diverges (GATE-04)"
    addressed_in: "tracked TODO (.planning/todos/pending/2026-05-29-budapest-backtest-gate-gate01.md)"
    evidence: "PRIORITY_TABLE is encoded in engine/swiss.py and unit-tested (GATE-03), but the fork was never exercised against real Budapest pairings because the backtest is deferred. Deferral note in REQUIREMENTS.md and 01-04-SUMMARY.md."
  - truth: "No sim output trusted and no UI built until GATE-01 passes (GATE-05, as originally stated)"
    addressed_in: "reinterpreted by user decision 2026-05-29"
    evidence: "Phase 2 is unblocked with the caveat that the trust badge must read 'engine validated vs Valve rulebook unit tests — full Budapest backtest pending seed data,' NOT 'validated vs Budapest backtest.' Recorded in REQUIREMENTS.md (GATE-05 reinterpreted note) and 01-04-SUMMARY.md Trust-Badge section."
human_verification: []
---

# Phase 1: Engine Backtest Gate — Verification Report

**Phase Goal:** A pytest-runnable, dependency-free correctness core that simulates the Valve Stage-1 Swiss format and reproduces a real past Major stage's pairings exactly — the hard gate that must pass before any output is trusted or any UI exists.

**Verified:** 2026-05-29
**Status:** passed (with documented, user-accepted deferrals of GATE-01/04/05)
**Re-verification:** No — initial verification

## Accepted Scope Decision

GATE-01 (Budapest round-by-round pairing reproduction), GATE-04 (priority-table fork exercised against real data), and GATE-05 (trust gated on named backtest) are DEFERRED by explicit user decision made at the Wave 4 human-verify checkpoint on 2026-05-29. The authoritative Valve 1-16 seed assignment could not be sourced; the HLTV VRS world-rank order demonstrably does not reproduce the actual R1/R2 pairings; asserting a green backtest on guessed seeds would be a false pass/fail (T-04-01). The engine is gated on the full suite of green Valve-rulebook unit tests instead. These deferrals are tracked, not silently ignored (see Deferred Items section and `.planning/todos/pending/2026-05-29-budapest-backtest-gate-gate01.md`). They do NOT represent undiscovered gaps.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | uv run pytest collects all test modules and runs green | VERIFIED | 21 passed, 1 skipped (deferred GATE-01); 0 failures; exit 0 |
| 2 | engine/probs.py p_map is logistic with S default 40; series() applies p²(3−2p) for Bo3 and identity for Bo1 | VERIFIED | `p_map` at line 29 of probs.py: `1.0 / (1.0 + 10 ** (-(ra - rb) / S))`; `series` at line 39: `p * p * (3 - 2 * p) if bo3 else p`; test_p_map and test_bo3 both PASS |
| 3 | An odds-override series prob passes through untouched; Bo3 NOT re-applied | VERIFIED | `series_prob()` in probs.py lines 42-61: `if market_series_prob is not None: return market_series_prob`; test_odds_override_passthrough PASSES |
| 4 | difficulty() on Valve's worked example (opponents 2-0 and 1-1) returns 2 | VERIFIED | `difficulty()` in probs.py line 71: `sum(o.wins - o.losses for o in t.opps)`; test_difficulty_formula PASSES; also guarded by test_difficulty_unit in test_swiss.py |
| 5 | engine/teams.py exposes the 16-team Cologne seed->team map and derives R1 pairings as [(i,i+8) for i in range(1,9)] with no second hardcoded copy | VERIFIED | `build_round1_pairs` at lines 131-138 of teams.py; `[(by_seed[i], by_seed[i + 8]) for i in range(1, 9)]`; no second hardcoded table anywhere in engine/ |
| 6 | Beta moment-fit helper clamps variance < p(1-p); epistemic outer-loop helper yields exactly one point draw in Phase 1; reported band collapses to inner Wilson band | VERIFIED | `beta_moment_fit` clamps at probs.py lines 102-110; `epistemic_draws` yields exactly one draw (line 89: `yield list(blend)`); test_epistemic_stub_and_beta_clamp PASSES; test_epistemic_band_collapses_to_wilson PASSES (matches Wilson to 1e-12) |
| 7 | engine/ imports neither streamlit, httpx, nor requests | VERIFIED | grep of all engine/*.py returns no forbidden imports; engine/__init__.py enforces the invariant in a comment; test_swiss_no_forbidden_imports and test_no_forbidden_imports (MC) both PASS |
| 8 | simulate_stage runs one full Valve Stage-1 Swiss: R1 from derived seed table, R2+ via single code path, terminating at 3 wins or 3 losses | VERIFIED | swiss.py: R1 calls `build_round1_pairs(teams)` (not a re-fold); rounds 2+ loop on active teams with no `if round==2`; test_bo3_placement_and_termination PASSES (8 seeds, all 16 terminate at 3W/3L) |
| 9 | Within-group ranking sorts by (−difficulty, seed); difficulty sort is actually USED as the fold key, not dead code | VERIFIED | `rank_group` at swiss.py line 82: `sorted(group, key=lambda t: (-difficulty(t), t.seed))`; test_fold_uses_difficulty_rank PASSES using a disjoint-construction fixture that fails if the difficulty term is removed |
| 10 | Pairing uses rematch-avoiding fold backed by verbatim 15-row Valve priority table for 6-team groups | VERIFIED | `PRIORITY_TABLE` in swiss.py lines 53-69: 15 rows; `_pair_via_priority_table` selects top-most rematch-free row; test_forced_rematch_pairing PASSES (positions 2,5 rematch -> engine selects Priority Row 2: 1v6,2v4,3v5 exactly) |
| 11 | When no rematch-free perfect matching exists, engine pairs least-disruptive rematch and logs warning | VERIFIED | `_least_disruptive_rematch` in swiss.py + `pair_within_group` fallback; test_no_valid_matching_fallback PASSES (2-team group of prior opponents; returns forced pair + WARNING logged, no crash) |
| 12 | A match is Bo3 iff a team is at 2 wins or 2 losses, else Bo1; no pair plays twice | VERIFIED | `_is_bo3` in swiss.py lines 188-199 checks `wins == ADVANCE_AT_WINS - 1` or `losses == ELIMINATE_AT_LOSSES - 1`; test_locked_results_honored and test_bo3_placement_and_termination assert no rematches every run |
| 13 | simulate_stage accepts locked dict and uses locked winner deterministically, recording in opps | VERIFIED | `_play` in swiss.py lines 210-229: `if key in locked: winner_id = locked[key]`; `_record_match` records opps in both directions including locked; test_locked_results_honored PASSES across different rng seeds |
| 14 | run_mc_progressive is generator-first: yields per-chunk Partials; separate cached-wrapper drains it | VERIFIED | `run_mc_progressive` is a generator yielding `Partial(done,total,running_p_adv)` per chunk and `return`ing `Result` via StopIteration.value; `run_mc` drains it; test_progress_partials_yielded PASSES (20 Partials for n_chunks=20) |
| 15 | RNG is SeedSequence(seed).spawn(n_chunks) over a PINNED chunk count; reproducible across runs and chunked execution | VERIFIED | montecarlo.py lines 168-170: `ss = np.random.SeedSequence(seed); child_seeds = ss.spawn(n_chunks)`; pinned default n_chunks=20; test_reproducibility PASSES; test_reproducibility_survives_n_chunks_default PASSES |
| 16 | MC tallies per-team 3-0 / advance / 0-3 with Wilson confidence bands (hand-coded, no scipy) | VERIFIED | `wilson(k, n, z)` at montecarlo.py lines 47-60: closed-form, no scipy; counts tallied in run_mc_progressive loop; test_wilson_closed_form PASSES to 1e-12 |
| 17 | MC retains full per-sim record sample (not just marginals) | VERIFIED | `Result.sample` accumulates one `{id:(wins,losses)}` map per sim; test_record_sample_retained PASSES (len==N, 2x3-0/2x0-3/8advance per sim) |
| 18 | Probability invariants hold every run (ΣP(3-0)≈2, ΣP(0-3)≈2, ΣP(advance)≈8, within ±0.05 at N≥50k) | VERIFIED | test_invariants PASSES at N=50k; actual sums structurally exact (2.000/8.000/2.000) because every sim produces exactly 2x3-0/2x0-3/8advance; smoke run confirms same |
| 19 | uv run python -m engine prints per-team P(3-0)/P(advance)/P(0-3) with Wilson bands and invariants hold | VERIFIED | Live run at N=5000: 16-row table printed cleanly (ASCII-safe on Windows cp1252); invariant sums print 2.000/8.000/2.000; GamerLegion tops P(3-0)=0.754 and P(advance)=0.999; THUNDER dOWNUNDER and FlyQuest top P(0-3) |
| 20 | data/stage1.json ships with 16 editable [INFERRED] Cologne seeds + default ratings | VERIFIED | File exists at data/stage1.json; 16 teams, seed 1-16, GamerLegion=92 through FlyQuest=40; `seeds_confirmed: false`; validates on load |
| 21 | Budapest 2025 fixture is frozen with internally-legal results (even if seeds unresolved) | VERIFIED | tests/fixtures/budapest_2025_stage1.json exists; seeding=null with UNRESOLVED note; test_budapest_fixture_shape_is_internally_legal PASSES (8/8 partition, stable advancer set, no rematch, legal terminal records, M80 present) |
| 22 | ENG-09: RNG seeding via SeedSequence.spawn survives chunked execution | VERIFIED | Pinned n_chunks=20 in DEFAULT_N_CHUNKS; test_reproducibility_survives_n_chunks_default verifies default == explicit n_chunks=20 |

**Score:** 22/22 truths verified (GATE-01/04/05 counted in Deferred section, not as failures)

---

### Deferred Items

Items not yet met due to an accepted external blocker — explicitly tracked, not silently omitted.

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | Budapest 2025 round-by-round pairing reproduction exactly (GATE-01) | .planning/todos/pending/2026-05-29-budapest-backtest-gate-gate01.md | User decision 2026-05-29: authoritative Valve 1-16 seed integers unsourceable; VRS world-rank order diverges from actual R1/R2 pairings (divergence documented in budapest-2025-reconciliation-DRAFT.md); asserting green on guessed seeds = false pass T-04-01 |
| 2 | Verbatim priority-table fork exercised against real pairings (GATE-04) | same TODO | PRIORITY_TABLE is encoded and unit-tested; the fork trigger (real pairing divergence) cannot be evaluated without authoritative seeds |
| 3 | Trust gate on named backtest completion (GATE-05 as originally stated) | REQUIREMENTS.md GATE-05 reinterpretation note + 01-04-SUMMARY.md trust-badge wording | Phase 2 trust badge must read "validated vs Valve rulebook unit tests — full Budapest backtest pending seed data" per the user decision record |

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pyproject.toml` | uv project, requires-python >=3.12, numpy + pytest pins, testpaths | VERIFIED | requires-python=">=3.12"; numpy>=2.4,<2.5; pytest>=9,<10; testpaths=["tests"] |
| `engine/__init__.py` | package root, no forbidden imports | VERIFIED | Exists; documents the no-forbidden-imports invariant |
| `engine/probs.py` | p_map logistic, Bo3 closed form, odds-override passthrough, Beta-clamp + epistemic stubs | VERIFIED | All five functions present and substantive (111 lines); exports p_map, series, series_prob, difficulty, epistemic_draws, beta_moment_fit |
| `engine/teams.py` | 16-team seed->team map, R1 derivation, default ratings, Stage config | VERIFIED | build_round1_pairs uses range(1,9); _DEFAULT_FIXTURE has all 16 teams; _validate_fixture on load; 139 lines |
| `engine/swiss.py` | PRIORITY_TABLE, rank_group, pair_within_group, simulate_stage, locked support | VERIFIED | 280 lines; all named exports present; imports difficulty from engine.probs (no second copy) |
| `engine/montecarlo.py` | SeedSequence.spawn RNG, per-chunk yield, sample retention, Wilson band, cached-wrapper | VERIFIED | 232 lines; run_mc_progressive and run_mc exported; wilson() present |
| `engine/__main__.py` | headless smoke run printing per-team probs + Wilson bands | VERIFIED | Exists; uv run python -m engine 5000 exits 0 and prints 16-row table |
| `data/stage1.json` | editable [INFERRED] Cologne seeds + ratings, GamerLegion present | VERIFIED | 27 lines; 16 teams; seeds_confirmed=false; GamerLegion present at seed 1 rating 92 |
| `tests/conftest.py` | shared fixtures (teams, seeds) for the whole suite | VERIFIED | FakeTeam + make_team factory + teams fixture + seeds fixture |
| `tests/test_probs.py` | test_difficulty_formula, test_p_map, test_bo3 math guards | VERIFIED | 5 tests; all PASS |
| `tests/test_swiss.py` | fold key, forced rematch, fallback, locked — all green | VERIFIED | 7 tests; all PASS |
| `tests/test_mc.py` | reproducibility, invariants, sample retention, epistemic-collapse — all green | VERIFIED | 8 tests; all PASS |
| `tests/test_backtest_budapest_2025.py` | gate test (skip-with-reason) + fixture-shape test (green) | VERIFIED | 1 SKIPPED (GATE-01 deferred, skip reason explicit); 1 PASSED (fixture-shape) |
| `tests/fixtures/budapest_2025_stage1.json` | reconciled Budapest 2025 Stage 1 fixture, seeding=null, M80 present | VERIFIED | Exists; seeding=null; seeding_note contains "UNRESOLVED"; "M80" in teams list |
| `.planning/todos/pending/2026-05-29-budapest-backtest-gate-gate01.md` | tracked TODO for deferred backtest | VERIFIED | File exists; deferral is tracked, not dropped |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| engine/swiss.py | engine.probs | `from engine.probs import difficulty, p_map, series` | WIRED | Line 37 of swiss.py; difficulty() is imported canonical, no second copy |
| engine/swiss.py ranking | fold | `(-difficulty, seed)` sort key feeding pair_within_group | WIRED | rank_group line 82; test_fold_uses_difficulty_rank proves sort is load-bearing (disjoint-construction) |
| engine/montecarlo.py | engine.swiss.simulate_stage | inner loop calls simulate_stage per sim | WIRED | montecarlo.py line 174: `simulate_stage(_fresh_teams(teams), ...)` |
| engine/montecarlo.py | SeedSequence.spawn | pinned n_chunks child generators | WIRED | Lines 168-170; `np.random.SeedSequence(seed).spawn(n_chunks)` |
| tests/test_probs.py | engine.probs | `from engine.probs import ...` | WIRED | Line 12; all six functions imported and exercised |
| tests/test_swiss.py | engine.swiss | `from engine.swiss import ...` | WIRED | Per-test local imports of difficulty, pair_within_group, PRIORITY_TABLE, simulate_stage |
| engine/teams.py R1 derivation | seed map | `[(by_seed[i], by_seed[i + 8]) for i in range(1, 9)]` | WIRED | Lines 137-138; no second hardcoded R1 table |

---

### Data-Flow Trace (Level 4)

Not applicable to Phase 1 — this phase delivers a headless engine core with no UI and no dynamic data rendering. The `uv run python -m engine` smoke run constitutes the only "rendering" and was verified live (21 teams, correct invariants, correct eyeball sanity).

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full pytest suite green | `uv run pytest -v` | 21 passed, 1 skipped, 0 failures in 9.39s | PASS |
| Difficulty formula: opponents 2-0 and 1-1 → 2 | test_difficulty_formula in test_probs.py | PASSED | PASS |
| Bo3 closed form: series(0.6, True) == 0.648 | test_bo3 in test_probs.py | PASSED | PASS |
| Headless smoke run prints 16-team table, invariant sums = 2/8/2 | `uv run python -m engine 5000` | Printed; sums 2.000/8.000/2.000; exit 0 | PASS |
| No forbidden imports in engine/ | `uv run python -c "import engine.probs, engine.teams, engine.swiss, engine.montecarlo"` | "no forbidden imports"; exit 0 | PASS |
| Fixture-shape test for deferred backtest | test_budapest_fixture_shape_is_internally_legal | PASSED | PASS |

---

### Probe Execution

No probe-*.sh files declared or present for this phase. The test suite is the probe.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ENG-01 | 01-01, 01-02 | R1 pairings derived from seed map, no second copy | SATISFIED | build_round1_pairs uses range(1,9); PRIORITY_TABLE not a second R1 copy |
| ENG-02 | 01-02 | Rounds 2+ via single code path, no if round==2 | SATISFIED | swiss.py loop has no round-number branch; rank_group handles R2 uniform difficulty falling to seed sort automatically |
| ENG-03 | 01-01, 01-02 | Difficulty = Σ(opp.wins − opp.losses), NOT Σ opp.wins | SATISFIED | probs.py line 71: `sum(o.wins - o.losses for o in t.opps)`; test_difficulty_formula asserts result is 2 not 3 |
| ENG-04 | 01-02 | Within-group fold sorts on difficulty-ranked order | SATISFIED | rank_group sort key is (-difficulty(t), t.seed); test_fold_uses_difficulty_rank proves it is load-bearing |
| ENG-05 | 01-02 | No rematch-free match → least-disruptive rematch + warning, no crash | SATISFIED | _least_disruptive_rematch + pair_within_group fallback; test_no_valid_matching_fallback PASSES |
| ENG-06 | 01-02 | Bo3 iff team at 2W or 2L | SATISFIED | _is_bo3 checks wins==2 or losses==2; test_bo3_placement_and_termination |
| ENG-07 | 01-02 | Teams terminate at 3W or 3L; no rematches | SATISFIED | test_locked_results_honored and test_bo3_placement_and_termination assert all terminals; opps uniqueness asserted |
| ENG-08 | 01-02 | locked dict honored deterministically, history in opps | SATISFIED | _play checks locked key before sampling; _record_match adds opps including locked; test_locked_results_honored PASSES across different rng seeds |
| ENG-09 | 01-03 | SeedSequence.spawn pinned chunk count for reproducibility | SATISFIED | SeedSequence(seed).spawn(n_chunks) with DEFAULT_N_CHUNKS=20; test_reproducibility and test_reproducibility_survives_n_chunks_default both PASS |
| GATE-01 | 01-04 | Round-by-round Budapest backtest reproduces actual pairings | DEFERRED | User decision 2026-05-29; seeds unsourceable; tracked TODO |
| GATE-02 | 01-01 | test_difficulty_formula asserts difficulty() == 2 | SATISFIED | PASSES in both test_probs.py and test_swiss.py |
| GATE-03 | 01-02 | Forced-rematch priority table + unmatchable fallback both green | SATISFIED | test_forced_rematch_pairing and test_no_valid_matching_fallback both PASS |
| GATE-04 | 01-04 | Greedy fold replaced by literal table lookup on divergence | DEFERRED | Table encoded and unit-tested; fork untested against real data (GATE-01 deferred) |
| GATE-05 | 01-04 | No output trusted until GATE-01 green (reinterpreted) | DEFERRED/REINTERPRETED | Phase 2 unblocked on rulebook unit tests; trust badge must not overclaim |
| MC-01 | 01-03 | N sims tallying per-team 3-0/advance/0-3 | SATISFIED | run_mc_progressive tallies all three; test_invariants PASSES |
| MC-02 | 01-03 | Wilson confidence bands, no scipy | SATISFIED | wilson() closed-form; test_wilson_closed_form PASSES to 1e-12 |
| MC-03 | 01-03 | Invariants ±0.05 at N≥50k | SATISFIED | Sums structurally exact 2/8/2; test_invariants PASSES at N=50k |
| MC-04 | 01-03 | Full per-sim record sample retained | SATISFIED | Result.sample accumulates; test_record_sample_retained PASSES (len==N) |
| MC-05 | 01-03 | Generator-first with per-chunk Partials; cached wrapper seam | SATISFIED | run_mc_progressive yields Partials; run_mc drains; test_progress_partials_yielded PASSES |
| MC-06 | 01-01, 01-02 | Bo3 = p²(3−2p) as single Bernoulli draw, never 3-map sampling | SATISFIED | series() in probs.py; _play in swiss.py uses single rng.random() < p_a draw; test_bo3 PASSES |
| PROB-01 | 01-01 | p_map = logistic with S default 40 | SATISFIED | probs.py line 29; test_p_map PASSES |
| PROB-02 | 01-01 | Odds-derived series prob used directly, Bo3 not re-applied | SATISFIED | series_prob() passthrough; test_odds_override_passthrough PASSES |
| PROB-03 | 01-01, 01-03 | Epistemic variance as OUTER loop | SATISFIED | epistemic_draws outer loop wraps chunk loop in run_mc_progressive; yields one draw in Phase 1 |
| PROB-04 | 01-01 | Beta MoM fit clamps var < p(1-p) | SATISFIED | beta_moment_fit clamps at probs.py lines 102-110; test_epistemic_stub_and_beta_clamp PASSES |
| PROB-05 | 01-01, 01-03 | Reported band = epistemic spread; single source collapses to Wilson | SATISFIED | test_epistemic_band_collapses_to_wilson PASSES (matches to 1e-12) |

**Coverage: 22/25 SATISFIED; 3 DEFERRED (GATE-01/04/05 — accepted user decision, not undiscovered gaps)**

---

### Anti-Patterns Found

The following items were surfaced by the code review (01-REVIEW.md). They are advisory findings carried from the review, not verification blockers — none prevent the phase goal from being achieved, and none contain unresolved TBD/FIXME/XXX debt markers.

| File | Finding | Severity | Impact on Phase Goal |
|------|---------|----------|----------------------|
| `engine/montecarlo.py:230` | CR-01: `assert result is not None` stripped under `python -O`; function would return None | WARNING | Does not affect phase goal (no -O use in test suite); fix recommended before Phase 2 |
| `engine/probs.py:102-110` | CR-02: `beta_moment_fit` produces invalid Beta params for mean=0.0 or mean=1.0 | WARNING | Unused in Phase 1 (epistemic_draws yields one point draw); fix required before Phase 5 |
| `engine/teams.py:84-85` | CR-03: `_validate_fixture` duplicate-seed check is dead code (dict keys are unique by definition) | WARNING | Real guard is in load_teams() at line 125; duplicate detection still works; advisory clean-up |
| `engine/montecarlo.py:119-120` | WR-04: n_chunks > N produces zero-sized chunks and spurious Partial emissions | WARNING | Does not affect test suite (N always >> n_chunks); guard recommended before Phase 2 |
| `engine/swiss.py:226` | IN-02: `series_prob()` exists but `_play` calls series(p_map(...)) inline, bypassing the canonical function | INFO | Phase 5 odds override will require a second change site if not fixed first |
| `tests/conftest.py:29` | WR-03: FakeTeam.opps is a list; Team.opps is a set; simulate_stage calls opps.add() which crashes on FakeTeam | WARNING | Current tests avoid passing FakeTeam to simulate_stage; latent contract mismatch; recommended fix before next wave |

No `TBD`, `FIXME`, or `XXX` markers found in any engine/ or tests/ file. The single "placeholder" comment found in montecarlo.py line 163 is a design-note describing the Phase 5 seam (`blend/var are single-source placeholders; Phase 5 supplies real per-source values`) — this is intentional architectural narration, not a debt marker, and the code it describes is fully implemented and tested.

---

### Human Verification Required

None. All phase-goal truths are verifiable programmatically. The deferred items (GATE-01/04/05) are tracked deferrals, not human-verify items.

---

### Open Risk: Budapest Divergence (carry forward to Phase 2)

The divergence finding in `budapest-2025-reconciliation-DRAFT.md` is worth noting as a risk carried into subsequent phases:

Under the available HLTV VRS world-rank ordering, the engine's N-vs-N+8 R1 fold and the pure-seed R2 fold do NOT reproduce Budapest's actual pairings. Two unresolved hypotheses:
(a) Budapest used a different seed-assignment scheme than VRS world-rank order, OR
(b) Valve's within-group pairing has a nuance the engine's difficulty-fold does not capture.

These cannot be disentangled without the authoritative seed bracket. Until GATE-01 is completed with authoritative seeds, the engine is validated only against the Valve rulebook unit tests, not against live Major data. Phase 2 trust badge wording must reflect this.

---

### Gaps Summary

No gaps. The phase goal — a pytest-runnable, dependency-free correctness core that simulates the Valve Stage-1 Swiss format, gated on rulebook unit tests — is fully achieved. The 21-test green suite (plus 1 correctly-deferred skip) is the hard gate the phase was narrowed to by user decision. GATE-01/04/05 are DEFERRED with full audit trail; they are not undiscovered gaps.

---

_Verified: 2026-05-29T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
