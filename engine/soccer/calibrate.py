"""Calibrate Dixon-Coles strengths to de-vigged sharp 1X2 (Phase 1).

This is the "synthesis" hinge: fit each team's (attack, defence) so the model's implied 1X2
matches the de-vigged sharp consensus on the matches the market prices well, then trust the model
to extrapolate to the thin/exotic markets it can't see.

It reuses the *pattern* of ``engine.backsolve.fit_ratings`` — damped Gauss-Newton with a GAUGE
ANCHOR to remove the additive null space — but the model here is different: the residual is a
3-vector per match (home/draw/away), there are TWO parameters per team, and the 1X2 comes from
integrating a Poisson scoreline matrix, so the Jacobian is computed numerically (forward
differences) rather than in closed form. numpy only, no scipy.

Gauge: λ depends only on ``attack_i - defence_j``, so adding a constant to every attack AND every
defence leaves all probabilities unchanged (a 1-D null space). Holding the anchor team's attack
and defence fixed pins it. ``base``/``home_adv``/``rho`` are treated as fixed hyperparameters.
Optional per-match ``weights`` carry the research-recommended time-decay / match-importance
weighting; pass higher weights for more recent / more competitive fixtures.
"""

from __future__ import annotations

import math

import numpy as np

from engine.soccer.dixon_coles import (
    DEFAULT_BASE,
    DEFAULT_RHO,
    MatchModel,
    match_1x2,
    strengths_from_elo,
)

Target = dict[tuple[int, int], tuple[float, float, float]]


def build_model(teams, targets: "Target | None" = None, *, home_adv: float = 0.0,
                anchor_id: int | None = None, shrinkage: float = 0.2, fit_spread: bool = True,
                neutral: bool = True) -> MatchModel:
    """Best-available calibrated model from team Elo priors + whatever sharp 1X2 ``targets`` exist.

    The one call the live odds path uses. Composition:
      1. if ``targets`` and ``fit_spread``: fit the global Elo->goals spread to them (fixes overall
         overconfidence) — else use the default spread;
      2. build the Elo-prior model at that spread;
      3. if ``targets``: per-team calibrate the COVERED teams toward their market lines (gauge-
         anchored, ``shrinkage`` toward the prior so sparsely-covered teams stay stable).
    With no targets this is just the spread-default Elo prior. With targets covering every team and
    low shrinkage it becomes a full market calibration. ``anchor_id`` defaults to a target's home team.
    """
    targets = targets or {}
    scale = fit_elo_scale(teams, targets, neutral=neutral) if (targets and fit_spread) else 250.0
    prior = strengths_from_elo(teams, elo_per_goal=scale, home_adv=home_adv)
    if not targets:
        return prior
    anchor = anchor_id if anchor_id is not None else next(iter(targets))[0]
    return calibrate_strengths(prior, targets, anchor_id=anchor, shrinkage=shrinkage, neutral=neutral)


def fit_elo_scale(teams, targets: "Target", *, base: float = DEFAULT_BASE, rho: float = DEFAULT_RHO,
                  neutral: bool = True, lo: float = 50.0, hi: float = 3000.0,
                  iters: int = 60) -> float:
    """Fit the global Elo->goals spread (``elo_per_goal``) so model 1X2 matches the market.

    The model's confidence scales with ``(elo_diff) / elo_per_goal``; a too-small scale makes
    strong teams near-certain (the overconfidence seen at the tournament level). This minimizes the
    squared 1X2 error between ``strengths_from_elo(teams, elo_per_goal=scale)`` and the de-vigged
    ``targets`` over a 1-D golden-section search — well-identified even from a few matches, since
    it's a single global parameter. Returns the best ``elo_per_goal`` (larger = less confident).
    """
    if not targets:
        return 0.5 * (lo + hi)  # nothing to fit -> neutral midpoint rather than a bound artifact

    def loss(scale: float) -> float:
        m = strengths_from_elo(teams, elo_per_goal=scale, base=base, rho=rho)
        err = 0.0
        for (h, a), tgt in targets.items():
            p = match_1x2(m, h, a, neutral=neutral)
            err += sum((pi - ti) ** 2 for pi, ti in zip(p, tgt))
        return err if math.isfinite(err) else float("inf")  # never let NaN steer the search

    inv_phi = (5 ** 0.5 - 1) / 2  # 0.618...
    a, b = lo, hi
    c, d = b - inv_phi * (b - a), a + inv_phi * (b - a)
    fc, fd = loss(c), loss(d)
    for _ in range(iters):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - inv_phi * (b - a)
            fc = loss(c)
        else:
            a, c, fc = c, d, fd
            d = a + inv_phi * (b - a)
            fd = loss(d)
    return 0.5 * (a + b)

# Match-importance multipliers (FIFA/Elo convention): competitive matches carry more signal than
# friendlies, which are documented predictive noise for national teams (arxiv 1705.09575).
IMPORTANCE = {
    "friendly": 1.0,
    "qualifier": 2.5,
    "nations_league": 2.5,
    "continental": 3.0,
    "confederations": 3.0,
    "world_cup": 4.0,
}
DEFAULT_HALF_LIFE_DAYS = 365.0


def time_decay(days_ago: float, half_life_days: float = DEFAULT_HALF_LIFE_DAYS) -> float:
    """Exponential recency weight: ``0.5 ** (days_ago / half_life_days)`` (1.0 today, 0.5 at the
    half-life). Older results count less, the standard Dixon-Coles time-weighting."""
    return 0.5 ** (max(0.0, days_ago) / half_life_days)


def match_weight(days_ago: float, competition: str = "friendly",
                 half_life_days: float = DEFAULT_HALF_LIFE_DAYS) -> float:
    """Combined weight = recency decay x match-importance multiplier (unknown competition -> 1.0)."""
    return time_decay(days_ago, half_life_days) * IMPORTANCE.get(competition, 1.0)


def build_match_weights(matches, half_life_days: float = DEFAULT_HALF_LIFE_DAYS
                        ) -> dict[tuple[int, int], float]:
    """Build the ``weights`` dict ``calibrate_strengths`` consumes from match metadata.

    ``matches`` is an iterable of dicts with ``home_id``, ``away_id``, ``days_ago`` and optional
    ``competition``. Returns ``{(home_id, away_id): recency x importance}``.
    """
    return {
        (m["home_id"], m["away_id"]): match_weight(
            m["days_ago"], m.get("competition", "friendly"), half_life_days)
        for m in matches
    }


def calibrate_strengths(prior: MatchModel, targets: Target, *, anchor_id: int,
                        iters: int = 60, neutral: bool = True, damping: float = 1e-2,
                        eps: float = 1e-4, weights: dict[tuple[int, int], float] | None = None,
                        shrinkage: float = 0.0, max_goals: int = 8) -> MatchModel:
    """Fit (attack, defence) so model 1X2 matches ``targets``; anchor's strengths held fixed.

    ``targets`` maps ``(home_id, away_id) -> (p_home, p_draw, p_away)`` (already de-vigged).
    Returns a new ``MatchModel`` sharing ``prior``'s base/home_adv/rho. ``weights`` (optional)
    scales each match's residual (time-decay / match-importance). ``shrinkage`` (optional, >= 0)
    adds a Tikhonov penalty pulling each strength toward its PRIOR value — regularization for
    sparse national teams (few/contradictory targets) so they stay near the Elo prior rather than
    overfitting. 0.0 = no shrinkage (unchanged).
    """
    if anchor_id not in prior.attack:
        raise ValueError(f"anchor_id {anchor_id} is not a team in the model")
    ids = sorted(prior.attack.keys())
    free = [t for t in ids if t != anchor_id]
    fi = {t: k for k, t in enumerate(free)}
    nfree = len(free)
    matches = list(targets.items())

    # Parameter vector: x[2k] = attack[free_k], x[2k+1] = defence[free_k].
    x = np.empty(2 * nfree)
    for t in free:
        x[2 * fi[t]] = prior.attack[t]
        x[2 * fi[t] + 1] = prior.defence[t]
    x0 = x.copy()  # the prior, the shrinkage target

    w = np.array([np.sqrt((weights or {}).get(m, 1.0)) for m, _ in matches], dtype=float)

    def model_from(xv: np.ndarray) -> MatchModel:
        attack = {anchor_id: prior.attack[anchor_id]}
        defence = {anchor_id: prior.defence[anchor_id]}
        for t in free:
            attack[t] = xv[2 * fi[t]]
            defence[t] = xv[2 * fi[t] + 1]
        return MatchModel(attack=attack, defence=defence, home_adv=prior.home_adv,
                          base=prior.base, rho=prior.rho)

    def residual(xv: np.ndarray) -> np.ndarray:
        m = model_from(xv)
        r = np.empty(3 * len(matches))
        for idx, ((h, a), tgt) in enumerate(matches):
            p = match_1x2(m, h, a, neutral=neutral, max_goals=max_goals)
            r[3 * idx:3 * idx + 3] = (np.array(p) - np.array(tgt)) * w[idx]
        return r

    for _ in range(iters):
        r0 = residual(x)
        # Forward-difference Jacobian (only params of teams in each match move that match's rows,
        # but a dense build keeps the code simple; calibration is offline).
        J = np.zeros((r0.size, x.size))
        for p in range(x.size):
            xp = x.copy()
            xp[p] += eps
            J[:, p] = (residual(xp) - r0) / eps
        JtJ = J.T @ J
        JtJ[np.diag_indices_from(JtJ)] += damping + shrinkage  # Levenberg + Tikhonov-to-prior
        grad = J.T @ r0 + shrinkage * (x - x0)  # shrinkage gradient pulls toward the prior
        try:
            dx = np.linalg.solve(JtJ, -grad)
        except np.linalg.LinAlgError:
            dx = np.linalg.lstsq(JtJ, -grad, rcond=None)[0]
        x = x + dx
        if np.linalg.norm(dx) < 1e-9:
            break

    return model_from(x)
