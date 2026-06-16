"""Playoff 7-pick optimizer tests (PLAY-02) — ballot validity, enumeration, optimum, coin math."""

from __future__ import annotations

import pytest

from engine.bracket import run_playoff_mc
from engine.playoff_optimizer import (
    PlayoffBallot,
    build_win_matrices,
    e_points,
    enumerate_ballots,
    optimize_playoffs,
    p_coin,
)
from engine.teams import Team


def _teams(ratings: dict[int, float] | None = None) -> list[Team]:
    ratings = ratings or {i: 50.0 for i in range(1, 9)}
    return [Team(id=i, name=f"T{i}", seed=i, rating=ratings[i]) for i in range(1, 9)]


# --- ballot validity ----------------------------------------------------------------------
def test_ballot_enforces_bracket_consistency():
    # QF winners 1,4,2,3; SF1 from {1,4}, SF2 from {2,3}; champ from SF picks — valid.
    PlayoffBallot((1, 4, 2, 3), (1, 2), 1)
    # SF1 pick not among its feeder QF picks -> reject.
    with pytest.raises(ValueError):
        PlayoffBallot((1, 4, 2, 3), (5, 2), 1)
    # Champion not among SF picks -> reject.
    with pytest.raises(ValueError):
        PlayoffBallot((1, 4, 2, 3), (1, 2), 4)


def test_picks_by_label_round_trips():
    b = PlayoffBallot((1, 4, 2, 3), (4, 3), 3)
    assert b.picks_by_label() == {
        "QF1": 1, "QF2": 4, "QF3": 2, "QF4": 3, "SF1": 4, "SF2": 3, "GF": 3
    }


def test_enumerate_yields_128_distinct_valid_ballots():
    ballots = enumerate_ballots(_teams())
    assert len(ballots) == 128  # 2^4 QF x 2 SF x 2 SF x 2 champion
    assert len(set(ballots)) == 128  # all distinct (frozen dataclass is hashable)


# --- scoring against the sample -----------------------------------------------------------
def test_e_points_and_pcoin_on_a_pinned_sample():
    # A degenerate sample where team ids 1,4,2,3 win their QFs every sim, 1 and 2 win SFs, 1 champ.
    sample = [
        {"QF1": 1, "QF2": 4, "QF3": 2, "QF4": 3, "SF1": 1, "SF2": 2, "GF": 1}
    ] * 100
    ids = list(range(1, 9))
    matrices = build_win_matrices(sample, ids)
    marginals = {label: {i: float(a.mean()) for i, a in by.items()} for label, by in matrices.items()}
    perfect = PlayoffBallot((1, 4, 2, 3), (1, 2), 1)
    # Perfect ballot: all 4 QF + 2 SF + champion correct -> E[points] = 4*1 + 2*2 + 1*3 = 11.
    assert e_points(perfect, marginals) == pytest.approx(11.0)
    assert p_coin(perfect, matrices) == pytest.approx(1.0)  # tiers all cleared every sim
    # A ballot wrong on the champion (and one SF) still clears 2 QF + ... but fails the GF tier.
    wrong_champ = PlayoffBallot((1, 4, 2, 3), (1, 2), 2)
    assert p_coin(wrong_champ, matrices) == pytest.approx(0.0)  # champion never correct


# --- optimize_playoffs --------------------------------------------------------------------
def test_optimizer_picks_the_dominant_favorite_as_champion():
    # Seed 1 hugely strong -> recommended (max-E[points]) champion should be id 1.
    res = run_playoff_mc(_teams({**{i: 50.0 for i in range(1, 9)}, 1: 250.0}), None, 40.0, 8000, seed=2)
    out = optimize_playoffs(res, _teams({**{i: 50.0 for i in range(1, 9)}, 1: 250.0}))
    assert out.recommended.champion == 1
    assert out.champion == 1
    assert out.p_champion > 0.5


def test_optimizer_recommends_the_expected_points_ballot():
    teams = _teams({1: 90, 2: 60, 3: 70, 4: 80, 5: 88, 6: 55, 7: 50, 8: 58})
    res = run_playoff_mc(teams, None, 40.0, 8000, seed=11)
    out = optimize_playoffs(res, teams)
    # Recommendation == the E[points]-optimal ballot; its expected score is the hero number.
    assert out.recommended is out.ballot_points
    assert out.recommended_e_points == pytest.approx(out.e_points_points)
    # The points ballot maximizes E[points]; the coin ballot maximizes P(coin) — each best at its own.
    assert out.e_points_points >= out.e_points_coin - 1e-9
    assert out.pcoin_coin >= out.pcoin_points - 1e-12
    # Hero score is within [0, max_points] (max = 4*1 + 2*2 + 1*3 = 11 with the defaults).
    assert out.max_points == pytest.approx(11.0)
    assert 0.0 <= out.recommended_e_points <= out.max_points + 1e-9
    # The recommended ballot's reported coin/tier odds are valid probabilities, coin <= each tier.
    for t in (out.tier_qf, out.tier_sf, out.tier_gf):
        assert 0.0 <= t <= 1.0
    assert out.recommended_pcoin <= min(out.tier_qf, out.tier_sf, out.tier_gf) + 1e-9


def test_optimizer_is_deterministic():
    teams = _teams({1: 90, 2: 60, 3: 70, 4: 80, 5: 88, 6: 55, 7: 50, 8: 58})
    res = run_playoff_mc(teams, None, 40.0, 6000, seed=4)
    a = optimize_playoffs(res, teams)
    b = optimize_playoffs(res, teams)
    assert a.recommended == b.recommended
    assert a.ballot_points == b.ballot_points
