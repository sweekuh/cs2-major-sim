---
phase: 06-multi-stage-scaffold-live-results-seam
plan: 04
subsystem: ui
tags: [streamlit, live-results, validate_lock, cache-key, provenance, fail-soft, apptest]

# Dependency graph
requires:
  - phase: 06-01
    provides: "stage_id leading cache-key positional (_cache_key_for / _compute_or_serve / run_mc_cached / optimize_cached) + stage selector"
  - phase: 06-02
    provides: "scripts/fetch_results.py with _stage_number (stage1->1) writing _meta.stage as an int; per-stage fixtures + team_aliases.json"
  - phase: 06-03
    provides: "ui/results_loader.load_results_cache (read-only json+pathlib, four-branch fail-soft None); frozen results_cache.json schema"
provides:
  - "Fetch latest results button (lazy-imports scripts.fetch_results inside the click branch only — httpx never on the app import path)"
  - "_prefill_results_into_locked: FINISHED rows pre-fill KEY_LOCKED via the EXISTING legal_pairings_for_round -> validate_lock -> add_lock path (no engine edit, no bypass)"
  - "_stage_int_for canonical int-vs-str stage reconciliation (matches scripts.fetch_results._stage_number) — fixes the silent 1 == 'stage1' no-prefill bug"
  - "results _meta.fetched_at threaded into the run cache key (_combined_fetched_at) so a fresh fetch re-fires the conditional re-sim even with an unchanged locked set"
  - "Atomic validate-before-remove conflict-confirm (_apply_fetched_conflict) — a fetched lock conflicting with a manual lock requires explicit confirm and is validated BEFORE any removal; manual lock preserved on an engine-illegal fetched lock"
  - "Per-lock provenance (auto vs manual) + _meta.fetched_at staleness surfaced via existing fmt_age/is_stale"
affects: [phase-07-stage2-seeding-chain, live-results-ingest, conditional-resim]

# Tech tracking
tech-stack:
  added: []  # Phase 6 installs ZERO packages (RESEARCH N/A); uv run, no new deps
  patterns:
    - "Route every fetched lock through the existing validator (no engine edit) — same path as a manual lock"
    - "Validate-before-remove atomic swap (compute prospective state on a copy, validate, only then mutate)"
    - "Fold a fetched-cache ISO _meta.fetched_at into the run cache key so a fresh fetch invalidates the memoized Result"
    - "One canonical str<->int stage mapping shared by the app filter and the fetcher write side (no second representation)"
    - "Lock provenance dict {frozenset((w,ell)): 'auto'|'manual'} — missing reads as 'manual' (pre-Phase-6 default)"

key-files:
  created: []
  modified:
    - "app.py — fetch-results button, _stage_int_for, _prefill_results_into_locked, _combined_fetched_at, _apply_fetched_conflict, _render_results_conflict, _render_results_provenance; fetched_at threaded into _run_or_serve/_live_anchor; pre-fill called at top of the main block"
    - "ui/state.py — KEY_RESULTS_OUTCOME, KEY_PENDING_RESULT_CONFLICT, KEY_LOCK_PROVENANCE"
    - "tests/test_app.py — 7 RES-02/03/04 AppTests + _results_cache/_finished_row/_patch_results/_ss_get helpers"

key-decisions:
  - "Reconciled to 06-02's existing _meta.stage int representation: _stage_int_for matches scripts.fetch_results._stage_number exactly (stage1->1..playoffs->4) — no second mapping introduced (plan step 3 directive)."
  - "Folded BOTH odds and results fetched_at into the single cache-key fetched_at slot via _combined_fetched_at, so a fresh fetch from either source re-fires the re-sim without widening the key tuple."
  - "Conflict gate lives in the app/UX layer beside validate_lock, never inside the engine — a conflict-with-a-manual-lock is a UX gate, not an engine illegality."
  - "On a rejected (engine-illegal) confirm the pending conflict is kept stashed and the manual lock preserved; only a legal confirm clears the pending and swaps."

patterns-established:
  - "Atomic validate-first swap: build prospective-without-fetched on a copy -> legal_pairings_for_round -> validate_lock -> mutate ONLY on None."
  - "Provenance-gated overwrite: an auto-fetch only stops for confirm when it conflicts with a 'manual'-provenance lock for the same pair."

requirements-completed: [RES-02, RES-03]

# Metrics
duration: 80min
completed: 2026-06-05
---

# Phase 6 Plan 04: Live-results seam wired into the app Summary

**Fetched FINISHED results pre-fill the active stage's KEY_LOCKED through the existing validate_lock path (no engine edit), a fresh _meta.fetched_at re-fires the conditional re-sim, and a fetched result conflicting with a manual lock requires an explicit, atomically-validated confirm that preserves the manual lock on an engine-illegal swap.**

## Performance

- **Duration:** ~80 min
- **Started:** 2026-06-05T22:35Z (approx)
- **Completed:** 2026-06-05T23:54Z
- **Tasks:** 2 (both TDD: RED → GREEN)
- **Files modified:** 3 (app.py, ui/state.py, tests/test_app.py)

## Accomplishments
- "Fetch latest results" button mirrors the odds button exactly — lazy-imports `scripts.fetch_results` inside the click branch only, persisted-outcome stash survives `st.rerun()`, never crashes the app (fail-soft).
- `_prefill_results_into_locked` projects each FINISHED row to `(round_idx, winner, loser)` (loser recovered from the sorted `match` tuple) and routes it through the SAME `legal_pairings_for_round` → `validate_lock` → `add_lock` path a manual lock uses — illegal fetched locks rejected with the existing reason, KEY_LOCKED untouched.
- The three plan-checker fixes all landed with passing tests: (1) `fetched_at` threaded into the cache key so a new fetch timestamp forces a MISS; (2) `_stage_int_for` canonical filter so `int 1` vs `"stage1"` fires (no silent `1 == "stage1"` no-prefill); (3) validate-before-remove atomicity so an engine-illegal fetched lock preserves the manual lock.
- Conflict-confirm is loud + explicit (`st.warning` diff with HTML-escaped names + an "Apply fetched result" button); provenance (auto vs manual) and `_meta.fetched_at` staleness surfaced via the existing `fmt_age`/`is_stale`.

## Task Commits

Each task was committed atomically (both TDD; RED tests + GREEN wiring in one commit per task):

1. **Task 1: fetch-results button + pre-fill via validate_lock + fetched_at in cache key + _stage_int_for filter (RES-02, RES-04)** — `29d09b7` (feat)
2. **Task 2: atomic conflict-confirm + provenance/staleness (RES-03)** — `edf49be` (feat)

**Plan metadata:** (this SUMMARY + STATE/ROADMAP) committed separately.

## Files Created/Modified
- `app.py` — fetch-results button (lazy import); `_stage_int_for` canonical str→int stage helper; `_row_to_pending` row projection; `_prefill_results_into_locked` (the RES-02 pre-fill returning the results `fetched_at`); `_combined_fetched_at` (folds odds+results timestamps into the one cache-key slot); `_apply_fetched_conflict` (atomic validate-first swap); `_render_results_conflict` (loud confirm UX); `_render_results_provenance` (auto/manual + staleness); `_RESULTS_FETCHED_AT` module global; pre-fill called at the top of the `with main:` block; `fetched_at` threaded through `_run_or_serve` + `_live_anchor`.
- `ui/state.py` — `KEY_RESULTS_OUTCOME`, `KEY_PENDING_RESULT_CONFLICT`, `KEY_LOCK_PROVENANCE` (with doc comments mirroring the existing KEY_* blocks).
- `tests/test_app.py` — 7 new AppTests (RES-02/03/04) + `_results_cache`/`_finished_row`/`_patch_results`/`_ss_get` helpers.

## Decisions Made
- Reconciled to 06-02's existing int `_meta.stage` representation rather than introducing a second mapping — `_stage_int_for` is byte-equivalent to `scripts.fetch_results._stage_number` (the plan's explicit "reconcile to that ONE" directive).
- Folded both odds and results `fetched_at` into the single existing cache-key slot via `_combined_fetched_at` (a tuple `(odds_ts, results_ts)`), avoiding any change to the cache-key tuple width or to `optimize_cached`'s splatted param order.
- Kept the conflict gate in the app/UX layer beside `validate_lock` (a manual-vs-fetched conflict is a UX gate, not an engine illegality) — zero engine edit.
- On a rejected (engine-illegal) confirm, the pending conflict stays stashed and the manual lock is preserved; only a legal confirm clears the pending and performs the swap.

## Deviations from Plan

None — plan executed exactly as written. All three load-bearing fixes were implemented as specified, each with the test the plan named. No bugs, missing critical functionality, blocking issues, or architectural changes required auto-handling during execution.

One in-test correction (not a plan deviation): the initial Task-2 tests used `at.session_state.get(...)`, but AppTest's `SessionState` proxy is subscript-only (no `.get()`). Added an `_ss_get(at, key, default)` test helper — a test-harness accommodation, not an app or plan change. The app code's `st.session_state.get(...)` is the public proxy and is correct (used throughout the existing app).

## Issues Encountered
- AppTest `SessionState` has no `.get()` — fixed in the test layer via `_ss_get` (subscript + presence check), matching how every existing test reads `at.session_state`.

## User Setup Required
None — no external service configuration required. The seam is fully fail-soft: no results cache / no key → manual entry still works with a banner. Live Cologne provider slugs/endpoints remain a deferred event-time `/browse` verify (carried from 06-03), not a build blocker.

## Next Phase Readiness
- Phase 6 (Multi-stage scaffold + live-results seam) is COMPLETE: 4/4 plans shipped. Stage 1 is usable for live result-locking from fetched results today (the user's stated priority).
- GATE-01 green; full suite green at 147 (140 baseline + 7 new). Zero engine edits across the plan (`git diff` touches no `engine/*.py`).
- Ready for Phase 7 (Stage 2 + inter-stage seeding chain): the results seam + `stage_id` cache key + per-stage state are all in place; `_prefill_results_into_locked` and `scripts.fetch_results.main(stage_id=...)` already accept any stage.

## Self-Check: PASSED

- `app.py` modified — FOUND (contains `_stage_int_for`, `_prefill_results_into_locked`, `_apply_fetched_conflict`).
- `ui/state.py` modified — FOUND (`KEY_RESULTS_OUTCOME`, `KEY_PENDING_RESULT_CONFLICT`, `KEY_LOCK_PROVENANCE`).
- `tests/test_app.py` modified — FOUND (7 new tests, all passing).
- Commit `29d09b7` (Task 1) — FOUND in `git log`.
- Commit `edf49be` (Task 2) — FOUND in `git log`.
- GATE-01 (`tests/test_backtest_budapest_2025.py`) — GREEN.
- Full suite `uv run pytest -q` — 147 passed.
- No engine edits — `git diff --name-only HEAD~2 HEAD -- engine/*.py` is empty.

---
*Phase: 06-multi-stage-scaffold-live-results-seam*
*Completed: 2026-06-05*
