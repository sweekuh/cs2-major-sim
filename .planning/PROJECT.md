# swiss-mc — Cologne 2026 Swiss Monte Carlo & Pick'Em Optimizer

## Current State

**v1.0 SHIPPED 2026-05-30** (Phases 1-5): the calibrated Cologne Stage-1 Swiss Pick'Em — engine
+ backtest, two-mode UI, dual-ballot optimizer, conditional live re-sim, fail-soft three-provider
odds ensemble. 113 tests green, GATE-01 backtest validated. Since then PRs #6-#9 landed live Cologne
odds, two P0 correctness fixes, and a public-facing forecast page (`public/index.html`).

**Public-release note:** the public `master` now gitignores `.planning/` and `CLAUDE.md` — GSD
planning is kept **local-only** (never committed). v3 *code* still ships to public `master` via
per-phase feature-branch PRs (as #6-#9 did).

**v3 — Full-Major STARTED 2026-06-02** (Phase 6+). The verified Cologne 2026 format (Wikipedia,
confirmed 2026-06-02) is an EXPANDED 32-team Major: **three** 16-team Swiss stages + an 8-team
single-elim playoff (Stage 3 is all-Bo3; the grand final is Bo5). v3 extends the validated engine
to Stages 2 & 3 + playoffs AND adds **live-results auto-ingest** so finished matches drive the
conditional re-sim and the inter-stage Buchholz seeding chain automatically. **Phase 6 SHIPPED 2026-06-06** — the multi-stage scaffold (stage selector + `stage_id` cache isolation; GATE-01 still green) and the fail-soft live-results read seam; 154 tests green, 7 review findings fixed. Next is Phase 7 (Stage 2 + the inter-stage seeding chain). See `.planning/MILESTONES.md`
and `.planning/milestones/v1.0-*` for the v1.0 archive.

## What This Is

An interactive Streamlit webapp (Python 3.12 · numpy) that simulates the IEM Cologne
Major 2026 Counter-Strike 2 Swiss stages via Monte Carlo, outputs per-team
P(3-0) / P(advance) / P(0-3) with confidence bands, recommends the optimal 2/6/2
Pick'Em ballot, reports the true P(≥5/10) coin odds, and supports round-by-round
result locking with conditional re-simulation. Win probabilities come from a
multi-provider market-odds ensemble pulled over APIs (Pinnacle anchor via OddsPapi,
blended with Polymarket and Kalshi), de-vigged, liquidity-weighted, and back-solved
into per-team ratings so the simulation can price unplayed Swiss branches. Single
local user (Zach) plus a few CS friends who clone the repo.

## Core Value

Honestly-calibrated probabilities for the exact quantities Pick'Em scores on —
P(3-0), P(advance), P(0-3) per team, plus P(≥5/10) for a ballot — including
conditional re-simulation that hand math cannot do past Round 3, without laundering
guessed inputs into false precision.

## Requirements

### Validated

- ✓ Headless Valve Stage-1 Swiss engine + Monte Carlo correctness core — v1.0. Buchholz `Σ(w−l)`, difficulty-rank fold, verbatim 15-row priority table, `locked` support, generator-first MC with `SeedSequence.spawn` reproducibility, full per-sim sample, closed-form Bo3, Wilson bands, invariants Σ=2/8/2.
- ✓ **Backtest gate GREEN (GATE-01/04/05) — 2026-05-29 — v1.0.** The engine reproduces StarLadder Budapest 2025 Stage 1's actual round-by-round pairings EXACTLY (R1-R5, including the 6-team priority-table rounds), validating Buchholz ranking + high-low fold + verbatim priority table against real data. Seeds from the authoritative Valve seeding VRS snapshot (`counter-strike_regional_standings` 2025_11_03, the "snapshot rule"). `BACKTEST_PASSED=True`.
- ✓ Two-mode Streamlit UI shell — v1.0. Pre-stage/Live toggle, editable ratings + S/N controls, validated Run, generator-driven progress, per-team probs with always-visible inline CI bars, colorblind-safe blue/amber status, trust badge, [INFERRED]-seed banner + confirm toggle, fail-soft odds banner, zero-config first run (no API key), `uv` bootstrap + README.
- ✓ Pick'Em optimizer — v1.0. Ballot A (greedy per-bucket marginal baseline) + Ballot B (P(≥5)-optimal hill-climb with re-bucketing), side by side with diff highlight, correlated-pick warning, P(≥5/10) hero scored against the stored sample (never a fresh MC run).
- ✓ Conditional re-sim + live mode — v1.0. Round-by-round result locking → conditional re-sim via the `locked` cache key, live/dead/secured status with P(≥5)-from-here delta, illegal-lock rejection with reasons, record-bucket bracket (solid locked / faint simulated).
- ✓ Fail-soft three-provider odds ensemble — v1.0. `OddsProvider` adapters (OddsPapi/Polymarket/Kalshi), de-vig + liquidity/sharpness-weighted log-opinion pool, ratings back-solve (series→map inversion + numpy-only logistic fit), epistemic Beta outer loop (band ⊇ Wilson, N-stable), read-only `data/odds_cache.json` seam; never gates, needs no API key. (Live-slug discovery deferred until Cologne markets post.)

### Active

<!-- v3 active requirements. Detailed REQ-IDs live in REQUIREMENTS.md. -->

**Full-Major scope (v3 — Phases 6+)**
- [ ] **Live-results auto-ingest** — fetch finished series from an API (APIs-only, fail-soft), write a read-only results cache, pre-fill the `locked` set + auto-derive the inter-stage seeding chain; manual entry stays as fallback (usable for Stage 1 immediately)
- [ ] **Stage 2 Swiss** — same v1.0 engine + multi-stage generalization; seeded from Stage-1 final Buchholz (8 qualifiers) + 8 VRS-invited
- [ ] **Stage 3 Swiss** — same engine in **all-Bo3 mode** (every match Bo3); seeded from Stage-2 final Buchholz + 8 VRS-invited
- [ ] **Playoff single-elim bracket** — 8 teams seeded by final Stage-3 Buchholz; Bo3 QF/SF + **Bo5 grand final**; optimized as a **7-match round-weighted ballot** (4 QF + 2 SF + 1 GF predictions; achievement thresholds 2-QF/1-SF/1-GF) — its OWN ballot type, NOT the Swiss 2/6/2

### Out of Scope

- Account / auth / multi-user — single local user; adds nothing for the use case
- Map-veto / map-pool modeling — single win prob per matchup; map-level Bo3 closed as not-needed (V3-04, validated by GATE-01)
- Scraping / browser automation — every source has a clean API; scraping is fragile, slow, ToS-risky, adds no signal
- Champion / Diamond-coin endgame prediction — out of scope for a Pick'Em-EV tool
- localStorage/sessionStorage (if an HTML variant is ever made) — keep state in Streamlit `session_state`
- Responsive / mobile / tablet, theming, branding — local single-user desktop tool
- Community/Discord/issue templates, SDK, telemetry — private tool

## Current Milestone: v3 — Full-Major

**Goal:** Extend the validated v1.0 correctness core to the rest of the Major — Stage 2 Swiss,
Stage 3 Swiss (all-Bo3), and the 8-team single-elim playoffs — and add live-results auto-ingest
so every stage's Pick'Em is calibrated and re-simmed automatically as matches finish.

**Verified format (Wikipedia, 2026-06-02 — `[[cologne-2026-full-format]]`):** expanded 32-team
Major. Stage 1 (16 VRS-invited, done) → Stage 2 (8 qualifiers + 8 invited) → Stage 3 (8 qualifiers
+ 8 invited, **all matches Bo3**) → Playoffs (8 teams single-elim, Bo3 QF/SF, **Bo5 grand final**).
Each Swiss stage is a single 16-team bracket, top 8 advance, Bo1 except adv/elim Bo3.

**Target features:**
- **Live-results auto-ingest** — a "fetch latest results" button pulls finished series from an API
  (source TBD by research; APIs-only, fail-soft), writes a read-only results cache, and pre-fills the
  `locked` set + derives the inter-stage seeding. Final series results only (no live map ticks).
  Manual entry remains the fallback. Applies to Stage 1 right away.
- **Inter-stage Buchholz seeding chain** — invited teams seed by global VRS; qualifiers seed by their
  FINAL Buchholz from the prior stage. Stage 2/3/playoff seeds are DERIVED from prior-stage results,
  not standalone `[INFERRED]` lists.
- **Stage 2 & Stage 3 Swiss** — same engine, same 2/6/2 Pick'Em + optimizer. Stage 3 adds an
  all-Bo3 stage flag (`p²(3−2p)` on every match, V3-01/V3-02).
- **Playoff bracket** — 8-team single-elim sim; **Bo5 grand final** needs a new closed form
  `p³(6p²−15p+10)`. Optimized as a **7-match round-weighted ballot** (its OWN ballot type, NOT the
  Swiss 2/6/2 E[correct] optimizer, V3-03). Exact ballot mechanics (7 match-winner picks vs the
  2-QF/1-SF/1-GF achievement thresholds) to be confirmed against the live in-game Pick'Em.
- **Map-level Bo3** — closed as **not-needed**: GATE-01 going green validated the closed-form
  `p²(3−2p)` against real data, so the single win prob per matchup stands (V3-04).

**Phasing:** split, Stage 2 first (user choice) — live-results, Stage 2, Stage 3, playoffs as
separate phases (final sequencing is the roadmapper's call; Phases 6-9 candidate). The event is
live (Stage 1 ~Jun 2-5, Stage 2 ~Jun 6-9, Stage 3 ~Jun 11-15, playoffs ~Jun 18-21), so live-results
ingest is weighted for immediacy.

## Context

- **Event:** IEM Cologne Major 2026. Stage 1 = 16 teams, first to 3 wins advances /
  3 losses eliminated; advancement & elimination matches Bo3, all others Bo1.
- **Format mechanics are nailed down** in the PRD/handoff (R1 N-vs-N+8 pairing,
  Buchholz from R3, no rematches, top-most non-rematch pairing row). The exact
  pairing/tiebreak table is pulled verbatim from Valve's `major-supplemental-rulebook.md`.
- **Seeds and default ratings are [INFERRED]** from announced R1 matchups (M80=6,
  NRG=9, Liquid=13 confirmed) and HLTV late-May 2026 order. Editable and reconciled
  against the official seed list at lock — a wrong seed silently corrupts every
  probability. `data/stage1.json` ships `seeds_confirmed=false`; the banner persists
  and the trust badge stays caveated until the user confirms.
- **Prior planning:** the companion `files/HANDOFF_claude_code.md` is the executable
  spec (repo layout, build order, exact engine pseudocode, acceptance tests). It has
  already passed `/plan-eng-review` (11 issues, 1 P0 Buchholz fix), `/plan-design-review`
  (3/10 → 9/10, §10.5 UI contract), and `/plan-devex-review` (TTHW 8min → <2min, §10.6).
  `files/PRD_cologne2026_pickem_simulator.md` holds the rationale. `TODOS.md` captures
  deferred work (cron-fed odds cache, Numba acceleration).
- **Why now:** Stage 1 Pick'Em locks once per stage; the tool must be ready and
  calibrated before lock, with conditional re-sim usable live during the event.

## Constraints

- **Tech stack**: Python 3.12, Streamlit, numpy, pure stdlib elsewhere, `httpx` confined to the odds layer — no other heavy deps. Engine ~300–500 LOC.
- **Bootstrap**: `uv` one command, cross-platform (author on Windows, friends on Mac/Linux); pip fallback. No bash-only `run.sh`.
- **Data sourcing**: APIs only, no scraping/browser automation. API keys from env (`.env` gitignored, `.env.example` shipped).
- **Correctness gate**: round-by-round backtest must pass before sim output is trusted or UI is built (slice-1 hard gate) — GREEN as of 2026-05-29.
- **Honesty**: CI bands visible everywhere; epistemic vs aleatoric uncertainty kept distinct; manual-input outputs labeled low confidence.
- **Performance**: pure-Python 100k run ~10–30s with spinner is acceptable for v0–v2; Numba acceleration deferred (TODOS #2) unless live-event latency annoys.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Win-prob source = multi-provider market-odds ensemble over APIs | Markets price the exact series; guessed inputs launder priors into false precision | ✓ Good — three-provider fail-soft ensemble shipped v1.0 |
| Interface = Streamlit (not static HTML) | Same process as engine + odds layer; only option that can run keyed server-side odds calls (HTML blocked by CORS) | ✓ Good — two-mode UI shipped v1.0 |
| Scope this cycle = full v3 (Stages 1–3 + playoffs + map-level) | User wants the whole-Major planning tool, not just Stage 1 | — v1.0 shipped Stage 1; Stages 2–3 + playoffs carry to v3 |
| Pick'Em scoring = official Valve binary (2/6/2, ≥5/10, exact-record 3-0/0-3) | Confirmed format; optimizer maximizes E[correct] and reports P(≥5) | ✓ Good — dual-ballot optimizer shipped v1.0 |
| Odds v1 = all three providers live (Pinnacle + Polymarket + Kalshi) | User wants divergence signal up front, not Pinnacle-only minimal set | ✓ Good — all three live + fail-soft v1.0 |
| Buchholz = `Σ(opp.wins − opp.losses)`, single seeding code path | Verified against rulebook worked example; `sum(o.wins)` passes invariants but corrupts all probs (eng-review P0) | ✓ Good — validated by GATE-01 backtest |
| Bo3 = closed form `p²(3−2p)` as a single Bernoulli draw | Exact for iid maps; sampling 3 maps only adds cost + noise (eng review, supersedes F2) | ✓ Good — GATE-01 green validated it; map-level Bo3 (V3-04) closed as not-needed |
| Epistemic variance via outer-loop Beta draws, not inner per-sim | Keeps source disagreement out of aleatoric MC noise so Wilson band isn't falsely tight at large N (G4) | ✓ Good — outer loop shipped v1.0, band ⊇ Wilson |
| Backtest is a slice-1 hard gate, not post-hoc validation | Only check that proves greedy rematch resolution matches Valve's priority table | ✓ Good — GATE-01 GREEN 2026-05-29 |
| Cologne 2026 is an expanded 32-team Major: 3 Swiss stages + 8-team playoff (Stage 3 all-Bo3, GF Bo5) | Verified vs Wikipedia 2026-06-02; the docs' "2 Swiss + playoffs" reading was correct, NOT the standard 2-stage Valve format | — v3 scoping basis; drives all-Bo3 + Bo5 + seeding-chain reqs |
| v3 adds live-results auto-ingest (fetch-button + read-only cache, final series only) | Auto-drives `locked` re-sim + the inter-stage seeding chain; mirrors the fail-soft odds seam; event is live | — added to v3 scope 2026-06-02 (user request) |
| Inter-stage seeds DERIVED from prior-stage final Buchholz, not standalone [INFERRED] lists | Verified format: qualifiers seed by final Buchholz, invited by VRS — seeds depend on results | — reshapes the [INFERRED]-seed handling for Stages 2/3/playoffs |
| GSD planning kept LOCAL-ONLY; v3 code ships to public master via per-phase PRs | Public-release PRs #8/#9 purged `.planning/` + `CLAUDE.md` from master and gitignored them | — planning never committed; code lands on master like #6-#9 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-02 — v3 (Full-Major) milestone STARTED. Verified Cologne format (3 Swiss + 8-team playoff, Stage 3 all-Bo3, GF Bo5); added live-results auto-ingest to scope; GSD planning now local-only (public master purged `.planning/`). v1.0 (Phases 1-5) shipped 2026-05-30.*
