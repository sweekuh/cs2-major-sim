---
phase: 03-pickem-optimizer
type: verification
date: 2026-05-29
verdict: PASS (with 1 medium semantic caveat for user ruling + minor optional hardening)
suite: "63 passed, 1 skipped (the unchanged deferred Budapest gate)"
---

# Phase 3 Verification & Validation — Pick'Em Optimizer

Independent V&V of the executed Phase 3 (engine/optimizer.py + UI wiring). Method: fresh
full-suite run + a high-effort code-review sweep (line-by-line, removed-behavior,
cross-file, semantic-vs-spec) + Success-Criteria traceability.

## Success Criteria (ROADMAP Phase 3) — all met

| # | Criterion | Verdict | Evidence |
|---|-----------|---------|----------|
| 1 | Ballot A (greedy) + Ballot B (P(≥5) hill-climb) side by side, both valid 2/6/2 no team twice, differing picks highlighted (OPT-01/02/03) | PASS¹ | `test_ballot_a_valid_262`, `test_ballot_b_valid_262`, `test_ballot_panel_renders_after_run`, `test_ballot_columns_lists_names_and_marks_diff` |
| 2 | Chosen ballot's P(≥5/10) by exact-record scoring of each sim, shown as hero (OPT-04) | PASS | `test_pge5_known_answer` (hand-computed 0.5), `test_hero_is_pge5_not_placeholder` (#7C5CFC hero, placeholder gone) |
| 3 | Correlated-pick warning fires when the two 0-3 picks meet in R1; Ballot B auto-avoids (OPT-05) | PASS | `test_correlated_03_warning_fires_and_b_avoids_it`, `test_correlated_detection_pure` |
| 4 | Optimizer consumes the stored sample, never re-runs the MC (OPT-04) | PASS | `test_optimizer_consumes_sample_not_mc` (monkeypatches `simulate_stage`/`run_mc` to raise; optimize() still returns) |

¹ See Finding 1 — the "E[correct]-optimal" *label* on Ballot A over-claims; the implementation
faithfully matches OPT-01's literal greedy definition.

## Findings

### 1 — [MEDIUM, semantic — both reviewers] Ballot A's greedy is NOT globally E[correct]-optimal
`engine/optimizer.py:ballot_a` / OPT-01 / HANDOFF §7 claim the greedy (top-2 P(3-0) → 3-0,
top-2 P(0-3) → 0-3, top-6 P(advance) → advance) is the *exact* E[correct] maximizer because
"E[correct] is a linear sum of independent slot-hit probabilities." That reasoning is
incomplete: the 3-0 and advance buckets compete for the same teams and Padv ≥ P30 for every
team, so it is an assignment problem — the 2 teams "spent" on the 3-0 slots should be those of
**smallest** (Padv − P30) gap, not the highest P(3-0).

Brute-force-confirmed counterexample (16-team marginals; the independent review enumerated all
C(12,2)·C(10,2)·C(8,6) valid assignments):
- X=Y=(P30 0.50, Padv 0.98); Z=W=(0.45, 0.45); A=B=C=D=(0.05, 0.90); G=H=(0.05, 0.50); 0-3 P=0.80, Q=0.70.
- **Greedy** 3-0={X,Y}, adv={A,B,C,D,G,H}, 0-3={P,Q}: E = 1.00 + 4.60 + 1.50 = **7.10**.
- **Optimal** 3-0={Z,W}, adv={X,Y,A,B,C,D}, 0-3={P,Q}: E = 0.90 + 5.56 + 1.50 = **7.96** (+0.86).

(My own smaller check: A=(.90,.90),B=(.95,1.0),C=(.92,1.0) → greedy 2.77 vs alt 2.85.) The
divergence appears when the P(3-0) rank disagrees with the advance-gap rank; for typical
favorites (high P30 ⟹ also high Padv) the two coincide, which is why the degenerate
`test_greedy_is_e_correct_optimal` passes. The claim is nonetheless false in general.

**Disposition:** the implementation matches OPT-01 *as written* (it literally specifies this
greedy); the inaccuracy is the "(E[correct]-optimal) / provably optimal, no search" wording.
This compounds with Finding 2 (Ballot B, the hero, is seeded from A and cannot re-bucket to
escape the blind spot), so it is not purely cosmetic. Resolution is the user's call — see the
verdict's three options.

### 2 — [MEDIUM, both reviewers] Ballot B's hill-climb cannot re-bucket its own picks
`ballot_b`/`_swap` only swaps a *picked* team for an *unpicked* team within the same bucket; it
never moves an already-picked team to a different bucket. So a higher-P(≥5) ballot that keeps
the same 10 teams but reassigns which 2 are the 3-0 picks (exactly the restructuring in Finding
1, and advance hits are far likelier than exact-3-0 hits) is **unreachable from the seed**.
Since Ballot B is seeded from the possibly-suboptimal Ballot A, it inherits A's blind spot.
"hill-climb single-team swaps" (HANDOFF §7) is ambiguous on whether intra-ballot bucket moves
count. **Fix (contained, spec-consistent):** add re-bucketing moves to the neighborhood.

### 3 — [FIXED] Correlated-pick warning looked names up by seed, not id
`app.py` resolved `opt.warning` (team **ids**) through the seed-keyed `by_seed` map — correct
only because id == seed for the default fixture, and inconsistent with the id-keyed `name_of`
used for the ballot directly below. Fixed in commit 25d578c (uses `name_of`).

### 4 — [LOW, optional] NaN on an empty sample (N=0)
If a `Result` with `sample=[]` ever reached `optimize()`, marginals and P(≥5) become NaN
(mean of empty) and the hero renders "nan%". Guarded in practice by the app/engine N≥1000
floor; the optimizer has no own guard. Optional hardening (raise on empty sample). Accepted.

### 5 — [LOW, accepted] optimize_cached fixture is an unkeyed dependency
`ui/cache.optimize_cached` keys on `(ratings_key, S, N, locked_key)` and reloads `load_teams()`
internally. A `data/stage1.json` team-name change with a byte-identical seed→rating map would
serve a stale `OptimizerOutput` within a session. Single-user tool, fixture static at runtime
— accepted; revisit if live fixture editing of names is ever added.

### 6 — [LOW, accepted] Optimizer implicitly assumes the 16-team / 2-6-2 contract
`_top` can return fewer than k for a <16-team set, making `Ballot.__post_init__` raise. This
is a loud crash, never a silently-wrong ballot. Accepted (the engine is Stage-1-fixed).

### 7 — [INFO, clean] Verified-correct items
- **Exact-record scoring has no off-by-one** (both reviewers): 3-0 hit = `(wins==3 & losses==0)`,
  advance hit = `wins>=3`, 0-3 hit = `(wins==0 & losses==3)`. A 3-0 team is also an advancer,
  but 3-0 picks and advance picks are disjoint teams, so no double-count. Matches PRD/HANDOFF.
- **Cross-file wiring clean**: `_run_or_serve` 2-tuple → 3-tuple updated at all return paths +
  the single unpack site; `optimize_cached(result, *cache_key)` arg order matches the signature.
- **Minor cleanup (optional)**: `ballot_b` discards its converged `best_score`, so `optimize()`
  recomputes `p_ge5(b)` once — one avoidable full-array pass at N=100k. Return `(Ballot, score)`
  to remove it. Negligible.

## Verdict

**PASS.** All four Success Criteria met; suite green (63 passed, 1 skipped). One genuine latent
bug found and **fixed** (Finding 3, the warning id/seed lookup). Findings 4–6 are
low-severity/accepted, Finding 7 confirms the scoring core is correct.

The substantive open item is **Findings 1 + 2 together**: the bucket-wise greedy is provably
not the global E[correct] maximizer (brute-force-confirmed +0.86 case), and Ballot B's
narrow swap neighborhood can't re-bucket to escape it — so even the P(≥5) hero can be
suboptimal in the (uncommon) marginal structures where the P(3-0) rank and the advance-gap
rank disagree. The implementation faithfully matches OPT-01 *as written*; the over-claim is in
the "optimal / no search" wording.

**RESOLVED (option 2 — broaden Ballot B + soften wording), implemented:**
- `ballot_b` now hill-climbs over a broadened `_neighbors` set that adds **re-bucketing
  moves** (exchange the buckets of two already-picked teams), so the P(≥5) recommendation can
  escape Ballot A's marginal-greedy blind spot — directly neutralizing Finding 2 and Finding
  1's practical impact on the hero. Still no brute-force enumeration; still deterministic.
- Ballot A is kept as the literal greedy OPT-01 defines, with the "(E[correct]-optimal) /
  provably optimal, no search" over-claim softened to "greedy per-bucket marginal baseline" in
  the `ballot_a` docstring and OPT-01.
- New regression tests: `test_rebucket_preserves_validity`, `test_neighbors_include_rebucketing_moves`,
  `test_ballot_b_is_full_neighborhood_local_optimum`. Suite now **66 passed, 1 skipped**.
- Option 3 (make Ballot A itself the exact E[correct] maximizer) was declined: it contradicts
  OPT-01's explicit "via greedy" and muddies the deliberate A-vs-B (naive-vs-search) contrast.
