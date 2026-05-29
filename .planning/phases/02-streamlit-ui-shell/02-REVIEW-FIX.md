---
phase: 02-streamlit-ui-shell
fixed_at: 2026-05-29T00:00:00Z
review_path: .planning/phases/02-streamlit-ui-shell/02-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-05-29
**Source review:** .planning/phases/02-streamlit-ui-shell/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (CR-01, WR-01, WR-02, WR-03, WR-04 — Info findings IN-01/IN-02 out of scope)
- Fixed: 5
- Skipped: 0

Full suite after fixes: `51 passed, 1 skipped` (was 50 passed, 1 skipped — the
CR-01 regression test adds one). `engine/` untouched and free of streamlit.

## Fixed Issues

### CR-01: `run_mc_cached` priming call doubles computation time on every first Run

**Files modified:** `app.py`, `tests/test_app.py`
**Commit:** 1f12359
**Applied fix:** Fix A (the review's preferred option). Removed the discarded
`run_mc_cached(ratings_key, S, int(N), locked_key)` priming call from `_run_or_serve`,
which re-ran the full N-sim engine a second time (result thrown away) on every cache
miss, doubling first-Run wall-clock with no user feedback. The `session_state` cache
already deduplicates per unique input tuple (single compute per key), which is sufficient
for Phase 2; the review explicitly endorses wiring cross-session reuse correctly in a
later phase. Also dropped the now-unused `run_mc_cached` import from `app.py`
(`freeze_ratings`/`freeze_locked` stay — `ratings_key`/`locked_key` still build the cache
key). The Phase 1x2 progress path (`n_chunks=20`) and the Phase 2x4 `freeze_locked` cache
key are unchanged.

Added `test_single_run_computes_mc_exactly_once`: spies on
`engine.montecarlo.run_mc_progressive` (the cache-miss compute path) via monkeypatch and
asserts it fires exactly once per Run, and that exactly one result is cached/rendered.

### WR-01: `KEY_N_INPUT` constant defined but never used

**Files modified:** `app.py`
**Commit:** d07374f
**Applied fix:** Imported `KEY_N_INPUT` from `ui.state` alongside the other key
constants and used `key=KEY_N_INPUT` for the N number-input instead of the hardcoded
literal `"N_input"`. The constant is now the single source of truth (was dead code), and
all widget keys are now constant-driven.

### WR-02: Validated trust badge branch renders wrong text with spurious `/` prefix

**Files modified:** `app.py`, `ui/state.py`
**Commit:** 0899b42
**Applied fix:** Added a dedicated `TRUST_BADGE_VALIDATED` string in `ui/state.py` and
rendered it in the green `st.success` branch instead of `f"/ {TRUST_BADGE_CAVEATED}"`.
This removes the self-contradiction (a green "validated" box that said "backtest pending
seed data") and drops the stray `"/ "` prefix. The validated wording is generic
("+ full round-by-round backtest") and deliberately does NOT mention Budapest, honoring
the CLAUDE.md trust-badge rule (the review's suggested string contained "Budapest", which
would violate it — used the constraint-provided safe wording instead). `BACKTEST_PASSED`
stays `False`, so the branch remains unreachable in Phase 2.

### WR-03: CI-bar count assertion too weak (`>= 16`)

**Files modified:** `tests/test_app.py`
**Commit:** fff00a4
**Applied fix:** Changed `assert len(bar_markup) >= 16` to `>= 48` to match the stated
intent (16 teams x 3 prob columns). The old bound passed even if 2 of 3 columns silently
lost their bars. Verified the app actually renders 48 bars, so the stronger assertion
passes without weakening anything.

### WR-04: Glyph assertion vacuously true (`assert "/" in html`)

**Files modified:** `tests/test_ui_helpers.py`
**Commit:** 238e5d8
**Applied fix:** Replaced the three bare substring checks with text-content assertions of
the form `assert f">{glyph} {label}<" in html` (e.g. `">/ secured<"`), pulling the glyph
and label from `ui.render.STATUS`. The old `"/" in html` was always true because the
`</span>` close tag contains `/`; the new assertion fails if the glyph changes. Applied
to all three states (advanced/eliminated/live).

---

_Fixed: 2026-05-29_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
