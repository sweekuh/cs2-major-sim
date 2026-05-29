---
phase: 01-engine-backtest-gate
reviewed: 2026-05-28T00:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - engine/probs.py
  - engine/swiss.py
  - engine/montecarlo.py
  - engine/teams.py
  - engine/__main__.py
  - engine/__init__.py
  - tests/conftest.py
  - tests/test_swiss.py
  - tests/test_mc.py
  - tests/test_probs.py
  - tests/test_backtest_budapest_2025.py
  - pyproject.toml
findings:
  critical: 3
  warning: 4
  info: 3
  total: 10
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-05-28T00:00:00Z
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

The engine's correctness-critical load-bearing invariants — Buchholz formula, Bo3 closed
form, within-group difficulty ranking, rematch avoidance — are correctly implemented and
guarded by the unit tests. The structural shape is sound.

Three critical issues were found: a production `assert` in `run_mc` that evaporates under
`python -O`, a `beta_moment_fit` edge case that produces invalid Beta parameters when
`mean` is 0 or 1, and the `_validate_fixture` duplicate-seed check being dead code (the
dict key-uniqueness invariant makes it unreachable — it silently cannot fire). Additionally,
`load_teams` raises an unguarded `KeyError` on malformed JSON entries, the `_drain`
function in `__main__.py` has an implicit `None` return on a code path that cannot be
reached in practice but is untested, and the `FakeTeam` / `Team` container type divergence
(`list` vs `set`) for `opps` is a latent contract mismatch.

The `counts_03` tally and 0-3 accounting in the Monte Carlo loop are correct as written.
The Buchholz import path (single canonical `difficulty()` from `engine.probs`) is clean.
The chunked RNG reproducibility structure (SeedSequence.spawn over a pinned chunk count)
is correct. The generator-return pattern for the final `Result` is correctly implemented.

---

## Critical Issues

### CR-01: `assert` strips under `-O` in `run_mc`, silently returning `None`

**File:** `engine/montecarlo.py:230`
**Issue:** `run_mc` uses `assert result is not None` as a guard before returning the
`Result`. Python's `-O` (optimize) flag strips all `assert` statements at compile time.
Under `-O`, if for any reason `StopIteration` is never raised (e.g., an empty generator
— impossible today but a latent risk as the code evolves), `result` stays `None` and the
function returns `None` instead of raising. Callers typed `-> Result` would then receive
`None` with no diagnostic.
**Fix:**
```python
# Replace the assert with an explicit runtime guard:
if result is None:
    raise RuntimeError(
        "run_mc_progressive exhausted without returning a Result — "
        "this is an internal engine bug"
    )
return result
```

---

### CR-02: `beta_moment_fit` produces invalid Beta parameters when `mean` is 0.0 or 1.0

**File:** `engine/probs.py:102-110`
**Issue:** When `mean == 0.0` or `mean == 1.0`, `bound = mean * (1 - mean) = 0.0`.
The branch `if bound > eps` is False, so `v = eps`. Then:
```
common = 0.0 * 1.0 / eps - 1.0 = -1.0
alpha  = 0.0 * (-1.0) = 0.0
beta   = 1.0 * (-1.0) = -1.0   # (for mean=0) or alpha=-1.0, beta=0.0 (for mean=1)
```
`numpy.random.Generator.beta(alpha, beta)` requires both parameters to be strictly
positive (> 0); passing 0 or negative raises `ValueError`. This is unused in Phase 1
because `epistemic_draws` yields one point draw, but the function is live code
(imported and called in `test_probs.py`) and is planned as the Phase 5 seam.
**Fix:**
```python
def beta_moment_fit(mean: float, var: float) -> tuple[float, float]:
    # Guard degenerate means before computing bound.
    eps = 1e-9
    mean = max(eps, min(1.0 - eps, mean))   # clamp mean away from 0/1
    bound = mean * (1.0 - mean)
    v = min(var, bound - eps) if bound > eps else eps
    v = max(v, eps)
    common = mean * (1.0 - mean) / v - 1.0
    alpha = mean * common
    beta_ = (1.0 - mean) * common
    return alpha, beta_
```

---

### CR-03: `_validate_fixture` duplicate-seed check is permanently dead code

**File:** `engine/teams.py:84-85`
**Issue:** `rows` is a `dict[int, tuple[str, float]]`. Python dicts cannot have duplicate
keys; `len(set(rows.keys())) != len(rows.keys())` is always False. The check at line 84
can never fire. The REAL duplicate-seed guard is the `if seed in rows` check in
`load_teams()` at line 125 — which is correct — but the presence of this dead guard in
`_validate_fixture` creates a false sense that the function enforces uniqueness, when it
cannot. If `_validate_fixture` is ever called with a freshly constructed dict that somehow
skipped the `load_teams` loop (e.g., from the in-code `_DEFAULT_FIXTURE` path), duplicate
seeds would not be caught here.
**Fix:**
```python
# Remove the dead check entirely, and add a comment noting that duplicate detection
# for the JSON path happens in load_teams() before this function is called:
# (remove lines 84-85)
# For the in-code _DEFAULT_FIXTURE path, duplicates are impossible by construction.
```
Alternatively, if `_validate_fixture` is intended to be callable with arbitrary `rows`
inputs in future, change the parameter type to accept a list of `(seed, name, rating)`
tuples so duplicate seeds can actually arrive and be caught.

---

## Warnings

### WR-01: `load_teams` raises `KeyError` on malformed JSON entries, not `ValueError`

**File:** `engine/teams.py:123-127`
**Issue:** At line 124, `entry["seed"]` raises a raw `KeyError` if the JSON entry omits
the `"seed"` key. Same for `"name"` and `"rating"` at line 127. The docstring says the
function "raises loudly on mismatch, duplicate seed, or bad rating" but does not mention
`KeyError`. A user who ships a slightly malformed `stage1.json` sees a traceback with
`KeyError: 'seed'` rather than a clear validation message.
**Fix:**
```python
for entry in teams_json:
    if not isinstance(entry, dict):
        raise ValueError(f"each team entry must be a dict, got {type(entry).__name__!r}")
    for field in ("seed", "name", "rating"):
        if field not in entry:
            raise ValueError(f"team entry missing required field {field!r}: {entry!r}")
    seed = entry["seed"]
    if seed in rows:
        raise ValueError(f"duplicate seed {seed} in {src}")
    rows[seed] = (entry["name"], entry["rating"])
```

---

### WR-02: `_drain` in `__main__.py` implicitly returns `None` if `StopIteration` is never raised

**File:** `engine/__main__.py:46-53`
**Issue:** `_drain` is annotated `-> Result` but has no fallback `return` after the
`try/except` block. If the generator exhausts without raising `StopIteration` (which
cannot happen today but is fragile), the function returns `None` implicitly. The
analogous `run_mc` wrapper uses `assert result is not None` (itself flagged as CR-01);
`_drain` has no guard at all. The caller at line 67 immediately calls `result.p_30()`
which would crash with `AttributeError: 'NoneType' object has no attribute 'p_30'`.
**Fix:**
```python
def _drain(teams, N: int) -> Result:
    gen = run_mc_progressive(teams, None, 40.0, N, {}, seed=SMOKE_SEED)
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        if stop.value is None:
            raise RuntimeError("run_mc_progressive did not return a Result")
        return stop.value
    raise RuntimeError("generator exhausted without StopIteration — internal engine bug")
```

---

### WR-03: `FakeTeam.opps` is a `list` but `Team.opps` is a `set`; `_is_rematch` iterates both, but `a.opps.add(b)` called on a `FakeTeam` would crash

**File:** `tests/conftest.py:29` / `engine/teams.py:71` / `engine/swiss.py:258-259`
**Issue:** `_record_match` in `swiss.py` calls `a.opps.add(b)` (line 258). This assumes
`opps` is a `set`. `FakeTeam.opps` is a `list` — `list` has no `.add()` method. If
`simulate_stage` is ever called with `FakeTeam` objects (as opposed to real `Team`
objects), it crashes with `AttributeError: 'list' object has no attribute 'add'`. The
current test suite avoids this by only passing real `Team` objects to `simulate_stage`.
However `test_locked_results_honored` and `test_bo3_placement_and_termination` both call
`simulate_stage(load_teams(), ...)`, not `FakeTeam` — correct. But the contract is
implicit, and any future test that passes `FakeTeam` to `simulate_stage` will crash
opaquely.
**Fix:** Give `FakeTeam` an `.add()` method, or change `opps` to `set` with
`eq=False` on `FakeTeam` (matching `Team`'s `eq=False` semantics). The simplest fix:
```python
# conftest.py
@dataclass(eq=False)
class FakeTeam:
    id: int
    seed: int = 0
    wins: int = 0
    losses: int = 0
    opps: set = field(default_factory=set)
```

---

### WR-04: `_chunk_sizes(N, n_chunks)` produces zero-sized chunks when `n_chunks > N`, yielding spurious `Partial` objects with no progress

**File:** `engine/montecarlo.py:119-120`
**Issue:** When `n_chunks > N` (e.g., `N=5, n_chunks=20`), `base = 0` and only the first
`N` chunks have size 1; the remaining `n_chunks - N` chunks have size 0. Each zero-sized
chunk still executes the `yield Partial(...)` at line 187, emitting 15 duplicate Partials
where `done` does not advance. This does not cause a division-by-zero (the inner loop
simply runs zero times and `done` is already positive from the previous chunk), but it
inflates the progress stream and could mislead the Phase-2 UI into thinking 20 chunks
of work landed when only 5 did.
**Fix:** Add a guard in `run_mc_progressive` or `_chunk_sizes`:
```python
if n_chunks > N:
    raise ValueError(
        f"n_chunks ({n_chunks}) must not exceed N ({N}); "
        "reduce n_chunks or increase N"
    )
```
Alternatively, filter zero-sized chunks before the inner loop:
```python
for chunk_idx, chunk_n in enumerate(sizes):
    if chunk_n == 0:
        continue
    ...
```

---

## Info

### IN-01: `locked` type hint in `run_mc_progressive` and `simulate_stage` is untyped `dict`

**File:** `engine/montecarlo.py:129` / `engine/swiss.py:232`
**Issue:** The `locked` parameter is typed as `dict` (bare) in both function signatures.
The actual contract is `dict[frozenset[int], int]` (frozenset of team IDs -> winner ID).
The loose type hint offers no tooling feedback if a caller passes a `dict[str, int]` or
similar wrong key type — which would produce a silent miss in `_play` (key lookup fails
silently, falling through to the sampling path) rather than a loud error.
**Fix:**
```python
from typing import TypeAlias
LockedMap: TypeAlias = dict[frozenset[int], int]
```
And update both function signatures: `locked: LockedMap`.

---

### IN-02: `series_prob` in `probs.py` is not called from `swiss.py`; `_play` computes the series prob inline

**File:** `engine/swiss.py:226` / `engine/probs.py:42-61`
**Issue:** `series_prob()` exists as the canonical "resolve a matchup's series win prob,
honoring an odds override" function. But `_play` (swiss.py line 226) calls
`series(p_map(ra, rb, S=S), _is_bo3(a, b))` directly, bypassing `series_prob` entirely.
This means: (1) when Phase 5 adds `market_series_prob`, the `swiss.py` hot path would
also need updating, creating a second change site; (2) the abstraction layer exists but
is not used where it matters most.
**Fix:** In `_play`, replace the inline call with:
```python
from engine.probs import series_prob
p_a = series_prob(ra=ra, rb=rb, bo3=_is_bo3(a, b), S=S)
```
This is a one-line change that wires the Phase-5 seam through the canonical function
(market_series_prob=None is the default, so Phase 1 behavior is identical).

---

### IN-03: No validation that `seed` is a non-negative integer in `run_mc_progressive`

**File:** `engine/montecarlo.py:148-151`
**Issue:** `run_mc_progressive` validates `N > 0` and `n_chunks > 0` but does not
validate `seed`. `numpy.random.SeedSequence` accepts negative integers and floats without
error, producing potentially surprising state, though not a crash. A float seed (e.g.,
`seed=1.5`) would raise a `TypeError` deep inside numpy rather than at the function
boundary with a clear message.
**Fix:**
```python
if not isinstance(seed, int) or seed < 0:
    raise ValueError(f"seed must be a non-negative integer, got {seed!r}")
```

---

_Reviewed: 2026-05-28T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
