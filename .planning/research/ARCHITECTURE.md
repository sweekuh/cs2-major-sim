# Architecture Research

**Domain:** Single-process Streamlit analytics app — Monte Carlo Swiss-tournament simulator + Pick'Em optimizer with a decoupled multi-provider odds ensemble
**Researched:** 2026-05-28
**Confidence:** HIGH (validating an already eng-reviewed handoff spec; concerns below are architectural reasoning over that spec, not external claims)

> **Scope of this doc.** The handoff §1/§7 already proposes a repo layout and the PRD §7 names the layers. This research **validates** that layout and surfaces the integration/boundary concerns the PRD underweights. It does **not** redraw the same diagram. Sections are marked **[CONFIRMS]** (the handoff has it right — adopt as-is) or **[REFINES]** (the handoff is silent, ambiguous, or under-specifies a seam that will bite).

---

## Standard Architecture

### System Overview

The system is a **three-layer single-process app with one out-of-process satellite** (the odds fetch job). The load-bearing architectural idea is that the three layers form a strict one-directional dependency chain — `engine` depends on nothing, `odds` depends on `engine` math only, `app` depends on both — and the odds *fetch* is pushed out of the request path entirely so the Streamlit rerun loop never blocks on a network call.

```
┌──────────────────────────────────────────────────────────────────────┐
│  PRESENTATION  (app.py — Streamlit, rerun on every widget change)      │
│  ┌────────────┐  ┌─────────────┐  ┌────────────┐  ┌────────────────┐  │
│  │ rating     │  │ S / N       │  │ mode toggle│  │ result-lock    │  │
│  │ data_editor│  │ sliders     │  │ pre/live   │  │ widgets        │  │
│  └─────┬──────┘  └──────┬──────┘  └─────┬──────┘  └───────┬────────┘  │
│        └────────────────┴───────────────┴─────────────────┘           │
│                 builds cache key (ratings, S, N, locked)              │
├────────────────────────────────┼──────────────────────────────────────┤
│                       @st.cache_data boundary                          │
│         (the ONLY thing that decides "recompute vs serve cached")      │
├────────────────────────────────┼──────────────────────────────────────┤
│  DOMAIN / CORRECTNESS CORE  (engine/ — pure, no Streamlit, no network) │
│  ┌──────────┐   ┌──────────────────────────────┐   ┌───────────────┐  │
│  │ teams.py │──▶│ swiss.py  (pairing+stage sim) │◀──│ probs.py      │  │
│  │ fixtures │   │   ▲ locked-results injection   │   │ p_map, Bo3,   │  │
│  └──────────┘   └───────────┬──────────────────┘   │ de-vig, pool  │  │
│                  ┌──────────▼───────────┐           └──────┬────────┘  │
│                  │ montecarlo.py        │                  │           │
│                  │ epistemic outer loop │◀── blended p ────┘           │
│                  │ + aleatoric inner    │     + variance               │
│                  │ + per-chunk yield    │                              │
│                  └──────────┬───────────┘                              │
│                  ┌──────────▼───────────┐                              │
│                  │ optimizer.py         │  per-team probs + sim sample │
│                  │ Ballot A / Ballot B  │                              │
│                  └──────────────────────┘                              │
├────────────────────────────────┼──────────────────────────────────────┤
│  ODDS / DATA-ACQUISITION  (odds/ — depends on engine.probs only)       │
│  ┌──────────────┐ ┌─────────────┐ ┌────────────┐   reads/writes       │
│  │ OddsPapi     │ │ Polymarket  │ │ Kalshi     │──▶ pool() ──┐         │
│  │ (live anchor)│ │ (stub→live) │ │ (stub→live)│             │         │
│  └──────────────┘ └─────────────┘ └────────────┘             ▼         │
│                                              ┌──────────────────────┐  │
│                  ratings back-solve ◀────────│ data/odds_cache.json │  │
│                  (probs.py)                  └──────────▲───────────┘  │
└──────────────────────────────────────────────────────┼───────────────┘
                                                         │ WRITES ONLY
                              ┌──────────────────────────┴───────────────┐
                              │  SATELLITE: fetch job (cron / manual btn) │
                              │  out-of-process; holds API keys; the      │
                              │  ONLY thing that calls get_quotes()       │
                              └───────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Boundary rule (what it must NOT do) |
|-----------|----------------|--------------------------------------|
| `engine/teams.py` | Single source of truth for seeds → team map; derives R1 pairing | Must not hardcode a second copy of R1 pairings (handoff §3 DRY warning) |
| `engine/swiss.py` | Faithful Valve pairing + stage simulation; accepts `locked` dict | Must not import numpy randomness directly — RNG injected as a `seed`/`Generator` param for reproducibility |
| `engine/probs.py` | All probability math: `p_map`, Bo3 closed form, de-vig, `pool()` | Must not know about Streamlit, providers, or HTTP — pure functions |
| `engine/montecarlo.py` | Epistemic outer loop + aleatoric inner loop; yields per-chunk partial aggregates | Must not call `st.*` — emits progress via a generator/callback, UI owns the bar |
| `engine/optimizer.py` | Ballot A (greedy, E[correct]) + Ballot B (hill-climb, P(≥5)) against the stored sim sample | Must not re-run the MC — it consumes the *stored sample*, not a fresh sim |
| `odds/base.py` | `OddsProvider` Protocol + `pool()` + cache read/write contract | The `pool()` math lives in `probs.py`; `base.py` owns the *contract*, not the math |
| `odds/*.py` providers | `get_quotes(matches) -> [OddsQuote]` per source | Called ONLY by the fetch satellite, never on a Streamlit rerun |
| `app.py` | Widget IA, cache keying, progress rendering, two-mode layout | Must not call `get_quotes()`; reads `odds_cache.json` only |
| fetch satellite | Calls providers, writes `odds_cache.json` | Out-of-process; the app never imports it |

---

## Recommended Project Structure

**[CONFIRMS]** the handoff §1 layout is sound and should be adopted essentially verbatim. Three **[REFINES]** additions below resolve seams the layout leaves implicit.

```
swiss-mc/
├── app.py                    # Streamlit entry: widgets, cache keys, progress UI
├── engine/
│   ├── __init__.py
│   ├── teams.py              # fixtures: 16 teams, seeds, R1 derived, default ratings
│   ├── swiss.py              # pairing + stage simulation (correctness core)
│   ├── montecarlo.py         # MC runner: outer epistemic / inner aleatoric / yield
│   ├── optimizer.py          # Ballot A greedy + Ballot B hill-climb
│   └── probs.py              # p_map, Bo3, de-vig, pool(), ratings back-solve
├── odds/
│   ├── base.py               # OddsProvider Protocol + pool() + cache I/O contract
│   ├── cache.py              # [REFINES] read/write odds_cache.json — the seam (TODOS #1)
│   ├── oddspapi.py           # Pinnacle anchor (live)
│   ├── polymarket.py         # stub → live
│   └── kalshi.py             # stub → live
├── scripts/
│   └── fetch_odds.py         # [REFINES] standalone fetch satellite (manual now / cron later)
├── tests/
│   ├── test_swiss.py         # invariants + no-rematch + BACKTEST (the gate)
│   ├── test_probs.py         # [REFINES] difficulty/p_map/Bo3/devig/pool/roundtrip units
│   └── test_optimizer.py
├── data/
│   ├── stage1.json           # editable seeds/ratings snapshot (ships → zero-config run)
│   └── odds_cache.json       # [REFINES] written by fetch job, read by app (gitignored)
├── pyproject.toml            # uv-managed; Python >=3.12 pin (handoff §10.6)
├── .env.example              # optional provider keys; .env gitignored
└── README.md
```

### Structure Rationale

- **`engine/` has zero outward dependencies.** This is *the* architectural invariant. It is what makes the backtest gate possible: you can `__main__`-smoke-test and unit-test the entire correctness core with no Streamlit, no network, no odds. If anything in `engine/` ever imports `streamlit` or `requests`, the gate has been compromised and the build order has broken down.
- **`odds/cache.py` is split out from `base.py`** because the cache file is a *contract between two processes* (the app and the fetch satellite), not part of the provider interface. The handoff folds this into `base.py`; separating it makes the TODOS #1 seam explicit from v1 so v2's cron addition is a zero-app-change drop-in.
- **`scripts/fetch_odds.py` exists from v1**, even though it's wired to a manual "fetch now" button first. Per TODOS #1, the v1 button and the v2 cron must write the *same* cache the app reads. Putting the fetch logic in a standalone script (callable both from the button and from cron) means v2 adds a crontab line and nothing else.
- **`test_probs.py` is broken out** from `test_swiss.py` because the eng-review's CRITICAL `test_difficulty_formula`, `test_bo3`, `test_devig`, `test_pool`, `test_rating_roundtrip` guard the math layer, which is a distinct correctness surface from the pairing engine.

---

## Architectural Patterns

### Pattern 1: Pure-core / impure-shell (Functional Core, Imperative Shell)

**[CONFIRMS]** This is the spine of the whole design and the handoff already enforces it implicitly via the build order.

**What:** `engine/` is a pure, deterministic, dependency-free core. All I/O (network, Streamlit widgets, file reads) lives in the shell (`app.py`, `scripts/`, `odds/cache.py`). The MC takes a `seed` and returns the same answer every time.

**When to use:** Any system with a correctness-critical compute kernel that must be testable in isolation before a UI exists. This is exactly the backtest-gate situation.

**Trade-offs:** Slightly more plumbing (RNG and progress callbacks must be passed in, not reached for). Massive payoff: the gate becomes a plain `pytest` run with no UI harness, and Numba (TODOS #2) can later replace the core without touching the shell.

**Example:**
```python
# engine/montecarlo.py — pure, injectable RNG, progress via callback
def run_mc(stage, ratings, S, N, locked, *, seed, on_chunk=None):
    rng = np.random.default_rng(seed)
    # ... outer epistemic loop, inner aleatoric loop ...
    # on_chunk(done, total, partial_p_advance)  ← UI owns rendering
```

### Pattern 2: Nested-loop uncertainty (epistemic outer / aleatoric inner)

**[CONFIRMS]** This is the handoff §5's key correctness decision and a genuine architectural constraint, not just a math detail — it dictates the *shape* of the MC runner.

**What:** Two distinct sources of uncertainty must stay separate. The **outer loop** draws a probability vector `p ~ Beta(blend, variance)` once per epistemic draw (source disagreement — does NOT shrink with N). The **inner loop** runs an MC batch of Bernoulli coin-flips at that fixed `p` (aleatoric tournament variance — Wilson band shrinks with N). Final per-team probs aggregate **across** outer draws; the reported band is the spread across draws and is wider than the inner Wilson band.

**When to use:** Whenever you have parameter uncertainty layered on top of process uncertainty and must not let one masquerade as the other. Burying the Beta draw inside the per-sim loop folds epistemic into aleatoric and makes the Wilson band falsely tight at large N (defeats goal G4).

**Trade-offs:** Cost multiplies (outer_draws × inner_N). Mitigation: single source → outer loop collapses to one point estimate and you run only the inner loop. Clamp `variance < p(1-p)` before the Beta method-of-moments fit or params go negative and crash on exactly the low-liquidity matches that matter most (handoff §5).

```
for draw in epistemic_draws:                  # OUTER — epistemic
    p_vec ~ Beta(blend, clamp(variance))
    for sim in inner_batch:                    # INNER — aleatoric
        simulate_stage(p_vec, rng)             # Bernoulli coin-flips
    tally per-team records
aggregate across draws → point + epistemic band ⊇ Wilson band
```

### Pattern 3: Generator-yielding compute for progressive UI

**[CONFIRMS + REFINES]** The handoff §10.5 calls this an "eng×design cross-impact." It is the single most important shape decision in the runner, and it collides head-on with `@st.cache_data` — a collision the handoff names but does not resolve.

**What:** The MC runs in chunks (e.g. 20 × 5k) and emits a partial aggregate after each chunk so the UI can paint a progress bar + a settling P(advance) tally. The runner already stores per-sim records, so emitting a running aggregate per chunk is nearly free.

**The unresolved tension — and the refinement:** A generator that yields progress and a `@st.cache_data` function that returns one cached value are **incompatible** — you cannot cache a generator's intermediate yields, and a cached function returns instantly on a hit (no progress to show, which is correct) but streams on a miss (progress needed). Resolve it with a **two-function split**:

```python
# Pure, uncached, yields progress — used on a cache MISS to drive the bar.
def run_mc_progressive(...): -> Iterator[Partial]

# Cached final result — the key is (ratings, S, N, locked).
@st.cache_data
def run_mc_cached(ratings, S, N, locked, seed):
    last = None
    for partial in run_mc_progressive(...):   # drain the generator
        last = partial                         # (UI bar driven separately on miss)
    return last.final
```

On a cache hit the app serves instantly (no bar). On a miss the app drives the bar from `run_mc_progressive` and then stores the final via `run_mc_cached`. **Build order implication:** the MC must be written generator-first in slice 1, even though the progress bar is a slice-2 UI concern — retrofitting yield into a monolithic `run_mc` after the fact is a rewrite.

### Pattern 4: Provider adapter + cross-process cache seam

**[REFINES]** The handoff has the adapter pattern (`OddsProvider` Protocol). The PRD/TODOS adds the cache seam but the layout doesn't make it a first-class component. Make it one.

**What:** Providers normalize their wire format to `OddsQuote`. `pool()` blends to `{p, variance, n}`. The app **never** calls `get_quotes()` on a rerun — it reads `odds_cache.json`. The fetch satellite (button or cron) is the only `get_quotes()` caller.

**When to use:** Any time a UI rerun model (Streamlit reruns the whole script per widget change; Community Cloud sleeps between requests) would otherwise put a blocking network call in the hot path. This is the TODOS #1 decoupling.

**Trade-offs:** One extra moving part (the cache file contract). Worth it: app stays fast, keys live only in the fetch job's env, and auto-fetch (v2) needs no app rewrite.

---

## Data Flow

### Primary flow (pre-stage → ballot)

```
data/stage1.json (seeds + [INFERRED] ratings)
        │
        ▼
[ratings via st.data_editor] ──┐
[S slider] [N input] ──────────┤── cache key (ratings, S, N, locked={})
[odds_cache.json if present] ──┘
        │
        ▼  probs.py: blended p + variance  (or rating-only p_map if no cache)
        │
        ▼  montecarlo.py
   ┌────────────────────────────────────────┐
   │ OUTER: for each epistemic Beta draw     │  (collapses to 1 if single-source)
   │   INNER: N/chunks × Bernoulli stage sims│  ← yields partial P(advance) per chunk
   │   tally per-team (3-0 / advance / 0-3)  │
   └────────────────────────────────────────┘
        │
        ▼  per-team P(3-0), P(advance), P(0-3) + Wilson (inner) + epistemic (outer) bands
        │
        ├──▶ results table + inline CI mini-bars (UI)
        │
        ▼  optimizer.py (consumes per-team probs + the STORED sim sample)
   Ballot A (greedy E[correct])  +  Ballot B (hill-climb P(≥5) vs sample)
        │
        ▼  recommended ballot, P(≥5) headline, correlated-pick warning
```

### Conditional re-sim feedback loop (live mode)

This is the killer feature and the one true *loop* in the data flow — the only place output feeds back into input.

```
locked: dict[frozenset({id,id}) -> winner_id]   ← user locks a real round result
        │
        ▼  becomes part of the cache key (ratings, S, N, locked)
        │     → key changes → cache MISS → re-sim fires
        ▼
montecarlo.py: locked matchups use winner deterministically (no sampling);
               remaining games sampled conditioned on standings/Buchholz/rematch history
        │
        ▼  re-tally → updated per-team probs
        │
        ▼  per locked pick: classify live / dead / secured + P(≥5)-from-here DELTA
        │
        └──▶ UI shows the CHANGE (71% → 58%), not just a new static number
```

**Key insight for the roadmap:** `locked` is part of the cache key, so the entire re-sim feature rides on the cache-key design from slice 2. The re-sim slice (4) adds the *locking widgets and the live/dead/secured classification*, but the simulation machinery to honor `locked` must exist in `swiss.py` from slice 1 (handoff §4 already specifies the `locked` param). This means: **build `locked` support into the engine in slice 1, even though the UI for it lands in slice 4.** Skipping it in slice 1 forces a `swiss.py` rewrite later.

### Odds acquisition flow (decoupled, never in the rerun path)

```
[manual "fetch now" button]  OR  [cron on Ubuntu host]   ← both call the same script
        │
        ▼  scripts/fetch_odds.py
   OddsPapi.get_quotes() + Polymarket + Kalshi  → [OddsQuote, ...]
        │
        ▼  pool()  → {match: {p, variance, n}}
        │
        ▼  WRITE data/odds_cache.json
        ┊
        ┊  (the app, on its own schedule, READS the cache — never writes, never fetches)
        ▼
app.py: probs.py ratings back-solve  →  per-team ratings  →  feeds the MC
        live odds override imminent-round known matchups
```

---

## Build Order (dependency-driven)

The handoff §2 build order is **[CONFIRMS]** correct. The refinements below make three cross-slice dependencies explicit so they aren't discovered late.

| Slice | Builds | Hard dependency | Cross-slice seam to honor NOW |
|-------|--------|-----------------|-------------------------------|
| **1. Engine + MC (headless)** | `teams`, `probs`, `swiss`, `montecarlo`; `__main__` smoke test | none | **(a)** RNG injected (`seed` param), not reached for. **(b)** MC written generator-first (yields per chunk) — slice 2 needs it. **(c)** `swiss.py` accepts `locked` from day one — slice 4 needs it. |
| **🚧 BACKTEST GATE** | `test_swiss.py` reproduces a real past stage's pairings exactly (Budapest/Austin 2025) + the CRITICAL unit tests | slice 1 | **Nothing past this point is trusted or built until this passes.** This is the only check that proves greedy rematch resolution matches Valve's priority table. Not deferrable (TODOS #3). |
| **2. Streamlit UI** | `app.py`: data_editor, sliders, Run, results table, CI bars, two-mode IA | gate passed | Cache key `(ratings, S, N, locked)`. Two-function MC split (Pattern 3): uncached progressive driver + cached final. Trust badge tied to the passed gate. |
| **3. Optimizer** | `optimizer.py`: Ballot A + Ballot B + correlated-pick warning | slice 1 (consumes stored sim sample) | Optimizer reads the *stored sample*, not a fresh MC run — the MC must retain its per-sim record matrix for Ballot B's vectorized P(≥5) scoring. |
| **4. Result-lock / conditional re-sim + bracket** | locking widgets, live/dead/secured classification, record-bucket bracket view | slices 1+2 (`locked` engine support + cache key) | Engine `locked` support already exists (slice 1). This slice is mostly UI + classification. Bracket is record-bucket columns, NOT a tree. |
| **5. Odds layer** | `OddsPapiProvider` live, `pool()`, `scripts/fetch_odds.py`, ratings back-solve; Polymarket/Kalshi stubbed | slices 1–2 | **Fails soft**: missing key → rating-only mode + banner, never crash. Manual button writes the *same* `odds_cache.json` the app reads (TODOS #1 seam). |
| **v2: cron auto-fetch** | crontab line calling `scripts/fetch_odds.py` | slice 5 seam | Zero app change if slice 5 honored the cache seam. |
| **v3: Stages 2–3, playoffs, map-level Bo3** | extend engine for multi-stage + single-elim; optional Bo3 map sampling | full v1 stack + backtest | Playoffs are trivial single-elim by comparison. Map-level Bo3 only if backtest demands it. |

**Why this order is forced by dependencies (not preference):**
1. **The backtest gate is the pivot.** Everything downstream (UI, optimizer, re-sim, odds) consumes engine output. Building any of it before the engine is proven correct means building on numbers that "pass invariants while corrupting all probs" (the Buchholz `sum(o.wins)` trap). The gate must come first — it is a *blocker*, not validation.
2. **Optimizer before re-sim** because Ballot B's P(≥5) machinery (scoring against the stored sample) is reused by the live-mode P(≥5)-from-here delta. Building re-sim first would mean building that scoring twice.
3. **Odds last** because the engine runs fully on rating-only mode (zero-config first sim). Odds are an *enhancement that fails soft*, never a gate — so they can't block any earlier slice, and putting them last keeps the network/key/cache complexity out of the critical correctness path.

---

## Anti-Patterns

### Anti-Pattern 1: Calling `get_quotes()` on a Streamlit rerun

**What people do:** Wire the odds fetch directly into `app.py` so the app pulls live odds each run.
**Why it's wrong:** Streamlit reruns the whole script on every widget nudge — a blocking network call per rerun makes the UI molasses, leaks keys into the UI session, and Community Cloud sleeps between requests so a fetch loop can't live in the app anyway (TODOS #1).
**Do this instead:** The app reads `data/odds_cache.json` only. A standalone `scripts/fetch_odds.py` (button-triggered now, cron-triggered in v2) is the sole `get_quotes()` caller and the sole cache writer.

### Anti-Pattern 2: Beta draw inside the per-sim inner loop

**What people do:** Sample `p ~ Beta` once per match per simulation, inside the MC's hot loop.
**Why it's wrong:** Folds epistemic (source-disagreement) uncertainty into aleatoric (coin-flip) noise, so it averages away with N and the reported Wilson band looks falsely tight at large N — defeating goal G4 (honest calibration).
**Do this instead:** Beta draw in the OUTER loop, once per epistemic draw; run a full aleatoric MC batch at that fixed `p`; aggregate across draws (handoff §5, Pattern 2).

### Anti-Pattern 3: Monolithic (non-yielding) MC runner

**What people do:** Write `run_mc()` as one blocking call returning final probs, planning to "add progress later."
**Why it's wrong:** The §10.5 progress-bar + live-tally UX requires per-chunk partial aggregates. Retrofitting yield into a monolithic runner is a rewrite of the hottest code path. The eng×design cross-impact was flagged precisely so this isn't discovered in slice 2.
**Do this instead:** Write the runner generator-first in slice 1 (Pattern 3), with the two-function cache split.

### Anti-Pattern 4: Two copies of the seed→R1-pairing fact

**What people do:** Hardcode the R1 `(1,9),(2,10),...` table *and* the seed list as separate fixtures.
**Why it's wrong:** Two hand-maintained copies of the same fact drift the moment the official seeds land — and a wrong seed silently corrupts every probability (handoff §3 DRY warning).
**Do this instead:** Seed→team map is the single source of truth; derive R1 pairing as `[(i, i+8) for i in range(1,9)]`.

### Anti-Pattern 5: Drawing the Swiss bracket as a tree

**What people do:** Render a single-elimination-style bracket tree.
**Why it's wrong:** Swiss teams reconverge by record — a tree misrepresents the format and confuses every CS viewer who reads the standard HLTV/Liquipedia record-bucket layout.
**Do this instead:** Record-bucket columns (`0-0 → 1-0 → 2-1 → ... → 3-0 adv / 0-3 elim`); locked results solid, simulated branches faint (handoff §10.5).

### Anti-Pattern 6: Letting `engine/` import `streamlit` or `requests`

**What people do:** Reach for `st.progress` or an HTTP client from inside the core for convenience.
**Why it's wrong:** It breaks the functional-core invariant, makes the backtest ungate-able without a UI/network harness, and blocks the Numba refactor (TODOS #2).
**Do this instead:** Inject the RNG and a progress callback; keep all I/O in the shell.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes / gotchas |
|---------|---------------------|-----------------|
| OddsPapi (Pinnacle anchor) | REST, free tier, behind `OddsPapiProvider` | One call also returns Thunderpick/GG.BET/Betway; Pinnacle weighted highest (sharp). Filter CS2 `sportId` by tournament. |
| Polymarket | Public API behind `PolymarketProvider` (stub→live) | Price ≈ probability (`vig_type="market"`); downweight thin markets. |
| Kalshi | Official API behind `KalshiProvider` (stub→live) | CFTC; thin volume on niche games. Read-only public market data — no scraping. |
| Thunderpick | **No direct provider** — arrives via OddsPapi | Never scrape (geo-restricted, ToS-hostile). |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `app.py` ↔ `engine/` | Direct function call, wrapped in `@st.cache_data` | Cache key `(ratings, S, N, locked)` is the recompute decision; the MC is generator-first under the cache. |
| `app.py` ↔ `odds/` | **File only** (reads `odds_cache.json`) | App never calls providers. The cross-process seam (TODOS #1). |
| fetch satellite ↔ `odds/` | Direct `get_quotes()` + `pool()`, writes cache | Sole network caller; sole key holder; sole cache writer. |
| `odds/` ↔ `engine/probs.py` | Direct call to de-vig/pool/back-solve math | Math lives in `probs.py`; `odds/` owns the contract + I/O, not the math. |
| `optimizer.py` ↔ `montecarlo.py` | Consumes stored per-sim record sample | Ballot B vectorizes P(≥5) over the retained sample; optimizer never re-runs the MC. |

---

## Sources

- `files/HANDOFF_claude_code.md` §1 (repo layout), §2 (build order), §4 (engine), §5 (math), §8 (odds), §10.5 (UI/progress), §10.6 (DX/fail-soft) — eng/design/DX-reviewed executable spec (HIGH confidence; authoritative for this project)
- `files/PRD_cologne2026_pickem_simulator.md` §6 (data model), §7 (architecture/stack), §10 (risks)
- `.planning/PROJECT.md` Key Decisions table (epistemic outer loop, backtest gate, single seeding path)
- `TODOS.md` #1 (cron-fed odds cache seam), #2 (Numba refactor target), #3 (backtest-as-gate)

---
*Architecture research for: Streamlit Monte Carlo Swiss simulator + Pick'Em optimizer with decoupled odds ensemble*
*Researched: 2026-05-28*
