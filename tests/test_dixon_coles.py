"""Dixon-Coles match-model guards (Phase 1).

Pins the goals-model invariants the whole fair-value engine rests on: proper 1X2 simplex,
favourite ordering, the low-score (draw) correction actually raising draw mass, and the scoreline
sampler matching its own distribution.
"""

from __future__ import annotations

import numpy as np
import pytest

from engine.soccer.dixon_coles import (
    MatchModel,
    expected_goals,
    match_1x2,
    outcome_1x2,
    sample_score,
    scoreline_matrix,
    strengths_from_elo,
)
from engine.soccer.teams import SoccerTeam

# Two-team model: team 1 strong, team 2 weak.
MODEL = MatchModel(attack={1: 0.4, 2: -0.4}, defence={1: 0.4, 2: -0.4}, home_adv=0.3, base=0.3, rho=-0.05)


def test_expected_goals_equal_strength_equal_lambda():
    m = MatchModel(attack={1: 0.0, 2: 0.0}, defence={1: 0.0, 2: 0.0}, base=0.3)
    lam_h, lam_a = expected_goals(m, 1, 2, neutral=True)
    assert lam_h == pytest.approx(lam_a)
    assert lam_h == pytest.approx(np.exp(0.3))


def test_home_adv_only_applies_off_neutral():
    neutral = expected_goals(MODEL, 1, 2, neutral=True)
    home = expected_goals(MODEL, 1, 2, neutral=False)
    assert home[0] > neutral[0]      # home λ boosted off-neutral
    assert home[1] == pytest.approx(neutral[1])  # away λ unchanged


def test_scoreline_matrix_is_a_distribution():
    m = scoreline_matrix(1.6, 1.1, rho=-0.05)
    assert m.sum() == pytest.approx(1.0)
    assert (m >= 0).all()


def test_outcome_1x2_sums_to_one_and_favours_stronger():
    p_home, p_draw, p_away = match_1x2(MODEL, 1, 2, neutral=True)
    assert p_home + p_draw + p_away == pytest.approx(1.0)
    assert p_home > p_away  # team 1 stronger


def test_symmetric_match_is_symmetric():
    m = MatchModel(attack={1: 0.1, 2: 0.1}, defence={1: 0.1, 2: 0.1}, base=0.3, rho=-0.05)
    p_home, _, p_away = match_1x2(m, 1, 2, neutral=True)
    assert p_home == pytest.approx(p_away, abs=1e-9)


def test_dixon_coles_correction_raises_draw_probability():
    lam_h, lam_a = 1.3, 1.2
    p_draw_indep = outcome_1x2(scoreline_matrix(lam_h, lam_a, rho=0.0))[1]
    p_draw_dc = outcome_1x2(scoreline_matrix(lam_h, lam_a, rho=-0.05))[1]
    assert p_draw_dc > p_draw_indep  # negative rho inflates 0-0 and 1-1


def test_sample_score_matches_distribution():
    rng = np.random.default_rng(0)
    lam_h, lam_a = 1.5, 1.0
    n = 40_000
    home_goals = np.empty(n)
    home_wins = 0
    for i in range(n):
        h, a = sample_score(lam_h, lam_a, rng, rho=0.0)
        home_goals[i] = h
        home_wins += h > a
    assert home_goals.mean() == pytest.approx(lam_h, abs=0.05)  # Poisson mean (rho=0)
    p_home_theory = outcome_1x2(scoreline_matrix(lam_h, lam_a, rho=0.0))[0]
    assert home_wins / n == pytest.approx(p_home_theory, abs=0.02)


def test_strengths_from_elo_orders_quality():
    teams = [
        SoccerTeam(id=1, name="Strong", group="A", elo=2000),
        SoccerTeam(id=2, name="Weak", group="A", elo=1500),
    ]
    m = strengths_from_elo(teams)
    assert m.attack[1] > m.attack[2]
    assert m.defence[1] > m.defence[2]
    # Stronger team should be favoured head-to-head.
    p_home, _, p_away = match_1x2(m, 1, 2, neutral=True)
    assert p_home > p_away
