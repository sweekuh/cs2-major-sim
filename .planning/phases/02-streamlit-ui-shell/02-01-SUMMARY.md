---
phase: 02-streamlit-ui-shell
plan: 01
subsystem: ui
tags: [streamlit, ui, cache, monte-carlo, generator, validation]
requires:
  - "engine.montecarlo.run_mc / run_mc_progressive (Phase 1 — frozen)"
  - "engine.teams.load_teams + data/stage1.json (Phase 1 — frozen)"
provides:
  - "app.py — runnable Streamlit entry (controls + Run + per-team probs)"
  - "ui.cache.freeze_locked / freeze_ratings / run_mc_cached (the Phase 2x4 cache-key seam)"
  - "ui.state.validate_ratings / FIXED_SEED / Mode / session_state key constants"
  - "ui.render.ci_bar_html / fmt_pct (XSS-safe inline CI bars)"
  - ".streamlit/config.toml theme (dark base, #7C5CFC accent, codeFont monospace)"
affects:
  - "Plan 02 (two-mode shell + visual tokens) builds on app.py + ui/"
  - "Plan 03 (trust badge / seed banner / DX docs) builds on the header strip"
  - "Phase 4 (result locking) fills the already-final locked={} cache-key shape"
tech-stack:
  added:
    - "streamlit>=1.57,<1.58 (installed 1.57.0)"
  patterns:
    - "freeze_locked: dict -> deterministic hashable cache key (NOT _locked escape)"
    - "Pattern 2 option B: session_state dict keyed on (ratings_key,S,N,locked_key) — single in-session compute + real progress bar"
    - "Cache-miss progress: iterate run_mc_progressive, no n_chunks override (stays 20)"
    - "Pure helpers (ui.state/ui.render) import no streamlit — AppTest-free unit tests"
key-files:
  created:
    - ".streamlit/config.toml"
    - "app.py"
    - "ui/__init__.py"
    - "ui/cache.py"
    - "ui/state.py"
    - "ui/render.py"
    - "tests/test_ui_helpers.py"
    - "tests/test_app.py"
  modified:
    - "pyproject.toml"
    - "uv.lock"
decisions:
  - "Fixed seed 20260528 (engine __main__ smoke seed) so reruns are reproducible and seed need not enter the cache key (RESEARCH A3)"
  - "Pattern 2 option B chosen: session_state mc_cache keyed on the tuple = single compute per unique key in-session + a real bar; run_mc_cached also primed for the cross-session memo"
  - "Live mode toggle deferred to plan 02 — this slice ships Pre-stage only (DEFAULT_MODE), controls + Run + probs"
  - "locked_key is a REAL cache-key arg via freeze_locked (NOT _locked) so Phase 4 locking moves >=1 P(advance) (RESIM-01)"
metrics:
  duration_min: 8
  tasks: 3
  files: 10
  completed: 2026-05-29
---

# Phase 2 Plan 01: Streamlit UI Shell — Run + Per-Team Probabilities Summary

The thinnest runnable end-to-end UI slice: a fresh clone runs `uv run streamlit run app.py`, clicks **Run** with the shipped default ratings (no API key, no editing), watches a real engine-driven progress bar, and sees per-team P(advance)/P(3-0)/P(0-3) with inline Wilson CI bars — over the two correctness seams (`freeze_locked` cache key, no-re-chunk progress loop) plus a rating gate that blocks Run before the engine is ever called.

## What Was Built

- **`pyproject.toml` + `uv.lock`** — added `streamlit>=1.57,<1.58` (installed 1.57.0; 1.58.0 is now current but the project pins 1.57.* per CLAUDE.md). `ui` registered in `[tool.setuptools].packages`. No httpx/python-dotenv (Phase 5 only).
- **`.streamlit/config.toml`** — `[theme]` dark base, `primaryColor=#7C5CFC`, dark surfaces, `codeFont=monospace` (the four CONFIRMED UI-SPEC tokens). Visual effect is Manual-Only per VALIDATION; existence + tokens checked here.
- **`ui/cache.py`** — `freeze_locked` / `freeze_ratings` (order-independent, hashable, round-tripping cache keys) and `run_mc_cached` (`@st.cache_data(show_spinner=False)`, `locked_key` a REAL key arg, `seed=FIXED_SEED`, default `n_chunks=20`).
- **`ui/state.py`** — `FIXED_SEED=20260528`, `MAX_N`, `Mode` enum, `DEFAULT_MODE=Pre-stage`, session_state key constants, `BAD_RATING_MSG`, and `validate_ratings` (empty/out-of-range gate mirroring engine `0<r<1000`). Streamlit-free.
- **`ui/render.py`** — `ci_bar_html` (numeric-only inputs, `#rrggbb` hue guard — T-02-XSS) + `fmt_pct`. Streamlit-free.
- **`app.py`** — `st.columns([1,3])` controls/main; `st.data_editor` (16 fixed rows, rating-only editable, `NumberColumn` 1..999), S slider, N input capped at `MAX_N`, Run button. Validated dispatch: HIT serves stored Result; MISS drives `st.progress` over `run_mc_progressive` then primes `run_mc_cached`. Per-team rows sorted by P(advance) with inline CI bars. All four states (loading/empty/error/success).
- **`tests/test_ui_helpers.py`** (7) + **`tests/test_app.py`** (5) — pure-function + AppTest coverage of the seams.

## Verification Results

- `uv run pytest -q` — **33 passed, 1 skipped** (the deferred Budapest GATE-01, expected). Phase 1 engine tests unregressed (engine/ untouched, confirmed via `git diff --stat HEAD -- engine/` = empty).
- `uv run pytest -q tests/test_ui_helpers.py` — 7 passed (freeze_locked roundtrip + order-independence, freeze_ratings, validate_ratings, ci_bar structure, XSS guard, run_mc_cached reproduces frozen run_mc).
- `uv run pytest -q tests/test_app.py` — 5 passed (zero-config run, cache hit, locked-in-key, progress-no-rechunk reproducibility, bad-rating block).
- `uv run streamlit run app.py --server.headless true` — launches cleanly (Local URL printed, no Traceback/Exception).

## TDD Gate Compliance

This plan is `type: execute` with per-task `tdd="true"`. Gate sequence held:
1. **RED** (Task 1, commit `05eb8da`, `test(...)`): 12 new tests collect and run xfail (not falsely green) against not-yet-built `ui/` + `app.py`.
2. **GREEN** (Task 2, commit `8eaba54`, `feat(...)`): `ui/` helpers land, 7 helper tests flip to pass.
3. **GREEN** (Task 3, commit `c962192`, `feat(...)`): `app.py` lands, 5 AppTest tests flip to pass, full suite green.

No REFACTOR commit needed (code landed clean). RED→GREEN gate commits present.

## Deviations from Plan

### Auto-fixed / decisions within scope

**1. [Rule 3 - Blocking] Registered `ui` package in `[tool.setuptools].packages`**
- **Found during:** Task 1 (`uv sync`).
- **Issue:** The project is a setuptools package (`packages = ["engine"]`); the new `ui/` package would not be importable from an installed build without being listed.
- **Fix:** Added `"ui"` to `[tool.setuptools].packages`. `uv sync` and all imports succeed.
- **Files:** `pyproject.toml`. **Commit:** `05eb8da`.

**2. [Within scope] streamlit pin resolves to 1.57.0 although 1.58.0 is now current**
- `pip index versions streamlit` shows 1.58.0 current (2026-05-29), but CLAUDE.md/the plan pin `1.57.*`. `>=1.57,<1.58` correctly installs 1.57.0. The pin was honored, not widened. Flag for the user: a future pin bump to 1.58 should re-verify `@st.cache_data` semantics (RESEARCH valid-until 2026-06-27).

No other deviations — the plan executed as written. No authentication gates (local single-user app, no network).

## Known Stubs

- **Live mode toggle** — `app.py` sets `mode = DEFAULT_MODE` (Pre-stage) and does not render the `st.segmented_control` toggle or the Live reorder. This is **intentional and documented in the plan** ("The two-mode toggle, bracket, and ballot panels are plan 02/03"). Plan 02 wires the toggle + mode reorder; plan 03 wires the trust badge / seed banner. The `Mode` enum and `DEFAULT_MODE` constant are in place so plan 02 is additive.
- **`locked = {}`** in `app.py` — the cache-key shape `(ratings_key, S, N, locked_key)` is final; Phase 4 fills `locked` with real results. This is the deliberate Phase 2x4 seam, not an unfinished stub.

No stubs prevent this plan's goal (honest per-team probabilities through a browser) from being achieved — the Run + probs path is fully wired to the real engine.

## Threat Flags

None. No new security surface beyond the plan's `<threat_model>`: rating/N input is validated before the engine (T-02-INPUT mitigated via `validate_ratings` + `MAX_N`), `ci_bar_html` interpolates numeric floats + a `#rrggbb`-validated hue only (T-02-XSS mitigated), and no network/secret handling was introduced (Phase 5).

## Self-Check: PASSED

All created files present on disk (app.py, ui/*, .streamlit/config.toml, tests/test_*, SUMMARY.md) and all three task commits found in git history (`05eb8da`, `8eaba54`, `c962192`).
