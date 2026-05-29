---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: phase_complete
stopped_at: Executed Phase 3 (03-01 + 03-02) — optimizer green, OPT-01..05 done
last_updated: "2026-05-29T00:00:00.000Z"
last_activity: 2026-05-29
progress:
  total_phases: 6
  completed_phases: 3
  total_plans: 9
  completed_plans: 9
  percent: 50
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-28)

**Core value:** Honestly-calibrated probabilities for the exact quantities Pick'Em scores on — P(3-0)/P(advance)/P(0-3) per team and P(≥5/10) per ballot — including conditional re-sim, without laundering guesses into false precision.
**Current focus:** Phase --phase — 2

## Current Position

Phase: 3 (pickem-optimizer) — COMPLETE (2/2 plans executed)
Plan: 03-01 + 03-02 executed; OPT-01..05 done
Status: Phase complete — next is Phase 4 (conditional re-sim + live mode)
Last activity: 2026-05-29

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 7
- Average duration: — min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 4 | - | - |
| 02 | 3 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01 P01 | 25 | 3 tasks | 12 files |
| Phase 01 P02 | 20 | 2 tasks | 3 files |
| Phase 01 P03 | 20 | 2 tasks | 3 files |
| Phase 01 P04 | 25 | DEFERRED-GATE | 3 files |
| Phase 02 P01 | 8 | 3 tasks | 10 files |
| Phase 02 P02 | 8 | 2 tasks | 4 files |
| Phase 02 P03 | 12 | 3 tasks | 5 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Phase 1]: Backtest is a slice-1 HARD GATE, not post-hoc validation — only check proving greedy rematch resolution matches Valve's priority table.
- [Phase 1]: Buchholz = `Σ(opp.wins − opp.losses)`, single seeding code path (eng-review P0).
- [Phase 1]: Three cross-phase seams honored now — `locked` in swiss.py (Phase 4), generator-first MC + per-sim sample (Phases 2/3), epistemic outer loop stubbed (Phase 5).
- [Phase 5]: Odds placed last — fails soft, never gates; first run needs no API key.
- [Phase 1]: Pinned pytest 9.x (live pip index showed 9.0.3 current); supersedes RESEARCH assumption A1 (8.x [ASSUMED]). numpy confirmed 2.4.6.
- [Phase 1]: difficulty() canonical Buchholz lives in engine/probs.py; swiss.py imports it in wave 2 (no second copy).
- [Phase 1]: Team is @dataclass(eq=False) so opponent OBJECTS live in opps (difficulty() reads o.wins-o.losses); identity equality is correct per distinct stage entity.
- [Phase 1]: simulate_stage(teams, ratings, S, rng, locked); ratings is optional {id:rating} override (None->team.rating), the Phase-5/MC seam.
- [Phase 1, 2026-05-29 USER DECISION]: DEFER the full Budapest pairing-reproduction backtest (GATE-01). Budapest Stage 1 RESULTS reconciled + frozen, but the authoritative Valve 1-16 seed integers could not be sourced (HLTV Cloudflare-walled; Liquipedia/Wikipedia publish no seed integers) and the VRS world-rank order does NOT reproduce the actual R1/R2 pairings. Asserting a green backtest on guessed seeds = false pass/fail (T-04-01). Phase 1 gated on the green rulebook unit tests instead; Phase 2 unblocked WITH caveat (trust badge: "validated vs rulebook unit tests — full Budapest backtest pending seed data").
- [Phase 2 P01]: Pattern 2 option B — session_state mc_cache keyed on (ratings_key,S,N,locked_key) gives single in-session compute + a real progress bar; run_mc_cached also primed for cross-session memo.
- [Phase 2 P01]: locked_key is a REAL @st.cache_data key arg via freeze_locked (NOT the _locked escape) so Phase 4 locking moves >=1 P(advance) (RESIM-01 / Pitfall 13).
- [Phase 2 P01]: Fixed seed 20260528; Live toggle deferred to plan 02 (this slice = Pre-stage controls+Run+probs); streamlit pin 1.57.* resolves 1.57.0 though 1.58.0 now current.
- Phase 2 plan 02: STATUS palette locked colorblind-safe (advanced/live blue #3B82F6, eliminated amber #F59E0B); colour always paired with ASCII glyph + text label, never red/green (UI-06)
- Phase 2 plan 02: hero number renders a placeholder stand-in (top-team P(advance)) so the 28px monospace accent slot is real now; Phase 3/4 fill the optimal-ballot P(>=5)
- Phase 2 plan 03: BACKTEST_PASSED=False explicit constant gates the trust badge — it cannot drift to a green validated claim while GATE-01 is deferred; trust_badge_state validates only when BOTH BACKTEST_PASSED AND seeds_confirmed (Pitfall 6)
- [Phase 3 PLANNED 2026-05-29]: optimizer is a pure, RNG-free layer over `Result.sample` — Ballot A greedy is the EXACT E[correct] maximizer (no enumeration), Ballot B hill-climbs P(≥5) from the A seed (no ~10M brute force); P(≥5) vectorized via precomputed boolean outcome matrices so it never re-runs the MC (ROADMAP SC4).
- [Phase 3 PLANNED 2026-05-29]: correlated-0-3-in-R1 detection REUSES `engine.swiss.build_round1_pairs` — no seed re-derivation (sidesteps the GATE-01 seed blocker); warning is reported for Ballot A (correlation-blind), Ballot B avoids the trap for free via the joint sample.
- [Phase 3 PLANNED 2026-05-29]: pre-stage hero = recommended (Ballot B) P(≥5), filling the Phase-2 `_hero_slot` placeholder; Live-mode "P(≥5)-from-here" delta stays Phase 4. `optimize_cached` memoized on the SAME (ratings_key,S,N,locked_key) MC cache tuple (no recompute per rerun).
- [Phase 3 NOTE]: `/gsd-plan-phase` slash command is not installed in the web session (no .claude/commands/, GSD framework not cloned into the container); Phase 3 planning AND execution were done by hand following GSD conventions on branch `phase-3-optimizer`.
- [Phase 3 EXECUTED 2026-05-29]: `engine/optimizer.py` shipped — Ballot A greedy, Ballot B hill-climb, vectorized `p_ge5` over `Result.sample`, `correlated_03_in_r1`, `optimize()` facade. 12 new tests (7 optimizer + 3 render + 2 AppTest); full suite 63 passed, 1 skipped. No engine mutation.
- [Phase 3 EXECUTED 2026-05-29]: `optimize_cached(_result, ratings_key, S, N, locked_key)` memoizes on the MC cache tuple with `_result` underscore-EXCLUDED (correct here — Result is a pure function of the key, reused without re-running the MC; the deliberate inverse of the locked-in-key rule). `_hero_slot` kept for the LIVE Phase-4 placeholder; PRE-STAGE hero is the real recommended P(≥5).
- [Phase 3 V&V 2026-05-29]: verdict PASS (66 passed, 1 skipped; see 03-VERIFICATION.md). Fixed a latent warning id/seed lookup. Key finding: the bucket-wise greedy is NOT the global E[correct] maximizer (brute-force-confirmed +0.86 case) and Ballot B couldn't re-bucket to escape it. Resolved (user: "you choose" → option 2): broadened Ballot B's hill-climb with re-bucketing moves (`_neighbors`/`_rebucket`) and softened OPT-01 / `ballot_a` wording from "E[correct]-optimal" to "greedy per-bucket marginal baseline". Ballot A stays the literal greedy; Ballot B is the real P(≥5) recommendation.
- Phase 2 plan 03: INFERRED-seed banner + seed->team reconcile expander persists until the seeds_confirmed toggle (positive confirmation, no red) dismisses it; fail-soft odds-off banner uses os.environ only (no httpx/dotenv import — preserves zero-config first run)

### Pending Todos

[From .planning/todos/pending/ — ideas captured during sessions]

- **Complete Budapest 2025 backtest gate (GATE-01) once authoritative seeds sourced** — `.planning/todos/pending/2026-05-29-budapest-backtest-gate-gate01.md`. Captures the seed blocker, the VRS-vs-actual-pairing divergence finding (possible engine within-group-pairing nuance, not just a data gap — worth root-causing before trusting Cologne), and the resume path (obtain seeded bracket → freeze seeds → unskip backtest → apply GATE-04 fork on divergence).

### Blockers/Concerns

[Issues that affect future work]

- **GATE-01/04 DEFERRED (2026-05-29 user decision):** The round-by-round backtest is BLOCKED on the authoritative Valve seed bracket (HLTV Cloudflare-walled). Phase 1 is gated on the green rulebook unit tests instead; Phase 2 proceeds WITH the caveat in the trust badge. The deferred backtest carries a real open question: the VRS order does not reproduce Budapest's R1/R2 pairings — this may be a seed-data gap OR an engine within-group-pairing nuance that must be root-caused before Cologne output is fully trusted. Tracked in .planning/todos/pending.
- **Phase 1×2 seam:** SeedSequence.spawn over pinned chunk count must survive Phase 2 chunked progress yielding.
- **Phase 2×4 seam:** `@st.cache_data` key must include `locked` from Phase 2 or Phase 4 becomes a re-architecture.
- **Phase 5×v2 seam:** read-only `odds_cache.json` contract (ODDS-07) must be written so the deferred v2 cron (OPS-01) is a zero-app-change drop-in.
- **Requirement count note:** REQUIREMENTS.md header says 48 v1 requirements; the enumerated REQ-IDs total 58. All 58 enumerated IDs are mapped — flag the header discrepancy to the user.

## Deferred Items

Items acknowledged and carried forward:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Operations | OPS-01 cron-fed odds cache (zero app change if ODDS-07 honored) | v2 | roadmap |
| Operations | OPS-02 Numba JIT of Swiss hot loop (only if pure-Python latency annoys) | v2 | roadmap |

## Session Continuity

Last session: 2026-05-29
Stopped at: Executed Phase 3 (03-01 + 03-02) on branch phase-3-optimizer — full suite 63 passed, 1 skipped
Resume file: None
Resume path: Phase 4 — `/gsd-plan-phase 4` (conditional re-sim + live mode; reuses optimizer.p_ge5 for the P(≥5)-from-here delta)

**Completed Phase:** 03 (pickem-optimizer) — 2 plans — 2026-05-29

Next: Phase 4 (conditional re-sim + live mode). The `locked` cache-key seam (Phase 2) and
`engine.optimizer.p_ge5` (Phase 3) are the two pieces it builds on — re-sim fires for free
via the locked key; the live hero (_hero_slot) gets the P(≥5)-from-here delta.
