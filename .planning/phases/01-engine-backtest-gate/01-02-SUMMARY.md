---
phase: 01-engine-backtest-gate
plan: 02
subsystem: engine
tags: [python, swiss, valve, buchholz, pairing, monte-carlo, tdd]

# Dependency graph
requires:
  - "01-01: engine.probs.difficulty (canonical Buchholz), p_map, series; engine.teams.Team + build_round1_pairs + load_teams; Wave-0 xfail scaffold in tests/test_swiss.py"
provides:
  - "engine/swiss.py: rank_group, pair_within_group, PRIORITY_TABLE (verbatim 15-row Valve oracle), simulate_stage (full single-stage Valve Swiss with deterministic locked support)"
  - "Bo3 placement (2W/2L), 3W/3L termination, no-rematch fold + priority-table resolution + least-disruptive rematch fallback"
  - "the locked dict[frozenset({id,id})->winner_id] seam Phase 4 conditional re-sim rides on"
affects: [03-monte-carlo, 04-backtest-gate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "difficulty() imported canonical from engine.probs — single source of truth, no second copy (ENG-03)"
    - "Single seeding code path for all rounds >= 2: rank key (-difficulty, seed), no if round==2 (ENG-02/04)"
    - "Valve 15-row priority table as the pairing oracle for 6-team groups; high-vs-low fold for other sizes (GATE-03/04)"
    - "opps holds opponent OBJECTS (difficulty reads o.wins-o.losses); Team made hashable (eq=False) so objects fit the opps set"
    - "Bo3 = closed form series() as a SINGLE Bernoulli draw via the injected rng — never 3-map sampling (MC-06)"
    - "locked honored deterministically and recorded in opps so the no-rematch rule respects locked history (ENG-08, Phase-4 seam)"

key-files:
  created:
    - engine/swiss.py
  modified:
    - engine/teams.py
    - tests/test_swiss.py

key-decisions:
  - "Team made hashable via @dataclass(eq=False): the engine stores opponent OBJECTS in opps (difficulty() needs o.wins/o.losses), and the default dataclass __eq__ makes instances unhashable so opps.add(team) would crash. Identity equality is correct — each Team is a distinct stage entity."
  - "simulate_stage signature is (teams, ratings, S, rng, locked) per the plan; ratings is an optional {id: rating} override (None -> use team.rating) — the Phase-5/MC seam."
  - "test_fold_uses_difficulty_rank rebuilt to a DISJOINT-pairing construction (difficulty order [1,2,4,3] -> {1v3,2v4} vs seed order [1,2,3,4] -> {1v4,2v3}); for a 4-team group the two pairs partition the ids, so an earlier reversal construction silently produced the same pairing set and could not prove the sort is load-bearing."
  - "Malformed locked key (winner id not one of the paired teams) raises ValueError rather than silently mis-applying — Phase 1 mitigation for T-02-01."

# Metrics
duration: ~20min
completed: 2026-05-28
---

# Phase 1 Plan 02: Swiss Engine (Pairing + Stage Simulator) Summary

**Built the correctness core — `engine/swiss.py` — the Valve Stage-1 Swiss pairing + single-stage simulator: a single seeding code path (`rank_group` by `(-difficulty, seed)`, difficulty imported canonical from `engine.probs`), Valve's verbatim 15-row `PRIORITY_TABLE` as the rematch-resolution oracle for 6-team groups with a high-vs-low fold for other sizes and a least-disruptive-rematch fallback that warns instead of crashing on `None`, plus `simulate_stage(teams, ratings, S, rng, locked)` that plays one full stage (Bo3 iff 2W/2L, single Bernoulli draw, terminate at 3W/3L, no rematches) and honors a `locked` dict deterministically while recording locked history in `opps`. All wave-2 swiss tests flipped from xfail to green.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 2 of 2
- **Files created:** 1 (+2 modified)

## Accomplishments

- The fold key is provably load-bearing, not dead code (Pitfall 3 / ENG-04): `test_fold_uses_difficulty_rank` uses a difficulty order (`[1,2,4,3]` -> `{1v3,2v4}`) that is fully disjoint from the raw-seed fold (`{1v4,2v3}`), so removing the difficulty term flips the output and fails the test. Verified empirically against `_fold_match`.
- `PRIORITY_TABLE` matches Valve's verbatim 15 rows from `01-RESEARCH.md`; the forced-rematch group (Priority-1 row contains a rematch on positions 2,5) correctly falls through to the top-most rematch-free row (Priority 2: `1v6,2v4,3v5`).
- The unmatchable group (a 2-team group where the only pair is a rematch) pairs the forced rematch and emits a `log.warning` — never an unhandled `None` / crash (ENG-05).
- `simulate_stage` honors a fully-locked Round 1 deterministically across different rng seeds; post-lock invariants hold every run (exactly 8 advance at 3W, 8 eliminated at 3L, exactly 2 go 3-0 and 2 go 0-3, no pair plays twice). Locked opponents are recorded in `opps` so the no-rematch rule respects locked history (ENG-08).
- `engine/swiss.py` imports no streamlit/httpx/requests (functional-core / gate-ability invariant holds; asserted by `test_swiss_no_forbidden_imports`).
- Full suite: 12 passed (5 probs math guards + 7 swiss), 5 xfailed (MC wave 3 + backtest wave 4) — the suite is not falsely green.

## Task Commits

1. **RED: wave-2 swiss tests** — `eed942b` (test) — replaced the xfail scaffold with real assertions; all failed (no `engine/swiss.py`).
2. **Task 1: within-group ranking + fold + verbatim priority-table oracle** — `c2eaf12` (feat) — GREEN gate for `rank_group`/`pair_within_group`/`PRIORITY_TABLE`/fallback.
3. **Task 2: simulate_stage — full Swiss loop, Bo3 placement, locked support** — `a11ec08` (feat) — GREEN gate for `simulate_stage`; includes the `engine/teams.py` hashability fix.

## Files Created/Modified

- `engine/swiss.py` *(created)* — `PRIORITY_TABLE` (15 rows verbatim), `rank_group`, `_is_rematch`, `_fold_match`, `_pair_via_priority_table`, `_least_disruptive_rematch`, `pair_within_group`, `_is_bo3`, `_play`, `simulate_stage`. `difficulty` imported from `engine.probs`.
- `engine/teams.py` *(modified)* — `Team` changed to `@dataclass(eq=False)` and `opps` retyped to a set of opponent objects (see Deviations).
- `tests/test_swiss.py` *(modified)* — xfail scaffold replaced with real assertions: `test_difficulty_unit`, `test_fold_uses_difficulty_rank`, `test_forced_rematch_pairing`, `test_no_valid_matching_fallback`, `test_locked_results_honored`, `test_bo3_placement_and_termination`, `test_swiss_no_forbidden_imports`.

## Verification

| Check | Result |
|-------|--------|
| `uv run pytest -q tests/test_swiss.py` | 7 passed |
| `uv run pytest -q` (full suite) | 12 passed, 5 xfailed — not falsely green |
| Difficulty sort is load-bearing (seed fold `{1v4,2v3}` != diff fold `{1v3,2v4}`) | OK (verified via `_fold_match`) |
| `PRIORITY_TABLE` rows 1/2 verbatim + len 15 | OK |
| Forced-rematch 6-team group -> Priority 2 (`1v6,2v4,3v5`) | OK |
| Unmatchable group -> least-disruptive rematch + warning, no crash | OK |
| Fully-locked R1 deterministic across rng seeds; invariants hold; no rematches | OK |
| `engine/swiss.py` imports no streamlit/httpx/requests | OK |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `Team` was unhashable, blocking object-valued `opps`**
- **Found during:** Task 2 (`simulate_stage` recording opponents).
- **Issue:** The canonical `engine.probs.difficulty()` iterates `o.wins - o.losses for o in t.opps`, i.e. `opps` must hold opponent OBJECTS, not ids (confirmed by `conftest.FakeTeam.opps` and `test_difficulty_formula`). But `engine.teams.Team` was a default `@dataclass` (`eq=True`), which makes instances unhashable, so `opps.add(team)` (a set) would raise `TypeError: unhashable type`.
- **Fix:** Changed `Team` to `@dataclass(eq=False)` (identity-based eq + hash — correct since each Team is a distinct stage entity) and retyped `opps: set[int]` -> `opps: set` of opponent objects, with an updated docstring. No wave-1 test compares `Team` equality, so this is safe.
- **Files modified:** `engine/teams.py`.
- **Commit:** `a11ec08`.

**2. [Rule 1 - Correctness] `test_fold_uses_difficulty_rank` construction did not actually distinguish the keys**
- **Found during:** Task 1 GREEN (the freshly-written test failed its own anti-dead-code assertion).
- **Issue:** The initial construction used a difficulty order that was a permutation whose 4-team fold produced the SAME pairing SET as the raw-seed fold (for 4 teams the two pairs partition the four ids, so a shared pair forces the other). The test could pass with the difficulty sort removed — i.e. it did not prove the sort is load-bearing.
- **Fix:** Rebuilt the fixture so the difficulty order is `[1,2,4,3]` (fold -> `{1v3,2v4}`), fully DISJOINT from the raw-seed fold (`{1v4,2v3}`). Removing the difficulty term now flips the output and fails the test (verified empirically).
- **Files modified:** `tests/test_swiss.py` (test was authored this plan; corrected before the GREEN commit).
- **Commit:** `c2eaf12`.

## Known Stubs

None. `simulate_stage` is fully wired against `engine.probs` (`series`, `p_map`) and `engine.teams` (`build_round1_pairs`, stage constants); no placeholder data or empty returns. The `ratings` override parameter accepts `None` (use each team's own rating) — this is the intended Phase-5/MC seam, not a stub.

## Threat Flags

None. `simulate_stage`'s only input surface is the caller-supplied `locked` dict and `ratings` (no network/auth/DB). The threat register's `T-02-01` (malformed locked key) is mitigated: a locked winner that is not one of the paired teams raises `ValueError` rather than being silently mis-applied. `T-02-02` (DoS on unmatchable group) is mitigated: the `None` fallback pairs the least-disruptive rematch + warns, bounded by group size.

## Notes for Later Waves

- **Wave 3 (montecarlo.py):** call `simulate_stage(load_teams(), ratings_or_None, S, child_rng, locked)` per sim inside the inner aleatoric loop; pass a FRESH `load_teams()` each sim (the engine mutates `wins/losses/opps`). `simulate_stage` returns `{id: Team}`; tally `t.wins == 3` (advance), `t.wins == 3 and t.losses == 0` (3-0), `t.losses == 3 and t.wins == 0` (0-3). The per-sim record sample (MC-04) can be derived from the returned final `(wins, losses)` per id.
- **Wave 4 (the backtest gate):** encode the reconciled Budapest 2025 fixture as a fully-`locked` board (one `frozenset({id,id}) -> winner_id` per played match) and assert `simulate_stage` GENERATES the actual round-by-round pairings. If an 8-team bucket's greedy fold diverges from Valve's table (open question A4), extend the `PRIORITY_TABLE` oracle to that size — the `len(ranked) == 6` guard in `pair_within_group` is the single place to branch.
- **8-team buckets:** `pair_within_group` currently routes only 6-team groups through the verbatim table and everything else through the generalizing fold. The wave-4 transcription must confirm whether any Budapest bucket held 8 teams and whether the fold reproduces Valve's pairing there (GATE-04 fork).

## Self-Check: PASSED
