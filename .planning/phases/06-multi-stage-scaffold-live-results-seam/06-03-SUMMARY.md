---
phase: 06-multi-stage-scaffold-live-results-seam
plan: 03
subsystem: api
tags: [results-seam, httpx, fail-soft, slug-join, fixtures, pandascore, bo3gg, read-only-cache]

# Dependency graph
requires:
  - phase: 06-01
    provides: engine.teams.load_stage (any-stage fixture loader) + ui.cache._path_for_stage stage map + stage_id cache key
  - phase: 05-03
    provides: the shipped odds seam mirrored byte-for-byte (ui/odds_loader.py, scripts/fetch_odds.py, odds/_match.resolve_id, recorded-fixture parse pattern)
provides:
  - "ui/results_loader.py — JSON+pathlib read-only loader for data/results_cache.json (four-branch fail-soft None; no httpx/dotenv/provider/engine import)"
  - "scripts/fetch_results.py — the ONLY results fetcher: out-of-app, lazy-httpx, FINISHED-only parse, slug-first team join (drop-on-unresolved), atomic versioned write; works for ANY stage via load_stage"
  - "data/team_aliases.json — committed {provider_slug -> internal_name} join map (placeholder slugs, event-time editable)"
  - "Frozen results-cache schema v1: {_meta:{fetched_at,version,source,stage}, results:[{match:[lo,hi],winner,round_idx,bo,status,provider_slugs}]}"
affects: [06-04, phase-07-seeding-chain]

# Tech tracking
tech-stack:
  added: []  # zero new deps — httpx already pinned/shipped from Phase 5
  patterns:
    - "Read-only fail-soft cache loader (json+pathlib only) — twin of ui/odds_loader.py"
    - "Lazy-httpx fetcher (httpx imported only inside _live_fetch) — twin of scripts/fetch_odds.py"
    - "Slug-first team join: exact team_aliases.json hit -> resolve_id name-substring fallback -> DROP-on-unresolved"
    - "Order-independent no-network test guard: booby_trapped_httpx fixture + static AST top-level-import assertion (NOT a sys.modules check)"

key-files:
  created:
    - ui/results_loader.py
    - scripts/fetch_results.py
    - data/team_aliases.json
    - tests/test_results_loader.py
    - tests/test_results_fetch.py
    - tests/fixtures/bo3gg_finished_sample.json
    - tests/fixtures/pandascore_finished_sample.json
  modified:
    - .env.example
    - .gitignore

key-decisions:
  - "Froze the STACK.md row shape {match:[lo,hi], winner, round_idx, bo, status, provider_slugs} (matches OddsQuote.match orientation + freeze_locked round-trip), _meta.version:1 like the odds cache (RESEARCH Open Q2)."
  - "Local _path_for_stage + _STAGE_FIXTURES copied into scripts/fetch_results.py rather than importing ui.cache._path_for_stage — ui.cache pulls streamlit, and the fetcher must import no streamlit/httpx at module top."
  - "No-network test guard uses the shipped booby-trap pattern (test_app_makes_no_network_on_rerun) + a static AST assertion, not sys.modules — order-independent under the full suite."

patterns-established:
  - "Results seam is a structural twin of the odds seam: loader-first (pure/testable), then fetcher (lazy-httpx, fail-soft, atomic versioned write)."
  - "Drop-on-unresolved team join: an unresolved provider team is dropped + log.warning'd, never guessed into a wrong engine id (protects the Phase-7 seeding chain)."

requirements-completed: [RES-01, RES-04, RES-05]

# Metrics
duration: 20min
completed: 2026-06-05
---

# Phase 6 Plan 03: Read-only live-results seam Summary

**Loader-first results seam — a json+pathlib read-only loader (four-branch fail-soft None) plus an out-of-app lazy-httpx fetcher that parses FINISHED-only bo3.gg/PandaScore fixtures, joins teams slug-first (drop-on-unresolved), and writes a versioned atomic results_cache.json — httpx never enters the app import path.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-06-05
- **Completed:** 2026-06-05
- **Tasks:** 2 (both TDD: RED -> GREEN)
- **Files modified:** 9 (7 created, 2 modified)

## Accomplishments
- `ui/results_loader.py`: read-only loader importing ONLY json+pathlib (no httpx/dotenv/provider/engine), four-branch fail-soft `None` (missing / malformed / non-dict / wrong-version), never raises into the UI — a structural twin of `ui/odds_loader.py`. Verified `import ui.results_loader` pulls no httpx.
- `scripts/fetch_results.py`: the single out-of-app results fetcher mirroring `scripts/fetch_odds.py` — lazy httpx (inside `_live_fetch` only; zero top-level `import httpx`), `httpx`/`httpcore` loggers forced to WARNING so `PANDASCORE_KEY` never logs, pure `_parse_bo3gg`/`_parse_pandascore` with FINISHED-only filter + slug-first join, atomic versioned write of `data/results_cache.json`, and `load_stage(_path_for_stage(stage_id))` so it works for any stage (not the frozen always-Stage-1 `load_teams`).
- Slug-first join (RES-05): each provider team SLUG resolves via an exact `data/team_aliases.json` hit first, then `odds/_match.resolve_id` name-substring fallback, then the WHOLE row is DROPPED + warned — proven both directions (a clean resolve and an unresolvable-team drop) against recorded fixtures.
- `data/team_aliases.json` committed (placeholder Cologne Stage-1 slugs, `[VERIFY AT EVENT TIME]`); `.env.example` gains a commented `PANDASCORE_KEY=` (bo3.gg primary is keyless); `.gitignore` gains `data/results_cache.json` (runtime artifact).
- GATE-01 (Budapest 2025 backtest) green; full suite **140 passed** (135 baseline + 5 new), zero regressions.

## Task Commits

Each task was committed atomically (TDD RED was folded into each task's GREEN commit since the test files are new and collect-RED before the module exists):

1. **Task 1: read-only fail-soft results loader (RES-04)** - `8c7e950` (feat)
2. **Task 2: FINISHED-only fetcher + recorded fixtures + slug-first join (RES-01/05)** - `9377bbf` (feat)
3. **Deviation fix: order-independent no-httpx test guard** - `1387a23` (fix — Rule 1, see Deviations)

**Plan metadata:** committed separately with this SUMMARY (`.planning/` is gitignored locally — code already landed in the three commits above).

## Files Created/Modified
- `ui/results_loader.py` - read-only `load_results_cache` (json+pathlib only, four-branch fail-soft None)
- `scripts/fetch_results.py` - the only results fetcher: lazy httpx, FINISHED-only parse, slug-first join, atomic versioned write
- `data/team_aliases.json` - committed `{provider_slug -> internal_name}` join map (placeholder slugs)
- `tests/test_results_loader.py` - RES-04 fail-soft + valid-v1 round-trip
- `tests/test_results_fetch.py` - RES-01/05 FINISHED parse, drop-on-unresolved, versioned write, no-httpx-in-parse-path (booby-trap + static AST)
- `tests/fixtures/bo3gg_finished_sample.json` - recorded bo3.gg FINISHED fixture (resolvable + fallback-resolve + non-finished + unresolvable + garbled rows)
- `tests/fixtures/pandascore_finished_sample.json` - recorded PandaScore FINISHED fixture (resolvable + running + unresolvable rows)
- `.env.example` - optional commented `PANDASCORE_KEY=` (FALLBACK A; bo3.gg keyless primary; first run needs no key)
- `.gitignore` - `data/results_cache.json` block (runtime artifact; `team_aliases.json`/`stageN.json` stay tracked)

## Decisions Made
- **Froze the STACK.md row shape** `{match:[lo,hi], winner, round_idx, bo, status, provider_slugs}` (over the ARCHITECTURE.md `{winner_id,loser_id}` variant) because it matches `OddsQuote.match` orientation and the `freeze_locked` round-trip — the downstream re-sim seam is then unchanged. `_meta.version:1` mirrors the odds cache so a future bump is a deliberate loader change.
- **Copied `_path_for_stage` + `_STAGE_FIXTURES` locally into the fetcher** rather than importing `ui.cache._path_for_stage`, because `ui.cache` imports streamlit — and the fetcher must import no streamlit (and no httpx) at module top. The local helper returns a `Path` and is byte-equivalent to the cache map.
- **Stage numbering for `_meta.stage`:** stage1->1, stage2->2, stage3->3, playoffs->4 (1-based), so the loaded cache records which stage it priced.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test order-pollution in the no-httpx guard**
- **Found during:** Task 2 (end-of-plan full-suite run)
- **Issue:** The two parse tests asserted `assert "httpx" not in sys.modules`. They PASSED in isolation but FAILED in the full suite, because an earlier test (the odds/live-fetch suite) legitimately imports httpx into `sys.modules` — so by the time the parse tests ran, httpx was already present. This is a buggy *test* assertion (order-dependent false negative), NOT a production-code defect: the fetcher's parse path is genuinely httpx-free (proven in isolation and by `import scripts.fetch_results` pulling no httpx).
- **Fix:** Replaced the `sys.modules` assertions with the shipped pattern from `tests/test_app.py::test_app_makes_no_network_on_rerun` — a `booby_trapped_httpx` fixture that monkeypatches every httpx network entrypoint (`get`/`post`/`request`/`Client`/`AsyncClient`/`stream`) to RAISE, proving the parse path never CALLS httpx — plus a new static `test_httpx_is_lazy_not_top_level` that AST-parses the fetcher source and asserts no top-level `import httpx` (lazy inside `_live_fetch` only). Both are order-independent.
- **Files modified:** tests/test_results_fetch.py
- **Verification:** Full suite 140 passed (was 2 failed), GATE-01 green; the 5 new tests pass both in isolation and under the full suite.
- **Committed in:** `1387a23` (separate fix commit, not amended into the task commit)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug — in test code, not production)
**Impact on plan:** No scope change and no production-code change. The fix hardened the no-network guard to the shipped, order-independent pattern. The slice landed exactly as planned otherwise.

## Issues Encountered
None beyond the test-ordering bug above (documented as a Rule 1 deviation).

## `[VERIFY AT EVENT TIME]` markers (DEFERRED — not build blockers)
These are data/endpoint values held for the event-time gstack `/browse` pass once Cologne fixtures post (RESEARCH A1/A2). The seam is built + tested against RECORDED fixtures now; the drop-on-unresolved path keeps every one of these fail-soft:
- `data/team_aliases.json` — placeholder Cologne Stage-1 provider slugs; seed the REAL 16 Stage-1 slugs at the `/browse` verify. The map is editable; an unresolved team drops + warns, never a fabricated lock.
- `scripts/fetch_results.py` `_live_fetch` — the live bo3.gg + PandaScore endpoint paths, headers, filter params, and the Cologne **tournament slug/id** are reconciled at the `/browse` pass. The live branch filters by tournament dynamically (never a hardcoded match id) and degrades to `[]` rather than guessing.
- The recorded fixtures' field names are `[PLACEHOLDER SHAPE — VERIFY AT EVENT TIME]` (handcrafted to the documented provider shapes); reconcile against the live responses at the same pass.

## User Setup Required
None to ship — the seam is fail-soft and the first run (plus all tests) needs NO key. Optional: a free `PANDASCORE_KEY` in `.env` enables the PandaScore FALLBACK A; bo3.gg is the keyless primary.

## Next Phase Readiness
- **06-04** can now wire the read-only loader into the app (the "Fetch latest results" button lazy-imports `scripts.fetch_results.main`; the app reads `data/results_cache.json` via `ui/results_loader.load_results_cache` and pre-fills `locked` through the existing `engine/live.py` validate/prefix contract). httpx stays out of the app import path — the 06-04 app-import guard (`test_no_network_on_rerun_with_results`) extends the booby-trap discipline established here.
- **Phase 7** (seeding chain) consumes the fetched FINISHED results as the locked set; the slug-first drop-on-unresolved join is the load-bearing protection against a mis-join corrupting the inter-stage seed derivation.

## Self-Check: PASSED
- All 7 created files exist on disk (verified).
- All 3 commits exist in git history (`8c7e950`, `9377bbf`, `1387a23`).
- `data/results_cache.json` is gitignored and NOT tracked; `data/team_aliases.json` IS tracked.
- Full suite 140 passed, GATE-01 green.

---
*Phase: 06-multi-stage-scaffold-live-results-seam*
*Completed: 2026-06-05*
