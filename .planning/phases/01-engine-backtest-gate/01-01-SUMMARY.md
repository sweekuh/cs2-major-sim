---
phase: 01-engine-backtest-gate
plan: 01
subsystem: testing
tags: [python, uv, numpy, pytest, swiss, monte-carlo, probability]

# Dependency graph
requires: []
provides:
  - "uv-bootstrapped Python >=3.12 project (pyproject.toml, uv.lock) with numpy 2.4.6 + pytest 9.0.3"
  - "engine/probs.py pure math core: p_map, series (Bo3 closed form), series_prob (odds passthrough), difficulty (canonical Buchholz), epistemic_draws + beta_moment_fit stubs"
  - "engine/teams.py single seed->team source of truth with derived R1 + validated JSON load"
  - "data/stage1.json editable [INFERRED] Cologne fixture"
  - "Full Wave 0 test scaffold: math guards green (test_probs) + RED xfail targets for waves 2/3/4 (test_swiss, test_mc, test_backtest_budapest_2025)"
affects: [02-swiss-engine, 03-monte-carlo, 04-backtest-gate, 05-odds-ensemble]

# Tech tracking
tech-stack:
  added: [uv 0.11.17, numpy 2.4.6, pytest 9.0.3]
  patterns:
    - "Functional core: engine/ imports no streamlit/httpx/requests (gate-ability invariant)"
    - "Single source of truth: R1 pairings derived [(i,i+8) for i in range(1,9)], not hardcoded twice"
    - "Nyquist Wave 0: every later wave gets a RED xfail target now"
    - "Epistemic OUTER loop stubbed (single point draw in Phase 1) so Phase 5 fills K Beta draws without a rewrite"

key-files:
  created:
    - pyproject.toml
    - uv.lock
    - engine/__init__.py
    - engine/probs.py
    - engine/teams.py
    - data/stage1.json
    - tests/__init__.py
    - tests/conftest.py
    - tests/test_probs.py
    - tests/test_swiss.py
    - tests/test_mc.py
    - tests/test_backtest_budapest_2025.py
  modified:
    - .gitignore

key-decisions:
  - "Pinned pytest 9.x (not the research-assumed 8.x): live `pip index versions` showed 9.0.3 is current; the plan instructs pinning the CONFIRMED version, so research assumption A1 (pytest 8.x [ASSUMED]) is superseded."
  - "Installed uv via the official Astral installer (uv was absent on PATH); uv is Approved in the RESEARCH Package Legitimacy Audit, so no human-verify checkpoint was required."
  - "difficulty() lives in engine/probs.py as the single canonical Buchholz definition that swiss.py imports in wave 2 (no second copy)."
  - "series_prob() wires the odds-override branch now with market source stubbed None; Phase 5 only supplies the value."

patterns-established:
  - "engine/ is a pure, dependency-free compute core; never imports streamlit/httpx/requests"
  - "Wave 0 test files are scaffolded with pytest.mark.xfail(strict=False) so the suite collects and is not falsely green while later-wave code is absent"
  - "JSON fixtures validated loudly on load (16 unique seeds, unique names, finite in-range ratings)"

requirements-completed: [ENG-01, ENG-03, PROB-01, PROB-02, PROB-03, PROB-04, PROB-05, MC-06, GATE-02]

# Metrics
duration: ~25min
completed: 2026-05-28
---

# Phase 1 Plan 01: Engine Math Core + Wave 0 Test Harness Summary

**Bootstrapped the dependency-free compute core — `engine/probs.py` (logistic p_map, `p²(3−2p)` Bo3 closed form, canonical Buchholz `Σ(opp.wins−opp.losses)`, odds-override passthrough, epistemic/Beta Phase-5 stubs) and `engine/teams.py` (single 16-team seed→team map with R1 derived + validated JSON) — and laid the full Nyquist Wave 0 test scaffold so the math guards run green while the engine/MC/gate tests sit RED (xfail) for their owning waves.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 3 of 3
- **Files created:** 12 (+1 modified)

## Accomplishments

- `uv run pytest` collects the entire suite; the four math guards (difficulty==2, p_map logistic, Bo3 0.648/0.5, odds passthrough) and the epistemic/Beta stub test PASS (5 passed); the 9 engine/MC/gate tests are RED via xfail (suite is not falsely green).
- The two load-bearing correctness facts are implemented and verified exactly: `difficulty()` on Valve's worked example (opponents 2-0 and 1-1) returns **2**, and `series(0.6, bo3=True) == 0.648` / `series(0.5, bo3=True) == 0.5`.
- `engine/teams.py` is the single seed→team source of truth; R1 pairings `[(1,9),(2,10),…,(8,16)]` are derived from `range(1,9)` with no second hardcoded copy, and `data/stage1.json` round-trips the same [INFERRED] fixture with loud load validation (rejects short lists, duplicate seeds, NaN ratings).
- `engine/probs` and `engine/teams` import no streamlit/httpx/requests (functional-core / gate-ability invariant holds).

## Task Commits

1. **Task 1: Scaffold uv project, deps, full Wave 0 test harness** — `247a9a8` (chore)
2. **Task 2: engine/probs.py math core** — `46a4836` (feat) — TDD GREEN gate; RED tests were committed in Task 1's scaffold
3. **Task 3: engine/teams.py + data/stage1.json** — `047b87f` (feat)

## Files Created/Modified

- `pyproject.toml` — uv project, requires-python >=3.12, numpy 2.4.x + dev pytest 9.x pins, `[tool.pytest.ini_options]` testpaths=tests
- `uv.lock` — resolved lockfile
- `engine/__init__.py` — package root documenting the no-forbidden-imports invariant
- `engine/probs.py` — p_map, series, series_prob (odds passthrough), difficulty (canonical Buchholz), epistemic_draws, beta_moment_fit
- `engine/teams.py` — Team dataclass, 16-team seed→team map, build_round1_pairs (derived), load_teams (validated), Stage config
- `data/stage1.json` — editable [INFERRED] Cologne seeds + default ratings
- `tests/conftest.py` — shared fixtures (teams, seeds) + FakeTeam factory for math guards
- `tests/test_probs.py` — math guards targeting wave-1 code (PASS)
- `tests/test_swiss.py` / `tests/test_mc.py` / `tests/test_backtest_budapest_2025.py` — RED xfail scaffolds for waves 2/3/4
- `.gitignore` — added `.pytest_cache/`

## Verification

| Check | Result |
|-------|--------|
| `uv run pytest -q tests/test_probs.py` | 5 passed |
| `uv run pytest -q` (full suite) | 5 passed, 9 xfailed — collects, not falsely green |
| `uv run python -c "import engine.probs, engine.teams"` (no forbidden imports) | OK |
| Task 3 plan verify (R1 derived, 16 teams, 8 pairs, seed i vs i+8) | OK: `[(1,9),(2,10),…,(8,16)]` |
| JSON round-trip + validation (short list / dup seed / NaN rejected) | OK |
| `difficulty()` worked example == 2 | OK |
| `series(0.6, True)==0.648`, `series(0.5, True)==0.5` | OK |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `uv` was not installed on the system**
- **Found during:** Task 1 (the entire plan bootstraps with `uv`).
- **Issue:** `uv` was absent from PATH (bash, PowerShell, and common install dirs all missed it); every plan verify command is `uv run …`.
- **Fix:** Installed `uv` 0.11.17 via the official Astral installer (`irm https://astral.sh/uv/install.ps1 | iex`) to `C:\Users\sweek\.local\bin`. `uv` is **Approved** in the RESEARCH Package Legitimacy Audit (canonical Astral dev tool), so this is not a slopsquat-risk install and no `checkpoint:human-verify` was required.
- **Files modified:** none (toolchain install).
- **Commit:** n/a (environment setup, not a repo change).

**2. [Rule 1 - Correctness] Pinned pytest 9.x instead of the research-assumed 8.x**
- **Found during:** Task 1 version verification.
- **Issue:** Research tagged pytest `8.x [ASSUMED]`; live `pip index versions pytest` showed **9.0.3** is the current line.
- **Fix:** The plan explicitly instructs pinning the *confirmed* current version, so `pyproject.toml` pins `pytest>=9,<10`. numpy confirmed at 2.4.6 (research 2.4.x [ASSUMED] held). This supersedes Assumption A1 in 01-RESEARCH.md.
- **Files modified:** `pyproject.toml`, `uv.lock`.
- **Commit:** `247a9a8`.

**3. [Rule 3 - Blocking] Pre-existing `.gitignore` already present**
- **Found during:** Task 1.
- **Issue:** A project `.gitignore` already existed (covered `__pycache__`, `.venv`, `.env`); the plan said to create one.
- **Fix:** Edited the existing file to add the missing `.pytest_cache/` rather than overwriting it.
- **Files modified:** `.gitignore`.
- **Commit:** `247a9a8`.

## Notes for Later Waves

- **Wave 2 (swiss.py):** import `difficulty` from `engine.probs` (canonical Buchholz, no re-definition). Remove the xfail marks in `tests/test_swiss.py` and assert real behavior; the priority table (15 rows) is in 01-RESEARCH.md.
- **Wave 3 (montecarlo.py):** fill the OUTER loop using `epistemic_draws` + `beta_moment_fit`; with one source the band must collapse to the inner Wilson band. Use `SeedSequence.spawn` over a **pinned** chunk count.
- **Wave 4 (the gate):** `tests/test_backtest_budapest_2025.py` is deliberately un-encoded — plan 01-04 Task 1 (autonomous:false checkpoint) re-fetches and reconciles the Budapest 2025 Stage 1 fixture via `/browse` before encoding (two research fetches disagreed on the 1-1 bucket).
- **Line endings:** Git warns LF→CRLF on Windows; harmless. Consider a `.gitattributes` with `* text=auto` if it becomes noisy.

## Self-Check: PASSED
