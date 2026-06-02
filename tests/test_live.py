"""Live-mode core tests (RED first, Phase-4 04-01) — the pure decision math for LIVE mode.

Mirrors the Phase-1/Phase-3 discipline: the correctness core is provable in pytest with
NO UI. Everything here imports from ``engine.live`` (which does not exist until the GREEN
tasks) so the file collects and runs RED until the impl lands.

The eleven tests cover the D1/D3/D4/D5/D6 contracts of 04-01-PLAN.md:

  - locked_dict_from_results (D1): list[(round, w, l)] -> {frozenset((w,l)): w}, order-free
  - validate_lock (D3/RESIM-03): None for legal; EXACT reason string for each illegal case
  - classify_pick (D4/RESIM-02): 'advanced'|'eliminated'|'live' off the CONDITIONAL sample
  - pge5_delta (D5/RESIM-02): two p_ge5 calls on ONE fixed anchor ballot, two samples
  - derive_bracket / legal_pairings_for_round (D6/RESIM-04): replay simulate_stage+pairings_out

Fixtures fabricate ``sample`` lists by hand (N tiny, hand-verifiable) — the classification
and delta paths are sample-only by contract, so we NEVER run the MC for them. The
bracket/validator tests reuse the Budapest fixture's seeds (id == seed there) and a fixed
``np.random.default_rng``.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

from engine.live import (
    BracketView,
    LivePrefixIncomplete,
    classify_pick,
    derive_bracket,
    legal_pairings_for_round,
    locked_dict_from_results,
    pge5_delta,
    validate_lock,
)
from engine.optimizer import Ballot, build_outcome_matrices
from engine.swiss import simulate_stage
from engine.teams import STAGE_SIZE, Team, load_teams

# ---------------------------------------------------------------------------
# Budapest fixture — reused for the bracket/validator replay tests (id == seed).
# ---------------------------------------------------------------------------
_BUDAPEST = (
    pathlib.Path(__file__).resolve().parent / "fixtures" / "budapest_2025_stage1.json"
)


def _budapest():
    return json.loads(_BUDAPEST.read_text(encoding="utf-8"))


def _budapest_seeding(fx) -> dict[int, str]:
    return {int(s): name for s, name in fx["seeding"].items()}


def _budapest_teams(fx) -> list[Team]:
    return [Team(id=s, name=name, seed=s, rating=50.0) for s, name in _budapest_seeding(fx).items()]


def _budapest_round_locks(fx, round_no: int) -> list[tuple[int, int, int]]:
    """The (round_idx, winner_id, loser_id) lock list for ONE Budapest round.

    ``round_no`` is the fixture's 1-based round number; ``round_idx`` in the returned
    tuples is 0-based (R1 == 0) to match pairings_out indexing.
    """
    name_to_seed = {name: s for s, name in _budapest_seeding(fx).items()}
    rnd = next(r for r in fx["rounds"] if r["round"] == round_no)
    return [
        (round_no - 1, name_to_seed[m["winner"]], name_to_seed[m["loser"]])
        for m in rnd["matches"]
    ]


# ---------------------------------------------------------------------------
# Cologne fixture helpers (the shipped 16-team set) for sample-only fabrications.
# ---------------------------------------------------------------------------
def _cologne_ids() -> list[int]:
    return [t.id for t in load_teams()]


def _record_sample(records_per_sim: list[dict[int, tuple[int, int]]]):
    """Identity passthrough — a fabricated ``sample`` is just a list of {id: (w,l)} dicts.

    Kept as a named helper so each test reads as "build a sample of N hand-authored sims".
    """
    return records_per_sim


# ===========================================================================
# D1 — lock-list <-> locked-dict projection
# ===========================================================================
def test_locked_dict_derived_from_results():
    # Three locks; winners are the second element of each (round, w, l) tuple.
    locked_results = [(0, 11, 3), (0, 8, 16), (1, 9, 1)]
    got = locked_dict_from_results(locked_results)

    expected = {
        frozenset((11, 3)): 11,
        frozenset((8, 16)): 8,
        frozenset((9, 1)): 9,
    }
    assert got == expected

    # Order-independence: the pair order inside an entry must not matter.
    swapped = [(0, 11, 3), (0, 8, 16), (1, 9, 1)]
    # rebuild from a reversed list -> same dict
    assert locked_dict_from_results(list(reversed(swapped))) == expected

    # Round-trip: every key/winner is recoverable as a (winner, loser) pair.
    for (_r, w, ell) in locked_results:
        key = frozenset((w, ell))
        assert key in got and got[key] == w


# ===========================================================================
# D3 — validate_lock reject/accept with EXACT reason strings (RESIM-03)
# ===========================================================================
def _cologne_teams() -> list[Team]:
    return load_teams()


def _name_of(teams: list[Team], tid: int) -> str:
    return next(t.name for t in teams if t.id == tid)


def test_validate_lock_rejects_rematch():
    teams = _cologne_teams()
    # Cologne R1 pairs seed i vs i+8 -> 1 vs 9 is a real R1 pairing.
    legal = {frozenset((1, 9))}
    prior = [(0, 1, 9)]  # 1 already beat 9 in R1
    reason = validate_lock((1, 9), 1, prior, teams, legal)
    a, b = _name_of(teams, 1), _name_of(teams, 9)
    assert reason == f"{a} vs {b} already played this stage — no rematches."


def test_validate_lock_rejects_terminated_team():
    teams = _cologne_teams()
    # Team id 1 wins three -> 3W (advanced). Locking it into another match must reject.
    prior = [(0, 1, 9), (1, 1, 10), (2, 1, 11)]  # 1 is now 3-0
    legal = {frozenset((1, 12))}
    reason = validate_lock((1, 12), 3, prior, teams, legal)
    t = _name_of(teams, 1)
    assert reason == (
        f"{t} is already out (3-0 advanced / 0-3 eliminated) — cannot play another match."
    )


def test_validate_lock_rejects_non_pairing():
    teams = _cologne_teams()
    # (1, 2) is NOT in the legal set for this round.
    legal = {frozenset((1, 9)), frozenset((2, 10))}
    reason = validate_lock((1, 2), 1, [], teams, legal)
    a, b = _name_of(teams, 1), _name_of(teams, 2)
    assert reason == (
        f"{a} and {b} are not paired this round — the format pairs by record + Buchholz."
    )


def test_validate_lock_rejects_double_booking():
    teams = _cologne_teams()
    # Team id 1 is already locked into another match THIS round (round_idx == 1).
    prior = [(1, 1, 5)]  # round 1: 1 beat 5
    legal = {frozenset((1, 9)), frozenset((1, 5))}
    reason = validate_lock((1, 9), 1, prior, teams, legal)
    t = _name_of(teams, 1)
    assert reason == f"{t} is already locked into another match this round."


def test_validate_lock_accepts_legal():
    fx = _budapest()
    teams = _budapest_teams(fx)
    # A genuine R1 pairing from derive_bracket's legal_pairings, two active teams,
    # winner in the pair -> None.
    bracket = derive_bracket(teams, {}, 40.0)
    r1_legal = set(bracket.legal_pairings[0])
    # pick the (11, 3) pairing (M80 vs B8) — both active, never played.
    pair = frozenset((11, 3))
    assert pair in r1_legal
    reason = validate_lock((11, 3), 0, [], teams, r1_legal)
    assert reason is None


# ===========================================================================
# D4 — classify_pick secured/dead/live against the CONDITIONAL sample [CRITICAL]
# ===========================================================================
def test_classify_secured_dead_live():
    """CRITICAL — exact P==1.0 -> advanced (secured), P==0.0 -> eliminated (dead),
    0<P<1 -> live, computed against the conditional sample via build_outcome_matrices.

    Cologne rule: an ADVANCE pick is correct on an exact 3-1/3-2 finish ONLY — a 3-0 does NOT
    satisfy it (a 3-0-bound team in the advance bucket is a DEAD advance pick; you'd have wanted
    it in the 3-0 bucket). Hand-built N=4 sims over ids 1,2,3,4:
      - team 1: ADVANCE pick, 3-1 in EVERY sim -> is_adv.mean()==1.0 (secured).
      - team 2: 3-0 pick, record (2,1) in EVERY sim -> is_30.mean()==0.0 (dead for 3-0).
      - team 3: ADVANCE pick, 3-1/3-2 in 2 of 4 sims -> is_adv.mean()==0.5 (live).
      - team 4: ADVANCE pick, 3-0 in EVERY sim -> is_adv.mean()==0.0 (DEAD under the Cologne
        rule; this would read "advanced" under the OLD wins>=3 scheme — the regression guard).
    """
    sample = _record_sample(
        [
            {1: (3, 1), 2: (2, 1), 3: (3, 1), 4: (3, 0)},
            {1: (3, 1), 2: (2, 1), 3: (3, 2), 4: (3, 0)},
            {1: (3, 1), 2: (2, 1), 3: (1, 3), 4: (3, 0)},
            {1: (3, 1), 2: (2, 1), 3: (2, 3), 4: (3, 0)},
        ]
    )
    ids = [1, 2, 3, 4]
    matrices = build_outcome_matrices(sample, ids)

    # team 1, advance bucket -> P==1.0 -> secured
    assert classify_pick(1, "picks_adv", matrices) == "advanced"
    # team 2, 3-0 bucket -> P==0.0 -> dead
    assert classify_pick(2, "picks_30", matrices) == "eliminated"
    # team 3, advance bucket -> 0<P<1 -> live
    assert classify_pick(3, "picks_adv", matrices) == "live"
    # team 4, advance bucket, always 3-0 -> P==0.0 -> DEAD (Cologne: 3-0 != advance pick)
    assert classify_pick(4, "picks_adv", matrices) == "eliminated"

    # Exact-equality discipline: the secured/dead verdicts ride on == 1.0 / == 0.0.
    is_30, is_adv, is_03 = matrices
    assert float(is_adv[1].mean()) == 1.0
    assert float(is_30[2].mean()) == 0.0
    assert 0.0 < float(is_adv[3].mean()) < 1.0
    assert float(is_adv[4].mean()) == 0.0


# ===========================================================================
# D5 — pge5_delta = two p_ge5 calls on ONE fixed anchor ballot (RESIM-02)
# ===========================================================================
def test_pge5_delta_uses_same_ballot():
    """Two fabricated samples (pre/post) and ONE fixed anchor Ballot; pge5_delta returns
    (before, after) = p_ge5(anchor, pre) , p_ge5(anchor, post); the value MOVES when the
    post sample differs. Pass ``ids`` explicitly.

    The anchor ballot is 2/6/2 over ids 1..10. The pre sample has the 6 advance picks all
    advancing (>=5 of 10 correct in every sim -> before high); the post sample knocks the
    advance picks down so P(>=5) falls.
    """
    ids = list(range(1, 17))
    anchor = Ballot(
        picks_30=(1, 2),
        picks_adv=(3, 4, 5, 6, 7, 8),
        picks_03=(9, 10),
    )

    def rec(adv_hits: bool) -> dict[int, tuple[int, int]]:
        r: dict[int, tuple[int, int]] = {}
        # 3-0 picks hit exactly (3,0); 0-3 picks hit exactly (0,3).
        r[1] = (3, 0)
        r[2] = (3, 0)
        r[9] = (0, 3)
        r[10] = (0, 3)
        # advance picks: (3,1) when adv_hits else (2,3) (eliminated, not advanced).
        for t in (3, 4, 5, 6, 7, 8):
            r[t] = (3, 1) if adv_hits else (2, 3)
        # filler teams (never picked) so build_outcome_matrices sees every id.
        for t in (11, 12, 13, 14, 15, 16):
            r[t] = (1, 3)
        return r

    pre_sample = [rec(True) for _ in range(8)]   # all 10 picks correct -> before == 1.0
    post_sample = [rec(False) for _ in range(8)]  # only 4 picks correct -> after == 0.0

    before, after = pge5_delta(anchor, _Result(pre_sample), _Result(post_sample), ids)
    assert before == 1.0
    assert after == 0.0
    assert before != after

    # Same anchor, both arms computed by p_ge5 on each sample with the SAME ids.
    pre_m = build_outcome_matrices(pre_sample, ids)
    post_m = build_outcome_matrices(post_sample, ids)
    from engine.optimizer import p_ge5

    assert before == p_ge5(anchor, pre_m)
    assert after == p_ge5(anchor, post_m)


class _Result:
    """Minimal Result stand-in carrying only ``.sample`` (the field pge5_delta reads).

    Plan WARNING-5 allows either a real engine.montecarlo.Result or a sample-only stand-in;
    we use a stand-in so the test never trips on Result.__init__ arity.
    """

    def __init__(self, sample):
        self.sample = sample


# ===========================================================================
# D6 — derive_bracket / legal_pairings_for_round replay the engine [CRITICAL x2]
# ===========================================================================
def test_derive_bracket_pairings_match_engine():
    """CRITICAL — derive_bracket's per-round legal_pairings equal the engine's pairings_out[R]
    for the SAME partial locks + a fixed rng. The replay IS the source of truth (RESIM-04).

    Use the FULL Budapest R1 result set as the partial ``locked`` so R2+ pairings are
    deterministically derivable from the locked R1 standings.
    """
    fx = _budapest()
    teams = _budapest_teams(fx)
    r1_locks = _budapest_round_locks(fx, 1)
    locked = locked_dict_from_results(r1_locks)

    bracket = derive_bracket(teams, locked, 40.0)
    assert isinstance(bracket, BracketView)

    # Engine replay with the SAME locks + a fixed rng, reading pairings_out directly.
    out: list[list[frozenset]] = []
    fresh = _budapest_teams(fx)
    simulate_stage(fresh, None, 40.0, np.random.default_rng(0), dict(locked), pairings_out=out)

    assert len(bracket.legal_pairings) == len(out)
    for r, engine_round in enumerate(out):
        assert set(bracket.legal_pairings[r]) == set(engine_round), (
            f"round {r} legal_pairings diverge from engine pairings_out"
        )


def test_legal_pairings_requires_full_prefix():
    """CRITICAL (BLOCKER 2) — legal_pairings_for_round requires a fully-locked prefix.

    (a) With rounds 0..round_idx-1 FULLY locked, legal_pairings_for_round(round_idx) returns
        a NON-EMPTY set that is INVARIANT across two differently-seeded replays — proving the
        FORMAT determines it, not the draw.
    (b) With an INCOMPLETE prefix (one R1 entry dropped), it raises LivePrefixIncomplete —
        it must NEVER return a single-draw pairing set.
    """
    fx = _budapest()
    teams = _budapest_teams(fx)
    full_r1 = _budapest_round_locks(fx, 1)  # all 8 R1 results

    # (a) full prefix -> round_idx == 1 (R2) pairings are determined.
    pairings_seed0 = legal_pairings_for_round(teams, full_r1, 40.0, 1)
    pairings_seed1 = legal_pairings_for_round(_budapest_teams(fx), full_r1, 40.0, 1)
    assert len(pairings_seed0) > 0
    # rng-invariance: the function pins its own throwaway rng, so two calls match exactly;
    # the set is format-determined, not a single-RNG-draw artifact.
    assert pairings_seed0 == pairings_seed1

    # The R2 pairings the engine actually generated (from the fixture's R2 matches), for a
    # concrete equality check that the returned set is the real R2 pairing set.
    name_to_seed = {name: s for s, name in _budapest_seeding(fx).items()}
    expected_r2 = {
        frozenset((name_to_seed[m["winner"]], name_to_seed[m["loser"]]))
        for m in next(r for r in fx["rounds"] if r["round"] == 2)["matches"]
    }
    assert pairings_seed0 == expected_r2

    # (b) incomplete prefix: drop one R1 entry -> raises.
    incomplete = full_r1[:-1]
    with pytest.raises(LivePrefixIncomplete):
        legal_pairings_for_round(teams, incomplete, 40.0, 1)


def test_locked_winner_deterministic():
    """A FULL ``locked`` dict makes every locked winner's (wins,losses) record identical
    across two differently-seeded replays — the locked prefix is deterministic (extends the
    engine's test_locked_results_honored semantics)."""
    fx = _budapest()
    name_to_seed = {name: s for s, name in _budapest_seeding(fx).items()}

    # Build the FULL locked dict (every Budapest match).
    locked: dict[frozenset, int] = {}
    for rnd in fx["rounds"]:
        for m in rnd["matches"]:
            w, ell = name_to_seed[m["winner"]], name_to_seed[m["loser"]]
            locked[frozenset((w, ell))] = w

    by_id0 = simulate_stage(_budapest_teams(fx), None, 40.0, np.random.default_rng(0), dict(locked))
    by_id1 = simulate_stage(_budapest_teams(fx), None, 40.0, np.random.default_rng(7), dict(locked))

    assert set(by_id0) == set(by_id1) == set(range(1, STAGE_SIZE + 1))
    for tid in by_id0:
        rec0 = (by_id0[tid].wins, by_id0[tid].losses)
        rec1 = (by_id1[tid].wins, by_id1[tid].losses)
        assert rec0 == rec1, f"team {tid} record differs across replays: {rec0} vs {rec1}"
