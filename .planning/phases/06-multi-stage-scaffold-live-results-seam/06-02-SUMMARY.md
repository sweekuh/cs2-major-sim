---
phase: 06-multi-stage-scaffold-live-results-seam
plan: 02
subsystem: ui
tags: [streamlit, multi-stage, seed-banner, fixtures, stg-05, apptest, fail-soft]

# Dependency graph
requires:
  - phase: 06-multi-stage-scaffold-live-results-seam
    plan: 01
    provides: "stage selector + KEY_STAGE session key, stage_id threaded through both cache wrappers, engine.teams.load_stage(path) + ui.cache._path_for_stage(stage_id), data/stage1.json + data/stage2.json"
  - phase: 02-ui-shell
    provides: "the _render_header_strip INFERRED-seed banner + reconcile expander + confirm toggle, ui.state.read_seeds_confirmed(path) (already path-parameterized, fail-safe to False), KEY_SEEDS_CONFIRMED, trust_badge_state"
provides:
  - "Per-stage [INFERRED]-seed banner (STG-05): the warning/reconcile/confirm toggle is scoped to the active stage_id via seeds_key=f'seeds_confirmed_{stage_id}', seeded from that stage's own fixture via read_seeds_confirmed(_path_for_stage(stage_id)) — confirming one stage cannot dismiss another's banner"
  - "data/stage3.json: 16-team Stage-3 fixture (committed), seeds_confirmed:false, carries an inert stage.all_bo3 flag Phase 8 consumes (unused this phase)"
  - "data/playoffs.json: 8-team playoff fixture (committed, size:8), seeds_confirmed:false, not simulated until Phase 9"
  - "tests/test_app.py::test_per_stage_seed_banner: the per-stage banner regression (Stage 1 no banner / Stage 2 banner + distinct seeds_confirmed_stage2 toggle key)"
affects: [stage-2-seeding-chain, stage-3-bo3, playoff-bracket, live-results-ingest]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-stage session key: f'seeds_confirmed_{stage_id}' scopes the seed-confirm banner to the active stage, seeded once per stage from that stage's own committed fixture flag (read-only, fail-safe to False)"
    - "Inert carried fixture flag: stage.all_bo3 ships in data/stage3.json now but is consumed only by Phase 8 — load_stage's {**stage} spread surfaces it in cfg with zero behavior change this phase"

key-files:
  created:
    - "data/stage3.json"
    - "data/playoffs.json"
  modified:
    - "app.py"
    - "ui/state.py"
    - "tests/test_app.py"

key-decisions:
  - "The banner is keyed on the module-global stage_id (read from session_state[KEY_STAGE], same active-stage source Slice 1 established) — the reconcile rows already iterate the per-stage `teams` globals rebound in Slice 1, so they show the active stage's seed→team rows automatically."
  - "stage.all_bo3 lives INSIDE the fixture's `stage` block so load_stage's `{**stage}` spread carries it into cfg with no loader change; it is documented as an inert Phase-6 flag (Phase 8 reads it for BO-01)."
  - "playoffs.json omits the Swiss advance_at_wins/eliminate_at_losses fields (a single-elim bracket has no Swiss thresholds); only stage.size:8 is needed and load_stage validates the 8-seed set against it."
  - "Kept the legacy KEY_SEEDS_CONFIRMED constant in ui/state.py as the documented base name (the live key is now per-stage) rather than deleting it — removing a public state constant is out of this slice's scope and it harms nothing."

patterns-established:
  - "Per-stage banner scoping: any per-stage confirm/dismiss UI state derives its session key from the active stage_id (f'{base}_{stage_id}') and seeds from that stage's own committed fixture — never a single shared key that one stage could flip for all."

requirements-completed: [STG-05]

# Metrics
duration: 13min
completed: 2026-06-05
---

# Phase 6 Plan 02: Per-stage [INFERRED]-seed banner + stage3/playoffs fixtures (Slice 2 — STG-05) Summary

**Made the [INFERRED]-seed banner PER-STAGE — keyed on `f"seeds_confirmed_{stage_id}"` and seeded from each stage's own committed fixture flag, so Stage 1 (confirmed) shows no banner while Stage 2/3 (unconfirmed) show the loud warning and confirming one stage cannot dismiss another's — and shipped the remaining committed `data/stage3.json` (size 16, inert `all_bo3` flag for Phase 8) + `data/playoffs.json` (size 8) so all four stages load via `load_stage`.**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-06-05T22:54:56Z
- **Completed:** 2026-06-05T23:07:35Z
- **Tasks:** 2 (Task 1 fixtures, Task 2 per-stage banner — TDD)
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments
- **STG-05 per-stage banner:** `app.py`'s `_render_header_strip` now scopes the seed-confirm state to the active `stage_id` via `seeds_key = f"seeds_confirmed_{stage_id}"`, seeded on first load of each stage from its OWN fixture via `read_seeds_confirmed(_path_for_stage(stage_id))` (read-only, fail-safe to False). The warning + reconcile expander + confirm toggle all bind to the per-stage key — confirming Stage 2 does not touch Stage 1's badge, and vice versa.
- **Two committed fixtures:** `data/stage3.json` (16 teams, `seeds_confirmed:false`, `stage.all_bo3:true` carried inert for Phase 8) and `data/playoffs.json` (8 teams, `size:8`, `seeds_confirmed:false`, not simulated until Phase 9) — both load cleanly through `engine.teams.load_stage`, neither gitignored.
- **TDD regression:** `tests/test_app.py::test_per_stage_seed_banner` proves the end-to-end guarantee (Stage 1 → no "Seeds are INFERRED" warning; Stage 2 → the warning + a distinct `seeds_confirmed_stage2` toggle key). RED first (Stage 2 wrongly showed no banner under the old single key), then GREEN.
- **GATE-01 stayed green at every task; full suite green at 135 passed** (134 baseline from 06-01 + 1 new), no regressions; no engine edits (UI/state + fixtures only).

## Task Commits

Each task committed atomically to `master`:

1. **Task 1: stage3 + playoffs committed fixtures (STG-05)** - `1a65a08` (feat)
2. **Task 2 (TDD): per-stage seed banner + confirm toggle (STG-05)**
   - RED: `18c7974` (test) — failing `test_per_stage_seed_banner`
   - GREEN: `b837a82` (feat) — per-stage `seeds_key` banner + the `test_seed_banner_dismissable` key update

_Note: STATE.md / ROADMAP.md / this SUMMARY live under the gitignored `.planning/` tree (the project keeps planning LOCAL-ONLY); they are written to disk but, if `git add`/commit skips them as gitignored, that is EXPECTED — the code commits above are the deliverable._

## Files Created/Modified
- `data/stage3.json` — NEW 16-team Stage-3 fixture, `seeds_confirmed:false`, `stage.all_bo3:true` (inert this phase; Phase 8 consumes it for BO-01). Placeholder `[INFERRED]` names (real seeds derive via the Phase-7 inter-stage Buchholz chain).
- `data/playoffs.json` — NEW 8-team playoff bracket fixture, `stage.size:8`, `seeds_confirmed:false`, no Swiss threshold fields. Placeholder `[INFERRED]` names (real seeds derive from the final Stage-3 Buchholz in Phase 9; not simulated this phase).
- `app.py` — `_render_header_strip`: replaced the single `KEY_SEEDS_CONFIRMED` banner state with the per-stage `seeds_key = f"seeds_confirmed_{stage_id}"`, seeded from `read_seeds_confirmed(_path_for_stage(stage_id))`; the warning/expander/toggle bind to the per-stage key. Dropped the now-dead `KEY_SEEDS_CONFIRMED` import.
- `ui/state.py` — documented `KEY_SEEDS_CONFIRMED` as the legacy base name (the live key is now per-stage); no behavior change.
- `tests/test_app.py` — ADDED `test_per_stage_seed_banner`; updated `test_seed_banner_dismissable` to look up the toggle by the per-stage key `seeds_confirmed_stage1` (the default-stage key after the STG-05 rename).

## Decisions Made
- **Banner keyed on the module-global `stage_id`** (read from `session_state[KEY_STAGE]`, the same active-stage source Slice 1 established). `_render_header_strip` is a no-arg function reading that global; the reconcile rows already iterate the per-stage `teams` globals that Slice 1 rebinds, so they render the active stage's seed→team rows with no further change.
- **`all_bo3` placed inside the fixture `stage` block** so `load_stage`'s `{**stage}` spread surfaces it in `cfg` with zero loader change. Verified `cfg["all_bo3"]` is truthy for stage3 while nothing in Phase 6 reads it (inert until Phase 8 / BO-01).
- **`playoffs.json` omits Swiss threshold fields** (`advance_at_wins`/`eliminate_at_losses`) — a single-elim bracket has no Swiss thresholds; `load_stage` validates the 8-seed set against `stage.size:8` and that suffices.
- **Kept the legacy `KEY_SEEDS_CONFIRMED` constant** in `ui/state.py` (now documented as the base name) rather than deleting a public state constant — out of this slice's scope, and harmless.

## Deviations from Plan

None affecting scope — the plan executed as written. One **mechanical test-update consequence** of the per-stage key rename is worth recording (it changed an existing *test*, not the source contract, and the plan's acceptance criteria explicitly require the full `test_app.py` to stay green through the banner change):

### Auto-fixed Issues

**1. [Rule 1 - Blocking] `test_seed_banner_dismissable` re-keyed to the per-stage toggle key**
- **Found during:** Task 2 (GREEN — running the full `tests/test_app.py`)
- **Issue:** The STG-05 rename makes the Stage-1 confirm toggle key `seeds_confirmed_stage1` instead of the old `seeds_confirmed`. The pre-existing `test_seed_banner_dismissable` looked the toggle up by `KEY_SEEDS_CONFIRMED` (`"seeds_confirmed"`), so it raised `StopIteration` (no widget with that key) — a direct, expected consequence of the per-stage key the plan mandates.
- **Fix:** Updated `test_seed_banner_dismissable` to look up the toggle by the default-stage per-stage key `seeds_confirmed_stage1` (and assert `session_state["seeds_confirmed_stage1"] is True` after toggling). Source contract unchanged; the test now reflects the per-stage reality. This is the same class of mechanical test update as Slice 1's `k[3]→k[4]` re-index.
- **Files modified:** `tests/test_app.py` (test only — zero source change from this fix)
- **Verification:** `test_seed_banner_dismissable` + `test_per_stage_seed_banner` both green; full `tests/test_app.py` 40 passed; full suite 135 passed; GATE-01 3 passed.
- **Committed in:** `b837a82` (Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 blocking — a mechanical existing-test re-key forced by the per-stage key rename the plan specifies). **Impact on plan:** None on deliverables. The source per-stage banner matches the plan exactly; only one existing test was updated to the new per-stage key, exactly as the plan's "an existing Stage-1 banner test still passes" criterion anticipates. No scope creep.

## Issues Encountered
- **Existing single-key banner test broke on the per-stage rename** — resolved as above (test re-keyed to `seeds_confirmed_stage1`, source unchanged). This is the only substantive consequence of making the banner per-stage: any test that bound the toggle by the old shared key must move to the active stage's `seeds_confirmed_{stage_id}` key.
- **Slow AppTest suites** — the full app/AppTest suites run ~2–4 min under the no-runtime cache storage manager; ran them to completion (no `&`, foreground) and read the tail. No flakiness observed.

## Known Stubs
The `[INFERRED]` placeholder team names + ratings in `data/stage3.json` and `data/playoffs.json` are **intentional, documented stubs** — the real seeds DERIVE downstream (Stage 3 from the Stage-2 final via the Phase-7 inter-stage Buchholz chain; the 8 playoff teams from the final Stage-3 Buchholz in Phase 9). The whole point of STG-05 is that each fixture ships `seeds_confirmed:false`, so the per-stage `[INFERRED]`-seed banner is the LOUD in-app signal that these are placeholders — they never silently masquerade as real bracket data. Each file's `_comment` states the derivation source and the phase that fills it. These do not block the plan's goal (a per-stage banner that persists until each stage is positively confirmed) — they are exactly what the banner exists to flag.

## Threat surface scan
No new security-relevant surface. Both new fixtures are read only by `engine.teams.load_stage`, which validates each against its OWN `stage.size` via `_validate_fixture_for_size` (a wrong seed count fails loud — T-06-04, pre-registered `mitigate`). `stage.all_bo3` is an inert carried flag (no behavior depends on it this phase). The per-stage banner reads `read_seeds_confirmed(_path_for_stage(stage_id))` read-only, fail-safe to False (banner shows) on any error — never mutating the fixture or the engine (T-06-05, pre-registered `accept`; a false-negative banner is the safe failure). No network, no new endpoints, no auth path, no new packages (Phase 6 installs zero — T-06-SC). No new threat flags.

## Next Phase Readiness
- All four stages now load via `load_stage` (`stage1`/`stage2` from Slice 1; `stage3`/`playoffs` from this slice), each carrying its own `seeds_confirmed` flag and showing its own per-stage banner. The `_STAGE_FIXTURES` map in `ui/cache.py` (already referencing `stage3.json`/`playoffs.json` since Slice 1) now resolves to real files.
- `data/stage3.json` carries the inert `all_bo3:true` flag in `cfg` ready for Phase 8 (BO-01) to read; `data/playoffs.json` (size 8) is ready for Phase 9's single-elim sim.
- Deferred (not blockers, per the plan): the live-results fetch/loader seam (RES-01..05) is the remaining Phase 6 work; the real Stage-2/3/playoff qualifier seeds derive in Phases 7/9. The stage selector still lists only Stage 1 / Stage 2 (`_STAGE_LABELS` in `app.py`) — surfacing Stage 3 / Playoffs in the selector is a later-slice/phase wiring decision, not a gap in STG-05 (the banner mechanism is per-stage for ALL four fixtures already).
- DEFERRED manual eyeball (not a build blocker, per the plan): `uv run streamlit run app.py`, switch to Stage 2, confirm the loud INFERRED-seed banner + reconcile expander render and that Stage 1 shows no banner.

## Self-Check: PASSED

All claimed files exist on disk (`data/stage3.json`, `data/playoffs.json`, `app.py`, `ui/state.py`, `tests/test_app.py`, this SUMMARY) and all three task commits are in the git log (`1a65a08`, `18c7974`, `b837a82`). Full suite green (135 passed); `tests/test_app.py` green (40 passed); GATE-01 green (3 passed).

---
*Phase: 06-multi-stage-scaffold-live-results-seam*
*Completed: 2026-06-05*
