# Phase 3 Research — Pick'Em Optimizer

Phase: 03-pickem-optimizer
Requirements: OPT-01, OPT-02, OPT-03, OPT-04, OPT-05
Depends on: Phase 1 (`Result.sample` — the full per-sim record vector, MC-04) · Phase 2 (UI shell, `_hero_slot`, cache pattern B)
Sources: `files/HANDOFF_claude_code.md` §6/§7/§10.5 · `files/PRD_cologne2026_pickem_simulator.md` F5 · `.planning/REQUIREMENTS.md` OPT-01..05 · `engine/montecarlo.py` (Result) · `engine/swiss.py` (`build_round1_pairs`)

## What this phase is

A pure decision layer on top of the proven engine. It reads the **stored per-sim
sample** (`Result.sample`: a length-N list of `{team_id: (wins, losses)}`) and the
marginal `Result.p_30/p_advance/p_03`, and produces two ballots side by side plus the
true coin odds. **It never runs the MC** — the sample is the contract (Success Criterion
4 / `test_pge5_known_answer`, `test_greedy_is_e_correct_optimal`).

## The format facts (load-bearing — getting any wrong corrupts the recommendation)

- **Ballot = 2 / 6 / 2 = 10 distinct teams, no overlap** (PRD §"10 calls"): 2 picks for
  exact **3-0**, 6 picks for **advance** (reach 3 wins: 3-0/3-1/3-2), 2 picks for exact
  **0-3**. A 3-0 pick is scored on the exact record, NOT on "advanced".
- **Scoring per sim (exact-record):** a 3-0 pick scores iff that team's record is exactly
  `(3, 0)`; an advance pick scores iff `wins >= 3`; a 0-3 pick scores iff record is exactly
  `(0, 3)`. Max 10. **≥5 correct upgrades the coin** — P(≥5/10) is the "true coin odds".
- **`advance` excludes the four already chosen** (OPT-01): the 6 advance slots are the top
  6 by P(advance) AFTER removing the two 3-0 and two 0-3 picks, so no team sits in two
  buckets and the ballot is valid by construction.

## Key decisions

### D1 — Ballot A is greedy and that greedy is the EXACT E[correct] maximizer (OPT-01)
E[correct] is a linear sum of per-slot hit probabilities (indicator expectations), so the
bucket-wise greedy — top 2 by P(3-0), top 2 by P(0-3), top 6 by P(advance) excluding the
four chosen — is not a heuristic; it is the maximizer. **No enumeration.** This is exactly
what `test_greedy_is_e_correct_optimal` pins on a degenerate deterministic sim (no single
swap improves E[correct]). HANDOFF §7.

### D2 — Ballot B needs SEARCH because P(≥5) is nonlinear + correlation-sensitive (OPT-02)
P(≥5) couples all 10 picks through the joint sim records, so it is not separable and greedy
does not maximize it. Full enumeration is ~10M ballots — **forbidden**. Use **hill-climb
single-team swaps seeded from Ballot A**: repeatedly try replacing one currently-picked team
in a bucket with one not-picked team (bucket sizes preserved → validity preserved), keep the
best strictly-improving swap, iterate to a local optimum. Converges fast and is the spec's
prescribed method.

### D3 — Vectorize P(≥5) against the sample with precomputed boolean matrices
One O(N·16) pass turns `Result.sample` into three `dict[team_id -> np.ndarray[bool]]` of
length N: `is_30`, `is_adv`, `is_03`. Then any ballot's P(≥5) is: stack its 10 selected
boolean rows → sum across picks → `(total >= 5).mean()`. Each eval is one vectorized reduce
over N, so the whole hill-climb (≈ 10 picks × ~6 candidates × a few passes ≈ a few hundred
evals) stays well under a second at N=100k. **This is why the optimizer can consume the
sample and never touch the RNG.**

### D4 — Correlated 0-3 trap detection reuses `build_round1_pairs` (OPT-05)
Two teams that meet in **Round 1** cannot both go 0-3 (one wins R1), so picking both caps
that bucket at 1 correct and drags P(≥5) down. R1 pairings are deterministic (seed *i* vs
*i+8*) and already live in `engine.swiss.build_round1_pairs(teams)` — reuse it, do NOT
re-derive seeds. The warning is computed on **Ballot A** (E[correct] is correlation-blind
and *can* fall into the trap). **Ballot B avoids it automatically** because the joint sample
encodes P(both 0-3) ≈ 0, so the P(≥5) search never keeps both — assert this in a test.

### D5 — Hero number = the recommended ballot's P(≥5) (OPT-04)
Per UI-SPEC §10.5 the ballot headline is the big P(≥5) percentage. The **recommended /
chosen** ballot is **Ballot B** (the P(≥5)-optimal one) — its P(≥5) fills the `_hero_slot`
placeholder that Phase 2 left in `app.py` (`_hero_slot`, currently the top-team P(advance)
stand-in). Ballot A's P(≥5) is shown alongside for comparison. Live-mode "P(≥5)-from-here"
delta is **Phase 4** — Phase 3 fills the **pre-stage** hero only.

### D6 — Optimizer output is memoized on the SAME cache key as the MC
The optimizer is a pure function of `(Result, teams)`, and `Result` is already keyed by
`(ratings_key, S, N, locked_key)` in `KEY_MC_CACHE`. Stash the optimizer output in
`st.session_state` under that same tuple (Phase 2 "pattern B"), or wrap it in
`@st.cache_data` keyed on the frozen inputs — single compute per unique run, recomputed
when (and only when) `locked` changes in Phase 4.

## Engine seams already in place (no engine change needed)

- `Result.sample` (MC-04) — full per-sim records, retained for exactly this.
- `Result.p_30()/p_advance()/p_03()` and `band_*` — marginals for Ballot A + display.
- `engine.swiss.build_round1_pairs(teams)` — deterministic R1 pairing for D4.
- `engine.teams.load_teams()` — id↔name↔seed for rendering + R1 lookup.
- `ADVANCE_AT_WINS = 3`, `ELIMINATE_AT_LOSSES = 3` (`engine.teams`) — the record thresholds.

**No change to `engine/montecarlo.py`, `engine/swiss.py`, or `engine/probs.py`.** The
optimizer is additive (`engine/optimizer.py` + `tests/test_optimizer.py`) plus a UI wiring
slice in `app.py`/`ui/`.

## Risks / pitfalls

| Risk | Mitigation |
|------|------------|
| Treating a 3-0 pick as "advanced" when scoring | Exact-record check `(3,0)`; covered by `test_pge5_known_answer` |
| Brute-forcing P(≥5) over ~10M ballots | Hill-climb from Ballot A only (D2); no enumeration |
| Optimizer secretly re-running the MC | Consumes `Result.sample` only; a test monkeypatches `simulate_stage` to raise and asserts the optimizer still computes |
| Ballot B keeping the R1 0-3 trap | Sample encodes P(both 0-3)≈0; `test` asserts B's 0-3 picks are not an R1 pair |
| Re-deriving R1 seeds by hand (the Phase-1 seed blocker) | Reuse `build_round1_pairs` — no seed re-derivation |
| Hill-climb non-determinism | Deterministic candidate order (sorted ids) + strict-improvement-only + tie-break to lower seed → reproducible Ballot B |
| Optimizer recompute on every Streamlit rerun | Memoize on the MC cache key (D6) |

## Test plan (HANDOFF §6 — the two named criticals are non-negotiable)

- `test_ballot_a_valid_262` / `test_ballot_b_valid_262` — exactly 2/6/2, no team twice.
- `test_greedy_is_e_correct_optimal` — degenerate deterministic sim; no single swap beats A.
- `test_pge5_known_answer` **[CRITICAL]** — tiny crafted sample with a hand-computed P(≥5).
- `test_optimizer_consumes_sample_not_mc` — monkeypatch `simulate_stage` to raise; optimizer still returns.
- `test_correlated_03_warning_fires` — ballot with two 0-3 picks that are an R1 pair → warning; and Ballot B's 0-3 picks are NOT an R1 pair on a sample where they meet.

## Plan split (2 plans, standard granularity)

- **03-01** — `engine/optimizer.py` pure core (OPT-01/02/04/05 logic) + `tests/test_optimizer.py` (all §6 optimizer tests, TDD). No UI.
- **03-02** — UI wiring: fill `_hero_slot` with Ballot B P(≥5) (OPT-04), render Ballot A vs B side by side with differing picks highlighted (OPT-03), correlated-pick warning banner (OPT-05), memoized on the MC cache key (D6); AppTest coverage + ballot-panel interaction states.
