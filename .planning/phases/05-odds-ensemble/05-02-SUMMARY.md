---
phase: 05-odds-ensemble
plan: 02
subsystem: engine
tags: [backsolve, invert-series, gauss-newton, epistemic, beta-draws, outer-loop, market-overrides, numpy, tdd]

# Dependency graph
requires:
  - phase: 01-engine-backtest-gate
    provides: "series/series_prob/beta_moment_fit/epistemic_draws stubs, simulate_stage ratings seam, run_mc_progressive OUTER epistemic loop, GATE-01 backtest"
  - phase: 05-odds-ensemble (05-01)
    provides: "odds/ pure core — BlendedProb(p, var, n_sources, bo3), pool(), de-vig (consumed by 05-03, not modified here)"
provides:
  - "engine/backsolve.py: invert_series (exact Bo3 inverse by bisection, identity Bo1) + fit_ratings (numpy-only Gauss-Newton logistic LS, gauge-anchored, NO scipy)"
  - "engine/swiss.py: keyword-only market_overrides threaded simulate_stage -> _play, oriented to lower-id (Bo3 NOT re-applied)"
  - "engine/probs.py: filled epistemic_draws — K Beta draws via existing beta_moment_fit clamp; k=1/var=0 exact no-op"
  - "engine/montecarlo.py: market_blend seam + K-draw outer loop; reported band = across-draw union of Wilson intervals (⊇ Wilson, N-invariant on disagreement)"
affects: [05-03, odds-cache, ui-odds-loader, app-backsolve-wiring]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Series->map invert BEFORE the ratings fit (Pitfall 9) — invert_series is the exact inverse of engine.probs.series"
    - "Hand-rolled numpy Gauss-Newton logistic least-squares with a gauge-anchored team (no scipy)"
    - "Epistemic OUTER loop: K Beta draws aggregated ACROSS draws; band = union of per-draw Wilson intervals (N-invariant epistemic floor)"
    - "Additive keyword-only seams (market_overrides / market_blend, default None = byte-identical no-op)"

key-files:
  created:
    - "engine/backsolve.py"
    - "tests/test_backsolve.py"
    - "tests/test_epistemic.py"
  modified:
    - "engine/probs.py"
    - "engine/swiss.py"
    - "engine/montecarlo.py"

key-decisions:
  - "Epistemic draws aggregate across K outer draws by UNIONING each draw's inner Wilson interval (min-lo, max-hi); with one no-op draw this collapses to exactly the single Wilson interval, so the rating-only band is byte-identical"
  - "Override orientation: _play looks up the id-bucket key f'{min}-{max}' and computes p_a = p if a.id<b.id else 1-p, because pair_within_group delivers pairs difficulty-ranked (high, low), NOT id-sorted"
  - "market_blend is a keyword-only {\"lo-hi\": (p, var)} seam on run_mc/run_mc_progressive; var>0 drives K=DEFAULT_EPISTEMIC_DRAWS (12) outer draws, var all-zero / None is the exact rating-only no-op"
  - "test_rating_roundtrip asserts gauge-invariant DIFFERENCES (absolute ratings recover only up to the anchor's gauge, which is the anchor team's seed rating)"

patterns-established:
  - "Pattern: epistemic spread is the ACROSS-draw spread, never folded into per-sim sampling (Pitfall 4) — proven N-invariant by test_band_stable_in_N"
  - "Pattern: the variance clamp is the EXISTING beta_moment_fit (var < mean*(1-mean)), CALLED never re-implemented (Pitfall 5)"

requirements-completed: [ODDS-04, PROB-03, PROB-04, PROB-05]

# Metrics
duration: ~75 min
completed: 2026-05-30
---

# Phase 5 Plan 02: Back-solve + Epistemic Outer Loop Summary

**Series->map inverse + numpy-only gauge-anchored Gauss-Newton ratings fit, an orientation-correct market_overrides seam threaded into _play, and a filled K-Beta epistemic OUTER loop whose reported band ⊇ inner Wilson and is N-invariant on disagreement — all additive, GATE-01 still green.**

## Performance

- **Duration:** ~75 min
- **Started:** 2026-05-30T05:30Z (approx)
- **Completed:** 2026-05-30T06:44Z
- **Tasks:** 3 (TDD: RED -> GREEN x2)
- **Files modified:** 6 (3 created, 3 modified)

## Accomplishments
- `invert_series` is the EXACT inverse of `engine.probs.series` (identity Bo1; bisection-invert `p^2(3-2p)` for Bo3 — `0.648 -> 0.6`, round-trips to 1e-6).
- `fit_ratings` is a hand-rolled numpy Gauss-Newton logistic least-squares fit (NO scipy) that recovers known ratings up to the additive gauge and reprices every target matchup; the gauge anchor removes the `(r+c)` null space (anchor pinned exactly).
- `market_overrides` threaded `simulate_stage -> _play` with the load-bearing orientation flip (id-bucket lookup, `p_a = p if a.id<b.id else 1-p`) so the override is correct even when `_play` receives the pair in (high-id, low-id) arg order; Bo3 is NOT re-applied (`series_prob(market_series_prob=...)`).
- `epistemic_draws` filled to yield K Beta draws via the EXISTING `beta_moment_fit` clamp; `k=1`/`var=0`/`rng=None` is the exact Phase-1 single-point no-op.
- `run_mc`/`run_mc_progressive` gained a keyword-only `market_blend` seam; the K outer draws each feed per-match `market_overrides` (distinct child SeedSequence per draw) and the reported band is the across-draw union of Wilson intervals — strictly wider than inner Wilson and N-invariant on a high-disagreement match.

## Task Commits

Each task committed atomically (TDD):

1. **Task 1: RED tests (test_backsolve.py + test_epistemic.py)** — `2bc8fcb` (test)
2. **Task 2: backsolve invert_series + fit_ratings + market_overrides plumbing** — `6b24c57` (feat)
3. **Task 3: fill epistemic_draws + wire K-Beta outer loop into the MC** — `d6aff61` (feat)

**Plan metadata:** _(this SUMMARY commit)_

## Files Created/Modified
- `engine/backsolve.py` (created) — `invert_series` (bisection Bo3 inverse) + `fit_ratings` (numpy Gauss-Newton logistic LS, gauge-anchored).
- `tests/test_backsolve.py` (created) — `test_invert_series`, `test_bo3_inverse_correct`, `test_rating_roundtrip` [CRITICAL], `test_gauge_anchor_removes_null_space`, `test_override_no_bo3_reapply` [ORIENTATION-CRITICAL].
- `tests/test_epistemic.py` (created) — `test_band_wider_than_wilson` [CRITICAL], `test_band_stable_in_N`, `test_rating_only_noop_unchanged` [GATE GUARD].
- `engine/probs.py` (modified) — filled `epistemic_draws(blend, var, *, k=1, rng=None)`; no-op guard + Beta branch calling the existing `beta_moment_fit`.
- `engine/swiss.py` (modified) — keyword-only `market_overrides` on `simulate_stage`/`_play` with the lower-id orientation; routed via `series_prob` (Bo3 not re-applied); dropped now-unused `series`/`p_map` imports.
- `engine/montecarlo.py` (modified) — `DEFAULT_EPISTEMIC_DRAWS`, `_epistemic_inputs`, `_union_band`, `market_blend`/`k_epistemic` params on both MC entries; K-draw outer loop wiring per-draw counts.

## Decisions Made
- **Band aggregation = union of per-draw Wilson intervals.** Each outer draw's per-team count gets its own Wilson interval; the reported band is `(min lo, max hi)` across draws. As N grows, each draw's Wilson half-width shrinks but the across-draw spread of point estimates does not — so the band is N-invariant on disagreement and collapses to exactly one Wilson interval in the no-op case (byte-identical band).
- **`market_blend` at the match level (D6).** The drawn `_p_vec` perturbs per-match series probs (the market gives p+var per match), translated to the id-bucket `market_overrides` contract `_play` already consumes.
- **`test_rating_roundtrip` asserts gauge-invariant differences.** Absolute ratings are only recoverable up to the anchor's gauge (the anchor team's seed rating), so the test asserts repricing + recovered differences, not raw absolute equality.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `test_rating_roundtrip` absolute-rating assertion was gauge-naive**
- **Found during:** Task 2 (GREEN part 1)
- **Issue:** The RED test asserted recovered absolute ratings equal the hand-set known values (`90.0 ± 0.5`), but `fit_ratings` anchors the gauge at the anchor team's *seed* rating (92 for id 1 in the fixture), so absolute ratings legitimately shift by the gauge offset. The fit was correct; the assertion was testing a non-recoverable quantity.
- **Fix:** Changed the assertion to the gauge-invariant, genuinely-recoverable quantities: repricing of every target matchup + recovered DIFFERENCES vs the anchor.
- **Files modified:** `tests/test_backsolve.py`
- **Verification:** All 5 backsolve tests pass; the fit still recovers correct rating differences.
- **Committed in:** `6b24c57` (Task 2 commit)

**2. [Rule 1 - Bug] `test_band_stable_in_N` Wilson reference used the summed count**
- **Found during:** Task 3 (GREEN part 2)
- **Issue:** The RED test computed the pure-Wilson reference as `wilson(epi2.counts_advance[lo_id], N2)`, but `counts_advance` is the SUM across K=12 draws (~238k), so `count/N2 > 1` drove `wilson` into a `math domain error`. The implementation was correct; the test's reference was wrong.
- **Fix:** Derive the pure-Wilson reference from a single-draw rating-only run (`market_blend=None`) at N2 — a genuine no-epistemic band that shrinks with N.
- **Files modified:** `tests/test_epistemic.py`
- **Verification:** `test_band_stable_in_N` passes; the epistemic band is N-invariant and exceeds the pure-Wilson width at N2.
- **Committed in:** `d6aff61` (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (2 test-assertion bugs, Rule 1). Both were RED-test authoring errors — the GREEN implementation was correct in each case and exposed an assertion that tested a non-recoverable / mis-scaled quantity.
**Impact on plan:** No scope creep; no production-code deviation. The engine touch remains strictly additive (two filled stubs + keyword-only args).

## Confirmation of CRITICAL guards
1. **Override orientation correct + tested.** `_play` looks the override up by the id-bucket `f"{min}-{max}"` and orients via `p_a = p if a.id<b.id else 1-p`. `test_override_no_bo3_reapply` delivers the pair to `_play` in (high-id, low-id) arg order and asserts the LOWER-id team wins at rate ~p (0.85), NOT the first arg (~0.15) and NOT `series(0.85)`=0.9355 — guarding both the silent half-matchup inversion AND Bo3 re-application.
2. **Band test injects var directly.** `test_band_wider_than_wilson` / `test_band_stable_in_N` hand-author `{"1-9": (0.5, 0.05)}` — var injected directly, NOT routed through a 1-source `pool()` (which would give var≈0 and the degenerate no-op path). The band is strictly wider than inner Wilson and N-invariant.
3. **Rating-only no-op byte-identical + GATE-01 green.** `epistemic_draws` with `var=0`/`rng=None`/`k=1` yields exactly one `list(blend)` draw; `market_overrides=None` / `market_blend=None` defaults leave `_play`/MC unchanged. `test_rating_only_noop_unchanged` asserts byte-identical counts; the 99 pre-existing tests + GATE-01 `test_backtest_budapest_2025` stay green (full suite 107 passed).

## Issues Encountered
None beyond the two auto-fixed test-assertion bugs documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- 05-02 deliverables ready for **05-03** (fetch script + cache seam + UI): the app's back-solve consumes `fit_ratings`/`invert_series`, and `run_mc(..., market_blend=...)` consumes the cache-derived `{"lo-hi": (p, var)}` blend directly.
- 05-03 is Wave 2 (depends on both 05-01 and 05-02). The live slug/ticker confirmation remains a deferred user `checkpoint:human-verify` via gstack `/browse`.

## Self-Check: PASSED
- Created files exist on disk: `engine/backsolve.py`, `tests/test_backsolve.py`, `tests/test_epistemic.py` — all FOUND.
- Commits present: `2bc8fcb` (RED), `6b24c57` (GREEN-1), `d6aff61` (GREEN-2) — all in `git log`.
- `uv run pytest -q tests/test_backsolve.py tests/test_epistemic.py` -> 8 passed.
- `uv run pytest -q` -> 107 passed (99 baseline + 8 new); GATE-01 green.

---
*Phase: 05-odds-ensemble*
*Completed: 2026-05-30*
