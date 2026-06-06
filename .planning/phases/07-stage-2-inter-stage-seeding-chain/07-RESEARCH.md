# Phase 7: Stage 2 + inter-stage seeding chain - Research

**Researched:** 2026-06-05
**Domain:** Pure deterministic seed derivation (inter-stage Buchholz chain) + frozen-engine reuse for a second Swiss stage
**Confidence:** HIGH (engine, loaders, live-guard, and fixtures read directly; the one genuinely new fact — the Valve Stage-2 invited/qualifier merge rule — pulled VERBATIM from the Valve supplemental rulebook and cross-confirmed on Wikipedia)

## Summary

Phase 7 has two deliverables and one of them is almost entirely *not new code*. STG-02 (run Stage 2 on the frozen engine) is a fixture-and-wiring task: the v1.0 engine (`simulate_stage`, `montecarlo`, `optimizer`) is already stage-size-agnostic and name-independent — it iterates `teams`, never `STAGE_SIZE` literally, and team names never enter the math. Phase 6 already shipped `load_stage(path)`, the `stage_id`-leading cache key in both `run_mc_cached`/`optimize_cached`, the stage selector, and a real (placeholder) `data/stage2.json`. So Stage 2 "simulating with Σ=2/8/2" needs **no engine edit** — it is proven by selecting Stage 2 and asserting the same invariants the Stage-1 MC tests already assert, plus the GATE-01 backtest staying green.

The real new work is `engine/seeding.py` (SEED-01/02/03): a **pure, file-I/O-free, RNG-free** function that, given a finished Stage-N final, produces the ordered seed→team map for Stage N+1. The Valve rule (now VERIFIED verbatim from the supplemental rulebook) is unambiguous and *simpler than the prior research feared*: **invited teams take seeds 1-8 (by pre-event Valve Regional Standing), qualifiers take seeds 9-16 (by their FINAL seed from the previous stage). They are NOT interleaved.** The qualifier's "final seed from the previous stage" is itself the Valve final-standings tiebreak chain: current W-L record → Difficulty Score (Buchholz `Σ(opp.w − opp.l)`) → initial seeding of that stage. Buchholz MUST come from the canonical `engine.probs.difficulty` (never a second copy — the ENG-03 trap). Determinism (SEED-02) is the correctness gate: identical prior-stage results must yield byte-identical seeds, which requires an EXPLICIT tiebreak chain and zero reliance on dict/set iteration order.

SEED-03 (auto-derive trigger) reuses the existing `engine.live.LivePrefixIncomplete` precondition: the next stage's seeds derive ONLY from a COMPLETE, fully-locked Stage-N final (every team terminated at 3W/3L). A partial fetch produces no seed list — never seed off sampled winners. The standings the chain consumes come from the same deterministic full-lock replay trick `engine.live.derive_bracket` already uses (`simulate_stage(..., locked=all_N, pairings_out=[])` with a throwaway RNG; a full lock prefix makes it RNG-invariant).

**Primary recommendation:** Build `engine/seeding.py` as a pure function `seed_next_stage(prior_teams, prior_standings, invited, qualifiers) -> list[Team]` that imports `engine.probs.difficulty`, ranks qualifiers by `(-difficulty, prior_final_seed)` into seeds 9-16 and invited by VRS rank into seeds 1-8, and is gated by a two-run determinism test (SEED-02) and a hand-worked tie test. Run Stage 2 entirely through the existing frozen engine + Phase-6 scaffold (no engine edit). Auto-derivation fires only behind a `LivePrefixIncomplete`-style completeness check. GATE-01 stays green because Stage 2 reuses `simulate_stage` byte-unchanged.

<user_constraints>
## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for Phase 7 (this is a non-interactive research task run ahead of `/gsd-discuss-phase`). The binding constraints are therefore the project's NON-NEGOTIABLE build rules from `CLAUDE.md` and the locked v3 decisions in `STATE.md` / `ROADMAP.md`, reproduced below as hard constraints the planner MUST honor:

### Locked Decisions (from CLAUDE.md + STATE.md + ROADMAP.md)
- **Buchholz / Difficulty Score = `Σ(opp.wins − opp.losses)`**, NOT `Σ opp.wins` (ENG-03). The seeding chain imports the canonical `engine.probs.difficulty` — NEVER a second copy.
- **GATE-01 (Budapest 2025 backtest) MUST stay green.** Stage 2 reuses `simulate_stage` unchanged — if Stage 2 needs an engine edit, the generalization is wrong.
- **The whole v3 milestone makes exactly ONE engine edit** (`all_bo3=False`, Phase 8 — NOT this phase). Phase 7 is additive-only: a NEW `engine/seeding.py` sibling module + fixture/wiring. Do NOT touch `engine/swiss.py`, `engine/montecarlo.py`, `load_teams`, or `_DEFAULT_FIXTURE`.
- **Seed derivation is pure: file-I/O-free, RNG-free, with a documented tiebreak chain.** Identical inputs yield identical seeds across runs (SEED-02 two-run determinism = the gate).
- **Seeds + default ratings are [INFERRED]** — keep editable, show the loud per-stage in-app banner, reconcile against the official seed list at lock. The Valve merge rule is held `[INFERRED]` + editable until confirmed against the official Cologne Stage-2 seeding when it posts.
- **Bo3 = closed form `p²(3−2p)` as a single Bernoulli draw** — never sample 3 maps (MC-06). Stage 2 is a normal Swiss stage (Bo1 default with Bo3 only on advancement/elimination matches via the existing `_is_bo3`). All-Bo3 is Stage 3 (Phase 8), NOT Stage 2.
- **Epistemic (source-disagreement) variance is an OUTER loop**, never folded into per-sim sampling (PROB-03/04). The seeding chain does not touch this; it operates on FINAL locked records only.
- **APIs only, no scraping.** The seeding chain consumes the Phase-6 results seam (`data/results_cache.json`), which is APIs-only and fail-soft.

### Claude's Discretion
- Exact signature/shape of `seed_next_stage` (the prior research sketch is a strong default but not binding — see Architecture Patterns).
- Whether the derived seed map is offered as an editable pre-fill in the UI vs. written to `data/stage2.json` (both honor the editable-`[INFERRED]` discipline; UI pre-fill is lower-risk and mirrors the results pre-fill pattern).
- Whether `invited` VRS data lives in the stage fixture's JSON or a separate constant.

### Deferred Ideas (OUT OF SCOPE for Phase 7)
- Stage 3 all-Bo3 (`all_bo3` flag) — Phase 8.
- Playoff bracket, Bo5 GF, nested ballot optimizer — Phase 9.
- The live Cologne provider-slug `/browse` confirmation — carried event-time verify, not a Phase-7 build blocker.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description (from REQUIREMENTS.md) | Research Support |
|----|-------------|------------------|
| **STG-02** | Stage 2 Swiss simulates via the FROZEN engine with Stage-2 teams; per-team P(3-0)/P(advance)/P(0-3) pass the same structural invariants (Σ = 2/8/2) as Stage 1. | Engine is stage-agnostic + name-independent (verified in `engine/swiss.py`, `montecarlo.py`); Phase 6 shipped `load_stage` + `stage_id` cache key + selector. New work = real Stage-2 fixture/seeds + an invariant test mirroring `test_mc.py::test_invariants`. NO engine edit. |
| **SEED-01** | Stage N+1 qualifier seeds derive from Stage N FINAL Buchholz (canonical `engine.probs.difficulty`); invited by VRS; invited/qualifier merge follows the Valve rule (verbatim, `[INFERRED]` + editable until confirmed). | Valve merge rule VERIFIED verbatim (supplemental rulebook): invited = seeds 1-8 by VRS, qualifiers = seeds 9-16 by final prior-stage seed. Tiebreak chain = W-L → Buchholz → initial seed. `difficulty()` confirmed canonical in `engine/probs.py:64`. |
| **SEED-02** | Seed derivation is a pure, file-I/O-free, RNG-free function with a documented tiebreak chain; identical inputs yield byte-identical seeds across runs (two-run determinism = the gate). **[correctness gate]** | Documented tiebreak chain below; two-run determinism test pattern mirrors `test_mc.py::test_reproducibility`. Determinism hazard = dict/set iteration order on Buchholz ties (PITFALLS Pitfall 3). |
| **SEED-03** | When a stage's results are complete and validated (reusing the `LivePrefixIncomplete` guard), next-stage seeds auto-derive; a partial/incomplete stage produces NO seed list. | `LivePrefixIncomplete` read directly (`engine/live.py:209`); `legal_pairings_for_round` already enforces the full-lock-prefix precondition. Auto-derive replays `simulate_stage(..., locked=all_N, pairings_out=[])` (the `derive_bracket` trick) only when the full prefix is locked. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Buchholz / final-standings computation | Functional core (`engine.probs.difficulty`) | — | Canonical, referentially transparent; one definition (ENG-03). The seeding chain CALLS it, never reimplements. |
| Stage N+1 seed derivation | Functional core (NEW `engine/seeding.py`) | — | Pure, RNG-free, file-I/O-free (SEED-02). Unit-testable in isolation like a mini-GATE. |
| Final-standings replay from locked results | Functional core (reuse `engine.live` replay pattern) | — | `simulate_stage(..., locked=all_N, pairings_out=[])` with throwaway RNG; full lock prefix = RNG-invariant. |
| Completeness gate (complete vs partial stage) | Functional core (reuse `engine.live.LivePrefixIncomplete`) | App (decides when to call) | The precondition logic already lives in `legal_pairings_for_round`; the app decides when a stage is "done". |
| Stage 2 simulation | Functional core (FROZEN `simulate_stage` + `montecarlo`) | — | Stage-agnostic already; different `teams` only. No engine edit (GATE-01). |
| Stage selection + cache isolation | UI (`ui/cache.py`, `app.py` — shipped Phase 6) | — | `stage_id`-leading cache key; selector writes `KEY_STAGE`. |
| Derived-seed pre-fill / editing + `[INFERRED]` banner | UI (`app.py` — extends shipped per-stage banner) | Functional core (provides the derived list) | Seed-safety discipline: editable + bannered until confirmed (STG-05 pattern, already shipped). |
| Provider fetch of Stage-1 finals | Script (`scripts/fetch_results.py` — shipped Phase 6) | — | httpx never on app import path; the input the chain consumes. |

## Standard Stack

No new packages. v3 adds ZERO runtime dependencies (REQUIREMENTS "Out of Scope": no scipy/pandas/requests/aiohttp). Phase 7 is pure stdlib + numpy + the existing engine.

### Core (all already present)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | ≥3.12 | Language (stdlib `sorted`, `dataclasses`, `json`, `pathlib`) | Project pin (CLAUDE.md) |
| numpy | 2.4.x | RNG for the throwaway replay (`np.random.default_rng(0)`) — seeding itself is RNG-free | Project pin; already the engine's only randomness source |
| (internal) `engine.probs` | — | Canonical `difficulty()` Buchholz | ENG-03 single-source-of-truth |
| (internal) `engine.swiss` | — | FROZEN `simulate_stage` for the standings replay + Stage 2 sim | GATE-01 frozen core |
| (internal) `engine.live` | — | `LivePrefixIncomplete` + the full-lock replay pattern | SEED-03 completeness gate already exists |
| (internal) `engine.teams` | — | `Team`, `load_stage`, `_validate_fixture_for_size` | Phase-6 multi-stage loader |

**Installation:** None. `uv run streamlit run app.py` / `uv run pytest -q` unchanged.

**Version verification:** N/A — no package install in this phase. The engine modules were all read directly this session and are the frozen v1.0 surface.

## Package Legitimacy Audit

> Not applicable — Phase 7 installs ZERO external packages. All code is new internal modules (`engine/seeding.py`) plus additive wiring against already-vendored engine code and the existing numpy/stdlib stack. No registry contact, no `pip install`, no `npm install`. slopcheck/registry verification is moot.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
  Stage-1 FINAL results
  (data/results_cache.json fetched  OR  manual KEY_LOCKED)
          │
          │  list[(round_idx, winner_id, loser_id)]   ── the existing Phase-4/6 lock-list contract
          ▼
  ┌───────────────────────────────────────────────────────────────────┐
  │  COMPLETENESS GATE  (reuse engine.live.LivePrefixIncomplete logic)  │
  │  every round fully locked AND every team terminated (3W or 3L)?     │
  │     NO  ──▶  produce NO seed list  (banner stays "awaiting finals")  │
  │     YES ──▶  proceed                                                 │
  └───────────────────────────────────────────────────────────────────┘
          │ YES
          ▼  replay  simulate_stage(fresh_teams, None, S, rng=default_rng(0),
          │                          locked=all_stage1, pairings_out=[])   [FROZEN, RNG-invariant under full lock]
          ▼
  final per-team objects {id: Team(wins, losses, opps)}
          │
          │  the 8 qualifiers = teams with wins == 3
          ▼
  ┌───────────────────────────────────────────────────────────────────┐
  │  engine.seeding.seed_next_stage(...)              [PURE: no I/O, no RNG]│
  │                                                                     │
  │   qualifiers (8):  sort key = (-difficulty(t), prior_final_seed(t)) │
  │                    difficulty() = canonical engine.probs.difficulty │
  │                    → assigned seeds 9..16 in that order             │
  │                                                                     │
  │   invited   (8):  sort key = vrs_global_rank (ascending)            │
  │                    → assigned seeds 1..8 in that order              │
  │                                                                     │
  │   merge: invited 1-8  THEN  qualifiers 9-16  (NOT interleaved)      │
  └───────────────────────────────────────────────────────────────────┘
          │
          ▼  ordered list[Team] for Stage 2  (seed = list position)
          │   [INFERRED] + editable in the UI until confirmed vs official seeds
          ▼
  Stage 2 runs on the FROZEN simulate_stage / run_mc_cached
          │   cache key carries stage_id="stage2"  (shipped Phase 6 — no cross-stage stale-serve)
          ▼
  per-team P(3-0)/P(advance)/P(0-3) with Σ = 2/8/2  (same invariants as Stage 1)
```

File-to-implementation mapping is in the Component Responsibilities table below, not in the diagram.

### Component Responsibilities

| File | Status | Responsibility | Constraint |
|------|--------|----------------|------------|
| `engine/seeding.py` | **NEW** | Pure `seed_next_stage(...)` — qualifiers by `(-difficulty, prior_seed)` into seeds 9-16, invited by VRS into seeds 1-8, merged 1-8 then 9-16. Returns ordered `list[Team]`. | Imports `engine.probs.difficulty` + `engine.teams.Team` ONLY. No streamlit/httpx, no file I/O, no RNG. Total function (never raises on legal input). |
| `engine/probs.py` | FROZEN | `difficulty()` (Buchholz). | Imported, never edited. |
| `engine/swiss.py` | FROZEN | `simulate_stage` for the standings replay + Stage 2 sim. | Imported, never edited (GATE-01). |
| `engine/live.py` | REUSE | `LivePrefixIncomplete` + full-lock replay (`legal_pairings_for_round` / `derive_bracket` pattern). | Reuse the precondition; a NEW thin helper for "is this stage complete?" is acceptable (additive, like `engine.live`'s own helpers). |
| `engine/teams.py` | REUSE | `Team`, `load_stage`, `_validate_fixture_for_size`. The derived seeds round-trip the SAME validation. | Frozen `load_teams`/`_DEFAULT_FIXTURE`/`_validate_fixture` untouched. |
| `data/stage2.json` | EDIT (data only) | Carry the 8 invited teams (VRS-ordered) + `[INFERRED]` qualifier placeholders + `seeds_confirmed: false`. | Same `_validate_fixture_for_size` discipline (16 unique seeds). NOT an engine edit. |
| `app.py` | EXTEND | Offer the derived Stage-2 seeds as an editable `[INFERRED]` pre-fill behind the completeness gate; the per-stage banner already exists (STG-05). | UX/wiring only; no engine edit. The conflict-confirm + pre-fill patterns already exist for results. |
| `tests/test_seeding.py` | **NEW** | SEED-02 two-run determinism gate + hand-worked tie test + the merge-rule test (invited 1-8 / qualifiers 9-16) + Buchholz-canonical test. | Mirrors `test_mc.py` / `test_swiss.py` patterns. |
| `tests/test_mc.py` (or `test_app.py`) | EXTEND | STG-02 Stage-2 invariant test (Σ=2/8/2 on the Stage-2 fixture). | Mirrors `test_mc.py::test_invariants`. |

### Pattern 1: Pure seed-derivation function (SEED-01/02)

**What:** A referentially-transparent function with an explicit, documented tiebreak chain. The shape sketched in the v3 ARCHITECTURE.md research (a strong default):

```python
# engine/seeding.py — NEW pure module (no streamlit/httpx, no file I/O, no RNG)
from __future__ import annotations
from dataclasses import dataclass
from engine.probs import difficulty   # canonical Buchholz Σ(opp.w − opp.l) — ENG-03, NO second copy
from engine.teams import Team


@dataclass(frozen=True)
class InvitedTeam:
    """A Stage-2 invited team seeded by its global Valve Regional Standing rank."""
    name: str
    vrs_rank: int      # global VRS rank (lower = better seed)
    rating: float      # [INFERRED] rating-only fallback prior; editable in the UI


def seed_next_stage(
    prior_finals: dict[int, "Team"],   # {id: final Team object} from the full-lock replay
    invited: list[InvitedTeam],        # the 8 VRS-invited teams
) -> list[Team]:
    """Derive the ordered seed 1..16 Team list for the next Swiss stage (VERIFIED Valve rule).

    Valve merge rule (supplemental rulebook, VERBATIM):
      "The teams directly invited to this stage will be seeds 1-8, and use their
       pre-event seed. The advancing 8 teams will be seeds 9-16 and use their final
       seed from the previous stage."  — NOT interleaved.

    Qualifiers = the 8 prior-stage teams with wins == ADVANCE_AT_WINS. Their "final seed
    from the previous stage" is the Valve final-standings order:
      W-L record  →  Difficulty Score (canonical difficulty())  →  initial seed.
    Since all 8 qualifiers share a 3-win record, the discriminator is (-difficulty, prior_seed).

    PURE: no RNG, no file I/O. Identical inputs → byte-identical output (SEED-02).
    """
    qualifiers = [t for t in prior_finals.values() if t.wins >= 3]  # ADVANCE_AT_WINS
    # Documented tiebreak chain — qualifiers by FINAL prior-stage standing:
    #   1. (record is uniform: all advancers are 3-x, so record drops out among the 8)
    #   2. Difficulty Score DESCENDING (higher Buchholz = better seed)  → -difficulty(t)
    #   3. initial seed of the prior stage ASCENDING (final tiebreak)   →  t.seed
    qualifiers_ranked = sorted(qualifiers, key=lambda t: (-difficulty(t), t.seed))

    # Invited by global VRS rank ASCENDING; vrs_rank is unique per the official list, but
    # add a stable name fallback so the sort is total even on a hand-entered duplicate.
    invited_ranked = sorted(invited, key=lambda iv: (iv.vrs_rank, iv.name))

    seeds: list[Team] = []
    # Seeds 1-8 = invited (pre-event / VRS order).
    for i, iv in enumerate(invited_ranked, start=1):
        seeds.append(Team(id=i, name=iv.name, seed=i, rating=iv.rating))
    # Seeds 9-16 = qualifiers (final prior-stage seed order).
    for offset, t in enumerate(qualifiers_ranked):
        s = 9 + offset
        seeds.append(Team(id=s, name=t.name, seed=s, rating=t.rating))
    return seeds
```

**When to use:** Always — this is the single derivation path. The output flows into the same `_validate_fixture_for_size` discipline (16 unique seeds 1..16) so a malformed derivation still fails loud.

**Key subtleties for the planner:**
- **`difficulty(t)` requires the replayed `Team` objects** (it reads `o.wins - o.losses` over `t.opps`, which hold opponent *objects*). So the chain must consume the post-replay `{id: Team}` from `simulate_stage`, NOT a flattened `{id: (wins, losses)}` — the bare record tuple loses the opponent set Buchholz needs. (The ARCHITECTURE.md sketch passing `prior_standings` + `prior_opps` separately also works, but reusing the live `Team` objects from the replay is simpler and reuses the canonical `difficulty()` directly.)
- **`id` vs `seed`:** the project rule "never assume `id == seed`" (`live.py:14`) applies. For the DERIVED Stage-2 fixture it is fine to set `id = seed = list position` (a fresh stage's teams are new entities, exactly as `data/stage1.json` does), but the qualifier's `t.seed` used in the tiebreak is the team's **Stage-1 initial seed**, not its Stage-2 seed. Keep these distinct in the code.

### Pattern 2: Stage 2 on the frozen engine (STG-02) — wiring, not code

**What:** Run Stage 2 with the same `run_mc_cached("stage2", ...)` / `optimize_cached` path Phase 6 already wired. The engine reuse is already proven by Phase 6's `test_stage_switch_isolates_cache`.

```python
# This already works end-to-end (Phase 6). Stage 2 needs only a real fixture + an invariant test:
teams, cfg = load_stage(_path_for_stage("stage2"))   # 16 Stage-2 teams (invited 1-8 + qualifiers 9-16)
result = run_mc(teams=teams, ratings=None, S=40.0, N=50_000, locked={}, seed=2024)
# Σ invariants identical to Stage 1 — see Pattern below.
```

**Why no engine edit:** `simulate_stage` iterates `teams` and uses `build_round1_pairs` (seed i vs i+8, size-derived), groups by `(wins, losses)`, ranks by `(-difficulty, seed)`, and the 6-team priority table fires on the same record-group structure. None of this is Stage-1-specific. Phase-6 SUMMARY confirms the engine is name-independent — identical per-seed ratings give identical counts regardless of the fixture's names.

### Pattern 3: Completeness-gated auto-derive (SEED-03)

**What:** Derive ONLY from a complete, fully-locked stage. Reuse the `LivePrefixIncomplete` precondition rather than inventing a new guard.

```python
# Conceptual — the app (or a thin engine.seeding helper) gates derivation:
def stage_is_complete(teams, locked_results, S) -> bool:
    """True iff every round is fully locked AND every team has terminated (3W/3L).

    Reuses the engine.live full-lock-prefix machinery: if legal_pairings_for_round can be
    asked for the round PAST the last and the prefix is fully locked, the stage is complete.
    A partial stage raises LivePrefixIncomplete (or leaves an active, non-terminated team).
    """
    by_id = derive_bracket(teams, locked_dict_from_results(locked_results), S).records
    return all(w >= 3 or l >= 3 for (w, l) in by_id.values()) and <every round fully locked>
```

Then: complete → replay → `seed_next_stage` → offer editable `[INFERRED]` seeds. Partial → no seed list, banner says "awaiting Stage-1 finals." This is the multi-stage analogue of the live-mode "don't open round R before R-1 is locked" rule.

### Anti-Patterns to Avoid
- **A second Buchholz implementation in `seeding.py`** (recompute `Σ(w−l)` inline). The exact ENG-03 trap — two copies drift. Import `engine.probs.difficulty`. (PITFALLS Anti-Pattern 4.)
- **Interleaving invited and qualifiers** by a combined ranking. The Valve rule is explicitly NOT interleaved (invited 1-8, qualifiers 9-16). Interleaving shifts the whole seed-i-vs-i+8 R1 fold and corrupts every Stage-2 pairing.
- **Ranking qualifiers by Buchholz alone with no explicit tiebreak.** Python's `sorted` is stable but the *input order* may be dict/set iteration order → non-deterministic seeds. Always append `prior_seed` (and a final id fallback) to the key. (PITFALLS Pitfall 3 — owns the reproducibility guarantee.)
- **Auto-seeding off a partial fetch.** Seeding off sampled (unlocked) winners produces a single-RNG-draw bracket. Gate on full completion. (PITFALLS Anti-Pattern 6.)
- **Editing `engine/swiss.py` / `montecarlo.py` / `load_teams` / `_DEFAULT_FIXTURE` to "support Stage 2."** They already support it. Any such edit breaks the freeze and risks GATE-01.
- **Flattening the replay to `{id: (wins, losses)}` before computing Buchholz.** `difficulty()` needs the opponent *objects* (`t.opps`). Carry the `Team` objects through.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Buchholz / Difficulty Score | A `sum(o.wins - o.losses ...)` inline in `seeding.py` | `engine.probs.difficulty` | ENG-03 single-source; two copies drift to the `Σw` bug |
| Final standings from locked results | A by-hand W-L tally + pairing re-derivation | `simulate_stage(..., locked=all_N, pairings_out=[])` replay (the `engine.live.derive_bracket` trick) | A full lock prefix makes the replay RNG-invariant; re-deriving pairings by hand re-opens the GATE-01 seed/Buchholz blind spot |
| "Is the stage finished / can I open the next?" precondition | A new completeness checker | `engine.live.LivePrefixIncomplete` + the `legal_pairings_for_round` full-lock-prefix logic | The exact precondition already exists and is tested (`test_live.py`) |
| Stage-2 Swiss simulation | A second Swiss simulator | FROZEN `engine.swiss.simulate_stage` + `engine.montecarlo.run_mc` | Stage-agnostic + name-independent already; GATE-01 frozen |
| Per-stage fixture validation | Bespoke 16-seed checks | `engine.teams._validate_fixture_for_size` (Phase 6 sibling) | Loud-fail on dup/short seed lists; mirrors `_validate_fixture` |
| Stage-2 cache isolation | A manual cache-bust on stage switch | The `stage_id`-leading cache key (shipped Phase 6, STG-04) | Already proven by `test_stage_switch_isolates_cache` |
| Editable `[INFERRED]`-seed banner | A new banner | The per-stage `seeds_confirmed_{stage_id}` banner + `read_seeds_confirmed` (shipped Phase 6, STG-05) | Already scoped per-stage |

**Key insight:** Phase 7 is ~90% reuse. The only genuinely new *code* is the pure `seed_next_stage` function; the only genuinely new *fact* is the Valve merge rule (now verified). Everything else — the engine, the replay trick, the completeness guard, the cache isolation, the banner — already exists and is tested. The risk is concentrated entirely in (a) the seed-derivation determinism and (b) getting the merge rule right; both are addressed below.

## Runtime State Inventory

> Phase 7 is greenfield code + data wiring (a new pure module + a fixture edit + UI pre-fill). It does NOT rename, refactor, or migrate any stored runtime state. The brief explicitly frames it as additive. The categories below are answered for completeness:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no datastore stores a seed map as a key. The derived seeds live in `data/stage2.json` (a committed editable fixture, regenerated by derivation) or as an in-session editable pre-fill. | None |
| Live service config | None — no external service holds Stage-2 seeds. The Stage-1 finals come from `data/results_cache.json` (the Phase-6 read-only fetched artifact, gitignored). | None |
| OS-registered state | None — no OS-level registration. | None |
| Secrets/env vars | None new — the chain reads no keys. The optional `PANDASCORE_KEY` (results fetch) is Phase-6 territory and unchanged. | None |
| Build artifacts | None — pure Python module + JSON; no compiled/installed artifact carries a Stage-2 seed. | None |

**The canonical question — after every file is updated, what runtime state still holds the old value?** Nothing. There is no "old value" to migrate: Stage-2 seeds are *derived* (or placeholder until derived), not a long-lived stored identity being renamed.

## Common Pitfalls

### Pitfall 1: Non-deterministic seeds from Buchholz ties (the SEED-02 gate)
**What goes wrong:** Two qualifiers finish with equal final Buchholz; ranking them by Buchholz alone leaves their relative order to dict/set iteration order, so re-running the app produces a different Stage-2 bracket from the same Stage-1 results, and the derived list may not match the official one when it posts.
**Why it happens:** `prior_finals` is a dict; `t.opps` is a set; `sorted` is stable but only preserves *input* order, which is iteration-order-dependent. Equal-Buchholz 3-1 qualifiers are common.
**How to avoid:** Explicit total tiebreak chain `(-difficulty(t), t.seed)` (and a final id fallback if you ever key on something non-unique). This mirrors the within-stage `rank_group` key at `swiss.py:85` exactly. The Valve rulebook confirms the final tiebreak IS "initial seeding of the current stage" — so `t.seed` (the prior-stage initial seed) is the *correct* documented discriminator, not an arbitrary one.
**Warning signs:** A determinism test that passes intermittently; seeds that differ between a fresh process and a warm one. **The two-run determinism test (SEED-02) is the gate** — assert byte-identical output across two independent `seed_next_stage` calls on the same input.

### Pitfall 2: Wrong merge rule (interleave vs separate)
**What goes wrong:** Assuming invited and qualifiers interleave by a combined ranking (e.g. all 16 sorted by some unified strength). This shifts every team's seed and therefore every R1 pairing (seed i vs i+8), silently corrupting the entire Stage-2 simulation.
**Why it happens:** It's a plausible-sounding default, and the Stage-1 rulebook line ("seeded solely on Global Standings") is about Stage 1 only, which can mislead.
**How to avoid:** The VERIFIED rule (supplemental rulebook): **invited = seeds 1-8 (pre-event/VRS), qualifiers = seeds 9-16 (final prior-stage seed). NOT interleaved.** Hold it `[INFERRED]` + editable until reconciled against the official Cologne Stage-2 seed list when it posts, but the rule itself is verbatim from Valve.
**Warning signs:** A Stage-2 R1 pairing that pits two invited teams against each other (impossible under the separate rule — seed 1 invited always faces seed 9, a qualifier).

### Pitfall 3: Computing Buchholz from a flattened record (losing the opponent set)
**What goes wrong:** Passing `{id: (wins, losses)}` into the seeding function and trying to compute Buchholz — but Buchholz needs each opponent's `(wins − losses)`, which the flattened tuple doesn't carry. Result: a wrong or impossible Buchholz, or a re-implementation that drifts.
**Why it happens:** `(wins, losses)` *feels* like "the standings," but `difficulty()` reads `t.opps` (opponent objects).
**How to avoid:** Carry the replayed `Team` objects (`{id: Team}` from `simulate_stage`) into `seed_next_stage` and call the canonical `difficulty()` on them. The opponent set is populated by the replay.
**Warning signs:** A Buchholz of 0 for everyone; needing to "reconstruct opponents" inside `seeding.py`.

### Pitfall 4: `seeds_confirmed=false` banner not persisting / dismissing the wrong stage
**What goes wrong:** Confirming Stage-1 seeds dismisses the Stage-2 `[INFERRED]` banner, or the derived Stage-2 seeds load with `seeds_confirmed=true` and suppress the banner the user needs.
**Why it happens:** A global (non-per-stage) confirm flag, or a derivation that writes `seeds_confirmed: true`.
**How to avoid:** The shipped per-stage `seeds_confirmed_{stage_id}` session key (Phase 6, STG-05) already scopes this correctly — reuse it. Derived seeds MUST carry `seeds_confirmed: false` (they are `[INFERRED]` until reconciled against the official list). `data/stage2.json` already ships `false`.
**Warning signs:** Switching Stage 1 → Stage 2 shows no banner despite unverified seeds; the trust badge reads "validated" on a derived-but-unconfirmed stage.

### Pitfall 5: Off-by-one in advance counting (who are the 8 qualifiers)
**What goes wrong:** Selecting qualifiers by `wins == 3` vs `wins >= 3`, or including a team that reached 3 wins in a malformed partial replay. Wrong qualifier set → wrong seeds 9-16.
**Why it happens:** `ADVANCE_AT_WINS == 3` and the terminal record is exactly 3-0/3-1/3-2 — but a guard on `>= 3` is safer against any future format change and matches the engine's own `t.wins >= ADVANCE_AT_WINS` active-team filter (`swiss.py:321`).
**How to avoid:** Use `t.wins >= ADVANCE_AT_WINS` (import the constant from `engine.teams`); assert exactly 8 qualifiers (a complete 16-team stage always yields exactly 8 advancers — assert it, fail loud otherwise). The completeness gate (Pitfall in SEED-03) guarantees the replay is a *finished* stage, so the count is exactly 8.
**Warning signs:** `seed_next_stage` producing a non-16-length list; `_validate_fixture_for_size` rejecting the derived fixture.

## Code Examples

### SEED-02 two-run determinism gate (the correctness gate)
```python
# tests/test_seeding.py — mirrors test_mc.py::test_reproducibility (same (input)->identical output shape)
def test_seed_derivation_is_deterministic():
    """SEED-02 GATE: identical prior-stage finals + invited list -> byte-identical Stage-2 seeds
    across two independent calls. No RNG, no file I/O, no dict/set-iteration-order dependence."""
    prior_finals = _build_finished_stage1_replay()   # {id: Team} from a fixed full-lock replay
    invited = _fixed_invited_8()
    a = seed_next_stage(prior_finals, invited)
    b = seed_next_stage(prior_finals, invited)
    assert [(t.seed, t.name, t.rating) for t in a] == [(t.seed, t.name, t.rating) for t in b]
    assert [t.seed for t in a] == list(range(1, 17))   # exactly seeds 1..16
```

### SEED-01 merge-rule + tie tests
```python
def test_invited_take_seeds_1_8_qualifiers_9_16():
    """SEED-01 (VERIFIED Valve rule): invited occupy seeds 1-8 (VRS order), qualifiers 9-16
    (final prior-stage seed order) — NOT interleaved."""
    seeds = seed_next_stage(prior_finals, invited)
    invited_names = {iv.name for iv in invited}
    assert all(seeds[i].name in invited_names for i in range(8))        # seeds 1-8 invited
    assert all(seeds[i].name not in invited_names for i in range(8, 16))# seeds 9-16 qualifiers

def test_qualifier_buchholz_tie_breaks_on_prior_seed():
    """A documented hand-worked tie: two qualifiers with equal final Buchholz rank by their
    Stage-1 initial seed (the Valve final tiebreak: W-L -> Difficulty -> initial seed)."""
    # construct two 3-1 qualifiers with equal difficulty() but prior seeds 3 and 7
    seeds = seed_next_stage(prior_finals_with_tie, invited)
    # the prior-seed-3 team gets the earlier (better) Stage-2 seed among the tied pair
    assert _stage2_seed_of(seeds, "PriorSeed3") < _stage2_seed_of(seeds, "PriorSeed7")

def test_buchholz_uses_canonical_difficulty():
    """ENG-03: seeding imports engine.probs.difficulty — no second copy. (Guard: the module
    source contains no inline 'o.wins - o.losses' Buchholz re-implementation.)"""
    import engine.seeding as s
    src = open(s.__file__, encoding="utf-8").read()
    assert "from engine.probs import difficulty" in src
    assert "o.wins - o.losses" not in src and "opp.wins - opp.losses" not in src
```

### STG-02 Stage-2 invariant test (mirrors `test_mc.py::test_invariants`)
```python
# tests/test_mc.py (or test_app.py) — STG-02
def test_stage2_invariants():
    """STG-02: Stage 2 on the FROZEN engine -> ΣP(3-0)≈2, ΣP(0-3)≈2, ΣP(advance)≈8 (±0.05),
    same structural invariants as Stage 1, no engine edit."""
    teams, _cfg = load_stage(_path_for_stage("stage2"))   # the real (or [INFERRED]) Stage-2 fixture
    N = 50_000
    r = run_mc(teams=teams, ratings=None, S=40.0, N=N, locked={}, seed=2024)
    assert abs(sum(c / N for c in r.counts_30.values()) - 2.0) <= 0.05
    assert abs(sum(c / N for c in r.counts_03.values()) - 2.0) <= 0.05
    assert abs(sum(c / N for c in r.counts_advance.values()) - 8.0) <= 0.05
```

### SEED-03 completeness gate (partial → no seeds)
```python
def test_partial_stage_yields_no_seeds():
    """SEED-03: a partially-locked Stage 1 (not every team terminated) produces NO Stage-2 seed
    list — reuse the LivePrefixIncomplete / full-lock-prefix precondition; never seed off sampled
    winners."""
    partial_locks = _stage1_locks_through_round(3)   # rounds 4-5 unlocked
    assert not stage_is_complete(stage1_teams, partial_locks, S=40.0)
    # the app/helper must NOT call seed_next_stage; it shows "awaiting finals" instead.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 24-team Major, MRQ regional qualifiers | 32-team Major, all slots filled by VRS invites (MRQs removed) | Major Supplemental Rulebook update 2025-06-09; format from BLAST.tv Austin 2025 onward | Stage 2 = 8 VRS-invited + 8 Stage-1 qualifiers; the merge rule this phase implements is the post-2025 format |
| (v1.0) Single Stage-1 fixture, always `stage1.json` | Per-stage fixtures + `stage_id` cache key + `load_stage` | Phase 6 (2026-06-05) | Stage 2 reuse is wiring, not engine work |

**Deprecated/outdated:**
- Any pre-2025 "24-team Major" or "MRQ" framing — Cologne 2026 is the 32-team VRS-invite format (verified Wikipedia + Valve rulebook).
- The prior-research worry that the merge rule might be interleaved or undocumented — RESOLVED: it is verbatim in the supplemental rulebook (invited 1-8 / qualifiers 9-16, separate).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The **specific Cologne 2026 Stage-2 invited team list and their VRS ranks** are not yet final/posted; the fixture's invited block is `[INFERRED]` + editable until reconciled. | SEED-01, `data/stage2.json` | LOW for the *algorithm* (the rule is verified); the *data* (which 8 teams, what ratings) is editable and bannered — wrong data ≠ wrong code. Reconcile at lock. |
| A2 | The qualifier ratings in the derived Stage-2 fixture are the `[INFERRED]` rating-only fallback prior (carried from Stage-1 ratings or re-entered); when live odds load, the app back-solves market-calibrated ratings. | Pattern 1, `data/stage2.json` | LOW — ratings are explicitly editable/`[INFERRED]` everywhere (CLAUDE.md). Affects probability magnitudes, not structure; Σ invariants hold regardless. |
| A3 | "Final seed from the previous stage" for a qualifier is operationally `(-difficulty, prior_initial_seed)` among the 8 advancers (all sharing a 3-win record). | Pattern 1, Pitfall 1 | LOW — directly from the rulebook tiebreak chain (W-L → Difficulty → initial seed). The 8 advancers' records differ only in losses (3-0/3-1/3-2); see Open Question 1 on whether losses sub-order the advancers. |
| A4 | Stage 2 is a normal Bo1-default Swiss stage (Bo3 only on advancement/elimination matches via the existing `_is_bo3`), NOT all-Bo3. | Pattern 2 | LOW — STATE.md/REQUIREMENTS assign all-Bo3 to Stage 3 (Phase 8, BO-01); Stage 2 uses the default path. Verified against the v3 phase map. |
| A5 | `invited` VRS data is provided to `seed_next_stage` as a list (from the fixture JSON or a constant); the function itself stays file-I/O-free. | Pattern 1 | LOW — the purity boundary is a design choice; the caller does the I/O. |

**If this table looks long:** every row is LOW-risk and concerns DATA (which teams/ratings) or a clearly-documented operational reading, not the verified algorithm or the verified merge rule. The load-bearing facts (merge rule, Buchholz definition, tiebreak chain) are VERIFIED, not assumed.

## Open Questions

1. **Do the qualifiers' loss records (3-0 vs 3-1 vs 3-2) sub-order them ABOVE Buchholz?**
   - What we know: The rulebook tiebreak chain is "W-L record → Difficulty Score → initial seed." All 8 advancers have 3 wins, but different losses (one 3-0, etc.). Strictly read, "W-L record" could mean a 3-0 team seeds above a 3-2 team *before* Buchholz is consulted.
   - What's unclear: Whether "final seed from the previous stage" collapses to pure Buchholz-order among advancers, or first buckets by losses (3-0 > 3-1 > 3-2) then Buchholz within each loss-bucket.
   - Recommendation: Implement the **full chain** `(losses_ascending, -difficulty, prior_seed)` for the qualifiers — this is the literal rulebook order (a 3-0 advancer outseeds a 3-2 advancer; ties within a loss-bucket break on Buchholz then initial seed). This is a SUPERSET of pure-Buchholz ordering and is the safer literal reading. Hold the exact behavior `[INFERRED]` + editable; reconcile against the official Stage-2 seed list when it posts (the seeds are editable anyway). Flag this explicitly in `/gsd-discuss-phase`. **This is the single design decision worth a human confirm before planning locks it.**

2. **Where does the invited VRS list live — in `data/stage2.json` or a separate constant?**
   - What we know: The fixture already carries a `teams` block; the invited 8 could live there (seeds 1-8) with qualifier placeholders (seeds 9-16), OR the invited list could be a separate `invited` JSON block the chain reads and merges.
   - What's unclear: Which is cleaner given the derived seeds overwrite 9-16.
   - Recommendation: Carry the invited 8 as the first 8 entries of `data/stage2.json` (`seeds_confirmed: false`), and have the auto-derive fill seeds 9-16 from the replay; the merge function takes the invited list + the replay finals. Either way honors the editable-`[INFERRED]` discipline. Claude's discretion.

3. **Should the derived seeds be WRITTEN to `data/stage2.json` or held as an in-session editable pre-fill?**
   - What we know: The results pre-fill pattern (Phase 6) holds fetched data in session and offers it as an editable overlay; it does not rewrite committed fixtures.
   - Recommendation: Mirror the results pre-fill — hold the derived seeds as an editable session overlay over the fixture, NOT a fixture rewrite (lower-risk, matches the shipped pattern, keeps the committed fixture as the `[INFERRED]` baseline). Claude's discretion; flag in discuss.

## Environment Availability

> Phase 7 has no NEW external dependencies. The Stage-1-finals input it consumes comes from the Phase-6 results seam (already built + tested on recorded fixtures; the live provider slugs are a carried event-time `/browse` verify, not a Phase-7 blocker). The chain itself is pure Python + the existing engine.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python ≥3.12 | all | ✓ | project pin | — |
| numpy | throwaway replay RNG | ✓ | 2.4.x (pinned) | — |
| `engine.probs` / `engine.swiss` / `engine.live` / `engine.teams` | the whole chain | ✓ | frozen v1.0 | — |
| `data/results_cache.json` (Stage-1 finals) | SEED-03 auto-derive | ✗ until fetched (or manual locks) | — | **Manual locking** — the user can lock Stage-1 finals by hand (the Phase-4 path); the chain derives from `KEY_LOCKED` regardless of source. First run needs no results source. |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** the fetched Stage-1 finals — falls back to manual lock entry (the existing Phase-4/6 contract). The seeding chain consumes `locked` whether it was fetched or hand-entered, so derivation works either way once Stage 1 is complete.

## Validation Architecture

> nyquist_validation is ENABLED (`config.json` workflow.nyquist_validation: true). This section maps every Phase-7 failure mode to the test/assertion that catches it, so VALIDATION.md derives directly.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (3.x-style asserts; numpy for RNG) |
| Config file | none — plain `tests/` discovery (no pytest.ini); `tests/conftest.py` exists for shared fixtures |
| Quick run command | `uv run pytest tests/test_seeding.py -x -q` (the new seeding module) |
| Full suite command | `uv run pytest -q` (147 baseline + new) |
| GATE-01 command | `uv run pytest tests/test_backtest_budapest_2025.py -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STG-02 | Stage 2 on frozen engine, Σ=2/8/2 | unit (invariant) | `uv run pytest tests/test_mc.py::test_stage2_invariants -x` | ❌ Wave 0 (mirror `test_invariants`) |
| STG-02 | No engine edit (freeze) | regression | `git diff --name-only <base> HEAD -- engine/swiss.py engine/montecarlo.py engine/teams.py` empty for the frozen funcs + `test_load_teams_unchanged` green | ✅ (`test_teams_load_stage.py::test_load_teams_unchanged`) |
| SEED-01 | Invited 1-8 / qualifiers 9-16 (not interleaved) | unit | `uv run pytest tests/test_seeding.py::test_invited_take_seeds_1_8_qualifiers_9_16 -x` | ❌ Wave 0 |
| SEED-01 | Buchholz via canonical `difficulty` (no 2nd copy) | unit (source guard) | `uv run pytest tests/test_seeding.py::test_buchholz_uses_canonical_difficulty -x` | ❌ Wave 0 |
| SEED-02 | **Two-run determinism (the gate)** | unit | `uv run pytest tests/test_seeding.py::test_seed_derivation_is_deterministic -x` | ❌ Wave 0 |
| SEED-02 | Documented tiebreak (hand-worked tie) | unit | `uv run pytest tests/test_seeding.py::test_qualifier_buchholz_tie_breaks_on_prior_seed -x` | ❌ Wave 0 |
| SEED-02 | Pure (no file I/O / no RNG / no streamlit import) | unit (source guard) | `uv run pytest tests/test_seeding.py::test_seeding_is_pure -x` (assert no `import streamlit/httpx/json/pathlib`, no `default_rng`) | ❌ Wave 0 |
| SEED-03 | Complete stage → seeds; partial → none | unit | `uv run pytest tests/test_seeding.py::test_partial_stage_yields_no_seeds -x` | ❌ Wave 0 |
| SEED-03 | Standings via full-lock replay (RNG-invariant) | unit | `uv run pytest tests/test_seeding.py::test_full_lock_replay_is_rng_invariant -x` (two RNG seeds → identical standings) | ❌ Wave 0 |
| (cross) | GATE-01 stays green | regression | `uv run pytest tests/test_backtest_budapest_2025.py -q` | ✅ (`test_backtest_budapest_2025.py`) |

### Failure Mode → Catching Assertion (for VALIDATION.md)
| Failure mode | Caught by |
|--------------|-----------|
| Non-deterministic seeds (dict/set order, equal Buchholz) | `test_seed_derivation_is_deterministic` (two-run byte-identical) + `test_qualifier_buchholz_tie_breaks_on_prior_seed` |
| Wrong merge (interleaved instead of separate) | `test_invited_take_seeds_1_8_qualifiers_9_16` |
| Buchholz re-implemented / `Σw` bug | `test_buchholz_uses_canonical_difficulty` (source guard) + the tie test (a `Σw` Buchholz orders ties differently) |
| Buchholz computed from flattened record (no opponents) | the tie test fails (difficulty() returns 0 / wrong) — and the chain consumes `{id: Team}`, asserted in the determinism fixture |
| Seeding off a partial/sampled stage | `test_partial_stage_yields_no_seeds` + `test_full_lock_replay_is_rng_invariant` |
| Off-by-one qualifier count (≠ 8) | derivation asserts exactly 8 advancers + `_validate_fixture_for_size` rejects a non-16 list (`test_load_stage_validates_against_declared_size` pattern) |
| Stage 2 broke the engine | `test_stage2_invariants` (Σ=2/8/2) + **GATE-01** (`test_backtest_budapest_2025`) + `test_load_teams_unchanged` |
| `[INFERRED]` banner dismissed wrong / missing on derived seeds | the per-stage banner is already tested (Phase 6 STG-05); add an AppTest asserting Stage-2 derived seeds carry `seeds_confirmed=false` and show the banner |

### The two-run determinism gate (SEED-02 — the phase's correctness gate)
Structure (mirrors `test_mc.py::test_reproducibility`): build a FIXED `prior_finals` (`{id: Team}` from a deterministic full-lock Stage-1 replay) and a FIXED `invited` list; call `seed_next_stage` twice; assert the two `[(seed, name, rating), ...]` lists are byte-identical AND the seed sequence is exactly `1..16`. Add a tie-specific variant (two equal-Buchholz qualifiers) asserting the documented `(... , prior_seed)` discriminator resolves them stably. Because the function is RNG-free and file-I/O-free, determinism reduces to "no reliance on iteration order" — the explicit tiebreak key is what makes the gate pass.

### The GATE-01 stay-green check (cross-cutting exit criterion)
Phase 7 touches NO engine file. The plan keeps GATE-01 green by construction:
1. `engine/seeding.py` is a NEW sibling — it imports `engine.probs.difficulty` and `engine.teams.Team` but edits nothing.
2. Stage 2 runs through the unchanged `simulate_stage` / `run_mc` (only `teams` differ).
3. The freeze is proven by running `tests/test_backtest_budapest_2025.py` (GATE-01) AND `test_load_teams_unchanged` after every task, plus a `git diff --name-only` over `engine/swiss.py`, `engine/montecarlo.py`, and the frozen `load_teams`/`_DEFAULT_FIXTURE`/`_validate_fixture` lines being empty.

### Wave 0 Gaps
- [ ] `tests/test_seeding.py` — NEW; covers SEED-01 (merge + canonical Buchholz), SEED-02 (determinism gate + tie + purity), SEED-03 (completeness + RNG-invariant replay).
- [ ] `tests/test_mc.py::test_stage2_invariants` (or a Stage-2 case in `test_app.py`) — STG-02 Σ=2/8/2 on the Stage-2 fixture.
- [ ] No framework install needed — pytest + numpy already in use; `tests/conftest.py` exists.
- [ ] Shared fixture helper: a deterministic `_build_finished_stage1_replay()` (a full-lock Stage-1 result) — put in `test_seeding.py` or `conftest.py`.

## Security Domain

> `security_enforcement` is not set in config.json (treated as enabled). Phase 7 has a minimal threat surface — a pure function + data wiring, no network, no auth, no new endpoints — but the input-validation row is load-bearing because corrupt seeds silently corrupt every downstream probability.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Single local desktop tool; no auth (out of scope). |
| V3 Session Management | no | No sessions beyond Streamlit's local state. |
| V4 Access Control | no | No multi-user. |
| V5 Input Validation | **yes** | Derived seeds round-trip the existing `_validate_fixture_for_size` loud-fail (16 unique seeds 1..16, finite ratings). The completeness gate (SEED-03) validates the prior stage is *finished* before deriving. Fetched Stage-1 results were already validated/joined in Phase 6 (slug-first, drop-on-unresolved). |
| V6 Cryptography | no | No crypto in this phase. |

### Known Threat Patterns
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed/derived fixture corrupts every Stage-2 pairing | Tampering | `_validate_fixture_for_size` loud-fail on the derived list; assert exactly 8 qualifiers + seeds 1..16 |
| Seeding off a partial/sampled stage (silent wrong seeds) | Tampering | Completeness gate (`LivePrefixIncomplete` reuse) — derive only from a full-lock finished stage |
| Fabricated lock from a bad team-name join feeding the chain | Spoofing/Tampering | Already mitigated upstream (Phase 6 slug-first join, drop-on-unresolved); the chain consumes only validated `locked` results |
| Non-determinism presenting false precision | Information disclosure (of confidence) | Two-run determinism gate (SEED-02) + `[INFERRED]` banner until reconciled |

## Sources

### Primary (HIGH confidence)
- **Valve Major Supplemental Rulebook** (`ValveSoftware/counter-strike_rules_and_regs`, `major-supplemental-rulebook.md`, raw GitHub) — the VERBATIM Stage-2/3 seeding rule ("invited = seeds 1-8, pre-event seed; advancing 8 = seeds 9-16, final seed from the previous stage"), the Difficulty Score definition ("sum of current wins minus sum of current losses for every opponent"), and the tiebreak chain ("Current W-L record → Difficulty Score → Initial seeding of the current stage").
- **engine/probs.py** (read directly) — canonical `difficulty()` Buchholz `Σ(opp.w − opp.l)` (line 64), `series`, `series_prob`, epistemic math.
- **engine/swiss.py** (read directly) — FROZEN `simulate_stage`, `rank_group` key `(-difficulty, seed)` (line 85), `build_round1_pairs`, the priority table, `pairings_out` observability seam.
- **engine/montecarlo.py** (read directly) — `run_mc`/`run_mc_progressive`, the Σ=2/8/2 sample structure, `_fresh_teams`.
- **engine/live.py** (read directly) — `LivePrefixIncomplete` (line 209), `legal_pairings_for_round` full-lock-prefix precondition, `derive_bracket` deterministic-replay trick.
- **engine/teams.py** (read directly) — `Team`, `load_stage`, `_validate_fixture_for_size`, frozen `load_teams`/`_DEFAULT_FIXTURE`.
- **scripts/fetch_results.py + ui/results_loader.py** (read directly) — the Phase-6 results seam producing the Stage-1 finals the chain consumes.
- **data/stage1.json, stage2.json, stage3.json, playoffs.json** (read directly) — fixture shape, `seeds_confirmed`, `[INFERRED]` handling.
- **tests/test_mc.py, test_swiss.py, test_backtest_budapest_2025.py, test_teams_load_stage.py** (read directly) — invariant + determinism + GATE-01 + freeze-regression test patterns to mirror.
- **.planning/research/ARCHITECTURE.md + PITFALLS.md** (v3 4-agent research, read directly) — the seeding-chain interface sketch and the determinism/tiebreak pitfall (Pitfall 3 owns the reproducibility guarantee).
- **.planning/phases/06-*/06-01-SUMMARY.md + 06-04-SUMMARY.md** (read directly) — what Phase 6 shipped (`load_stage`, `stage_id` cache key, results pre-fill via `validate_lock`).

### Secondary (MEDIUM confidence)
- **Wikipedia — IEM Cologne Major 2026** — independently confirmed the same merge rule: "Invited teams will be initially seeded according to their global Valve Regional Standing, while the eight teams qualified ... will be seeded according to their final Buchholz score"; NOT interleaved; final-standings tiebreak "win-loss record, then Buchholz, then initial seeding." Agrees with the Valve rulebook (cross-verification → HIGH for the rule).
- **WebSearch (egamersworld / esportsinsider / Liquipedia Majors)** — confirmed the 32-team VRS-invite format, MRQ removal (2025-06-09 rulebook update), Stage 2 = 8 invited + 8 Stage-1 qualifiers.

### Tertiary (LOW confidence — data, not algorithm)
- The *specific* Cologne 2026 Stage-2 invited team list + VRS ranks + ratings — not yet final/posted; held `[INFERRED]` + editable (A1/A2). The Liquipedia and Wikipedia pages did not enumerate a final Stage-2 invited 8 at fetch time. Reconcile via gstack `/browse` when Stages post (carried event-time verify).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; all engine modules read directly this session.
- Architecture (seeding chain): HIGH — the pure-function design is read from prior v3 research and matches the engine's own `rank_group` discipline; the merge rule is verbatim from Valve + cross-confirmed.
- Merge rule (SEED-01): HIGH — verbatim from the Valve supplemental rulebook, independently confirmed on Wikipedia.
- Pitfalls: HIGH — drawn from the v3 PITFALLS.md (which read the same frozen engine) + the verified rulebook tiebreak chain.
- Stage-2 reuse (STG-02): HIGH — Phase 6 already proved the engine is stage-agnostic + name-independent via `test_stage_switch_isolates_cache`.
- The one genuinely uncertain item is Open Question 1 (do advancer losses sub-order above Buchholz) — flagged for human confirm in discuss; the recommended literal reading is safe and the seeds are editable regardless.

**Research date:** 2026-06-05
**Valid until:** 2026-07-05 for the algorithm/engine facts (stable, frozen). The Cologne-specific invited list + seeds are event-time data — reconcile against the official Stage-2 seeding the moment it posts (Stage 2 games start ~2026-06-06).

## RESEARCH COMPLETE
