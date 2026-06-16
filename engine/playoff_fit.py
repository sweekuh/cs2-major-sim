"""Champion-futures calibration: fit per-team playoff ratings from P(champion) targets (PLAY-04).

Pure numpy + the bracket engine — NO streamlit/httpx/scipy (functional-core invariant). The
twin of ``engine.qualifyfit`` for the playoffs: where qualifyfit fits Swiss ratings so the
simulated P(qualify) matches the market's qualify markets, this fits the 8 playoff ratings so
the simulated P(champion) matches the market's tournament-WINNER futures — the sharpest external
signal for the one thing the playoffs decide.

Why this is an accuracy win (not just moving numbers): the shipped playoff ratings are the
Stage-3 map priors carried forward, which encode pre-event map strength but NOT the bracket draw
or the market's aggregated read of the title race. Champion futures aggregate rosters, form,
head-to-heads, and the bracket — so anchoring P(champion) to them, then letting the bracket sim
fill in the consistent SF/final/round probabilities, is a strictly better champion estimate than
raw carried-forward ratings (mirrors why the R1 back-solve and QFIT beat the [INFERRED] prior).

DETERMINISM + COMMON RANDOM NUMBERS: every iteration re-runs the SAME ``n_per_iter`` bracket sims
from the SAME fixed seed, so only the ratings move between iterations — the MC noise is common, the
P(champion) surface the stepper sees is smooth, and the whole fit is a deterministic function of
its inputs (asserted by tests/test_playoff_fit.py::test_fit_is_deterministic).

GAUGE: champion probs depend only on rating DIFFERENCES, so after each step every rating is
re-centered so the top seed (min id) keeps its base rating — mirroring qualifyfit / fit_ratings,
making the fit identifiable.
"""

from __future__ import annotations

import math

import numpy as np

from engine.bracket import DEFAULT_BO, simulate_bracket
from engine.teams import Team

# Champion probs structurally sum to 1.0 (exactly one champion per sim). Futures carry vig/noise,
# so a raw target sum lands near — not at — 1.0; accept a sane window and renormalize. OUTSIDE it
# the targets are structurally garbage (a missing market, a mis-joined team, decimal-odds
# confusion) and must fail LOUD, never silently fit (mirrors qualifyfit._validate_targets).
_TARGET_SUM_LO = 0.80
_TARGET_SUM_HI = 1.20
_TARGET_EPS = 1e-4


def _simulate_champion_probs(
    teams: list[Team],
    ratings: dict[int, float],
    S: float,
    bo: dict[str, int],
    *,
    n: int,
    seed: int,
) -> dict[int, float]:
    """One K=1 bracket Monte-Carlo pass: P(champion) per team over ``n`` sims.

    The rng is rebuilt from the SAME ``seed`` on every call (common random numbers — see the
    module docstring): identical (ratings, inputs) -> identical counts, and across iterations only
    the ratings move, so the stepper sees a smooth p_champ(r) surface. ``simulate_bracket`` does
    not mutate teams, so no per-sim fresh copy is needed (unlike the Swiss sim)."""
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    counts = {t.id: 0 for t in teams}
    for _ in range(n):
        winners = simulate_bracket(teams, ratings, S, rng, bo=bo)
        counts[winners["GF"]] += 1
    return {tid: c / n for tid, c in counts.items()}


def _validate_targets(champion_targets: dict, ids: list[int]) -> tuple[dict[int, float], float]:
    """Validate + renormalize the champion targets; returns ``(targets, raw_sum)``.

    FAIL-LOUD (mirrors qualifyfit): exactly the 8 team ids, every p strictly in (0, 1), and a sum
    within [0.80, 1.20] (vig/noise tolerance) — anything else raises ValueError. The accepted sum
    is renormalized to exactly 1.0 (champion probs structurally sum to 1: one champion per sim)."""
    if not isinstance(champion_targets, dict):
        raise ValueError(
            f"champion_targets must be a dict of {{team_id: prob}}, got "
            f"{type(champion_targets).__name__!r}"
        )
    got, want = set(champion_targets), set(ids)
    if got != want:
        missing, extra = sorted(want - got), sorted(got - want)
        raise ValueError(
            f"champion_targets must cover exactly the {len(ids)} team ids; "
            f"missing={missing} extra={extra}"
        )
    targets: dict[int, float] = {}
    for tid in ids:
        p = float(champion_targets[tid])
        if not (0.0 < p < 1.0) or p != p:
            raise ValueError(f"champion target for team {tid} must be strictly in (0, 1), got {p!r}")
        targets[tid] = p
    raw_sum = sum(targets.values())
    if not (_TARGET_SUM_LO <= raw_sum <= _TARGET_SUM_HI):
        raise ValueError(
            f"champion targets sum to {raw_sum:.3f}, outside the sane [{_TARGET_SUM_LO}, "
            f"{_TARGET_SUM_HI}] window — champion probs structurally sum to 1.0; a sum this far "
            "off means a missing/mis-joined market, refusing to fit garbage"
        )
    scale = 1.0 / raw_sum
    targets = {
        tid: min(max(p * scale, _TARGET_EPS), 1.0 - _TARGET_EPS) for tid, p in targets.items()
    }
    return targets, raw_sum


def _logit10(p: float) -> float:
    return math.log10(p / (1.0 - p))


def fit_champion_ratings(
    teams: list[Team],
    S: float,
    champion_targets: dict[int, float],
    *,
    bo: dict[str, int] | None = None,
    base_ratings: dict[int, float] | None = None,
    n_per_iter: int = 30_000,
    max_iters: int = 40,
    tol: float = 0.01,
    eta: float = 0.18,
    seed: int = 20260528,
) -> tuple[dict[int, float], dict]:
    """Fit the 8 playoff ratings so the simulated P(champion) matches the market's champion futures.

    ``teams`` is the seed-1..8 bracket fixture; ``S`` the logistic spread; ``champion_targets`` is
    ``{team_id: P(win the title)}`` from the winner futures — validated FAIL-LOUD (exactly the 8
    ids, each p in (0, 1), sum within [0.80, 1.20] then renormalized to 1.0; see _validate_targets).

    Iteration: a K=1 bracket MC of ``n_per_iter`` sims (fixed ``seed`` every iteration — common
    random numbers, so the fit is DETERMINISTIC for identical inputs) yields p_i = P(champion) per
    team; each rating then takes a damped logit step ``r_i += eta * S * (logit10(t_i) - logit10(p_i))``
    (S is the decades-per-rating-point scale of engine.probs.p_map), with p_i clamped away from 0/1
    by 1/(2*n_per_iter); ratings are re-centered so the top seed (min id) keeps its base rating (the
    gauge anchor). Stops when max_i |p_i - t_i| <= tol or after ``max_iters`` evaluations.

    ``eta`` defaults LOW (0.18): winning the title is THREE series deep (4 for a Bo5 final), so the
    logit of P(champion) is far steeper in rating than the per-map logit S describes — a high eta
    oscillates. As a determinism-preserving guard the step HALVES whenever an iteration's max_err
    got WORSE than the previous one (overshoot backoff — a pure function of the deterministic error
    sequence, so the fit stays bit-stable). The returned ratings are the last EVALUATED iterate.

    Returns ``(fitted_ratings, diagnostics)``: ``{team_id: rating}`` plus at least
    ``{"iters", "max_err", "converged", "target_sum"}``.
    """
    ids = [t.id for t in teams]
    targets, raw_sum = _validate_targets(champion_targets, ids)
    if n_per_iter <= 0:
        raise ValueError(f"n_per_iter must be a positive integer, got {n_per_iter!r}")
    if max_iters <= 0:
        raise ValueError(f"max_iters must be a positive integer, got {max_iters!r}")
    bo = bo or DEFAULT_BO

    base = {t.id: float(t.rating) for t in teams}
    if base_ratings:
        base.update({int(k): float(v) for k, v in base_ratings.items() if int(k) in base})

    anchor_id = min(ids)  # the top seed — the gauge-anchor convention
    gauge = base[anchor_id]
    p_clamp = 1.0 / (2.0 * n_per_iter)

    ratings = dict(base)
    iters = 0
    max_err = math.inf
    prev_err = math.inf
    step = float(eta)
    converged = False
    for it in range(1, max_iters + 1):
        iters = it
        p = _simulate_champion_probs(teams, ratings, S, bo, n=n_per_iter, seed=seed)
        max_err = max(abs(p[tid] - targets[tid]) for tid in ids)
        if max_err <= tol:
            converged = True
            break
        if it == max_iters:
            break  # out of budget: return the EVALUATED iterate, never a blind final step
        if max_err > prev_err:
            step *= 0.5  # overshoot backoff — deterministic
        prev_err = max_err
        for tid in ids:
            pc = min(max(p[tid], p_clamp), 1.0 - p_clamp)
            ratings[tid] += step * S * (_logit10(targets[tid]) - _logit10(pc))
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
