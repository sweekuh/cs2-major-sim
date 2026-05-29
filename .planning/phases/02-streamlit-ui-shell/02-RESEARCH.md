# Phase 2: Streamlit UI Shell - Research

**Researched:** 2026-05-28
**Domain:** Streamlit 1.57 frontend over a proven headless numpy MC engine — caching, editable tables, generator-driven progress, theming, and headless app testing
**Confidence:** HIGH (Streamlit API specifics verified against current docs.streamlit.io; engine contract verified against committed Phase-1 code)

## Summary

Phase 2 is a thin Streamlit shell over a finished, frozen engine. The design is already locked (02-UI-SPEC + HANDOFF §10.5/§10.6); this research resolves the **Streamlit 1.57 API mechanics** the planner needs and **how to test a Streamlit app headlessly**. The engine seam is exact and committed: `engine.montecarlo.run_mc_progressive(teams, ratings, S, N, locked, *, seed, n_chunks=20)` is a generator yielding `Partial(done, total, running_p_adv)` per chunk and returning a `Result`; `run_mc(...)` drains it. The UI wraps `run_mc` in `@st.cache_data` for hits and iterates `run_mc_progressive` directly for the progress bar on misses.

The single highest-risk item is the **unhashable `locked` dict in the cache key** (UI-02, Phase 2×4 seam). Streamlit hashes positional/keyword args to build the cache key and raises `UnhashableParamError` on a raw dict. The leading-underscore escape hatch (`_locked`) is the WRONG fix here — it *excludes* the arg from the key, which is exactly the stale-results bug the seam exists to prevent (Pitfall 13). The correct pattern is to convert `locked` to a deterministic hashable form (a sorted tuple of `(sorted-tuple-pair, winner)`) at the UI boundary, key the cache on that, and reconstruct the dict inside the cached wrapper.

Every other API question resolves cleanly: `st.segmented_control` is GA (since 1.56), `st.data_editor` + `st.column_config.NumberColumn` handle the 16-team editable table with built-in numeric validation, `st.progress` returns an updatable handle, config.toml 1.57 theming now exposes `font`/`codeFont`/`headingFont` + a full color palette + `primaryColor`/`backgroundColor`/`secondaryBackgroundColor`, and `streamlit.testing.v1.AppTest` is the official headless test harness (asserts widgets/values/reruns/exceptions/session_state — but NOT CSS or pixels).

**Primary recommendation:** Build `app.py` as a single-page two-mode shell. Convert `locked` to a hashable tuple before the cached call; wrap `run_mc` (not `run_mc_progressive`) in `@st.cache_data`; drive `st.progress` by iterating `run_mc_progressive` on a miss. Theme via `.streamlit/config.toml` (`base="dark"`, `primaryColor="#7C5CFC"`, `codeFont="monospace"`); render CI mini-bars as inline HTML in `st.markdown(unsafe_allow_html=True)`. Test with `AppTest`; route all visual acceptance (CI-bar rendering, colorblind palette) to VALIDATION.md Manual-Only.

## Architectural Responsibility Map

This is a single-process Streamlit app (one tier: the Streamlit server runs the Python that holds the engine). The meaningful boundary is **UI layer (`app.py`) vs. engine core (`engine/`)** — `app.py` imports `engine`, never the reverse (functional-core purity, CLAUDE.md).

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Widget rendering, mode toggle, layout | UI (`app.py`) | — | Pure Streamlit; no engine concern |
| Ratings editing + cell validation | UI (`app.py`) | — | `st.data_editor`; engine receives a clean `{id: rating}` dict |
| Cache-key construction (hashable `locked`) | UI (`app.py`) | — | UI owns the boundary translation; engine stays dict-native |
| MC computation | engine (`run_mc` / `run_mc_progressive`) | — | Frozen Phase-1 core; UI must not re-chunk or re-seed |
| Progress reporting | UI consumes engine `Partial` | engine yields `Partial` | Engine already emits per-chunk Partials; UI maps them to `st.progress` |
| Probability → number + CI-bar render | UI (`app.py`) | engine provides `band_*` | Engine computes Wilson bands; UI renders them as inline bars |
| Seed/odds banners, trust badge | UI (`app.py`) | `engine.teams` flags [INFERRED] | Pure presentation + the seeds-confirmed `session_state` flag |
| Fixture load / default ratings | `engine.teams.load_teams()` | UI calls it | DX-01 zero-config; engine already loads `data/stage1.json` w/ fallback |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| streamlit | `>=1.57,<1.58` (current 1.57.0, Apr 28 2026) | UI shell, widgets, caching, theming | [CITED: pypi.org/project/streamlit] Project-pinned (CLAUDE.md, STACK.md). Only option holding the keyed odds calls later; `@st.cache_data` semantics unchanged in the 2026 release. |
| numpy | `>=2.4,<2.5` (current 2.4.6) | Already a transitive dep via the engine | [VERIFIED: engine code imports numpy] No new use in `app.py` directly; engine owns it. |

No new runtime packages are introduced in Phase 2. `httpx` / `python-dotenv` are Phase-5 only and MUST NOT be imported by the first-run path (DX zero-config promise).

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | `>=9,<10` (already pinned, dev) | Run `AppTest`-based UI tests | [VERIFIED: pyproject.toml dev group] AppTest tests live under `tests/` and run via the existing pytest harness. |

`streamlit.testing.v1.AppTest` ships **inside** the `streamlit` package — no extra test dependency needed. [CITED: docs.streamlit.io/develop/api-reference/app-testing]

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `st.segmented_control` | `st.radio(horizontal=True)` | Locked-in fallback per UI-SPEC §Open-Items #2. Radio is older/more universal but reads as a form field, not a mode switch. segmented_control is GA — use it. |
| `st.data_editor` | `st.number_input` × 16 | 16 individual inputs is a `st.metric` mosaic anti-pattern (UI-06 forbids it); data_editor gives an aligned monospace table. Use data_editor. |
| pandas DataFrame for the editor | list-of-dicts | STACK.md forbids pandas. `st.data_editor` accepts a list-of-dicts and returns the same type. Use list-of-dicts. |
| Inline-HTML CI bars | `st.column_config.ProgressColumn` | ProgressColumn renders ONE bar per cell but can't sit *beneath* a monospace number in the same cell, and styling is fixed. Inline HTML in `st.markdown` is the only way to get the "number + thin bar under it" layout (UI-04). |

**Installation:** No install action. `streamlit` is pinned in `pyproject.toml` by adding it to `[project].dependencies` (it is currently absent — Phase 1 was engine-only with just numpy). The planner MUST add `streamlit>=1.57,<1.58` to `pyproject.toml`.

**Version verification (run during planning, do not trust this doc's date):**
```bash
pip index versions streamlit    # confirm 1.57.x is still current
```
Confirmed 1.57.0 (Apr 28 2026) current at research time. [CITED: pypi.org/project/streamlit]

## Package Legitimacy Audit

Only one new package (`streamlit`) is introduced, and it is a top-tier, project-mandated dependency already vetted in `.planning/research/STACK.md`. slopcheck not run (single well-known package; no hallucination surface).

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| streamlit | PyPI | ~6 yrs (since 2019) | ~5M+/wk | github.com/streamlit/streamlit | not run (canonical) | Approved — CLAUDE.md-mandated |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                          .streamlit/config.toml  (theme: dark base, #7C5CFC accent,
                          codeFont monospace)  ── read once at startup by Streamlit
                                   │
  USER widget change ──► Streamlit reruns app.py top-to-bottom (every interaction)
                                   │
        ┌──────────────────────────────────────────────────────────────────┐
        │  app.py  (UI layer — imports engine, never imported by engine)     │
        │                                                                    │
        │  load_teams() ──► editable ratings (st.data_editor + NumberColumn) │
        │      │                       │                                     │
        │  mode = st.segmented_control("Pre-stage" / "Live")                 │
        │  S = st.slider     N = st.number_input    locked = {} (Phase 4)    │
        │      │                                                             │
        │  [Run ▶] clicked? ──► validate ratings ──bad cell──► block + error │
        │      │ (valid)                                                     │
        │      ▼                                                             │
        │  locked_key = freeze_locked(locked)   # dict ─► hashable tuple     │
        │      │                                                             │
        │  ┌── CACHE HIT ───────────────┐   ┌── CACHE MISS ────────────────┐ │
        │  │ run_mc_cached(ratings_key, │   │ iterate run_mc_progressive(  │ │
        │  │   S, N, locked_key)        │   │   teams, ratings, S, N,      │ │
        │  │ ─► Result (instant)        │   │   locked, seed=FIXED)        │ │
        │  └────────────┬───────────────┘   │ per Partial:                 │ │
        │               │                   │   st.progress(done/total)    │ │
        │               │                   │   show running_p_adv tally   │ │
        │               │                   │ on StopIteration ─► Result   │ │
        │               │                   │ then store via run_mc_cached │ │
        │               │                   └────────────┬─────────────────┘ │
        │               └───────────────┬────────────────┘                   │
        │                               ▼                                     │
        │   render: hero P(≥5) · per-team table (number + inline CI bar via   │
        │   st.markdown unsafe_allow_html) · bracket shell · banners · badge  │
        └──────────────────────────────────────────────────────────────────┘
                                   │ imports
                                   ▼
        engine/  (FROZEN functional core — montecarlo / swiss / teams / probs)
        run_mc_progressive(...)->Iterator[Partial], returns Result
        run_mc(...)->Result   |  load_teams()->list[Team]   |  Result.band_*
```

### Recommended Project Structure
```
swiss-mc/
├── app.py                  # NEW — single-page Streamlit entry (the whole Phase-2 deliverable)
├── ui/                     # OPTIONAL — extract pure helpers here so they're AppTest-free unit-testable
│   ├── __init__.py
│   ├── cache.py            # freeze_locked(), run_mc_cached (the @st.cache_data wrapper)
│   ├── render.py           # ci_bar_html(), status_glyph(), number formatting
│   └── state.py            # mode enum, session_state keys, validation helpers
├── .streamlit/
│   └── config.toml         # NEW — [theme] base=dark, primaryColor, font/codeFont
├── engine/                 # FROZEN (Phase 1) — do not modify
├── data/stage1.json        # FROZEN (Phase 1) — DX-01 zero-config fixture
├── tests/
│   ├── test_app.py         # NEW — AppTest-based UI tests
│   └── test_ui_helpers.py  # NEW — pure-function tests (freeze_locked, ci_bar_html, validation)
└── pyproject.toml          # MODIFY — add streamlit>=1.57,<1.58 to [project].dependencies
```

Extracting pure helpers into `ui/` is recommended but not mandatory: pure functions (`freeze_locked`, CI-bar HTML, rating validation) are unit-testable without `AppTest`, which is faster and more precise than driving them through the full app. Keep `app.py` thin enough to read top-to-bottom.

### Pattern 1: Hashable `locked` cache key (THE correctness pattern — UI-02 / Phase 2×4 seam)
**What:** `@st.cache_data` hashes each argument to build the key. A raw `dict` raises `UnhashableParamError`. The leading-underscore escape (`_locked`) silences the error but **excludes the arg from the key** — which silently serves stale pre-lock distributions in Live mode (Pitfall 13, the exact bug the seam forbids). The correct fix is to pass a deterministic **hashable** representation and reconstruct inside.

**When to use:** Always, from Phase 2 — `locked` is `{}` now but the key shape must be final so Phase 4 is a no-op data change, not a re-architecture.

**Example:**
```python
# Source: pattern derived from docs.streamlit.io/develop/concepts/architecture/caching
#         (UnhashableParamError + hashing rules) applied to the frozen engine seam.
import streamlit as st
from engine.montecarlo import run_mc
from engine.teams import load_teams

def freeze_locked(locked: dict) -> tuple:
    """dict[frozenset({a,b}) -> winner_id]  ->  a deterministic hashable key.

    Sort each pair's members AND sort the pairs, so the key is order-independent:
    {frozenset({9,1}): 1}  and  {frozenset({1,9}): 1}  produce the SAME tuple.
    """
    return tuple(sorted(
        (tuple(sorted(pair)), winner) for pair, winner in locked.items()
    ))

def freeze_ratings(ratings: dict[int, float]) -> tuple:
    """{id: rating} -> sorted tuple of (id, rating). Same order-independence rationale."""
    return tuple(sorted(ratings.items()))

@st.cache_data(show_spinner=False)   # we drive our OWN progress bar; suppress the default
def run_mc_cached(ratings_key: tuple, S: float, N: int, locked_key: tuple):
    """Cached final result. Key = (ratings_key, S, N, locked_key) — all hashable.
    Reconstruct the dicts the engine wants from the hashable keys, then call the
    FROZEN run_mc (which itself drains run_mc_progressive with the pinned n_chunks=20)."""
    ratings = dict(ratings_key)
    locked = {frozenset(pair): winner for pair, winner in locked_key}
    teams = load_teams()
    return run_mc(teams, ratings, S, N, locked=locked, seed=20260528)
```
**Why NOT `_locked`:** `def run_mc_cached(..., _locked)` would make the cache key blind to locks; locking a real result in Phase 4 would return the cached pre-lock `Result` and **no P(advance) would move** — directly failing RESIM-01's detection criterion ("locking a result must move at least one P(advance) value"). [VERIFIED: docs.streamlit.io caching — "prepend the parameter name with an underscore ... it will not be used for caching"]

### Pattern 2: Generator-driven progress on a cache miss (UI-03, the design×eng seam)
**What:** On a miss, iterate the FROZEN `run_mc_progressive` directly to feed `st.progress`; capture the returned `Result` via `StopIteration.value`; then prime the cache so the *next* identical call hits. Do NOT re-chunk or change `n_chunks` (Phase 1×2 reproducibility seam).

**When to use:** The Run / Re-sim cache-miss path only. Cache hits skip this entirely.

**Example:**
```python
# Source: st.progress loop (docs.streamlit.io/.../st.progress) + frozen engine generator
#         contract (engine/montecarlo.py run_mc_progressive yields Partial, returns Result).
from engine.montecarlo import run_mc_progressive

def run_with_progress(teams, ratings, S, N, locked):
    bar = st.progress(0, text="Simulating…")
    gen = run_mc_progressive(teams, ratings, S, N, locked, seed=20260528)  # n_chunks defaults to 20 — DO NOT override
    result = None
    try:
        while True:
            p = next(gen)                        # p: Partial(done, total, running_p_adv)
            frac = p.done / p.total
            bar.progress(frac, text=f"Simulating… {p.done:,} / {p.total:,}")
            # running_p_adv is per-team {id: float}; surface a live tally (e.g. top team)
    except StopIteration as stop:
        result = stop.value                      # the final Result
    bar.empty()
    return result
```
Note: `st.progress` accepts a float `0.0–1.0` or int `0–100`. [VERIFIED: docs.streamlit.io/.../st.progress] The seed is **fixed** (`20260528`, matching the engine's `__main__` smoke run) so reruns are reproducible and the cache key need not include it; if the planner wants per-session variety, add `seed` to the cache key — but a fixed seed is correct for a deterministic tool.

**Caching the miss result:** after `run_with_progress` produces `Result`, call `run_mc_cached(ratings_key, S, N, locked_key)` so the value is memoized. Because `run_mc_cached` itself recomputes via `run_mc`, the simplest correct shape is: on a miss show the progress bar by iterating `run_mc_progressive`, but ALSO let `run_mc_cached` be the single source the render reads from. Two clean options for the planner:
- **(A, simplest)** Always render from `run_mc_cached(...)`. To get a progress bar, check the cache first via a session flag, and on the first computation run `run_with_progress` purely for the bar, then call `run_mc_cached` (it recomputes once — ~15s — but is then memoized). Downside: the very first run computes the MC twice.
- **(B, recommended)** Use `@st.cache_data` with a manual store: run `run_with_progress` to get the `Result` + bar, then stash it with `st.cache_data`'s programmatic API is not ideal — instead keep `Result` in `st.session_state` keyed by `(ratings_key, S, N, locked_key)`. Render from `session_state`. This computes the MC exactly once per unique key AND drives the bar. The `@st.cache_data` decorator is still used for any pure derived values.

The planner should pick **(B)**: a `session_state` dict keyed on the same `(ratings_key, S, N, locked_key)` tuple gives both single-compute-per-key and a real progress bar, and survives reruns within a session. `@st.cache_data` on `run_mc_cached` remains the cross-session/cleaner fallback if double-compute is acceptable. Document this tradeoff in the plan; do not let it become an accidental double-run on every miss.

### Pattern 3: Editable ratings table with blocking validation (UI-02 / UI-05)
**What:** `st.data_editor` with `column_config={"rating": st.column_config.NumberColumn(...)}` and `num_rows="fixed"`. It returns the edited structure in its original type (list-of-dicts in, list-of-dicts out). [VERIFIED: docs.streamlit.io/.../st.data_editor]

**When to use:** The controls column, both modes.

**Example:**
```python
# Source: docs.streamlit.io/develop/api-reference/data/st.data_editor + st.column_config.NumberColumn
rows = [{"seed": t.seed, "team": t.name, "rating": t.rating} for t in teams]
edited = st.data_editor(
    rows,
    num_rows="fixed",                       # can't add/delete the 16 teams
    disabled=["seed", "team"],              # only rating is editable
    column_config={
        "seed":   st.column_config.NumberColumn("Seed", disabled=True),
        "team":   st.column_config.TextColumn("Team", disabled=True),
        "rating": st.column_config.NumberColumn(
            "Rating", min_value=1, max_value=999, step=1, format="%d"
        ),
    },
    key="ratings_editor",
)
ratings = {r["seed"]: r["rating"] for r in edited}
```

**Validation nuance (IMPORTANT for UI-05 copy):** `NumberColumn` performs **built-in client-side validation** — it restricts the cell to numeric input and *ignores* pasted non-numeric text. [VERIFIED: docs.streamlit.io/.../st.column_config.NumberColumn + discuss.streamlit.io]. So the UI-SPEC's "Ratings must be numbers. Fix the highlighted cell, then Run." error for a *non-numeric* cell is **largely pre-empted by the widget** — a user cannot easily type letters into a NumberColumn. The realistic "bad cell" failure modes that the app MUST still block are:
- An **empty / `None`** rating cell (deleting a value leaves `None`; `NumberColumn` may then return unexpected types — see streamlit#13305). Validate `r["rating"] is None` → block Run with the inline error.
- A rating **out of range** (the engine's `_validate_fixture` rejects ratings outside `0 < r < 1000` and raises `ValueError`). Mirror that bound in `min_value`/`max_value` AND re-check before Run so a bad value never reaches the engine as an exception.
The planner should therefore treat UI-05's "bad rating cell" as **empty-or-out-of-range**, validate the returned `edited` rows in `app.py` before constructing `ratings`, and block the Run button (show the inline error) if any fail. Don't rely on the widget alone.

### Anti-Patterns to Avoid
- **Passing the raw `locked` dict to `@st.cache_data`:** raises `UnhashableParamError`. Convert with `freeze_locked` first.
- **Using `_locked` to silence the error:** silently drops `locked` from the key → stale Live-mode results (Pitfall 13). Never do this.
- **Re-chunking the progress loop / changing `n_chunks`:** breaks Phase-1 reproducibility (Phase 1×2 seam). Iterate `run_mc_progressive` as-is; it yields exactly `n_chunks=20` Partials.
- **`st.metric` card mosaic for the 16 teams:** UI-06 explicitly forbids equal-weight cards. Use the dense data_editor / table; the hero P(≥5) is the only big number.
- **`@st.cache_data` with `show_spinner=True` while also showing your own progress bar:** double UI. Set `show_spinner=False` on the cached function.
- **Importing `httpx`/`python-dotenv` at module top in `app.py`:** breaks the DX zero-config first-run promise. The odds path is a banner stub only in Phase 2.
- **Mutating `engine/`:** the core is frozen and AppTest-purity-checked. UI imports engine; never the reverse.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Memoizing the 15s MC across reruns | A manual dict cache with hand-rolled key hashing | `@st.cache_data` (+ `freeze_locked` for the dict arg) | Streamlit reruns the whole script on every widget change; cache_data is the purpose-built, reruns-aware memoizer. |
| Editable 16-row numeric grid | 16 `st.number_input`s in a loop | `st.data_editor` + `NumberColumn` | Built-in numeric validation, alignment, fixed rows, single return structure. |
| Mode toggle | Two buttons + manual session_state | `st.segmented_control` | GA, single-select, returns the chosen option directly. |
| Progress UI | A manual `st.empty()` + percentage math from scratch | `st.progress(...)` handle + the engine's `Partial.done/total` | Engine already computes `done`/`total`; just map to the bar. |
| Headless UI tests | Selenium / Playwright browser automation | `streamlit.testing.v1.AppTest` | Official in-process harness; no browser, fast, asserts the element tree + session_state. |
| Wilson CI math | A new CI implementation in the UI | `Result.band_30/band_advance/band_03` | Engine already computed Wilson bands (MC-02). UI only renders them. |
| Fixture loading / defaults | Re-reading `stage1.json` in `app.py` | `engine.teams.load_teams()` | Already validates + falls back to in-code defaults (DX-01). |

**Key insight:** Phase 2 should add almost no logic — it is presentation + a cache boundary + a progress loop over an already-correct generator. The two genuinely new pieces of *code* are `freeze_locked` (the cache-key translation) and the inline CI-bar HTML; everything else is wiring existing Streamlit widgets to the frozen engine API.

## Common Pitfalls

### Pitfall 1: `UnhashableParamError` on the `locked` dict
**What goes wrong:** `@st.cache_data` raises at the first Run because `dict` (and `frozenset` keys) aren't hashed by default.
**Why it happens:** Streamlit hashes args to form the key; dicts are mutable/unhashable. [VERIFIED: docs.streamlit.io/develop/concepts/architecture/caching]
**How to avoid:** Pattern 1 — `freeze_locked(locked)` → sorted tuple, key the cache on that, reconstruct inside.
**Warning signs:** Exception on first Run mentioning "Cannot hash argument".

### Pitfall 2: Stale Live-mode results (the Phase 2×4 seam, Pitfall 13)
**What goes wrong:** Locking a real result returns the cached pre-lock distribution; no probability moves.
**Why it happens:** `locked` omitted from the cache key (e.g. via `_locked`, or forgetting to include `locked_key`).
**How to avoid:** Include `locked_key` in the cache key from Phase 2, even though `locked == {}` now. Phase 4 detection: locking must move ≥1 P(advance) (RESIM-01).
**Warning signs:** In Phase 4, a lock changes nothing on screen.

### Pitfall 3: MC runs twice on every cache miss
**What goes wrong:** The miss path runs `run_mc_progressive` for the bar AND then `run_mc_cached` recomputes — ~30s instead of ~15s.
**Why it happens:** Naively combining "drive the bar" + "memoize" computes the result twice.
**How to avoid:** Pattern 2 option (B) — stash the `Result` from the progress loop in `session_state` keyed by the same tuple; render from there; compute once.
**Warning signs:** First Run feels ~2× the expected ~15s.

### Pitfall 4: Reproducibility break from re-chunking the progress loop
**What goes wrong:** Changing `n_chunks` or splitting differently to "smooth" the bar changes the per-team counts.
**Why it happens:** `SeedSequence(seed).spawn(n_chunks)` reproducibility depends on `(seed, n_chunks)`; the backtest validated `n_chunks=20`. [VERIFIED: 01-03-SUMMARY.md + engine code]
**How to avoid:** Never pass a different `n_chunks`; iterate the generator as-is (20 Partials).
**Warning signs:** Same inputs give different numbers across sessions.

### Pitfall 5: "Bad rating cell" error never fires (UI-05)
**What goes wrong:** Planner writes a test for typing letters into the rating column; `NumberColumn` ignores it, so the error path is dead.
**Why it happens:** `NumberColumn` does built-in numeric validation — non-numeric text is rejected/ignored at the widget. [VERIFIED: discuss.streamlit.io + docs]
**How to avoid:** Define the "bad cell" as **empty/`None` or out-of-range** rating (the cases the widget *does* allow), validate `edited` rows in `app.py`, block Run on failure.
**Warning signs:** UI-05 acceptance test can't reach the error branch.

### Pitfall 6: Trust badge claims more than is true
**What goes wrong:** Badge shows a green ✓ "validated vs Budapest backtest".
**Why it happens:** GATE-01/04 are DEFERRED (seeds unsourceable); the backtest never ran. [VERIFIED: STATE.md 2026-05-29 decision]
**How to avoid:** Badge MUST read **"engine validated vs Valve rulebook unit tests — full backtest pending seed data"** and be tied to BOTH (a) backtest-passed (currently false) AND (b) seeds-confirmed toggle. In Phase 2 both are unmet → badge ships in caveated form (UI-07, Pitfall "both not one").
**Warning signs:** Badge text mentions "Budapest"/"Austin backtest" or shows a green checkmark.

### Pitfall 7: AppTest can't see the CI bars
**What goes wrong:** A test asserts the CI mini-bar renders visually and fails.
**Why it happens:** `AppTest` inspects the element tree, not CSS/pixels. [VERIFIED: docs.streamlit.io app-testing]
**How to avoid:** Assert the CI bar's *presence as markdown/HTML content* (the `<div>` string is in `at.markdown[i].value`); route actual *visual* rendering + color to VALIDATION.md Manual-Only.
**Warning signs:** A test tries to check bar width/color in pixels.

## Code Examples

### CI mini-bar under a monospace number (UI-04 / UI-06)
```python
# Source: st.markdown(unsafe_allow_html=True) — Streamlit-sanctioned for custom inline HTML.
# Renders: a right-aligned monospace number with a thin 4px Wilson bar beneath it.
def ci_bar_html(p: float, lo: float, hi: float, hue: str = "#3B82F6") -> str:
    pct = f"{p*100:.1f}%"
    left = max(0.0, lo) * 100
    width = max(0.0, (hi - lo)) * 100
    return (
        f'<div style="font-family:ui-monospace,monospace;text-align:right">{pct}</div>'
        f'<div style="height:4px;background:#3A3D46;border-radius:2px;position:relative">'
        f'  <div style="position:absolute;left:{left:.1f}%;width:{width:.1f}%;'
        f'height:4px;background:{hue};border-radius:2px"></div>'
        f'</div>'
    )
st.markdown(ci_bar_html(0.82, 0.80, 0.84), unsafe_allow_html=True)
```
Use the **status hue at full opacity** for the filled portion and `#3A3D46` for the track (UI-SPEC Color §contrast). `unsafe_allow_html=True` is required for raw HTML; this is the standard Streamlit technique when native widgets can't express the layout.

### Status glyph + label (colorblind-safe, ASCII — UI-06)
```python
# ASCII-only glyphs survive the Windows cp1252 console lesson from Phase 1.
STATUS = {
    "advanced":   ("/", "secured",  "#3B82F6"),   # blue
    "live":       ("o", "live",     "#3B82F6"),
    "eliminated": ("x", "dead",     "#F59E0B"),   # amber — NEVER red/green
}
glyph, label, hue = STATUS["advanced"]
st.markdown(f'<span style="color:{hue}">{glyph} {label}</span>', unsafe_allow_html=True)
```

### `.streamlit/config.toml` theme (1.57)
```toml
# Source: docs.streamlit.io/develop/api-reference/configuration/config.toml [theme]
[theme]
base = "dark"                 # #0E1117 background, dense tables read best on dark
primaryColor = "#7C5CFC"      # accent: CTA button, hero number, active segment, focus ring
backgroundColor = "#0E1117"   # dominant surface
secondaryBackgroundColor = "#1A1D24"   # controls column / cards / banner strip
font = "sans-serif"           # body/UI default stack
codeFont = "monospace"        # ALL numbers via st.code / <code> / inline monospace (UI-06)
```
1.57 theming exposes `base`, `primaryColor`, `backgroundColor`, `secondaryBackgroundColor`, `textColor`, `font`, `codeFont`, `headingFont`, `baseRadius`, `borderColor`, `dataframeBorderColor`, and a color palette. [VERIFIED: docs.streamlit.io config.toml]. **What config.toml CANNOT do:** per-cell inline CI bars, per-number right-alignment inside a table, the thin 4px bar layout — those require `st.markdown(unsafe_allow_html=True)` (the CI-bar example above). Monospace *numbers* can come from `codeFont` + wrapping numbers in `st.code`/`<code>`; monospace *everywhere* is not desired (body stays sans).

### AppTest skeleton
```python
# Source: docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest
from streamlit.testing.v1 import AppTest

def test_run_button_produces_probs():
    at = AppTest.from_file("app.py").run()
    at.slider(key="S_slider").set_value(40).run()
    at.button(key="run_btn").click().run()
    assert not at.exception                       # no crash
    assert any("advance" in m.value.lower() for m in at.markdown)

def test_bad_rating_blocks_run():
    at = AppTest.from_file("app.py").run()
    # set an out-of-range / empty rating via the data_editor, then click Run
    at.button(key="run_btn").click().run()
    assert any("Fix the highlighted cell" in m.value for m in at.markdown)
```
`set_value(...).run()` and `.click().run()` are the universal widget methods; every interaction needs an explicit `.run()`. [VERIFIED: discuss.streamlit.io + docs cheat-sheet]. **Caveat:** `data_editor` value-setting through AppTest is known to be awkward (reassigning + run may not propagate cleanly — discuss.streamlit.io/t/55017); for the "bad cell blocks Run" test, prefer driving the validation **helper function directly** in `test_ui_helpers.py` (a pure unit test) and use AppTest only to confirm the block message appears when validation fails.

## Runtime State Inventory

Greenfield UI addition over a frozen engine — no rename/refactor/migration. Section omitted (no stored data, service config, OS state, secrets, or build artifacts are renamed or migrated). `data/stage1.json` is consumed read-only via the existing `load_teams()`. New: `pyproject.toml` gains a `streamlit` dep (reinstall via `uv sync`).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | runtime | ✓ (Phase 1 ran) | >=3.12 | — |
| uv | `uv run streamlit run app.py` bootstrap (DX-03) | assumed ✓ (Phase 1 used `uv run pytest`) | — | documented `pip install streamlit numpy` + `streamlit run app.py` |
| streamlit | the entire UI | ✗ (not yet a dep) | target 1.57.x | none — must be added to pyproject + `uv sync` |
| numpy | engine (transitive) | ✓ | 2.4.x | — |

**Missing dependencies with no fallback:** `streamlit` — the planner MUST add `streamlit>=1.57,<1.58` to `[project].dependencies` in `pyproject.toml` (currently engine-only) and run `uv sync` / `uv run` to install it. This is a required first task.
**Verify during planning:**
```bash
uv --version            # confirm uv present (used in Phase 1)
pip index versions streamlit   # confirm 1.57.x current
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest `>=9,<10` (already pinned) + `streamlit.testing.v1.AppTest` (ships in streamlit) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths=["tests"]`) — exists |
| Quick run command | `uv run pytest tests/test_ui_helpers.py -x` (pure-function tests, sub-second) |
| Full suite command | `uv run pytest -q` (engine tests + UI helper tests + AppTest tests) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| UI-01 | Mode toggle present; main column reorders | AppTest | `uv run pytest tests/test_app.py::test_mode_toggle_reorders -x` | ❌ Wave 0 |
| UI-02 | `@st.cache_data` keyed on `(ratings,S,N,locked)`; edit→Run recomputes; repeat hits cache | unit + AppTest | `pytest tests/test_ui_helpers.py::test_freeze_locked_order_independent` + `tests/test_app.py::test_cache_hit_is_instant` | ❌ Wave 0 |
| UI-03 | Progress bar + running P(advance) from the generator (not blank spinner) | AppTest (presence) + manual (live tally motion) | `pytest tests/test_app.py::test_progress_renders` | ❌ Wave 0 |
| UI-04 | Every prob cell = number + always-visible inline CI bar | unit (HTML string) + **manual** (visual render) | `pytest tests/test_ui_helpers.py::test_ci_bar_html_contains_bar_div` | ❌ Wave 0 |
| UI-05 | All 4 states per feature; bad rating cell blocks Run | unit (validation) + AppTest (block message) | `pytest tests/test_ui_helpers.py::test_validate_ratings_rejects_empty_and_out_of_range` + `tests/test_app.py::test_bad_rating_blocks_run` | ❌ Wave 0 |
| UI-06 | Monospace numbers; one accent; colorblind status + glyph/label; contrast ≥4.5:1 | unit (glyph/hue mapping) + **manual** (visual + contrast) | `pytest tests/test_ui_helpers.py::test_status_palette_never_red_green` | ❌ Wave 0 |
| UI-07 | Trust badge tied to BOTH backtest-passed AND seeds-confirmed; caveated wording | AppTest (text) | `pytest tests/test_app.py::test_trust_badge_caveated_until_both` | ❌ Wave 0 |
| DX-01 | Zero-config first run: fresh clone hits Run, no key/edit, ~15s | AppTest (no exception, probs render with defaults) + manual (timing) | `pytest tests/test_app.py::test_default_run_no_config` | ❌ Wave 0 |
| DX-02 | Persistent dismissable INFERRED-seed banner w/ reconcile diff; "seeds confirmed" toggle | AppTest (banner present until toggle) | `pytest tests/test_app.py::test_seed_banner_dismissable` | ❌ Wave 0 |
| DX-03 | `uv run streamlit run app.py` cross-platform; py pinned; pip fallback | manual (cross-OS launch) | — (manual-only) | n/a |
| DX-04 | README quickstart in the specified order | manual (doc review) | — (manual-only) | n/a |
| DX-05 | `.env.example` lists optional keys; `.env` gitignored | unit (file presence) | `pytest tests/test_app.py::test_env_example_present_and_gitignored` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_ui_helpers.py -x` (pure helpers; fast)
- **Per wave merge:** `uv run pytest -q` (full suite incl. AppTest + frozen engine tests — engine tests must stay green, proving no engine mutation)
- **Phase gate:** Full suite green before `/gsd-verify-work`, plus the Manual-Only checklist signed.

### Wave 0 Gaps
- [ ] `tests/test_ui_helpers.py` — pure-function tests: `freeze_locked` order-independence, `freeze_ratings`, `ci_bar_html` structure, rating validation (empty/out-of-range), status palette never-red/green. Covers UI-02/04/05/06.
- [ ] `tests/test_app.py` — AppTest-driven: default run no-config, cache hit instant, progress renders, trust badge caveated, seed banner dismissable, bad-rating block message, mode toggle. Covers UI-01/03/05/07, DX-01/02/05.
- [ ] `.streamlit/config.toml` — theme file (referenced by tests asserting accent/monospace presence is **manual-only**, but the file must exist).
- [ ] Framework install: add `streamlit>=1.57,<1.58` to `pyproject.toml` `[project].dependencies`, `uv sync`. AppTest needs no extra package.

### Manual-Only acceptance (route to VALIDATION.md Manual-Only)
AppTest cannot assert CSS/pixels. These are manual:
- **UI-04 visual CI-bar rendering** (bar appears beneath each number, 4px, correct fill).
- **UI-06 colorblind palette + ≥4.5:1 contrast** (blue/amber actually render; contrast measured).
- **UI-03 live P(advance) tally motion** (the number visibly settles as chunks land).
- **DX-01 ~15s timing** (wall-clock of the default 100k run).
- **DX-03 cross-OS launch** (`uv run streamlit run app.py` on Windows + Mac/Linux).
- **DX-04 README quickstart** ordering / content review.
- **Mode-reorder *visual* hierarchy** (AppTest can confirm elements/order in the tree; the *visual* hero-vs-table emphasis is manual).

## Security Domain

> `security_enforcement` config not located in this session; treating as enabled and scoping to this phase's actual surface.

Phase 2 is a **local single-user desktop app** with **no network, no auth, no DB, no secrets** (odds/httpx/`.env` are Phase 5; Phase 2 ships only the fail-soft banner stub). The attack surface is minimal.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Single local user; no auth (Out of Scope, REQUIREMENTS.md) |
| V3 Session Management | no | Streamlit `session_state` is in-process, single user |
| V4 Access Control | no | No multi-user, no resources to gate |
| V5 Input Validation | **yes** | Rating cells: `NumberColumn` min/max + `app.py` empty/range validation before the engine (mirrors `engine.teams._validate_fixture`, threat T-01-01). S/N: `st.slider`/`st.number_input` bounded; cap N (engine already caps at 5M for the CLI — mirror a sane UI cap). |
| V6 Cryptography | no | No secrets, no crypto in Phase 2 |

### Known Threat Patterns for a local Streamlit single-user app
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS via `unsafe_allow_html` CI-bar HTML | Tampering | The CI-bar HTML is **app-generated from numeric values only** (formatted floats), never from user free-text. Never interpolate the editable *team name* or any user string into `unsafe_allow_html` markup. Team names come from the frozen fixture; ratings are numbers. Keep it that way. |
| Out-of-range / empty rating reaching the engine | Tampering / DoS | Validate in `app.py` before calling the engine; the engine's `_validate_fixture` also raises (defense in depth). |
| Absurd N causing a multi-hour hang | DoS | Cap N in the UI (e.g. `max_value` on the number_input); engine CLI already caps at 5M. |

No `httpx`/network/secret handling in Phase 2 — those threats (key leakage, SSRF, de-vig of untrusted odds) belong to Phase 5 and must NOT be pulled forward.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `uv` is installed on the dev machine (Phase 1 used `uv run`) | Environment Availability | Low — Phase 1 commits show `uv run pytest`; pip fallback documented regardless (DX-03). |
| A2 | `security_enforcement` config treated as enabled (key not located this session) | Security Domain | Low — the section is included; if disabled it's harmless extra rigor. |
| A3 | Fixed `seed=20260528` (matching engine `__main__`) is the right default; reruns should be reproducible | Pattern 2 | Low — deterministic tool wants reproducible runs; if per-session variety is wanted, add `seed` to the cache key. Flag to user. |
| A4 | The "bad rating cell" (UI-05) means empty/out-of-range, since `NumberColumn` blocks non-numeric text at the widget | Pattern 3 / Pitfall 5 | Medium — if the planner writes the error path against non-numeric text, the branch is unreachable. Confirmed widget behavior via docs+forum but not exercised against 1.57 specifically. |

## Open Questions (RESOLVED — see plan 02-01/02-03 decisions)

> All three resolved by the plan designs: (1) RESOLVED option B — session_state keyed on the tuple (02-01 Task 3); (2) RESOLVED — validate via pure helper, AppTest only for the block message (02-01 Task 3); (3) RESOLVED — explicit `BACKTEST_PASSED=False` constant (02-03 Task 1).

1. **Double-compute on the first cache miss (Pattern 2 A vs B).**
   - What we know: driving the progress bar requires iterating `run_mc_progressive`; memoizing requires storing the `Result`.
   - What's unclear: whether the planner prefers the simplest shape (option A, ~2× first-run cost) or the `session_state`-keyed single-compute (option B).
   - Recommendation: **option B** (session_state keyed on the same tuple) — single ~15s compute + a real bar. Document the tradeoff in the plan.

2. **`data_editor` testability under AppTest.**
   - What we know: AppTest supports `at.data_editor` but value-setting is awkward (discuss.streamlit.io/t/55017).
   - What's unclear: whether edited-cell propagation works cleanly in 1.57's AppTest.
   - Recommendation: test rating validation via the pure helper (`test_ui_helpers.py`); use AppTest only for the resulting block message. Don't over-invest in driving the editor through AppTest.

3. **Where the trust badge reads "backtest passed" from.**
   - What we know: GATE-01/04 are deferred; badge ships caveated tied to BOTH backtest AND seeds-confirmed.
   - What's unclear: the concrete source of the "backtest passed" boolean (a constant flag in code? a test-result file?).
   - Recommendation: a single explicit module-level constant (e.g. `BACKTEST_PASSED = False`) the badge reads, flipped only when GATE-01 lands. Keep it obvious so it can't silently drift true.

## Sources

### Primary (HIGH confidence)
- `engine/montecarlo.py`, `engine/teams.py` (committed Phase-1 code) — exact `run_mc` / `run_mc_progressive` / `Partial` / `Result` / `load_teams` signatures — the integration contract.
- `.planning/phases/01-engine-backtest-gate/01-03-SUMMARY.md` — generator-first split, pinned `n_chunks=20`, sample retention, cache-wrapper seam.
- docs.streamlit.io/develop/concepts/architecture/caching — `@st.cache_data` hashing, `UnhashableParamError`, leading-underscore + `hash_funcs` rules.
- docs.streamlit.io/develop/api-reference/data/st.data_editor + .../st.column_config.NumberColumn — editable table, `num_rows="fixed"`, numeric validation, return types.
- docs.streamlit.io/develop/api-reference/widgets/st.segmented_control — GA since 1.56, signature.
- docs.streamlit.io/develop/api-reference/status/st.progress — handle, `.progress()`/`.empty()`, value range.
- docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest — AppTest API + limits (no CSS/pixels).
- docs.streamlit.io/develop/api-reference/configuration/config.toml — `[theme]` keys incl. `codeFont` (monospace).
- `.planning/research/STACK.md` — Streamlit 1.57 pin, `@st.cache_data` unchanged, no-pandas/scipy.

### Secondary (MEDIUM confidence)
- discuss.streamlit.io/t/testing-st-data-editor/55017 — AppTest + data_editor caveats.
- docs.streamlit.io app-testing cheat-sheet / get-started — `set_value().run()`, `.click().run()` patterns.
- discuss.streamlit.io / github streamlit#13305, #11519 — NumberColumn None/dtype edge cases (informs the "bad cell" definition).

### Tertiary (LOW confidence)
- None load-bearing; all API claims cross-verified against official docs.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — single project-pinned package (streamlit 1.57), engine deps frozen.
- Architecture / engine seam: HIGH — read directly from committed Phase-1 code.
- Streamlit API specifics (cache, data_editor, segmented_control, progress, AppTest, theme): HIGH — verified against current docs.streamlit.io.
- "Bad cell" UI-05 semantics: MEDIUM — widget numeric-validation behavior confirmed via docs + forum, not exercised against 1.57 in this session (A4).
- Pitfalls: HIGH — derived from official caching docs + the project's own documented seams (Pitfall 13, trust-badge "both not one").

**Research date:** 2026-05-28
**Valid until:** 2026-06-27 (~30 days; Streamlit 1.57 is a stable pinned release — re-verify only if the pin moves to 1.58+).
