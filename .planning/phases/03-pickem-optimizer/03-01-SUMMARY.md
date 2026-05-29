---
phase: 03-pickem-optimizer
plan: 01
subsystem: engine
tags: [optimizer, ballot, pge5, e-correct, pure-core]
requires:
  - "engine.montecarlo.Result.sample (Phase 1 MC-04 — the retained per-sim record vectors)"
  - "engine.teams.build_round1_pairs / ADVANCE_AT_WINS / ELIMINATE_AT_LOSSES (Phase 1 — frozen)"
provides:
  - "engine.optimizer.Ballot — validated 2/6/2 ballot (disjoint, hashable)"
  - "engine.optimizer.ballot_a — greedy E[correct] maximizer (OPT-01)"
  - "engine.optimizer.build_outcome_matrices / marginals_from_matrices / p_ge5 / e_correct"
  - "engine.optimizer.ballot_b — P(>=5) hill-climb, no enumeration (OPT-02)"
  - "engine.optimizer.correlated_03_in_r1 — R1 0-3 trap detection via build_round1_pairs (OPT-05)"
  - "engine.optimizer.ballot_diff / OptimizerOutput / optimize — the facade the UI consumes"
affects:
  - "Plan 02 wires optimize() into the UI (hero P(>=5), A-vs-B panel, warning)"
  - "Phase 4 reuses p_ge5 for the live P(>=5)-from-here delta against the locked re-sim sample"
tech-stack:
  added: []
  patterns:
    - "Sample-only: optimizer reads Result.sample; NEVER calls run_mc/simulate_stage (ROADMAP SC4)"
    - "Vectorized P(>=5): precomputed dict[id -> bool ndarray] matrices, one reduce per eval"
    - "Greedy Ballot A = exact E[correct] maximizer (linear slot sum); no enumeration"
    - "Ballot B hill-climb single-team swaps from the A seed; deterministic (sorted, strict-improve)"
    - "R1-trap reuses engine.teams.build_round1_pairs — no seed re-derivation (sidesteps GATE-01)"
key-files:
  created:
    - "engine/optimizer.py"
    - "tests/test_optimizer.py"
  modified: []
decisions:
  - "Marginals computed from the sample matrices inside optimize() (not Result.counts) so Ballot A's ranking and Ballot B's P(>=5) score the SAME distribution — no counts/sample divergence."
  - "Ballot A excludes the 2 3-0 picks from the 0-3 pool and all 4 from the advance pool, so the ballot is valid 2/6/2 by construction (OPT-03)."
  - "Recommended ballot = Ballot B (P(>=5)-optimal); its P(>=5) is the hero number (OPT-04)."
  - "Correlated-pick warning reported for Ballot A (correlation-blind); Ballot B avoids the trap for free because the joint sample makes P(both 0-3)=0 for an R1 pair."
requirements: [OPT-01, OPT-02, OPT-04, OPT-05]
---

# 03-01 Summary — engine/optimizer.py pure core

Built the headless, streamlit-free, RNG-free Pick'Em decision core over the stored per-sim
sample. Ballot A is the greedy E[correct] maximizer; Ballot B hill-climbs P(>=5) against the
sample (no brute force); P(>=5) is vectorized via precomputed boolean outcome matrices; the
correlated-0-3-in-R1 trap is detected by reusing `build_round1_pairs`. `optimize(result,
teams)` returns both ballots, their P(>=5) + E[correct], the differing picks, the
recommended hero P(>=5), and the warning.

## Tests (7, all green; the two HANDOFF §6 criticals included)
- `test_greedy_is_e_correct_optimal` — no single swap beats Ballot A on a degenerate sim.
- `test_pge5_known_answer` [CRITICAL] — crafted 4-sim sample yields P(>=5) = 0.5 exactly.
- `test_optimizer_consumes_sample_not_mc` — simulate_stage/run_mc monkeypatched to raise; optimize() still returns (sample-only, ROADMAP SC4).
- `test_correlated_03_warning_fires_and_b_avoids_it` — engineered 6-sim trap: Ballot A picks the R1 pair {1,9} (warning fires, P(>=5)=0); Ballot B moves off it (not an R1 pair, P(>=5) > 0).
- `test_ballot_a_valid_262` / `test_ballot_b_valid_262` / `test_correlated_detection_pure`.

Full suite: 63 passed, 1 skipped (the unchanged deferred Budapest gate). No engine mutation.
