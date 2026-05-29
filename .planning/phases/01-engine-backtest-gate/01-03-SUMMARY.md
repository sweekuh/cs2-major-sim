---
phase: 01-engine-backtest-gate
plan: 03
subsystem: engine
tags: [python, numpy, monte-carlo, seedsequence, wilson, generator, tdd]

# Dependency graph
requires:
  - "01-01: engine.probs.epistemic_draws (outer-loop single-draw stub) + p_map/series; engine.teams.load_teams + Team + STAGE_SIZE + ADVANCE_AT_WINS/ELIMINATE_AT_LOSSES; tests/test_mc.py xfail scaffold"
  - "01-02: engine.swiss.simulate_stage(teams, ratings, S, rng, locked) returning {id: final Team}; mutates wins/losses/opps so each sim needs a FRESH team set"
provides:
  - "engine/montecarlo.py: run_mc_progressive (generator yielding Partial(done,total,running_p_adv) per chunk, returning Result), run_mc (drains it — the @st.cache_data wrapper seam), wilson() closed-form band, Partial + Result dataclasses"
  - "SeedSequence(seed).spawn(n_chunks) over a PINNED n_chunks=20 → reproducible per-team counts across runs/machines and chunk-safe (ENG-09)"
  - "Result.sample: the FULL per-sim record sample (list of {id:(wins,losses)} per sim, length N) — the Phase 3 Ballot B / Phase 4 re-sim seam (MC-04)"
  - "engine/__main__.py: uv run python -m engine [N] headless smoke run printing the per-team P(3-0)/P(advance)/P(0-3) table + Wilson bands + invariant sums"
affects: [02-streamlit-ui, 03-pickem-optimizer, 04-conditional-resim, 05-odds-ensemble]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Generator-first two-function split: run_mc_progressive yields per-chunk Partials and `return`s the Result; run_mc drains via next()/StopIteration.value — no streamlit import, just the seam Phase 2 decorates with @st.cache_data (MC-05)"
    - "SeedSequence(seed).spawn(n_chunks) with PINNED n_chunks=20; one default_rng per chunk; N split deterministically via divmod so reproducibility depends only on (seed, n_chunks) (ENG-09, Pitfall 10)"
    - "Outer epistemic_draws loop wraps the chunk loop; Phase 1 yields one point draw → spread 0 → reported band == inner hand-coded Wilson band (PROB-03/05)"
    - "Each sim rebuilds a fresh team set from the template's (id,name,seed,rating) because simulate_stage mutates wins/losses/opps (Wave-2 handoff note)"
    - "Wilson score interval hand-coded in numpy (no scipy); same closed form reused for all three per-team bands (MC-02)"
    - "ASCII-only CLI output so the smoke run survives a Windows cp1252 console (no Σ/≈/± Unicode)"

key-files:
  created:
    - engine/montecarlo.py
    - engine/__main__.py
  modified:
    - tests/test_mc.py

key-decisions:
  - "run_mc_progressive returns the final Result as the generator's `return` value (captured via StopIteration.value in run_mc), while yielding only Partials — this keeps the per-chunk progress payload and the final aggregate cleanly separated, which is exactly the Phase-2 split (uncached generator drives the bar; cached wrapper serves the Result)."
  - "Each sim calls _fresh_teams(template) to rebuild Team objects from identity fields only; reproducibility comes entirely from the SeedSequence-derived rng, not from object reuse, so cloning per sim is safe and required (simulate_stage mutates state)."
  - "__main__ default smoke N=50k with a FIXED seed (20260528); argv N is validated as a positive int and capped at 5M (T-03-02) — negative/zero/NaN/huge all raise SystemExit with a message rather than crashing or hanging."
  - "The invariant sums (ΣP(3-0)/ΣP(advance)/ΣP(0-3)) are structurally exact (2.000/8.000/2.000) at any N because every single sim produces exactly 2×3-0, 8 advance, 2×0-3 — the ±0.05 tolerance is slack that the closed format never actually consumes."

requirements-completed: [ENG-09, MC-01, MC-02, MC-03, MC-04, MC-05, PROB-03, PROB-05]

# Metrics
duration: ~20min
completed: 2026-05-28
---

# Phase 1 Plan 03: Monte Carlo Runner + Headless Smoke Run Summary

**Completed the headless Walking Skeleton: `engine/montecarlo.py` runs N Valve-Swiss stage sims over the proven `simulate_stage` engine and produces per-team P(3-0)/P(advance)/P(0-3) with hand-coded Wilson bands, structured generator-first with all three cross-phase seams correct — `SeedSequence.spawn` over a PINNED 20-chunk count for reproducible chunk-safe RNG (ENG-09), a retained full per-sim record sample (MC-04), and an outer single-draw epistemic loop whose band collapses to the inner Wilson band (PROB-03/05) — and `engine/__main__.py` prints the 16-row per-team table via `uv run python -m engine`, the one real interaction proving fixtures→swiss→MC→probs runs locally. All MC tests flipped from xfail to green; only the wave-4 backtest gate remains xfail.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 2 of 2
- **Files created:** 2 (+1 modified)

## Accomplishments

- `run_mc_progressive` is genuinely generator-first: it yields exactly `n_chunks` `Partial(done, total, running_p_adv)` payloads (one per pinned chunk) and `return`s the final `Result`; `run_mc` drains it via `next()`/`StopIteration.value` — the two-function split Phase 2 wraps with `@st.cache_data`, with no streamlit import (asserted by `test_no_forbidden_imports`).
- Reproducibility holds two ways (ENG-09/Pitfall 10): two independent `run_mc(seed=…)` calls return identical per-team 3-0/advance/0-3 counts (`test_reproducibility`), and the pinned default `n_chunks=20` reproduces an explicit `n_chunks=20` exactly (`test_reproducibility_survives_n_chunks_default`) — the backtest will run the SAME chunked path the app ships.
- The FULL per-sim record sample is retained on `Result.sample` (length N, one `{id:(wins,losses)}` map per sim), and every sim satisfies the structural laws exactly: 2×3-0, 2×0-3, 8 advance (`test_record_sample_retained`) — the Phase 3 Ballot B / Phase 4 re-sim seam.
- Invariants hold at N=50k within ±0.05 (`test_invariants`); in practice the sums are structurally exact (2.000/8.000/2.000) at any N.
- The epistemic outer loop is a single-draw no-op: the per-team reported `band_advance` equals `wilson(advance_count, N)` to 1e-12 (`test_epistemic_band_collapses_to_wilson`) — Phase 5 fills K Beta draws here without a rewrite (PROB-03/05).
- `wilson(k, n, z)` matches the closed-form Wilson score interval to 1e-12 and returns (0.0, 0.0) for n=0 (`test_wilson_closed_form`); no scipy (MC-02).
- `uv run python -m engine 5000` prints the 16-row per-team table sorted by P(advance) with Wilson bands and the invariant sums; eyeball-sane (GamerLegion tops P(3-0)=0.754 and P(advance)=0.999; THUNDER dOWNUNDER P(0-3)=0.400 and FlyQuest 0.308 top the bottom).
- Full suite: 20 passed, 1 xfailed (only the wave-4 backtest gate) — not falsely green.

## Task Commits

1. **RED: wave-3 MC tests** — `ae4632e` (test) — replaced the xfail scaffold with real assertions against `run_mc_progressive`/`run_mc`/`wilson`; failed with `ModuleNotFoundError: engine.montecarlo`.
2. **Task 1: run_mc_progressive (GREEN)** — `766fc04` (feat) — SeedSequence.spawn pinned chunks, sample retention, Wilson band, epistemic stub; all 8 MC tests green.
3. **Task 2: engine/__main__.py headless smoke run** — `f1ae4b5` (feat) — per-team table + Wilson bands + invariant sums; includes the Windows cp1252 ASCII fix (see Deviations).

## Files Created/Modified

- `engine/montecarlo.py` *(created)* — `wilson`, `Partial`, `Result` (with `p_30`/`p_advance`/`p_03` helpers), `_fresh_teams`, `_chunk_sizes`, `run_mc_progressive` (generator), `run_mc` (drainer). Imports numpy, `engine.probs.epistemic_draws`, `engine.swiss.simulate_stage`, `engine.teams`. No streamlit/httpx.
- `engine/__main__.py` *(created)* — `_parse_n` (T-03-02 validation/cap), `_drain`, `_fmt_band`, `main`; `uv run python -m engine [N]`.
- `tests/test_mc.py` *(modified)* — xfail scaffold replaced with 8 real tests: `test_wilson_closed_form`, `test_reproducibility`, `test_reproducibility_survives_n_chunks_default`, `test_record_sample_retained`, `test_invariants`, `test_progress_partials_yielded`, `test_epistemic_band_collapses_to_wilson`, `test_no_forbidden_imports`.

## Verification

| Check | Result |
|-------|--------|
| `uv run pytest -q tests/test_mc.py` | 8 passed |
| `uv run pytest -q` (full suite) | 20 passed, 1 xfailed (wave-4 backtest gate only) — not falsely green |
| `uv run python -m engine 5000` | prints 16-row table + Wilson bands + invariant sums; exit 0 |
| Reproducibility: two run_mc(seed) → identical counts; default n_chunks==explicit 20 | OK |
| Per-sim sample retained (len N, 2×3-0 / 2×0-3 / 8 advance every sim) | OK |
| Invariants at N=50k within ±0.05 (sums exactly 2.000/8.000/2.000) | OK |
| Reported band == inner Wilson (single source) to 1e-12 | OK |
| Eyeball sanity: GamerLegion tops P(3-0)/P(advance); THUNDER/FlyQuest top P(0-3) | OK |
| argv N rejects negative / NaN / huge (T-03-02) without crash/hang | OK |
| `engine.montecarlo` / `engine.__main__` import no streamlit/httpx/requests | OK |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `uv run python -m engine` crashed on Windows with `UnicodeEncodeError`**
- **Found during:** Task 2 (first run of the smoke command).
- **Issue:** The output used Unicode math symbols (`Σ`, `≈`, `±`, em-dash `—`). The author is on Windows, whose console defaults to the `cp1252` codec, which cannot encode `Σ` (`Σ`) — the program raised `UnicodeEncodeError` mid-print and the invariant-summary line (the load-bearing part of the smoke output) never printed, exiting non-zero. This is broken behavior on the documented target platform, not a feature gap.
- **Fix:** Replaced all Unicode glyphs in `__main__.py` output with ASCII equivalents (`sum P(...)`, `~2`, `+/-0.05`, `-`). The table, bands, and invariant line now print cleanly on cp1252; exit 0.
- **Files modified:** `engine/__main__.py`.
- **Commit:** `f1ae4b5`.

**2. [Rule 2 - Critical functionality] argv N DoS validation (threat T-03-02)**
- **Found during:** Task 2 (the plan's `<threat_model>` assigns T-03-02 `mitigate` to `__main__`).
- **Issue:** Raw `int(argv[1])` would accept negative/zero N (the MC raises, but with an opaque trace), accept absurd N (a multi-hour hang / OOM), and crash on non-integers (`nan`, floats) with an unhandled `ValueError`.
- **Fix:** `_parse_n` validates N is a positive int, caps it at `MAX_N=5_000_000`, and raises `SystemExit` with a clear message for negative/zero/NaN/huge/non-integer input. `run_mc_progressive` also guards `N <= 0` / `n_chunks <= 0` defensively.
- **Files modified:** `engine/__main__.py`, `engine/montecarlo.py`.
- **Commit:** `f1ae4b5` / `766fc04`.

## Known Stubs

None that block the plan goal. The `epistemic_draws` outer loop yields a single point draw by design (PROB-03/05 single-source no-op, owned by Phase 5) — this is the intended structured seam, not a placeholder: the loop is wired outer now and the band correctly collapses to Wilson. `ratings=None` flows through to each team's own rating (the Phase-5 override seam). `blend`/`var` passed to `epistemic_draws` are single-source placeholders (`var` all-zero); Phase 5 supplies real per-source values.

## Threat Flags

None. `engine.montecarlo`'s only input surface is the caller-supplied (seed, N, locked, ratings, n_chunks); no network/auth/DB. `__main__`'s only external surface is argv N, mitigated (T-03-02). The numpy RNG here is statistical, never repurposed for secrets.

## Notes for Later Waves

- **Wave 4 (the backtest gate, 01-04):** the backtest does NOT need the MC — it asserts `simulate_stage` GENERATES Budapest's actual round-by-round pairings off a fully-`locked` board. The MC's value to wave 4 is that `run_mc`'s reproducibility proves the chunked path is deterministic before the gate trusts it.
- **Phase 2 (Streamlit):** decorate a thin wrapper around `run_mc` with `@st.cache_data` keyed on `(ratings, S, N, locked)` — `locked` MUST be in the key (Phase 2×4 seam). Drive the progress bar by iterating `run_mc_progressive` directly on a cache miss (each `Partial` carries `done`/`total`/`running_p_adv`); serve `run_mc`'s `Result` on a hit. Do NOT re-chunk the progress loop in a way that changes `n_chunks` or reproducibility breaks.
- **Phase 3 (optimizer):** consume `Result.sample` (the retained per-sim record vectors) for Ballot B's P(≥5) hill-climb; never re-run the MC.
- **Phase 5 (odds):** fill `epistemic_draws` to yield K Beta draws; `run_mc_progressive` already aggregates across the outer loop, so the reported band will widen beyond Wilson automatically once spread > 0. `Result.band_*` is the place the epistemic spread must be folded in (currently == Wilson for one draw).

## Self-Check: PASSED

- Files: FOUND engine/montecarlo.py, FOUND engine/__main__.py, FOUND tests/test_mc.py
- Commits: FOUND ae4632e (RED), FOUND 766fc04 (Task 1 GREEN), FOUND f1ae4b5 (Task 2)
