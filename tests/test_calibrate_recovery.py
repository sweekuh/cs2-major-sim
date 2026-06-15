"""Calibration recovery guard (Phase 1) — mirrors test_backsolve.py::test_rating_roundtrip.

Build a KNOWN model, generate de-vigged 1X2 targets from it, calibrate from a neutral prior, and
assert (1) the fit reprices every target and (2) it recovers the gauge-invariant attack/defence
DIFFERENCES vs the anchor. This is the proof the synthesis hinge actually works.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from engine.soccer.calibrate import (
    IMPORTANCE,
    build_match_weights,
    build_model,
    calibrate_strengths,
    fit_elo_scale,
    match_weight,
    time_decay,
)
from engine.soccer.dixon_coles import MatchModel, match_1x2, strengths_from_elo
from engine.soccer.teams import SoccerTeam

IDS = [1, 2, 3, 4, 5]
TRUE = MatchModel(
    attack={1: 0.0, 2: 0.30, 3: -0.20, 4: 0.15, 5: -0.10},
    defence={1: 0.0, 2: 0.20, 3: -0.25, 4: 0.10, 5: 0.05},
    home_adv=0.0, base=0.3, rho=-0.05,
)
ANCHOR = 1


def _targets():
    # Full double round-robin gives enough independent equations to identify the strengths.
    return {(h, a): match_1x2(TRUE, h, a, neutral=True)
            for h, a in itertools.permutations(IDS, 2)}


def test_recovery_reprices_targets():
    prior = MatchModel(attack={i: 0.0 for i in IDS}, defence={i: 0.0 for i in IDS},
                       home_adv=0.0, base=0.3, rho=-0.05)
    fit = calibrate_strengths(prior, _targets(), anchor_id=ANCHOR, iters=80)
    for (h, a), tgt in _targets().items():
        got = match_1x2(fit, h, a, neutral=True)
        assert got == pytest.approx(tgt, abs=5e-3)


def test_recovery_matches_gauge_invariant_differences():
    prior = MatchModel(attack={i: 0.0 for i in IDS}, defence={i: 0.0 for i in IDS},
                       home_adv=0.0, base=0.3, rho=-0.05)
    fit = calibrate_strengths(prior, _targets(), anchor_id=ANCHOR, iters=80)
    for t in IDS:
        # Differences vs the anchor are gauge-invariant and should match the truth.
        assert (fit.attack[t] - fit.attack[ANCHOR]) == pytest.approx(
            TRUE.attack[t] - TRUE.attack[ANCHOR], abs=3e-2)
        assert (fit.defence[t] - fit.defence[ANCHOR]) == pytest.approx(
            TRUE.defence[t] - TRUE.defence[ANCHOR], abs=3e-2)


def test_time_decay_halves_at_half_life():
    assert time_decay(0) == pytest.approx(1.0)
    assert time_decay(365, 365) == pytest.approx(0.5)
    assert time_decay(730, 365) == pytest.approx(0.25)


def test_match_weight_importance_ordering():
    assert IMPORTANCE["world_cup"] > IMPORTANCE["qualifier"] > IMPORTANCE["friendly"]
    # Same recency, a World Cup match outweighs a friendly.
    assert match_weight(10, "world_cup") > match_weight(10, "friendly")
    # Unknown competition falls back to recency only (multiplier 1.0).
    assert match_weight(0, "mystery_cup") == pytest.approx(1.0)


def test_build_match_weights_shape():
    w = build_match_weights([
        {"home_id": 1, "away_id": 2, "days_ago": 0, "competition": "world_cup"},
        {"home_id": 3, "away_id": 4, "days_ago": 365, "competition": "friendly"},
    ])
    assert w[(1, 2)] == pytest.approx(4.0)         # 1.0 recency x 4.0 importance
    assert w[(3, 4)] == pytest.approx(0.5)         # 0.5 recency x 1.0 importance


def test_calibration_respects_weights():
    # Two contradictory targets about whether team 1 or team 2 is stronger; the up-weighted one wins.
    prior = MatchModel(attack={1: 0.0, 2: 0.0}, defence={1: 0.0, 2: 0.0}, home_adv=0.0, base=0.3, rho=-0.05)
    targets = {(1, 2): (0.70, 0.20, 0.10),   # team 1 strongly favoured
               (2, 1): (0.70, 0.20, 0.10)}   # team 2 strongly favoured (neutral -> contradictory)

    favour_1 = calibrate_strengths(prior, targets, anchor_id=1, iters=60,
                                   weights={(1, 2): 10.0, (2, 1): 1.0})
    favour_2 = calibrate_strengths(prior, targets, anchor_id=1, iters=60,
                                   weights={(1, 2): 1.0, (2, 1): 10.0})
    p1_when_1 = match_1x2(favour_1, 1, 2, neutral=True)[0]
    p1_when_2 = match_1x2(favour_2, 1, 2, neutral=True)[0]
    assert p1_when_1 > 0.5 > p1_when_2  # weighting pulls the fit toward the heavier match


def test_shrinkage_keeps_sparse_team_near_prior():
    # A single strong target pushes team 2's strength far from the prior; shrinkage reins it in.
    prior = MatchModel(attack={1: 0.0, 2: 0.0}, defence={1: 0.0, 2: 0.0}, home_adv=0.0, base=0.3, rho=-0.05)
    target = {(1, 2): (0.85, 0.10, 0.05)}  # team 1 heavily favoured -> team 2 strength wants to drop
    free = calibrate_strengths(prior, target, anchor_id=1, iters=60, shrinkage=0.0)
    shrunk = calibrate_strengths(prior, target, anchor_id=1, iters=60, shrinkage=5.0)
    assert abs(shrunk.attack[2]) < abs(free.attack[2])   # shrinkage pulls toward the prior (0)
    assert abs(shrunk.attack[2]) < abs(free.attack[2]) * 0.6


def test_fit_elo_scale_recovers_known_spread():
    teams = [SoccerTeam(id=i, name=f"T{i}", group="A", elo=elo)
             for i, elo in enumerate([2100, 1950, 1800, 1650, 1500], start=1)]
    true_scale = 400.0
    truth = strengths_from_elo(teams, elo_per_goal=true_scale)
    targets = {(h, a): match_1x2(truth, h, a, neutral=True)
               for h, a in itertools.permutations([t.id for t in teams], 2)}
    fit = fit_elo_scale(teams, targets, neutral=True)
    assert fit == pytest.approx(true_scale, rel=0.1)


def test_fit_elo_scale_empty_targets_returns_midpoint_not_bound():
    teams = [SoccerTeam(id=1, name="A", group="A", elo=1800)]
    assert fit_elo_scale(teams, {}, lo=50.0, hi=3000.0) == pytest.approx(1525.0)


def test_fit_elo_scale_handles_extreme_target_without_nan():
    # A near-certain market with a big Elo gap forces tiny scales into the Poisson-overflow zone;
    # the NaN-safe loss + uniform scoreline fallback must keep the fit finite and in-range.
    teams = [SoccerTeam(id=1, name="Strong", group="A", elo=2100),
             SoccerTeam(id=2, name="Weak", group="A", elo=1300)]
    fit = fit_elo_scale(teams, {(1, 2): (0.999, 0.0009, 0.0001)}, lo=50.0, hi=3000.0)
    assert 50.0 <= fit <= 3000.0 and fit == fit  # finite, in range (fit==fit rejects NaN)


def test_fit_elo_scale_larger_when_market_less_confident():
    teams = [SoccerTeam(id=1, name="Strong", group="A", elo=2100),
             SoccerTeam(id=2, name="Weak", group="A", elo=1500)]
    # A near-even market (50/27/23) implies a MUCH wider spread than the Elo gap suggests.
    fit = fit_elo_scale(teams, {(1, 2): (0.50, 0.27, 0.23)}, neutral=True)
    assert fit > 250.0  # bigger scale = less confident than the default


def test_build_model_no_targets_is_elo_prior():
    teams = [SoccerTeam(id=1, name="A", group="A", elo=2000), SoccerTeam(id=2, name="B", group="A", elo=1600)]
    m = build_model(teams)
    ref = strengths_from_elo(teams)
    assert match_1x2(m, 1, 2, neutral=True) == pytest.approx(match_1x2(ref, 1, 2, neutral=True))


def test_build_model_calibrates_covered_teams_to_market():
    teams = [SoccerTeam(id=i, name=f"T{i}", group="A", elo=elo)
             for i, elo in enumerate([2100, 1950, 1800, 1650, 1500], start=1)]
    truth = strengths_from_elo(teams, elo_per_goal=500.0)  # a wider (less confident) true spread
    targets = {(h, a): match_1x2(truth, h, a, neutral=True)
               for h, a in itertools.permutations([t.id for t in teams], 2)}
    m = build_model(teams, targets, shrinkage=0.0)  # full calibration
    for (h, a), tgt in targets.items():
        assert match_1x2(m, h, a, neutral=True) == pytest.approx(tgt, abs=8e-3)


def test_calibrate_rejects_unknown_anchor():
    prior = MatchModel(attack={1: 0.0, 2: 0.0}, defence={1: 0.0, 2: 0.0}, home_adv=0.0, base=0.3, rho=-0.05)
    with pytest.raises(ValueError):
        calibrate_strengths(prior, {(1, 2): (0.5, 0.3, 0.2)}, anchor_id=999)


def test_anchor_held_fixed():
    prior = MatchModel(attack={i: 0.5 for i in IDS}, defence={i: 0.5 for i in IDS},
                       home_adv=0.0, base=0.3, rho=-0.05)
    fit = calibrate_strengths(prior, _targets(), anchor_id=ANCHOR, iters=10)
    assert fit.attack[ANCHOR] == prior.attack[ANCHOR]
    assert fit.defence[ANCHOR] == prior.defence[ANCHOR]
