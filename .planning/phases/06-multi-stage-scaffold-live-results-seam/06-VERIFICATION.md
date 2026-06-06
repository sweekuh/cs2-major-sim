---
phase: 06-multi-stage-scaffold-live-results-seam
verified: 2026-06-05T22:00:00Z
status: passed
score: 8/8 must-haves verified
overrides_applied: 0
post_review_fixes: 7 findings resolved (2 HIGH/2 MED/3 LOW); suite 147→154
---

# Phase 6: Multi-stage scaffold + live-results seam — Verification Report

**Phase Goal:** Make the app multi-stage-aware WITHOUT breaking the engine freeze, and stand up the fail-soft live-results auto-ingest seam — so switching stages never serves another stage's cached numbers, and finished Stage-1 series can auto-pre-fill the `locked` set today (the same fetched results are the Phase-7 seeding chain's input).
**Verified:** 2026-06-05
**Status:** passed
**Re-verification:** No — initial verification

> **Post-verification code review (advisory, [06-REVIEW.md](06-REVIEW.md)):** a deep adversarial pass found 7 silent defects in the live-results *application* layer (the load-bearing seams — cache key, freeze, validate-before-remove, secret handling — all came back clean). All 7 were fixed test-first and committed (`76e2e4f`…`a5d1414`); suite 147→154, GATE-01 still green. Most consequential: **HI-01** — the single-pass prefill silently dropped later-round rows when the bo3.gg feed is reverse-chronological, which would have fed the Phase-7 seeding chain incomplete results; now sorted by `round_idx` at both write and read time with a multi-round reverse-order regression test.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | STG-01: `load_stage(path)` loads per-stage fixtures and returns `(teams, cfg)` without touching the frozen `load_teams` path | VERIFIED | `engine/teams.py` lines 175–202: `load_stage` is a pure sibling below the frozen block. `tests/test_teams_load_stage.py` 4 tests pass; GATE-01 stays green. |
| 2 | STG-04 (correctness gate): `stage_id` is a real leading positional in BOTH `run_mc_cached` and `optimize_cached`; cross-stage cache entries are never shared | VERIFIED | `ui/cache.py:73–96` and `:100–127`: `stage_id` is the first parameter in both; both bodies call `load_stage(_path_for_stage(stage_id))`; zero `load_teams()` calls remain. `test_stage_id_in_cache_key` PASS; `test_stage_switch_isolates_cache` PASS. |
| 3 | STG-05: Per-stage `[INFERRED]`-seed banner with per-stage confirm state; Stage 1 (confirmed) shows no banner; Stage 2/3 show the warning; confirming one stage does not affect another | VERIFIED | `app.py:201` uses `seeds_key = f"seeds_confirmed_{stage_id}"` seeded from `read_seeds_confirmed(_path_for_stage(stage_id))`. `test_per_stage_seed_banner` PASS. Stage 1 fixture `seeds_confirmed: true`, stage 2/3 `false`. |
| 4 | GATE-01 freeze: `load_teams`/`_DEFAULT_FIXTURE`/`_validate_fixture` byte-unchanged; Budapest backtest green; `load_teams_unchanged` freeze-regression green | VERIFIED | Git diff for `engine/teams.py` in commit `9a399f7` shows zero deletions in the frozen range (lines 74–140); only additive sibling functions. `test_backtest_budapest_2025`: 3 passed. `test_load_teams_unchanged`: passed. |
| 5 | RES-01/04: `ui/results_loader.py` imports only `json`+`pathlib`; `load_results_cache` returns `None` on missing/malformed/wrong-version cache; no crash; first run needs no results source | VERIFIED | `ui/results_loader.py` imports: `json`, `pathlib` only. `python -c "import ui.results_loader; 'httpx' not in sys.modules"` confirmed. `test_results_cache_failsoft` 5 branches PASS. |
| 6 | RES-01/05: Fetcher is FINISHED-only; slug-first join via `data/team_aliases.json`; unresolved team dropped, never mis-joined; httpx lazy-imported inside live-fetch helper only | VERIFIED | `scripts/fetch_results.py:273` has the sole `import httpx` inside `_live_fetch`. `_FINISHED = {"finished", "settled"}` filter present. `_resolve_team` is slug-first then `resolve_id` fallback then `None`. `test_finished_fixture_parses` and `test_unresolved_team_fails_soft` PASS. |
| 7 | RES-02: Fetched FINISHED results pre-fill `KEY_LOCKED` via the EXISTING `validate_lock` path; `_meta.fetched_at` threads into the cache key; active-stage filter uses `_stage_int_for` (no raw `1 == "stage1"` comparison) | VERIFIED | `app.py:860–918`: `_prefill_results_into_locked` routes every row through `legal_pairings_for_round` → `validate_lock` → `add_lock`. `_stage_int_for` defined at line 151 using `_STAGE_NUMBERS`; `grep '1 == "stage1"'` returns zero. `_combined_fetched_at` folds results timestamp alongside odds timestamp. `test_fetched_results_prefill_locked`, `test_fetched_at_refires_resim` PASS. |
| 8 | RES-03: Conflict with a manual lock requires explicit confirm; validate-before-remove is atomic; engine-illegal fetched lock leaves manual lock intact; provenance (auto/manual) and staleness (`_meta.fetched_at`) surfaced | VERIFIED | `app.py:935–975`: `_apply_fetched_conflict` builds prospective copy without the manual entry, calls `validate_lock`, commits only on `None` return. `app.py:978–1053`: `_render_results_conflict` + `_render_results_provenance`. `test_fetch_conflict_requires_confirm`, `test_conflict_confirm_validates_before_remove`, `test_provenance_and_staleness_surfaced` PASS. |

**Score:** 8/8 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `engine/teams.py` | `load_stage` + `_validate_fixture_for_size` siblings; frozen path untouched | VERIFIED | Siblings at lines 150–202; frozen block (lines 74–140) diff-clean |
| `ui/cache.py` | `stage_id` real leading positional in both cached functions; `_path_for_stage` helper; no `load_teams()` calls | VERIFIED | Lines 73–127; `grep load_teams()` returns 0 |
| `data/stage2.json` | 16-team second fixture, `seeds_confirmed: false`, distinct team set | VERIFIED | 16 teams, `seeds_confirmed: false`, placeholder names distinct from stage1 |
| `data/stage3.json` | 16-team, `seeds_confirmed: false`, `all_bo3: true` | VERIFIED | `load_stage` returns 16 teams, `cfg["all_bo3"] == True` |
| `data/playoffs.json` | 8-team, `seeds_confirmed: false` | VERIFIED | `load_stage` returns 8 teams, `cfg["size"] == 8` |
| `ui/results_loader.py` | Four-branch fail-soft loader, json+pathlib only | VERIFIED | Exact mirror of `ui/odds_loader.py`; httpx absent at import time |
| `scripts/fetch_results.py` | FINISHED-only fetcher; slug-first join; lazy httpx; atomic write | VERIFIED | `_live_fetch` is the sole httpx import site; `_FINISHED` filter; `_resolve_team` slug-first |
| `data/team_aliases.json` | Committed slug→name map; `_comment` present; NOT gitignored | VERIFIED | 16 slugs present; `_comment` key present; `.gitignore` line 16 covers `results_cache.json` not `team_aliases.json` |
| `ui/state.py` | `KEY_STAGE`, `KEY_RESULTS_OUTCOME`, `KEY_PENDING_RESULT_CONFLICT`, `KEY_LOCK_PROVENANCE` | VERIFIED | All four constants present at lines 47, 60, 67, 72 |
| `app.py` | `_stage_int_for`, `_prefill_results_into_locked`, `_apply_fetched_conflict`, fetch-results button, stage selector | VERIFIED | All five named items present at lines 151, 860, 935, 409, 308 respectively |
| `tests/test_teams_load_stage.py` | 4 tests including freeze regression | VERIFIED | 4 passed |
| `tests/test_results_loader.py` | Fail-soft loader tests | VERIFIED | 5 passed |
| `tests/test_results_fetch.py` | Recorded-fixture parse + unresolved-team tests | VERIFIED | 5 passed (after earlier fix commit) |
| `tests/test_app.py` — new Phase-6 tests | `test_stage_switch_isolates_cache`, `test_per_stage_seed_banner`, `test_fetched_results_prefill_locked`, `test_fetched_at_refires_resim`, `test_no_results_failsoft`, `test_no_network_on_rerun_with_results`, `test_fetch_conflict_requires_confirm`, `test_conflict_confirm_validates_before_remove`, `test_provenance_and_staleness_surfaced` | VERIFIED | All 9 pass |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `ui/cache.py run_mc_cached` | `engine.teams.load_stage` | `load_stage(_path_for_stage(stage_id))` — NOT `load_teams()` | WIRED | Line 93: `teams, _cfg = load_stage(_path_for_stage(stage_id))`; `load_teams()` count = 0 in `ui/cache.py` |
| `ui/cache.py optimize_cached` | `engine.teams.load_stage` | same pattern | WIRED | Line 126: `teams, _cfg = load_stage(_path_for_stage(stage_id))` |
| `app.py _cache_key_for` | `stage_id` LEADS tuple | `(stage_id, freeze_ratings(ratings), S, int(N), freeze_locked(locked), fetched_at)` | WIRED | Line 664; k[0] == stage_id confirmed by `k[4]` index tests passing |
| `app.py _prefill_results_into_locked` | `engine.live.validate_lock + legal_pairings_for_round + ui.state.add_lock` | same path as manual lock — no bypass | WIRED | Lines 908–914: `legal_pairings_for_round` → `validate_lock` → `add_lock` |
| `app.py _prefill_results_into_locked` | `_stage_int_for` | `cache_stage_int != active_stage_int` comparison, both sides ints | WIRED | Lines 878–882; `grep "_meta.*stage.*== *stage_id"` returns 0 |
| `app.py results fetched_at` | `ui/cache.py run_mc_cached` | `_combined_fetched_at` folds into `_cache_key_for` `fetched_at` slot | WIRED | Lines 921–932, 719 |
| `app.py fetch-results button` | `scripts.fetch_results.main` | lazy `from scripts.fetch_results import main` inside click branch | WIRED | Line 412; httpx never in the app import path confirmed by `test_no_network_on_rerun_with_results` |
| `ui/results_loader.py` | `data/results_cache.json` | `json.loads` + version gate, `None` on any error | WIRED | Lines 48–58; `_SUPPORTED_VERSION = 1` gate |
| `scripts/fetch_results.py join` | `odds/_match.resolve_id + data/team_aliases.json` | slug-first exact hit → `resolve_id` fallback → DROP | WIRED | `_resolve_team` function lines 118–136 |
| `app.py per-stage banner` | `ui.state.read_seeds_confirmed` | `read_seeds_confirmed(_path_for_stage(stage_id))` | WIRED | Line 206 |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `run_mc_cached` | `teams` | `load_stage(_path_for_stage(stage_id))` reads the active stage's committed fixture | Yes — validated fixture with real team/rating data | FLOWING |
| `app.py` results pre-fill | `KEY_LOCKED` | `load_results_cache()` → row projection → `add_lock` via `validate_lock` | Yes — sourced from `data/results_cache.json` (written by `scripts/fetch_results.py`) | FLOWING |
| `_cache_key_for` `fetched_at` | `_RESULTS_FETCHED_AT` | `_prefill_results_into_locked()` returns `_meta.fetched_at` ISO string | Yes — ISO-8601 UTC from the cache write time | FLOWING |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `load_stage` returns correct teams and cfg | `python -c "from engine.teams import load_stage; t,c=load_stage('data/stage1.json'); print(len(t), c['seeds_confirmed'])"` | `16 True` | PASS |
| `load_stage` handles stage3 and playoffs | `python -c "from engine.teams import load_stage; t3,c3=load_stage('data/stage3.json'); t8,c8=load_stage('data/playoffs.json'); print(len(t3), c3['all_bo3'], len(t8), c8['size'])"` | `16 True 8 8` | PASS |
| `ui/results_loader` imports no httpx | `python -c "import ui.results_loader; import sys; print('httpx' in sys.modules)"` | `False` | PASS |
| `_load_aliases` fail-soft on bad path | `python -c "from scripts.fetch_results import _load_aliases; print(_load_aliases('/bad/path') == {})"` | `True` | PASS |
| Full test suite | `uv run pytest -q` | `147 passed in 259s` | PASS |

---

## Probe Execution

Step 7c: SKIPPED (no `scripts/*/tests/probe-*.sh` probe files exist in this project; test suite is the validation contract).

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| STG-01 | 06-01 | Per-stage fixture load via `load_stage(path)` wrapper; GATE-01 frozen | SATISFIED | `engine/teams.py` load_stage sibling; GATE-01 green; `test_load_teams_unchanged` green |
| STG-04 | 06-01 | `stage_id` real leading positional in BOTH cache functions; no cross-stage stale-serve | SATISFIED | `ui/cache.py`; `test_stage_switch_isolates_cache`; `test_stage_id_in_cache_key`; `k[4]` index tests pass |
| STG-05 | 06-02 | Per-stage `[INFERRED]`-seed banner; confirming one stage does not dismiss another | SATISFIED | `app.py` `seeds_key = f"seeds_confirmed_{stage_id}"`; `test_per_stage_seed_banner` |
| RES-01 | 06-03 | Fetch FINISHED series from provider ladder; read-only cache; httpx not in app import path | SATISFIED | `scripts/fetch_results.py`; `ui/results_loader.py`; httpx absent from app import path confirmed |
| RES-02 | 06-04 | Fetched results pre-fill `KEY_LOCKED`; `fetched_at` in cache key re-fires re-sim; canonical stage filter | SATISFIED | `_prefill_results_into_locked`; `_stage_int_for`; `_combined_fetched_at`; 4 RES-02 AppTests |
| RES-03 | 06-04 | Conflict with manual lock → explicit confirm; atomic validate-before-remove; provenance + staleness surfaced | SATISFIED | `_apply_fetched_conflict`; `_render_results_conflict`; `_render_results_provenance`; 3 RES-03 AppTests |
| RES-04 | 06-03/04 | Fail-soft: missing key/network/source → manual entry + banner, never crash; first run works | SATISFIED | `load_results_cache` four-branch None; `test_no_results_failsoft`; `test_no_network_on_rerun_with_results` |
| RES-05 | 06-03 | Provider team join slug-first via `data/team_aliases.json`; unresolved → drop + loud, never mis-locked | SATISFIED | `_resolve_team`; `_load_aliases`; `test_unresolved_team_fails_soft` |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `scripts/fetch_results.py` | 268, 285, 293 | `[VERIFY AT EVENT TIME]` — live provider endpoint paths and Cologne tournament slug | Info | Intentional; these are comments marking the event-time `/browse` verification task that is explicitly deferred per design (not a gap — the recorded-fixture test path exercises the full seam) |
| `data/team_aliases.json` | 2 | `[PLACEHOLDER — VERIFY AT EVENT TIME]` in `_comment` | Info | Intentional; the prompt explicitly states "live Cologne provider slug + real team_aliases.json seeding is an intentional DEFERRED event-time /browse verify" |

No `TBD`, `FIXME`, or `XXX` markers in any Phase-6-modified file. No unreferenced debt markers. The `[VERIFY AT EVENT TIME]` comments are tracked qualitative notes, not code debt — they reference the `/browse` pass explicitly documented in `06-03-PLAN.md` and `06-04-PLAN.md` as a post-event-time action.

---

## Load-Bearing Gate Verification (per prompt)

**Gate 1 — STG-04 cache key correctness:**
- `stage_id` is the first positional parameter in `run_mc_cached(stage_id, ratings_key, S, N, locked_key)` at `ui/cache.py:74`.
- `stage_id` is the first non-underscore positional in `optimize_cached(_result, stage_id, ratings_key, S, N, locked_key, fetched_at)` at `ui/cache.py:100`.
- Neither uses the `_arg` underscore escape for `stage_id` — it is a real key arg in both.
- Both bodies call `load_stage(_path_for_stage(stage_id))` — confirmed no `load_teams()` calls in `ui/cache.py`.
- `test_stage_switch_isolates_cache`: asserts that keys from Stage 1 and Stage 2 runs are disjoint (`stage1_keys & stage2_keys == set()`). PASS.
- `test_stage_id_in_cache_key`: asserts two stages return different Results; same stage is a cache HIT. PASS.

**Gate 2 — GATE-01 engine freeze:**
- Git diff `9a399f7` (the engine-touching commit) shows +68 lines, 0 deletions in `engine/teams.py`. The frozen block (lines 74–140: `_validate_fixture`, `_teams_from_rows`, `load_teams`, `_DEFAULT_FIXTURE`) was not edited.
- `test_backtest_budapest_2025`: 3 passed (Budapest 2025 round-by-round pairings reproduced exactly).
- `test_load_teams_unchanged`: passed (byte-identical 16-team Stage-1 list after sibling addition).

**Gate 3 — RES-02 int-vs-str filter:**
- `_stage_int_for` defined at `app.py:151` using `_STAGE_NUMBERS = {"stage1": 1, "stage2": 2, "stage3": 3, "playoffs": 4}`.
- `scripts/fetch_results._stage_number` uses the identical mapping (verified: both return `1` for `"stage1"`, `4` for `"playoffs"`).
- `grep '"_meta".*"stage".*== *stage_id'` returns 0 — no raw int-vs-str comparison anywhere.
- `test_fetched_results_prefill_locked` explicitly tests that a cache with `_meta.stage = 1` (int) fires the pre-fill when `stage_id = "stage1"` (str). PASS.
- `fetched_at` is returned by `_prefill_results_into_locked` and consumed by `_combined_fetched_at` → `_cache_key_for`. PASS.

**Gate 4 — RES-03 conflict atomicity:**
- `_apply_fetched_conflict` (`app.py:935`) builds `prospective` list WITHOUT mutating session_state, runs `legal_pairings_for_round` + `validate_lock` on the prospective, and only commits the swap on `validate_lock == None`.
- On a non-None reason: `st.error(reason); return` — `KEY_LOCKED` and provenance are untouched.
- `test_conflict_confirm_validates_before_remove` asserts the manual lock survives an engine-illegal fetched-lock confirm. PASS.

**Gate 5 — RES-01/04/05 fail-soft:**
- `ui/results_loader.py`: imports `json` and `pathlib` only. Confirmed with `python -c "import ui.results_loader; import sys; print('httpx' in sys.modules)"` → `False`.
- `load_results_cache(None)` returns `None` (missing file) — confirmed by test.
- `_resolve_team` returns `None` when both slug-first and `resolve_id` fail — the caller logs and `continue`s (no fabrication).
- `test_no_results_failsoft`: app renders and runs with no `results_cache.json`. PASS.
- `test_no_network_on_rerun_with_results`: httpx booby-trapped, rerun touches no network. PASS.

---

## Human Verification Required

**1. Stage selector UI rendering**
- **Test:** Run `uv run streamlit run app.py`, switch the Stage selector between "Stage 1" and "Stage 2"
- **Expected:** Team table changes to the selected stage's teams; the "Seeds are INFERRED" banner appears for Stage 2 but not Stage 1; per-team probs never flash the prior stage's numbers between switches
- **Why human:** Visual rendering and stage-transition UX cannot be asserted by AppTest (AppTest does not render Streamlit widgets visually)

**2. Fetch-results button UX (no live data yet)**
- **Test:** Run the app, click "Fetch latest results"
- **Expected:** Spinner shows "Fetching finished results…"; outcome stash renders "No finished results yet…" or succeeds silently; app does not crash; no httpx traceback visible
- **Why human:** Live provider endpoint response (bo3.gg) is event-time; no Cologne results posted yet; cannot test the success path without real data

**3. Conflict-confirm UX — visual review**
- **Test:** Manually lock a result in Live mode, then trigger a conflicting fetch (load a prepared `data/results_cache.json` with the opposite winner for the same pair)
- **Expected:** Loud `st.warning` diff message; "Apply fetched result" button; manual lock stays intact until confirmed; an engine-illegal confirm shows `st.error(reason)` and preserves the manual lock
- **Why human:** Cannot inject a conflicting cache and drive the Streamlit button in AppTest without custom fixtures; the automated tests cover the logic path but not the rendered diff wording

---

## Deferred Items

Items intentionally deferred by design, not gaps:

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | Live Cologne provider slug + `data/team_aliases.json` real slugs | Event-time `/browse` verify (post-event action) | Phase 6 PLAN and RESEARCH explicitly mark `[VERIFY AT EVENT TIME]`; placeholder slugs are committed and the seam is fully tested with recorded fixtures |
| 2 | STG-02: Stage 2 Swiss simulation with structural invariant tests | Phase 7 | REQUIREMENTS.md traceability table; Phase 7 goal covers STG-02 + SEED-01/02/03 |
| 3 | STG-03/BO-01: Stage 3 all-Bo3 mode | Phase 8 | REQUIREMENTS.md traceability; `all_bo3` flag is carried in `data/stage3.json` and available for Phase 8 to consume |

---

## Gaps Summary

No gaps. All 8 must-haves are VERIFIED. The full test suite runs 147 tests, all passing, including GATE-01 (Budapest backtest), the STG-04 correctness gate (`test_stage_switch_isolates_cache`), and the full RES-01 through RES-05 AppTest and unit-test coverage. The engine freeze is confirmed by git diff. The only open items are the three deliberate event-time deferrals and three human visual checks above.

---

_Verified: 2026-06-05_
_Verifier: Claude (gsd-verifier)_
