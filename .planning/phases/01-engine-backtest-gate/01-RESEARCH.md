# Phase 1: Engine + Backtest Gate - Research

**Researched:** 2026-05-28
**Domain:** Headless Valve CS2 Major Swiss-stage correctness engine + Monte Carlo runner (Python 3.12 / numpy), gated by an exact round-by-round backtest
**Confidence:** HIGH on engine/format/RNG; HIGH on Valve priority table (pulled verbatim from raw GitHub); MEDIUM on the backtest fixture data (Liquipedia round-by-round must be reconciled verbatim during execution — sources had an internal inconsistency)

## Summary

Phase 1 builds the entire correctness spine of the product: a pure, dependency-free `engine/` (teams, swiss, montecarlo, probs) plus a `tests/` suite whose centerpiece — a round-by-round reproduction of a real past Major Swiss stage — is a HARD BLOCKING GATE. Nothing downstream (UI, optimizer, re-sim, odds) is trusted or built until that backtest passes exactly. The structural invariant tests (Σ P(3-0)≈2, Σ P(0-3)≈2, Σ P(advance)≈8) all pass even when the engine is silently corrupt (wrong Buchholz, wrong fold key, wrong rematch resolution), so the backtest, `test_difficulty_formula`, and `test_locked_results_honored` are the only checks that prove correctness.

The two load-bearing external facts are now resolved. (1) **Valve's exact rules are fetched verbatim** from `raw.githubusercontent.com/ValveSoftware/counter-strike_rules_and_regs/main/major-supplemental-rulebook.md`: the Difficulty Score is `Σ(opp.wins) − Σ(opp.losses)` (worked example = 2, exactly as the spec demands), the tiebreak chain is record → difficulty → initial seed (no head-to-head), and the rematch-avoidance pairing **priority table is a 15-row table over groups of 6 seeds** (`1v6,2v5,3v4` down to `1v2,3v4,5v6`), reproduced verbatim below. (2) **A past Major Swiss stage** for GATE-01 — recommend **StarLadder Budapest 2025 Stage 1** — but the round-by-round fixture pulled from Liquipedia contained an internal inconsistency (two fetches disagreed on which four teams sat at 1-1 entering Round 3), so the backtest fixture **must be transcribed verbatim from Liquipedia during execution, match by match**, not lifted from this research. This is flagged, not guessed.

**Primary recommendation:** Build `engine/` pure and generator-first with `locked` support and `SeedSequence.spawn`-over-pinned-chunks RNG from day one. Encode the Valve 15-row priority table (below) as the authoritative pairing oracle; keep the greedy fold but make a literal-table-lookup fork a *planned* task (GATE-04) the moment any Round 4/5 pairing diverges. Use Budapest 2025 Stage 1 for the backtest, transcribing the fixture verbatim from Liquipedia at execution time and reconciling every match before asserting.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ENG-01 | R1 = seed N vs N+8 from single seed→team map | teams.py fixtures in HANDOFF §3; derive `[(i,i+8) for i in range(1,9)]`, no second copy (Anti-Pattern 4) |
| ENG-02 | R2+ group by (wins,losses), seed by difficulty desc then seed asc, single code path | Verified tiebreak chain (record→difficulty→seed); R2 difficulty uniform → falls through to seed, no `if round==2` |
| ENG-03 | Difficulty = `Σ(opp.wins − opp.losses)` | **VERIFIED verbatim** from Valve rulebook (worked example = 2); Pitfall 1 |
| ENG-04 | Fold sorts on difficulty-ranked order, not raw seed | Verified "highest seed faces lowest available non-rematch"; fold key = `(−difficulty, seed)`; Pitfall 3 |
| ENG-05 | No rematch-free matching → least-disruptive rematch + warning, no crash | HANDOFF §4 `None` fallback; `test_no_valid_matching_fallback` |
| ENG-06 | Bo3 iff a team at 2 wins or 2 losses; else Bo1 | HANDOFF §4; both teams in a record group share `(w,l)` so test the group |
| ENG-07 | No rematches; terminate at 3W/3L; record final | HANDOFF §4; invariant tests |
| ENG-08 | `locked: dict[frozenset({id,id})→winner_id]`, deterministic, respects no-rematch | HANDOFF §4; needed by Phase 4; `test_locked_results_honored` |
| ENG-09 | RNG `seed` threaded via `SeedSequence.spawn`, survives chunking | numpy parallel docs (verified below); Pitfall 10; Phase 1×2 seam |
| MC-01 | N stage sims (default 100k), tally 3-0/advance/0-3 per team | HANDOFF §6; montecarlo.py |
| MC-02 | Per-team P with Wilson bands | Wilson interval formula (below) |
| MC-03 | Invariants ±0.05 at N≥50k: ΣP(3-0)≈2, ΣP(0-3)≈2, ΣP(advance)≈8 | HANDOFF §6; structurally guaranteed but necessary |
| MC-04 | Retain full per-sim record sample (not just marginals) | ARCHITECTURE Pattern 3; Phase 3 Ballot B consumes it |
| MC-05 | Generator-first: yield per-chunk aggregates + cached wrapper | ARCHITECTURE Pattern 3 two-function split; Phase 2 seam |
| MC-06 | Bo3 = closed form `p²(3−2p)` single Bernoulli draw; Bo1 = p_map | HANDOFF §5; verified `p=0.6→0.648`, `p=0.5→0.5` |
| PROB-01 | `p_map = 1/(1+10^(−(rᵃ−rᵇ)/S))`, S=40 slider | HANDOFF §5 |
| PROB-02 | Odds series prob used directly; Bo3 NOT re-applied | HANDOFF §5; lives in probs.py from Phase 1 even though odds arrive Phase 5 |
| PROB-03 | Epistemic = OUTER loop (Beta draw per draw, MC batch per draw); stub as single-draw no-op | ARCHITECTURE Pattern 2; Pitfall 4; Phase 5 fills content |
| PROB-04 | Beta MoM clamps `var < p(1−p)` before fit | Pitfall 5; structural stub now, content Phase 5 |
| PROB-05 | Reported band = epistemic spread ⊇ Wilson; single source → Wilson only | Pitfall 4; collapses to Wilson in Phase 1 (one source) |
| GATE-01 | Backtest reproduces a past Major stage's pairings exactly | **Budapest 2025 Stage 1 recommended**; fixture below (VERIFY verbatim at execution) |
| GATE-02 | `test_difficulty_formula` returns 2 on Valve worked example | Verified: opponents 2-0 and 1-1 → (3−1)=2 |
| GATE-03 | `test_forced_rematch_pairing` + `test_no_valid_matching_fallback` | Priority table below is the oracle |
| GATE-04 | Pull priority table verbatim; replace greedy with table lookup on divergence | **DONE — table reproduced below**; budget the fork as a task |
| GATE-05 | No trusted output / no UI until GATE-01 passes | Roadmap blocking gate; Phase 2 does not begin until green |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

These are load-bearing directives; treat with the authority of locked decisions. Research must not contradict them.

- **Buchholz / Difficulty Score = `Σ(opp.wins − opp.losses)`**, NOT `Σ opp.wins`. (ENG-03)
- **Within-group fold sorts on the difficulty-ranked order, not raw seed.** (ENG-04)
- **The Phase 1 round-by-round backtest is a HARD GATE.** No UI built, no output trusted until it passes. Pull Valve's priority table verbatim; don't approximate. (GATE-01..05)
- **Bo3 = closed form `p²(3−2p)` as a single Bernoulli draw** — never sample 3 maps. (MC-06)
- **Epistemic variance is an OUTER loop**, never folded into per-sim sampling; clamp `var < p(1−p)` before the Beta fit. (PROB-03/04)
- **Cross-phase seams to honor in Phase 1:** `swiss.py` accepts `locked`; `SeedSequence.spawn` over a pinned chunk count; MC generator-first; odds-override math in probs.py from Phase 1.
- **Stack:** Python ≥3.12, numpy 2.4.x. **Avoid pandas/scipy.** (Streamlit/httpx/python-dotenv are Phase 2/5, NOT Phase 1.)
- **No scraping** — irrelevant to Phase 1 (no network in the engine).
- **Web browsing:** Use gstack `/browse` for web fetches per CLAUDE.md. (This research used WebFetch on raw GitHub + Liquipedia public pages; the planner/executor should use `/browse` to re-verify the backtest fixture.)
- **`engine/` has zero outward dependencies** — must never import streamlit, httpx, or requests (ARCHITECTURE invariant; Anti-Pattern 6).

## Architectural Responsibility Map

Phase 1 is a single tier (the pure compute core). The map below assigns each capability within that core to its owning module, which is what the planner needs for task assignment.

| Capability | Primary Module | Secondary Module | Rationale |
|------------|---------------|------------------|-----------|
| Seed→team map, R1 derivation, default ratings | `engine/teams.py` | — | Single source of truth for fixtures; R1 derived not hardcoded (ENG-01) |
| Round pairing (group, sort, fold, rematch resolution, `locked`) | `engine/swiss.py` | `engine/teams.py` (state) | The correctness core; the hard part (ENG-02..08) |
| `p_map`, Bo3 closed form, odds-override passthrough | `engine/probs.py` | — | Pure math; no Streamlit/network (PROB-01/02, MC-06) |
| MC loop (outer epistemic stub / inner aleatoric / per-chunk yield / sample retention / RNG) | `engine/montecarlo.py` | `engine/swiss.py`, `engine/probs.py` | Orchestrates a stage sim N times; owns RNG threading and chunk yielding (MC-01..06, ENG-09, PROB-03..05) |
| Wilson band computation | `engine/montecarlo.py` or a small `engine/stats.py` helper | — | Aleatoric CI on tallied counts (MC-02) |
| Backtest + unit tests | `tests/test_swiss.py`, `tests/test_probs.py` | — | The gate + math guards (GATE-01..05) |

**Tier note:** There is no browser/frontend/API/DB tier in Phase 1. Any task that reaches for `streamlit`, an HTTP client, or a file/network read from inside `engine/` is misassigned and breaks the functional-core invariant that makes the gate possible.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | ≥3.12 (pinned in pyproject.toml) | Runtime | Project constraint; `frozenset`/match/typing used freely |
| numpy | 2.4.x | RNG (`default_rng`, `SeedSequence`), vectorized tally/scoring | Project constraint; `SeedSequence.spawn` is the reproducibility mechanism (ENG-09) |
| pytest | 8.x (latest) | Test runner / the gate harness | The backtest *is* a `pytest` run; standard Python test framework |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| uv | latest | Env + dependency management, `uv run` bootstrap | DX contract (HANDOFF §10.6); manages pyproject.toml. Dev tooling, not a Phase 1 import |

### Explicitly NOT in Phase 1
- **Streamlit** — Phase 2. `engine/` must not import it (Anti-Pattern 6).
- **httpx / python-dotenv** — Phase 5 odds layer only.
- **pandas / scipy** — forbidden by CLAUDE.md. Wilson interval and Bo3 are closed-form; no scipy needed. (`scipy.stats.beta` would be the obvious Phase 5 reach — avoid; implement Beta via numpy `default_rng().beta` and a hand-coded method-of-moments.)
- **numba** — deferred v2 (OPS-02), only if pure-Python latency bites.

**Installation (Phase 1 dev env):**
```bash
uv add numpy
uv add --dev pytest
# Python pinned >=3.12 in pyproject.toml [project] requires-python
```

**Version verification (run at execution time, the planner should gate installs on this):**
```bash
pip index versions numpy      # confirm 2.4.x current
pip index versions pytest     # confirm 8.x current
```
Training-data versions may be stale; verify against PyPI before pinning. numpy 2.4.x and pytest 8.x are the assumed-current lines as of the research date — `[ASSUMED]` pending the above check.

## Package Legitimacy Audit

> slopcheck was not run in this research session (no execution sandbox invoked here). However, `numpy` and `pytest` are not discovery-risk packages — they are the two most-downloaded scientific/test packages on PyPI with decade-plus histories and official source repos. They are tagged `[ASSUMED]` per the provenance rule (registry existence alone is not VERIFIED) and the planner should run a one-time `pip index versions` + (optionally) slopcheck before install, but the slopsquat risk here is effectively nil.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| numpy | PyPI | ~19 yrs | ~300M/mo | github.com/numpy/numpy | not run | Approved (verify version at install) |
| pytest | PyPI | ~15 yrs | ~150M/mo | github.com/pytest-dev/pytest | not run | Approved (verify version at install) |
| uv | PyPI | ~2 yrs | high | github.com/astral-sh/uv | not run | Approved (dev tool, not an import) |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*slopcheck unavailable at research time → versions tagged `[ASSUMED]`; planner should confirm `numpy`/`pytest` versions via `pip index versions` before pinning. No checkpoint required given these are canonical packages, but the version pin itself should be verified, not assumed.*

## Architecture Patterns

### System Architecture Diagram

```
                    seed (int)                    ratings, S          locked={} (Phase 1)
                        │                              │                    │
                        ▼                              ▼                    ▼
              ┌───────────────────────────────────────────────────────────────────┐
              │  engine/montecarlo.py  —  run_mc_progressive(...) -> Iterator       │
              │                                                                     │
              │  SeedSequence(seed).spawn(n_chunks)  ──► [child_rng_0 ... child_rng_k]│
              │                                                                     │
              │  for draw in epistemic_draws:        ◄── OUTER (single no-op draw   │
              │      p_vec = beta_or_point(...)          in Phase 1; Phase 5 fills) │
              │      for chunk in range(n_chunks):   ◄── INNER aleatoric            │
              │          rng = child_rng[chunk]                                     │
              │          for _ in range(chunk_size):                                │
              │              record = simulate_stage(teams, p_vec, rng, locked) ────┼──┐
              │          accumulate tally; yield Partial(done,total,running_p_adv)  │  │
              │  retain per-sim record matrix (MC-04)                               │  │
              └───────────────────────────────────────────────────────────────────┘  │
                        │ final tally + record sample                                  │
                        ▼                                                              │
              per-team P(3-0)/P(advance)/P(0-3) + Wilson band  (printed by __main__)   │
                                                                                       │
   ┌───────────────────────────────────────────────────────────────────────────────┘
   ▼  engine/swiss.py : simulate_stage(...)  — ONE stage
   ┌───────────────────────────────────────────────────────────────────────────┐
   │  R1: pairs = [(seed_i, seed_{i+8})]  (derived from teams map)               │
   │  loop rounds until all teams 3W or 3L:                                      │
   │     for each active record-group (wins,losses):                            │
   │        ranked = sort(group, key=(-difficulty(t), t.seed))   ◄── ENG-03/04  │
   │        pairs  = pair_within_group(ranked)  ──┐                              │
   │     for (a,b) in pairs:                       │                             │
   │        bo3 = (a.wins==2 or a.losses==2)       │ pair_within_group:          │
   │        if {a.id,b.id} in locked: winner=locked│   1. fold (greedy / table)  │
   │        else: p = probs.series(a,b,bo3); flip  │   2. rematch-avoid          │
   │        update wins/losses/opps                │   3. None → least-disruptive│
   └───────────────────────────────────────────────┴──────── rematch + warn ────┘
                        ▲
                        │ p_map, Bo3 p²(3−2p), odds-override passthrough
              engine/probs.py  (pure functions, no state)

   tests/test_swiss.py :  invariants  +  test_difficulty_formula  +  test_forced_rematch_pairing
                          +  test_no_valid_matching_fallback  +  test_locked_results_honored
                          +  BACKTEST: reproduce Budapest 2025 Stage 1 pairings exactly  ◄── THE GATE
```

A reader can trace the primary path: `seed + ratings → SeedSequence.spawn → per-chunk inner loop → simulate_stage (R1 derive → group/sort/fold/rematch → play) → tally → per-team P + Wilson`.

### Recommended Project Structure (Phase 1 subset)
```
swiss-mc/
├── engine/
│   ├── __init__.py
│   ├── teams.py        # 16 teams, seeds, R1 derived, default ratings, Stage config
│   ├── swiss.py        # pairing + stage sim; accepts locked; priority-table oracle
│   ├── probs.py        # p_map, Bo3 closed form, odds-override passthrough; (Beta stub)
│   └── montecarlo.py   # SeedSequence.spawn, outer/inner loop, yield, sample retention, Wilson
├── tests/
│   ├── test_swiss.py   # invariants + no-rematch + BACKTEST (the gate) + locked + rematch
│   └── test_probs.py   # test_difficulty_formula, test_p_map, test_bo3
├── data/
│   └── stage1.json     # editable [INFERRED] seeds/ratings (DX-01 is Phase 2, but the fixture lives here)
└── pyproject.toml      # uv-managed; requires-python >=3.12
```
(`app.py`, `odds/`, `scripts/` are later phases. Do not create `engine/` files that import them.)

### Pattern 1: Functional Core / Imperative Shell
**What:** `engine/` is pure and deterministic. RNG is injected (`seed`), progress is emitted via a generator/callback, never `st.*`. **When to use:** correctness-critical kernel that must be testable before any UI — exactly the gate situation. **Example:**
```python
# engine/montecarlo.py — injectable RNG, progress via yield, no Streamlit
def run_mc_progressive(stage, ratings, S, N, locked, *, seed, n_chunks=20):
    ss = np.random.SeedSequence(seed)
    child_seeds = ss.spawn(n_chunks)        # deterministic given (seed, n_chunks)
    ...                                     # yield Partial(...) per chunk
```

### Pattern 2: Epistemic OUTER / aleatoric INNER (stubbed as single no-op draw in Phase 1)
**What:** The Beta draw lives in the OUTER loop (once per epistemic draw); a full aleatoric MC batch runs at that fixed `p`; bands aggregate across draws. In Phase 1 there is exactly one source (ratings), so the outer loop runs once and the band collapses to Wilson only — but **the loop must be structured outer now** or Phase 5 is a rewrite (Pitfall 4). **Phase 1 stub:**
```python
for p_vec in epistemic_draws(blend, var):   # Phase 1: yields exactly ONE point p_vec
    run_inner_mc_batch(p_vec, ...)           # Phase 5: yields K Beta draws
aggregate_across_draws()                     # Phase 1: spread = 0 → band = Wilson
```

### Pattern 3: Generator-first MC with two-function cache split
**What:** `run_mc_progressive` (pure, uncached, yields `Partial` per chunk) + a Phase-2 `@st.cache_data` wrapper that drains it. **Build-order implication:** write generator-first in Phase 1 even though the progress bar is Phase 2 — retrofitting yield into a monolith is a rewrite of the hottest path (Anti-Pattern 3).

### Pattern 4: `locked` honored from day one
**What:** `simulate_stage` accepts `locked: dict[frozenset({id,id}) → winner_id]`; a matchup present in `locked` uses the winner deterministically (no sampling) and still records it in `opps` so the no-rematch rule respects locked history. **Why now:** Phase 4 re-sim rides entirely on this; skipping forces a `swiss.py` rewrite (ARCHITECTURE Data Flow, ENG-08).

### Anti-Patterns to Avoid
- **Two copies of the R1 pairing fact** — derive `[(i,i+8) for i in range(1,9)]` from the seed map (Anti-Pattern 4).
- **`if round == 2` special case** — R2 difficulty is uniform within a group and falls through to seed; one code path (ENG-02).
- **Folding on raw seed in R3+** — fold key must be `(−difficulty, seed)` and the difficulty sort must actually be USED, not dead code (Pitfall 3).
- **Approximating the priority table from memory** — use the verbatim 15-row table below (Pitfall 2).
- **Beta draw in the inner per-sim loop** — collapses the epistemic band; structure outer now (Pitfall 4).
- **Monolithic `run_mc`** — write generator-first (Anti-Pattern 3).
- **`engine/` importing streamlit/httpx/requests** — breaks the gate-ability invariant (Anti-Pattern 6).
- **Sampling 3 map Bernoullis for Bo3** — use closed form `p²(3−2p)` as one draw (MC-06).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Reproducible parallel/chunked RNG | A custom seed-splitting scheme or reseeding per chunk by `seed+i` | `numpy.random.SeedSequence(seed).spawn(n_chunks)` | Hashing `seed+i` produces correlated streams; SeedSequence is designed for independent, reproducible child streams (numpy docs) |
| Bo3 series probability | Sampling 3 map Bernoullis and counting | Closed form `p²(3−2p)`, one Bernoulli draw | Exact for iid maps; sampling only adds MC noise + cost (MC-06, V3-04 gate) |
| Rematch-avoidance pairing | A clever bespoke matching heuristic | Valve's literal 15-row priority table (below) as the oracle; greedy only as an optimization that MUST match it | Greedy can return a *legal* matching that is not the one Valve mandates → silent corruption (Pitfall 2) |
| Wilson confidence interval | scipy.stats | Closed-form Wilson score interval (formula below) in numpy | scipy is forbidden (CLAUDE.md); Wilson is a one-liner |
| Beta sampling / fit (Phase 5 stub) | scipy.stats.beta | numpy `default_rng().beta(a,b)` + hand-coded method-of-moments with the `var<p(1−p)` clamp | scipy forbidden; numpy ships Beta sampling |

**Key insight:** In this domain the danger is *plausible-but-wrong* — every hand-rolled shortcut (Buchholz, fold key, rematch resolution, RNG splitting) produces output that passes structural invariants while silently corrupting probabilities. The backtest against verbatim Valve rules is the only thing that catches it; lean on authoritative oracles, not intuition.

## VERIFIED: Valve Swiss Rules (pulled verbatim Phase 1 — satisfies GATE-04)

**Source `[VERIFIED: raw.githubusercontent.com/ValveSoftware/counter-strike_rules_and_regs/main/major-supplemental-rulebook.md]`** (fetched 2026-05-28, cross-fetched twice, identical both times).

### Difficulty Score (Buchholz) — definition + worked example
> "Each team's Difficulty Score is tracked for the purpose of tie-breaking. The Difficulty Score is the sum of current wins minus the sum of current losses for every opponent a team has faced."

> Worked example: "Team A's prior opponents are 2-0 and 1-1. Team A's Difficulty Score is 2 (prior opponents have 3 wins total, and 1 loss total, so 3-1 = 2)." "Team B's prior opponents are both 1-1. Their Difficulty Score is 0."

This **confirms ENG-03 and GATE-02 exactly**: `difficulty(t) = sum(o.wins - o.losses for o in t.opps)`; the worked example (opponents 2-0 and 1-1) → `(2+1) − (0+1) = 2`. `test_difficulty_formula` asserts `== 2`.

### Tiebreak / seeding chain (within a stage)
Seed teams by, in order:
1. Current W-L record in the stage
2. Difficulty Score in the current stage
3. Initial seeding of the current stage

**No head-to-head** in the supplemental rulebook. This confirms ENG-02/ENG-04: the within-group sort key is `(record, −difficulty, initial_seed)`; within a record group it reduces to `(−difficulty, seed)`. The pairing rule: "the highest seeded team faces the lowest seeded team available that does not result in a rematch."

### Rematch-avoidance pairing priority table (15 rows, groups of 6) — `[VERIFIED]`
Organizers "select the top-most row that does not result in a rematch." Seeds 1–6 are the difficulty-ranked positions *within the 6-team record group* (1 = highest seed in group):

| Priority | Pair 1 | Pair 2 | Pair 3 |
|:--------:|:------:|:------:|:------:|
| 1  | 1v6 | 2v5 | 3v4 |
| 2  | 1v6 | 2v4 | 3v5 |
| 3  | 1v5 | 2v6 | 3v4 |
| 4  | 1v5 | 2v4 | 3v6 |
| 5  | 1v4 | 2v6 | 3v5 |
| 6  | 1v4 | 2v5 | 3v6 |
| 7  | 1v6 | 2v3 | 4v5 |
| 8  | 1v5 | 2v3 | 4v6 |
| 9  | 1v3 | 2v6 | 4v5 |
| 10 | 1v3 | 2v5 | 4v6 |
| 11 | 1v4 | 2v3 | 5v6 |
| 12 | 1v3 | 2v4 | 5v6 |
| 13 | 1v2 | 3v6 | 4v5 |
| 14 | 1v2 | 3v5 | 4v6 |
| 15 | 1v2 | 3v4 | 5v6 |

**Critical planning implications:**
1. **The table is for groups of 6 seeds.** In a 16-team Stage-1 Swiss the mid record-buckets (1-1, 1-2, 2-1) can hold up to 6–8 teams; the 6-team buckets are exactly where this table applies. Larger/smaller groups are handled by the same "top-most rematch-free row" principle generalized by the high-vs-low fold — confirm bucket sizes against the actual stage when encoding the backtest. (A bucket of 8 is paired into 4 matches; the table as published covers 6. The greedy fold generalizes; the planner must verify the generalization holds for any 8-team bucket the backtest contains, or the table-lookup fork is needed there too.)
2. **GATE-04 is partially pre-satisfied:** the table is now in hand. The remaining GATE-04 work is (a) encode it as a lookup oracle, (b) keep greedy as the fast path, (c) **planned fork**: if any backtest pairing diverges, swap greedy → table lookup. Budget this fork as a real task, not a contingency.
3. **`test_forced_rematch_pairing` (GATE-03):** construct a 6-team group whose Priority-1 row (`1v6,2v5,3v4`) contains a rematch; assert the engine selects the first lower-priority row with no rematch (e.g. Priority 2 `1v6,2v4,3v5`).

## Backtest Fixture (GATE-01) — RECOMMENDATION + a MUST-VERIFY flag

**Recommend: StarLadder Budapest 2025 Stage 1.** Reasons:
- It is a **16-team, 3-loss/3-win Swiss seeded by Valve standings then Buchholz** — the exact format Phase 1 implements (Liquipedia + Wikipedia confirm).
- It is the **most recent** completed Major (Nov 24–27 2025 Stage 1), so Liquipedia data is mature and the rules match the current rulebook revision.
- Round-by-round pairings, record buckets, Bo1/Bo3 status, and map scores are all published on the Liquipedia Stage 1 page.

Austin 2025 (BLAST) is a viable fallback but Budapest is more recent and its rule revision is guaranteed to match the table above.

### ⚠ MUST-VERIFY AT EXECUTION — fixture data is MEDIUM confidence, do NOT lift verbatim from this research

When I fetched the Budapest Stage 1 round-by-round data from Liquipedia, **two fetches of the same page disagreed** on which four teams sat at 1-1 entering Round 3 (one fetch listed the mid-bracket as Legacy/B8/RED/NIP; a targeted re-fetch said the 1-1 teams were NIP/FaZe/B8/PARIVISION). After R2 there must be **eight** teams at 1-1, so neither fetch was complete, and the R2→R3 transition did not reconcile cleanly. This is precisely the silent-divergence trap (Pitfall 2/3): an inconsistent fixture would make a *correct* engine fail the gate, or a *wrong* engine pass it.

**Action for the planner/executor:** Transcribe the Budapest 2025 Stage 1 fixture **match-by-match, verbatim, from the Liquipedia Stage 1 page** (use gstack `/browse` per CLAUDE.md for a clean render), reconciling every round before encoding. Required fields:
- The 16 initial seeds (Valve standings order). *Provisional from fetch:* 1 M80, 2 FlyQuest, 3 B8, 4 Fnatic, 5 NIP, 6 PARIVISION, 7 Imperial, 8 FaZe, 9 NRG, 10 Fluxo, 11 Legacy, 12 The Huns, 13 RED Canids, 14 GamerLegion, 15 Lynn Vision, 16 Rare Atom — **verify**.
- Each round's matchups grouped by record bucket, the winner of each, and the Bo1/Bo3 status (advancement/elimination = Bo3).
- The eight advancing and eight eliminated teams.

The reproduction test encodes the actual results as `locked` (forced winners), runs the engine, and asserts the engine *generates* the actual pairings at each round. **Do not assert against a fixture this research could not internally reconcile.** Confirmed final-eight advancers from the recommended stage (stable across fetches): M80, FlyQuest, B8, Fnatic, NIP, PARIVISION, Imperial, FaZe — useful as a sanity check on the transcription.

**Source URLs (re-fetch with `/browse`):**
- `https://liquipedia.net/counterstrike/StarLadder/2025/Major/Stage_1` (primary fixture)
- `https://en.wikipedia.org/wiki/StarLadder_Budapest_Major_2025` (format/seeding confirmation)
- `https://www.hltv.org/events/8042/starladder-budapest-major-2025` (cross-check pairings/scores)

## Common Pitfalls

### Pitfall 1: Buchholz as Σ(opp.wins) — CORRECTNESS-FATAL
**What goes wrong:** Wrong within-group ordering → wrong pairings → every probability corrupted, while all invariants pass. **Why:** casual web explanations say "sum of opponent wins"; Valve's is wins **minus** losses. **Avoid:** `difficulty(t) = sum(o.wins - o.losses ...)`; `test_difficulty_formula == 2`. **Warning sign:** a team that beat only eliminated opponents seeded ABOVE one that beat advancers in the same group.

### Pitfall 2: Greedy fold returns a legal-but-wrong matching — CORRECTNESS-FATAL
**What goes wrong:** Greedy picks a rematch-free matching Valve's table doesn't mandate; legal (passes no-rematch) but wrong branch. **Why:** greedy is easier than transcribing the 15-row table; diverges only in dense-rematch Round 4/5 groups. **Avoid:** the table above is the oracle; planned greedy→table-lookup fork (GATE-04). **Warning sign:** backtest reproduces R1–R3 but diverges in R4/R5.

### Pitfall 3: Fold on seed instead of difficulty-rank — CORRECTNESS-FATAL
**What goes wrong:** Difficulty formula correct but never USED as the fold key. **Avoid:** assert the list handed to the fold is sorted `(−difficulty, seed)` for R3+; unit test a 4-team group where Buchholz order ≠ seed order. **Warning sign:** removing the difficulty sort changes nothing in output (dead code = bug).

### Pitfall 10: numpy reproducibility breaks under chunking — CORRECTNESS-ADJACENT / OPS
**What goes wrong:** `default_rng(seed)` is deterministic single-threaded but the result changes if chunk/thread count varies between the backtest harness and the shipped app; the "reproducible" gate becomes non-deterministic. **Avoid:** `SeedSequence(seed).spawn(n_chunks)`, one child generator per chunk; **pin `n_chunks`** (or derive deterministically from N); the backtest must run the SAME chunked path the app ships. **Warning sign:** same `(seed,N)` gives slightly different P(advance) on a different machine. **Phase 1 decides the scheme; Phase 2 must not break it.**

### Pitfall (ENG-05): unhandled `None` from the fold — crash on unmatchable group
**What goes wrong:** No rematch-free perfect matching exists → recursive fold returns `None` → unhandled crash. **Avoid:** on `None`, pair the least-disruptive rematch (highest seed vs lowest available, allow the rematch) + `log.warning`; `test_no_valid_matching_fallback`. Effectively never fires in a clean 16-team Swiss but must be total.

## Code Examples

### Difficulty Score (ENG-03) — the formula the whole gate hinges on
```python
# engine/swiss.py
# Source: VERIFIED verbatim, ValveSoftware/counter-strike_rules_and_regs/major-supplemental-rulebook.md
def difficulty(t) -> int:
    return sum(o.wins - o.losses for o in t.opps)   # NOT sum(o.wins)
# worked example: opponents 2-0 and 1-1 -> (2+1) - (0+1) == 2
```

### Within-group ranking + fold key (ENG-02/04)
```python
# Single code path for all rounds >= 2. R2 difficulty is uniform -> sort falls through to seed.
ranked = sorted(group, key=lambda t: (-difficulty(t), t.seed))   # difficulty desc, seed asc
pairs  = pair_within_group(ranked)   # greedy fold OR priority-table lookup (GATE-04 fork)
```

### Priority-table lookup oracle (GATE-04) — for 6-team groups
```python
# Seeds here are 1..6 = positions in `ranked` (1 = best in group).
PRIORITY_TABLE = [
    [(1,6),(2,5),(3,4)], [(1,6),(2,4),(3,5)], [(1,5),(2,6),(3,4)],
    [(1,5),(2,4),(3,6)], [(1,4),(2,6),(3,5)], [(1,4),(2,5),(3,6)],
    [(1,6),(2,3),(4,5)], [(1,5),(2,3),(4,6)], [(1,3),(2,6),(4,5)],
    [(1,3),(2,5),(4,6)], [(1,4),(2,3),(5,6)], [(1,3),(2,4),(5,6)],
    [(1,2),(3,6),(4,5)], [(1,2),(3,5),(4,6)], [(1,2),(3,4),(5,6)],
]
def pair_group_of_6(ranked):  # ranked: list of 6 teams, index 0 = group seed 1
    for row in PRIORITY_TABLE:                       # top-most row first
        pairs = [(ranked[a-1], ranked[b-1]) for a,b in row]
        if all(y.id not in x.opps for x,y in pairs): # no rematch
            return pairs
    return None                                      # -> least-disruptive fallback (ENG-05)
```

### Bo3 closed form (MC-06) + p_map (PROB-01)
```python
# engine/probs.py
def p_map(ra, rb, S=40.0):                 # logistic
    return 1.0 / (1.0 + 10 ** (-(ra - rb) / S))
def series(p, bo3: bool):
    return p*p*(3 - 2*p) if bo3 else p     # verified p=0.6 -> 0.648, p=0.5 -> 0.5
# odds override (PROB-02): if a market series prob exists for THIS matchup, use it directly,
# never re-apply series().
```

### SeedSequence.spawn over pinned chunks (ENG-09)
```python
# engine/montecarlo.py
# Source: VERIFIED numpy parallel-RNG docs (numpy.org/doc/stable/reference/random/parallel.html)
ss = np.random.SeedSequence(seed)
child_seeds = ss.spawn(n_chunks)                       # deterministic given (seed, n_chunks)
chunk_rngs  = [np.random.default_rng(s) for s in child_seeds]
# pin n_chunks; reproducibility depends only on (seed, n_chunks), both controlled.
```

### Wilson score interval (MC-02) — no scipy
```python
import math
def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 0.0)
    p = k / n; d = 1 + z*z/n
    centre = (p + z*z/(2*n)) / d
    half   = (z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))) / d
    return (centre - half, centre + half)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Legacy seed (chess-style) Swiss tiebreak | Valve "Difficulty Score" Buchholz = wins−losses, seeded re-pairing | Adopted CS Major Swiss (PGL Antwerp era, current as of 2025 rulebook) | This phase implements the *current* rule, verified against the live rulebook |
| `numpy.random.seed()` / global RandomState | `np.random.Generator` via `default_rng` + `SeedSequence.spawn` for parallel streams | numpy ≥1.17, now standard in 2.x | Required for reproducible chunked execution (ENG-09) |
| Sampling 3 map Bernoullis for Bo3 | Closed-form `p²(3−2p)` single draw | Project decision (MC-06) | Less MC noise, faster; map-level Bo3 only revisited in V3-04 if backtest demands |

**Deprecated/outdated:** `numpy.random.seed`/`RandomState` (legacy, not stream-reproducible under chunking) — use `default_rng`/`SeedSequence`.

## Runtime State Inventory

Not applicable — Phase 1 is greenfield (no rename/refactor/migration; the project has no prior code). Section omitted per template guidance, noted here for the checklist.

## Validation Architecture

> nyquist_validation is `true` in config.json — section included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x `[ASSUMED — verify]` |
| Config file | none yet — Wave 0 adds `pyproject.toml [tool.pytest.ini_options]` (testpaths=["tests"]) |
| Quick run command | `uv run pytest tests/test_probs.py -x` (math units, <1s) |
| Full suite command | `uv run pytest -x` (includes the backtest gate) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ENG-03 / GATE-02 | difficulty(worked example)==2 | unit | `uv run pytest tests/test_probs.py::test_difficulty_formula -x` | ❌ Wave 0 |
| MC-06 / PROB-01 | p=0.6→Bo3 0.648; p=0.5→0.5; p_map logistic | unit | `uv run pytest tests/test_probs.py::test_bo3 tests/test_probs.py::test_p_map -x` | ❌ Wave 0 |
| ENG-04 | fold key = difficulty rank (Buchholz≠seed group) | unit | `uv run pytest tests/test_swiss.py::test_fold_uses_difficulty_rank -x` | ❌ Wave 0 |
| GATE-03 | forced-rematch group → matches priority table | unit | `uv run pytest tests/test_swiss.py::test_forced_rematch_pairing -x` | ❌ Wave 0 |
| GATE-03 / ENG-05 | unmatchable group → fallback, no crash | unit | `uv run pytest tests/test_swiss.py::test_no_valid_matching_fallback -x` | ❌ Wave 0 |
| ENG-08 | locked winners deterministic, no-rematch respects locked | unit | `uv run pytest tests/test_swiss.py::test_locked_results_honored -x` | ❌ Wave 0 |
| ENG-09 / MC-05 | same (seed,N) → identical per-team counts across runs | unit | `uv run pytest tests/test_swiss.py::test_reproducible_under_chunking -x` | ❌ Wave 0 |
| ENG-06/07, MC-01/03 | 8 advance / 2×3-0 / 2×0-3, no rematch, Bo3 placement, ΣP invariants ±0.05@N≥50k | property | `uv run pytest tests/test_swiss.py::test_invariants -x` | ❌ Wave 0 |
| **GATE-01** | **reproduce Budapest 2025 Stage 1 pairings EXACTLY** | integration | `uv run pytest tests/test_swiss.py::test_backtest_budapest_2025 -x` | ❌ Wave 0 (fixture VERIFY at exec) |
| MC-04 | full per-sim record sample retained | unit | `uv run pytest tests/test_swiss.py::test_record_sample_retained -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_probs.py -x` (sub-second math guards)
- **Per wave merge:** `uv run pytest -x` (full suite incl. backtest gate)
- **Phase gate:** full suite green — and specifically `test_backtest_budapest_2025` PASS — before `/gsd-verify-work`. GATE-05: no Phase 2 work until this is green.

### Wave 0 Gaps
- [ ] `pyproject.toml [tool.pytest.ini_options]` + `requires-python >=3.12` + numpy/pytest deps
- [ ] `tests/test_probs.py` — difficulty, p_map, Bo3 (math guards)
- [ ] `tests/test_swiss.py` — invariants, fold key, forced rematch, fallback, locked, reproducibility, **backtest**
- [ ] `data/stage1.json` — current Cologne [INFERRED] fixture (for the smoke run) AND a separate Budapest-2025 backtest fixture (VERIFY verbatim)
- [ ] Framework install: `uv add numpy && uv add --dev pytest`

## Security Domain

> Phase 1 is a pure, offline compute core with no untrusted input, no network, no auth, no persistence of user data. Most ASVS categories are N/A. Included for completeness.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Single local user, no auth (out of scope) |
| V3 Session Management | no | No sessions in Phase 1 |
| V4 Access Control | no | No multi-user |
| V5 Input Validation | partial | Backtest fixture / ratings are developer-supplied JSON; validate structure when loaded (Phase 2 owns the editor). Phase 1: assert fixture shape in the test, fail loud on malformed `locked` keys |
| V6 Cryptography | no | RNG here is statistical (numpy), NOT cryptographic — never repurpose `SeedSequence` for secrets |

### Known Threat Patterns for offline numpy engine
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed `data/stage1.json` (wrong seed count, dup seeds) | Tampering | Validate 16 unique seeds / 16 teams on load; raise on mismatch (Phase 2 banner reconciles; Phase 1 asserts) |
| Non-reproducible "reproducible" backtest (chunk drift) | — (integrity) | Pin `n_chunks`; SeedSequence.spawn (Pitfall 10) — this is the real integrity threat for Phase 1 |
| Statistical RNG mistaken for secure RNG | Information disclosure | N/A here, but note: numpy RNG is not for secrets if ever reused elsewhere |

No `security_enforcement` key is set in config.json (absent = enabled); the genuine Phase 1 "security" surface is **data integrity** (reproducibility + fixture validity), addressed above.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | numpy 2.4.x and pytest 8.x are current | Standard Stack | Low — `pip index versions` at install corrects it; APIs used (`default_rng`, `SeedSequence.spawn`, `beta`) are stable across 2.x |
| A2 | Budapest 2025 Stage 1 initial seed order (M80=1 … Rare Atom=16) | Backtest Fixture | HIGH — wrong seeds make a correct engine fail the gate; **MUST verify verbatim from Liquipedia at execution** (already flagged) |
| A3 | The full Budapest round-by-round pairings/results | Backtest Fixture | HIGH — fetch was internally inconsistent (1-1 bucket disagreement); **MUST transcribe match-by-match at execution** |
| A4 | The 15-row priority table covers the relevant backtest buckets; 8-team buckets handled by the same generalized fold | Valve Rules | MEDIUM — if the backtest contains an 8-team bucket whose pairing the greedy generalization gets wrong, the table-lookup fork must extend to it; the backtest will surface this |
| A5 | Budapest format matches the current rulebook revision exactly | Backtest Fixture | LOW-MEDIUM — most recent Major; Wikipedia confirms Valve-standings + Buchholz seeding; confirm no stage-specific rule deviation |

**Items A2/A3 are the load-bearing assumptions.** They are tagged HIGH risk deliberately: this research could fetch the *rules* authoritatively (verbatim GitHub, twice, identical) but could NOT obtain an internally-consistent round-by-round *fixture* in one pass. The planner must budget a verification task: re-fetch Budapest 2025 Stage 1 via `/browse`, reconcile every match, before encoding `test_backtest_budapest_2025`.

## Open Questions (RESOLVED via Execution — see 01-04 Task 1)

> Both questions below are **intentionally unresolvable at planning time** — the Budapest
> fixture data was internally inconsistent across fetches, so encoding it now would bake in an
> error. Their resolution path is fully planned: plan **01-04 Task 1** is an `autonomous: false`
> `checkpoint:human-verify` task that re-fetches and reconciles the fixture via gstack `/browse`
> before the backtest is encoded. The reconciliation *is* the gate — not pre-work for it.

1. **Exact Budapest 2025 Stage 1 round-by-round fixture.**
   - What we know: format confirmed (16-team Valve+Buchholz Swiss); final-eight advancers stable (M80, FlyQuest, B8, Fnatic, NIP, PARIVISION, Imperial, FaZe); R1 seeded pairings provisionally captured.
   - What's unclear: the exact R2→R5 within-bucket pairings (two fetches disagreed on the 1-1 bucket entering R3); the full Bo1/Bo3 map scores per match.
   - **RESOLUTION:** Transcribed verbatim via `/browse` and reconciled match-by-match (8 teams must be at 1-1 after R2) in **01-04 Task 1** (autonomous: false checkpoint), THEN encoded in `test_backtest_budapest_2025`. Do not encode from this research.

2. **Bucket sizes > 6 in the chosen backtest stage.**
   - What we know: Valve's published priority table is for 6-team groups.
   - What's unclear: whether any Budapest Stage 1 record bucket held 8 teams and, if so, whether the greedy fold reproduces Valve's pairing there.
   - **RESOLUTION:** Bucket sizes recorded during the 01-04 Task 1 transcription; if an 8-team bucket diverges, the GATE-04 priority-table-lookup fork (01-04 Task 2) extends to that size or fetches the corresponding rulebook section. Resolved at execution, not planning.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12+ | entire engine | (verify at exec) | — | none — hard requirement |
| numpy | RNG + vectorized tally | (verify at exec: `uv add numpy`) | 2.4.x `[ASSUMED]` | none — core dependency |
| pytest | the gate harness | (verify at exec: `uv add --dev pytest`) | 8.x `[ASSUMED]` | none — tests are the gate |
| uv | bootstrap | (verify at exec) | latest | pip + venv documented fallback (DX §10.6) |
| Internet (`/browse`) | one-time fetch of the Budapest fixture | yes (used in research) | — | this research's provisional data + Wikipedia/HLTV cross-check |

**Missing dependencies with no fallback:** Python 3.12+, numpy, pytest are hard requirements — the planner should add an install/verify task in Wave 0.
**Missing dependencies with fallback:** uv → pip+venv. The Budapest fixture fetch → `/browse` at execution (already the plan).

## Sources

### Primary (HIGH confidence)
- `raw.githubusercontent.com/ValveSoftware/counter-strike_rules_and_regs/main/major-supplemental-rulebook.md` — Difficulty Score definition + worked example, tiebreak chain, **15-row rematch priority table** (fetched twice, identical). VERIFIED.
- `numpy.org/doc/stable/reference/random/parallel.html` + `/multithreading.html` — `SeedSequence.spawn` for reproducible parallel streams (cited in PITFALLS.md, consistent with Pitfall 10).
- `files/HANDOFF_claude_code.md` §3/§4/§5/§6/§10.5/§10.6 — eng/design/DX-reviewed executable spec (project authority).
- `.planning/research/ARCHITECTURE.md`, `.planning/research/PITFALLS.md` — prior project research (functional-core, generator-first, outer-loop, all 15 pitfalls).

### Secondary (MEDIUM confidence)
- `en.wikipedia.org/wiki/StarLadder_Budapest_Major_2025` — format, Valve-standings + Buchholz seeding, dates, champion (Vitality). Confirms backtest-stage suitability.
- `liquipedia.net/counterstrike/StarLadder/2025/Major/Stage_1` — round-by-round fixture (data internally inconsistent across fetches; MUST re-verify verbatim at execution).

### Tertiary (LOW confidence)
- `hltv.org/events/8042/starladder-budapest-major-2025` — cross-check for pairings/scores (not yet deep-fetched; use at execution to triangulate the Liquipedia fixture).

## Metadata

**Confidence breakdown:**
- Valve rules (Buchholz, tiebreak, priority table): HIGH — pulled verbatim from raw GitHub, fetched twice identically.
- Engine architecture / patterns / RNG scheme: HIGH — eng-reviewed spec + numpy docs + prior project research all agree.
- Standard stack: HIGH (numpy/pytest correctness) / version numbers ASSUMED pending `pip index versions`.
- Backtest fixture data: MEDIUM — stage choice is solid; round-by-round data must be re-fetched and reconciled verbatim at execution (flagged HIGH-risk in Assumptions Log).

**Research date:** 2026-05-28
**Valid until:** Rules/priority table — stable (Valve rulebook changes rarely; re-verify if a new Major revises it). Stack versions — ~30 days. Backtest fixture — verify before encoding regardless of age.
