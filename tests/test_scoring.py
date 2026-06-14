"""Scoring-rule + reliability guards (Phase 1).

Pins the proper-scoring-rule behaviour (perfect=0, ordinal RPS) and that the reliability diagram
recovers a known calibration.
"""

from __future__ import annotations

import math

import pytest

from engine.soccer.scoring import (
    brier,
    log_loss,
    outcome_index,
    reliability_bins,
    rps,
    score_set,
)


def test_outcome_index():
    assert outcome_index(2, 0) == 0
    assert outcome_index(1, 1) == 1
    assert outcome_index(0, 3) == 2


def test_perfect_prediction_scores_zero():
    p = (1.0, 0.0, 0.0)
    assert log_loss(p, 0) == pytest.approx(0.0, abs=1e-9)
    assert brier(p, 0) == pytest.approx(0.0)
    assert rps(p, 0) == pytest.approx(0.0)


def test_confident_wrong_is_heavily_penalized():
    assert log_loss((0.98, 0.01, 0.01), 2) > 4.0  # ~ -ln(0.01)


def test_rps_rewards_nearer_miss():
    # Actual = away. Predicting all-draw (adjacent) beats predicting all-home (far).
    assert rps((0.0, 1.0, 0.0), 2) < rps((1.0, 0.0, 0.0), 2)


def test_score_set_aggregates():
    preds = [(1.0, 0.0, 0.0), (0.0, 0.0, 1.0)]
    outs = [0, 2]
    s = score_set(preds, outs)
    assert s["n"] == 2
    assert s["log_loss"] == pytest.approx(0.0, abs=1e-9)


def test_reliability_recovers_known_calibration():
    # 100 forecasts of (0.50, 0.25, 0.25); outcomes home 50% / draw 25% / away 25% -> perfectly
    # calibrated: the 0.50 slots occur 50% of the time, the 0.25 slots 25%.
    preds = [(0.50, 0.25, 0.25)] * 100
    outs = [0] * 50 + [1] * 25 + [2] * 25
    bins = reliability_bins(preds, outs, n_bins=10)
    by_pred = {round(b["mean_pred"], 2): b for b in bins}
    assert by_pred[0.50]["empirical"] == pytest.approx(0.50, abs=1e-9)
    assert by_pred[0.25]["empirical"] == pytest.approx(0.25, abs=1e-9)
