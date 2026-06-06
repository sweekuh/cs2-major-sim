# Phase 6: Multi-stage scaffold + live-results seam - Pattern Map

**Mapped:** 2026-06-04
**Files analyzed:** 14 new/modified files
**Analogs found:** 14 / 14 (every new file has a shipped, read-this-session analog)

> Phase 6 is a *copy-the-shipped-seam* phase. Almost nothing here is a new design — it is
> (1) a sibling loader wrapper, (2) one new cache-key positional, and (3) a structural TWIN
> of the already-shipped odds seam. Each section below quotes the REAL current source of the
> analog (line numbers from a direct read 2026-06-04) so the executor copies the exact shape.

## FROZEN-PATH GUARDRAIL (read first)

`engine/teams.py` `load_teams` / `_DEFAULT_FIXTURE` / `_validate_fixture` is the **byte-frozen
GATE-01 path**. `tests/test_backtest_budapest_2025.py` (GATE-01) is the only real check on the
pairing logic and it MUST stay green. The new `load_stage(path)` and `_validate_fixture_for_size(rows, size)`
are **SIBLINGS that live alongside the frozen functions — never edits to their bodies.**

- GATE-01 builds its own `Team` objects and imports `simulate_stage`/`build_round1_pairs`/`Team`
  directly — it does NOT call `load_teams`. [VERIFIED: `tests/test_backtest_budapest_2025.py:26-27, 56-59`]
- BUT `test_live.py`, `test_app.py`, `conftest.py`, and the shipped app all call `load_teams()`
  and assume Stage-1's 16 teams. Editing the loader's default breaks those.
- **WRONG (flag in review):** any diff that touches lines `engine/teams.py:74-100` (`_validate_fixture`),
  `:30-47` (`_DEFAULT_FIXTURE`), or `:110-140` (`load_teams`). Parameterizing `_validate_fixture`
  with a `size=STAGE_SIZE` default still EDITS a frozen function — prefer the new sibling.
- The freeze-regression companion test (`test_load_teams_unchanged`) must assert `load_teams()`
  still returns the byte-identical 16-team Stage-1 list AND GATE-01 stays green.

## File Classification

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `ui/results_loader.py` (NEW) | loader / read-seam | file-I/O (read-only) | `ui/odds_loader.py` | exact |
| `scripts/fetch_results.py` (NEW) | data-acquisition / fetcher | request-response → file-I/O | `scripts/fetch_odds.py` | exact |
| `data/results_cache.json` (NEW) | config / runtime artifact | file-I/O (gitignored) | `data/odds_cache.json` | exact |
| `data/team_aliases.json` (NEW) + slug join | config / data + helper reuse | transform (slug→id) | `odds/_match.py::resolve_id` + Budapest `team_aliases` block | role-match |
| `engine/teams.py` `load_stage`/`_validate_fixture_for_size` (NEW siblings) | model / loader wrapper | file-I/O → validate | `engine/teams.py` `load_teams`/`_validate_fixture` (FROZEN — wrap, do not edit) | exact (sibling) |
| `ui/cache.py` `run_mc_cached`/`optimize_cached` (MODIFY) | cache boundary | transform (memoize) | the existing signatures in `ui/cache.py:47-88` | exact (in-place) |
| `data/stage2.json` (NEW minimal fixture) | config / data | file-I/O | `data/stage1.json` | exact |
| `tests/test_teams_load_stage.py` (NEW) | test | — | GATE-01 `test_backtest_budapest_2025.py` + load_teams behavior | role-match |
| `tests/test_results_loader.py` (NEW) | test | — | `test_app.py::test_cache_loader_failsoft` (lines 750-785) | exact |
| `tests/test_results_fetch.py` (NEW) | test | — | `tests/test_odds.py` recorded-fixture pattern | exact |
| `tests/fixtures/bo3gg_finished_sample.json` (NEW) | test fixture | — | `tests/fixtures/kalshi_sample.json` (recorded provider fixture) | role-match |
| `app.py` stage selector + `stage_id` thread (MODIFY) | controller / UI | request-response | `app.py:550-557` `_cache_key_for` + `:820` optimizer splat | exact (in-place) |
| `app.py` fetch-results button (MODIFY) | controller / UI | event-driven (click) | `app.py:288-330` odds fetch button (lazy-import) | exact |
| `app.py` pre-fill `locked` + conflict-confirm (MODIFY) | controller / UI | event-driven | `app.py:689-711` `_commit_lock` + `engine/live.py` validate/prefix | exact |
| `.env.example` + `.gitignore` (MODIFY) | config | — | existing `.env.example` / `.gitignore` | exact |

---

## Pattern Assignments

### `ui/results_loader.py` (NEW — loader, read-only file-I/O)

**Analog:** `ui/odds_loader.py` (read VERBATIM this session — the whole file is 53 lines).

**Copy this structure exactly — swap only the path + supported version + docstring.** The module
imports ONLY `json` + `pathlib` (no httpx / dotenv / provider / engine import) so the zero-config
first run is preserved and the no-network-on-rerun test stays green.

Module docstring intent + imports (`ui/odds_loader.py:21-32`):
```python
from __future__ import annotations

import json
from pathlib import Path

# Default cache path — mirrors scripts.fetch_odds.DEFAULT_OUT but kept local (this module imports no
# scripts/ code, so httpx/dotenv stay out of the app import path).
_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "odds_cache.json"

# The only schema version this loader accepts — a version bump must be a deliberate loader change, so
# a stale/foreign schema fails closed to None (rating-only) rather than feeding mis-shaped data.
_SUPPORTED_VERSION = 1
```

Core fail-soft read (`ui/odds_loader.py:35-52`) — return `None` on ANY error, never raise:
```python
def load_odds_cache(path: str | Path | None = None) -> dict | None:
    src = Path(path) if path is not None else _CACHE_PATH
    try:
        raw = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    meta = raw.get("_meta")
    if not isinstance(meta, dict) or meta.get("version") != _SUPPORTED_VERSION:
        return None
    return raw
```

**For results:** rename `load_odds_cache` → `load_results_cache`, point `_CACHE_PATH` at
`data/results_cache.json`, keep `_SUPPORTED_VERSION = 1`. The four fail-soft branches
(missing / malformed / non-dict / wrong-version → `None`) are the load-bearing contract — copy them
1:1. Do NOT add a httpx or `scripts.fetch_results` import (that re-opens the network-on-rerun bug).

---

### `scripts/fetch_results.py` (NEW — fetcher, request-response → atomic file-I/O)

**Analog:** `scripts/fetch_odds.py` (read VERBATIM — 213 lines).

**Five load-bearing patterns to copy from the odds fetcher:**

1. **Lazy dotenv + httpx-logger-to-WARNING (the key never leaks)** (`scripts/fetch_odds.py:132-136`):
```python
    load_dotenv_safe()  # keys live HERE (T-05-SECRET); never imported by the app
    # httpx logs the full request URL (incl. the ?apiKey=… query param) at INFO — force WARNING so
    # the OddsPapi key is NEVER emitted to logs/stdout (T-05-SECRET).
    for _n in ("httpx", "httpcore"):
        logging.getLogger(_n).setLevel(logging.WARNING)
```
For results the key is the optional `PANDASCORE_KEY` (FALLBACK A); bo3.gg + Kalshi-derived are keyless.
Same `?token=`/`Authorization` leak risk → keep the WARNING clamp.

2. **`load_dotenv_safe()` — dotenv imported INSIDE the function, fail-soft** (`scripts/fetch_odds.py:195-207`):
```python
def load_dotenv_safe() -> None:
    try:
        from dotenv import load_dotenv
    except Exception as exc:  # noqa: BLE001 — dotenv missing is fail-soft (keyless run still works)
        log.warning("python-dotenv unavailable (%s); running with the ambient environment", exc)
        return
    load_dotenv()
```

3. **Per-provider try/except fail-soft — a provider failure logs + continues** (`scripts/fetch_odds.py:70-78, 103-115`):
```python
    try:
        return Provider().get_quotes(fixtures_for_provider, teams=teams)
    except Exception as exc:  # noqa: BLE001 — fail-soft: a provider failure logs + continues
        log.warning("provider %s failed: %s", getattr(Provider, "name", Provider), exc)
        return []
```
Mirror this for the provider ladder bo3.gg → PandaScore → Kalshi-derived: a missing key skips its
provider (`log.info("no PANDASCORE_KEY — skipping PandaScore fallback")`, mirroring `:106`), a dead
endpoint logs + falls through, no market → an empty-but-valid cache, NEVER an exception.

4. **ISO-8601 UTC `_meta.fetched_at` + versioned cache + atomic write** (`scripts/fetch_odds.py:174-192`):
```python
    cache = {
        "_meta": {
            # ISO-8601 UTC at WRITE time — the app's run cache key folds this in (T-05-STALEBAND).
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "version": CACHE_VERSION,
            "providers_present": providers_present,
            "round_hint": 1,
        },
        "blended": blended,
    }
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cache, indent=2), encoding="utf-8")
```
For results, swap `"blended"` for `"results"` (the row list, schema below) and add `"source"`/`"stage"`
to `_meta`. Keep `mkdir(parents=True, exist_ok=True)` + `write_text` (the atomic-write idiom).

5. **httpx is lazy-imported INSIDE the fetch method only** — the odds providers do this
(`scripts/fetch_odds.py` imports `OddsPapiProvider`/`KalshiProvider` whose `.fetch()` lazy-imports
httpx; the recorded-fixture `get_quotes` path imports nothing). The `__main__` guard
(`scripts/fetch_odds.py:210-212`) makes it runnable as `python -m scripts.fetch_results`:
```python
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
```

**Provider-id join inside the fetcher:** `fetch_odds.py:137` does `teams = load_teams()` then the
providers map names via `odds/_match`. The results fetcher must call `load_stage(path)` for the active
stage's teams (NOT `load_teams()` — it must work for any stage) and join slug-first (see `team_aliases.json`
below). FINISHED-only filter: drop any row whose status is not `finished`/`settled`.

---

### `data/results_cache.json` (NEW — gitignored runtime artifact)

**Analog:** `data/odds_cache.json` (versioned read-only cache) + its `.gitignore` entry.

**Frozen schema to write** (from RESEARCH §"Frozen results-cache schema" — freeze the STACK.md
`match:[lo,hi]`/`winner` shape so it matches `OddsQuote.match` orientation + the `freeze_locked`
round-trip):
```json
{
  "_meta": {"fetched_at": "<iso-utc>", "version": 1, "source": "bo3gg|pandascore|kalshi", "stage": 1},
  "results": [
    {"match": [9, 1], "winner": 1, "round_idx": 0, "bo": 1, "status": "finished",
     "provider_slugs": ["gamerlegion", "nrg"]}
  ]
}
```
- `match` is the SORTED `[lo, hi]` engine-id tuple (same orientation as `OddsQuote.match`).
- `winner` is the engine id; `round_idx` is 0-based (R1 == 0) — matches `KEY_LOCKED`'s
  `(round_idx, winner_id, loser_id)` shape so the loser is recoverable as `lo if winner==hi else hi`.

**Gitignore it like the odds cache.** The current `.gitignore:7-10` entry:
```
# Fetched odds cache (a runtime artifact, not source — ODDS-07). Its ABSENCE is the normal
# first-run state and is handled fail-soft (rating-only + banner). scripts/fetch_odds.py writes
# it; the app only ever READS it via ui/odds_loader.py.
data/odds_cache.json
```
Add a parallel `data/results_cache.json` block with the same comment shape. [VERIFIED: `.gitignore`
ignores `data/odds_cache.json`; `data/stage1.json` is NOT ignored — so per-stage fixtures +
`team_aliases.json` stay COMMITTED, only `results_cache.json` is ignored.]

---

### `data/team_aliases.json` (NEW — committed) + slug-first join

**Analog (helper):** `odds/_match.py::resolve_id` (lines 25-38). **Analog (file convention):** the
Budapest fixture's `team_aliases` block (`tests/fixtures/budapest_2025_stage1.json:38-55`).

The reused resolver (`odds/_match.py:25-38`) — exact normalized hit first, then substring either
direction, then `None` so the caller DROPS rather than guessing:
```python
def resolve_id(name: str, name_to_id: dict[str, int]) -> int | None:
    key = _norm(name)
    if key in name_to_id:
        return name_to_id[key]
    for cand, tid in name_to_id.items():
        if key and (key in cand or cand in key):
            return tid
    return None
```
`_norm` (`:20-22`) is `"".join(s.lower().split())` (case/space-insensitive). `build_name_to_id`
(`:15-17`) maps `_norm(t.name) -> t.id` from a loaded team list.

The existing committed convention (`budapest_2025_stage1.json:38-55`) is `{internal_name -> provider_short}`:
```json
  "team_aliases": {
    "M80": "M80",
    "FlyQuest": "FLY",
    "PARIVISION": "PV",
    "GamerLegion": "GL"
  }
```
**For results:** create `data/team_aliases.json` as `{provider_slug -> internal_name}` (or `-> engine_id`).
The join is **slug-first** (exact alias hit on the provider's slug), then `resolve_id` name-substring
fallback, then **DROP + log on no match — never guess** (a mis-join fabricates a lock that corrupts
the re-sim and the Phase-7 seeding chain). An unresolved team must surface a LOUD banner
("couldn't map team X — enter manually"), never a silent mis-lock.

> **EVENT-TIME DEFERRAL:** the real Cologne provider slugs are a `/browse` verify once markets post.
> Seed `team_aliases.json` with placeholder slugs now; it is editable and the drop-on-unresolved path
> keeps it fail-soft. Do NOT block the phase on it. [RESEARCH A1, "VERIFY AT EVENT TIME"]

---

### `engine/teams.py` `load_stage(path)` + `_validate_fixture_for_size(rows, size)` (NEW SIBLINGS)

**Analog:** `engine/teams.py` `load_teams` (`:110-140`) + `_validate_fixture` (`:74-100`) — the
**FROZEN GATE-01 path. WRAP, NEVER EDIT** (see the guardrail at the top of this doc).

The frozen `_validate_fixture` body to MIRROR (not edit) into a size-parameterized sibling
(`engine/teams.py:74-100`):
```python
def _validate_fixture(rows: dict[int, tuple[str, float]]) -> None:
    seeds = list(rows.keys())
    if len(seeds) != STAGE_SIZE:
        raise ValueError(f"fixture must have exactly {STAGE_SIZE} teams, got {len(seeds)}")
    if set(seeds) != set(range(1, STAGE_SIZE + 1)):
        raise ValueError(f"seeds must be exactly 1..{STAGE_SIZE}, got {sorted(seeds)}")
    names = [name for name, _ in rows.values()]
    if len(set(names)) != len(names):
        raise ValueError("duplicate team name in fixture")
    for seed, (name, rating) in rows.items():
        if not isinstance(rating, (int, float)):
            raise ValueError(f"rating for seed {seed} ({name}) is not numeric: {rating!r}")
        if rating != rating or not (0 < rating < 1000):
            raise ValueError(f"rating for seed {seed} ({name}) out of range: {rating!r}")
```
**New sibling `_validate_fixture_for_size(rows, size)`:** same body, but replace every `STAGE_SIZE`
with the `size` parameter. Leave the frozen `_validate_fixture` byte-identical (it keeps the literal
`STAGE_SIZE = 16` for Stage-1/GATE-01).

The frozen `load_teams` JSON-load + dup-seed guard to MIRROR (`engine/teams.py:118-140`):
```python
    if path is None and not DATA_PATH.exists():
        return _teams_from_rows(_DEFAULT_FIXTURE)
    src = Path(path) if path is not None else DATA_PATH
    raw = json.loads(src.read_text(encoding="utf-8"))
    teams_json = raw.get("teams") if isinstance(raw, dict) else raw
    ...
    rows: dict[int, tuple[str, float]] = {}
    for entry in teams_json:
        ...
        seed = entry["seed"]
        if seed in rows:
            raise ValueError(f"duplicate seed {seed} in {src}")
        rows[seed] = (entry["name"], entry["rating"])
    return _teams_from_rows(rows)
```

**New `load_stage(path)` shape** (RESEARCH §Pattern 1 — reads `stage.size` from the JSON, validates
against THAT size, returns `(teams, stage_config)`; never calls the frozen path):
```python
def load_stage(path: str | Path) -> tuple[list[Team], dict]:
    """Load any per-stage fixture, validated against its OWN declared stage.size.
    Returns (teams, stage_config). load_teams / _DEFAULT_FIXTURE / _validate_fixture
    (the GATE-01 path) are NOT called and NOT edited."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    stage = raw.get("stage") or {}
    size = int(stage.get("size", 16))
    rows: dict[int, tuple[str, float]] = {}
    for entry in raw["teams"]:                       # keep load_teams's dup-seed guard
        seed = entry["seed"]
        if seed in rows:
            raise ValueError(f"duplicate seed {seed} in {path}")
        rows[seed] = (entry["name"], entry["rating"])
    _validate_fixture_for_size(rows, size)           # NEW size-parameterized sibling
    teams = [Team(id=s, name=n, seed=s, rating=float(r)) for s, (n, r) in sorted(rows.items())]
    return teams, {"size": size, "seeds_confirmed": bool(raw.get("seeds_confirmed", False)), **stage}
```
Reuse the existing `Team` dataclass (`engine/teams.py:50-71`) and `sorted(rows.items())` ordering —
identical to `_teams_from_rows` (`:102-107`). Everything downstream (`build_round1_pairs:143-150`,
`simulate_stage`, `difficulty`) iterates `teams`, never `STAGE_SIZE`, so it is stage-size-agnostic
already. [VERIFIED via RESEARCH §Pattern 1 — `build_round1_pairs` iterates `teams`.]

---

### `ui/cache.py` `run_mc_cached` / `optimize_cached` (MODIFY — add `stage_id` positional) — STG-04 GATE

**Analog:** the existing signatures in `ui/cache.py:47-88` (quote them exactly). **This is the
correctness gate** — `stage_id` must be a REAL positional arg in BOTH keys, NEVER a leading-underscore
escape (that silences `UnhashableParamError` but EXCLUDES it from the key → cross-stage stale serve).

The module docstring already documents the underscore trap to AVOID (`ui/cache.py:1-13`):
```
The leading-underscore escape (``_locked``) silences the error but EXCLUDES the arg from the
key — which silently serves stale pre-lock distributions in Live mode. The correct fix: convert
``locked`` to a deterministic hashable tuple, key the cache on that real arg, and reconstruct
inside the wrapper.
```

CURRENT `run_mc_cached` (`ui/cache.py:47-65`) — note line 64 `teams = load_teams()` is the v3 BUG
(always Stage 1):
```python
@st.cache_data(show_spinner=False)
def run_mc_cached(
    ratings_key: tuple, S: float, N: int, locked_key: tuple
) -> Result:
    ratings = dict(ratings_key)
    locked = {frozenset(pair): winner for pair, winner in locked_key}
    teams = load_teams()                       # ← v3 BUG: always Stage 1
    return run_mc(teams, ratings, S, N, locked=locked, seed=FIXED_SEED)
```

CURRENT `optimize_cached` (`ui/cache.py:68-88`) — note line 88 `load_teams()` is the same bug;
`_result` correctly carries the underscore (it IS a pure function of the rest of the key):
```python
@st.cache_data(show_spinner=False)
def optimize_cached(
    _result: Result,
    ratings_key: tuple,
    S: float,
    N: int,
    locked_key: tuple,
    fetched_at=None,
) -> OptimizerOutput:
    return optimize(_result, load_teams())     # ← v3 BUG: always Stage 1
```

**v3 TARGET — `stage_id` LEADING (first) positional in BOTH; load the RIGHT fixture via `load_stage`:**
```python
@st.cache_data(show_spinner=False)
def run_mc_cached(stage_id: str, ratings_key: tuple, S: float, N: int, locked_key: tuple) -> Result:
    teams, _cfg = load_stage(_path_for_stage(stage_id))   # NOT load_teams()
    ratings = dict(ratings_key)
    locked = {frozenset(pair): winner for pair, winner in locked_key}
    return run_mc(teams, ratings, S, N, locked=locked, seed=FIXED_SEED)

@st.cache_data(show_spinner=False)
def optimize_cached(_result: Result, stage_id: str, ratings_key: tuple, S: float, N: int,
                    locked_key: tuple, fetched_at=None) -> OptimizerOutput:
    teams, _cfg = load_stage(_path_for_stage(stage_id))
    return optimize(_result, teams)
```
- Keep `_result` underscore-escaped (correct HERE only — `optimize_cached` docstring `:77-87`).
- `stage_id` is a short string `"stage1"|"stage2"|"stage3"|"playoffs"`. Add a `_path_for_stage(stage_id)`
  helper mapping it to `data/stageN.json`.
- **Order matters:** `app.py:820` splats `optimize_cached(result, *cache_key)`, so the tuple element
  order in `_cache_key_for` MUST match `optimize_cached`'s params AFTER `_result`. Leading-first means
  `_cache_key_for` returns `(stage_id, ...)` first too.

---

### `data/stage2.json` (NEW minimal fixture)

**Analog:** `data/stage1.json` (per-stage fixture schema — read verbatim, 27 lines).

Copy the exact schema (`data/stage1.json:1-27`): top-level `_comment`, `stage:{size,advance_at_wins,
eliminate_at_losses}`, `seeds_confirmed`, `teams:[{seed,name,rating}]`. For Stage 2 ship
**`"seeds_confirmed": false`** (real qualifier seeds derive in Phase 7) with `[INFERRED]` placeholder
team names — that is what makes the per-stage banner show. The stage block:
```json
  "stage": {
    "size": 16,
    "advance_at_wins": 3,
    "eliminate_at_losses": 3
  },
  "seeds_confirmed": true,
  "teams": [
    { "seed": 1, "name": "GamerLegion", "rating": 92 },
    ...
  ]
```
(All v3 Swiss fixtures are size 16; `playoffs.json` is size 8 — RESEARCH A4. Phase 6 only needs a
minimal second fixture so the cross-stage cache-isolation AppTest has a real second stage to switch to.)

---

## App Wiring (`app.py` MODIFY)

### Stage selector + `stage_id` threading — STG-04 (the integration gate)

**Analog:** `app.py:550-557` `_cache_key_for` + `:820` optimizer splat.

CURRENT `_cache_key_for` (`app.py:550-557`):
```python
def _cache_key_for(ratings: dict, locked: dict, fetched_at=None):
    """The ``(ratings_key, S, int(N), locked_key, fetched_at)`` cache tuple."""
    return (freeze_ratings(ratings), S, int(N), freeze_locked(locked), fetched_at)
```
**v3 TARGET** — add `stage_id` LEADING, keep the SAME order as `optimize_cached`'s params after `_result`:
```python
def _cache_key_for(ratings: dict, locked: dict, stage_id: str, fetched_at=None):
    return (stage_id, freeze_ratings(ratings), S, int(N), freeze_locked(locked), fetched_at)
```
The optimizer splat to keep consistent (`app.py:820`): `opt = optimize_cached(result, *cache_key)`.

Build the selector with `st.selectbox`/`st.radio` writing a new `KEY_STAGE` session key; pass its
value into every `_cache_key_for` / `_compute_or_serve` call and into `run_mc_cached`.

**Existing tests that BREAK on this change (executor MUST update — they index `k[3]`):**
- `tests/test_app.py::test_locked_in_cache_key` (lines 114-127) — calls `run_mc_cached(rk, 40.0, 2000, lk_empty)`
  (4 args). Add `stage_id` as the new first arg: `run_mc_cached("stage1", rk, 40.0, 2000, lk_empty)`.
- `tests/test_app.py::test_live_lock_changes_cache_key:541` — `assert any(k[3] != () for k in new_keys)`
  → becomes `k[4]` (leading `stage_id` shifts locked_key from index 3 → 4).
- `tests/test_app.py::test_live_lock_moves_p_advance:552` — `pre_key = next(k for k in cache if k[3] == ())`
  → `k[4]`; `post_key = next(k for k in cache if k[3] != ())` (`:561`) → `k[4]`.
- `tests/test_app.py::test_live_delta_anchor_uses_pre_key:684, 698` — both `k[3]` → `k[4]`.
- `tests/test_ui_helpers.py::test_run_mc_cached_uses_frozen_seed_and_default_chunks` (RESEARCH says
  lines 381-401) — calls `run_mc_cached(rk, 40.0, 2000, lk)` → add the leading `stage_id`.
- NOTE the `KEY_MC_CACHE` comment in `ui/state.py:47` (`dict: (ratings_key, S, N, locked_key) -> Result`)
  should gain `stage_id` too.

> The index updates are mechanical. Insert `stage_id` LEADING (clearer scoping) and bump `k[3]`→`k[4]`,
> OR insert trailing to keep indices stable (less honest). RESEARCH recommends LEADING. [Open Question 1]

### Per-stage `[INFERRED]`-seed banner — STG-05

**Analog:** `app.py:155-195` banner + toggle, backed by `ui/state.py:126-139` `read_seeds_confirmed`
+ `:103` `KEY_SEEDS_CONFIRMED`.

`read_seeds_confirmed` ALREADY takes a path arg (`ui/state.py:126-139`) — pass the active stage's
fixture path:
```python
def read_seeds_confirmed(path: str | Path | None = None) -> bool:
    src = Path(path) if path is not None else _DATA_PATH
    try:
        raw = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(raw.get("seeds_confirmed", False)) if isinstance(raw, dict) else False
```
The banner-seeding pattern to parameterize per-stage (`app.py:158-159`):
```python
    if KEY_SEEDS_CONFIRMED not in st.session_state:
        st.session_state[KEY_SEEDS_CONFIRMED] = read_seeds_confirmed()
```
**v3:** make the session key per-stage (`f"seeds_confirmed_{stage_id}"`) and call
`read_seeds_confirmed(stage_fixture_path)`. Each stage's fixture carries its own `seeds_confirmed`
(`stage1.json` ships `true`; `stage2/3` ship `false`), so the warning persists per-stage until that
stage is positively confirmed. The `st.warning` + reconcile expander + `st.toggle` block
(`app.py:174-195`) is reused verbatim, just keyed per stage.

### Fetch-results button (lazy-import) — RES-01

**Analog:** `app.py:288-330` the odds "Fetch odds now" button.

The exact lazy-import-inside-the-click-branch idiom + persisted-outcome pattern (`app.py:299-330`):
```python
    _outcome = st.session_state.pop(KEY_ODDS_OUTCOME, None)
    if _outcome:
        {"success": st.success, "info": st.info, "error": st.error}.get(_outcome[0], st.info)(_outcome[1])
    if st.button("Fetch odds now", key="fetch_odds_btn"):
        with st.spinner("Contacting books — Pinnacle / Polymarket / Kalshi…"):
            try:
                from scripts.fetch_odds import main as _fetch_odds_main  # LAZY — click branch only
                cache = _fetch_odds_main()
                ...
            except Exception as exc:  # noqa: BLE001 — the button NEVER crashes the app (fail-soft)
                st.session_state[KEY_ODDS_OUTCOME] = ("error", f"Odds fetch failed (running rating-only): {exc}")
        st.rerun()
```
**For results:** a "Fetch latest results" button that `from scripts.fetch_results import main` INSIDE
the click branch only, wraps the call in `st.spinner` + try/except fail-soft, stashes a persisted
outcome (`KEY_RESULTS_OUTCOME`), then `st.rerun()`. The persisted-outcome stash (`:295-303`) is
load-bearing: a message drawn before `st.rerun()` is discarded — stash it and render on the next run.
This keeps httpx out of the import path (`test_app_makes_no_network_on_rerun:952-971` is the guard).

### Pre-fill `locked` from fetched results + conflict-confirm — RES-02/03

**Analog:** `app.py:689-711` `_commit_lock` + the reused `engine/live.py` contracts (validate /
prefix-guard, all UNCHANGED — zero engine edit).

CURRENT `_commit_lock` (`app.py:689-711`) — the EXACT path every lock (manual OR fetched) must flow through:
```python
def _commit_lock(pending: tuple[int, int, int]) -> None:
    round_idx, winner_id, loser_id = pending
    locked_results = st.session_state.get(KEY_LOCKED, [])
    try:
        legal = legal_pairings_for_round(teams, locked_results, S, round_idx)
    except Exception as exc:  # incomplete prefix — should not happen from the gated controls
        st.error(str(exc))
        return
    reason = validate_lock((winner_id, loser_id), round_idx, locked_results, teams, legal)
    if reason is not None:
        st.error(reason)                       # illegal — KEY_LOCKED + mc_cache stay untouched
    else:
        st.session_state[KEY_LOCKED] = add_lock(locked_results, round_idx, winner_id, loser_id)
```

The reused engine seams (DO NOT reimplement — `engine/live.py`):
- `locked_dict_from_results(locked_results)` (`:47-58`) — projects `list[(round_idx, w, ell)]` →
  `{frozenset((w,ell)): w}` (the exact `freeze_locked` shape).
- `validate_lock(new, round_idx, locked_results, teams, legal_pairings)` (`:82-148`) — returns a
  human reason string or `None`. Five illegal cases (winner-not-in-pair, rematch, terminated,
  non-pairing, double-booking) with EXACT reason strings. Every fetched lock routes through this — no bypass.
- `legal_pairings_for_round(teams, locked_results, S, round_idx)` (`:269-316`) — raises
  `LivePrefixIncomplete` (`:209-217`) if a prior round is not fully locked. Auto-derivation must fire
  ONLY on a complete validated prefix.
- `ui.state.add_lock(locked_results, round_idx, winner_id, loser_id)` (`ui/state.py:191-202`) —
  returns a NEW list (never mutates). The non-empty `KEY_LOCKED` then flows UNCHANGED through
  `locked_dict` → `freeze_locked` → cache key → conditional re-sim.

**RES-02 projection (per fetched result row), reusing the above** — recover the loser from the sorted
match tuple, then run the SAME guard/validate path as a manual lock:
```python
results = load_results_cache()                 # ui/results_loader.py (read-only)
if results:
    for row in results["results"]:             # current stage only
        lo, hi = row["match"]; w = row["winner"]; ell = lo if w == hi else hi
        pending = (row["round_idx"], w, ell)
        # 1) prefix guard via legal_pairings_for_round (LivePrefixIncomplete)
        # 2) RES-03 conflict check vs an existing MANUAL lock for the same pair → require confirm
        # 3) validate_lock(...) → reject illegal fetched locks with the existing reason string
        # 4) on accept + no conflict → ui.state.add_lock(KEY_LOCKED, *pending)
```

**RES-03 conflict-confirm:** a fetched result that conflicts with an existing MANUAL lock for the
same pair requires explicit user confirm (show the diff loudly via `st.warning`) — NEVER a silent
overwrite (the manual lock is authoritative ground truth). An un-locked match may pre-fill, still
subject to `validate_lock`. Tag provenance (auto vs manual) and surface `_meta.fetched_at` staleness
(reuse `ui.render.fmt_age`/`is_stale` — RESEARCH §Don't Hand-Roll). New session keys for the
active stage, per-stage `seeds_confirmed`, and pending-conflict state go in `ui/state.py`.

---

## Shared Patterns

### Fail-soft read-only cache (loader contract)
**Source:** `ui/odds_loader.py:35-52`
**Apply to:** `ui/results_loader.py`
The four-branch `None`-on-error read (missing / malformed / non-dict / wrong-version), JSON+pathlib
only, never raises into the UI, no httpx/dotenv/engine import. Copy 1:1.

### Lazy-import network deps inside the click branch / fetch method
**Source:** `app.py:308` (`from scripts.fetch_odds import main` inside the button branch),
`scripts/fetch_odds.py:135-136, 203` (httpx-logger WARNING + dotenv-inside-function)
**Apply to:** the fetch-results button + `scripts/fetch_results.py`
httpx NEVER enters the app import path; the app imports only `ui/results_loader.py`. Guard:
`test_app_makes_no_network_on_rerun` (`tests/test_app.py:952-971`).

### Slug/name → engine-id resolution (one resolver, drop-on-unresolved)
**Source:** `odds/_match.py:25-38` (`resolve_id`) + `:15-22` (`build_name_to_id`/`_norm`)
**Apply to:** the results provider→engine-id join
Slug-first via `team_aliases.json`, `resolve_id` substring fallback, DROP + loud banner on no match.
One trust boundary — never a second name resolver, never a `name == name` join.

### Route every lock through the existing validator (no engine edit)
**Source:** `engine/live.py:47-58, 82-148, 269-316` + `app.py:689-711` `_commit_lock`
**Apply to:** RES-02 auto-prefill
Auto-derived locks flow through `locked_dict_from_results` → `legal_pairings_for_round` (prefix guard)
→ `validate_lock` → `add_lock`, identically to manual locks. No bypass — the engine invariants hold.

### Versioned cache + ISO `_meta.fetched_at` folded into the cache key (staleness)
**Source:** `scripts/fetch_odds.py:174-187` (write) + `app.py:550-557` `_cache_key_for` (fold)
**Apply to:** `data/results_cache.json` + the app's results read
`_meta.version:1` (a bump is a deliberate loader change); ISO-UTC `fetched_at` at write time, folded
into the `@st.cache_data` key so a fresh fetch invalidates the memoized re-sim (T-05-STALEBAND).

### Secret never logged
**Source:** `scripts/fetch_odds.py:132-136` (httpx/httpcore logger → WARNING; `load_dotenv` lives in scripts)
**Apply to:** `scripts/fetch_results.py` (the optional `PANDASCORE_KEY`)
The key VALUE is never returned or logged — presence-only. `.env` gitignored; `.env.example` gains a
commented `PANDASCORE_KEY=` line. Guard: `test_env_example_present_and_gitignored`
(`tests/test_app.py:456-473`) — extend its assertions if the executor adds the new key line.

---

## Test Patterns

### `tests/test_results_loader.py` (RES-04)
**Analog:** `tests/test_app.py::test_cache_loader_failsoft` (lines 750-785) — copy 1:1 against
`load_results_cache`. The four fail-soft cases + the valid-v1-round-trip:
```python
    assert load_odds_cache(tmp_path / "nope.json") is None        # missing
    bad.write_text("{not json", ...); assert load_odds_cache(bad) is None      # malformed
    arr.write_text("[1, 2, 3]", ...); assert load_odds_cache(arr) is None      # non-dict
    wrongver.write_text(json.dumps({"_meta": {"version": 2}, ...}), ...)        # wrong version → None
    good.write_text(json.dumps({"_meta": {..., "version": 1}, ...}), ...)       # valid v1 round-trips
```
Swap the valid payload's `"blended"` for `"results"` (the row schema above).

### `tests/test_results_fetch.py` (RES-01/RES-05)
**Analog:** `tests/test_odds.py:1-60` recorded-fixture pattern — PURE / fixture-driven, NO network,
httpx stays out of the import path. Load a recorded `tests/fixtures/bo3gg_finished_sample.json`
(mirror `tests/fixtures/kalshi_sample.json`), parse it to `(match, winner, round_idx)` rows, assert an
unparseable row is DROPPED (never raises), and assert the slug-first join resolves a slug to the right
engine id while an unresolved team fails soft.

### `tests/test_teams_load_stage.py` (STG-01 + the freeze companion)
**Analog:** GATE-01 `tests/test_backtest_budapest_2025.py` (it builds its own `Team`s and never calls
`load_teams` — `:26-27, 56-59`) + `load_teams` behavior. Two duties:
- `test_load_stage_*` — `load_stage(path)` validates against the JSON's `stage.size`, returns
  `(teams, cfg)`, rejects a dup/short seed set LOUDLY (mirror `_validate_fixture`'s raises).
- `test_load_teams_unchanged` (FREEZE REGRESSION) — `load_teams()` still returns the byte-identical
  16-team Stage-1 list after the loader generalization, AND GATE-01 stays green. This is the proof the
  frozen path was not perturbed.

### `tests/test_ui_helpers.py::test_stage_id_in_cache_key` (STG-04 unit)
**New** — two stages with the SAME `(ratings, S, N, locked)` under different `stage_id` → DIFFERENT
cached Results; same `stage_id` → cache HIT (same object). The smallest proof of cross-stage isolation.

---

## No Analog Found

None. Every new/modified file in Phase 6 has a shipped, read-this-session analog. The only items
held for an event-time `/browse` verify are DATA values, not patterns:

| Item | Reason held |
|------|-------------|
| Cologne provider tournament slug/id (bo3.gg / PandaScore) | Markets not posted until ~event time; the fetcher filters by tournament dynamically (never hardcode an id). [RESEARCH A1/A2] |
| `data/team_aliases.json` real Cologne slugs | Same event-time `/browse` pass; the file is editable + drop-on-unresolved keeps it fail-soft. [RESEARCH A1] |

---

## Metadata

**Analog search scope:** `ui/`, `scripts/`, `engine/`, `odds/`, `data/`, `tests/`, repo root
(`.gitignore`, `.env.example`).
**Files read this session (live source, line-cited above):** `ui/odds_loader.py`, `ui/cache.py`,
`ui/state.py`, `odds/_match.py`, `scripts/fetch_odds.py`, `engine/teams.py`, `engine/live.py`,
`app.py` (§§155-195, 280-340, 540-570, 680-720, 800-835), `data/stage1.json`, `.gitignore`,
`.env.example`, `tests/test_app.py` (§§114-134, 456-473, 521-565, 668-704, 750-785, 952-971),
`tests/test_backtest_budapest_2025.py:1-70`, `tests/test_odds.py:1-60`,
`tests/fixtures/budapest_2025_stage1.json:30-59`.
**Pattern extraction date:** 2026-06-04
