---
phase: 02-streamlit-ui-shell
reviewed: 2026-05-29T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - app.py
  - ui/cache.py
  - ui/state.py
  - ui/render.py
  - tests/test_app.py
  - tests/test_ui_helpers.py
findings:
  critical: 1
  warning: 4
  info: 2
  total: 7
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-05-29
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Reviewed the Phase 2 Streamlit UI shell: `app.py`, the `ui/` package (`cache.py`, `state.py`, `render.py`), and both test files. The two correctness seams (Phase 2x4 cache-key seam and Phase 1x2 progress seam) are structurally sound. The trust badge invariants hold. XSS guards in `render.py` are correct. Input validation blocks the engine on bad ratings.

One critical defect: the cache-miss path runs the full MC engine **twice** — once through `_drive_progress` (correct, shows the progress bar) and once again through `run_mc_cached` (broken "priming" call whose result is discarded and which silently doubles wall-clock time before the page renders). The cross-session `@st.cache_data` priming mechanism itself is architecturally sound in intent but the wiring has a gap.

Four warnings cover a dead state constant, a pre-broken trust badge branch, and two weak test assertions.

---

## Critical Issues

### CR-01: `run_mc_cached` priming call doubles computation time on every first Run

**File:** `app.py:296-299`

**Issue:** On every cache miss, `_run_or_serve` runs the full MC engine twice. `_drive_progress` runs `run_mc_progressive` (N sims, shows the progress bar, ~15 s for 100k). After it returns and the result is stored in `session_state`, `run_mc_cached(...)` is called to "prime the @st.cache_data memo" — but `run_mc_cached` internally calls `run_mc` (another full N-sim run, hidden from the user with `show_spinner=False`). Its **return value is never used**: the caller returns the `_drive_progress` result on the next line. The net effect is ~30 s of wall-clock freeze instead of ~15 s on first Run; the progress bar empties at the halfway mark and then the page remains visually frozen for another ~15 s before it updates.

The cross-session caching intent is partially sound: `@st.cache_data` persists across sessions while the server process lives, so a second new session with the same inputs would get a cheap `@st.cache_data` hit via `_drive_progress` + instant `run_mc_cached`. But the first-ever run in a process takes 2x the stated time with no user feedback.

```python
# app.py lines 295-300 (current — broken)
result = _drive_progress(ratings, S, int(N), locked)
cache[cache_key] = result
# Prime the cross-session @st.cache_data memo (Pattern 2 option B).
run_mc_cached(ratings_key, S, int(N), locked_key)   # <-- full re-run, result discarded
return result, None
```

**Fix — Option A (simplest, drop the priming call):** remove line 299. In-session deduplication via `session_state` is sufficient for Phase 2; if cross-session reuse is needed it can be wired correctly in a later phase.

```python
# app.py lines 295-299 (fixed)
result = _drive_progress(ratings, S, int(N), locked)
cache[cache_key] = result
return result, None
```

**Fix — Option B (keep cross-session reuse):** make `run_mc_cached` the primary compute path and keep the progress bar as a pre-flight. The cache miss path calls `_drive_progress` for the bar then immediately returns `run_mc_cached(...)`, whose `@st.cache_data` result is stored and served. The session-state layer is still used for deduplication within a session.

---

## Warnings

### WR-01: `KEY_N_INPUT` constant is defined but never used — key is hardcoded in `app.py`

**File:** `ui/state.py:51` and `app.py:174`

**Issue:** `ui/state.py` defines `KEY_N_INPUT = "N_input"` as the single source of truth for the N number-input's session key. But `app.py` never imports `KEY_N_INPUT`; the widget is created with the literal string `key="N_input"` at line 174. All other widget keys use the imported constants (`KEY_S_SLIDER`, `KEY_RUN_BUTTON`, etc.). If the string ever needs to change it must be updated in two places, and the constant is dead code.

```python
# ui/state.py line 51 (currently a dead constant)
KEY_N_INPUT = "N_input"

# app.py line 174 (hardcoded, should use the constant)
N = st.number_input(..., key="N_input")   # should be key=KEY_N_INPUT
```

**Fix:** Import `KEY_N_INPUT` alongside the other key constants in `app.py` and use it:

```python
# app.py imports — add KEY_N_INPUT
from ui.state import (
    ..., KEY_N_INPUT, KEY_S_SLIDER, ...
)

# app.py line 174
N = st.number_input(..., key=KEY_N_INPUT)
```

---

### WR-02: Validated trust badge branch renders the wrong text with a spurious `/` prefix

**File:** `app.py:87-88`

**Issue:** The "validated" branch of the trust badge (line 88) is unreachable today (`BACKTEST_PASSED = False`), but it is pre-broken for the phase when `BACKTEST_PASSED` is flipped to `True`. The branch renders:

```python
st.success(f"/ {TRUST_BADGE_CAVEATED}")
```

This produces `st.success` (a **green box**) containing: `/ engine validated vs Valve rulebook unit tests — full backtest pending seed data`. Two problems:

1. The displayed text is `TRUST_BADGE_CAVEATED` — which explicitly says "backtest pending" — shown inside a green "validated" visual container. The visual and the text directly contradict each other.
2. The leading `"/ "` is unexplained and appears to be a stray glyph or cut-and-paste artefact. It would render literally as `/ engine validated…`.

The "validated" state needs its own dedicated string (e.g. `TRUST_BADGE_VALIDATED = "engine validated vs Valve rulebook unit tests + Budapest round-by-round backtest"`) so flipping `BACKTEST_PASSED = True` does not produce a self-contradicting badge.

**Fix:**

```python
# ui/state.py — add after TRUST_BADGE_CAVEATED
TRUST_BADGE_VALIDATED = (
    "engine validated vs Valve rulebook unit tests + full round-by-round backtest"
)

# app.py line 87-91
if trust_badge_state(seeds_confirmed) == "validated":
    st.success(TRUST_BADGE_VALIDATED)       # green + consistent text
else:
    st.caption(TRUST_BADGE_CAVEATED)        # neutral caption, no change
```

---

### WR-03: `test_ci_bars_on_every_cell_after_run` lower-bound assertion is too weak to catch regressions

**File:** `tests/test_app.py:171`

**Issue:** The test comment says "16 teams x 3 prob columns = 48 inline CI bars (a generous lower bound guards regressions)" but the actual assertion is `>= 16`, not `>= 48`. If a regression caused only one column to render bars (16 bars total) the test would still pass. The comment's stated intent and the actual assertion are mismatched — `>= 16` would only catch complete loss of CI bars, not partial loss.

```python
# test_app.py line 172-173 (current — too weak)
bar_markup = [m for m in at.markdown if "position:absolute" in m.value]
assert len(bar_markup) >= 16   # passes even if 2 of 3 columns lost their bars
```

**Fix:** Match the assertion to the stated intent:

```python
# 16 teams * 3 prob columns = 48 CI bars; >= 48 is the correct regression guard.
assert len(bar_markup) >= 48
```

---

### WR-04: `test_status_badge_html_pairs_glyph_and_label` glyph assertion is vacuously true

**File:** `tests/test_ui_helpers.py:138`

**Issue:** The test asserts `assert "/" in html` to verify the `"advanced"` status glyph. But the rendered HTML string is:

```
<span style="color:#3B82F6;font-family:ui-monospace,monospace">/ secured</span>
```

The `</span>` closing tag also contains `"/"`, so `"/" in html` is always `True` regardless of what the glyph is. If the glyph were changed to `"X"` the assertion would still pass (the `</span>` alone would satisfy it). The assertion does not actually verify the glyph.

```python
# test_ui_helpers.py line 138 (current — vacuously true)
assert "/" in html          # always True due to </span>
```

**Fix:** Assert the glyph appears in the text content, not anywhere in the HTML:

```python
from ui.render import STATUS
glyph, label, _ = STATUS["advanced"]
# Verify glyph appears as text content, not just as part of an HTML closing tag.
assert f">{glyph} {label}<" in html   # matches ">/ secured<" in the span's text content
```

---

## Info

### IN-01: `.get()` fallback in `_render_header_strip` is unreachable dead code

**File:** `app.py:84`

**Issue:** The `False` default in `st.session_state.get(KEY_SEEDS_CONFIRMED, False)` is unreachable. Lines 81-83 unconditionally ensure `KEY_SEEDS_CONFIRMED` is set in `session_state` before line 84 is evaluated (either just written on line 83, or already present from a prior rerun). The `.get(..., False)` guard is therefore dead code that cannot execute.

```python
# app.py lines 81-84
if KEY_SEEDS_CONFIRMED not in st.session_state:
    st.session_state[KEY_SEEDS_CONFIRMED] = read_seeds_confirmed()
# The False default here is never reached:
seeds_confirmed = bool(st.session_state.get(KEY_SEEDS_CONFIRMED, False))
```

**Fix:** Use direct access since the key is guaranteed present:

```python
seeds_confirmed = bool(st.session_state[KEY_SEEDS_CONFIRMED])
```

---

### IN-02: Empty-state table uses seed order; result table uses P(advance) order — inconsistent sort

**File:** `app.py:249` vs `app.py:211`

**Issue:** `_render_probs_empty` iterates `for t in teams:` (module-level seed-ordered list), showing teams in ascending seed order. `_render_probs_table` sorts teams by descending `P(advance)`. When the user clicks Run, the table reorders, which can be disorienting if they were scanning a particular row's position. Neither ordering is wrong in isolation, but the pre-run and post-run tables should use the same order so positions are stable.

**Fix:** Sort the empty-state rows by seed as well to make both states seed-ordered, or (preferred) sort both by the same stable key (e.g. seed descending). The reorder on first Run is avoidable by sorting the empty table identically to how the result table would sort with all-equal probabilities:

```python
# _render_probs_empty: match the result table's sort key (ties break by seed)
for t in sorted(teams, key=lambda x: x.seed):
    ...
```

---

_Reviewed: 2026-05-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
