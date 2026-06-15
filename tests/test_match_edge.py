"""Per-match prediction + EV guards."""

from __future__ import annotations

import pytest

from engine.soccer.calibrate import calibrate_strengths
from engine.soccer.dixon_coles import MatchModel, match_1x2, strengths_from_elo
from engine.soccer.teams import SoccerTeam
from monitor.match_edge import (
    decimal_ev,
    kalshi_ev,
    market_targets,
    match_prediction,
    results_to_tuples,
)
from odds._match import build_name_to_id

# Team 1 clearly stronger than team 2.
MODEL = MatchModel(attack={1: 0.4, 2: -0.4}, defence={1: 0.4, 2: -0.4}, home_adv=0.3, base=0.3, rho=-0.05)


def test_prediction_picks_favorite_and_sums_to_one():
    pred = match_prediction(MODEL, 1, 2, neutral=True)
    assert pred["pick"] == "home"
    assert sum(pred["probs"].values()) == pytest.approx(1.0)
    assert pred["pick_prob"] == pred["probs"]["home"]


def test_decimal_ev_sign():
    # True prob 0.60 at 2.0 decimal -> EV = 0.6*2 - 1 = +0.20.
    assert decimal_ev(0.60, 2.0) == pytest.approx(0.20)
    # True prob 0.40 at 2.0 -> -0.20 (-EV).
    assert decimal_ev(0.40, 2.0) == pytest.approx(-0.20)


def test_kalshi_ev_nets_the_fee():
    # YES at 0.50, true 0.60: gross 0.10, minus 2c fee at 0.50 -> 0.08.
    assert kalshi_ev(0.60, 0.50) == pytest.approx(0.08)
    # No edge -> negative after fee.
    assert kalshi_ev(0.51, 0.50) < 0


_TEAMS = [SoccerTeam(id=1, name="France", group="I", elo=2063),
          SoccerTeam(id=2, name="Senegal", group="I", elo=1869)]
_FIX = [{"home": "France", "away": "Senegal", "odds": {"home": 1.45, "draw": 4.50, "away": 6.50}}]


def test_market_targets_devigs_and_keys_by_id():
    t = market_targets(_FIX, build_name_to_id(_TEAMS))
    assert (1, 2) in t
    assert sum(t[(1, 2)]) == pytest.approx(1.0)
    assert t[(1, 2)][0] > t[(1, 2)][2]  # France favoured


def test_market_targets_skips_partial_or_unresolved():
    n2i = build_name_to_id(_TEAMS)
    assert market_targets([{"home": "France", "away": "Senegal", "odds": {"home": 1.45}}], n2i) == {}
    assert market_targets([{"home": "Atlantis", "away": "Senegal",
                            "odds": {"home": 2, "draw": 3, "away": 4}}], n2i) == {}


def test_market_targets_skips_invalid_odds_without_crashing():
    n2i = build_name_to_id(_TEAMS)
    # Negative and sub-1.0 are not valid decimal odds -> skipped (would otherwise crash the de-vig).
    assert market_targets([{"home": "France", "away": "Senegal",
                            "odds": {"home": -1.45, "draw": 4.5, "away": 6.5}}], n2i) == {}
    assert market_targets([{"home": "France", "away": "Senegal",
                            "odds": {"home": 0.5, "draw": 4.5, "away": 6.5}}], n2i) == {}


def test_results_to_tuples_resolves_and_skips():
    n2i = build_name_to_id(_TEAMS)  # France=1, Senegal=2
    matches = [
        {"home": "France", "away": "Senegal", "home_goals": 2, "away_goals": 1},   # ok
        {"home": "France", "away": "Senegal", "home_goals": None, "away_goals": 1},  # no score -> skip
        {"home": "Atlantis", "away": "Senegal", "home_goals": 1, "away_goals": 0},   # unresolved -> skip
    ]
    assert results_to_tuples(matches, n2i) == [(1, 2, 2, 1)]


def test_calibration_collapses_overconfidence_toward_market():
    n2i = build_name_to_id(_TEAMS)
    targets = market_targets(_FIX, n2i)
    prior = strengths_from_elo(_TEAMS)            # France >> Senegal by Elo -> overconfident
    cal = calibrate_strengths(prior, targets, anchor_id=1, shrinkage=0.0, neutral=True)
    market = targets[(1, 2)][0]
    before = match_1x2(prior, 1, 2, neutral=True)[0]
    after = match_1x2(cal, 1, 2, neutral=True)[0]
    assert abs(after - market) < abs(before - market)   # moved toward the market
    assert abs(after - market) < 0.05                    # and lands close to it
