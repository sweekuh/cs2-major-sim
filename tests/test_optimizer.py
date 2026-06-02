"""Pick'Em optimizer tests — Phase 3 plan 01 (engine/optimizer.py).

The two named criticals (HANDOFF §6) carry the correctness weight:
  - test_greedy_is_e_correct_optimal — Ballot A is the E[correct] maximizer.
  - test_pge5_known_answer — a hand-computed P(>=5) on a tiny crafted sample.

Plus the sample-only contract (test_optimizer_consumes_sample_not_mc): the optimizer reads
the stored Result.sample and NEVER re-runs the MC (ROADMAP Success Criterion 4), and the
correlated-0-3-in-R1 trap (OPT-05): the warning fires for Ballot A and Ballot B avoids it.

Fixtures are hand-authored record samples — the MC is never run to build them (that is the
whole point). Each sample is tiny so the criticals are auditable by eye.
"""

from __future__ import annotations

from engine.montecarlo import Result
from engine.optimizer import (
    Ballot,
    _neighbors,
    _rebucket,
    _swap,
    ballot_a,
    ballot_b,
    build_outcome_matrices,
    correlated_03_in_r1,
    e_correct,
    marginals_from_matrices,
    optimize,
    p_ge5,
)
from engine.teams import load_teams

IDS = list(range(1, 17))  # the fixture ids == seeds 1..16


def _result(sample: list[dict[int, tuple[int, int]]]) -> Result:
    """Build a Result from a hand-authored sample, deriving the marginal counts from it."""
    counts_30 = {i: sum(1 for s in sample if s[i] == (3, 0)) for i in IDS}
    counts_adv = {i: sum(1 for s in sample if s[i][0] >= 3) for i in IDS}
    counts_03 = {i: sum(1 for s in sample if s[i] == (0, 3)) for i in IDS}
    return Result(
        n=len(sample),
        counts_30=counts_30,
        counts_advance=counts_adv,
        counts_03=counts_03,
        sample=sample,
    )


def _degenerate_records() -> dict[int, tuple[int, int]]:
    """A deterministic stage outcome: 1,2 go 3-0; 3..8 advance 3-1; 9,10 go 0-3; 11..16 lose 2-3."""
    rec: dict[int, tuple[int, int]] = {}
    for s in (1, 2):
        rec[s] = (3, 0)
    for s in (3, 4, 5, 6, 7, 8):
        rec[s] = (3, 1)
    for s in (9, 10):
        rec[s] = (0, 3)
    for s in (11, 12, 13, 14, 15, 16):
        rec[s] = (2, 3)
    return rec


def _degenerate_sample(n: int = 4) -> list[dict[int, tuple[int, int]]]:
    rec = _degenerate_records()
    return [dict(rec) for _ in range(n)]


def test_ballot_a_valid_262():
    """Ballot A is exactly 2/6/2 with no team in two buckets, and greedy picks the obvious
    teams on the degenerate sample (OPT-01/OPT-03)."""
    out = optimize(_result(_degenerate_sample()), load_teams())
    a = out.ballot_a
    assert len(a.picks_30) == 2 and len(a.picks_adv) == 6 and len(a.picks_03) == 2
    assert len(set(a.all_ids)) == 10
    assert set(a.picks_30) == {1, 2}
    assert set(a.picks_03) == {9, 10}
    assert set(a.picks_adv) == {3, 4, 5, 6, 7, 8}


def test_ballot_b_valid_262():
    """Ballot B stays a valid 2/6/2 ballot with no team in two buckets (OPT-02/OPT-03)."""
    out = optimize(_result(_degenerate_sample()), load_teams())
    b = out.ballot_b
    assert len(b.picks_30) == 2 and len(b.picks_adv) == 6 and len(b.picks_03) == 2
    assert len(set(b.all_ids)) == 10


def test_greedy_is_e_correct_optimal():
    """HANDOFF §6: on a degenerate deterministic sample, Ballot A maximizes E[correct] —
    no single-team swap improves it (the greedy is the exact maximizer, OPT-01)."""
    sample = _degenerate_sample()
    matrices = build_outcome_matrices(sample, IDS)
    p_30, p_adv, p_03 = marginals_from_matrices(matrices)
    a = ballot_a(p_30, p_adv, p_03)

    base = e_correct(a, p_30, p_adv, p_03)
    assert base == 10.0  # every pick correct on the clean degenerate sim

    # No single-team swap (replace a picked team with a not-picked team in any bucket)
    # improves E[correct]. Enumerate the swaps here in the TEST, not the implementation.
    chosen = set(a.all_ids)
    others = [t for t in IDS if t not in chosen]
    for bucket in ("picks_30", "picks_adv", "picks_03"):
        for out_id in getattr(a, bucket):
            for in_id in others:
                trial = _swap(a, bucket, out_id, in_id)
                assert e_correct(trial, p_30, p_adv, p_03) <= base + 1e-9


def test_pge5_known_answer():
    """HANDOFF §6 CRITICAL: a tiny crafted sample yields the hand-computed P(>=5) exactly.

    Fixed ballot = 3-0:{1,2}, advance:{3,4,5,6,7,8}, 0-3:{9,10}. Correct counts per sim,
    by hand (3-0 exact, advance = exact 3-1/3-2, 0-3 exact). The answer is unchanged from the
    old wins>=3 rule here because no advance-PICKED team (3..8) ever finishes 3-0 in these sims:
      sim A: 1,2=(3,0)✓✓; 3..8 advance ✓×6; 9,10=(0,3)✓✓            -> 10  (>=5)
      sim B: 1=(3,0)✓; 2=(3,1)✗; 3,4 advance ✓✓; 5..8 lose ✗; 9=(0,3)✓; 10✗ ->  4  (<5)
      sim C: 1,2=(3,0)✓✓; 3,4,5 advance ✓✓✓; 6..8 ✗; 9,10 ✗         ->  5  (>=5)
      sim D: all picks wrong                                          ->  0  (<5)
    Two of four sims clear >=5 -> P(>=5) = 2/4 = 0.5.
    """
    base = {i: (2, 3) for i in IDS}  # default: eliminated 2-3 (neither 3-0, advance, nor 0-3)

    sim_a = {**base, 1: (3, 0), 2: (3, 0), 3: (3, 1), 4: (3, 1), 5: (3, 1),
             6: (3, 1), 7: (3, 1), 8: (3, 1), 9: (0, 3), 10: (0, 3)}
    sim_b = {**base, 1: (3, 0), 2: (3, 1), 3: (3, 1), 4: (3, 1), 9: (0, 3), 10: (1, 3)}
    sim_c = {**base, 1: (3, 0), 2: (3, 0), 3: (3, 2), 4: (3, 2), 5: (3, 2)}
    sim_d = {**base, 9: (3, 0), 10: (3, 1)}

    sample = [sim_a, sim_b, sim_c, sim_d]
    matrices = build_outcome_matrices(sample, IDS)
    ballot = Ballot((1, 2), (3, 4, 5, 6, 7, 8), (9, 10))
    assert p_ge5(ballot, matrices) == 0.5


def test_advance_pick_requires_3_1_or_3_2():
    """CRITICAL (Cologne rule): an ADVANCE-bucket pick is correct ONLY on an exact 3-1/3-2
    finish. A 3-0 satisfies the 3-0 bucket, NEVER the advance bucket. This guards the fix from
    the old `wins >= 3` scheme (which the existing fixtures could not catch because no advance
    pick ever finishes 3-0 in them).
    """
    base = {i: (2, 3) for i in IDS}
    # team 3 -> 3-0, team 4 -> 3-1, team 5 -> 3-2, team 6 -> 2-3 (out).
    sim = {**base, 3: (3, 0), 4: (3, 1), 5: (3, 2), 6: (2, 3)}
    is_30, is_adv, is_03 = build_outcome_matrices([sim], IDS)

    # 3-0 finish: counts for the 3-0 bucket, NOT the advance bucket.
    assert bool(is_30[3][0]) is True
    assert bool(is_adv[3][0]) is False, "a 3-0 finish must NOT satisfy an advance pick (Cologne)"
    # 3-1 and 3-2: advance-bucket hits, not 3-0.
    assert bool(is_adv[4][0]) is True and bool(is_adv[5][0]) is True
    assert bool(is_30[4][0]) is False and bool(is_30[5][0]) is False
    # 2-3: neither.
    assert bool(is_adv[6][0]) is False and bool(is_30[6][0]) is False

    # P(>=5) penalises putting a 3-0-bound team in the advance bucket. An all-3-0 sim where the
    # advance picks ALL go 3-0 scores 0 advance hits under the Cologne rule (would be 6 under
    # the old wins>=3 rule).
    all_30 = {**{i: (2, 3) for i in IDS}, 1: (3, 0), 2: (3, 0),
              3: (3, 0), 4: (3, 0), 5: (3, 0), 6: (3, 0), 7: (3, 0), 8: (3, 0)}
    mtx = build_outcome_matrices([all_30], IDS)
    ballot = Ballot((1, 2), (3, 4, 5, 6, 7, 8), (9, 10))  # advance picks all finish 3-0
    # 2 correct (the 3-0 bucket) < 5 -> P(>=5) == 0 (was 8 correct / 1.0 under the old rule).
    assert p_ge5(ballot, mtx) == 0.0


def test_optimizer_consumes_sample_not_mc(monkeypatch):
    """ROADMAP SC4: the optimizer scores the stored sample and NEVER re-runs the MC.

    Make the simulation entry points explode; optimize() must still return a recommendation.
    """
    import engine.montecarlo as mc
    import engine.swiss as swiss

    def _boom(*args, **kwargs):
        raise AssertionError("optimizer must not run the MC — it scores Result.sample")

    monkeypatch.setattr(swiss, "simulate_stage", _boom)
    monkeypatch.setattr(mc, "run_mc", _boom)
    monkeypatch.setattr(mc, "run_mc_progressive", _boom)

    out = optimize(_result(_degenerate_sample()), load_teams())
    assert 0.0 <= out.recommended_pge5 <= 1.0
    assert len(set(out.recommended.all_ids)) == 10


def test_correlated_detection_pure():
    """correlated_03_in_r1 returns the pair iff the two 0-3 picks meet in R1 (OPT-05).

    R1 pairs are (i, i+8): seeds 1 & 9 meet; seeds 9 & 10 do not.
    """
    teams = load_teams()
    trap = Ballot((2, 3), (4, 5, 6, 7, 8, 10), (1, 9))  # 0-3 picks 1 & 9 meet in R1
    assert correlated_03_in_r1(trap, teams) == (1, 9)
    safe = Ballot((3, 4), (5, 6, 7, 8, 11, 12), (9, 10))  # 9 & 10 do not meet
    assert correlated_03_in_r1(safe, teams) is None


def _trap_sample() -> list[dict[int, tuple[int, int]]]:
    """6 sims engineered so greedy Ballot A's two 0-3 picks (seeds 1 & 9) are an R1 pair that
    can NEVER both go 0-3 (one wins R1), so the trap ballot's P(>=5) is 0; seed 2 is a third
    0-3 option that co-occurs with seed 1, so an alternative pair scores > 0.

    Every sim: 3,4 go 3-0 (+2); exactly one advance pick (5,6,7,8,10,11 in turn) advances (+1)
    -> the 8 non-0-3 picks contribute exactly 3, so clearing >=5 needs BOTH 0-3 picks correct.
      seed1 0-3 in sims 1-3, seed9 0-3 in sims 4-6 (disjoint -> never both), seed2 0-3 in 1,4.
    """
    advancer = {1: 5, 2: 6, 3: 7, 4: 8, 5: 10, 6: 11}
    s1_03, s9_03, s2_03 = {1, 2, 3}, {4, 5, 6}, {1, 4}
    sims = []
    for k in range(1, 7):
        rec = {i: (2, 3) for i in IDS}
        rec[3] = (3, 0)
        rec[4] = (3, 0)
        rec[advancer[k]] = (3, 1)
        if k in s1_03:
            rec[1] = (0, 3)
        if k in s9_03:
            rec[9] = (0, 3)
        if k in s2_03:
            rec[2] = (0, 3)
        sims.append(rec)
    return sims


def test_rebucket_preserves_validity():
    """_rebucket exchanges two picked teams' buckets, keeping the same 10 teams + 2/6/2 sizes
    (V&V Finding 2 — the move family that lets Ballot B re-assign Ballot A's own picks)."""
    a = Ballot((1, 2), (3, 4, 5, 6, 7, 8), (9, 10))
    # Move team 3 (advance) into 3-0 and team 1 (3-0) into advance.
    b = _rebucket(a, "picks_30", 1, "picks_adv", 3)
    assert set(b.all_ids) == set(a.all_ids)  # same 10 teams
    assert len(b.picks_30) == 2 and len(b.picks_adv) == 6 and len(b.picks_03) == 2
    assert 3 in b.picks_30 and 1 in b.picks_adv


def test_neighbors_include_rebucketing_moves():
    """The hill-climb neighborhood contains re-bucketing moves (same 10 teams, different
    buckets) — not just picked<->unpicked swaps (V&V Finding 2 regression guard)."""
    a = Ballot((1, 2), (3, 4, 5, 6, 7, 8), (9, 10))
    same_team_reassignments = [
        n for n in _neighbors(a, IDS) if set(n.all_ids) == set(a.all_ids) and n != a
    ]
    assert same_team_reassignments, "neighborhood must include re-bucketing of picked teams"


def test_ballot_b_is_full_neighborhood_local_optimum():
    """Ballot B converges to a local optimum under the FULL neighborhood: no single neighbor
    (in/out swap OR re-bucketing) strictly improves P(>=5) (OPT-02)."""
    teams = load_teams()
    out = optimize(_result(_trap_sample()), teams)
    matrices = build_outcome_matrices(_trap_sample(), [t.id for t in teams])
    best = out.ballot_b
    best_score = p_ge5(best, matrices)
    for neighbor in _neighbors(best, [t.id for t in teams]):
        assert p_ge5(neighbor, matrices) <= best_score + 1e-12


def test_correlated_03_warning_fires_and_b_avoids_it():
    """OPT-05: Ballot A falls into the correlated 0-3-in-R1 trap (warning fires); Ballot B,
    scoring P(>=5) against the joint sample, avoids it automatically."""
    teams = load_teams()
    out = optimize(_result(_trap_sample()), teams)

    # Ballot A (correlation-blind greedy) picks the R1 pair {1,9} -> warning fires.
    assert set(out.ballot_a.picks_03) == {1, 9}
    assert out.warning == (1, 9)
    assert out.pge5_a == 0.0  # the trap can never clear >=5

    # Ballot B moved off the trap: its 0-3 picks are NOT an R1 pair and it scores better.
    assert correlated_03_in_r1(out.ballot_b, teams) is None
    assert out.pge5_b > out.pge5_a
