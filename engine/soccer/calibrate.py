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

import numpy as np

from engine.soccer.dixon_coles import MatchModel, match_1x2

Target = dict[tuple[int, int], tuple[float, float, float]]


def calibrate_strengths(prior: MatchModel, targets: Target, *, anchor_id: int,
                        iters: int = 60, neutral: bool = True, damping: float = 1e-2,
                        eps: float = 1e-4, weights: dict[tuple[int, int], float] | None = None,
                        max_goals: int = 8) -> MatchModel:
    """Fit (attack, defence) so model 1X2 matches ``targets``; anchor's strengths held fixed.

    ``targets`` maps ``(home_id, away_id) -> (p_home, p_draw, p_away)`` (already de-vigged).
    Returns a new ``MatchModel`` sharing ``prior``'s base/home_adv/rho. ``weights`` (optional)
    scales each match's residual (time-decay / match-importance).
    """
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
        JtJ[np.diag_indices_from(JtJ)] += damping  # Levenberg damping
        try:
            dx = np.linalg.solve(JtJ, -J.T @ r0)
        except np.linalg.LinAlgError:
            dx = np.linalg.lstsq(JtJ, -J.T @ r0, rcond=None)[0]
        x = x + dx
        if np.linalg.norm(dx) < 1e-9:
            break

    return model_from(x)
