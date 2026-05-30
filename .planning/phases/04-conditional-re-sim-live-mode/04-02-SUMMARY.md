---
phase: 04-conditional-re-sim-live-mode
plan: 02
subsystem: ui
tags: [streamlit, live-mode, lock, delta-hero, status-chips, record-bucket-bracket, cache-key, apptest]

requires:
  - phase: 04-01
    provides: "engine/live.py pure core — locked_dict_from_results, validate_lock, classify_pick, pge5_delta, derive_bracket, legal_pairings_for_round, LivePrefixIncomplete, BracketView"
  - phase: 02
    provides: "freeze_locked->locked_key->cache_key path, _run_or_serve, _drive_progress, the LIVE-mode shell, the STATUS palette / status_badge_html / hero_number_html"
  - phase: 03
    provides: "optimize_cached (Ballot B recommended), build_outcome_matrices + p_ge5 reused for the from-here delta"
provides:
  - "LIVE-mode round-by-round lock controls writing st.session_state[KEY_LOCKED], gated so round R appears only once R-1 is fully entered"
  - "The derived engine locked dict flowing through the EXISTING freeze_locked->locked_key->cache_key fill point so a non-empty lock re-sims for free (RESIM-01)"
  - "From-here P(>=5) delta hero (before% -> after%) anchored on a FIXED Ballot B captured once from the EMPTY-locked pre_key Result (RESIM-02)"
  - "Per-pick live/dead/secured status chips via classify_pick + status_badge_html (blue/amber, never red/green)"
  - "Record-bucket bracket COLUMNS (solid-locked / faint-simulated, escaped names) via derive_bracket + bracket_columns_html (RESIM-04)"
  - "validate_lock gating each lock with st.error; an impossible lock mutates neither KEY_LOCKED nor the mc_cache (RESIM-03)"
affects: [phase-5-odds-ensemble]

tech-stack:
  added: []
  patterns:
    - "Lock truth = ordered list[(round, winner, loser)] in KEY_LOCKED; the engine locked dict is a pure DERIVED projection fed through the unchanged cache key (no new key arg)"
    - "Anchor/pre-lock delta flow: pre_key = (ratings_key, S, int(N), freeze_locked({})); _compute_or_serve get-or-compute keeps each distinct key single-compute (CR-01)"
    - "Live-mode invariant: round-R controls gated on R-1 fully entered so legal_pairings_for_round never hits a partial prefix (never raises LivePrefixIncomplete in the UI path)"

key-files:
  created:
    - .planning/phases/04-conditional-re-sim-live-mode/04-02-SUMMARY.md
  modified:
    - ui/state.py
    - ui/render.py
    - app.py
    - tests/test_app.py

key-decisions:
  - "The locked={} fill point in _run_or_serve becomes locked_dict(st.session_state[KEY_LOCKED]) — the derived dict flows through the EXISTING freeze_locked->cache_key path; no new key, no _locked escape (RESIM-01/Pitfall 13)"
  - "Anchor (Ballot B) captured ONCE from the EMPTY-locked pre_key Result via optimize_cached(pre_lock_result, *pre_key).recommended, stored in KEY_LIVE_ANCHOR, never re-optimized per round (RESIM-02/BLOCKER 1)"
  - "_compute_or_serve is a shared get-or-compute keyed on (ratings, S, N, locked); the empty-locked pre_key is a DISTINCT key from the locked run so CR-01 single-compute stays green"
  - "Lock commit reads KEY_PENDING_LOCK (radio selection OR a test injection) and validates via validate_lock BEFORE mutating KEY_LOCKED; an illegal lock only st.errors (RESIM-03)"
  - "Status chips walk the anchor ballot WITH bucket labels (picks_30/picks_adv/picks_03) so classify_pick classifies in the correct bucket — never a flattened id list"

patterns-established:
  - "name_of / ids built ONCE in the LIVE block (not reused from _render_ballot_panel's local) and passed into bracket render + status chips"
  - "bracket_columns_html: canonical record-bucket flex columns, opacity:1 locked / opacity:0.5 simulated, html.escape names, no tree/connector markup"

requirements-completed: [RESIM-01, RESIM-02, RESIM-03, RESIM-04]

duration: 22 min
completed: 2026-05-29
---

# Phase 4 Plan 02: LIVE-mode UI Wiring Summary

**Round-by-round result locking that re-sims for free through the existing locked cache key, a P(>=5)-from-here delta arrow anchored on a fixed Ballot B captured from the empty-locked pre_key Result, per-pick live/dead/secured chips, and a record-bucket bracket — impossible locks rejected with a reason.**

## Performance

- **Duration:** 22 min
- **Started:** 2026-05-29
- **Completed:** 2026-05-29
- **Tasks:** 2 (TDD: RED helpers/tests → GREEN app wiring)
- **Files modified:** 4 (ui/state.py, ui/render.py, app.py, tests/test_app.py)

## Accomplishments

- Locking a round result writes `KEY_LOCKED`; the derived engine `locked` dict flows through the UNCHANGED `freeze_locked`→`locked_key`→`cache_key` path (the `locked={}` fill point), so a non-empty lock changes the key, misses the session `mc_cache`, and re-sims conditioned on the lock — ≥1 P(advance) moves (RESIM-01).
- The LIVE `_hero_slot` renders the from-here `before% → after%` P(>=5) delta via `hero_number_html`, anchored on Ballot B captured ONCE at the first Run from the EMPTY-locked `pre_key` Result and held fixed across rounds (RESIM-02 / BLOCKER 1). The anchor never re-optimizes; `before` is read off the pre_key Result's own sample.
- Each locked pick row shows its live/dead/secured chip via the existing `status_badge_html` (blue/amber + ASCII glyph + label, never red/green), classified by `classify_pick` against the conditional sample, walking the anchor ballot WITH its bucket label.
- An impossible lock (rematch / terminated team / non-pairing / double-booking / winner-not-in-pair) is blocked: `validate_lock`'s reason shows via `st.error`, and `KEY_LOCKED` + the `mc_cache` are not mutated (RESIM-03).
- The bracket renders as record-bucket COLUMNS (`0-0 → 1-0/0-1 → … → 3-0 adv / 0-3 elim`) from `derive_bracket`, locked solid / simulated faint, names `html.escape`-d — never a tree (RESIM-04).
- Round-R lock controls appear only once round R-1 is fully entered, so `legal_pairings_for_round` is never called on a partial prefix.

## Task Commits

1. **Task 1: ui/state.py lock helpers + ui/render.py bracket columns + RED tests** — `a83e0c6` (test)
2. **Task 2: app.py LIVE wiring (lock controls + delta hero + status chips + bracket + lock gating)** — `2a0f378` (feat)

_TDD: Task 1 shipped the helpers + 5 RED (xfail strict) live AppTests + a passing pure bracket assertion; Task 2 wired app.py and removed the xfail markers (GREEN)._

## Files Created/Modified

- `ui/state.py` — `KEY_LOCKED` / `KEY_LIVE_ANCHOR` / `KEY_PENDING_LOCK` constants + pure list-in/list-out lock helpers `add_lock` / `remove_last_lock` / `locks_for_round` / `locked_dict` (delegates to `engine.live.locked_dict_from_results`).
- `ui/render.py` — `bracket_columns_html(bracket_view, name_of)`: canonical record-bucket flex columns, solid-locked (`opacity:1`) vs simulated-faint (`opacity:0.5`), `html.escape` names, no tree markup.
- `app.py` — derived `locked` at the fill point in `_run_or_serve`; `_compute_or_serve` get-or-compute; `_live_anchor` (pre_key anchor capture) + `_render_live_hero` (delta arrow); `_render_lock_controls` + `_commit_lock` (round-gated, validate_lock-gated); `_open_round_idx`; `_render_status_chips`; `_render_bracket_live`; rewired LIVE main block; `import html`.
- `tests/test_app.py` — 5 live AppTests (`test_live_lock_changes_cache_key`, `test_live_lock_moves_p_advance`, `test_impossible_lock_shows_reason`, `test_live_status_chips_render`, `test_live_delta_anchor_uses_pre_key`) + a pure `test_bracket_columns_html_is_columns_not_tree`.

## Decisions Made

- Lock-commit contract: the "Lock result" button commits `KEY_PENDING_LOCK` (the radio selection on the normal path, or a direct injection for tests exercising the `validate_lock` gate). This made `test_impossible_lock_shows_reason` exercise the real gate without needing the UI to offer an illegal pairing.
- `_compute_or_serve` extracted from `_run_or_serve` so the LIVE pre_key (empty-locked) compute reuses the exact same single-compute-per-key memoization — keeping CR-01 green while serving the anchor.

## Deviations from Plan

None — plan executed exactly as written. The only test adjustment was preserving the pre-existing LIVE empty-state copy "Lock a result to go live." (asserted by `test_mode_toggle_reorders_main_column`); my first draft had reworded it, which would have broken that existing test, so I restored the exact string. This is honoring an existing contract, not a scope deviation.

## Issues Encountered

- Initial draft of the lock-commit handler used a button `on_click` callback that re-staged `KEY_PENDING_LOCK` from the radio, which would clobber a test-injected illegal pending lock. Resolved by deriving the pending lock at button-click time only when not already staged/injected, so the rematch-injection test commits the injected pair and the validate_lock reason surfaces.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Phase 4 is complete: both plans (04-01 pure core, 04-02 LIVE UI) executed. RESIM-01..04 satisfied.
- Full suite **85 passed** (was 79 baseline; +5 live AppTests + 1 pure bracket assertion). GATE-01 Budapest backtest **green** (3 passed). CR-01 single-compute guard green. No engine mutation.
- Ready for Phase 5 (Odds Ensemble). The `data/odds_cache.json` read-only seam (ODDS-07) is the remaining cross-phase contract to honor.

## Self-Check: PASSED

- Files: `04-02-SUMMARY.md`, `ui/state.py`, `ui/render.py`, `app.py`, `tests/test_app.py` all FOUND.
- Commits: `a83e0c6` (test, Task 1), `2a0f378` (feat, Task 2) both FOUND in git log.
- Verification: `uv run pytest -q tests/test_app.py` → 26 passed; `uv run pytest -q` → 85 passed; GATE-01 `test_backtest_budapest_2025` → 3 passed (green).

---
*Phase: 04-conditional-re-sim-live-mode*
*Completed: 2026-05-29*
