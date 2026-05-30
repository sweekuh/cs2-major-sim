# Requirements: swiss-mc — v3 (Full-Major)

**Milestone:** v3 — Full-Major (Stages 2 & 3 Swiss + playoff single-elimination bracket)
**Predecessor:** v1.0 — Cologne Swiss-Stage Pick'Em (✅ shipped 2026-05-30; 54/54 reqs satisfied). v1.0 requirements archived in `.planning/milestones/v1.0-REQUIREMENTS.md`.

**Core Value:** Honestly-calibrated probabilities for the exact quantities Pick'Em scores on —
P(3-0)/P(advance)/P(0-3) per team and P(≥5/10) per ballot — including conditional re-sim, without
laundering guesses into false precision. v3 extends this from Stage 1 to the whole Major.

> Scope this milestone = full **v3**: Stages 2 and 3 Swiss plus the playoff single-elimination
> bracket, reusing the v1.0-validated correctness core. The playoff Pick'Em is its OWN ballot type
> (7-prediction round-weighted), NOT the Swiss 2/6/2.

## Active Requirements (v3)

### Full-Major scope

- [ ] **V3-01**: Stage 2 Swiss simulated via the same (v1.0-validated) engine with Stage 2 seeds; per-team probs pass the same invariants
- [ ] **V3-02**: Stage 3 Swiss simulated via the same engine with Stage 3 seeds; per-team probs pass the same invariants
- [ ] **V3-03**: Playoff single-elimination bracket simulated and optimized. NOTE (confirmed from the live in-game Pick'Em, 2026-05-28): the Playoffs Pick'Em is a **7-prediction ballot** scored by round — 2 Quarterfinal picks, 1 Semifinal pick, 1 Grand Final pick (achievements: "Place all seven Pick'Em predictions for the Playoffs", "two correct Quarterfinals", "one correct Semifinals", "a correct Grand Final"). The optimizer objective for playoffs is therefore round-weighted, NOT the Swiss 2/6/2 E[correct] — model it as its own ballot type, not a reuse of the Swiss optimizer.

### Closed / decided

- [x] **V3-04 — CLOSED: not-needed**: Optional map-level Bo3 modeling. **Decision (2026-05-30):** closed as not-needed. GATE-01 going GREEN (Budapest 2025 Stage 1 reproduced EXACTLY under the single-series-prob closed form `p²(3−2p)`) validated the closed-form Bo3 assumption against real data, so the single win prob per matchup stands and map-level Bo3 modeling is not required. The iid closed form is exact for identical independent maps; map-pool/veto modeling is a significant data burden with no accuracy gain.

## v2 Requirements (Operations — deferred, not in v3 phasing)

Tracked, carried forward from v1.0 planning. Not in the current milestone unless pulled forward.

- **OPS-01**: Standalone cron job (Ubuntu host) calls providers and writes `data/odds_cache.json`; app reads only — auto-fetch once per round after pairings post (TODOS #1; zero app change because the ODDS-07 read-only cache seam was honored in v1.0)
- **OPS-02**: Numba JIT acceleration of the Swiss hot loop to bring 100k-sim runs under ~2s — only if pure-Python latency annoys during live use (TODOS #2; requires array-of-structs refactor)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Account / auth / multi-user | Single local user; adds nothing for the use case |
| Map-veto / map-pool modeling | Single win prob per matchup; map-level Bo3 closed as not-needed (V3-04) |
| Scraping / browser automation | Every source has a clean API; scraping is fragile, slow, ToS-risky, adds no signal |
| Champion / Diamond-coin endgame prediction | Out of scope for a Pick'Em-EV tool |
| Streaming / live-tick odds | Pick'Em locks once per stage; streaming buys nothing over per-round fetch |
| Third-party confidence-pool scoring | Confirmed format is Valve binary; weighted-points objective not needed |
| localStorage/sessionStorage | Keep state in Streamlit `session_state` |
| Responsive / mobile / tablet, theming, branding | Local single-user desktop tool |
| Community/Discord/issue templates, SDK, DX telemetry | Private tool |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| V3-01 | Phase 6 | Pending |
| V3-02 | Phase 6 | Pending |
| V3-03 | Phase 6 | Pending |
| V3-04 | Phase 6 | Closed (not-needed — closed-form Bo3 validated by GATE-01) |
| OPS-01 | v2 (deferred) | Deferred |
| OPS-02 | v2 (deferred) | Deferred |

**Coverage:**
- v3 active requirements: V3-01, V3-02, V3-03 (V3-04 closed/decided)
- Mapped to phases: 3 active + 1 closed → Phase 6
- v2 deferred (not phased): OPS-01, OPS-02

---
*v3 requirements scoped 2026-05-30 at the v1.0 → v3 milestone boundary. v1.0 requirements (54 satisfied) archived in `.planning/milestones/v1.0-REQUIREMENTS.md`.*
