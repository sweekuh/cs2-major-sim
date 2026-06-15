"""Feed finished results back into the model via the World Football Elo update.

After a match finishes, its scoreline should revise the two teams' strengths. We use the standard
World Football Elo update (eloratings.net): a goal-difference multiplier, a home/neutral term, and
a match-importance K (World Cup K = 60). The update is zero-sum (the winner gains exactly what the
loser concedes), so applying a sequence of results just re-weights the field; ``build_model`` then
rebuilds the goals model from the updated Elo. Base Elo is never mutated in place — ``apply_results``
returns a NEW dict — so the feedback step is reproducible and reversible.

Pure: math + an id-keyed Elo dict, no I/O.
"""

from __future__ import annotations

WORLD_CUP_K = 60.0      # match-importance K for a World Cup (World Football Elo convention)
HOME_ADV_ELO = 100.0    # home advantage in Elo points (~ the eloratings.net value)


def expected_score(elo_a: float, elo_b: float, *, home_adv: float = 0.0) -> float:
    """Elo expected score for A vs B (0..1), with optional home advantage added to A's rating."""
    return 1.0 / (1.0 + 10 ** (-((elo_a + home_adv) - elo_b) / 400.0))


def gd_multiplier(goal_diff: int) -> float:
    """World Football Elo goal-difference multiplier: 1 for a 0/1-goal margin, 1.5 for 2, then
    ``(11 + |gd|) / 8`` for 3+ (a 3-0 -> 1.75, a 4-0 -> 1.875)."""
    g = abs(goal_diff)
    if g <= 1:
        return 1.0
    if g == 2:
        return 1.5
    return (11 + g) / 8.0


def update_one(elo_home: float, elo_away: float, home_goals: int, away_goals: int,
               *, k: float = WORLD_CUP_K, home_adv: float = 0.0) -> tuple[float, float]:
    """Updated (elo_home, elo_away) after one result. Zero-sum: home delta = -away delta."""
    we = expected_score(elo_home, elo_away, home_adv=home_adv)
    w = 1.0 if home_goals > away_goals else (0.5 if home_goals == away_goals else 0.0)
    delta = k * gd_multiplier(home_goals - away_goals) * (w - we)
    return elo_home + delta, elo_away - delta


def apply_results(elos: dict[int, float], results, *, k: float = WORLD_CUP_K,
                  hosts=frozenset(), home_adv_elo: float = HOME_ADV_ELO) -> dict[int, float]:
    """Fold a sequence of ``(home_id, away_id, home_goals, away_goals)`` into a NEW Elo dict.

    A host playing a non-host at home gets ``home_adv_elo`` in the expectation (so beating a weaker
    side at home earns slightly fewer points, as it should). Unknown team ids are skipped.
    """
    out = dict(elos)
    for home, away, hg, ag in results:
        if home not in out or away not in out:
            continue
        ha = home_adv_elo if (home in hosts and away not in hosts) else 0.0
        out[home], out[away] = update_one(out[home], out[away], hg, ag, k=k, home_adv=ha)
    return out
