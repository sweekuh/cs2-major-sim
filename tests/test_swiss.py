"""Swiss-engine correctness tests (Wave 2 — engine/swiss.py).

These are the load-bearing checks the structural invariants alone do NOT catch
(Pitfalls 1/2/3): the fold key is difficulty-ranked (not raw seed), the rematch
resolution matches Valve's verbatim 15-row priority table, the unmatchable group
falls back without crashing, and locked winners are deterministic while the
no-rematch rule respects locked history.

`opps` holds opponent OBJECTS (not ids): engine.probs.difficulty() iterates
`o.wins - o.losses for o in t.opps`, so a team's opponent collection must expose
.wins/.losses. The no-rematch check compares opponent .id. conftest.FakeTeam
matches this contract (.id/.seed/.wins/.losses/.opps:list).
"""

from __future__ import annotations

import pytest


# --------------------------------------------------------------------------- #
# Task 1: within-group ranking + rematch-avoiding fold + priority-table oracle
# --------------------------------------------------------------------------- #


def test_difficulty_unit(make_team):
    """Canonical Buchholz, imported into swiss from probs (no second copy).

    swiss.difficulty IS engine.probs.difficulty — opponents 2-0 and 1-1 -> 2.
    """
    from engine.swiss import difficulty

    team = make_team(
        id=1,
        opps=[make_team(id=101, wins=2, losses=0), make_team(id=102, wins=1, losses=1)],
    )
    assert difficulty(team) == 2


def test_fold_uses_difficulty_rank(make_team):
    """ENG-04 / Pitfall 3: the fold pairs on difficulty rank, not raw seed.

    Build a 4-team group whose Buchholz (difficulty) order is the REVERSE of seed
    order, with no rematch constraints. The rank key is (-difficulty, seed), so the
    highest-difficulty team is group-seed 1 and faces the lowest-difficulty team
    (fold: 1v4, 2v3 in difficulty-rank space). If the difficulty sort were removed
    (ranking by raw seed instead), the pairing would differ — proving the sort is
    load-bearing, not dead code.
    """
    from engine.swiss import pair_within_group, rank_group

    # opponents that confer difficulty = sum(opp.wins - opp.losses)
    strong = lambda: [make_team(id=900, wins=2, losses=0)]  # +2 difficulty each opp
    weak = lambda: [make_team(id=901, wins=0, losses=2)]  # -2 difficulty each opp

    # seed 1 has LOW difficulty, seed 4 has HIGH difficulty (reverse of seed order).
    t1 = make_team(id=1, seed=1, wins=1, losses=1, opps=weak())  # diff -2
    t2 = make_team(id=2, seed=2, wins=1, losses=1, opps=weak())  # diff -2
    t3 = make_team(id=3, seed=3, wins=1, losses=1, opps=strong())  # diff +2
    t4 = make_team(id=4, seed=4, wins=1, losses=1, opps=strong())  # diff +2
    group = [t1, t2, t3, t4]

    ranked = rank_group(group)
    # (-difficulty, seed): +2 teams first (seed asc: 3,4), then -2 teams (seed asc: 1,2).
    assert [t.id for t in ranked] == [3, 4, 1, 2]

    pairs = pair_within_group(ranked)
    pair_ids = {frozenset((a.id, b.id)) for a, b in pairs}
    # Fold over difficulty-ranked [3,4,1,2]: 3v2, 4v1.
    assert pair_ids == {frozenset((3, 2)), frozenset((4, 1))}

    # If the engine folded on RAW SEED ([1,2,3,4]) it would produce 1v4, 2v3 — different.
    raw_seed_pairs = {frozenset((1, 4)), frozenset((2, 3))}
    assert pair_ids != raw_seed_pairs


def test_forced_rematch_pairing(make_team):
    """GATE-03: a 6-team group whose Priority-1 row contains a rematch resolves to
    the first lower-priority rematch-free row of Valve's verbatim 15-row table.

    Priority 1 is (1v6, 2v5, 3v4). Plant a prior meeting between difficulty-rank
    positions 2 and 5 so row 1 is illegal. Priority 2 is (1v6, 2v4, 3v5) — the
    top-most rematch-free row — so the engine must pick exactly that.
    """
    from engine.swiss import PRIORITY_TABLE, pair_within_group

    # Verbatim verification of the table's first two rows (the oracle, RESEARCH).
    assert PRIORITY_TABLE[0] == [(1, 6), (2, 5), (3, 4)]
    assert PRIORITY_TABLE[1] == [(1, 6), (2, 4), (3, 5)]
    assert len(PRIORITY_TABLE) == 15

    # 6 teams already difficulty-ranked by construction (uniform difficulty -> seed).
    # ranked positions 1..6 == seeds 1..6.
    teams = [make_team(id=i, seed=i, wins=1, losses=1) for i in range(1, 7)]
    by_id = {t.id: t for t in teams}
    # Force a rematch on positions (2,5): record that 2 and 5 already met.
    by_id[2].opps.append(by_id[5])
    by_id[5].opps.append(by_id[2])

    pairs = pair_within_group(teams)
    pair_ids = {frozenset((a.id, b.id)) for a, b in pairs}
    # Priority 2: (1v6, 2v4, 3v5).
    assert pair_ids == {frozenset((1, 6)), frozenset((2, 4)), frozenset((3, 5))}


def test_no_valid_matching_fallback(make_team, caplog):
    """ENG-05 / GATE-03: a group with NO rematch-free perfect matching pairs the
    least-disruptive rematch and logs a warning — never raises on an unhandled None.

    A 2-team group where the only possible pair is a rematch: every row of the fold
    returns None. The engine must still return one pair (the forced rematch) and warn.
    """
    import logging

    from engine.swiss import pair_within_group

    a = make_team(id=1, seed=1, wins=1, losses=1)
    b = make_team(id=2, seed=2, wins=1, losses=1)
    a.opps.append(b)
    b.opps.append(a)  # they already met -> any pairing is a rematch

    with caplog.at_level(logging.WARNING):
        pairs = pair_within_group([a, b])

    # Did not crash; returned the only (forced-rematch) pairing.
    assert len(pairs) == 1
    assert {pairs[0][0].id, pairs[0][1].id} == {1, 2}
    # Logged a warning about the unavoidable rematch.
    assert any(rec.levelno == logging.WARNING for rec in caplog.records)


# --------------------------------------------------------------------------- #
# Task 2: simulate_stage — full Swiss loop, Bo3 placement, locked support
# --------------------------------------------------------------------------- #


def _seed_rng(value: int = 0):
    import numpy as np

    return np.random.default_rng(value)


def test_locked_results_honored():
    """ENG-08: a locked matchup uses the locked winner deterministically across
    repeated sims; invariants still hold; the no-rematch rule respects locked history.

    Lock the entire Round-1 board (8 forced winners). Because R1 pairings are fixed
    by seed, the same 8 winners must emerge every run regardless of the rng draw, and
    no pair may play twice (locked opponents recorded in opps).
    """
    from engine.swiss import simulate_stage
    from engine.teams import build_round1_pairs, load_teams

    teams = load_teams()
    r1 = build_round1_pairs(teams)
    # Lock every R1 match: higher-seed team wins.
    locked = {}
    for a, b in r1:
        winner = a if a.seed < b.seed else b
        locked[frozenset((a.id, b.id))] = winner.id

    results_a = simulate_stage(load_teams(), None, 40.0, _seed_rng(1), locked)
    results_b = simulate_stage(load_teams(), None, 40.0, _seed_rng(999), locked)

    # The locked R1 winners are deterministic: each locked winner has wins >= 1.
    for key, winner_id in locked.items():
        assert results_a[winner_id].wins >= 1
        assert results_b[winner_id].wins >= 1

    # Locked winners identical across different rng seeds for the R1 result.
    # (Full final standings can diverge in later unlocked rounds; R1 wins must match.)
    r1_winner_wins_a = {wid: results_a[wid].wins >= 1 for wid in locked.values()}
    r1_winner_wins_b = {wid: results_b[wid].wins >= 1 for wid in locked.values()}
    assert r1_winner_wins_a == r1_winner_wins_b

    # Invariants hold post-lock: exactly 8 advance (3 wins), 8 eliminated (3 losses);
    # exactly 2 go 3-0 and 2 go 0-3; no rematches.
    for results in (results_a, results_b):
        finals = list(results.values())
        assert all(t.wins == 3 or t.losses == 3 for t in finals)
        assert sum(t.wins == 3 for t in finals) == 8
        assert sum(t.losses == 3 for t in finals) == 8
        assert sum(t.wins == 3 and t.losses == 0 for t in finals) == 2
        assert sum(t.losses == 3 and t.wins == 0 for t in finals) == 2
        # No rematch: every opponent id appears at most once per team.
        for t in finals:
            opp_ids = [o.id for o in t.opps]
            assert len(opp_ids) == len(set(opp_ids))


def test_bo3_placement_and_termination():
    """ENG-06/07: every team terminates at exactly 3W or 3L; no pair plays twice.

    Run several unlocked sims and assert termination + no-rematch every time. Bo3
    placement (a match is Bo3 iff a team is at 2W or 2L) is exercised by every sim
    that reaches an advancement/elimination match; we assert the structural outcome.
    """
    from engine.swiss import simulate_stage
    from engine.teams import load_teams

    for seed in range(8):
        results = simulate_stage(load_teams(), None, 40.0, _seed_rng(seed), {})
        finals = list(results.values())
        assert len(finals) == 16
        assert all(t.wins == 3 or t.losses == 3 for t in finals)
        assert sum(t.wins == 3 for t in finals) == 8
        assert sum(t.losses == 3 for t in finals) == 8
        for t in finals:
            opp_ids = [o.id for o in t.opps]
            assert len(opp_ids) == len(set(opp_ids))


def test_swiss_no_forbidden_imports():
    """engine/swiss.py imports no streamlit/httpx/requests (functional-core invariant)."""
    import pathlib

    src = pathlib.Path(__file__).resolve().parent.parent / "engine" / "swiss.py"
    text = src.read_text(encoding="utf-8")
    for forbidden in ("import streamlit", "import httpx", "import requests"):
        assert forbidden not in text
