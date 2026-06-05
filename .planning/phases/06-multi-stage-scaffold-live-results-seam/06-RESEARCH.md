# Phase 6: Multi-stage scaffold + live-results seam - Research

**Researched:** 2026-06-04
**Domain:** Streamlit multi-stage cache-keying + a fail-soft live-results auto-ingest seam onto a FROZEN, GATE-01-gated Monte Carlo Swiss engine
**Confidence:** HIGH (every claim grounded in a direct read of the shipped source; provider API shapes carry forward verified prior research from `.planning/research/STACK.md`, 2026-06-02)

## Summary

Phase 6 makes the app multi-stage-aware and stands up the live-results auto-ingest seam, **without touching the frozen engine**. It is a pure *additive sibling-module + additive-cache-key-arg* phase: nothing in `engine/` changes. The two correctness gates are (1) GATE-01 (`tests/test_backtest_budapest_2025.py`) stays byte-green because the loader generalization is a NEW `load_stage(path)` wrapper that leaves `load_teams`/`_DEFAULT_FIXTURE` untouched, and (2) STG-04 — `stage_id` becomes a REAL positional cache-key arg in BOTH `run_mc_cached` and `optimize_cached`, or switching stages silently serves another stage's cached numbers.

The results seam is a **structural twin of the already-shipped odds seam** — `scripts/fetch_results.py` (out-of-app httpx, mirrors `scripts/fetch_odds.py`) writes a read-only, versioned `data/results_cache.json`; `ui/results_loader.py` (JSON+pathlib only, mirrors `ui/odds_loader.py`) reads it; the app folds `_meta.fetched_at` into the cache key (the `T-05-STALEBAND` discipline) and pre-fills the existing `KEY_LOCKED` lock list, which already flows through `engine.live.locked_dict_from_results` → `freeze_locked` → the cache key → conditional re-sim. **Zero new engine work** — the lock list is the existing Phase-4 contract; the fetch just pre-fills it. Provider team identities join slug-first via a committed `data/team_aliases.json` (reusing `odds/_match.resolve_id`), and an unresolved team OR a fetch that conflicts with a manual lock is surfaced LOUDLY and requires explicit confirm.

**Primary recommendation:** Slice 1 = stage selector + `load_stage(path)` + `stage_id`-in-cache-key working end-to-end for the EXISTING Stage 1 (prove cross-stage isolation with a test before any results ingest). Slice 2 = the results seam (fetch_results → results_loader → pre-fill `locked` → conflict-confirm). Treat the Cologne provider slugs + `team_aliases.json` seeding as a DEFERRED event-time `/browse` verify — document the API shape and exactly what to confirm; do not block on markets that have not posted.

## Project Constraints (from CLAUDE.md)

These are load-bearing and OVERRIDE any default recommendation. The planner must verify compliance:

- **Engine freeze:** v3 makes exactly ONE engine edit total, and it is NOT in this phase (it is `all_bo3=False` in Phase 8). Phase 6 is all NEW sibling modules / wrapper functions / additive cache-key args. If a plan requires editing `engine/swiss.py` pairing logic or the `load_teams`/`_DEFAULT_FIXTURE` body, the approach is wrong — flag it.
- **GATE-01 is a HARD GATE and MUST stay green** — `tests/test_backtest_budapest_2025.py` reproduces Budapest 2025 Stage 1 pairings exactly. The loader generalization must not perturb the `load_teams` / `_DEFAULT_FIXTURE` code path. [VERIFIED: ran `uv run pytest tests/test_backtest_budapest_2025.py` 2026-06-04 — 3 passed.]
- **Buchholz / Difficulty = `Σ(opp.wins − opp.losses)`** via the canonical `engine.probs.difficulty` — never a second copy. (Not edited this phase; Phase 7 consumes it.)
- **APIs only, no scraping.** Keys from env (`.env` gitignored). Missing key → fail soft + banner, never a crash. First run needs no results source.
- **Stack pins:** Python ≥3.12, Streamlit 1.57.* (pinned), numpy 2.4.x, `httpx` for fetching (lazy-imported, never in the app import path), `python-dotenv`. Avoid pandas/scipy. Bootstrap is `uv run streamlit run app.py`. **v3 adds ZERO new runtime deps** — `httpx` + `numpy` + stdlib cover the results seam.
- **Seeds + default ratings are [INFERRED]** — keep editable, show the loud in-app banner, reconcile against the official seed list at lock. Per-stage in v3.
- **Web fetching uses gstack `/browse`** — never `mcp__claude-in-chrome__*`. This matters for the event-time slug verify.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STG-01 | User selects stage (Stage 1/2/3/Playoffs); each loads its own teams/seeds from a per-stage fixture (`data/stageN.json`, `data/playoffs.json`) via a `load_stage(path)` wrapper that leaves the GATE-01 `load_teams` path frozen. | §STG-01 — `load_stage` design + per-stage fixture schema (mirrors `data/stage1.json`); `_validate_fixture`/`STAGE_SIZE` analysis; selector wiring in `app.py`. |
| STG-04 | The `@st.cache_data` keys for BOTH `run_mc_cached` and `optimize_cached` include `stage_id` as a real positional arg, so switching stages never serves another stage's cached numbers. **[correctness gate]** | §STG-04 — exact current signatures, what Streamlit hashes, the leading-underscore pitfall, the exact insertion point, and the existing tests that break + how to update them. |
| STG-05 | A per-stage `[INFERRED]`-seed banner persists and seeds stay editable for each stage until that stage's seeds are positively confirmed against the official list. | §STG-05 — the existing banner/`read_seeds_confirmed`/`KEY_SEEDS_CONFIRMED` mechanism + how to make it per-stage. |
| RES-01 | "Fetch latest results" pulls FINISHED series (final outcomes only) over the provider ladder (bo3.gg → PandaScore → Kalshi-derived), writing a read-only `data/results_cache.json`; the app only reads (httpx never in the app import path). | §RES-01/RES-04 — `scripts/fetch_results.py` design mirroring `fetch_odds.py`; FINISHED-only filter; provider API shapes. |
| RES-02 | Fetched results pre-fill the current stage's `locked` set so the existing conditional re-sim runs from auto-locked results without manual entry. | §RES-02 — the lock-list projection path; reuse of `LivePrefixIncomplete`. |
| RES-03 | An auto-fetched result never silently overwrites a manual lock — a conflict requires explicit user confirm; provenance (auto vs manual) and stale-cache state (`_meta.fetched_at`) surfaced. | §RES-03/RES-05 — conflict detection + confirm-UX shape; provenance tagging. |
| RES-04 | Fail-soft — missing key / network failure / unavailable source degrades to manual entry + banner, never a crash or gate; first run needs no results source. | §RES-01/RES-04 — the read-only-cache fail-soft contract, byte-for-byte from the odds seam. |
| RES-05 | Provider team identities join to internal Team ids slug-first via `data/team_aliases.json` (reusing `odds/_match.py`); an unresolved team is surfaced loudly, never silently mis-locked. | §RES-03/RES-05 — slug-first join, the existing `team_aliases` convention, drop-on-unresolved discipline. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Stage selection (which fixture/teams) | Presentation (`app.py` selector) | — | UI state choice; drives which data file loads + the `stage_id` in the cache key. Pure UI concern. |
| Per-stage fixture load + validation | Domain (`engine/teams.py` NEW `load_stage`) | Data (`data/stageN.json`) | A NEW wrapper reads `stage.size` from JSON and validates against it; reuses `Team`/`_teams_from_rows`. Leaves the frozen `load_teams` default path untouched. |
| Stage-scoped cache isolation | Cache boundary (`ui/cache.py` + `app.py:_cache_key_for`) | — | `stage_id` folds into the key tuple. The single most important integration point — miss it and every stage past Stage 1 silently renders another stage's probs. |
| Results fetch (network) | Data-acquisition (`scripts/fetch_results.py`) | External (bo3.gg / PandaScore / Kalshi) | Sole results fetcher + key holder, OUT of the render path. `httpx` lazy-imported inside `fetch()`. |
| Results read (app-side) | Presentation read seam (`ui/results_loader.py`) | Data (`data/results_cache.json`) | JSON+pathlib only; never raises into the UI; no httpx/engine import. Mirrors `ui/odds_loader.py`. |
| Provider team → engine-id join | Domain helper (`odds/_match.resolve_id`) reused | Data (`data/team_aliases.json`) | Slug-first via the alias map, name-substring fallback; drop-on-unresolved. Same trust boundary as the odds parsers. |
| Pre-fill `locked` + conditional re-sim | Domain (`engine.live` — REUSED unchanged) | — | The fetched lock list is the existing Phase-4 `KEY_LOCKED` contract. No engine work. |
| Conflict / [INFERRED]-seed banners | Presentation (`app.py` + `ui/render.py`) | Session state (`ui/state.py`) | Loud `st.warning` + explicit confirm; reuses the existing banner/toggle/session-state patterns. |

## Standard Stack

### Core (all already present — v3 adds ZERO runtime deps)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| streamlit | 1.57.* (pinned) | UI shell, `@st.cache_data`, session state, the stage selector + fetch button | Already the app's only UI framework; the `@st.cache_data` hashing rule is the heart of STG-04. [CITED: CLAUDE.md stack pins] |
| numpy | 2.4.x | (unchanged) MC engine + replay | Already pinned; results seam needs no numpy beyond the existing replay. [CITED: CLAUDE.md] |
| httpx | >=0.28,<0.29 (already pinned) | The new results fetcher's HTTP client | Already in the stack and already confined to the fetch layer; the results fetcher is a sibling of `scripts/fetch_odds.py` — same lazy-`import httpx`-inside-`fetch()` discipline. [CITED: .planning/research/STACK.md] |
| python-dotenv | >=1.0,<2.0 (already pinned) | Load an optional `PANDASCORE_KEY` for the fallback provider | Only the PandaScore fallback needs a key; bo3.gg + Kalshi-derived are keyless. Same `load_dotenv_safe()` pattern as `scripts/fetch_odds.py`. [CITED: .planning/research/STACK.md] |
| stdlib `json` / `pathlib` | stdlib | Parse responses; write/read `data/results_cache.json` | Mirror `ui/odds_loader.py` exactly: a JSON+pathlib read-only loader the app imports. No parsing dep. [VERIFIED: read `ui/odds_loader.py`] |

### Alternatives Considered (results provider ladder)
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| bo3.gg (PRIMARY) | PandaScore free Fixtures tier (FALLBACK A) | bo3.gg is keyless + near-real-time but an undocumented endpoint; PandaScore is documented + stable but needs a key (1000 req/hr free). Use bo3.gg primary, PandaScore as the robust fallback if bo3.gg's shape shifts. [CITED: .planning/research/STACK.md] |
| bo3.gg / PandaScore | Kalshi-derived (FALLBACK B, already wired) | Kalshi settles **1–12 h after** the match ends — too slow as primary; fine as an offline backstop reading the existing `KXCS2GAME` `result`/`status:"settled"` field. [CITED: .planning/research/STACK.md] |
| any of the above | Liquipedia LPDB / GRID Series Events | Liquipedia = educational-only ToS + 1 req/2 s + wiki-edit lag; GRID Series Events is paid. Explicitly excluded. [CITED: .planning/research/STACK.md, REQUIREMENTS.md Out of Scope] |

**Installation:** No `pyproject.toml` change. `.env.example` gains an optional commented `PANDASCORE_KEY=` line (primary path is keyless; first run still needs no key).

**Version verification:** No new packages to slopcheck — this phase installs nothing. The Package Legitimacy Audit below is N/A.

## Package Legitimacy Audit

**Not applicable.** Phase 6 installs ZERO external packages — every dependency (`httpx`, `numpy`, `python-dotenv`, stdlib `json`/`pathlib`, `streamlit`) is already declared and shipped in v1.0. The only `.env.example` addition is a commented `PANDASCORE_KEY=` placeholder for a free PandaScore account (the FALLBACK A provider); obtaining that key is a user action, not a package install. No slopcheck pass is required.

## Architecture Patterns

### System Architecture Diagram

```
                          ┌─────────────────────── PRESENTATION (app.py + ui/) ───────────────────────┐
  user clicks             │  [NEW] stage selector: Stage 1 | Stage 2 | Stage 3 | Playoffs             │
  "Stage 2"  ────────────▶│        └─ picks data/stageN.json  AND  a stage_id IN THE CACHE KEY         │
                          │  [NEW] "fetch latest results" button (explicit click, NEVER on rerun)      │
  user clicks             │        └─ LAZY-imports scripts.fetch_results (httpx stays out of import)   │
  "fetch results" ───────▶│  [NEW] conflict-confirm + per-stage [INFERRED]-seed banner                 │
                          └──────────────────────────────────┬────────────────────────────────────────┘
                                                             │
                       ┌─────── @st.cache_data / session cache boundary ────────┐
                       │  key = (▸stage_id◂, ratings, S, N, locked, fetched_at)  │  ← stage_id NEW (STG-04)
                       └──────────────────────────────────┬─────────────────────┘
                                                          │
   data/stageN.json ──load_stage(path)──▶ teams ─────────▼──────────  DOMAIN / CORRECTNESS CORE (engine/ — FROZEN)
   (size, seeds_confirmed, teams[])                       run_mc(teams, ...)  ── reuses simulate_stage UNCHANGED
                                                          │              │
   data/results_cache.json ──results_loader──▶ lock list │              ▼
   (READ ONLY, fetched by scripts/)            (round,w,l)│      engine.live.locked_dict_from_results  (REUSED)
                                                          │              │  pre-fills `locked` → conditional re-sim
                                                          ▼              ▼
                                              engine.live.legal_pairings_for_round / validate_lock  (REUSED)
                                                          │  rejects illegal fetched locks with existing reason strings
   ─────────────────── DATA-ACQUISITION (out of render path) ───────────────────
   scripts/fetch_results.py  ──httpx (lazy)──▶  bo3.gg | PandaScore | Kalshi-derived
        │  FINISHED series only · slug-first join via data/team_aliases.json (odds/_match.resolve_id)
        └─ writes ▶ data/results_cache.json  (read-only artifact; gitignored; absence = manual-entry mode)
```

Trace the primary use case: user selects Stage 2 → selector loads `data/stage2.json` via `load_stage` AND sets `stage_id="stage2"` → cache key now carries `stage_id` so it cannot collide with Stage 1 → user clicks "fetch results" → `fetch_results.py` pulls FINISHED Stage-2 series, joins teams via the alias map, writes `results_cache.json` → `results_loader` reads it → projects to the `(round, winner, loser)` lock list → `engine.live.validate_lock` accepts/rejects → pre-fills `KEY_LOCKED` → conditional re-sim runs from the auto-locked results.

### Recommended Project Structure (NEW + ADDITIVE only)
```
data/
├── stage1.json          # EXISTS (the frozen-load fixture; load_stage reads it too)
├── stage2.json          # [NEW] per-stage fixture (invited VRS + [INFERRED] qualifier placeholders)
├── stage3.json          # [NEW] (carries an all_bo3 flag for Phase 8; not used this phase)
├── playoffs.json        # [NEW] 8-team fixture (size:8; not simulated this phase)
├── team_aliases.json    # [NEW] {internal_name -> provider_slug} OR {provider_slug -> engine_id} join map
├── odds_cache.json      # EXISTS (gitignored runtime artifact)
└── results_cache.json   # [NEW] gitignored runtime artifact, written by scripts/fetch_results.py
engine/
└── teams.py             # [ADDITIVE] add load_stage(path) WRAPPER; load_teams/_DEFAULT_FIXTURE BYTE-FROZEN
ui/
├── cache.py             # [ADDITIVE] stage_id as a real positional key arg in BOTH wrappers
├── results_loader.py    # [NEW] JSON+pathlib read-only loader (mirrors ui/odds_loader.py)
└── state.py             # [ADDITIVE] stage session-state keys; per-stage seeds_confirmed
scripts/
└── fetch_results.py     # [NEW] the ONLY results fetcher (mirrors scripts/fetch_odds.py)
results/                 # [NEW, OPTIONAL] provider parsers (bo3gg.py, pandascore.py) — or inline in fetch_results
app.py                   # [ADDITIVE] stage selector, fetch-results button, conflict-confirm, per-stage banner
```

### Pattern 1: `load_stage(path)` as a wrapper that leaves the frozen path byte-identical
**What:** A NEW function in `engine/teams.py` that reads `stage.size` from the JSON, validates against THAT size, and returns `(teams, stage_config)` — never touching `load_teams` or `_DEFAULT_FIXTURE`.
**When to use:** Every stage load in v3 (the app calls `load_stage`, not `load_teams`, except where Stage-1 zero-config defaulting is wanted).
**Why it's safe:** `Team`, `build_round1_pairs`, `rank_group`, the pairing fold, and `difficulty` are ALL stage-size-agnostic already — they iterate `teams`, never `STAGE_SIZE`. [VERIFIED: read `engine/swiss.py` — no `STAGE_SIZE` reference in the pairing path; read `engine/teams.py:143-150` `build_round1_pairs` iterates `teams`.] The only frozen-risk is `_validate_fixture`'s hardcoded `STAGE_SIZE`; `load_stage` must validate against a per-stage size instead of importing that path.

```python
# engine/teams.py — [ADDITIVE], the GATE-01 path (load_teams/_DEFAULT_FIXTURE/_validate_fixture) UNTOUCHED.
# Source pattern: derived from the existing load_teams (engine/teams.py:110-140) + ARCHITECTURE.md §1.
def load_stage(path: str | Path) -> tuple[list[Team], dict]:
    """Load any per-stage fixture, validated against its OWN declared size.

    Returns (teams, stage_config) where stage_config carries size/advance/eliminate/
    seeds_confirmed (+ a bo3_all flag Phase 8 consumes). load_teams / _DEFAULT_FIXTURE /
    _validate_fixture (the GATE-01 path) are NOT called and NOT edited.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    stage = raw.get("stage") or {}
    size = int(stage.get("size", 16))
    rows = {e["seed"]: (e["name"], e["rating"]) for e in raw["teams"]}  # + dup-seed guard, see load_teams
    _validate_fixture_for_size(rows, size)   # NEW size-parameterized validator (sibling, not the frozen one)
    teams = [Team(id=s, name=n, seed=s, rating=float(r)) for s, (n, r) in sorted(rows.items())]
    return teams, {"size": size, "seeds_confirmed": bool(raw.get("seeds_confirmed", False)), **stage}
```

**Note for the planner:** the existing `_validate_fixture` hardcodes `STAGE_SIZE = 16` and is imported nowhere outside `engine/teams.py`. Two clean options: (a) a NEW `_validate_fixture_for_size(rows, size)` sibling (preferred — keeps the frozen one literally untouched), or (b) parameterize `_validate_fixture` with a `size=STAGE_SIZE` default (the default keeps Stage-1/GATE-01 byte-identical, but it edits a frozen-path function, so option (a) is safer given the freeze rule). All four v3 Swiss/playoff fixtures except playoffs are 16-team; `playoffs.json` is size 8.

### Pattern 2: `stage_id` as a REAL positional cache-key arg (STG-04, the correctness gate)
**What:** Thread `stage_id` (a short string, e.g. `"stage1"`/`"stage2"`/`"stage3"`/`"playoffs"`) into the `@st.cache_data` key of BOTH `run_mc_cached` and `optimize_cached` as a real positional arg — never the leading-underscore escape.
**When to use:** Every cached MC + optimizer call in v3.
**Why it's the gate:** see §STG-04 below for the full mechanism, the existing-test breakage, and the exact insertion point.

### Pattern 3: Mirror the odds seam byte-for-byte for results (RES-01/04)
**What:** `scripts/fetch_results.py` writes a versioned read-only `data/results_cache.json`; `ui/results_loader.py` reads it JSON-only; the app folds `_meta.fetched_at` into the cache key. This is a structural TWIN of the shipped odds seam, not a new design.
**When to use:** All results ingest.
**Example (the loader — copy `ui/odds_loader.py` verbatim, swap the path + schema):**
```python
# ui/results_loader.py — [NEW]. Source pattern: ui/odds_loader.py:35-52 (read VERBATIM this session).
_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "results_cache.json"
_SUPPORTED_VERSION = 1

def load_results_cache(path: str | Path | None = None) -> dict | None:
    """Read data/results_cache.json read-only; None on ANY error (missing/malformed/wrong version).
    NEVER raises into the UI. No httpx / dotenv / provider import (the app import path stays clean)."""
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

### Anti-Patterns to Avoid
- **Editing `load_teams`/`_DEFAULT_FIXTURE`/`_validate_fixture` to add stages:** breaks the freeze and risks GATE-01. Use a NEW `load_stage` wrapper. [CITED: ARCHITECTURE.md Anti-Pattern, PITFALLS.md Pitfall 4 debt row]
- **Leaving `stage_id` out of the cache key "for now":** the exact same stale-serve class as the original `_locked` underscore escape the project already burned itself on. [CITED: PITFALLS.md Pitfall 4]
- **`stage_id` as a leading-underscore `_arg`:** silences `UnhashableParamError` but EXCLUDES it from the key — re-creates the cross-stage stale-serve bug. Must be a real positional arg. [VERIFIED: `ui/cache.py:1-13` docstring describes this exact trap for `locked`.]
- **`load_teams()` hardcoded to `stage1.json` inside `run_mc_cached`:** today `run_mc_cached` calls `teams = load_teams()` (always Stage 1). In v3 it must load the RIGHT fixture for `stage_id`. [VERIFIED: `ui/cache.py:64`.]
- **Name-match the results join (`name == name`):** mis-attributes a result to the wrong team → a fabricated lock → corrupted re-sim and (Phase 7) corrupted seeding. Use slug-first via `team_aliases.json`, drop on unresolved. [CITED: PITFALLS.md Pitfall 5]
- **Auto-fetch silently overwriting a manual lock:** the user's manual lock is authoritative ground truth. A conflicting fetch requires explicit confirm. [CITED: PITFALLS.md Pitfall 5b]
- **httpx anywhere in the app import path:** `test_app_makes_no_network_on_rerun` booby-traps httpx and asserts the render path never touches it. `fetch_results.py` must lazy-import httpx inside `fetch()` only, and the app must import only `ui/results_loader.py`. [VERIFIED: `tests/test_app.py:952-971`.]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Read-only fetched-cache loader | A new bespoke results reader | Copy `ui/odds_loader.py` structure verbatim (path + version gate + fail-soft None) | The exact fail-soft contract (missing/malformed/wrong-version → None, never raise) is already proven + tested. [VERIFIED: `ui/odds_loader.py`] |
| Provider team-name → engine id | A second name resolver | `odds/_match.resolve_id` / `build_name_to_id` (already importable, engine-free) | One resolver, one trust boundary; slug-alias is an additive upgrade on top. [VERIFIED: `odds/_match.py`] |
| FINISHED-series fetch + write | A new fetch harness | Copy `scripts/fetch_odds.py` (`load_dotenv_safe`, per-provider try/except fail-soft, httpx-logger-to-WARNING, ISO `_meta.fetched_at`, atomic write) | The whole fail-soft fetch discipline (no key → skip provider, no market → empty valid cache, key never logged) is already built. [VERIFIED: `scripts/fetch_odds.py`] |
| Pre-fill `locked` from results | A new lock-injection path | `engine.live.locked_dict_from_results` + `ui.state.add_lock` + the existing `KEY_LOCKED` flow | The `(round, winner, loser)` lock list is the existing Phase-4 contract; fetch just appends to it. [VERIFIED: `engine/live.py:47-58`, `ui/state.py:62, 191-202`] |
| Reject an illegal fetched lock | A new validator | `engine.live.validate_lock` (rematch/terminated/non-pairing/double-book reasons) | Auto-derived locks flow through the SAME validator — no bypass — so the engine invariants still hold. [VERIFIED: `engine/live.py:82-148`] |
| "Stage N complete?" guard before any auto-derive | A new completeness check | `engine.live.LivePrefixIncomplete` precondition (full-prefix replay) | Auto-derivation must fire only on a complete, validated stage final; this is the multi-stage analogue already implemented. [VERIFIED: `engine/live.py:209-217, 269-316`] |
| Fetched-cache staleness display | New staleness math | `ui.render.fmt_age` / `is_stale` / `provider_labels` (already pure + tested) | The odds panel already renders relative age + a stale warning from `_meta.fetched_at`. [VERIFIED: `ui/render.py:351-392`] |

**Key insight:** Phase 6 is almost entirely *copy-the-odds-seam + add-one-cache-key-arg + add-one-loader-wrapper*. The riskiest hand-rolled temptation is a second team resolver or a bypass around `validate_lock` — both re-open the fabricated-lock corruption that feeds the Phase-7 seeding chain.

## Runtime State Inventory

> Phase 6 introduces NEW per-stage fixtures and a NEW runtime cache. The following is the state inventory for the multi-stage generalization (it is a structural change, so a runtime-state pass applies even though it is not a rename).

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data (fixtures) | `data/stage1.json` EXISTS and is COMMITTED (not gitignored). New `data/stage2.json`/`stage3.json`/`playoffs.json`/`team_aliases.json` must be committed fixtures too. | Create + commit per-stage fixtures; seed `team_aliases.json` (slugs are an event-time `/browse` verify). |
| Live runtime cache | `data/results_cache.json` is a FETCHED ARTIFACT — must be gitignored exactly like `data/odds_cache.json` (which IS in `.gitignore`). Its ABSENCE is the normal first-run state. | Add `data/results_cache.json` to `.gitignore`. [VERIFIED: `.gitignore` lists `data/odds_cache.json`; `data/stage1.json` is NOT ignored.] |
| Session state | New session-state keys for the active stage + per-stage `seeds_confirmed` + pending-conflict state. The existing `KEY_MC_CACHE` dict is keyed on the run tuple — adding `stage_id` to that tuple changes every key shape. | Add stage keys to `ui/state.py`; ensure the in-session `mc_cache` dict keys now carry `stage_id` (the tuple grows by one leading element). |
| Secrets / env vars | Optional `PANDASCORE_KEY` (FALLBACK A). bo3.gg + Kalshi-derived are keyless. `.env` is gitignored; `.env.example` is committed and currently lists `ODDSPAPI_KEY`/`POLYMARKET`/`KALSHI`. | Add a commented `PANDASCORE_KEY=` line to `.env.example`. Missing key → skip PandaScore, fall through (fail-soft). [VERIFIED: `tests/test_app.py:456-473` asserts `.env.example` contents + `.env` gitignored.] |
| Build artifacts | None — no compiled artifacts, no package rename, no egg-info. | None. |

**Nothing found in category (build artifacts):** None — verified by inspecting the repo layout (`engine/`, `ui/`, `odds/`, `scripts/`, `data/` are plain `.py`/`.json`; no compiled/installed package state).

## Common Pitfalls

### Pitfall 1: Cache-key omits `stage_id` → switching stages serves another stage's cached numbers (STG-04 — THE GATE)
**What goes wrong:** Today the MC cache key is `(ratings_key, S, N, locked_key)` and the optimizer key is `(ratings_key, S, N, locked_key, fetched_at)` — **no stage id** — and `run_mc_cached` hardcodes `teams = load_teams()` (always `stage1.json`). Two stages that share `(ratings, S, N, locked={}, fetched_at)` — e.g. both at empty-locked pre-stage with default ratings — collide: Stage 2 serves Stage 1's cached Result, and/or the wrong fixture loads entirely. [VERIFIED: `ui/cache.py:47-65, 68-88`; `app.py:550-557`.]
**Why it happens:** v1.0 was single-stage, so stage identity was implicit. Adding stages without threading a stage id is the path of least resistance; the collision only manifests when two stages coincide on the other key fields — easy to miss in a one-stage demo.
**How to avoid:** Add `stage_id` as a REAL positional arg to BOTH `run_mc_cached` and `optimize_cached`, in the tuple. Make `run_mc_cached` load the RIGHT fixture for that `stage_id` (via `load_stage`), not always `stage1.json`. Thread `stage_id` through `_cache_key_for` in `app.py` and every call site (`_compute_or_serve`, the LIVE empty-locked `pre_key`, the optimizer memo).
**Warning signs:** Stage 2's per-team table looks identical to Stage 1's; switching stages doesn't trigger a re-sim spinner; team names in a stage's table don't match that stage's field. [CITED: PITFALLS.md Pitfall 4]

### Pitfall 2: The loader generalization perturbs the GATE-01 path (STG-01)
**What goes wrong:** Editing `load_teams`, `_DEFAULT_FIXTURE`, or `_validate_fixture` to support per-stage sizes changes a code path GATE-01 depends on. Note that `test_backtest_budapest_2025.py` builds its OWN `Team` objects directly (`Team(id=s, name=name, seed=s, rating=50.0)`) and imports `simulate_stage`/`build_round1_pairs`/`Team` — it does NOT call `load_teams`. [VERIFIED: `tests/test_backtest_budapest_2025.py:26-27, 56-60`.] BUT `test_live.py`, `test_app.py`, `conftest.py`, and the shipped app all call `load_teams()` and assume Stage-1's 16 teams. A change to the loader's default behavior breaks those.
**Why it happens:** "Just parameterize the existing loader" is tempting and looks harmless.
**How to avoid:** A NEW `load_stage(path)` wrapper + a NEW `_validate_fixture_for_size(rows, size)` sibling. Leave `load_teams`/`_DEFAULT_FIXTURE`/`_validate_fixture` byte-identical. Add a freeze-regression test (see Validation Architecture) asserting GATE-01 stays green AND `load_teams()` still returns the identical 16-team Stage-1 list.
**Warning signs:** GATE-01 red; `test_zero_config_first_run` red; the Stage-1 default fixture loads a different team set. [CITED: PITFALLS.md Pitfall 4 debt row, ARCHITECTURE.md frozen-boundary table]

### Pitfall 3: Live-results join is fragile, overwrites a manual lock, or an outage gates/crashes (RES-03/04/05)
**What goes wrong:** Three sub-traps: (a) a `name == name` join mis-attributes a result (the API returns "MOUZ" vs "mousesports", "FaZe" vs "FaZe Clan", transliterations, mid-event renames) → a fabricated lock; (b) a fetched result silently overwrites a manual lock the user entered as ground truth; (c) an API outage / partial / in-progress round blocks the app or throws.
**Why it happens:** Esports result data is messy; name normalization is an afterthought; "auto-ingest" tempts a design where the fetch is authoritative — but in THIS app the user's manual lock is authoritative.
**How to avoid:** (a) slug-first id mapping via `data/team_aliases.json` + `resolve_id` fallback; on an unresolved team, FAIL SOFT (banner "couldn't map team X, enter manually"), never guess. (b) A fetched result that conflicts with an existing manual lock requires explicit confirm (diff shown), never a silent replace; an un-locked match can pre-fill, still subject to `validate_lock`. (c) Read-only `results_cache.json` + fail-soft: outage/partial → banner + manual entry stays usable; the app never gates or crashes; first run needs no results API. Every auto-derived lock flows through the EXISTING `locked_dict_from_results` → `validate_lock` path (no bypass).
**Warning signs:** A team you didn't expect appears as a locked winner; the spinner hangs when offline; a manual lock changed after a fetch; re-sim numbers jump without you locking anything. [CITED: PITFALLS.md Pitfall 5]

### Pitfall 4: A second read-only cache that the app accidentally fetches on rerun
**What goes wrong:** If `ui/results_loader.py` (or anything it imports) pulls in `httpx`/`scripts.fetch_results`, the zero-config first run breaks and the app makes network calls on rerun.
**Why it happens:** Convenience imports.
**How to avoid:** `ui/results_loader.py` imports ONLY `json`/`pathlib` (mirror `ui/odds_loader.py`'s explicit "no httpx/dotenv/provider/engine import"). The fetch button lazy-imports `scripts.fetch_results` INSIDE the click branch only (mirror `app.py:308`'s `from scripts.fetch_odds import main`). `test_app_makes_no_network_on_rerun` is the regression guard. [VERIFIED: `ui/odds_loader.py:1-19`, `app.py:288-330`, `tests/test_app.py:952-971`.]

## Code Examples

### STG-04: the exact current signatures + what Streamlit hashes + the insertion point
```python
# ui/cache.py — CURRENT (read VERBATIM 2026-06-04). The @st.cache_data hashes EACH positional arg
# to build the key. locked_key is a REAL positional (NOT underscore-escaped) — that is the proven
# correctness pattern. _result carries a leading underscore so it is EXCLUDED (correct HERE only,
# because the Result is a pure function of the rest of the key).

@st.cache_data(show_spinner=False)
def run_mc_cached(ratings_key: tuple, S: float, N: int, locked_key: tuple) -> Result:
    ratings = dict(ratings_key)
    locked = {frozenset(pair): winner for pair, winner in locked_key}
    teams = load_teams()                       # ← v3 BUG: always Stage 1. Must load load_stage(stage_id).
    return run_mc(teams, ratings, S, N, locked=locked, seed=FIXED_SEED)

@st.cache_data(show_spinner=False)
def optimize_cached(_result: Result, ratings_key: tuple, S: float, N: int,
                    locked_key: tuple, fetched_at=None) -> OptimizerOutput:
    return optimize(_result, load_teams())     # ← v3 BUG: always Stage 1.

# ── v3 TARGET (STG-04) — stage_id a REAL positional in BOTH keys ──────────────────────────
@st.cache_data(show_spinner=False)
def run_mc_cached(stage_id: str, ratings_key: tuple, S: float, N: int, locked_key: tuple) -> Result:
    teams, _cfg = load_stage(_path_for_stage(stage_id))   # load the RIGHT fixture
    ratings = dict(ratings_key)
    locked = {frozenset(pair): winner for pair, winner in locked_key}
    return run_mc(teams, ratings, S, N, locked=locked, seed=FIXED_SEED)

@st.cache_data(show_spinner=False)
def optimize_cached(_result: Result, stage_id: str, ratings_key: tuple, S: float, N: int,
                    locked_key: tuple, fetched_at=None) -> OptimizerOutput:
    teams, _cfg = load_stage(_path_for_stage(stage_id))
    return optimize(_result, teams)
```
**Insertion-point decision:** Put `stage_id` FIRST (leading positional), or keep it adjacent to the other key fields — either works for `@st.cache_data` (all positionals hash into the key). Leading-first is the clearest signal that it scopes everything. Whatever position is chosen, `app.py:_cache_key_for` must build the tuple in the SAME order, because `optimize_cached(result, *cache_key)` splats the app's `cache_key` tuple positionally. [VERIFIED: `app.py:820` `optimize_cached(result, *cache_key)`; `app.py:550-557` `_cache_key_for`.]

```python
# app.py — CURRENT _cache_key_for (app.py:550-557). The optimizer splats this tuple after _result,
# so its element ORDER must match optimize_cached's params AFTER _result.
def _cache_key_for(ratings, locked, fetched_at=None):
    return (freeze_ratings(ratings), S, int(N), freeze_locked(locked), fetched_at)
# ── v3 TARGET ──
def _cache_key_for(ratings, locked, stage_id, fetched_at=None):
    return (stage_id, freeze_ratings(ratings), S, int(N), freeze_locked(locked), fetched_at)
#   and optimize_cached(_result, stage_id, ratings_key, S, N, locked_key, fetched_at) matches this order.
```

**Existing tests that BREAK on this change (planner MUST update them — they call the wrappers positionally):**
- `tests/test_ui_helpers.py::test_run_mc_cached_uses_frozen_seed_and_default_chunks` — calls `run_mc_cached(rk, 40.0, 2000, lk)` (4 args). [VERIFIED: lines 381-401.]
- `tests/test_app.py::test_locked_in_cache_key` — calls `run_mc_cached(rk, 40.0, 2000, lk_empty)` and `run_mc_cached(rk, 40.0, 2000, lk_locked)`. [VERIFIED: lines 114-127.]
- `tests/test_app.py` LIVE tests assert on `k[3]` / `k[3] != ()` to find the locked_key position in `mc_cache` keys (e.g. `test_live_lock_changes_cache_key:541`, `test_live_lock_moves_p_advance:552`, `test_live_delta_anchor_uses_pre_key:684`). **Adding `stage_id` as the LEADING element shifts locked_key from index 3 to index 4** — these `k[3]` assertions must become `k[4]` (or the planner inserts `stage_id` AFTER locked_key to keep indices stable — but leading-first is cleaner and the index updates are mechanical). [VERIFIED: `tests/test_app.py:541, 552-561, 684-698`.]

### RES-01: provider API shapes (event-time verify aware)
```text
PRIMARY — bo3.gg public JSON API  [CITED: .planning/research/STACK.md; MEDIUM-HIGH — undocumented endpoint]
  GET https://api.bo3.gg/api/v1/matches
  Auth: NONE (keyless). Send browser-like headers — load-bearing, a generic UA may be refused:
        origin: https://bo3.gg   referer: https://bo3.gg/   user-agent: <a real browser UA>
  Finished-series query (JSON:API filter syntax):
        ?scope=widget-matches&page[offset]=0&page[limit]=100&sort=-start_date
        &filter[matches.status][in]=finished
        &filter[matches.discipline_id][eq]=1            # 1 = CS2
        &with=teams,tournament,games
  Cologne scope: filter[matches.tournament_id][eq]=<id once known>, OR post-filter the `tournament`
        include by slug/name client-side (mirror the substring-tournament filter odds/kalshi.py uses).
  Shape (finished match): array of match objects; each has status:"finished", a winner/winner_team_id,
        two `teams` (each id/name/slug/acronym), per-series score, a `tournament` include (id/name/slug).
  FINISHED-only: filter[matches.status][in]=finished — final series outcomes only (no live map ticks).

FALLBACK A — PandaScore free "Fixtures" tier  [CITED: .planning/research/STACK.md; MEDIUM-HIGH]
  GET https://api.pandascore.co/csgo/matches      (CS2 uses the legacy /csgo/ prefix)
  Auth: one key — Authorization: Bearer <PANDASCORE_KEY>  (or ?token=). Free Fixtures plan = 1000 req/hr,
        includes schedules+results. Free/stats plans are "non-betting use only" — this personal
        Pick'Em-EV tool qualifies; note it in the requirement.
  Finished query: ?filter[status]=finished&filter[...serie/tournament/league...]=<cologne>&sort=-end_at&per_page=100
  Shape: documented match: id, status:"finished", winner_id, winner{}, opponents[]→{opponent:{id,name,acronym,slug}},
         results[]→{team_id,score}, serie/tournament/league for scoping.

FALLBACK B — Kalshi-derived (ALREADY WIRED)  [CITED: .planning/research/STACK.md]
  Zero new fetch code: odds/kalshi.py::fetch already pulls KXCS2GAME markets. A settled market has
  result ("yes"/"no") + status:"settled"; the winner is the YES team of the settled market, already
  mapped to engine ids by odds/_match.resolve_id. DEGRADED only: settles 1–12 h after the match ends.

[VERIFY AT EVENT TIME — gstack /browse, DEFERRED]:
  - Confirm the Cologne tournament id/slug on bo3.gg + PandaScore once Stage-1 fixtures post.
    The fetcher MUST filter by tournament dynamically (substring/slug), never hardcode a match id.
  - Seed data/team_aliases.json with the 16 Stage-1 (then Stage-2/3) provider slugs at the same pass.
    This is the load-bearing calibration step — a mis-join silently corrupts the locked set + seeding chain.
  Markets/fixtures are not posted until ~event time; do NOT block this phase on it.
```

### Frozen results-cache schema (design once, like the odds cache)
```json
{
  "_meta": {"fetched_at": "<iso-utc>", "version": 1, "source": "bo3gg|pandascore|kalshi", "stage": 1},
  "results": [
    {"match": [9, 1], "winner": 1, "round_idx": 0, "bo": 1, "status": "finished",
     "provider_slugs": ["gamerlegion", "nrg"]}
  ]
}
```
- `match` is the SORTED `[lo, hi]` engine-id tuple — identical orientation to `OddsQuote.match`, so the downstream re-sim seam is unchanged. `winner` is the engine id. `round_idx` is 0-based (R1 == 0), matching `KEY_LOCKED`'s `(round_idx, winner_id, loser_id)` shape.
- The app folds `_meta.fetched_at` into the `@st.cache_data` key (the same `T-05-STALEBAND` discipline the odds cache uses) so a fresh fetch invalidates the memoized re-sim. [CITED: .planning/research/STACK.md schema; ARCHITECTURE.md §5; cross-checked against `data/odds_cache.json` + `scripts/fetch_odds.py:174-183`.]
- **Note (schema variant):** ARCHITECTURE.md proposes `{stage, round_idx, winner_id, loser_id}` per row; STACK.md proposes `{match:[lo,hi], winner, bo, status, provider_slugs}`. They are equivalent — the planner should pick ONE and freeze it (recommend the STACK.md `match`/`winner` shape since it matches the existing `OddsQuote.match` orientation and the `freeze_locked` round-trip). Carry `round_idx` either way (the lock list needs it).

### `data/team_aliases.json` — the slug-first join map
```json
{
  "_comment": "provider slug -> internal Team name (or engine id). Seeded at the event-time /browse verify.",
  "natus-vincere": "NaVi",
  "the-mongolz": "The MongolZ",
  "gamerlegion": "GamerLegion"
}
```
**Existing convention to reuse:** the Budapest fixture already carries a `team_aliases` map of `{internal_name -> provider_short}` (e.g. `"FlyQuest": "FLY"`, `"PARIVISION": "PV"`). [VERIFIED: `tests/fixtures/budapest_2025_stage1.json:38-55`.] For results, invert/extend it to `{provider_slug -> engine_id}` (or `-> internal_name` then `resolve_id`). The join is **slug-first** (exact alias hit), then `odds/_match.resolve_id` name-substring fallback, then DROP + log on no match (never guess). [CITED: .planning/research/STACK.md "team-name → engine-id join"; `odds/_match.py:25-38`.]

### RES-02: pre-fill `locked` from fetched results (reuse the Phase-4 contract)
```python
# Conceptual flow (app.py wiring — NO engine change). Sources: engine/live.py, ui/state.py.
results = load_results_cache()                          # ui/results_loader.py (read-only)
if results:
    for row in results["results"]:                     # current stage only
        lo, hi = row["match"]; w = row["winner"]; ell = lo if w == hi else hi
        pending = (row["round_idx"], w, ell)
        # 1) legal-prefix guard (reuse LivePrefixIncomplete via legal_pairings_for_round)
        # 2) conflict check vs an existing MANUAL lock for the same pair → require confirm (RES-03)
        # 3) validate_lock(...) → reject illegal fetched locks with the existing reason strings
        # 4) on accept + no conflict → ui.state.add_lock(KEY_LOCKED, *pending)
# The non-empty KEY_LOCKED then flows UNCHANGED through locked_dict → freeze_locked → cache key → re-sim.
```
This reuses `engine.live.locked_dict_from_results`, `legal_pairings_for_round`/`LivePrefixIncomplete`, `validate_lock`, and `ui.state.add_lock` — all already shipped + tested. [VERIFIED: `engine/live.py:47-58, 82-148, 269-316`; `ui/state.py:191-202`; `app.py:689-711` `_commit_lock`.]

### STG-05: per-stage [INFERRED]-seed banner (extend the existing mechanism)
```python
# CURRENT (ui/state.py:126-139 + app.py:158-195): read_seeds_confirmed() reads data/stage1.json's
# top-level "seeds_confirmed" flag read-only (fail-safe to False); KEY_SEEDS_CONFIRMED drives the
# st.warning banner + the dismiss toggle; the trust badge reads the same flag.
# v3: parameterize by the active stage's fixture path + a per-stage session key.
def read_seeds_confirmed(path=None) -> bool: ...        # already takes a path arg — pass the stage fixture
KEY_SEEDS_CONFIRMED_FOR = lambda stage_id: f"seeds_confirmed_{stage_id}"   # per-stage session key
# Each stage's fixture carries its own "seeds_confirmed" (stage1.json ships true; stage2/3 ship false).
# The banner persists per-stage until that stage's seeds are positively confirmed.
```
[VERIFIED: `ui/state.py:126-139` `read_seeds_confirmed(path=...)` already accepts a path; `data/stage1.json:8` `"seeds_confirmed": true`; `app.py:158-195` banner + toggle; `tests/test_app.py:334-348` reads the flag.]

## State of the Art

| Old (v1.0) Approach | Current (v3) Approach | When Changed | Impact |
|---------------------|----------------------|--------------|--------|
| Single stage; `load_teams()` always loads `stage1.json` | `load_stage(path)` wrapper + per-stage fixtures; selector picks the path | Phase 6 | Multi-stage without touching the frozen loader |
| Cache key `(ratings, S, N, locked[, fetched_at])` | `(stage_id, ratings, S, N, locked, fetched_at)` | Phase 6 (STG-04) | No cross-stage stale serves |
| Odds seam only (`odds_cache.json`) | Twin results seam (`results_cache.json`) for FINISHED series | Phase 6 (RES-01) | Auto-pre-fill `locked`; the input the Phase-7 seeding chain consumes |
| Manual lock entry only | Auto-ingest pre-fills + manual stays the fallback | Phase 6 (RES-02) | Faster live use; manual lock remains authoritative |

**Deprecated/excluded:** Liquipedia LPDB + GRID Series Events as results sources (ToS / paid); Polymarket-derived results (CS2 = novelty futures only, no per-match Cologne markets); any scraping. [CITED: REQUIREMENTS.md Out of Scope; .planning/research/STACK.md]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The Cologne tournament slug/id on bo3.gg + PandaScore (and the per-team provider slugs for `team_aliases.json`) | RES-01, team_aliases.json | A wrong slug silently corrupts the `locked` set + the Phase-7 seeding chain — the load-bearing calibration. MITIGATION: held `[VERIFY AT EVENT TIME]`; the fetcher filters by tournament dynamically; `team_aliases.json` is editable; an unresolved team fails soft (drop + banner), never a fabricated lock. Markets not posted until ~event time. |
| A2 | bo3.gg endpoint shape (path, filter params, includes, browser-header requirement) | RES-01 | Endpoint is undocumented/unofficial → shape can shift. MITIGATION: defensive parsing (drop unparseable rows, never raise) + PandaScore (documented) as FALLBACK A. [CITED: .planning/research/STACK.md, MEDIUM-HIGH — extracted from a live community wrapper.] |
| A3 | PandaScore free Fixtures tier includes finished results at 1000 req/hr and a personal Pick'Em-EV tool satisfies the "non-betting use only" clause | RES-01 fallback | If the free tier excludes results or the use clause is read strictly, FALLBACK A is unavailable. MITIGATION: bo3.gg is primary + keyless; Kalshi-derived is FALLBACK B. [CITED: .planning/research/STACK.md, MEDIUM-HIGH.] |
| A4 | The Stage-2/3 per-stage fixtures are 16-team and `playoffs.json` is 8-team | STG-01 | A wrong size would trip the size-parameterized validator (loud fail, not silent). LOW risk — verified vs the Wikipedia/MEMORY format (3 Swiss stages of 16 + 8-team playoff). [CITED: REQUIREMENTS.md format block, MEMORY cologne-2026-full-format.] |
| A5 | Stage-2/3 fixtures ship `seeds_confirmed:false` + `[INFERRED]` qualifier placeholders (real seeds derive in Phase 7) | STG-05 | If shipped `true`, the per-stage banner wouldn't show. LOW risk — the seeding chain (Phase 7) is what fills real qualifier seeds; pre-results state is `[INFERRED]` by design. [CITED: ARCHITECTURE.md component table.] |

## Open Questions

1. **`stage_id` insertion position in the cache tuple (leading vs trailing).**
   - What we know: `@st.cache_data` hashes all positionals; `app.py` splats `cache_key` into `optimize_cached(result, *cache_key)`, so the tuple order must match the params after `_result`. Several `test_app.py` LIVE tests index `k[3]` for the locked_key.
   - What's unclear: whether to insert `stage_id` leading (clearer scoping, shifts `k[3]`→`k[4]`) or trailing (keeps existing indices, less obvious).
   - Recommendation: insert LEADING (`stage_id` first) and update the `k[3]`→`k[4]` assertions — the index updates are mechanical and a leading scope arg is the honest signal. Document the chosen order in `_cache_key_for`'s docstring.

2. **Results-cache schema: STACK.md `{match,winner,bo,...}` vs ARCHITECTURE.md `{winner_id,loser_id,...}` row shape.**
   - What we know: both carry the same information; the lock list needs `round_idx`.
   - What's unclear: which to freeze.
   - Recommendation: freeze the STACK.md `match:[lo,hi]` + `winner` shape (matches `OddsQuote.match` orientation + `freeze_locked` round-trip) and add `round_idx`. Version it (`_meta.version:1`) like the odds cache so a future bump is a deliberate loader change.

3. **Does Phase 6 simulate Stage 2/3/Playoffs, or only stand up the scaffold for Stage 1?**
   - What we know: ROADMAP maps STG-02 (Stage 2 sim) to Phase 7, STG-03/BO-01 to Phase 8, playoffs to Phase 9. Phase 6's success criteria say the results seam "applies to Stage 1 NOW."
   - What's unclear: whether the Phase-6 stage selector should expose Stage 2/3/Playoffs as selectable-but-empty, or only Stage 1 with the plumbing ready.
   - Recommendation: build the selector + `load_stage` + `stage_id`-cache-key generally (so Stage 2/3 are *loadable*), but the thin first slice proves cross-stage isolation using the EXISTING Stage 1 (and a trivial second fixture/stub) — actual Stage-2 simulation + seeding is Phase 7. This matches the MVP slicing hint.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | everything | ✓ | 3.12.10 | — |
| uv (runner) | `uv run pytest` / `uv run streamlit` | ✓ | (project bootstrap) | — |
| pytest | the test suite | ✓ (via `uv run`) | 128 tests collected | — |
| httpx | `scripts/fetch_results.py` (lazy) | ✓ (already pinned, used by odds fetch) | >=0.28,<0.29 | — |
| bo3.gg API | RES-01 PRIMARY | ✗ (live network; Cologne markets not posted until ~event time) | — | PandaScore (A) / Kalshi-derived (B) / manual entry |
| PandaScore API | RES-01 FALLBACK A | ✗ (needs a free `PANDASCORE_KEY`; results not posted yet) | — | bo3.gg / Kalshi-derived / manual entry |
| PANDASCORE_KEY env var | PandaScore fallback only | ✗ (user must create a free account; optional) | — | bo3.gg keyless primary; missing key → skip provider |

**Missing dependencies with no fallback:** None that block the phase — the seam is built fail-soft. A missing results source degrades to manual entry (already fully functional for Stage 1).

**Missing dependencies with fallback:** The live provider APIs + `PANDASCORE_KEY` are all event-time/optional. The phase builds the seam + tests it against RECORDED fixtures (the exact pattern the odds providers use: `get_quotes(recorded_fixture)` parses with no httpx); the live `/browse` slug confirm + `team_aliases.json` seeding is the DEFERRED event-time verify. [VERIFIED: `odds/kalshi.py:72-94` / `odds/oddspapi.py:76-94` `get_quotes` parse recorded fixtures with no network — mirror this for results provider parsers.]

## Validation Architecture

> `workflow.nyquist_validation: true` in `.planning/config.json` — this section is REQUIRED. The downstream workflow creates VALIDATION.md from it.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (+ `streamlit.testing.v1.AppTest` for UI; ships inside streamlit, no extra dep) |
| Config file | none — invoked via `uv run pytest`; `tests/conftest.py` provides shared fixtures |
| Quick run command | `uv run pytest tests/test_backtest_budapest_2025.py tests/test_ui_helpers.py -q` (the gate + the cache-key units, ~1 s) |
| Full suite command | `uv run pytest -q` (128 tests baseline, all green 2026-06-04) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STG-04 | Same `(ratings,S,N,locked)` under two different `stage_id`s → DIFFERENT cached Results; same `stage_id` → cache HIT (same object) | unit | `uv run pytest tests/test_ui_helpers.py::test_stage_id_in_cache_key -x` | ❌ Wave 0 |
| STG-04 | Switching the active stage in the UI never shows the prior stage's probs; a stage switch creates a new `mc_cache` key carrying `stage_id` | AppTest | `uv run pytest tests/test_app.py::test_stage_switch_isolates_cache -x` | ❌ Wave 0 |
| STG-01 | `load_stage(path)` validates against the JSON's `stage.size`, returns `(teams, cfg)`; rejects a dup/short seed set loudly | unit | `uv run pytest tests/test_teams_load_stage.py -x` | ❌ Wave 0 |
| STG-01 / GATE-01 | FREEZE REGRESSION: GATE-01 stays green AND `load_teams()` returns the byte-identical 16-team Stage-1 list after the loader generalization | unit | `uv run pytest tests/test_backtest_budapest_2025.py tests/test_teams_load_stage.py::test_load_teams_unchanged -x` | ⚠️ GATE-01 EXISTS (green); freeze-companion ❌ Wave 0 |
| STG-05 | Per-stage `[INFERRED]`-seed banner persists per stage until that stage's `seeds_confirmed` is positively flipped; reads the stage fixture read-only | AppTest + unit | `uv run pytest tests/test_app.py::test_per_stage_seed_banner -x` | ❌ Wave 0 |
| RES-04 | `load_results_cache` returns None on missing/malformed/non-dict/wrong-version; a valid v1 cache round-trips (fail-soft, never raises) | unit | `uv run pytest tests/test_results_loader.py::test_results_cache_failsoft -x` | ❌ Wave 0 |
| RES-04 | App renders + runs with NO results cache and NO key (manual entry works day one); no crash | AppTest | `uv run pytest tests/test_app.py::test_no_results_failsoft -x` | ❌ Wave 0 |
| RES-04 | App makes NO network call on rerun (httpx booby-trapped) with the results seam wired | AppTest | `uv run pytest tests/test_app.py::test_no_network_on_rerun_with_results -x` | ⚠️ analogue EXISTS (`test_app_makes_no_network_on_rerun`); extend ❌ |
| RES-01 | A recorded bo3.gg / PandaScore FINISHED fixture parses to `(match,winner,round_idx)` rows; an unparseable row is dropped, never raises | unit | `uv run pytest tests/test_results_fetch.py::test_finished_fixture_parses -x` | ❌ Wave 0 |
| RES-05 | Slug-first join via `team_aliases.json` resolves a provider slug to the right engine id; an unresolved team is DROPPED + surfaced, never mis-locked | unit | `uv run pytest tests/test_results_fetch.py::test_unresolved_team_fails_soft -x` | ❌ Wave 0 |
| RES-02 | Fetched FINISHED results pre-fill `KEY_LOCKED`; the derived non-empty `locked_key` changes the cache key → conditional re-sim fires; an illegal fetched lock is rejected with the existing `validate_lock` reason string | AppTest | `uv run pytest tests/test_app.py::test_fetched_results_prefill_locked -x` | ❌ Wave 0 |
| RES-03 | A fetched result that conflicts with a MANUAL lock requires explicit confirm (loud), never silently overwrites; provenance + `_meta.fetched_at` surfaced | AppTest | `uv run pytest tests/test_app.py::test_fetch_conflict_requires_confirm -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_backtest_budapest_2025.py <the task's new test file> -q` (GATE-01 + the slice under test).
- **Per wave merge:** `uv run pytest -q` (full 128 + new tests; GATE-01 green is mandatory).
- **Phase gate:** Full suite green + GATE-01 green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/test_teams_load_stage.py` — covers STG-01 (`load_stage` validate/return) + the `test_load_teams_unchanged` freeze companion.
- [ ] `tests/test_results_loader.py` — covers RES-04 loader fail-soft (mirror `test_cache_loader_failsoft` in `test_app.py`).
- [ ] `tests/test_results_fetch.py` — covers RES-01/RES-05 provider-fixture parse + slug join (mirror `tests/test_odds.py` recorded-fixture pattern).
- [ ] `tests/fixtures/bo3gg_finished_sample.json` + `tests/fixtures/pandascore_finished_sample.json` — recorded FINISHED-series fixtures (mirror `tests/fixtures/kalshi_sample.json`).
- [ ] New `data/stage2.json` (+ a minimal second fixture) so the cross-stage cache-isolation AppTest has a real second stage to switch to.
- [ ] New cases in `tests/test_ui_helpers.py` / `tests/test_app.py` for STG-04 (cache isolation) + the `k[3]`→`k[4]` index updates to the existing LIVE tests.
- [ ] Framework install: none — pytest + AppTest already present via `uv run`.

*(The existing GATE-01, `test_cache_loader_failsoft`, and `test_app_makes_no_network_on_rerun` are the proven templates; the new tests mirror them.)*

## Security Domain

> `security_enforcement` is not set to false — included. Phase 6 adds a network fetcher + reads provider JSON, so the input-validation + secret-handling surface matters.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Single local user; no auth surface. |
| V3 Session Management | no | Streamlit session state only; no cross-user sessions. |
| V4 Access Control | no | Local desktop tool. |
| V5 Input Validation | yes | Validate fetched results before they touch `locked`/seeds — mirror `_validate_fixture`'s loud-fail; drop unparseable provider rows (never raise); the slug join drops-on-unresolved (never guess a team). Per-stage fixtures pass `_validate_fixture_for_size`. |
| V6 Cryptography | no | No crypto; no secrets stored beyond an optional API key in `.env`. |
| V7 Error handling / logging | yes | `httpx`/`httpcore` loggers forced to WARNING so the `PANDASCORE_KEY` query param is NEVER logged (mirror `scripts/fetch_odds.py:135-136, 178-179`). Fail-soft per-provider try/except. |
| V9 Communications | partial | HTTPS only (httpx defaults; bo3.gg/PandaScore are https). |
| V12 Files / resources | yes | `results_cache.json` is a read-only artifact the app only reads; the fetcher writes it atomically (`mkdir(parents=True)` + `write_text`, mirror `fetch_odds.py:185-187`). Gitignored. |

### Known Threat Patterns for {Python · Streamlit · httpx · provider JSON}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key leaked via committed `.env` or request-URL logging | Information disclosure | `.env` gitignored (existing); `.env.example` committed; httpx logger → WARNING so `?token=`/`?apiKey=` never printed. [VERIFIED: `scripts/fetch_odds.py:132-136`; `tests/test_app.py:456-473`.] |
| Fetched JSON trusted as schema-valid → malformed fetch corrupts `locked`/seeds | Tampering | Validate before applying; drop unparseable rows; route every fetched lock through `validate_lock` (no bypass). [CITED: PITFALLS.md Security Mistakes.] |
| Mis-mapped team (name collision) → fabricated lock | Tampering | Slug-first join via `team_aliases.json`; reconcile against the stage's seed list; unresolved → drop + loud banner. [CITED: PITFALLS.md Pitfall 5a.] |
| Raw provider team name rendered in the UI → injection via a crafted name | Tampering/XSS | Escape at the UI boundary (existing `html.escape` discipline in `ui/render.py`; `validate_lock` reason strings are escaped at the app boundary). [VERIFIED: `ui/render.py` `_ballot_card_html`/`bracket_columns_html` escape names; `app.py:794` `html.escape`.] |
| httpx imported into the app render path → network on rerun | Denial of service / surprise calls | httpx lazy-imported inside `fetch()` only; the app imports only `ui/results_loader.py` (JSON+pathlib). Guarded by `test_app_makes_no_network_on_rerun`. [VERIFIED: `tests/test_app.py:952-971`.] |
| Auto-fetch overwrites a manual lock (ground truth) | Tampering / integrity | Conflict requires explicit confirm; never silent replace. [CITED: PITFALLS.md Pitfall 5b.] |

## MVP Slicing Hint

`Mode: mvp` — vertical slices (UI → logic → data, thin end-to-end). The dependency-forced order:

- **Slice 1 (the pivot — STG-01 + STG-04):** stage selector in `app.py` + `load_stage(path)` + `stage_id` threaded into BOTH cache wrappers and `_cache_key_for`, working end-to-end **for the existing Stage 1** (plus one minimal second fixture so the cross-stage isolation test has a real second stage). Gate: `test_stage_id_in_cache_key` (two stages → different Results; same stage → hit) + the GATE-01 freeze-regression companion. This MUST land first — every later stage relies on it. Ship the `k[3]`→`k[4]` test-index updates here. [CITED: ARCHITECTURE.md build-order A; PITFALLS.md Pitfall 4.]
- **Slice 2 (STG-05):** per-stage `[INFERRED]`-seed banner (parameterize the existing `read_seeds_confirmed`/`KEY_SEEDS_CONFIRMED` by the active stage). Small, rides on Slice 1's selector.
- **Slice 3 (RES-01/04 — the read-only seam):** `ui/results_loader.py` (loader-first, fail-soft, tested against a recorded fixture) + `scripts/fetch_results.py` (out-of-app httpx, FINISHED-only, slug-first join). Loader before fetcher (loader is pure + testable without network), mirroring how the odds seam shipped (`ui/odds_loader.py` GREEN before the AppTest wiring).
- **Slice 4 (RES-02/03/05 — wire into the app):** pre-fill `KEY_LOCKED` from fetched results through the existing `validate_lock`/`LivePrefixIncomplete` path; conflict-confirm UX; provenance + `fetched_at` display. Reuses Phase-4 contracts entirely.

Stage 1 is usable for live result-locking immediately (the user's stated priority); actual Stage-2 simulation + the seeding chain are Phase 7.

## Sources

### Primary (HIGH confidence — direct read of the shipped source, this session)
- `ui/cache.py` — exact `run_mc_cached`/`optimize_cached` signatures, the `_locked` underscore-escape trap, `load_teams()` hardcoding (STG-04 target).
- `engine/teams.py` — `load_teams`/`_DEFAULT_FIXTURE`/`_validate_fixture`/`STAGE_SIZE`/`build_round1_pairs` (STG-01 target; the frozen path).
- `engine/swiss.py`, `engine/montecarlo.py`, `engine/probs.py` — confirmed `simulate_stage`/`run_mc`/`difficulty` are stage-size-agnostic and consume `teams` + `locked` unchanged (no engine edit needed this phase).
- `engine/live.py` — `locked_dict_from_results`, `validate_lock`, `legal_pairings_for_round`, `LivePrefixIncomplete` (RES-02 reuse).
- `ui/odds_loader.py`, `scripts/fetch_odds.py`, `odds/base.py`, `odds/_match.py`, `odds/kalshi.py`, `odds/oddspapi.py`, `odds/polymarket.py` — the read-only-cache fail-soft + lazy-httpx + recorded-fixture-parse pattern the results seam mirrors byte-for-byte (RES-01/04/05).
- `app.py`, `ui/render.py`, `ui/state.py` — `_cache_key_for`/`_compute_or_serve`/`_run_or_serve`/`_live_anchor`, the fetch-button lazy-import, the `[INFERRED]`-seed banner + `read_seeds_confirmed`/`KEY_SEEDS_CONFIRMED`, `fmt_age`/`is_stale`/`provider_labels` (STG-05, RES-03/04 wiring).
- `data/stage1.json`, `data/odds_cache.json`, `tests/fixtures/budapest_2025_stage1.json` — fixture + cache + `team_aliases` schemas to match.
- `tests/test_backtest_budapest_2025.py` (GATE-01), `tests/test_app.py`, `tests/test_ui_helpers.py`, `tests/test_live.py`, `tests/conftest.py` — the test patterns + the exact existing assertions that break on the `stage_id` change.
- `.gitignore` — confirmed `data/odds_cache.json` ignored / `data/stage1.json` committed (so `results_cache.json` → gitignore, per-stage fixtures + `team_aliases.json` → committed).
- `uv run pytest` (2026-06-04): 128 tests collected; GATE-01 green (3 passed).

### Secondary (HIGH–MEDIUM — prior v3 research, 2026-06-02, grounded in the same source read)
- `.planning/research/STACK.md` — verified provider ladder (bo3.gg primary / PandaScore fallback / Kalshi backstop), API shapes, the `results_cache.json` schema, the `team_aliases.json` join design, zero-new-deps verdict.
- `.planning/research/ARCHITECTURE.md` — the frozen-boundary table, the odds-seam-mirror table, the `stage_id`-in-key call-out, the build order.
- `.planning/research/PITFALLS.md` — Pitfall 4 (cache-key stage id) + Pitfall 5 (results fail-soft/join/confirm) with code-line citations + the "Looks Done But Isn't" checklist.
- `.planning/ROADMAP.md` (Phase 6 section), `.planning/REQUIREMENTS.md` (STG/RES defs + Out of Scope), `.planning/STATE.md`, `CLAUDE.md` (non-negotiables).

### Tertiary (event-time verify — DEFERRED, gstack `/browse`)
- bo3.gg + PandaScore Cologne tournament slug/id confirmation + `team_aliases.json` seeding — markets/fixtures not posted until ~event time; documented above as `[VERIFY AT EVENT TIME]`, not a build blocker. [CITED: STACK.md sources — PandaScore pricing/limits/data-sample pages; bo3.gg community wrapper; Kalshi settlement FAQ.]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new deps; everything (httpx/numpy/dotenv/stdlib) already shipped + verified in v1.0.
- Architecture (load_stage wrapper, stage_id cache key, odds-seam mirror): HIGH — grounded in a direct read of every touched file + the GATE-01 backtest's actual imports; the cache-key indices and breaking tests are quoted from source.
- Pitfalls: HIGH — the two correctness gates (STG-04 cross-stage isolation, GATE-01 freeze) and the RES fail-soft/join/confirm traps are confirmed against the exact code lines that implement the analogous odds-seam guards.
- Provider API shapes (bo3.gg/PandaScore): MEDIUM-HIGH — verified in prior research against live docs + a community wrapper; bo3.gg is an undocumented endpoint, mitigated by defensive parsing + PandaScore fallback + the deferred event-time slug confirm.

**Research date:** 2026-06-04
**Valid until:** ~2026-06-18 (event-window; the provider-slug/`team_aliases` facts crystallize at event time. The source-grounded engine/cache/seam claims are stable until the codebase changes.)
