"""Back-solve correctness guards (ODDS-04, PROB-02, Pitfall 9, T-05-ORIENT/SERIES/BO3).

RED-first (the Phase 1/3/4 Wave-0 convention): these import from the not-yet-existing
``engine.backsolve`` so they collect and run RED, not falsely green. They prove:

  - invert_series is the EXACT inverse of engine.probs.series (identity Bo1, bisection
    Bo3 inverse: 0.648 -> 0.6) — Pitfall 9 / ODDS-04.
  - fit_ratings (numpy-only Gauss-Newton, NO scipy) recovers KNOWN ratings up to the
    additive gauge from MAP-level target probs, and reprices the targets within tol.
  - the gauge anchor removes the additive (r + c) null space (the fit is identifiable).
  - a market_overrides entry resolves the imminent round's matchup DIRECTLY via
    series_prob(market_series_prob=...) — Bo3 NOT re-applied (PROB-02) — and is oriented
    to the LOWER-id team EVEN when _play receives the pair difficulty-ranked (high-id,
    low-id), with no silent half-matchup inversion (T-05-ORIENT).
"""

from __future__ import annotations

import numpy as np
import pytest

from engine.backsolve import fit_ratings, invert_series
from engine.probs import p_map, series
from engine.teams import Team, load_teams


# ---------------------------------------------------------------------------
# (a) series -> map invert (ODDS-04, Pitfall 9)
# ---------------------------------------------------------------------------
def test_invert_series():
    """invert_series is the exact inverse of engine.probs.series.

    Bo3: series(0.6, True) == 0.648, so invert_series(0.648, True) == 0.6.
    series(0.5, True) == 0.5 (fixed point). Bo1 is the identity.
    """
    assert invert_series(0.648, True) == pytest.approx(0.6, abs=1e-6)
    assert invert_series(0.5, True) == pytest.approx(0.5, abs=1e-9)
    # Bo1 identity.
    for q in (0.1, 0.5, 0.73, 0.9):
        assert invert_series(q, False) == q
    # Round-trip the forward series through the inverse for a few q.
    for q in (0.55, 0.648, 0.72, 0.81, 0.93):
        assert series(invert_series(q, True), True) == pytest.approx(q, abs=1e-6)


def test_bo3_inverse_correct():
    """For a grid of map probs p, invert_series(series(p, True), True) recovers p.

    The forward q = p^2(3-2p) is strictly monotone on [0, 1], so bisection recovers the
    exact input (the inverse exists and is unique).
    """
    for p in (0.55, 0.6, 0.7, 0.8):
        q = series(p, True)
        assert invert_series(q, True) == pytest.approx(p, abs=1e-6)


# ---------------------------------------------------------------------------
# (b) logistic ratings fit (ODDS-04) — hand-rolled numpy Gauss-Newton, NO scipy
# ---------------------------------------------------------------------------
# Hand-set KNOWN ratings (the auditable expectation for the roundtrip): the fit must
# recover these (up to the additive gauge) from the MAP-level probs they generate.
_KNOWN = {1: 90.0, 2: 60.0, 3: 50.0, 4: 40.0}
_S = 40.0
_MATCHUPS = [(1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)]


def _known_teams():
    return [t for t in load_teams() if t.id in _KNOWN]


def _targets():
    return {(i, j): p_map(_KNOWN[i], _KNOWN[j], S=_S) for i, j in _MATCHUPS}


def test_rating_roundtrip():
    """CRITICAL: feeding fit_ratings KNOWN map probs recovers the known ratings.

    The model depends only on rating DIFFERENCES (an additive gauge): adding a constant to
    every rating leaves all targets unchanged, so absolute ratings are recoverable only up
    to the anchor's chosen gauge (here the anchor team's seed rating from the fixture, not
    the hypothetical 90). We assert the two GAUGE-INVARIANT, fully-recoverable quantities:
      (1) the recovered ratings REPRICE every target matchup within tolerance, and
      (2) the recovered DIFFERENCES (r_i - r_anchor) match the known differences.
    """
    teams = _known_teams()
    targets = _targets()
    anchor_id = 1
    recovered = fit_ratings(targets, teams, _S, anchor_id)

    # (1) Reprice every target matchup (the strongest, gauge-invariant invariant).
    for (i, j), tgt in targets.items():
        assert p_map(recovered[i], recovered[j], S=_S) == pytest.approx(tgt, abs=1e-3)

    # (2) Recovered DIFFERENCES vs the anchor match the known differences exactly (the
    # additive gauge cancels in a difference).
    for tid, true_r in _KNOWN.items():
        rec_diff = recovered[tid] - recovered[anchor_id]
        true_diff = true_r - _KNOWN[anchor_id]
        assert rec_diff == pytest.approx(true_diff, abs=0.5)


def test_gauge_anchor_removes_null_space():
    """The anchor team's recovered rating equals its fixed gauge value EXACTLY.

    p_map(r_i, r_j) depends only on (r_i - r_j), so {r + c} is a null space. Fixing
    r[anchor_id] to a gauge constant removes that additive degeneracy and makes the fit
    identifiable. We assert the anchor is held EXACTLY at its seed rating.
    """
    teams = _known_teams()
    targets = _targets()
    anchor_id = 2
    anchor_team = next(t for t in teams if t.id == anchor_id)
    recovered = fit_ratings(targets, teams, _S, anchor_id)

    assert recovered[anchor_id] == pytest.approx(anchor_team.rating, abs=1e-9)
    for (i, j), tgt in targets.items():
        assert p_map(recovered[i], recovered[j], S=_S) == pytest.approx(tgt, abs=1e-3)


# ---------------------------------------------------------------------------
# (c) market_overrides: direct, Bo3-not-reapplied, LOWER-id oriented (PROB-02/T-05-ORIENT)
# ---------------------------------------------------------------------------
def test_override_no_bo3_reapply():
    """ORIENTATION-CRITICAL (T-05-ORIENT / PROB-02): _play orients the override to the
    LOWER-id team and uses it DIRECTLY (Bo3 NOT re-applied) even when it receives the pair
    in (high-id, low-id) arg order.

    We exercise ``engine.swiss._play`` directly (the unit under the orientation contract):
    a pair delivered in (HIGH-id, LOW-id) arg order — exactly what ``pair_within_group``
    produces for difficulty-ranked groups (swiss.py:294), NOT id order.

    Orientation arithmetic (hand-computed):
      The stored override ``p`` = P(LOWER-id team wins). _play's FIRST arg here is the
      HIGH-id team, so the FIRST arg wins with prob ``(1 - p)``. A NAIVE arg-order lookup
      (treating ``p`` as "P(first arg wins)") would make the LOWER-id team win at rate
      ``(1 - p)`` — a silent inversion. The correct orientation makes the LOWER-id team
      win at rate ``p``.

    We pick p = 0.85 (lower-id strongly favored) and assert the LOWER-id team wins at
    ~p, NOT the first (high-id) arg. We also assert Bo3 is NOT re-applied: with p=0.85
    the realized rate is p itself (~0.85), not series(0.85)=0.9355 — proving the market
    series prob flowed straight through series_prob(market_series_prob=p_a).
    """
    from engine.swiss import _is_bo3, _play

    P = 0.85  # P(LOWER-id team wins the SERIES)

    # Two teams. Deliver them to _play in (HIGH-id, LOW-id) arg order: a = id 14, b = id 5.
    hi = Team(id=14, name="HI", seed=14, rating=50.0, wins=2, losses=0)
    lo = Team(id=5, name="LO", seed=5, rating=50.0, wins=2, losses=0)
    assert hi.id > lo.id  # delivered high-id first (the orientation hazard)

    # _is_bo3 here is True (both at 2 wins), so a naive path would re-apply Bo3. The
    # override must SKIP series()/Bo3 (PROB-02): realized lower-id rate == P, not series(P).
    assert _is_bo3(hi, lo)

    key = f"{min(hi.id, lo.id)}-{max(hi.id, lo.id)}"  # "5-14"
    overrides = {key: P}  # value = P(LOWER-id wins)

    N = 20000
    rng = np.random.default_rng(20260529)
    lo_wins = 0
    for _ in range(N):
        winner, _loser = _play(hi, lo, None, 40.0, rng, {}, market_overrides=overrides)
        if winner.id == lo.id:
            lo_wins += 1
    rate = lo_wins / N

    # Lower-id wins at ~P (correct orientation), NOT (1 - P) (the naive-inversion rate),
    # and NOT series(P)=0.9355 (Bo3 wrongly re-applied).
    assert rate == pytest.approx(P, abs=0.015), (
        f"lower-id win rate {rate:.3f}: expected ~{P} (oriented). A naive arg-order lookup "
        f"gives ~{1 - P:.3f}; re-applying Bo3 gives ~{series(P, True):.3f}."
    )
    assert abs(rate - (1 - P)) > 0.1, "rate matches the naive-inversion value — orientation bug"
    assert abs(rate - series(P, True)) > 0.05, "rate matches series(P) — Bo3 wrongly re-applied"

    # Additive control: WITHOUT the override, _play falls back to the rating-based path.
    # Equal ratings -> series prob 0.5 (a coinflip), materially different from P=0.85.
    rng_ctrl = np.random.default_rng(20260529)
    lo_wins_ctrl = sum(
        _play(hi, lo, None, 40.0, rng_ctrl, {})[0].id == lo.id for _ in range(N)
    )
    rate_ctrl = lo_wins_ctrl / N
    assert rate_ctrl == pytest.approx(0.5, abs=0.02), (
        f"control (no override) rate {rate_ctrl:.3f} should be the rating coinflip 0.5; "
        "default market_overrides=None must be the unchanged rating path"
    )
