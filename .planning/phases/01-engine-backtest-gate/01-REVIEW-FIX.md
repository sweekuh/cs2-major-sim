---
phase: 01-engine-backtest-gate
fixed_at: 2026-05-28T00:00:00Z
review_path: .planning/phases/01-engine-backtest-gate/01-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 1: Code Review Fix Report

**Fixed at:** 2026-05-28T00:00:00Z
**Source review:** .planning/phases/01-engine-backtest-gate/01-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 7 (CR-01, CR-02, CR-03, WR-01, WR-02, WR-03, WR-04 — Info findings IN-01/02/03 out of scope)
- Fixed: 7
- Skipped: 0

Test suite re-run after all fixes: `uv run pytest -q` → **21 passed, 1 skipped** (unchanged from the pre-fix baseline). No expected test values, the difficulty formula, the priority table, the fold key, or any correctness invariant were modified; all fixes are defensive/robustness only.

## Fixed Issues

### CR-01: `assert` strips under `-O` in `run_mc`, silently returning `None`

**Files modified:** `engine/montecarlo.py`
**Commit:** b91c5a9
**Applied fix:** Replaced `assert result is not None` in `run_mc` with an explicit `if result is None: raise RuntimeError(...)` guard so the contract holds even under `python -O`. Verified via `ast.parse`.

### CR-02: `beta_moment_fit` produces invalid Beta parameters when `mean` is 0.0 or 1.0

**Files modified:** `engine/probs.py`
**Commit:** 6a15253
**Applied fix:** Clamp `mean` strictly into `(eps, 1-eps)` before computing `bound`, then keep the variance strictly below the maximal bound with a multiplicative ceiling (`bound * (1 - eps)`) and a multiplicative floor (`eps * bound`), computing `common = bound / v - 1`. This guarantees both `alpha` and `beta` come out strictly positive at the degenerate means.

Note on the review's suggested patch: the literal patch in REVIEW.md (clamp mean, then `v = min(var, bound - eps) if bound > eps else eps; v = max(v, eps)`) was verified by direct execution and still produced **non-positive** alpha/beta at `mean=0/1` — because after clamping, `bound ≈ 1e-9` so `bound > eps` is false and `v` ends up equal to/above `bound`, driving `common ≤ 0`. The applied fix adapts the suggestion to actually satisfy the "both params strictly positive" requirement. Confirmed across `(0.0,0.0)`, `(1.0,0.0)`, `(0.5,0.0)`, `(0.6,0.01)`, `(0.3,0.5)`, `(0.5,0.25)` that `alpha>0`, `beta>0`, and `numpy.random.Generator.beta` accepts them. The existing `test_probs.py` invariant `a/(a+b) == mean` still holds and the test passes.

**Status flag: requires human verification.** This fix changes numeric computation in `beta_moment_fit`. Syntax + the existing test pass, and the mean-recovery invariant is preserved, but a human should confirm the variance-clamping behavior is acceptable for the Phase-5 epistemic seam (the function is unused in Phase 1).

### CR-03: `_validate_fixture` duplicate-seed check is permanently dead code

**Files modified:** `engine/teams.py`
**Commit:** 07dec7e
**Applied fix:** Removed the unreachable `if len(set(seeds)) != len(seeds)` check (dict keys are unique by construction) and replaced it with an explanatory comment noting that JSON-path duplicate detection happens in `load_teams()` and the in-code `_DEFAULT_FIXTURE` path cannot have duplicates. The exact-seed-set check that follows subsumes any count/range mismatch.

### WR-01: `load_teams` raises `KeyError` on malformed JSON entries, not `ValueError`

**Files modified:** `engine/teams.py`
**Commit:** 012b7d1
**Applied fix:** Added a per-entry `isinstance(entry, dict)` check and a required-field loop (`seed`, `name`, `rating`) that raises a descriptive `ValueError` before any key access, so malformed `stage1.json` entries produce a clear validation message instead of a raw `KeyError`. Verified by loading a fixture missing the `seed` key → `ValueError: team entry missing required field 'seed'`.

### WR-02: `_drain` in `__main__.py` implicitly returns `None` if `StopIteration` is never raised

**Files modified:** `engine/__main__.py`
**Commit:** 223c649
**Applied fix:** Added `if stop.value is None: raise RuntimeError(...)` inside the `except StopIteration` block and a terminal `raise RuntimeError(...)` after the loop so `_drain` always satisfies its `-> Result` annotation rather than implicitly returning `None`.

### WR-03: `FakeTeam.opps` is a `list` but `Team.opps` is a `set`

**Files modified:** `tests/conftest.py`, `tests/test_swiss.py`
**Commit:** 347f670
**Applied fix:** Changed `FakeTeam` to `@dataclass(eq=False)` with `opps: set = field(default_factory=set)` (matching `engine.teams.Team`'s identity-hash + set contract), updated the `make_team` factory to wrap `opps` in `set(...)`, converted the four `.opps.append(...)` test-setup call sites in `test_swiss.py` to `.opps.add(...)`, and corrected the `.opps:list` docstring annotation to `.opps:set`. No expected assertion values changed (assertions compare on `.id`). Full suite still 21 passed, 1 skipped.

### WR-04: `_chunk_sizes` produces zero-sized chunks when `n_chunks > N`, yielding spurious `Partial` objects

**Files modified:** `engine/montecarlo.py`
**Commit:** a6c087e
**Applied fix:** Added a `if chunk_n == 0: continue` guard at the top of the chunk loop in `run_mc_progressive` (the skip-filter option from REVIEW.md, per the phase constraint — not the raise option). This suppresses no-progress `Partial` yields and removes any divide-by-zero risk in `running_p_adv`. Verified reproducibility is unchanged for the normal `n_chunks <= N` case (a zero-sized chunk consumes no RNG draws, so its pinned child seed going unused does not shift any other chunk's stream), and that `N=5, n_chunks=20` now yields exactly 5 partials instead of 20.

## Skipped Issues

None — all in-scope findings were fixed.

---

_Fixed: 2026-05-28T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
