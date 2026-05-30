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
Phase 1 and is placed last because rating-only mode is fully functional and the first
run needs no API key; and v3 (Phase 6) reuses the validated engine for Stages 2–3 and
playoffs. Reversing any adjacent pair forces a rewrite.

## Milestones

- ✅ **v1.0** — Cologne Swiss-Stage Pick'Em — Phases 1-5 (shipped 2026-05-30)
- 🔭 **v3** — Full-Major — Phase 6 (next)

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

- [ ] **Phase 6: Full-Major v3** — Stages 2–3 Swiss + playoff single-elim via the same engine; playoffs use their own 7-pick round-weighted ballot type (map-level Bo3 closed as not-needed)

## Phase Details

### Phase 6: Full-Major v3 (next milestone)
**Goal**: Extend the validated engine to the whole Major — Stages 2 and 3 Swiss plus the playoff single-elimination bracket — reusing the same correctness core. The playoff Pick'Em is its OWN ballot type, not a reuse of the Swiss 2/6/2 optimizer.
**Mode:** mvp
**Depends on**: Phases 1–5 (full v1.0 stack + passed backtest)
**Requirements**: V3-01, V3-02, V3-03, V3-04
**Success Criteria** (what must be TRUE):
  1. Stage 2 and Stage 3 Swiss simulate via the same engine with different seeds, producing per-team probs that pass the same invariants (V3-01/V3-02).
  2. The playoff single-elimination bracket simulates and is optimized end-to-end as a **7-prediction round-weighted ballot** — 2 Quarterfinal picks, 1 Semifinal pick, 1 Grand Final pick — NOT the Swiss 2/6/2; the optimizer objective for playoffs is round-weighted and modeled as its own ballot type (V3-03).
  3. V3-04 (optional map-level Bo3 modeling) is **closed: not-needed** — GATE-01 going green validated the closed-form `p²(3−2p)` assumption against real data, so map-level modeling is not required (V3-04).
**Plans**: TBD
**UI hint**: yes

**Playoff ballot detail (V3-03):** Confirmed from the live in-game Pick'Em — the Playoffs Pick'Em
is a **7-prediction ballot scored by round**: 2 Quarterfinal picks, 1 Semifinal pick, 1 Grand
Final pick (achievements: "Place all seven Pick'Em predictions for the Playoffs", "two correct
Quarterfinals", "one correct Semifinals", "a correct Grand Final"). The optimizer objective is
therefore round-weighted, NOT the Swiss 2/6/2 E[correct] — model it as its own ballot type, not
a reuse of the Swiss optimizer.

**Map-level Bo3 gate (V3-04 — closed: not-needed):** The iid closed form is exact for identical
independent maps; sampling 3 map Bernoullis only adds MC noise without accuracy gain. Map-pool/
veto modeling is a significant data burden. GATE-01 going green (Budapest 2025 reproduced exactly
under the single-series-prob `p²(3−2p)` assumption) confirms the closed form is not the error
source, so V3-04 is explicitly **closed as not-needed**.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Engine + Backtest Gate | 4/4 | Complete (GATE-01 GREEN) | 2026-05-29 |
| 2. Streamlit UI Shell | 3/3 | Complete | 2026-05-29 |
| 3. Pick'Em Optimizer | 2/2 | Complete | 2026-05-29 |
| 4. Conditional Re-Sim + Live Mode | 2/2 | Complete | 2026-05-29 |
| 5. Odds Ensemble | 3/3 | Complete (live-slug /browse confirm DEFERRED) | 2026-05-30 |
| 6. Full-Major v3 | 0/TBD | v3 / next milestone | - |
