---
phase: 04-conditional-re-sim-live-mode
plan: 01
subsystem: testing
tags: [live, validator, classify, pge5-delta, bracket, pure-core, tdd, numpy]

# Dependency graph
requires:
  - phase: 01-engine-correctness-core
    provides: "simulate_stage(..., locked, pairings_out=[]) deterministic-replay + locked seam; ADVANCE_AT_WINS/ELIMINATE_AT_LOSSES; the GATE-01 Budapest backtest path"
  - phase: 03-pickem-optimizer
    provides: "engine.optimizer.build_outcome_matrices + p_ge5 + Ballot — reused verbatim for classification and the from-here delta"
provides:
  - "engine/live.py — pure, streamlit-free live-mode core sitting on the frozen engine"
  - "locked_dict_from_results (D1) — lock-list <-> engine `locked` dict projection"
  - "validate_lock (D3/RESIM-03) — rejects rematch / terminated / non-pairing / double-booking / winner-not-in-pair with EXACT reason strings"
  - "classify_pick (D4/RESIM-02) — secured/dead/live STATUS keys off the conditional sample"
  - "pge5_delta (D5/RESIM-02) — the from-here arrow as two p_ge5 calls on ONE fixed anchor ballot"
  - "derive_bracket + BracketView + legal_pairings_for_round + LivePrefixIncomplete (D6/RESIM-04) — replay simulate_stage for pairings + record standings, with the full-prefix guard"
affects: [04-02 (LIVE-mode UI wiring consumes the entire pure core)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure functional-core layer over the frozen engine: import swiss/optimizer/teams, never mutate them (mirrors the optimizer's streamlit-free discipline)"
    - "Replay-as-source-of-truth: bracket pairings + validator legal_pairings come from simulate_stage(..., pairings_out=[]), never hand-derived (no GATE-01 re-opening)"
    - "Sample-only classification/delta: read Result.sample via build_outcome_matrices / p_ge5, never re-run the MC"
    - "rng-invariance precondition: legal_pairings_for_round requires a fully-locked prefix and raises LivePrefixIncomplete rather than return a single-draw artifact"

key-files:
  created:
    - "engine/live.py — the live-mode pure core (316 lines)"
    - "tests/test_live.py — the eleven live-core tests (374 lines), authored TDD RED-first"
  modified: []

key-decisions:
  - "validate_lock check order is winner-not-in-pair -> rematch -> terminated -> non-pairing -> double-booking, so each test hits its specific reason; the structural/degenerate checks precede the state checks"
  - "Used a sample-only _Result stand-in in the test (per plan WARNING-5) so fixtures never trip on engine.montecarlo.Result.__init__ arity; classify/delta read only .sample"
  - "legal_pairings_for_round enforces the prefix by comparing each prior round's locked set to the engine's pairings_out[r] exactly (set equality), raising LivePrefixIncomplete on any mismatch"

patterns-established:
  - "Pattern: no engine mutation — engine/live.py is the only new engine file; full suite + GATE-01 prove the frozen engine is untouched"
  - "Pattern: _fresh_teams rebuilt locally (not imported from montecarlo's private helper) so the replay owns its mutable Team state"

requirements-completed: [RESIM-02, RESIM-03, RESIM-04]

# Metrics
duration: ~12 min
completed: 2026-05-29
---

# Phase 4 Plan 01: Live-Mode Pure Core Summary

**`engine/live.py` — a pure, streamlit-free live-mode core that validates locks with exact reason strings, classifies picks secured/dead/live against the conditional sample, computes the P(>=5)-from-here delta on a fixed anchor ballot, and derives the record-bucket bracket + validator legal-pairings by replaying the frozen engine — with NO engine mutation and the GATE-01 Budapest backtest still green.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 3 (1 RED test task + 2 GREEN impl tasks)
- **Files created:** 2 (`engine/live.py`, `tests/test_live.py`)
- **Files modified (engine):** 0 — no engine mutation

## Accomplishments
- `tests/test_live.py`: eleven hand-authored tests (RED-first) over the not-yet-existing `engine.live` API, including the three CRITICALs — `test_classify_secured_dead_live`, `test_derive_bracket_pairings_match_engine`, `test_legal_pairings_requires_full_prefix`.
- `engine/live.py` (316 lines, > the 120 min): `locked_dict_from_results` (D1), `validate_lock` (D3/RESIM-03), `classify_pick` (D4/RESIM-02), `pge5_delta` (D5/RESIM-02), `derive_bracket` + `BracketView` + `legal_pairings_for_round` + `LivePrefixIncomplete` (D6/RESIM-04).
- The bracket/validator path REPLAYS `simulate_stage(..., pairings_out=[])` — `test_derive_bracket_pairings_match_engine` asserts the derived per-round legal_pairings equal the engine's `pairings_out[R]` exactly (the replay IS the source of truth).
- The BLOCKER-2 rng-invariance guard: `legal_pairings_for_round` requires a fully-locked prefix (rng-invariant set across `default_rng(0)` vs `default_rng(1)`) and raises `LivePrefixIncomplete` on an incomplete prefix — never a single-draw artifact.
- Full suite: **79 passed** (68 baseline + 11 new), zero regressions. GATE-01 `test_backtest_budapest_2025` still green.

## Task Commits

Each task was committed atomically (TDD: RED test → GREEN impl ×2):

1. **Task 1: tests/test_live.py — eleven live-core tests (RED)** — `5113562` (test)
2. **Task 2: engine.live lock projection + validate_lock + classify_pick (GREEN 1)** — `80ddd35` (feat)
3. **Task 3: pge5_delta + derive_bracket + legal_pairings_for_round (GREEN 2)** — `48fd101` (feat)

## Files Created/Modified
- `engine/live.py` — the live-mode pure core: D1 lock projection, D3 validator, D4 classifier, D5 delta, D6 bracket/legal-pairings replay + prefix guard. Imports swiss/optimizer/teams only; mutates none.
- `tests/test_live.py` — eleven tests; fabricates `sample` lists by hand (N tiny) for classify/delta, reuses the Budapest fixture seeds (id == seed) + a fixed `np.random.default_rng` for the bracket/validator replays.

## Decisions Made
- **validate_lock check order:** winner-not-in-pair → rematch → terminated-team → non-pairing → double-booking. Structural/degenerate checks precede state checks so every test surfaces its specific reason (e.g. the double-booking test's `(1,9)` is legal + non-rematch + team 1 not terminated, so it correctly falls through to the double-booking check).
- **Sample-only `_Result` stand-in in the test** (plan WARNING-5 sanctioned): avoids any coupling to `engine.montecarlo.Result.__init__` arity; `pge5_delta` reads only `.sample`.
- **Prefix enforcement by exact set equality:** `legal_pairings_for_round` compares each prior round's locked set against the engine's `pairings_out[r]` and raises `LivePrefixIncomplete` on any mismatch — so the validator can never accept/reject against an arbitrary draw.

## Deviations from Plan

None - plan executed exactly as written.

The eleven named tests, the eight exported symbols, the no-engine-mutation invariant, the RED-first discipline, and all three CRITICALs were implemented as specified. No bugs, missing critical functionality, or blockers surfaced.

---

**Total deviations:** 0
**Impact on plan:** None — clean TDD execution; the frozen engine and optimizer were imported and called only.

## Issues Encountered
None.

## Threat Flags
None — no new network endpoints, auth paths, file access, or schema changes. The threat register's `mitigate` dispositions (T-04-MUT no-mutation, T-04-SEED replay-not-hand-derive, T-04-DRAW prefix-guard, T-04-MC sample-only, T-04-BADLOCK validate-before-engine) are all realized and test-covered.

## Known Stubs
None — `engine/live.py` is fully wired; every function reads real engine/optimizer output. (The UI that consumes this core is Plan 04-02, intentionally out of scope here.)

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The entire live-mode decision math is provable in `pytest` with no UI — Plan 04-02 (LIVE-mode UI wiring) can consume `validate_lock`, `classify_pick`, `pge5_delta`, `derive_bracket`, and `legal_pairings_for_round` directly.
- The `locked` dict projection (D1) is the exact shape `freeze_locked` → `cache_key` consumes, so re-sim "fires for free" once 04-02 wires the lock list into `app.py`'s `_run_or_serve`.
- No blockers. GATE-01 stays green; no engine mutation.

## Self-Check: PASSED
- `engine/live.py` — FOUND on disk (316 lines).
- `tests/test_live.py` — FOUND on disk (374 lines).
- Commit `5113562` (RED test) — FOUND in git log.
- Commit `80ddd35` (GREEN 1) — FOUND in git log.
- Commit `48fd101` (GREEN 2) — FOUND in git log.
- `uv run pytest -q tests/test_live.py` — 11 passed.
- `uv run pytest -q` — 79 passed (no regression).
- `test_backtest_budapest_2025` — 3 passed (GATE-01 green).

---
*Phase: 04-conditional-re-sim-live-mode*
*Completed: 2026-05-29*
