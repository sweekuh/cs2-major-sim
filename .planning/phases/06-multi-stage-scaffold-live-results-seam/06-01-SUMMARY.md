---
phase: 06-multi-stage-scaffold-live-results-seam
plan: 01
subsystem: ui
tags: [streamlit, cache, monte-carlo, multi-stage, stage-id, fixtures, tdd]

# Dependency graph
requires:
  - phase: 01-engine-backtest
    provides: "frozen GATE-01 pairing path (engine.teams load_teams / _validate_fixture / _DEFAULT_FIXTURE) — wrapped, never edited"
  - phase: 02-ui-shell
    provides: "@st.cache_data MC seam (ui.cache run_mc_cached / optimize_cached / freeze_locked / freeze_ratings) + ui.state KEY_* session constants"
  - phase: 04-live-resim
    provides: "live empty-locked anchor (_live_anchor) + _cache_key_for / _compute_or_serve cache-key plumbing"
  - phase: 05-odds
    provides: "fetched_at fold into the cache key (T-05-STALEBAND) — preserved alongside the new leading stage_id"
provides:
  - "engine.teams.load_stage(path) -> (teams, cfg): per-stage fixture loader validated against the JSON's own stage.size"
  - "engine.teams._validate_fixture_for_size(rows, size): size-parameterized sibling of the frozen _validate_fixture"
  - "ui.cache._path_for_stage(stage_id): stage_id -> data/stageN.json mapping (ValueError on unknown id)"
  - "stage_id as a REAL leading positional in BOTH run_mc_cached and optimize_cached (STG-04 cross-stage cache isolation)"
  - "app.py Stage 1 / Stage 2 selector (KEY_STAGE) + stage_id threaded through _cache_key_for / _compute_or_serve / _live_anchor"
  - "data/stage2.json: minimal 16-team second fixture (committed) for the cross-stage isolation test"
affects: [stage-2-seeding-chain, stage-3-bo3, playoff-bracket, live-results-ingest]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Sibling-wrapper around a frozen function (load_stage beside load_teams) — generalize without editing the frozen body"
    - "stage_id LEADS every cache key tuple; element order kept identical across _cache_key_for / run_mc_cached / optimize_cached because app.py splats *cache_key"
    - "Module-global re-bind after a selector widget runs (teams/by_seed rebind to the selected stage post-widget)"

key-files:
  created:
    - "data/stage2.json"
    - "tests/test_teams_load_stage.py"
  modified:
    - "engine/teams.py"
    - "ui/cache.py"
    - "ui/state.py"
    - "app.py"
    - "tests/test_ui_helpers.py"
    - "tests/test_app.py"

key-decisions:
  - "STG-04 unit proof uses each stage's OWN ratings + a fixture-load-differs assertion (the Swiss engine outcome is a pure function of per-seed ratings/S/N/locked/seed — team NAMES never enter the math — so identical seed-ratings yield identical counts regardless of which fixture's names load; the load-bearing isolation property is that stage_id selects a different fixture per stage)."
  - "Cache-HIT proof asserts VALUE equality, not object identity — @st.cache_data returns a deepcopy of cached values, so `is` identity is never preserved across calls."
  - "Selector options ARE the stage_ids (with format_func labels) so session_state[KEY_STAGE] always holds a stage_id that _path_for_stage consumes directly."

patterns-established:
  - "Frozen-path sibling: new loader generalizations live BELOW the frozen functions and never call them (load_stage / _validate_fixture_for_size)."
  - "stage_id-leading cache key: the whole MC+optimizer key is scoped by stage_id so a stage switch can never stale-serve the prior stage's Result."

requirements-completed: [STG-01, STG-04]

# Metrics
duration: 35min
completed: 2026-06-05
---

# Phase 6 Plan 01: Multi-stage scaffold + live-results seam (Slice 1 — the pivot) Summary

**Made the app multi-stage-aware end-to-end: a `load_stage(path)` sibling that leaves the frozen GATE-01 path byte-identical, `stage_id` threaded as a REAL leading positional into both MC + optimizer cache keys (STG-04 cross-stage isolation), and a Stage 1 / Stage 2 selector — without breaking the freeze.**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-06-05T22:25Z (approx)
- **Completed:** 2026-06-05
- **Tasks:** 4 (Task 1, Task 2, Task 3a, Task 3b)
- **Files modified:** 8 (2 created, 6 modified)

## Accomplishments
- `engine.teams.load_stage(path)` + `_validate_fixture_for_size(rows, size)` siblings — load/validate ANY per-stage fixture against its OWN declared `stage.size`, with the frozen `load_teams` / `_DEFAULT_FIXTURE` / `_validate_fixture` bodies untouched (pure-additions diff; freeze regression `test_load_teams_unchanged` green).
- `stage_id` is now a REAL leading positional in BOTH `run_mc_cached` and `optimize_cached`; both load `load_stage(_path_for_stage(stage_id))` instead of the always-Stage-1 loader — the STG-04 correctness gate against cross-stage stale-serve.
- App exposes a Stage 1 / Stage 2 selector (`KEY_STAGE`); the module `teams`/`by_seed` globals re-bind to the selected stage, and `stage_id` threads through `_cache_key_for` / `_compute_or_serve` / the live anchor `pre_key`. The optimizer splats (`optimize_cached(result, *cache_key)`) needed no change — they pick up the new leading element automatically.
- GATE-01 (Budapest 2025 backtest) stayed green at every task; the full suite is green at **134 passed** (128 baseline + 6 new), no regressions.

## Task Commits

Each task committed atomically to `master`:

1. **Task 1 (TDD): load_stage + freeze siblings (STG-01)**
   - RED: `c7aca2c` (test) — failing load_stage + freeze-regression tests
   - GREEN: `9a399f7` (feat) — load_stage + _validate_fixture_for_size siblings
2. **Task 2: stage_id in both cache keys + stage2 fixture (STG-04)** - `652abd4` (feat)
3. **Task 3a: mechanical k[3]→k[4] re-index + positional updates** - `6952b3a` (test)
4. **Task 3b (TDD): stage selector + stage_id threading + STG-04 isolation tests**
   - RED: `15d2707` (test) — STG-04 unit + app-switch isolation tests
   - GREEN: `6a5191d` (feat) — selector + _cache_key_for surgery + stage_id threading

_Note: STATE.md / ROADMAP.md / this SUMMARY live under the gitignored `.planning/` tree (the project keeps planning local-only); they are written to disk but not part of the code commits above._

## Files Created/Modified
- `engine/teams.py` — ADDED `_validate_fixture_for_size(rows, size)` + `load_stage(path)` siblings below the frozen path (no edits to frozen lines; no streamlit/httpx import).
- `ui/cache.py` — ADDED `_path_for_stage(stage_id)`; `run_mc_cached` + `optimize_cached` take `stage_id` LEADING and load `load_stage(_path_for_stage(stage_id))`.
- `ui/state.py` — ADDED `KEY_STAGE = "active_stage"`; updated the `KEY_MC_CACHE` comment to the 5-element `(stage_id, ratings_key, S, N, locked_key)` shape.
- `app.py` — ADDED Stage 1 / Stage 2 `st.selectbox` (writes `KEY_STAGE`); re-bind `teams`/`by_seed` to the selected stage; `_cache_key_for` gains leading `stage_id`; `_compute_or_serve` / run flow / `_live_anchor` thread it.
- `data/stage2.json` — NEW minimal 16-team second fixture (committed), `seeds_confirmed: false`, team set differs from stage1 so a stage switch is observable.
- `tests/test_teams_load_stage.py` — NEW STG-01 tests + the `test_load_teams_unchanged` freeze companion.
- `tests/test_ui_helpers.py` — `test_run_mc_cached_uses_frozen_seed_and_default_chunks` gains leading `"stage1"` (the `direct == cached` Stage-1-equivalence assertion preserved verbatim); ADDED `test_stage_id_in_cache_key`.
- `tests/test_app.py` — `k[3]`→`k[4]` re-index of the four LIVE cache-key tests + leading `"stage1"` in `test_locked_in_cache_key`; ADDED `test_stage_switch_isolates_cache`.

## Decisions Made
- **STG-04 unit-test proof shape (important nuance):** the Swiss engine outcome is a pure function of `(per-seed ratings, S, N, locked, seed)` — team **names** never enter the math. So `run_mc_cached("stage1", rk, …)` and `run_mc_cached("stage2", rk, …)` with the SAME seed-keyed ratings produce IDENTICAL `counts_advance` (both fixtures are seeds 1..16). The honest proof therefore: (a) two stages with their OWN fixture ratings produce different Results, and (b) `stage_id` selects a different fixture per stage (the load-bearing isolation property the optimizer/render rely on, since `optimize_cached` passes the loaded `teams` to the optimizer). This is faithful to the real app — each stage has its own teams hence its own editor/market ratings.
- **Cache-HIT asserted on VALUE, not identity:** `@st.cache_data` returns a deepcopy of cached values (proven empirically here — `is` failed even on a genuine hit), so the hit is asserted via `counts_advance` equality.
- Selector options are the stage_ids themselves (`format_func` for labels) so `session_state[KEY_STAGE]` is always a valid stage_id; the test injects `KEY_STAGE = "stage2"` directly (robust to widget type, mirroring how the LIVE tests inject `KEY_LOCKED`).

## Deviations from Plan

None affecting scope — the plan executed as written. One **test-design refinement** within Task 3b is worth recording (it changed the *test*, not the source, and stays within the plan's STG-04 intent):

### Test-design refinement (Task 3b, within plan intent)

**1. [Rule 1 - correctness of the test's premise] `test_stage_id_in_cache_key` proof reshaped**
- **Found during:** Task 3b (writing the STG-04 unit test)
- **Issue:** The plan's `<behavior>` sketched "two stages → different `counts_advance`" using a shared seed-keyed ratings dict. That assertion is FALSE given the engine ignores team names: with identical per-seed ratings + FIXED_SEED, both stages (both seeds 1..16) produce byte-identical `counts_advance`. A test asserting inequality there would be wrong, and the cache-HIT `is`-identity assertion the sketch implied also fails because `st.cache_data` returns copies.
- **Fix:** Reshaped the test to the faithful STG-04 proof: (a) each stage's OWN ratings → different Results; (b) `stage_id` selects a different fixture per stage (the actual isolation guarantee — `run_mc_cached`/`optimize_cached` load `load_stage(stage_id)`); (c) cache HIT asserted on value equality. The integration `test_stage_switch_isolates_cache` AppTest still proves the end-to-end guarantee directly: a Stage-2 run creates a `"stage2"`-leading `mc_cache` key disjoint from the `"stage1"` key.
- **Files modified:** `tests/test_ui_helpers.py` (test only — zero source change from this refinement)
- **Verification:** `test_stage_id_in_cache_key` + `test_stage_switch_isolates_cache` both green; the source `stage_id` threading is unchanged and independently proven by both.
- **Committed in:** `15d2707` (Task 3b RED) / verified green under `6a5191d`

---

**Total deviations:** 0 scope deviations; 1 test-design refinement (kept within the STG-04 must-have: "same (ratings,S,N,locked) under different stage_ids returns DIFFERENT cached Results / same stage_id is a cache HIT" — proven via fixture-load divergence + the AppTest, the parts the engine's name-independence actually permits).
**Impact on plan:** None on deliverables. The source threading matches the plan exactly; only the unit test's assertions were made faithful to the engine's name-independence. No scope creep.

## Issues Encountered
- **Engine name-independence vs. the sketched unit assertion** — resolved as above (test reshaped, source unchanged). This is the single substantive thing learned: a cross-stage divergence in `counts_advance` requires differing RATINGS, not merely differing team names; the optimizer-facing fixture load is where stage identity actually bites.
- **Background test runs** — the full app/AppTest suites are slow (~2–4 min) under the no-runtime `MemoryCacheStorageManager`; ran them in the background and polled to completion. No flakiness observed.

## Threat surface scan
No new security-relevant surface. `load_stage` reads only committed `data/stageN.json` fixtures and fails loud via `_validate_fixture_for_size` (mirrors `_validate_fixture`; T-06-01 mitigated). No network, no new endpoints, no auth path. `data/stage2.json`'s `[INFERRED]` placeholder names are an intentional, documented stub (real Stage-2 seeds derive in Phase 7) — not a data-source stub that misleads the UI.

## Next Phase Readiness
- The `stage_id`-keyed cache + `load_stage` wrapper that every later slice rides on are landed and proven (STG-04). Stage 2 (Phase 7) can now seed from a real second fixture and reuse the frozen engine through `load_stage`.
- Deferred (not blockers): the per-stage `[INFERRED]`-seed banner (STG-05), the live-results fetch/loader seam (RES-01..05), and `data/stage2.json`'s real qualifier seeds (Phase 7 inter-stage Buchholz chain). These are the remaining Phase 6 plans / Phase 7 work, not gaps in this slice.
- DEFERRED manual eyeball (not a build blocker, per the plan): `uv run streamlit run app.py`, switch Stage 1 ↔ Stage 2, confirm the team table changes and never flashes the prior stage's probs.

## Self-Check: PASSED

All claimed files exist on disk (engine/teams.py, ui/cache.py, ui/state.py, app.py, data/stage2.json, tests/test_teams_load_stage.py, 06-01-SUMMARY.md) and all six task commits are in the git log (c7aca2c, 9a399f7, 652abd4, 6952b3a, 15d2707, 6a5191d). Full suite green (134 passed); GATE-01 green (3 passed).

---
*Phase: 06-multi-stage-scaffold-live-results-seam*
*Completed: 2026-06-05*
