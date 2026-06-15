"""Per-match prediction + EV guards."""

from __future__ import annotations

import pytest

from engine.soccer.dixon_coles import MatchModel
from monitor.match_edge import decimal_ev, kalshi_ev, match_prediction

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
