"""Market-odds back-solve: series->map invert + logistic ratings fit (ODDS-04, D5).

Pure, numpy-only, no I/O, no streamlit/httpx. Two non-negotiables (getting either wrong
silently corrupts the priced branches):

  - INVERT series->map BEFORE fitting ratings (Pitfall 9). A market series prob is for a
    SPECIFIC format (Bo1 or Bo3). ``invert_series`` recovers the per-map ``p``: identity
    for Bo1, the EXACT inverse of ``engine.probs.series`` (``p^2(3-2p)``) by bisection for
    Bo3 (strictly monotone, so bisection is valid). Fitting ratings to series probs
    conflates Bo1 and Bo3 so one rating cannot price both unplayed branches.

  - The fit is a hand-rolled numpy Gauss-Newton logistic least-squares — NO scipy (stack
    constraint). The model ``p_map(r_i, r_j) = sigmoid((r_i - r_j)*ln10/S)`` depends only
    on rating DIFFERENCES, so {r + c} is an additive null space; one GAUGE-ANCHORED team
    (rating held fixed each iteration) removes it and makes the fit identifiable.

The imminent round's KNOWN matchups are injected DIRECTLY as a per-match override (Bo3 NOT
re-applied, PROB-02) via the keyword-only ``market_overrides`` arg threaded through
``engine.swiss.simulate_stage`` -> ``_play`` (see swiss.py). This module only produces the
back-solved ratings + the inverse; the override plumbing lives in swiss.py.
"""

from __future__ import annotations

import math

import numpy as np

from engine.probs import series


def invert_series(q: float, bo3: bool) -> float:
    """Recover the per-map win prob ``p`` from a SERIES prob ``q``.

    Identity for Bo1; for Bo3 the exact inverse of ``engine.probs.series`` (``p^2(3-2p)``)
    by bisection on [0, 1] — the forward map is strictly monotone increasing, so bisection
    converges to the unique inverse. Verified: ``invert_series(0.648, True) == 0.6`` and
    ``invert_series(0.5, True) == 0.5`` (the exact inverse of ``series``).
    """
    if not bo3:
        return q
    lo, hi = 0.0, 1.0
    for _ in range(60):  # 2^-60 ~ 1e-18: well below the 1e-6 the gate asserts
        mid = 0.5 * (lo + hi)
        if mid * mid * (3 - 2 * mid) < q:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def fit_ratings(
    targets: dict[tuple[int, int], float],
    teams: list,
    S: float,
    anchor_id: int,
    iters: int = 50,
) -> dict[int, float]:
    """Hand-rolled numpy Gauss-Newton logistic least-squares ratings fit (ODDS-04).

    ``targets`` is ``dict[(i, j) -> float]`` of MAP-level probs (ALREADY inverted) meaning
    P(team i beats team j on a map). The model is
    ``p_map(r_i, r_j) = sigmoid((r_i - r_j)*ln10/S)`` (engine.probs.p_map rewritten in
    nats). We minimize ``Σ (model_ij - target_ij)^2`` over the per-team ratings by
    Gauss-Newton with the logistic Jacobian, FIXING ``r[anchor_id]`` at its gauge value
    (the team's seed rating) each iteration to remove the additive ``(r + c)`` null space.
    numpy only, NO scipy. Returns ``{id: rating}``.

    The gauge: ``p_map`` depends only on ``(r_i - r_j)``, so adding a constant to every
    rating leaves all targets unchanged — the system is rank-deficient by one. Holding the
    anchor fixed pins the gauge so the fit is identifiable (test_gauge_anchor_removes_null_space).
    """
    ids = [t.id for t in teams]
    idx = {tid: k for k, tid in enumerate(ids)}
    n = len(ids)
    anchor_team = next(t for t in teams if t.id == anchor_id)
    gauge = float(anchor_team.rating)
    a_k = idx[anchor_id]

    # Initialize at each team's own seed rating (a good warm start; converges fast).
    r = np.array([float(t.rating) for t in teams], dtype=float)
    r[a_k] = gauge

    # Precompute the matchup index arrays and target vector.
    rows = list(targets.items())
    ii = np.array([idx[i] for (i, _j), _ in rows], dtype=int)
    jj = np.array([idx[j] for (_i, j), _ in rows], dtype=int)
    tvec = np.array([t for _, t in rows], dtype=float)
    c = math.log(10.0) / S  # nats-per-rating-point scale

    for _ in range(iters):
        z = c * (r[ii] - r[jj])
        p = _sigmoid(z)
        resid = p - tvec  # residual to drive to zero
        dp = p * (1.0 - p) * c  # d p_ij / d r_i  (and -dp for r_j)

        # Gauss-Newton normal equations J^T J dr = -J^T resid, with the anchor row/col
        # pinned (gauge fix). Build J^T J and J^T resid over the free params.
        JTJ = np.zeros((n, n), dtype=float)
        JTr = np.zeros(n, dtype=float)
        for m in range(len(rows)):
            a, b = ii[m], jj[m]
            g = dp[m]
            # gradient of residual_m wrt r_a = +g, wrt r_b = -g
            JTJ[a, a] += g * g
            JTJ[b, b] += g * g
            JTJ[a, b] -= g * g
            JTJ[b, a] -= g * g
            JTr[a] += g * resid[m]
            JTr[b] -= g * resid[m]

        # Pin the anchor: fix r[anchor] (its update is forced to 0). Replace its row with
        # the identity so the solve leaves it unchanged, zero its column contribution.
        JTJ[a_k, :] = 0.0
        JTJ[:, a_k] = 0.0
        JTJ[a_k, a_k] = 1.0
        JTr[a_k] = 0.0

        # Levenberg damping keeps the solve well-conditioned (the gauge already removes the
        # rank-1 null space, but damping guards near-degenerate target sets).
        JTJ[np.diag_indices(n)] += 1e-9
        try:
            dr = np.linalg.solve(JTJ, -JTr)
        except np.linalg.LinAlgError:
            dr = np.linalg.lstsq(JTJ, -JTr, rcond=None)[0]
        r = r + dr
        r[a_k] = gauge  # re-pin the gauge each iteration

    return {tid: float(r[idx[tid]]) for tid in ids}
