---
phase: 6
slug: multi-stage-scaffold-live-results-seam
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-04
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `06-RESEARCH.md` § Validation Architecture / Security Domain. The planner refines the Per-Task map (Task IDs) during planning.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + `streamlit.testing.v1.AppTest` (ships inside streamlit — no extra dep) + pure-helper unit tests |
| **Config file** | none — invoked via `uv run pytest`; `tests/conftest.py` provides shared fixtures |
| **Quick run command** | `uv run pytest tests/test_backtest_budapest_2025.py tests/test_ui_helpers.py -q` (the gate + cache-key units, ~1s) |
| **Full suite command** | `uv run pytest -q` (128-test baseline, all green 2026-06-04, GATE-01 green) |
| **Estimated runtime** | ~10–30s (AppTest runs the script headless; cap N small in tests) |

**GATE-01 is the cross-cutting exit criterion** — `tests/test_backtest_budapest_2025.py` MUST stay green for every commit. It never calls `load_teams`, so the STG-01 loader generalization is provably non-perturbing; the freeze-regression companion (`test_load_teams_unchanged`) proves it.

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/test_backtest_budapest_2025.py <the task's new test file> -q` (GATE-01 + the slice under test)
- **After every plan wave:** `uv run pytest -q` (full 128 + new tests; GATE-01 green is mandatory — UI/results work must not regress the engine)
- **Before `/gsd-verify-work`:** full suite green AND GATE-01 green
- **Max feedback latency:** ~30s

---

## Per-Task Verification Map

> Task IDs are TBD until the planner assigns them. Requirement→behavior→command rows are pre-seeded from research § Validation Architecture; every load-bearing seam has a test. Threat Ref → research § Security Domain.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | — | 1 | STG-04 | — | Same `(ratings,S,N,locked)` under two different `stage_id`s → DIFFERENT cached Results; same `stage_id` → cache HIT (same object). **Not the `_`-underscore escape.** | unit | `uv run pytest tests/test_ui_helpers.py::test_stage_id_in_cache_key -x` | ❌ W0 | ⬜ pending |
| TBD | — | 1 | STG-04 | — | Switching the active stage in the UI never shows the prior stage's probs; a stage switch creates a new `mc_cache` key carrying `stage_id` | AppTest | `uv run pytest tests/test_app.py::test_stage_switch_isolates_cache -x` | ❌ W0 | ⬜ pending |
| TBD | — | 1 | STG-01 | T-V5 | `load_stage(path)` validates against the JSON's `stage.size`, returns `(teams, cfg)`; rejects a dup/short seed set loudly | unit | `uv run pytest tests/test_teams_load_stage.py -x` | ❌ W0 | ⬜ pending |
| TBD | — | 1 | STG-01 / GATE-01 | — | **FREEZE REGRESSION:** GATE-01 green AND `load_teams()` returns the byte-identical 16-team Stage-1 list after the loader generalization | unit | `uv run pytest tests/test_backtest_budapest_2025.py tests/test_teams_load_stage.py::test_load_teams_unchanged -x` | ⚠️ GATE-01 green; freeze-companion ❌ W0 | ⬜ pending |
| TBD | — | 2 | STG-05 | — | Per-stage `[INFERRED]`-seed banner persists per stage until that stage's `seeds_confirmed` is positively flipped; reads the stage fixture read-only | AppTest + unit | `uv run pytest tests/test_app.py::test_per_stage_seed_banner -x` | ❌ W0 | ⬜ pending |
| TBD | — | 3 | RES-04 | T-V12 | `load_results_cache` returns None on missing/malformed/non-dict/wrong-version; a valid v1 cache round-trips (fail-soft, never raises) | unit | `uv run pytest tests/test_results_loader.py::test_results_cache_failsoft -x` | ❌ W0 | ⬜ pending |
| TBD | — | 3 | RES-04 | — | App renders + runs with NO results cache and NO key (manual entry works day one); no crash | AppTest | `uv run pytest tests/test_app.py::test_no_results_failsoft -x` | ❌ W0 | ⬜ pending |
| TBD | — | 3 | RES-04 | T-DoS | App makes NO network call on rerun (httpx booby-trapped) with the results seam wired | AppTest | `uv run pytest tests/test_app.py::test_no_network_on_rerun_with_results -x` | ⚠️ analogue exists; extend ❌ W0 | ⬜ pending |
| TBD | — | 3 | RES-01 | T-V5 | A recorded bo3.gg / PandaScore FINISHED fixture parses to `(match,winner,round_idx)` rows; an unparseable row is dropped, never raises | unit | `uv run pytest tests/test_results_fetch.py::test_finished_fixture_parses -x` | ❌ W0 | ⬜ pending |
| TBD | — | 3 | RES-05 | T-tamper | Slug-first join via `team_aliases.json` resolves a provider slug to the right engine id; an unresolved team is DROPPED + surfaced, never mis-locked | unit | `uv run pytest tests/test_results_fetch.py::test_unresolved_team_fails_soft -x` | ❌ W0 | ⬜ pending |
| TBD | — | 4 | RES-02 | — | Fetched FINISHED results pre-fill `KEY_LOCKED`; non-empty `locked_key` changes the cache key → conditional re-sim fires; an illegal fetched lock is rejected with the existing `validate_lock` reason string | AppTest | `uv run pytest tests/test_app.py::test_fetched_results_prefill_locked -x` | ❌ W0 | ⬜ pending |
| TBD | — | 4 | RES-03 | T-integrity | A fetched result that conflicts with a MANUAL lock requires explicit confirm (loud), never silently overwrites; provenance + `_meta.fetched_at` surfaced | AppTest | `uv run pytest tests/test_app.py::test_fetch_conflict_requires_confirm -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_teams_load_stage.py` — STG-01 (`load_stage` validate/return) + the `test_load_teams_unchanged` freeze companion
- [ ] `tests/test_results_loader.py` — RES-04 loader fail-soft (mirror `test_cache_loader_failsoft` in `test_app.py`)
- [ ] `tests/test_results_fetch.py` — RES-01/RES-05 provider-fixture parse + slug join (mirror `tests/test_odds.py` recorded-fixture pattern)
- [ ] `tests/fixtures/bo3gg_finished_sample.json` + `tests/fixtures/pandascore_finished_sample.json` — recorded FINISHED-series fixtures (mirror `tests/fixtures/kalshi_sample.json`)
- [ ] `data/stage2.json` (minimal second fixture) — so the cross-stage cache-isolation AppTest has a real second stage to switch to
- [ ] New cases in `tests/test_ui_helpers.py` / `tests/test_app.py` for STG-04 (cache isolation) + the `k[3]`→`k[4]` index updates to the existing LIVE tests
- [ ] Framework install: **none** — pytest + AppTest already present via `uv run`

*The existing GATE-01, `test_cache_loader_failsoft`, and `test_app_makes_no_network_on_rerun` are the proven templates; the new tests mirror them.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Confirm Cologne tournament slug/id on bo3.gg + PandaScore; seed `data/team_aliases.json` | RES-01 / RES-05 | Markets/fixtures not posted until ~event time; live external data | **DEFERRED to event time.** gstack `/browse` bo3.gg + PandaScore Cologne pages; record the slug/id + the 16-team slug→engine-id map into `data/team_aliases.json`. `[VERIFY AT EVENT TIME]` — not a build blocker. |
| Per-stage `[INFERRED]`-seed banner + conflict-confirm dialog render correctly | STG-05 / RES-03 | AppTest asserts presence/state, not visual appearance | `uv run streamlit run app.py`, switch stages, trigger a conflicting fetch, eyeball the loud banner + confirm control |
| Stage selector reorders/reloads teams without stale numbers | STG-04 | wall-clock + visual cross-check of the automated isolation test | switch Stage 1 ↔ Stage 2 in the UI, confirm probs visibly change and never flash the prior stage's values |

---

## Validation Sign-Off

- [ ] All tasks have an `<automated>` verify or a Manual-Only entry
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers the 3 new test files + the `stage2.json` fixture (no framework install needed)
- [ ] GATE-01 freeze-regression companion present and green
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
