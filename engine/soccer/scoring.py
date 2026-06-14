"""Proper scoring rules + reliability for probabilistic 1X2 forecasts (Phase 1, reusable).

Extracted so the backtest, the CLV path, and any calibration check share one implementation.
Lower is better for all three scores. Outcomes are the ordered triple (home, draw, away).

- log-loss: penalizes confident errors hardest (optimization-oriented).
- Brier: decomposes into calibration + resolution; interpretable.
- RPS (Ranked Probability Score): rewards probability mass placed NEAR the true ordinal outcome —
  the football-standard 1X2 score (Constantinou & Fenton).
- reliability_bins: bins predicted probabilities vs realized frequency (the reliability diagram) so
  you can see whether the stated probabilities are honest, not just sharp.
"""

from __future__ import annotations

import math

_EPS = 1e-12


def outcome_index(home_goals: int, away_goals: int) -> int:
    """0 home win / 1 draw / 2 away win."""
    if home_goals > away_goals:
        return 0
    return 1 if home_goals == away_goals else 2


def log_loss(probs, actual: int) -> float:
    return -math.log(max(probs[actual], _EPS))


def brier(probs, actual: int) -> float:
    return sum((p - (1.0 if i == actual else 0.0)) ** 2 for i, p in enumerate(probs))


def rps(probs, actual: int) -> float:
    """Ranked Probability Score for ordered (home, draw, away). Lower is better."""
    y = [1.0 if i == actual else 0.0 for i in range(3)]
    cp = cy = total = 0.0
    for i in range(2):  # r-1 cumulative terms
        cp += probs[i]
        cy += y[i]
        total += (cp - cy) ** 2
    return total / 2.0


def score_set(preds, outcomes) -> dict[str, float]:
    """Mean log-loss / Brier / RPS over parallel lists of prob-triples and actual indices."""
    n = len(preds)
    if n == 0:
        return {"log_loss": float("nan"), "brier": float("nan"), "rps": float("nan"), "n": 0}
    return {
        "log_loss": sum(log_loss(p, a) for p, a in zip(preds, outcomes)) / n,
        "brier": sum(brier(p, a) for p, a in zip(preds, outcomes)) / n,
        "rps": sum(rps(p, a) for p, a in zip(preds, outcomes)) / n,
        "n": n,
    }


def reliability_bins(preds, outcomes, n_bins: int = 10) -> list[dict]:
    """Reliability diagram data over ALL (match, outcome-class) slots.

    For each predicted class probability, record whether that class occurred (1/0), bin by the
    predicted probability, and report the mean predicted probability vs the empirical frequency per
    non-empty bin. A well-calibrated model has ``mean_pred ≈ empirical`` in every bin.
    """
    pts: list[tuple[float, float]] = []
    for probs, actual in zip(preds, outcomes):
        for k, p in enumerate(probs):
            pts.append((p, 1.0 if k == actual else 0.0))
    out: list[dict] = []
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        sel = [(p, h) for p, h in pts if (lo <= p < hi) or (b == n_bins - 1 and p == hi)]
        if not sel:
            continue
        out.append({
            "lo": lo, "hi": hi, "n": len(sel),
            "mean_pred": sum(p for p, _ in sel) / len(sel),
            "empirical": sum(h for _, h in sel) / len(sel),
        })
    return out
