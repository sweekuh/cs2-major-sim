# Requirements: swiss-mc — v3 (Full-Major)

**Milestone:** v3 — Full-Major (live-results ingest + Stages 2 & 3 Swiss + playoff single-elimination bracket)
**Predecessor:** v1.0 — Cologne Stage-1 Swiss Pick'Em (✅ shipped 2026-05-30; 54/54 reqs; 113 tests; GATE-01 GREEN). v1.0 reqs archived in `.planning/milestones/v1.0-REQUIREMENTS.md`. Post-ship PRs #6–#9 landed live odds, two P0 fixes, and a public forecast page.

**Core Value:** Honestly-calibrated probabilities for the exact quantities Pick'Em scores on —
P(3-0)/P(advance)/P(0-3) per team and P(≥5/10) per ballot — including conditional re-sim, without
laundering guesses into false precision. v3 extends this from Stage 1 to the whole Major and adds
auto-ingest of live results so the re-sim and the inter-stage seeding update themselves.

> **Verified format (Wikipedia, 2026-06-02 — `[[cologne-2026-full-format]]`):** expanded 32-team Major.
> Stage 1 (16 VRS-invited, done) → Stage 2 (8 qualifiers + 8 invited) → Stage 3 (8 qualifiers + 8 invited,
> **all matches Bo3**) → Playoffs (8 teams single-elim, Bo3 QF/SF, **Bo5 grand final**). Each Swiss stage
> is a single 16-team bracket, top 8 advance. Qualifiers seed by their FINAL Buchholz; invited by VRS.

> **Engine boundary:** the entire v3 milestone makes exactly ONE engine edit (a keyword-only
> `all_bo3=False` whose default path is byte-identical). Everything else is NEW sibling modules or
> additive kwargs. **GATE-01 (Budapest backtest) MUST stay green for every engine-touching phase.**

## Active Requirements (v3)

### Multi-stage infrastructure (STG)

- [x] **STG-01
**: User can select which stage to view/simulate (Stage 1 / Stage 2 / Stage 3 / Playoffs); each stage loads its own teams/seeds from a per-stage fixture (`data/stageN.json`, `data/playoffs.json`) via a `load_stage(path)` wrapper that leaves the GATE-01 `load_teams` path frozen.
- [ ] **STG-02**: Stage 2 Swiss simulates via the FROZEN engine with Stage-2 teams; per-team P(3-0)/P(advance)/P(0-3) pass the same structural invariants (Σ = 2/8/2) as Stage 1. *(was V3-01)*
- [ ] **STG-03**: Stage 3 Swiss simulates via the FROZEN engine with Stage-3 teams; same invariants. *(was V3-02; match-format handled by BO-01)*
- [x] **STG-04
**: The `@st.cache_data` keys for BOTH `run_mc_cached` and `optimize_cached` include `stage_id` as a real positional arg, so switching stages never serves another stage's cached numbers (no cross-stage stale-serve). **[correctness gate]**
- [x] **STG-05
**: A per-stage `[INFERRED]`-seed banner persists and seeds stay editable for each stage until that stage's seeds are positively confirmed against the official list.

### Live-results ingest (RES)

- [x] **RES-01
**: User can click "fetch latest results" to pull FINISHED series (final outcomes only — no live map ticks) from a results API over the provider ladder (bo3.gg → PandaScore → Kalshi-derived), writing a read-only `data/results_cache.json`; the app only reads the cache (httpx never enters the app import path).
- [x] **RES-02
**: Fetched results pre-fill the current stage's `locked` set, so the existing conditional re-sim runs from auto-locked results without manual entry.
- [x] **RES-03
**: An auto-fetched result never silently overwrites a manual lock — a conflict requires explicit user confirm; provenance (auto vs manual) and stale-cache state (`_meta.fetched_at`) are surfaced.
- [x] **RES-04
**: Fail-soft — a missing key / network failure / unavailable source degrades to manual entry + a banner, never a crash or gate; first run needs no results source (Stage 1 manual locking works day one).
- [x] **RES-05
**: Provider team identities are joined to internal Team ids slug-first via `data/team_aliases.json` (reusing `odds/_match.py`); an unresolved team is surfaced loudly, never silently mis-locked.

### Inter-stage seeding chain (SEED)

- [ ] **SEED-01**: Stage N+1 qualifier seeds are derived from Stage N's FINAL Buchholz (`Σ(opp.w − opp.l)` via the canonical `engine.probs.difficulty`); invited teams seed by VRS; the invited/qualifier merge follows the Valve rule (pulled verbatim, held `[INFERRED]` + editable until confirmed).
- [ ] **SEED-02**: Seed derivation is a pure, file-I/O-free, RNG-free function with a documented tiebreak chain; identical inputs yield identical seeds across runs (two-run determinism test is the gate). **[correctness gate]**
- [ ] **SEED-03**: When a stage's results are complete and validated (reusing the `LivePrefixIncomplete` guard), the next stage's seeds auto-derive from them; a partial/incomplete stage produces no seed list.

### Match formats (BO)

- [ ] **BO-01**: Stage 3 runs in all-Bo3 mode — every match resolves through the closed-form `p²(3−2p)` — via a keyword-only `all_bo3` flag that applies on the rating-fallback branch ONLY (a market series price is never re-Bo3'd, PROB-02), leaving the Bo1-default GATE-01 path byte-identical.
- [ ] **BO-02**: The playoff grand final uses a verified Bo5 closed form `p³(6p²−15p+10)`, locked by a property test (== cumulative binomial on a grid, strictly monotone, f(0.5)=0.5, symmetric f(p)+f(1−p)=1).

### Playoffs (PO)

- [ ] **PO-01**: The 8-team single-elimination playoff bracket (4 QF → 2 SF → 1 GF) simulates end-to-end (Bo3 QF/SF + Bo5 GF) in a NEW sim module seeded from final Stage-3 Buchholz, retaining a full per-sim bracket sample.
- [ ] **PO-02**: A NEW playoff ballot optimizer recommends the optimal **nested** bracket (4 QF + 2 SF + 1 GF predictions, champion ⊆ finalists ⊆ QF winners) by brute-force enumerating the ~16 coherent brackets for a global optimum — its OWN ballot type, NOT a reuse of the Swiss 2/6/2 optimizer.
- [ ] **PO-03**: The optimizer maximizes the round-weighted **joint-AND** objective `P(≥2 QF ∧ ≥1 SF ∧ GF correct)` scored against the JOINT bracket sample (never multiplied marginals); the three tier marginals + E[achievements] are reported as diagnostics only.
- [ ] **PO-04**: Playoff ballot mechanics (the nesting constraint + SF scoring semantics) are re-confirmed against the live in-game Cologne Pick'Em before the optimizer objective is finalized — build the sample + outcome matrices first, wire the objective last. **[hard gate]**

### Closed / decided

- [x] **V3-04 — CLOSED: not-needed**: Optional map-level Bo3 modeling. GATE-01 going GREEN validated the closed-form `p²(3−2p)` against real data, so the single win prob per matchup stands; map-pool/veto modeling is a data burden with no accuracy gain. Carried from v1.0→v3 scoping.

## v2 Requirements (Operations — deferred, not in v3 phasing)

- **OPS-01**: Standalone cron job calls providers and writes `data/odds_cache.json` **and now `data/results_cache.json`**; app reads only — auto-fetch once per round after pairings/results post (zero app change because the read-only cache seams are honored). The v3 RES layer makes this a one-crontab-line drop-in.
- **OPS-02**: Numba JIT of the Swiss hot loop to bring 100k-sim runs under ~2s — only if pure-Python latency annoys during live use (requires an array-of-structs refactor).

## Out of Scope

| Feature | Reason |
|---------|--------|
| Live in-progress map-tick scores / streaming | Pick'Em scores on series outcomes only; final-series results suffice (RES is final-only) |
| 7 *independent* playoff match picks | WRONG model — the ballot is a nested bracket fill (champion ⊆ finalists ⊆ QF winners) |
| E[correct] objective for the playoff ballot | Over-weights the 4 cheap QF picks; use the round-weighted joint-AND objective (PO-03) |
| Scraping / browser automation (HLTV scrape) | APIs only; bo3.gg/PandaScore/Kalshi cover results; scraping is fragile + ToS-risky |
| Liquipedia LPDB / GRID Series Events as results source | Liquipedia ToS = educational-only + 1 req/2s; GRID Series Events is paid |
| New runtime deps (scipy/pandas/requests/aiohttp) | v3 adds ZERO deps — httpx + numpy + stdlib cover it |
| Account / auth / multi-user · theming / mobile · Champion-coin endgame prediction | Single local desktop tool; out of scope for a Pick'Em-EV tool |
| Map-veto / map-pool modeling | Single win prob per matchup; map-level Bo3 closed as not-needed (V3-04) |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| STG-01, STG-04, STG-05 | Phase 6 | Pending |
| RES-01, RES-02, RES-03, RES-04, RES-05 | Phase 6 | Pending |
| STG-02 | Phase 7 | Pending |
| SEED-01, SEED-02, SEED-03 | Phase 7 | Pending |
| STG-03, BO-01 | Phase 8 | Pending |
| BO-02, PO-01, PO-02, PO-03, PO-04 | Phase 9 | Pending |
| V3-04 | — | Closed (not-needed) |
| OPS-01, OPS-02 | v2 (deferred) | Deferred |

**Coverage:** 19/19 active reqs mapped (STG×5, RES×5, SEED×3, BO×2, PO×4) across Phases 6–9 — no orphans, no duplicates. V3-04 closed (not-needed); OPS-01/02 deferred to v2. Phase mapping finalized in ROADMAP.md (`/gsd-roadmap`, 2026-06-02).

---
*v3 requirements scoped 2026-06-02 at the v1.0 → v3 milestone boundary, informed by 4-agent research (`.planning/research/`); phases 6–9 fixed in ROADMAP.md 2026-06-02. Planning kept LOCAL-ONLY (public master gitignores `.planning/`). v1.0 reqs (54 satisfied) archived in `.planning/milestones/v1.0-REQUIREMENTS.md`.*
