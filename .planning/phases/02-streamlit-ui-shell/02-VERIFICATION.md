---
phase: 02-streamlit-ui-shell
verified: 2026-05-29T00:00:00Z
status: human_needed
score: 18/18 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Run `uv run streamlit run app.py`, click Run with default settings, observe the probability table"
    expected: "CI mini-bars render visually under every probability number; numbers are monospace-aligned; table layout is readable"
    why_human: "AppTest cannot assert CSS rendering, pixel layout, or visual HTML output — only element tree presence"
  - test: "After a Run, inspect the status legend in Live mode (switch the toggle)"
    expected: "Blue `o live`, amber `x dead`, blue `/ secured` badges render in the browser with correct colours; colorblind-safe; never red/green"
    why_human: "Colorblind palette correctness requires eyeballing in a real browser; AppTest has no colour-rendering layer"
  - test: "Click Run with N=100000 (default) and time the wall-clock duration"
    expected: "Approximately 15 seconds with a live-updating progress bar showing the running sim count; never a blank spinner"
    why_human: "Wall-clock timing cannot be asserted in AppTest without brittle time.sleep thresholds"
  - test: "Run `uv run streamlit run app.py` from a cold shell (fresh clone, or on Mac/Linux)"
    expected: "App launches to the browser in one command on all three platforms with no errors"
    why_human: "Cross-OS launch (Windows/Mac/Linux) cannot be verified programmatically in a single environment"
  - test: "Open the README.md and read through the quickstart and cold-start drill sections"
    expected: "Prose is clear; the ordering matches DX-04 spec (what-it-is -> run command -> no-API-key note -> numbers meaning -> seed reconcile -> .env.example); cold-start drill is at the end and covers git pull -> confirm seeds -> flip toggle -> Run"
    why_human: "Documentation prose quality and DX-04 ordering correctness require human reading"
---

# Phase 2: Streamlit UI Shell — Verification Report

**Phase Goal:** A usable two-mode Streamlit app over the proven engine — editable ratings, S/N controls, Run, results table with always-visible CI mini-bars, [INFERRED]-seed safety banner, trust badge, and a zero-config first run that needs no API key.
**Verified:** 2026-05-29
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A fresh clone runs `uv run streamlit run app.py` with no API key and no editing (DX-01/DX-03) | VERIFIED | `app.py` imports `load_teams()` at module level using `data/stage1.json`; no httpx/python-dotenv installed; `test_zero_config_first_run` passes |
| 2 | Clicking Run computes the MC and renders per-team P(advance)/P(3-0)/P(0-3) (DX-01) | VERIFIED | `_drive_progress` iterates `run_mc_progressive`, result dispatches to `_render_probs_table`; `test_zero_config_first_run` asserts "advance" in markdown output |
| 3 | `locked` IS part of the cache key via `freeze_locked` (NOT underscore-excluded) so a changed `locked` yields a different cached output (UI-02 / Phase 2x4 seam) | VERIFIED | `ui/cache.py:47-64` — `locked_key` is a real positional arg in `@st.cache_data`; `test_locked_in_cache_key` passes (two distinct locked dicts -> two distinct `counts_advance` results) |
| 4 | `freeze_locked` round-trips: the reconstructed dict equals the original | VERIFIED | `ui/cache.py:25-34`; `test_freeze_locked_roundtrip` and `test_freeze_locked_order_independent` pass |
| 5 | Cache-miss progress loop does NOT re-chunk: n_chunks stays 20 and reproducibility holds (UI-03 / Phase 1x2 seam) | VERIFIED | `_drive_progress` calls `run_mc_progressive` with no `n_chunks` override; `test_progress_preserves_reproducibility` passes (progressive counts == direct run_mc counts; partials <= 20) |
| 6 | CR-01 fix: a single Run computes the MC exactly once (no double-compute on cache miss) | VERIFIED | `run_mc_cached` is not imported or called in `app.py`; `test_single_run_computes_mc_exactly_once` passes (spy confirms `run_mc_progressive` fires exactly once) |
| 7 | Empty or out-of-range rating blocks Run with inline message; engine never called (UI-05) | VERIFIED | `_run_or_serve` calls `validate_ratings` before any engine dispatch; `test_bad_rating_blocks_run` passes; `test_validate_ratings_rejects_empty_and_out_of_range` covers bounds 0 < r < 1000 |
| 8 | All four interaction states render for the run+probs feature: loading / empty-pre-run / error / success (UI-05) | VERIFIED | `app.py` has distinct branches for `result is None`, `error_msg`, and rendered result; `_render_probs_empty` shows EM_DASH; `_render_probs_table` shows CI bars |
| 9 | app.py is importable headlessly by AppTest with no import-time side effects (DX-03) | VERIFIED | All AppTest tests run without exception; no `if __name__ == "__main__"` patterns; `load_teams()` at module level is benign (reads local JSON) |
| 10 | Pre-stage / Live mode toggle is present and selects mode (UI-01) | VERIFIED | `st.segmented_control` wired to `ui.state.Mode`; `test_two_mode_toggle_present` and `test_mode_toggle_reorders_main_column` pass |
| 11 | Selecting Live mode reorders the main column to Live-first layout (UI-01) | VERIFIED | `app.py:333-383` — mode-conditional branches; `test_mode_toggle_reorders_main_column` asserts `Your picks — status` precedes `Delta probabilities` in Live |
| 12 | Every probability cell renders number + always-visible inline Wilson CI mini-bar (UI-04) | VERIFIED | `_render_probs_table` calls `ci_bar_html` for every cell; `test_ci_bars_on_every_cell_after_run` asserts >= 48 `position:absolute` bars (16 teams x 3 columns) |
| 13 | Status uses colorblind-safe blue/amber — NEVER red/green — always paired with ASCII glyph + text label (UI-06) | VERIFIED | `STATUS` dict in `ui/render.py:32-36` has exactly 3 states with hues only `#3B82F6`/`#F59E0B`; `test_status_palette_never_red_green` and `test_status_glyphs_are_ascii_only` pass |
| 14 | Trust badge reads EXACTLY `engine validated vs Valve rulebook unit tests — full backtest pending seed data`; `BACKTEST_PASSED=False`; gated on BOTH flags (UI-07) | VERIFIED | `TRUST_BADGE_CAVEATED` string matches verbatim in `ui/state.py:70-72`; `BACKTEST_PASSED=False` at line 64; `trust_badge_state` requires BOTH; `test_trust_badge_wording` passes (asserts exact string, Budapest-free, both-gated logic) |
| 15 | Persistent dismissable `⚠ Seeds are INFERRED` banner with field-by-field reconcile area; dismissed by `seeds_confirmed` toggle (DX-02) | VERIFIED | `_render_header_strip` in `app.py:68-127`; `test_seed_banner` asserts team names in reconcile area; `test_seed_banner_dismissable` confirms toggle dismisses warning |
| 16 | README quickstart in DX-04 order + 30-second event-day cold-start drill (DX-04) | VERIFIED | `README.md` starts with `uv run streamlit run app.py`, "no API key" note, ~15s expectation, numbers meaning, seed reconcile, .env.example section, ends with cold-start drill; `test_readme_quickstart_and_cold_start_drill` passes |
| 17 | `.env.example` lists optional provider keys; `.env` gitignored (DX-05) | VERIFIED | `.env.example` has `ODDSPAPI_KEY=`, `POLYMARKET_API_KEY=`, `KALSHI_API_KEY=`; `.gitignore` line 5 is `.env`; `test_env_example_present_and_gitignored` passes |
| 18 | Engine purity: ui imports engine, never the reverse; engine/ untouched; no httpx/network (DX-03 / architectural seam) | VERIFIED | No `import ui` / `from ui` in any `engine/*.py`; `uv run python -c "import httpx"` fails (ModuleNotFoundError); `ui/__init__.py` explicitly documents the import direction |

**Score:** 18/18 truths verified

---

### Deferred Items

None. The Live-mode placeholder (dead-end "Lock a result to go live") is the accepted user deferral per the 2026-05-29 user decision — Phase 4 fills it. This is not a gap.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pyproject.toml` | streamlit>=1.57,<1.58 in [project].dependencies | VERIFIED | Line 13: `"streamlit>=1.57,<1.58"` present |
| `.streamlit/config.toml` | [theme] dark base + primaryColor + codeFont monospace | VERIFIED | `[theme]` with `base="dark"`, `primaryColor="#7C5CFC"`, `codeFont="monospace"` |
| `app.py` | Streamlit entry, >= 60 lines | VERIFIED | 384 lines; controls, validated Run, progress dispatch, per-team probs, all four states, header strip, mode toggle |
| `ui/cache.py` | freeze_locked, freeze_ratings, run_mc_cached | VERIFIED | All three functions present; `locked_key` is a real cache-key arg (not `_locked`) |
| `ui/state.py` | Mode enum, validate_ratings, FIXED_SEED, BACKTEST_PASSED, trust_badge_state, read_seeds_confirmed, odds_key_present | VERIFIED | All exports present; BACKTEST_PASSED=False; TRUST_BADGE_CAVEATED exact string |
| `ui/render.py` | ci_bar_html, status_badge_html, STATUS, hero_number_html | VERIFIED | All present; STATUS has 3 colorblind-safe states; XSS guards in ci_bar_html and status_badge_html |
| `tests/test_ui_helpers.py` | Pure-function tests for seams | VERIFIED | 12 tests covering freeze_locked, freeze_ratings, validate_ratings, ci_bar_html, STATUS palette, status_badge_html, hero_number_html, run_mc_cached |
| `tests/test_app.py` | AppTest tests for all phase must-haves | VERIFIED | 24 tests including all critical seam tests listed in VALIDATION.md |
| `README.md` | DX-04 quickstart + cold-start drill | VERIFIED | Present; quickstart at top; cold-start drill at end |
| `.env.example` | Optional provider keys; .env gitignored | VERIFIED | All three provider keys listed; .env in .gitignore |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app.py` | `ui.state.validate_ratings` | Called in `_run_or_serve` before any engine dispatch | VERIFIED | `app.py:289` — `offenders = validate_ratings(edited)`; engine path only reached if offenders is empty |
| `app.py` | `engine.montecarlo.run_mc_progressive` | Cache-miss progress loop | VERIFIED | `app.py:193` — `gen = run_mc_progressive(teams, ratings, S, N, locked, seed=FIXED_SEED)`; no n_chunks override |
| `app.py` | `ui.render.ci_bar_html` | Per-team prob cells | VERIFIED | `app.py:229-240` — every P(advance)/P(3-0)/P(0-3) column uses `ci_bar_html(...)` |
| `app.py` | `ui.state.trust_badge_state` | Header strip badge | VERIFIED | `app.py:89` — `trust_badge_state(seeds_confirmed)` gates the badge display |
| `app.py` | `ui.state.Mode` | `st.segmented_control` | VERIFIED | `app.py:132-139` — control bound to `Mode.PRE_STAGE.value` / `Mode.LIVE.value` |
| `ui.cache.run_mc_cached` | `engine.montecarlo.run_mc` | Cached wrapper | VERIFIED | `ui/cache.py:64` — calls `run_mc(teams, ratings, S, N, locked=locked, seed=FIXED_SEED)` |
| `.gitignore` | `.env` | Secrets never committed | VERIFIED | `.gitignore` line 5: `.env` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `app.py._render_probs_table` | `result` (Result from engine) | `_drive_progress` via `run_mc_progressive` -> `StopIteration.value` | Yes — engine simulates N Swiss tournaments against real team ratings from `data/stage1.json` | FLOWING |
| `ui/cache.run_mc_cached` | `Result` | `engine.montecarlo.run_mc` with reconstructed ratings/locked dicts | Yes — full MC run, not a stub return | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full pytest suite passes | `uv run pytest -q` | 51 passed, 1 skipped (Budapest GATE-01 deferred — expected) | PASS |
| freeze_locked / status palette / trust badge unit tests | `uv run pytest -q tests/test_ui_helpers.py::test_status_palette_never_red_green tests/test_ui_helpers.py::test_freeze_locked_roundtrip tests/test_ui_helpers.py::test_status_badge_html_pairs_glyph_and_label` | 3 passed | PASS |
| Core AppTest seams: trust badge, seed banner, CI bars, CR-01, locked cache key, reproducibility | `uv run pytest -q tests/test_app.py::test_single_run_computes_mc_exactly_once tests/test_app.py::test_trust_badge_wording tests/test_app.py::test_seed_banner tests/test_app.py::test_seed_banner_dismissable tests/test_app.py::test_ci_bars_on_every_cell_after_run` | 5 passed | PASS |
| Zero-config run, cache hit, bad rating block, locked-in-key, reproducibility | `uv run pytest -q tests/test_app.py::test_zero_config_first_run tests/test_app.py::test_locked_in_cache_key tests/test_app.py::test_progress_preserves_reproducibility tests/test_app.py::test_bad_rating_blocks_run` | 4 passed | PASS |
| httpx absent (zero-config first-run promise) | `uv run python -c "import httpx"` | ModuleNotFoundError | PASS (absence confirmed) |
| Engine purity — no reverse imports | grep `import ui` in `engine/` | No matches | PASS |

---

### Probe Execution

No explicit probe scripts defined for this phase. Verification covered by pytest suite above.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| UI-01 | 02-02 | Two-mode toggle; main column reorders by mode | SATISFIED | `st.segmented_control` + mode-conditional ordering; `test_two_mode_toggle_present`, `test_mode_toggle_reorders_main_column` pass |
| UI-02 | 02-01 | @st.cache_data keyed on (ratings, S, N, locked) | SATISFIED | `freeze_locked` is real cache-key arg; `test_locked_in_cache_key`, `test_cache_hit_is_instant` pass |
| UI-03 | 02-01 | Progress bar + live P(advance) tally via MC generator | SATISFIED | `_drive_progress` iterates `run_mc_progressive` with no n_chunks override; `test_progress_preserves_reproducibility` pass |
| UI-04 | 02-01/02 | Always-visible inline CI mini-bars on every probability cell | SATISFIED | `ci_bar_html` in every cell of `_render_probs_table`; `test_ci_bars_on_every_cell_after_run` asserts >= 48 bars |
| UI-05 | 02-01 | All four interaction states; bad rating blocks run | SATISFIED | Four states implemented; `validate_ratings` gate; `test_bad_rating_blocks_run` pass |
| UI-06 | 02-02 | Monospace numbers; one accent; colorblind-safe blue/amber status; ASCII glyphs | SATISFIED (automated portion) | `STATUS` palette tested; ci_bar_html uses monospace; hero uses accent; visual render is Manual-Only |
| UI-07 | 02-03 | Trust badge with exact caveated wording; gated on BOTH BACKTEST_PASSED AND seeds_confirmed | SATISFIED | `TRUST_BADGE_CAVEATED` exact string; `BACKTEST_PASSED=False`; both-gated `trust_badge_state`; `test_trust_badge_wording` pass |
| DX-01 | 02-01 | data/stage1.json ships; first run needs no API key | SATISFIED | `data/stage1.json` present with 16 teams; no httpx/dotenv in deps; `test_zero_config_first_run` pass |
| DX-02 | 02-03 | Persistent dismissable [INFERRED]-seed banner with reconcile area | SATISFIED | `_render_header_strip` shows warning + expander with seed->team rows; toggle dismisses; `test_seed_banner`, `test_seed_banner_dismissable` pass |
| DX-03 | 02-01 | `uv run streamlit run app.py` bootstrap; Python >=3.12; no bash-only launcher | SATISFIED | `pyproject.toml` requires-python >=3.12; single command bootstrap; `test_zero_config_first_run` headless launch confirmed |
| DX-04 | 02-03 | README quickstart at top in DX-04 order + 30-second cold-start drill | SATISFIED | README structure matches spec; `test_readme_quickstart_and_cold_start_drill` pass |
| DX-05 | 02-03 | .env.example lists optional keys; .env gitignored | SATISFIED | `.env.example` has ODDSPAPI_KEY + Polymarket + Kalshi; .gitignore has `.env`; `test_env_example_present_and_gitignored` pass |

All 12 phase-2 requirements (UI-01..07, DX-01..05) are SATISFIED by automated evidence.

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `app.py` | `return null` / empty implementations | None found | N/A |
| `ui/render.py` | Hardcoded empty data | None found — all functions produce real HTML from inputs | N/A |
| `app.py:280-308` | `locked = {}` | Info only — intentional Phase 2x4 seam, documented in plan and SUMMARY | No impact — the cache-key shape is final; Phase 4 fills the dict |
| `ui/state.py:64` | `BACKTEST_PASSED = False` | Info only — explicit gate, not a stub | No impact — badge correctly caveated while GATE-01 is deferred |

No `TBD`, `FIXME`, or `XXX` debt markers found in any phase-2 modified files. No red/green palette values in `STATUS`. No `return {}` / `return []` hollow stubs — the `locked = {}` is an intentional forward-seam, not a hollow return.

The code review (02-REVIEW.md) identified 5 issues (CR-01, WR-01..04); all 5 were fixed per 02-REVIEW-FIX.md and verified by the post-fix suite (51 passed, 1 skipped). The two Info items (IN-01 dead `.get()` fallback, IN-02 sort inconsistency between empty/result tables) were intentionally left out of scope; neither affects correctness or the phase goal.

---

### Human Verification Required

#### 1. Visual CI Mini-Bars Under Every Probability Number

**Test:** Run `uv run streamlit run app.py`, click Run with default settings, observe the probability table in the browser.
**Expected:** Every probability cell shows the numeric percentage above a 4px horizontal bar spanning the Wilson confidence interval. Bars should always be visible (never hover/expand-hidden). Numbers should be monospace-aligned.
**Why human:** AppTest verifies the HTML is generated (48 `position:absolute` elements), but cannot render CSS or assert visual layout correctness.

#### 2. Colorblind-Safe Status Palette Renders Correctly in Browser

**Test:** After a Run, switch the toggle to Live mode and inspect the status legend.
**Expected:** `o live` and `/ secured` appear in blue; `x dead` appears in amber. No red or green anywhere. Glyphs and labels are always paired (colour is not the only signal).
**Why human:** `test_status_palette_never_red_green` confirms the hex values are `#3B82F6`/`#F59E0B` in code, but actual browser colour rendering, contrast ratio >= 4.5:1, and the visual "never red/green" contract require eyeballing in a real browser.

#### 3. ~15s Timing with Live Progress Bar (Not a Blank Spinner)

**Test:** Click Run with N=100000 (default) and observe the progress bar.
**Expected:** A progress bar showing `Simulating… X / 100,000` updates live during the ~15 second run. The bar fills progressively; the page does not freeze. After completion the table renders.
**Why human:** Wall-clock timing cannot be asserted reliably in AppTest; the "live-updating" quality of the progress bar requires watching the browser in real time.

#### 4. Cross-OS Launch

**Test:** Run `uv run streamlit run app.py` from a fresh clone on Mac or Linux (author environment is Windows).
**Expected:** App launches to the browser in one command on all three platforms. No OS-specific path or encoding errors.
**Why human:** Single-OS CI environment; cross-platform correctness requires running on another platform.

#### 5. README Prose Quality and DX-04 Order

**Test:** Read through the README from top to bottom.
**Expected:** The quickstart ordering feels natural (what-it-is -> run command -> no-API-key -> what numbers mean -> seed reconcile -> optional .env); the cold-start drill at the end is concise and actionable; the trust badge paragraph matches the in-app badge wording.
**Why human:** `test_readme_quickstart_and_cold_start_drill` checks for key strings but cannot assess prose clarity, ordering intuition, or whether a new user could follow it cold.

---

### Gaps Summary

No automatable gaps. All 18 must-have truths are VERIFIED by code inspection and the test suite (51 passed, 1 skipped — the single skip is the deferred Budapest GATE-01 which is explicitly accepted per the 2026-05-29 user decision and is not a Phase 2 responsibility).

The 5 Human Verification items above are all **Manual-Only** items per the phase's own 02-VALIDATION.md contract — they were never expected to be automatable and are not failures of the automated must-haves. The automated seams all hold.

---

_Verified: 2026-05-29_
_Verifier: Claude (gsd-verifier)_
