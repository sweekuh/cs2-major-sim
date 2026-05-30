---
phase: 05-odds-ensemble
plan: 01
subsystem: odds
tags: [odds, de-vig, log-opinion-pool, providers, pure-core, tdd, numpy]

# Dependency graph
requires:
  - phase: 01-engine-core
    provides: engine.teams.load_teams (id/name map for team-string -> engine-id resolution); engine.probs.beta_moment_fit (downstream var clamp, used in 05-02)
provides:
  - "odds/base.py — OddsQuote + BlendedProb frozen dataclasses, OddsProvider Protocol, devig_fixed_two_way, normalize_market_price, pool() log-opinion pool with cross-source epistemic variance (PURE numpy)"
  - "odds/oddspapi.py — OddsPapiProvider: fixed-odds de-vig + soft-book bundle pre-pooled to ONE Pinnacle-anchored opinion (Pitfall 7)"
  - "odds/polymarket.py + odds/kalshi.py — keyless market-price providers (normalize, never two-way de-vig; empty-market -> [])"
  - "odds/_match.py — shared team-string -> engine-id resolver (keeps base.py engine-free)"
  - "tests/test_odds.py + tests/fixtures/{oddspapi,polymarket,kalshi}_sample.json — 10 odds-core tests against recorded fixtures"
affects: [05-02-backsolve-epistemic, 05-03-fetch-cache-ui]

# Tech tracking
tech-stack:
  added: []  # no new deps — base/pool are numpy-only; httpx install belongs to 05-03
  patterns:
    - "De-vig routed on vig_type at the call site (fixed -> devig_fixed_two_way; market -> normalize_market_price)"
    - "Within-provider pre-pool collapses correlated soft books to ONE independent opinion before the cross-provider pool"
    - "Log-opinion pool = originate/liquidity-weighted geometric mean in logit + delta-method cross-source variance"
    - "httpx lazy-imported INSIDE the live-fetch method only — parse path is import-time httpx-free"
    - "Providers accept a parsed dict OR a path (no network); engine import isolated to odds/_match.py"

key-files:
  created:
    - odds/__init__.py
    - odds/base.py
    - odds/oddspapi.py
    - odds/polymarket.py
    - odds/kalshi.py
    - odds/_match.py
    - tests/test_odds.py
    - tests/fixtures/oddspapi_sample.json
    - tests/fixtures/polymarket_sample.json
    - tests/fixtures/kalshi_sample.json
  modified: []

key-decisions:
  - "Lazy-import httpx inside fetch() only (never module-top) so the parse path collects with no httpx installed and nothing leaks into the app import path (D1/DX-01) — verified httpx NOT in sys.modules after import+parse"
  - "Added odds/_match.py to isolate the engine.teams import, keeping odds/base.py + pool() strictly engine-free and pure"
  - "Provider get_quotes signature: get_quotes(fixtures, *, teams) accepting a parsed dict OR a path; teams is the engine team list, from which providers build the name->id map"
  - "Soft-book originate weights: Pinnacle 1.0, soft copies 0.3 — Pinnacle-anchors the within-bundle pre-pool without an equal-weight headcount"

patterns-established:
  - "Pattern: de-vig is a routing decision on vig_type, never a default — market prices are price≈prob (spread/fee only), fixed odds get the two-way overround removal"
  - "Pattern: correlated sources are pre-pooled to one opinion within the provider, so the cross-provider pool counts independent originators not books"

requirements-completed: [ODDS-01, ODDS-02, ODDS-03, ODDS-05]

# Metrics
duration: ~25 min
completed: 2026-05-29
---

# Phase 5 Plan 01: Pure Odds Core Summary

**The `odds/` package — vig_type-routed de-vig (fixed two-way overround vs market price-normalize), the OddsPapi soft-book bundle pre-pooled to ONE Pinnacle-anchored opinion, and an originate/liquidity-weighted log-opinion pool emitting `BlendedProb(p, var, n_sources, bo3)` — all pure numpy, TDD-proven against recorded fixtures with httpx kept out of the import path.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 3 (RED test, base.py GREEN, providers GREEN)
- **Files created:** 10 (6 source, 1 test, 3 fixtures)
- **Files modified:** 0 (zero engine/app/ui mutation, as scoped)

## Accomplishments
- De-vig routed on `vig_type`: `devig_fixed_two_way(1.5, 2.5) == 0.625` for OddsPapi fixed odds; `normalize_market_price` for the prediction markets — a market price is provably NOT two-way de-vigged (Pitfall 8 guard green).
- The OddsPapi soft-book bundle (Pinnacle + 3 soft books) collapses to EXACTLY ONE Pinnacle-anchored `OddsQuote` per match before `pool()` sees it, so the cross-provider pool never headcounts the soft books (Pitfall 7 guard green).
- `pool()` is an originate/liquidity-weighted log-opinion pool (geometric mean in logit + delta-method cross-source variance): agreeing sources -> var≈0, disagreeing sources -> var>0, single source -> var≈0.
- Keyless fail-soft fact proven: Polymarket + Kalshi (keyless public reads) still pool to `n_sources == 2` with no `ODDSPAPI_KEY`; an empty Kalshi market yields `[]`, never an error.
- httpx confined to the live-fetch branch (lazy import) — verified `httpx` is NOT in `sys.modules` after importing and parsing all three providers, so the app import path stays clean (DX-01).

## Task Commits

1. **Task 1: tests/test_odds.py + recorded fixtures (RED)** - `eedc059` (test)
2. **Task 2: odds/base.py — dataclasses, de-vig, log-opinion pool (GREEN)** - `f308cfe` (feat)
3. **Task 3: odds/{oddspapi,polymarket,kalshi}.py + _match.py (GREEN)** - `226f8c8` (feat)

## Files Created/Modified
- `odds/__init__.py` - package marker + httpx-confinement invariant docstring
- `odds/base.py` - OddsQuote/BlendedProb dataclasses, OddsProvider Protocol, `devig_fixed_two_way`, `normalize_market_price`, `_logit`/`_sigmoid`, `pool()` (pure numpy)
- `odds/oddspapi.py` - OddsPapiProvider: per-book fixed de-vig + Pinnacle-anchored bundle pre-pool to one quote
- `odds/polymarket.py` - PolymarketProvider: Gamma `/events` market-price normalize, keyless
- `odds/kalshi.py` - KalshiProvider: `trade-api/v2/markets` yes-mid normalize, keyless, empty-market -> []
- `odds/_match.py` - shared team-string -> engine-id resolver (case/space-insensitive contains)
- `tests/test_odds.py` - 10 odds-core tests (de-vig routing, pool variance, bundle-one-opinion, provider parse, empty-market, keyless 2-source)
- `tests/fixtures/{oddspapi,polymarket,kalshi}_sample.json` - recorded-shape JSON for one Cologne matchup (GamerLegion vs NRG)

## Decisions Made
- **httpx confinement is import-time, not just runtime:** the fixture-parse path (`get_quotes`) does NOT import httpx; httpx is lazy-imported inside the deferred `fetch()` network branch only. This was the load-bearing constraint from the plan — verified by asserting `httpx` stays out of `sys.modules`.
- **`odds/_match.py` added** to isolate the `engine.teams` import so `odds/base.py`/`pool()` remain strictly engine-free and pure numpy.
- **Originate weights** Pinnacle=1.0 / soft books=0.3 anchor the within-bundle pre-pool on the sharp originator without an equal-weight headcount.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking/Structural] Added `odds/_match.py` (not in the literal `files_modified` list)**
- **Found during:** Task 3 (providers)
- **Issue:** All three providers need a team-string -> engine-id resolver that imports `engine.teams`. Putting that import in `odds/base.py` would violate the "base.py/pool() are pure, engine-free" invariant (D1/DX-01); duplicating it in each provider would fork the alias logic.
- **Fix:** Extracted the resolver to a single shared `odds/_match.py` that owns the lone `engine.teams` import, keeping `base.py` pure and the alias logic in one place.
- **Files modified:** `odds/_match.py` (new)
- **Verification:** All 10 `tests/test_odds.py` pass; `odds.base` import asserted free of httpx/engine/streamlit; full suite 99 green.
- **Committed in:** `226f8c8` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 structural/blocking).
**Impact on plan:** The extra module strengthens the D1/DX-01 purity boundary rather than expanding scope — `base.py` stays engine-free exactly as the plan requires. No engine/app/ui mutation; no new dependencies.

## Issues Encountered
None. The TDD RED step collected correctly (`ModuleNotFoundError: No module named 'odds'`), base.py logic was verified directly before the providers existed (the full test module can only collect once all provider imports resolve, so Task 2 was validated via a direct numpy check + a `sys.modules` purity assertion), and Task 3 flipped all ten tests green in one pass.

## User Setup Required
None - no external service configuration required. (Live slug/ticker confirmation and the httpx/python-dotenv install are deferred to 05-03.)

## Next Phase Readiness
- **05-02 (back-solve + epistemic) is unblocked** — it depends only on the frozen engine and is parallel-safe with this plan; `BlendedProb(p, var, n_sources, bo3)` is the contract it will consume.
- **05-03 (fetch script + cache + UI)** can now import `OddsPapiProvider`/`PolymarketProvider`/`KalshiProvider` and `pool()`; the live-fetch (`fetch()`) branch is stubbed `NotImplementedError`, to be wired against live slugs at the 05-03 user `checkpoint:human-verify`.
- **Verification:** `uv run pytest -q tests/test_odds.py` -> 10 passed; `uv run pytest -q` -> 99 passed (89 baseline + 10 new); GATE-01 `test_backtest_budapest_2025` -> 3 passed (no engine mutation).

## Self-Check: PASSED

- Created files exist on disk: `odds/{__init__,base,oddspapi,polymarket,kalshi,_match}.py`, `tests/test_odds.py`, `tests/fixtures/{oddspapi,polymarket,kalshi}_sample.json` — all FOUND.
- Commits exist: `eedc059` (RED), `f308cfe` (base.py), `226f8c8` (providers) — all FOUND in `git log`.
- Full suite 99 green; GATE-01 backtest green; httpx confirmed out of the parse import path.

---
*Phase: 05-odds-ensemble*
*Completed: 2026-05-29*
