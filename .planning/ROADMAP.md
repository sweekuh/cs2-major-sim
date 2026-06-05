# Roadmap: swiss-mc — Cologne 2026 Swiss MC & Pick'Em Optimizer

## Overview

The build is one strict dependency chain, not a menu. A faithful Valve Swiss engine
is worthless unless its pairing logic is provably correct, so the round-by-round
backtest is a **hard blocking gate** at the end of Phase 1 — no UI, optimizer, odds,
or trusted output exists until it reproduces a real past Major stage's pairings
exactly. From there each layer rides on the one below: the Streamlit shell (Phase 2)
needs the generator-first MC and a `locked`-keyed cache; the optimizer (Phase 3) needs
the stored per-sim record sample; conditional re-sim + live mode (Phase 4) needs the
engine's `locked` support and the optimizer's P(≥5) scoring; the odds ensemble
(Phase 5) is a fail-soft enhancement that fills the epistemic outer loop stubbed in
Phase 1.

**v3 (Phases 6–9)** extends the FROZEN, GATE-01-gated engine to the rest of the Major
along a dependency-forced order: the stage-id cache-key fix + live-results seam must
land before any second stage (Phase 6); Stage 2 proves frozen-engine reuse, then the
inter-stage seeding chain rides on it (Phase 7); Stage 3 adds the single keyword-only
`all_bo3` flag (Phase 8); and the playoff bracket — the one genuinely new structural
sim, with its own Bo5 closed form and nested ballot optimizer — comes last because it
depends on Stage-3 seeds and on every reusable piece being proven (Phase 9).
**GATE-01 (the Budapest 2025 backtest) MUST stay green for every engine-touching
phase** — it is the cross-cutting exit criterion for v3. Reversing any adjacent pair
forces a rewrite.

## Milestones

- ✅ **v1.0** — Cologne Swiss-Stage Pick'Em — Phases 1-5 (shipped 2026-05-30)
- 🔭 **v3** — Full-Major — Phases 6-9 (in progress)

Archives: `.planning/milestones/v1.0-ROADMAP.md`, `.planning/milestones/v1.0-REQUIREMENTS.md`. Running log: `.planning/MILESTONES.md`.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.
Phase numbering continues across milestones — v3 work begins at Phase 6, never restarts.

<details>
<summary>✅ v1.0 (Phases 1-5) — SHIPPED 2026-05-30</summary>

- [x] **Phase 1: Engine + Backtest Gate** — Headless Valve Swiss engine + generator-first MC; round-by-round backtest is a hard blocking gate (✅ GATE-01 GREEN 2026-05-29 — reproduces Budapest 2025 Stage 1 R1-R5 exactly)
- [x] **Phase 2: Streamlit UI Shell** — Two-mode app with `locked`-keyed cache, CI mini-bars, [INFERRED]-seed banner, zero-config first run (✅ 2026-05-29)
- [x] **Phase 3: Pick'Em Optimizer** — Ballot A (greedy per-bucket baseline) + Ballot B (P(≥5) hill-climb) against the stored sim sample, with correlated-pick warning (✅ 2026-05-29)
- [x] **Phase 4: Conditional Re-Sim + Live Mode** — Round-by-round result locking, live/dead/secured status with P(≥5) delta, record-bucket bracket (✅ 2026-05-29)
- [x] **Phase 5: Odds Ensemble** — Three-provider log-opinion pool, ratings back-solve, epistemic outer loop, read-only cache seam; fails soft, never gates (✅ 2026-05-30 — full suite 113 passed, GATE-01 green; live-slug /browse confirm DEFERRED until Cologne markets post)

Full phase details (goals, plans, seams, decisions) archived in `.planning/milestones/v1.0-ROADMAP.md`.

</details>

**v3 — Full-Major (Phases 6-9):**

- [ ] **Phase 6: Multi-stage scaffold + live-results seam** — stage-id-in-cache-key correctness gate + stage selector + per-stage fixtures; the fail-soft live-results auto-ingest seam (applies to Stage 1 NOW; pre-fills `locked`; the input the seeding chain consumes)
- [ ] **Phase 7: Stage 2 + inter-stage seeding chain** — Stage 2 Swiss on the FROZEN engine (proves "different teams only") + the pure, deterministic `engine/seeding.py` that derives Stage N+1 seeds from Stage N final Buchholz
- [ ] **Phase 8: Stage 3 (all-Bo3)** — the single keyword-only `all_bo3` flag (rating-fallback branch only; market path untouched); GATE-01 stays green + no-double-Bo3 the gate
- [ ] **Phase 9: Playoff bracket + Bo5 + nested ballot optimizer** — the 8-team single-elim sim (Bo3 QF/SF + Bo5 GF), the verified Bo5 closed form, and the NEW nested round-weighted ballot optimizer (joint-AND objective, brute-force ~16 brackets)

## Phase Details

### Phase 6: Multi-stage scaffold + live-results seam
**Goal**: Make the app multi-stage-aware without breaking the freeze, and stand up the fail-soft live-results auto-ingest seam — so switching stages never serves another stage's cached numbers, and finished Stage-1 series can auto-pre-fill the `locked` set today (the same fetched results are the input the Phase-7 seeding chain consumes).
**Mode:** mvp
**Depends on**: Phases 1–5 (full v1.0 stack + passed backtest; the odds read-only-cache seam is the template the results seam mirrors)
**Requirements**: STG-01, STG-04, STG-05, RES-01, RES-02, RES-03, RES-04, RES-05
**Success Criteria** (what must be TRUE):
  1. User can select Stage 1 / Stage 2 / Stage 3 / Playoffs; each loads its own teams/seeds from a per-stage fixture via a `load_stage(path)` wrapper that leaves the GATE-01 `load_teams` / `_DEFAULT_FIXTURE` path byte-frozen (STG-01).
  2. The same `(ratings, S, N, locked, fetched_at)` under two different stages returns DIFFERENT cached Results — `stage_id` is a real positional arg in BOTH the `run_mc_cached` and `optimize_cached` keys (never the leading-underscore escape); switching stages always re-sims, never cross-stage stale-serves (STG-04). **[correctness gate]**
  3. User can click "fetch latest results" to pull FINISHED series only into a read-only `data/results_cache.json` (httpx never enters the app import path), and the fetched results pre-fill the current stage's `locked` set so the existing conditional re-sim runs from auto-locked results (RES-01, RES-02).
  4. Provider team identities join to internal ids slug-first via `data/team_aliases.json`; an unresolved team or a fetch that conflicts with a manual lock is surfaced loudly and requires explicit confirm — never a silent overwrite or a fabricated lock (RES-05, RES-03).
  5. A missing key / network failure / unavailable source degrades to manual entry + a banner — never a crash or a gate; first run needs no results source, and per-stage `[INFERRED]`-seed banners persist with editable seeds until each stage is confirmed (RES-04, STG-05).
**Plans**: 4 plans (3 waves — MVP vertical slices)
- [x] 06-01-PLAN.md — Slice 1 (the pivot): stage selector + `load_stage(path)` + `stage_id` in BOTH cache keys (STG-01, STG-04) [Wave 1] — DONE 2026-06-05 (134 tests green, GATE-01 green)
- [x] 06-02-PLAN.md — Slice 2: per-stage `[INFERRED]`-seed banner + stage3/playoffs fixtures (STG-05) [Wave 2] — DONE 2026-06-05 (135 tests green, GATE-01 green)
- [ ] 06-03-PLAN.md — Slice 3: read-only results seam — `ui/results_loader.py` + `scripts/fetch_results.py` (RES-01, RES-04, RES-05) [Wave 2]
- [ ] 06-04-PLAN.md — Slice 4: wire results into app — pre-fill `locked` via `validate_lock` + conflict-confirm + provenance (RES-02, RES-03) [Wave 3]
**UI hint**: yes
**Verify pass**: confirm the Cologne tournament slug/id on bo3.gg + PandaScore at ingest and seed `data/team_aliases.json` (gstack `/browse`) — a thin event-time verify, not a research phase.
**GATE-01:** must stay green (loader generalization must not touch `load_teams`/`_DEFAULT_FIXTURE`).

### Phase 7: Stage 2 + inter-stage seeding chain
**Goal**: Run Stage 2 Swiss on the FROZEN engine with Stage-2 teams (proving the generalization is "different teams only" — no engine edit), and build the pure, deterministic seeding chain that derives Stage N+1 seeds from Stage N's FINAL Buchholz so the chain — not a hand-typed list — drives every downstream stage.
**Mode:** mvp
**Depends on**: Phase 6 (stage scaffold + stage-id cache key; the fetched results that complete a Stage-1 final are the seeding chain's input)
**Requirements**: STG-02, SEED-01, SEED-02, SEED-03
**Success Criteria** (what must be TRUE):
  1. Stage 2 Swiss simulates via the FROZEN `simulate_stage` with Stage-2 teams; per-team P(3-0)/P(advance)/P(0-3) pass the same structural invariants (Σ = 2/8/2) as Stage 1, with no engine edit required to run it (STG-02).
  2. Stage N+1 qualifier seeds derive from Stage N's FINAL Buchholz via the canonical `engine.probs.difficulty` (one Buchholz definition, never a second copy); invited teams seed by VRS; the invited/qualifier merge follows the Valve rule held `[INFERRED]` + editable until confirmed (SEED-01).
  3. Seed derivation is a pure, file-I/O-free, RNG-free function with a documented tiebreak chain; identical prior-stage results yield byte-identical seeds across two runs (the two-run determinism test is the gate) (SEED-02). **[correctness gate]**
  4. When a stage's results are complete and validated (reusing the `LivePrefixIncomplete` guard), the next stage's seeds auto-derive from them; a partial/incomplete stage produces NO seed list (SEED-03).
**Plans**: TBD
**UI hint**: yes
**Verify pass**: pull the Valve invited/qualifier seed-merge rule verbatim (MEDIUM-confidence gap; held `[INFERRED]` + editable until verified against the official Cologne seeding when Stages post).
**GATE-01:** must stay green (Stage 2 reuses `simulate_stage` unchanged — if it needs an engine edit, the generalization is wrong).

### Phase 8: Stage 3 (all-Bo3)
**Goal**: Run Stage 3 as an all-Bo3 Swiss stage via a single keyword-only `all_bo3` flag that applies on the rating-fallback branch ONLY, so a market series price is never re-Bo3'd and the Bo1-default GATE-01 path stays byte-identical.
**Mode:** mvp
**Depends on**: Phase 6 (stage scaffold) + Phase 7 (Stage-3 seeds derive from the Stage-2 final via the seeding chain)
**Requirements**: STG-03, BO-01
**Success Criteria** (what must be TRUE):
  1. Stage 3 Swiss simulates via the FROZEN engine with Stage-3 teams in all-Bo3 mode — every match resolves through the closed-form `p²(3−2p)` — and per-team probs pass the same Σ = 2/8/2 invariants (STG-03).
  2. The all-Bo3 behavior is driven by a keyword-only `all_bo3` flag (`bo3 = all_bo3 or _is_bo3(a, b)` at the call site); `all_bo3=False` leaves the default path byte-identical and the Budapest backtest green (BO-01).
  3. A market-priced Stage-3 match's P equals the raw market series number — the market-override branch is never wrapped in a second `p²(3−2p)` (no double-Bo3); a rating-input match applies `series(p_map, bo3=True)` exactly once (BO-01). **[correctness gate]**
  4. The epistemic outer loop holds under Bo3-compressed means: high `var` with mean near 0/1 does not raise, and the reported band still ⊇ the inner Wilson band (routes through the existing `beta_moment_fit` clamp — never a second clamp implementation).
**Plans**: TBD
**UI hint**: yes
**GATE-01:** must stay green — the no-double-Bo3 market-bypass test + an `all_bo3=False` freeze-regression test are the gate.

### Phase 9: Playoff bracket + Bo5 + nested ballot optimizer
**Goal**: Simulate the 8-team single-elimination playoff end-to-end (Bo3 QF/SF + Bo5 grand final) in a NEW sim module, and recommend the optimal NESTED 7-pick bracket via a NEW round-weighted optimizer — its OWN ballot type, scored against the JOINT bracket sample, NOT a reuse of the Swiss 2/6/2.
**Mode:** mvp
**Depends on**: Phase 7 (final Stage-3 Buchholz seeds the 8-team bracket via the seeding chain) + Phase 8 (Stage 3 must complete to produce those seeds)
**Requirements**: BO-02, PO-01, PO-02, PO-03, PO-04
**Success Criteria** (what must be TRUE):
  1. The grand final uses the verified Bo5 closed form `p³(6p²−15p+10)`, locked by a property test (== cumulative binomial on a grid, strictly monotone, f(0.5)=0.5, symmetric f(p)+f(1−p)=1); a market GF price passes through untouched (BO-02). **[correctness gate]**
  2. The 8-team single-elim bracket (4 QF → 2 SF → 1 GF) simulates end-to-end in a NEW `engine/playoff.py` sibling seeded from final Stage-3 Buchholz, honoring `locked` + `market_overrides`, retaining a full per-sim bracket sample (PO-01).
  3. A NEW playoff optimizer (`engine/playoff_opt.py`, its OWN `PlayoffBallot` type) recommends the optimal NESTED bracket (champion ⊆ finalists ⊆ QF winners) by brute-force enumerating the ~16 coherent brackets for a global optimum — NOT a reuse of the Swiss optimizer (PO-02).
  4. The optimizer maximizes the round-weighted JOINT-AND objective `P(≥2 QF ∧ ≥1 SF ∧ GF correct)` scored against the JOINT bracket sample (never multiplied marginals) — a downstream pick scores only in sims where its team actually advanced; tier marginals + E[achievements] are diagnostics only (PO-03). **[correctness gate]**
  5. The playoff ballot mechanics (the nesting constraint + SF scoring semantics) are re-confirmed against the live in-game Cologne Pick'Em before the objective is finalized — the sample + outcome matrices are built first, the objective wired last (PO-04). **[hard gate]**
**Plans**: TBD
**UI hint**: yes
**Verify pass**: re-confirm playoff ballot mechanics vs the live in-game Pick'Em (~Jun 16–18) — **HARD GATE** (PO-04); build the sample/matrices first, finalize the objective after.
**GATE-01:** must stay green (the playoff is a sibling module — `montecarlo.py`/`swiss.py` are not edited; copy the MC scaffold rather than mutate the frozen one).

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Engine + Backtest Gate | 4/4 | Complete (GATE-01 GREEN) | 2026-05-29 |
| 2. Streamlit UI Shell | 3/3 | Complete | 2026-05-29 |
| 3. Pick'Em Optimizer | 2/2 | Complete | 2026-05-29 |
| 4. Conditional Re-Sim + Live Mode | 2/2 | Complete | 2026-05-29 |
| 5. Odds Ensemble | 3/3 | Complete (live-slug /browse confirm DEFERRED) | 2026-05-30 |
| 6. Multi-stage scaffold + live-results seam | 2/4 | In Progress (06-01, 06-02 done) | - |
| 7. Stage 2 + inter-stage seeding chain | 0/TBD | Not started | - |
| 8. Stage 3 (all-Bo3) | 0/TBD | Not started | - |
| 9. Playoff bracket + Bo5 + nested ballot optimizer | 0/TBD | Not started | - |
