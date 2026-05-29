---
phase: 01-engine-backtest-gate
plan: 04
subsystem: engine
tags: [python, pytest, backtest, fixture, swiss, deferred-gate]

# Dependency graph
requires:
  - "01-02: engine.swiss.simulate_stage(teams, ratings, S, rng, locked) — the pairing engine the deferred backtest will eventually assert against"
  - "01-03: engine.montecarlo reproducibility (proves the chunked path the future backtest will run is deterministic)"
provides:
  - "tests/fixtures/budapest_2025_stage1.json: the FROZEN, verified Budapest 2025 Stage 1 RESULTS (16 teams, full R1-R5 round-by-round matchups/winners/Bo-status, 8 advance / 8 eliminated). seeding=null (UNRESOLVED). Records the VRS-vs-actual-pairing divergence finding."
  - "tests/test_backtest_budapest_2025.py: GATE-01 backtest SKIPPED-with-reason (deferred pending authoritative seeds) + a green fixture-shape test that validates internal legality without seeds (T-04-02)"
  - ".planning/todos/pending/2026-05-29-budapest-backtest-gate-gate01.md: tracked TODO capturing the blocker, the divergence finding, and the resume path"
affects: [02-streamlit-ui, 06-full-major-v3]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deferred-gate pattern: when a hard gate is blocked on unobtainable external data, freeze the VERIFIED partial (results), record the blocker + divergence in the fixture itself, skip-with-reason the unprovable assertion, and gate the phase on the already-green narrower checks — never assert a green backtest on guessed data (T-04-01)"
    - "Fixture-shape validation (T-04-02) asserts internal legality (8/8 partition, no rematch, legal terminal records, stable advancer set) WITHOUT requiring the seeding or asserting pairing generation"

key-files:
  created:
    - tests/fixtures/budapest_2025_stage1.json
    - .planning/todos/pending/2026-05-29-budapest-backtest-gate-gate01.md
  modified:
    - tests/test_backtest_budapest_2025.py

key-decisions:
  - "USER DECISION 2026-05-29: DEFER the full Budapest pairing-reproduction backtest (GATE-01). The RESULTS reconciled cleanly (both anchors verified) but the authoritative Valve 1-16 seed integers could not be sourced (HLTV Cloudflare-walled; Liquipedia/Wikipedia publish no seed integers), and the HLTV VRS world-rank order does NOT reproduce the actual R1 pairings or the R2 pure-seed fold. Asserting a backtest on a guessed seeding would be a false pass/fail (T-04-01). Phase 1 is gated on the green rulebook unit tests instead; Phase 2 unblocked WITH caveat."
  - "engine/swiss.py left UNTOUCHED — the GATE-04 priority-table fork was never exercised against real pairings (the backtest that would trigger it is deferred). The fork is part of the deferred work, not encoded blind."
  - "test_backtest_budapest_2025 is SKIPPED (not xfail): it is explicitly deferred pending data, not 'expected to fail' on a bug. A separate fixture-shape test stays green to freeze the verified results and validate fixture integrity (T-04-02)."

requirements-completed: []

# Metrics
duration: ~25min
completed: 2026-05-29
---

# Phase 1 Plan 04: Budapest Backtest Gate (DEFERRED) Summary

**The Budapest 2025 Stage 1 fixture was transcribed and fully reconciled via /browse — the round-by-round RESULTS are verified and internally consistent (both anchors confirmed: exactly 8 teams at 1-1 entering R3; final eight = M80, FlyQuest, B8, Fnatic, NIP, PARIVISION, Imperial, FaZe) — and frozen at `tests/fixtures/budapest_2025_stage1.json` with `seeding: null`. The authoritative Valve 1-16 SEED assignment could NOT be sourced (HLTV Cloudflare-walled; Liquipedia/Wikipedia publish no seed integers), and critically the HLTV VRS world-rank order does NOT reproduce the actual R1 pairings or the R2 pure-seed fold — a divergence that cannot be disentangled (wrong-seeds vs an engine within-group-pairing nuance) without the authoritative bracket. Per an explicit user decision, the full pairing-reproduction backtest (GATE-01) is DEFERRED to a tracked TODO, the engine is gated on the already-green rulebook unit tests instead, and Phase 2 is unblocked with the caveat documented. The full suite is green: 21 passed, 1 skipped (the deferred backtest), with a new fixture-shape test validating fixture integrity without seeds (T-04-02).**

## What Was Done

- **Fixture frozen (results verified, seeds unresolved):** `tests/fixtures/budapest_2025_stage1.json` encodes the 16 teams, full R1-R5 round-by-round matchups/winners/scores/Bo-status, per-round record buckets, the 1-1-entering-R3 anchor, and the final 8 advance / 8 eliminated. `seeding` is `null` with a `seeding_note` explaining it is UNRESOLVED. Provenance recorded (Liquipedia oldid 3296139; HLTV VRS via user). Contains "M80".
- **Backtest deferred (not faked):** `test_backtest_budapest_2025` is `@pytest.mark.skip(reason="GATE-01 deferred ...")`. A new green test `test_budapest_fixture_shape_is_internally_legal` asserts the verified results are internally legal — 8/8 advance/eliminate partition, the stable advancer set, no rematch across all locked matchups, legal terminal records — WITHOUT needing the seeding or asserting pairing generation (T-04-02).
- **TODO filed:** `.planning/todos/pending/2026-05-29-budapest-backtest-gate-gate01.md` captures the blocker, the divergence finding, and the full resume path.
- **engine/swiss.py untouched:** no GATE-04 fork applied (never exercised against real data; deferred).

## The Divergence Finding (flag — possible engine nuance, not only a data gap)

This is the part worth root-causing before fully trusting the engine for Cologne:

- **R1 actual:** M80-B8, Imperial-RareAtom, FlyQuest-Legacy, PARIVISION-TheHuns, Fluxo-GamerLegion, NRG-NIP, FaZe-LynnVision, Fnatic-RED. Under the VRS world-rank order, the engine's N-vs-N+8 R1 fold would give Legacy-NIP, B8-LynnVision, FaZe-NRG, ... — completely different.
- **R2 "High"** (8 R1-winners, no rematch possible, uniform Buchholz → should be a pure seed fold): actual FlyQuest-Imperial, M80-PARIVISION, Fnatic-Fluxo, FaZe-NRG. Neither the world-rank order nor the per-card "orange" VRS order reproduces this fold.

**Two hypotheses, not yet disentangled:** (a) Budapest's published seed integers differ from both visible HLTV rankings, OR (b) Valve's within-group pairing has a nuance the engine's difficulty-fold does not capture (a real engine bug). These cannot be separated without the authoritative seed bracket — which is exactly why a green backtest must NOT be asserted now (T-04-01).

## Gate Status

| Gate | Status | Note |
|------|--------|------|
| GATE-01 (round-by-round backtest reproduces Budapest pairings) | **DEFERRED** | Blocked on authoritative Valve seeds; tracked in `.planning/todos/pending`. NOT marked complete. |
| GATE-02 (`test_difficulty_formula` == 2 on Valve's worked example) | ✓ | Green in `tests/test_swiss.py::test_difficulty_unit` (Wave 2). |
| GATE-03 (priority-table forced-rematch + unmatchable fallback) | ✓ | Green in `tests/test_swiss.py::test_forced_rematch_pairing` / `test_no_valid_matching_fallback` (Wave 2). |
| GATE-04 (greedy → verbatim priority-table lookup on divergence) | **DEFERRED** | Table encoded in `engine/swiss.py` (`PRIORITY_TABLE`, verified vs RESEARCH in unit tests) but the fork was never exercised against real pairings. NOT marked complete. |
| GATE-05 (gate before Phase 2) | **REINTERPRETED** | The hard backtest gate is deferred; Phase 1 is instead gated on the green rulebook unit tests (all passing). Phase 2 unblocked WITH the caveat below. |

## Trust-Badge Wording for Phase 2

Phase 2's persistent trust badge (UI-07) MUST read:

> **"engine validated vs Valve rulebook unit tests — full Budapest backtest pending seed data"**

NOT "engine validated vs Budapest 2025 backtest." The rulebook unit tests (difficulty formula, difficulty-rank fold, verbatim priority-table oracle, rematch fallback, locked determinism, MC invariants/reproducibility) are all green, but the round-by-round real-data backtest has NOT yet run. The badge wording must not overclaim.

## Deviations from Plan

This entire plan is itself an explicit, user-directed deviation from the original 01-04-PLAN.md, which instructed "remove the xfail marker so the gate is a real PASS/FAIL" and assert exact pairing reproduction. That instruction was overridden at the Task 1 human-verify checkpoint by a documented user decision once the seeding blocker surfaced (see Key Decisions and Gate Status above). No Rule 1-4 auto-deviations were applied during execution; `engine/swiss.py` was deliberately not modified.

## Verification

| Check | Result |
|-------|--------|
| `uv run pytest -q` (full suite) | 21 passed, 1 skipped (only the deferred backtest) |
| `tests/fixtures/budapest_2025_stage1.json` frozen, `seeding: null`, contains "M80" | OK |
| `test_budapest_fixture_shape_is_internally_legal` (8/8 partition, stable advancers, no rematch, legal records) | passed |
| `test_backtest_budapest_2025` skipped-with-reason (GATE-01 deferred) | skipped |
| `engine/swiss.py` untouched (no GATE-04 fork) | OK (not in git diff) |
| TODO filed at `.planning/todos/pending/` | OK |

## Known Stubs

None that masquerade as complete. The deferral is explicit and tracked:
- `test_backtest_budapest_2025` is skipped-with-reason (not silently passing).
- `engine/swiss.py`'s `PRIORITY_TABLE` is real and unit-tested, but its use as the GATE-04 fork oracle against real Budapest pairings is deferred (the divergence root-cause is part of the resume path).

## Threat Flags

None new. T-04-01 (assert against an unreconciled/guessed fixture) was actively avoided — the seeding is recorded as `null` rather than guessed, and the backtest is skipped rather than asserted on bad data. T-04-02 (fixture parse / shape) is mitigated by the green fixture-shape test. T-04-03 (which stage validated the engine) is satisfied honestly: the validated artifact is the rulebook unit-test suite, NOT the Budapest backtest — recorded for the Phase 2 trust badge.

## Self-Check: PASSED

- Files: FOUND tests/fixtures/budapest_2025_stage1.json, FOUND tests/test_backtest_budapest_2025.py, FOUND .planning/todos/pending/2026-05-29-budapest-backtest-gate-gate01.md
- Suite: 21 passed, 1 skipped (verified via uv run pytest)
- engine/swiss.py: untouched (confirmed absent from git diff)
