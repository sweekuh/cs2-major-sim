"""Qualify-market calibration: back-solve per-team ratings from P(qualify) targets (QFIT-01).

Pure numpy + the swiss engine — NO streamlit/httpx/scipy (functional-core invariant). The R1
back-solve (``engine.backsolve.fit_ratings``) can only see the eight Round-1 series prices, so
the ratings it produces encode the market's view of ROUND 1 ONLY; the market's qualify markets
(P(team finishes 3-X)) carry its view of rounds 2-5, which no R1 price can express. This module
fits per-team ratings so the SIMULATED P(qualify) matches those qualify-market targets.

ORTHOGONALITY (the load-bearing design fact): every R1 match present in ``market_blend`` is
priced DIRECTLY from the market inside the sim (``simulate_stage``'s ``market_overrides`` seam,
PROB-02/T-05-ORIENT) — the fitted ratings therefore only influence rounds 2-5. The fit moves
the round-2-5 strength view WITHOUT disturbing the R1 anchor, so it composes with (never fights)
the R1 back-solve the app already runs.

DETERMINISM + COMMON RANDOM NUMBERS: every iteration re-runs the SAME ``n_per_iter`` sims from
the SAME fixed seed, so the only thing that changes between iterations is the ratings — the
Monte-Carlo noise is common across iterations (the q(r) surface seen by the stepper is smooth)
and the whole fit is a deterministic function of its inputs (asserted by
tests/test_qualifyfit.py::test_fit_is_deterministic). Epistemic var is irrelevant here: the fit
calls ``simulate_stage`` directly (K=1 — the epistemic OUTER loop in run_mc would multiply cost
by ~12 and add nothing to a point fit).

GAUGE: qualify probs depend only on rating DIFFERENCES (the same additive null space as
``fit_ratings``), so after each step every rating is re-centered so the top seed (min id) keeps
its base rating — mirroring fit_ratings' anchor convention, making the fit identifiable.
"""

from __future__ import annotations

import math

import numpy as np

from engine.swiss import simulate_stage
from engine.teams import ADVANCE_AT_WINS, Team

# qualify probs structurally sum to QUALIFY_SLOTS (8 of 16 teams reach 3 wins in every sim).
QUALIFY_SLOTS = 8
# Markets carry vig/noise, so a raw qualify-market sum lands near — not at — 8. Accept a sane
# window and renormalize; OUTSIDE it the targets are structurally garbage (a missing market, a
# mis-joined team, decimal-odds confusion) and must fail LOUD, never silently fit (see
# fit_qualify_ratings docstring).
_TARGET_SUM_LO = 7.0
_TARGET_SUM_HI = 9.0
# Renormalizing a near-1 target with a sub-8 raw sum can push it past 1 (e.g. 0.95 * 8/7.2 >
# 1); clamp the RENORMALIZED targets back inside (0, 1) so their logits stay finite. The raw
# targets are still validated strictly inside (0, 1) first — the clamp only absorbs the
# renormalization overshoot, never a garbage input.
_TARGET_EPS = 1e-4


def _fresh_teams(template: list[Team]) -> list[Team]:
    """Clean per-sim Team copies — ``simulate_stage`` mutates wins/losses/opps (the Wave-2
    handoff note); only id/name/seed/rating carry over. Mirrors montecarlo._fresh_teams."""
    return [Team(id=t.id, name=t.name, seed=t.seed, rating=t.rating) for t in template]


def _market_overrides(market_blend) -> dict[str, float] | None:
    """Normalize ``market_blend`` to the engine's ``market_overrides`` shape: ``{"lo-hi": p}``.

    Accepts either ``{"lo-hi": p}`` (the CLI's p-only shape) or ``{"lo-hi": (p, var)}`` (the
    app's blend shape) — var is irrelevant to a point fit (K=1, no epistemic draws). Returns
    None for an empty/absent blend (the pure rating-driven sim).
    """
    if not market_blend:
        return None
    out: dict[str, float] = {}
    for key, val in market_blend.items():
        p = val[0] if isinstance(val, (tuple, list)) else val
        out[str(key)] = float(p)
    return out


def _simulate_qualify_probs(
    teams: list[Team],
    ratings: dict[int, float],
    S: float,
    overrides: dict[str, float] | None,
    *,
    all_bo3: bool,
    n: int,
    seed: int,
) -> dict[int, float]:
    """One K=1 Monte-Carlo pass: P(qualify) = P(wins >= 3) per team over ``n`` sims.

    The rng is rebuilt from the SAME ``seed`` on every call (common random numbers — see the
    module docstring): identical (ratings, inputs) -> identical counts, and across iterations
    only the ratings move, so the stepper sees a smooth q(r) surface.
    """
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    counts = {t.id: 0 for t in teams}
    for _ in range(n):
        by_id = simulate_stage(
            _fresh_teams(teams), ratings, S, rng, {},
            market_overrides=overrides, all_bo3=all_bo3,
        )
        for tid, t in by_id.items():
            if t.wins >= ADVANCE_AT_WINS:
                counts[tid] += 1
    return {tid: c / n for tid, c in counts.items()}


def _validate_targets(qualify_targets: dict, ids: list[int]) -> tuple[dict[int, float], float]:
    """Validate + renormalize the qualify targets; returns ``(targets, raw_sum)``.

    FAIL-LOUD contract (the one deliberate departure from the app's fail-soft style): these
    targets are an EXPLICIT user/market input feeding an offline fit, not a runtime cache a
    Streamlit rerun must survive. A wrong/partial target set would not crash anything — it
    would converge to confidently WRONG ratings that then silently price every round-2-5
    branch. So: exactly the 16 team ids, every p strictly inside (0, 1), and a sum within
    [7.0, 9.0] (vig/noise tolerance) — anything else raises ValueError. The accepted sum is
    renormalized to exactly 8 (qualify probs structurally sum to 8: eight of sixteen teams
    reach 3 wins in EVERY sim, so targets that don't sum to 8 are unfittable as-is).
    """
    if not isinstance(qualify_targets, dict):
        raise ValueError(
            f"qualify_targets must be a dict of {{team_id: prob}}, got {type(qualify_targets).__name__!r}"
        )
    got, want = set(qualify_targets), set(ids)
    if got != want:
        missing, extra = sorted(want - got), sorted(got - want)
        raise ValueError(
            f"qualify_targets must cover exactly the {len(ids)} team ids; "
            f"missing={missing} extra={extra}"
        )
    targets: dict[int, float] = {}
    for tid in ids:
        p = float(qualify_targets[tid])
        if not (0.0 < p < 1.0) or p != p:
            raise ValueError(f"qualify target for team {tid} must be strictly in (0, 1), got {p!r}")
        targets[tid] = p
    raw_sum = sum(targets.values())
    if not (_TARGET_SUM_LO <= raw_sum <= _TARGET_SUM_HI):
        raise ValueError(
            f"qualify targets sum to {raw_sum:.3f}, outside the sane [{_TARGET_SUM_LO}, "
            f"{_TARGET_SUM_HI}] window — qualify probs structurally sum to {QUALIFY_SLOTS}; "
            "a sum this far off means a missing/mis-joined market, refusing to fit garbage"
        )
    scale = QUALIFY_SLOTS / raw_sum
    targets = {
        tid: min(max(p * scale, _TARGET_EPS), 1.0 - _TARGET_EPS) for tid, p in targets.items()
    }
    return targets, raw_sum


def _logit10(p: float) -> float:
    return math.log10(p / (1.0 - p))


def fit_qualify_ratings(
    teams: list[Team],
    S: float,
    market_blend,
    qualify_targets: dict[int, float],
    *,
    all_bo3: bool = False,
    base_ratings: dict[int, float] | None = None,
    n_per_iter: int = 20_000,
    max_iters: int = 15,
    tol: float = 0.015,
    eta: float = 0.35,
    seed: int = 20260528,
) -> tuple[dict[int, float], dict]:
    """Fit per-team ratings so the simulated P(qualify) matches the market's qualify targets.

    ``teams`` is the 16-team fixture; ``S`` the logistic spread (PROB-01); ``market_blend`` the
    R1 market prices (``{"lo-hi": p}`` or ``{"lo-hi": (p, var)}`` — p = P(lower-id wins the
    SERIES)), which the sim prices DIRECTLY so the fitted ratings only steer rounds 2-5 (see
    module docstring); ``qualify_targets`` is ``{team_id: P(qualify)}`` from the qualify
    markets — validated FAIL-LOUD (exactly the 16 ids, each p in (0, 1), sum within [7, 9] then
    renormalized to exactly 8; see _validate_targets for WHY garbage must never silently fit).

    Iteration: a K=1 MC of ``n_per_iter`` sims (fixed ``seed`` every iteration — common random
    numbers, so the fit is DETERMINISTIC for identical inputs) yields q_i per team; each rating
    then takes a damped logit step ``r_i += eta * S * (logit10(t_i) - logit10(q_i))`` (S is the
    decades-per-rating-point scale of engine.probs.p_map, so a logit gap maps to rating points),
    with q_i clamped away from 0/1 by 1/(2*n_per_iter); ratings are then re-centered so the top
    seed (min id) keeps its base rating (the gauge anchor — qualify probs depend only on rating
    differences, mirroring fit_ratings' convention). Stops when max_i |q_i - t_i| <= tol or
    after ``max_iters`` evaluations.

    ``eta`` defaults to 0.35, NOT ~0.7: the logit of P(QUALIFY) is ~2.5-3x steeper in rating
    than the per-MAP logit the S scale describes (a Swiss run compounds 3-5 matches), so the
    fixed-point gain is ``eta * g`` with g ≈ 2.7 (≈ 4 under all-Bo3, which sharpens every
    series) — measured empirically: eta=0.7 oscillates without converging while 0.3-0.5
    converges in 3-4 iterations. As a determinism-preserving guard for steeper target sets,
    the step HALVES whenever an iteration's max_err got WORSE than the previous one (overshoot
    backoff — pure function of the deterministic error sequence, so the fit stays bit-stable).

    The returned ratings are always the last EVALUATED iterate (no trailing un-evaluated step),
    so ``diagnostics["max_err"]`` describes exactly the dict returned.

    Returns ``(fitted_ratings, diagnostics)``: ``{team_id: rating}`` plus at least
    ``{"iters", "max_err", "converged"}`` (also ``"target_sum"``, the raw pre-renormalization
    sum, for the CLI report).
    """
    ids = [t.id for t in teams]
    targets, raw_sum = _validate_targets(qualify_targets, ids)
    if n_per_iter <= 0:
        raise ValueError(f"n_per_iter must be a positive integer, got {n_per_iter!r}")
    if max_iters <= 0:
        raise ValueError(f"max_iters must be a positive integer, got {max_iters!r}")

    base = {t.id: float(t.rating) for t in teams}
    if base_ratings:
        base.update({int(k): float(v) for k, v in base_ratings.items() if int(k) in base})

    anchor_id = min(ids)  # the top seed — fit_ratings' gauge-anchor convention
    gauge = base[anchor_id]
    overrides = _market_overrides(market_blend)
    q_clamp = 1.0 / (2.0 * n_per_iter)  # keep logit10(q) finite on a 0- or n-count team

    ratings = dict(base)
    iters = 0
    max_err = math.inf
    prev_err = math.inf
    step = float(eta)
    converged = False
    for it in range(1, max_iters + 1):
        iters = it
        q = _simulate_qualify_probs(
            teams, ratings, S, overrides, all_bo3=all_bo3, n=n_per_iter, seed=seed
        )
        max_err = max(abs(q[tid] - targets[tid]) for tid in ids)
        if max_err <= tol:
            converged = True
            break
        if it == max_iters:
            break  # out of budget: return the EVALUATED iterate, never a blind final step
        # Overshoot backoff (see docstring): a worse max_err than last iteration means the
        # eta*gain product exceeded 1 for this target set — halve the step. Deterministic.
        if max_err > prev_err:
            step *= 0.5
        prev_err = max_err
        # Damped logit step toward each target, then re-pin the gauge.
        for tid in ids:
            qc = min(max(q[tid], q_clamp), 1.0 - q_clamp)
            ratings[tid] += step * S * (_logit10(targets[tid]) - _logit10(qc))
        shift = gauge - ratings[anchor_id]
        ratings = {tid: r + shift for tid, r in ratings.items()}
        ratings[anchor_id] = gauge  # exact re-pin (float shift can be off by 1 ulp)

    diagnostics = {
        "iters": iters,
        "max_err": float(max_err),
        "converged": converged,
        "target_sum": float(raw_sum),
    }
    return {tid: float(r) for tid, r in ratings.items()}, diagnostics
