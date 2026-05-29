"""Math-correctness guards for engine.probs (and the canonical difficulty()).

These target code that lands in THIS plan (wave 1) and must PASS — they are NOT
xfail. They are the only tests that catch the silent-corruption bugs the
structural invariants miss (Buchholz wins-minus-losses, Bo3 closed form).
"""

from __future__ import annotations

import math

from engine.probs import beta_moment_fit, difficulty, epistemic_draws, p_map, series, series_prob


def test_p_map():
    """Logistic map-win probability; equal ratings -> 0.5, favorite > 0.5 (PROB-01)."""
    assert p_map(50.0, 50.0) == 0.5
    assert p_map(50.0, 50.0, S=40.0) == 0.5
    # Higher-rated team is favored.
    assert p_map(92.0, 40.0) > 0.5
    assert p_map(40.0, 92.0) < 0.5
    # Matches the closed-form logistic exactly.
    ra, rb, S = 92.0, 40.0, 40.0
    assert math.isclose(p_map(ra, rb, S=S), 1.0 / (1.0 + 10 ** (-(ra - rb) / S)))
    # Symmetry: p_map(a,b) + p_map(b,a) == 1.
    assert math.isclose(p_map(70.0, 55.0) + p_map(55.0, 70.0), 1.0)


def test_bo3():
    """Bo3 closed form p^2(3-2p); Bo1 identity (MC-06). Hand-computed points."""
    assert math.isclose(series(0.6, bo3=True), 0.648)
    assert math.isclose(series(0.5, bo3=True), 0.5)
    assert series(0.6, bo3=False) == 0.6
    assert series(0.5, bo3=False) == 0.5
    # Bo3 sharpens favorites: p>0.5 -> series>p; p<0.5 -> series<p.
    assert series(0.6, bo3=True) > 0.6
    assert series(0.4, bo3=True) < 0.4
    # Endpoints are fixed.
    assert series(1.0, bo3=True) == 1.0
    assert series(0.0, bo3=True) == 0.0


def test_difficulty_formula(make_team):
    """Valve's worked example: opponents 2-0 and 1-1 -> difficulty 2 (ENG-03/GATE-02).

    This is THE test that catches the sum(o.wins) vs sum(o.wins - o.losses) bug,
    which passes every structural invariant while corrupting all probabilities.
    """
    opp_2_0 = make_team(id=101, wins=2, losses=0)
    opp_1_1 = make_team(id=102, wins=1, losses=1)
    team = make_team(id=1, opps=[opp_2_0, opp_1_1])
    # (2 + 1) - (0 + 1) == 2, NOT (2 + 1) == 3.
    assert difficulty(team) == 2

    # Valve's Team B worked example: both opponents 1-1 -> difficulty 0.
    team_b = make_team(id=2, opps=[make_team(id=103, wins=1, losses=1), make_team(id=104, wins=1, losses=1)])
    assert difficulty(team_b) == 0


def test_odds_override_passthrough():
    """An explicit market series prob is used directly; Bo3 NOT re-applied (PROB-02)."""
    # When a market series prob is supplied, it passes through untouched even for a Bo3
    # matchup — the market already prices the series.
    assert series_prob(ra=92.0, rb=40.0, bo3=True, market_series_prob=0.73) == 0.73
    assert series_prob(ra=92.0, rb=40.0, bo3=False, market_series_prob=0.73) == 0.73
    # No market prob -> fall back to series(p_map(...), bo3). For equal ratings p_map=0.5,
    # Bo3 of 0.5 is still 0.5.
    assert math.isclose(series_prob(ra=50.0, rb=50.0, bo3=True, market_series_prob=None), 0.5)
    # Bo3 fallback applies the closed form: p_map favorite then p^2(3-2p).
    p = p_map(60.0, 50.0)
    assert math.isclose(series_prob(ra=60.0, rb=50.0, bo3=True, market_series_prob=None), p * p * (3 - 2 * p))


def test_epistemic_stub_and_beta_clamp():
    """Phase 1 epistemic outer loop yields exactly ONE draw; Beta MoM clamps var < p(1-p).

    The reported band collapses to the inner Wilson band for a single source
    (PROB-03/04/05). This guards the Phase-5 seam: the loop is OUTER now so Phase 5
    fills K Beta draws without a rewrite.
    """
    blend = [0.6, 0.4, 0.55]
    var = [0.0, 0.0, 0.0]
    draws = list(epistemic_draws(blend, var))
    # Exactly one point draw in Phase 1 (single-source no-op).
    assert len(draws) == 1
    assert list(draws[0]) == blend

    # beta_moment_fit clamps var < mean*(1-mean) so Beta params stay positive.
    a, b = beta_moment_fit(0.5, 1.0)  # absurd var=1.0 must be clamped below 0.25
    assert a > 0 and b > 0
    # A reasonable in-range variance produces sane Beta params (mean recovered).
    mean, v = 0.6, 0.02
    a2, b2 = beta_moment_fit(mean, v)
    assert a2 > 0 and b2 > 0
    assert math.isclose(a2 / (a2 + b2), mean, abs_tol=1e-9)
