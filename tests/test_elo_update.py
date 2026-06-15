"""Elo-update (results -> model feedback) guards."""

from __future__ import annotations

import pytest

from engine.soccer.elo_update import (
    apply_results,
    expected_score,
    gd_multiplier,
    update_one,
)


def test_expected_score_symmetry_and_order():
    assert expected_score(1800, 1800) == pytest.approx(0.5)
    assert expected_score(2000, 1600) > 0.5
    assert expected_score(1600, 2000) < 0.5
    # Home advantage lifts the home expectation.
    assert expected_score(1800, 1800, home_adv=100) > 0.5


def test_gd_multiplier_steps():
    assert gd_multiplier(0) == 1.0
    assert gd_multiplier(1) == 1.0
    assert gd_multiplier(-1) == 1.0
    assert gd_multiplier(2) == 1.5
    assert gd_multiplier(3) == pytest.approx(1.75)
    assert gd_multiplier(5) == pytest.approx(2.0)


def test_update_is_zero_sum():
    eh, ea = update_one(1900, 1700, 2, 0)
    assert (eh - 1900) == pytest.approx(-(ea - 1700))


def test_favourite_win_small_underdog_win_big():
    # Favourite (1900) beating underdog (1700) by the same margin earns FEWER points than the
    # underdog would for the same upset win.
    fav_gain = update_one(1900, 1700, 1, 0)[0] - 1900
    dog_gain = update_one(1700, 1900, 1, 0)[0] - 1700
    assert 0 < fav_gain < dog_gain


def test_draw_costs_the_favourite():
    eh, ea = update_one(2000, 1600, 1, 1)  # strong home only draws -> loses Elo
    assert eh < 2000 and ea > 1600


def test_apply_results_moves_winner_up_loser_down_and_is_pure():
    elos = {1: 1880, 2: 1730}  # Mexico, South Africa
    updated = apply_results(elos, [(1, 2, 2, 0)])
    assert updated[1] > 1880 and updated[2] < 1730
    assert elos == {1: 1880, 2: 1730}  # original untouched (returns a new dict)


def test_apply_results_skips_unknown_ids():
    elos = {1: 1800}
    assert apply_results(elos, [(1, 99, 3, 0)]) == elos  # unknown away id -> skipped
