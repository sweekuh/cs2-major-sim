"""Dixon-Coles bivariate-Poisson match model — the soccer fair-value core (Phase 1).

This REPLACES the CS2 win-probability model (`engine.probs.p_map`/`series`): soccer needs draws
AND scorelines (goal difference decides group tiebreakers), which a 2-outcome logistic cannot
produce. Dixon-Coles (1997) is double-Poisson with a low-score correction:

    λ_home = exp(base + attack[home] - defence[away] + home_adv·¬neutral)
    λ_away = exp(base + attack[away] - defence[home])

Conventions (documented so the calibration sign-handling stays correct):
  - ``attack``/``defence`` are LOG-space strengths; 0.0 is league-average. HIGHER attack = scores
    more; HIGHER defence = concedes FEWER (a strong opponent defence lowers your λ).
  - ``base`` is the log baseline goals-per-team (~log(1.35) ≈ 0.30 for World Cup scoring).
  - ``home_adv`` is added to the home λ only when the match is NOT at a neutral venue (most World
    Cup games are neutral; the three hosts get it at home).

The Dixon-Coles ``τ`` term reweights only the four low scores (0-0, 1-0, 0-1, 1-1) to fix the
draw deficit independent Poisson produces; ``rho`` (typically small negative) controls it.

Pure numpy/math — no I/O, no engine/app imports — so it stays on the functional core path.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# World Cup scoring baseline: ~2.7 total goals/match -> ~1.35 per team. log(1.35) ≈ 0.30.
DEFAULT_BASE = math.log(1.35)
DEFAULT_RHO = -0.05
DEFAULT_MAX_GOALS = 10


@dataclass(frozen=True)
class MatchModel:
    """Calibrated team strengths + global terms for the Dixon-Coles model.

    ``attack``/``defence`` map team id -> log-space strength (0 = average). ``home_adv`` applies
    only at non-neutral venues; ``base`` is the log baseline goal rate; ``rho`` the low-score
    correction. Immutable so a calibrated model is a safe value to pass around.
    """

    attack: dict[int, float]
    defence: dict[int, float]
    home_adv: float = 0.0
    base: float = DEFAULT_BASE
    rho: float = DEFAULT_RHO


def expected_goals(model: MatchModel, home_id: int, away_id: int, *, neutral: bool = True) -> tuple[float, float]:
    """Expected goals (λ_home, λ_away) for a fixture under ``model``. ``neutral`` drops home_adv."""
    ha = 0.0 if neutral else model.home_adv
    lam_h = math.exp(model.base + model.attack[home_id] - model.defence[away_id] + ha)
    lam_a = math.exp(model.base + model.attack[away_id] - model.defence[home_id])
    return lam_h, lam_a


def _poisson_pmf(lam: float, kmax: int) -> np.ndarray:
    """Vector ``[P(0), ..., P(kmax)]`` for a Poisson(lam), computed without scipy."""
    ks = np.arange(kmax + 1)
    logp = -lam + ks * math.log(lam) - np.array([math.lgamma(k + 1) for k in ks])
    return np.exp(logp)


def _tau(lam_h: float, lam_a: float, rho: float, n: int) -> np.ndarray:
    """The Dixon-Coles low-score correction matrix (only the 2x2 corner differs from 1.0)."""
    t = np.ones((n, n), dtype=float)
    t[0, 0] = 1.0 - lam_h * lam_a * rho
    t[0, 1] = 1.0 + lam_h * rho
    t[1, 0] = 1.0 + lam_a * rho
    t[1, 1] = 1.0 - rho
    return t


def scoreline_matrix(lam_h: float, lam_a: float, rho: float = DEFAULT_RHO,
                     max_goals: int = DEFAULT_MAX_GOALS) -> np.ndarray:
    """Joint P(home=x, away=y) matrix (rows=home goals, cols=away goals), DC-corrected + normalized.

    The independent-Poisson outer product is multiplied by the ``τ`` corner correction and
    renormalized (the correction and the truncation at ``max_goals`` both perturb the mass).
    """
    ph = _poisson_pmf(lam_h, max_goals)
    pa = _poisson_pmf(lam_a, max_goals)
    m = np.outer(ph, pa) * _tau(lam_h, lam_a, rho, max_goals + 1)
    m = np.clip(m, 0.0, None)  # the τ corner can go slightly negative for extreme λ/rho
    s = m.sum()
    if not np.isfinite(s) or s <= 0.0:
        # Pathological λ (an absurd rating spread under a tiny spread scale) under/overflows the
        # Poisson pmf to all-zero; fall back to a uniform scoreline so downstream math stays finite
        # instead of propagating NaN (which would silently mis-steer e.g. the fit_elo_scale search).
        return np.full_like(m, 1.0 / m.size)
    return m / s


def outcome_1x2(matrix: np.ndarray) -> tuple[float, float, float]:
    """(P(home win), P(draw), P(away win)) from a scoreline matrix. home win = home goals > away."""
    p_draw = float(np.trace(matrix))
    p_home = float(np.tril(matrix, -1).sum())  # rows>cols => home goals > away goals
    p_away = float(np.triu(matrix, 1).sum())
    return p_home, p_draw, p_away


def match_1x2(model: MatchModel, home_id: int, away_id: int, *, neutral: bool = True,
              max_goals: int = DEFAULT_MAX_GOALS) -> tuple[float, float, float]:
    """Closed-form (P_home, P_draw, P_away) for a fixture — the liquid match-market fair value."""
    lam_h, lam_a = expected_goals(model, home_id, away_id, neutral=neutral)
    return outcome_1x2(scoreline_matrix(lam_h, lam_a, model.rho, max_goals))


def sample_score(lam_h: float, lam_a: float, rng: np.random.Generator, *, rho: float = DEFAULT_RHO,
                 max_goals: int = DEFAULT_MAX_GOALS) -> tuple[int, int]:
    """Draw one (home_goals, away_goals) from the DC scoreline distribution (the per-match MC draw).

    Samples a flat index from the normalized scoreline matrix — exact w.r.t. the DC distribution
    (unlike drawing two independent Poissons, which would discard the low-score correction).
    """
    m = scoreline_matrix(lam_h, lam_a, rho, max_goals)
    flat = m.ravel()
    idx = rng.choice(flat.size, p=flat)
    return int(idx // m.shape[1]), int(idx % m.shape[1])


def strengths_from_elo(teams, *, elo_per_goal: float = 250.0, base: float = DEFAULT_BASE,
                       home_adv: float = 0.0, rho: float = DEFAULT_RHO) -> MatchModel:
    """Warm-start a MatchModel from Elo priors (symmetric attack==defence == quality).

    Quality ``q_i = (elo_i - mean_elo) / elo_per_goal`` in log-goal units; a stronger team both
    scores more (attack) and concedes fewer (defence), so we set ``attack_i = defence_i = q_i``.
    Then λ depends on quality DIFFERENCES (``attack_h - defence_a = q_h - q_a``), the intended
    Elo-difference behaviour. ``elo_per_goal`` ≈ Elo points per one log-goal unit (calibration
    refines the strengths afterwards; this only needs to be a sane start).
    """
    elos = np.array([t.elo for t in teams], dtype=float)
    mean = float(elos.mean())
    attack = {t.id: (t.elo - mean) / elo_per_goal for t in teams}
    defence = dict(attack)  # symmetric warm start
    return MatchModel(attack=attack, defence=defence, home_adv=home_adv, base=base, rho=rho)
