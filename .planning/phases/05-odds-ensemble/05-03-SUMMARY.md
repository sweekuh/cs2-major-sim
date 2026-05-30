---
phase: 05-odds-ensemble
plan: 03
subsystem: odds
tags: [fetch-script, cache-seam, streamlit, fail-soft, httpx, python-dotenv, back-solve, epistemic]

# Dependency graph
requires:
  - phase: 05-odds-ensemble (05-01)
    provides: "odds/ package — OddsPapi/Polymarket/Kalshi adapters, pool() -> BlendedProb, _match resolver"
  - phase: 05-odds-ensemble (05-02)
    provides: "engine/backsolve.py (invert_series/fit_ratings) + run_mc(..., market_blend=...) epistemic seam"
  - phase: 02-app-shell
    provides: "app.py run path (_run_or_serve/_compute_or_serve/_cache_key_for), ui/state.py odds_key_present + banner"
provides:
  - "scripts/fetch_odds.py — the ONE odds entry (UI 'fetch now' button AND v2-cron `python -m scripts.fetch_odds`); load_dotenv, per-provider fail-soft, pool() per match, writes the frozen data/odds_cache.json schema"
  - "ui/odds_loader.py — json-only, version-gated, fail-soft None read seam (no httpx/dotenv/provider/engine import)"
  - "app.py odds wiring — valid cache back-solves ratings + feeds epistemic blend/var into the run path; _meta.fetched_at folds into the run cache key (stale-band guard); a 'Fetch odds now' button OUT of the render path"
  - "data/odds_cache.json frozen schema (the v2-cron drop-in contract) + gitignore"
affects: [06, odds-cache, cron, pickem-optimizer]

# Tech tracking
tech-stack:
  added: ["httpx>=0.28,<0.29 (0.28.1)", "python-dotenv>=1.2,<2 (1.2.2)"]
  patterns:
    - "Read-only cache seam: the app's ONLY odds contact is load_odds_cache() reading data/odds_cache.json; fetch is a separate script behind an explicit user action (Pitfall 11)"
    - "Lazy network-dep import: scripts.fetch_odds (httpx/dotenv) imported INSIDE the button click branch only, never at app module top (DX-01/T-05-APPIMPORT)"
    - "Stale-band cache-key guard: fold _meta.fetched_at into the run cache key so a var-only refetch invalidates the memoized Result"

key-files:
  created:
    - "scripts/__init__.py"
    - "scripts/fetch_odds.py"
    - "ui/odds_loader.py"
  modified:
    - "app.py — odds-cache wiring + fetch-now button + progress-fraction clamp"
    - "ui/cache.py — optimize_cached extended with the 5th fetched_at key element"
    - "tests/test_app.py — 6 Phase-5 odds tests"
    - "pyproject.toml — httpx + python-dotenv deps; odds/+scripts/ packaged"
    - ".gitignore — data/odds_cache.json"

key-decisions:
  - "Back-solve targets are MAP-level: each blended series p is inverted via invert_series(p, bo3) BEFORE fit_ratings (Pitfall 9); the top seed (min id) is the gauge anchor"
  - "fetched_at folded into the run cache key (clean 1-line extension) — NO stale-band limitation to document; optimize_cached signature extended to match"
  - "Progress fraction clamped into [0,1] in _drive_progress (the engine's running done-tally overshoots N*k under the epistemic outer loop; st.progress raises on >1) — engine NOT modified"
  - "discover_fixtures returns {} until Cologne markets post (DEFERRED) — a no-fixtures fetch writes a valid empty-blended cache, never an error"

patterns-established:
  - "v2-cron drop-in: ONE crontab line (`python -m scripts.fetch_odds`) writes the SAME file the app reads — zero app change"
  - "Fail-soft everywhere: no key + no cache -> rating-only + existing banner; empty/bad cache -> None; per-provider try/except"

requirements-completed: [ODDS-05, ODDS-06, ODDS-07, ODDS-08]

# Metrics
duration: ~75 min
completed: 2026-05-30
---

# Phase 5 Plan 03: Odds Cache Seam + Fetch Script Summary

**Read-only odds-cache seam wiring the 05-01 providers + 05-02 back-solve/epistemic into the app: `scripts/fetch_odds.py` (button AND v2-cron entry) writes a frozen `data/odds_cache.json`; the app reads it json-only via `ui/odds_loader.py`, back-solves ratings + feeds market blend/var into the existing MC run path, with `_meta.fetched_at` in the run cache key as the stale-band guard — all preserving the zero-config fail-soft first run.**

## Performance

- **Duration:** ~75 min
- **Started:** 2026-05-30T06:55Z (approx)
- **Completed:** 2026-05-30T07:15Z (approx)
- **Tasks:** 2 of 3 executed (Task 3 is a DEFERRED human-verify checkpoint — see Outstanding)
- **Files modified:** 8 (3 created, 5 modified)

## Accomplishments
- **`scripts/fetch_odds.py`** — the single fetch entry for both the UI "fetch now" button (lazy-imported in the click handler) and a future v2 cron (`python -m scripts.fetch_odds`). `load_dotenv()` (keys live here, never in the app), `discover_fixtures` reuses `build_round1_pairs` (never re-derives seeds), per-provider `try/except` fail-soft, `pool()` per match, writes the frozen schema `{_meta:{fetched_at ISO-8601 UTC, version, providers_present, round_hint}, blended:{"lo-hi":{p,var,n_sources,bo3}}}`. No streamlit import.
- **`ui/odds_loader.py`** — json + pathlib ONLY (no httpx/dotenv/provider/engine), version-gated, returns `None` on any error (missing/bad/wrong-version) → rating-only + the existing "live odds off" banner. Mirrors `read_seeds_confirmed`.
- **App wiring** — a valid non-empty cache back-solves per-team ratings (`invert_series` series→map, then `fit_ratings` gauge-anchored on the top seed) and carries `market_blend={"lo-hi":(p,var)}` into the epistemic OUTER loop via the existing `run_mc_progressive(..., market_blend=...)` seam, so the odds change the reported probabilities. A "Fetch odds now" button triggers the fetch OUT of the render path.
- **Stale-band guard (T-05-STALEBAND)** — `_meta.fetched_at` folded into `_cache_key_for(ratings, locked, fetched_at)` (clean 1-line extension; `optimize_cached` extended to match) so a fresh fetch that moves only `var` (not the back-solved ratings) still invalidates the memoized Result. **No stale-band limitation remains** — the key extension was clean.
- **Zero-config + fail-soft preserved** — no key + no cache → rating-only, existing banner, no crash; `odds_key_present()` stays `os.environ`-only; httpx/dotenv verified ABSENT from the app import path.

## Task Commits

1. **Task 1: deps gate + fetch script + json loader + RED tests** — `2e6aa8b` (feat)
2. **Task 2: app.py cache wiring + fetch-now button + GREEN** — `31c5d54` (feat)

**Plan metadata:** (this commit) (docs: complete plan)

## Files Created/Modified
- `scripts/__init__.py` — package marker (the only package importing httpx/dotenv at script level)
- `scripts/fetch_odds.py` — the ONE fetch entry; frozen-schema cache writer; per-provider fail-soft
- `ui/odds_loader.py` — json-only fail-soft read seam (no network deps)
- `app.py` — `_odds_from_cache` (back-solve + blend derivation), `_cache_key_for(..., fetched_at)`, `_compute_or_serve`/`_drive_progress` thread `market_blend`, "Fetch odds now" button, progress clamp
- `ui/cache.py` — `optimize_cached` gains the 5th `fetched_at` key element (defaults None; pre-Phase-5 sites unchanged)
- `tests/test_app.py` — 6 Phase-5 tests (loader fail-soft unit + 5 AppTest)
- `pyproject.toml` — httpx + python-dotenv pinned (PyPI-confirmed); `odds`/`scripts` packaged
- `.gitignore` — `data/odds_cache.json` (fetched artifact)

## Decisions Made
- **Map-level back-solve targets:** each blended series `p` is inverted to a map prob via `invert_series(p, bo3)` BEFORE `fit_ratings` (Pitfall 9 — fitting ratings to series probs would conflate Bo1/Bo3). Gauge anchor = the top seed (`min(t.id)`) held fixed. Verified the round-trip: a target map prob of 0.850 reproduces `p_map = 0.850` from the fitted ratings.
- **Clean `fetched_at` key extension chosen** over the documented-limitation fallback — `_cache_key_for` took the new arg in one line; `optimize_cached` was extended to keep `*cache_key` unpacking consistent.
- **`discover_fixtures` returns `{}`** until live markets post — the recorded-fixture path (tests + offline build) supplies fixtures explicitly via `main(fixtures=...)`; a no-fixtures fetch produces a valid empty cache.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Progress-fraction overshoot crashes st.progress under the epistemic outer loop**
- **Found during:** Task 2 (cache-fed run path)
- **Issue:** With a non-empty `market_blend` (var>0) the MC runs K epistemic draws, and `run_mc_progressive`'s running `done` tally can momentarily exceed `total` (the engine's `total_done` sums per-draw advance counts, not sims) → `frac = done/total` reached 1.3375 → `st.progress` raised `StreamlitAPIException: Progress Value has invalid value`. This only surfaces once odds feed the epistemic loop, so it was latent until this plan.
- **Fix:** Clamp `frac` into `[0.0, 1.0]` in `_drive_progress` (and cap the displayed counter at `total`). The progress bar is cosmetic; the engine's tally is out of this plan's scope (consumes 05-02, never mutates engine), so the defensive clamp in the app is the correct fix.
- **Files modified:** `app.py`
- **Verification:** `test_cache_present_feeds_sim` (var>0 odds-fed run) passes; full suite 113 passed; GATE-01 green.
- **Committed in:** `31c5d54` (Task 2 commit)

**2. [Rule 3 - Blocking] optimize_cached signature extended for the 5-element cache key**
- **Found during:** Task 2 (stale-band key extension)
- **Issue:** Folding `fetched_at` into the run cache key made `cache_key` a 5-tuple; the two `optimize_cached(result, *cache_key)` call sites unpack it positionally and would pass 5 args to a 4-arg-after-`_result` function.
- **Fix:** Added a 5th positional `fetched_at=None` to `optimize_cached` (in the cache-seam module `ui/cache.py`, within this plan's seam scope) so the optimizer memoizes on the SAME key as the run and `*cache_key` unpacks cleanly. Defaults None → pre-Phase-5 rating-only call sites are unchanged.
- **Files modified:** `ui/cache.py`
- **Verification:** Phase-3 ballot tests + Phase-4 LIVE delta-anchor tests still pass; full suite 113 passed.
- **Committed in:** `31c5d54` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking). **Impact:** Both necessary for the odds-fed run to work correctly; no scope creep. The engine and `odds/` package were NOT modified (this plan consumes the 05-01/05-02 seams).

## Known Stubs

**1. `discover_fixtures` live-URL discovery — `{}` (DEFERRED, intentional)**
- **File:** `scripts/fetch_odds.py` (`discover_fixtures`)
- **Reason:** IEM Cologne 2026 markets have NOT posted (2026-05-30 — the expected state), so the live slug/ticker/field-name shapes (Assumptions A2–A5) cannot be confirmed. The branch is marked `[DEFERRED — verify once Cologne markets post]`. This is NOT a UI stub: a no-fixtures fetch writes a valid empty-blended cache and the app stays fully fail-soft (rating-only + keyless). Resolved at the Task-3 human-verify checkpoint once markets go live (see Outstanding). The providers + parsers are built and unit-tested against recorded JSON fixtures; only the live discovery is deferred.

## Issues Encountered
- The Task-1 RED convention: three of the six new tests (`test_no_odds_failsoft`, `test_zero_config_first_run_still_works`, `test_app_makes_no_network_on_rerun`) are **preservation guards** that the existing app already satisfies (it already runs rating-only with the banner and never imports httpx), so they were GREEN from Task 1 — the xfail markers were removed from those three. Only the two wiring-dependent cases (`test_cache_present_feeds_sim`, `test_fresh_fetch_invalidates_cache`) carried xfail through Task 1 and flipped GREEN in Task 2.

## Outstanding (DEFERRED human-verify checkpoint — Task 3, NOT a build blocker)

Task 3 is a `checkpoint:human-verify` that is **deferred because IEM Cologne 2026 CS2 markets have not posted (2026-05-30 — the expected state).** The app is fully functional rating-only + keyless either way; this is an enhancement gate, not a failure.

**When Cologne markets post, the user must confirm via gstack `/browse` (never the mcp chrome tools — CLAUDE.md):**
1. **OddsPapi** — confirm CS2 IEM Cologne fixture coverage and the real `/fixtures` + `/odds` field names (tournament string, `bookmakerOdds`/market-id, participant names); adjust `odds/oddspapi.py` parsing + `discover_fixtures` if the recorded shapes differ. **Budget the ~250 req/month free quota** — manual button + per-round trigger only, no polling.
2. **Polymarket** — confirm the Cologne event slug and whether per-match (vs only tournament-winner) markets exist; adjust `odds/polymarket.py` (keyless Gamma `/events`).
3. **Kalshi** — confirm the CS2/Cologne series ticker (esports coverage is sparse — `[]` is a valid fail-soft result); adjust `odds/kalshi.py` (keyless trade-api v2).
4. Run `python -m scripts.fetch_odds` against the live endpoints, confirm `data/odds_cache.json` writes a non-empty `blended` map, then hit Run in the app and confirm the odds-fed probs move vs rating-only.

Resume signal: `"verified"` (live slugs confirmed + a live fetch populates the cache) or `"deferred"` (keep the recorded-fixture build until markets post).

## User Setup Required

**Optional external service** — see [05-USER-SETUP.md](./05-USER-SETUP.md):
- `ODDSPAPI_KEY` (OddsPapi dashboard, free tier ~250 req/month) — leave blank to run keyless (Polymarket+Kalshi) or rating-only. The app needs NO key for the first run.

## Next Phase Readiness
- Phase 5 (Odds Ensemble) all 3 plans executed (05-01 core, 05-02 back-solve/epistemic, 05-03 cache seam). The odds layer is wired end-to-end against recorded fixtures; the only outstanding item is the deferred live-slug confirmation (gated on markets posting).
- The v2-cron drop-in seam (ONE crontab line, zero app change) is ready (ODDS-07/OPS-01).
- GATE-01 Budapest backtest stays GREEN (no engine mutation). Full suite: 113 passed (107 baseline + 6 new).

## Self-Check: PASSED

- Created files exist on disk: `scripts/__init__.py`, `scripts/fetch_odds.py`, `ui/odds_loader.py`, `.planning/phases/05-odds-ensemble/05-03-SUMMARY.md`, `.planning/phases/05-odds-ensemble/05-USER-SETUP.md` — all FOUND.
- Task commits exist: `2e6aa8b` (Task 1), `31c5d54` (Task 2) — both FOUND.
- `uv run pytest -q tests/test_app.py` → 34 passed (incl. the 6 new Phase-5 tests, no xfails).
- `uv run pytest -q` → 113 passed (107 baseline + 6 new). GATE-01 `test_backtest_budapest_2025` GREEN.
- T-05-APPIMPORT verified: no httpx / python-dotenv / scripts.fetch_odds in the app top-level import graph.
- No engine/ or odds/ mutation (this plan consumes the 05-01/05-02 seams).

---
*Phase: 05-odds-ensemble*
*Completed: 2026-05-30*
