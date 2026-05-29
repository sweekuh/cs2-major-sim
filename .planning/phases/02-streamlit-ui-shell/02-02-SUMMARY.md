---
phase: 02-streamlit-ui-shell
plan: 02
subsystem: ui
tags: [streamlit, ui, layout, theming, tokens, colorblind]
requires:
  - "ui.render.ci_bar_html / fmt_pct (Phase 2 plan 01 — inline Wilson CI bars)"
  - "ui.state.Mode / DEFAULT_MODE / KEY_MODE (Phase 2 plan 01 — mode enum + keys)"
  - "ui.cache.freeze_locked / freeze_ratings / run_mc_cached (Phase 2 plan 01 — cache seam)"
  - "engine.montecarlo.run_mc_progressive + Result.band_* (Phase 1 — frozen)"
provides:
  - "ui.render.STATUS — locked colorblind-safe status palette (advanced/live/eliminated)"
  - "ui.render.status_badge_html — ASCII glyph + text label + blue/amber hue (never red/green)"
  - "ui.render.hero_number_html — 28px monospace reserved-accent hero number"
  - "app.py — st.segmented_control Pre-stage/Live toggle + mode-conditional main-column reorder"
  - "app.py — structured ballot / live-status / bracket placeholders with UI-SPEC empty copy"
affects:
  - "Phase 3 (optimizer) fills the recommended-ballot hero slot + ballot content"
  - "Phase 4 (result locking) fills the Live locked-pick status, delta probs, and bracket record buckets"
  - "Plan 03 (trust badge / seed banner / DX docs) layers onto the header strip"
tech-stack:
  added: []
  patterns:
    - "STATUS = {state: (ascii_glyph, label, hue)} — colour reinforces glyph+label, never the sole signal (UI-06)"
    - "Mode-conditional section ordering: a single Mode enum drives which subheader/placeholder is the top main-column section"
    - "Shared _render_probs_table reused for Pre-stage probs and Live delta-probs (delta content is Phase 4)"
    - "AppTest assertions on element collections (at.subheader / at.info / at.segmented_control), never str(at)"
key-files:
  created: []
  modified:
    - "ui/render.py"
    - "app.py"
    - "tests/test_ui_helpers.py"
    - "tests/test_app.py"
decisions:
  - "Hero slot renders a placeholder hero number (top-team P(advance) stand-in) so the 28px monospace accent slot is real now; Phase 3/4 fill the optimal-ballot P(>=5) content"
  - "Live mode kept as a structured placeholder shell (locking is Phase 4) — empty copy 'Lock a result to go live.' retained per the 2026-05-29 user decision"
  - "Status legend rendered in Live mode from status_badge_html so the blue/amber + ASCII glyph + label contract is exercised before Phase 4 wires real per-team status"
metrics:
  duration_min: 8
  tasks: 2
  files: 4
  completed: 2026-05-29
---

# Phase 2 Plan 02: Two-Mode Shell + Locked Visual-Token Contract Summary

Layered the Pre-stage/Live mode toggle and the locked colorblind-safe visual-token contract onto the plan-01 runnable slice: a `st.segmented_control` whose selection reorders the main column (UI-01), every probability cell still carries an always-visible inline Wilson CI mini-bar (UI-04), and the UI-06 token system — monospace numbers, one reserved accent, and blue/amber status always paired with an ASCII glyph + text label, never red/green.

## What Was Built

- **`ui/render.py`** — added the locked `STATUS` palette (`advanced`→`/ secured` blue, `live`→`o live` blue, `eliminated`→`x dead` amber; never red/green), `status_badge_html(state)` (ASCII glyph + text label + hue, unknown state raises — T-02-XSS), and `hero_number_html(pct)` (28px monospace number in the reserved accent `#7C5CFC`, numeric-only guard). The plan-01 `ci_bar_html` / `fmt_pct` are untouched.
- **`app.py`** — added the `st.segmented_control` Pre-stage/Live toggle bound to `ui.state.Mode` (default Pre-stage on first load). The main column now reorders by mode:
  - **Pre-stage:** (1) Recommended-ballot placeholder + hero slot (empty copy `Run to see the recommended ballot.`), (2) per-team probs table (number + always-visible inline CI bar), (3) collapsed bracket expander showing the seeded R1 `(seed, seed+8)` table only.
  - **Live:** (1) locked-pick status placeholder + status legend (`status_badge_html`) + hero slot (empty copy `Lock a result to go live.`), (2) delta-probs area (reuses the probs render; delta content is Phase 4), (3) collapsed bracket expander.
  - Extracted `_render_probs_table` / `_render_probs_empty` / `_render_bracket` / `_run_or_serve` / `_hero_slot` helpers so both modes share the engine dispatch and the CI-bar render.
- **`tests/test_ui_helpers.py`** (+5) — `test_status_palette_never_red_green`, `test_status_glyphs_are_ascii_only`, `test_status_badge_html_pairs_glyph_and_label`, `test_status_badge_html_rejects_unknown_state`, `test_hero_number_html_is_monospace_accent`.
- **`tests/test_app.py`** (+3) — `test_two_mode_toggle_present`, `test_mode_toggle_reorders_main_column` (asserts the subheader ordering swaps and the mode-specific empty copy appears), `test_ci_bars_on_every_cell_after_run` (>=16 inline CI bars after a Run — guards the reorder from dropping bars).

## Verification Results

- `uv run pytest -q tests/test_ui_helpers.py` — **12 passed** (7 plan-01 + 5 new token tests).
- `uv run pytest -q tests/test_app.py` — **8 passed** (5 plan-01 + 3 new toggle/reorder/CI tests).
- `uv run pytest -q` — **41 passed, 1 skipped** (the deferred Budapest GATE-01, expected). Up from 33 passed at plan start; no regression.
- Engine untouched: `git diff --stat HEAD -- engine/` is empty.
- AppTest smoke: a fresh `AppTest.from_file("app.py").run()` then Run click raises no exception; 48 inline CI bars (16 teams × 3 columns) render and 1 accent hero number (`28px` + `#7C5CFC`) renders. Flipping the toggle to Live reorders subheaders to `Your picks — status` / `Delta probabilities` and shows `Lock a result to go live.`

## TDD Gate Compliance

Task 1 was `tdd="true"`: tests added first and confirmed RED (5 failures, all `ImportError` against the not-yet-built `STATUS` / `status_badge_html` / `hero_number_html` — not falsely green), then GREEN after implementing `ui/render.py` (commit `42b3df6`). Task 2 is a non-TDD `auto` task (the toggle/reorder is layout, exercised via AppTest); its tests were added alongside the `app.py` change and pass (commit `29df60b`).

## Deviations from Plan

None affecting behavior. Two within-scope notes:

**1. [Within scope] Hero slot shows a placeholder stand-in number, not the real P(>=5).**
The plan scopes the optimal-ballot P(≥5) content to Phase 3 (Pre-stage) / Phase 4 (Live). To make the 28px monospace accent hero SLOT real now (per the plan action "render the shell + the hero_number_html slot now"), `_hero_slot` renders the top team's P(advance) as a stand-in. This is the documented shell, replaced by the optimizer output in Phase 3/4.

**2. [Within scope] Live status legend rendered from `status_badge_html`.**
The plan calls for the Live section to use `status_badge_html` for the `o live`/`x dead`/`/ secured` legend. Real per-team locked status is Phase 4; this plan renders the static legend so the blue/amber + ASCII glyph + label contract is visible and exercised now.

No authentication gates (local single-user app, no network). `STATUS` import was dropped from `app.py` (only the three render functions are used there) to keep imports clean.

## Known Stubs

- **Recommended-ballot content / Live locked-pick status / delta-probs / bracket record buckets** — structured placeholders with the correct UI-SPEC empty-state copy and the real hero/status/CI renderers wired. Phase 3 fills the ballot + P(≥5) hero; Phase 4 fills the Live locked-pick status, the delta content, and the bracket record-bucket columns. Intentional and documented in the plan (`<objective>`: "the ballot and live-status panels ship as structured placeholders wired for plans 3/4").
- **`locked = {}`** in `_run_or_serve` — the cache-key shape `(ratings_key, S, N, locked_key)` is final; Phase 4 fills `locked`. Deliberate Phase 2×4 seam, not an unfinished stub.

No stubs prevent this plan's goal (mode-switchable shell + honest never-hidden CI in the colorblind-safe token language). The toggle, reorder, CI bars, status tokens, and hero renderer are all real.

## Threat Flags

None. No new security surface beyond the plan's `<threat_model>`: `status_badge_html` interpolates only a fixed enum of ASCII glyph/label/hue constants and raises on an unknown state (T-02-XSS); `hero_number_html` interpolates a numeric-formatted percentage only (numeric guard); `ci_bar_html` is unchanged from plan 01. The mode value is a single-select widget that only reorders layout — no engine/file/network path (T-02-MODE accepted).

## Self-Check: PASSED

- Files modified present on disk: `ui/render.py`, `app.py`, `tests/test_ui_helpers.py`, `tests/test_app.py`.
- Task commits found in git history: `42b3df6` (feat 02-02 status tokens + hero), `29df60b` (feat 02-02 two-mode toggle + reorder + CI bars).
- `STATUS`, `status_badge_html`, `hero_number_html` import and behave as asserted (12 helper tests green); toggle + reorder verified via AppTest (8 app tests green); full suite 41 passed / 1 skipped, engine untouched.
