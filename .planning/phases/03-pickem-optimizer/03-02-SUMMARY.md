---
phase: 03-pickem-optimizer
plan: 02
subsystem: ui
tags: [streamlit, ui, ballot, hero, optimizer, cache]
requires:
  - "engine.optimizer.optimize / OptimizerOutput (Plan 03-01)"
  - "ui.cache.freeze_ratings / freeze_locked + the (ratings_key,S,N,locked_key) cache tuple (Phase 2)"
  - "ui.render.hero_number_html / fmt_pct (Phase 2)"
provides:
  - "ui.cache.optimize_cached — @st.cache_data optimizer memo keyed on the MC cache tuple"
  - "ui.render.ballot_columns — A-vs-B side-by-side HTML, differing picks marked (XSS-safe)"
  - "ui.render.correlated_pick_warning_text — st.warning copy (OPT-05)"
  - "app.py _render_ballot_panel — pre-stage hero P(>=5) + dual ballot + warning"
affects:
  - "Phase 4 fills the LIVE-mode hero (_hero_slot) with the P(>=5)-from-here delta"
tech-stack:
  added: []
  patterns:
    - "optimize_cached(_result, ratings_key, S, N, locked_key): _result underscore-EXCLUDED from the key (it's a pure function of the key, reused without re-running the MC) — the deliberate inverse of the locked-must-be-in-key rule"
    - "Team names HTML-escaped before unsafe_allow_html (T-03-XSS); fixed titles not escaped"
    - "Diff highlight = bold + ASCII '*' (colour never the only signal — UI-06)"
    - "Correlated warning via st.warning (natively amber, colorblind-safe; '!' ASCII glyph)"
key-files:
  created: []
  modified:
    - "ui/cache.py"
    - "ui/render.py"
    - "app.py"
    - "tests/test_ui_helpers.py"
    - "tests/test_app.py"
decisions:
  - "Optimizer memoized via @st.cache_data on the SAME (ratings_key,S,N,locked_key) tuple as run_mc_cached; the already-computed Result is passed as the underscore arg so the MC is NEVER re-run (avoids the CR-01 double-compute)."
  - "_hero_slot retained for LIVE mode (Phase-4 P(>=5)-from-here placeholder); PRE-STAGE hero is the real recommended-ballot P(>=5) via _render_ballot_panel."
  - "_run_or_serve now returns the cache_key so the optimizer can key off it without recomputing."
requirements: [OPT-03, OPT-04, OPT-05]
---

# 03-02 Summary — UI wiring

Filled the Phase-2 `_hero_slot` placeholder with the real recommended-ballot P(>=5) and
added the pre-stage ballot panel: Ballot A (Max E[correct]) and Ballot B (Max P(>=5)) side
by side with differing picks marked, plus the correlated-0-3-in-R1 warning banner. The
optimizer is memoized on the same cache key as the MC and scores the stored sample — it
never re-runs the simulation.

## Tests (5 new, all green)
- helpers: `test_ballot_columns_lists_names_and_marks_diff`, `test_ballot_columns_escapes_team_names`, `test_correlated_pick_warning_text_format`.
- AppTest: `test_ballot_panel_renders_after_run` (A & B render), `test_hero_is_pge5_not_placeholder` (#7C5CFC hero with a %, placeholder gone in pre-stage).

Full suite: 63 passed, 1 skipped. Existing Phase-2 AppTests (toggle reorder, CI bars, empty
states) unregressed.
