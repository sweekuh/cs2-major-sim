"""Calibration recovery guard (Phase 1) — mirrors test_backsolve.py::test_rating_roundtrip.

Build a KNOWN model, generate de-vigged 1X2 targets from it, calibrate from a neutral prior, and
assert (1) the fit reprices every target and (2) it recovers the gauge-invariant attack/defence
DIFFERENCES vs the anchor. This is the proof the synthesis hinge actually works.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from engine.soccer.calibrate import calibrate_strengths
from engine.soccer.dixon_coles import MatchModel, match_1x2

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


def test_anchor_held_fixed():
    prior = MatchModel(attack={i: 0.5 for i in IDS}, defence={i: 0.5 for i in IDS},
                       home_adv=0.0, base=0.3, rho=-0.05)
    fit = calibrate_strengths(prior, _targets(), anchor_id=ANCHOR, iters=10)
    assert fit.attack[ANCHOR] == prior.attack[ANCHOR]
    assert fit.defence[ANCHOR] == prior.defence[ANCHOR]
