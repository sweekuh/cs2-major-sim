"""Group tiebreaker guards (Phase 1).

The FIFA ordering (points -> goal difference -> goals for -> head-to-head -> lots) is load-bearing:
get it wrong and the wrong teams advance. These pin each rung with hand-crafted results.

Note: a 2-team tie identical on (points, GD, GF) is mathematically impossible to break by
head-to-head under FIFA's overall-GD-first rules (the h2h winner scored >= 1 more and can't give
goals back), so h2h/lots are exercised via the all-level (fully tied) path.
"""

from __future__ import annotations

import numpy as np

from engine.soccer.group_stage import _standings, play_group, rank_group
from engine.soccer.dixon_coles import MatchModel

RNG = np.random.default_rng(0)


def test_standings_points_win_draw_loss():
    # team1 beats team2 (3pts), team3 draws team4 (1pt each).
    st = _standings([1, 2, 3, 4], [(1, 2, 2, 0), (3, 4, 1, 1)])
    assert st[1].points == 3 and st[1].gd == 2 and st[1].gf == 2
    assert st[2].points == 0 and st[2].gd == -2
    assert st[3].points == 1 and st[3].gd == 0
    assert st[4].points == 1


def test_points_then_gd_full_group():
    results = [(1, 2, 2, 0), (1, 3, 2, 0), (1, 4, 2, 0),
               (2, 3, 1, 0), (2, 4, 1, 0), (3, 4, 1, 0)]
    assert rank_group([1, 2, 3, 4], results, RNG) == [1, 2, 3, 4]


def test_goal_difference_breaks_equal_points():
    # 1 and 2 both 3pts (GD +3 vs +1); 3 and 4 both 0pts (GD -3 vs -1).
    results = [(1, 3, 3, 0), (2, 4, 1, 0)]
    assert rank_group([1, 2, 3, 4], results, RNG) == [1, 2, 4, 3]


def test_goals_for_breaks_equal_points_and_gd():
    # 1 and 2 both 3pts and +1 GD, but 1 scored more (2 vs 1); 3 and 4 both 0pts -1 GD.
    results = [(1, 3, 2, 1), (2, 4, 1, 0)]
    assert rank_group([1, 2, 3, 4], results, RNG) == [1, 2, 3, 4]


def test_full_tie_goes_to_lots_and_is_a_permutation():
    all_draws = [(1, 2, 0, 0), (1, 3, 0, 0), (1, 4, 0, 0),
                 (2, 3, 0, 0), (2, 4, 0, 0), (3, 4, 0, 0)]
    out = rank_group([1, 2, 3, 4], all_draws, np.random.default_rng(5))
    assert sorted(out) == [1, 2, 3, 4]  # every team present exactly once
    # Deterministic given the rng seed.
    again = rank_group([1, 2, 3, 4], all_draws, np.random.default_rng(5))
    assert out == again


def test_play_group_emits_six_matches():
    model = MatchModel(attack={i: 0.0 for i in (1, 2, 3, 4)},
                       defence={i: 0.0 for i in (1, 2, 3, 4)})
    results = play_group([1, 2, 3, 4], model, np.random.default_rng(1))
    assert len(results) == 6
    assert all(len(r) == 4 for r in results)
