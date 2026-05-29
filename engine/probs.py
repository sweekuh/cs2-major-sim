"""Pure probability math for the Swiss MC core.

No state, no I/O, no streamlit/httpx/requests. Every function here is referentially
transparent so the backtest gate can verify it in isolation.

Load-bearing facts (getting any wrong silently corrupts every probability):
  - p_map is the logistic per-map win prob, S default 40 (PROB-01).
  - series() is the Bo3 closed form p^2(3-2p) as a SINGLE Bernoulli draw (MC-06) —
    never sample three map Bernoullis.
  - An odds-derived series prob for THIS matchup passes through untouched; Bo3 is NOT
    re-applied (PROB-02) — the market already prices the series.
  - difficulty() is Buchholz = sum(opp.wins - opp.losses), NOT sum(opp.wins) (ENG-03).
  - Epistemic (source-disagreement) variance is an OUTER loop; Phase 1 yields exactly one
    point draw (single-source no-op) so the reported band collapses to the inner Wilson
    band. The Beta method-of-moments fit clamps var < p(1-p) before fitting (PROB-03/04/05).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence


def p_map(ra: float, rb: float, S: float = 40.0) -> float:
    """Logistic per-map win probability of team A (rating ``ra``) vs B (``rb``).

    p_map(r, r) == 0.5; the higher-rated team is favored. S (default 40) becomes a
    Phase-2 slider: lower S -> bigger favorites, higher S -> more coinflips (PROB-01).
    """
    return 1.0 / (1.0 + 10 ** (-(ra - rb) / S))


def series(p: float, bo3: bool) -> float:
    """Series win probability from a per-map win prob ``p``.

    Bo3 closed form ``p^2 * (3 - 2p)`` (exact for iid maps) used as a single Bernoulli
    draw by the MC; Bo1 is the identity. Verified: series(0.6, True) == 0.648,
    series(0.5, True) == 0.5 (MC-06).
    """
    return p * p * (3 - 2 * p) if bo3 else p


def series_prob(
    *,
    ra: float,
    rb: float,
    bo3: bool,
    market_series_prob: float | None = None,
    S: float = 40.0,
) -> float:
    """Resolve the series win prob for THIS matchup, honoring an odds override.

    If ``market_series_prob`` is supplied (Phase 5 odds layer), it is used directly and
    series()/Bo3 is NOT re-applied — the market already prices the series (PROB-02).
    Otherwise fall back to ``series(p_map(ra, rb, S), bo3)``.

    The market source is stubbed as ``None`` in Phase 1 (odds arrive Phase 5), but the
    branch is wired now so Phase 5 only supplies the value.
    """
    if market_series_prob is not None:
        return market_series_prob
    return series(p_map(ra, rb, S=S), bo3)


def difficulty(t) -> int:
    """Valve Difficulty Score (Buchholz) for a team ``t``.

    ``sum(opp.wins - opp.losses for opp in t.opps)`` — NOT ``sum(opp.wins)`` (ENG-03).
    Verified against the rulebook's worked example: opponents 2-0 and 1-1 -> (2+1)-(0+1)
    == 2. This is the canonical definition; swiss.py imports it in wave 2 (no second copy).
    """
    return sum(o.wins - o.losses for o in t.opps)


def epistemic_draws(
    blend: Sequence[float],
    var: Sequence[float],
) -> Iterator[Sequence[float]]:
    """Epistemic OUTER-loop generator (PROB-03).

    Phase 1 has exactly one probability source (ratings), so this yields EXACTLY ONE
    point p-vector (the blend, a single-source no-op). Because the spread across draws is
    zero, the reported band collapses to the inner Wilson (aleatoric) band (PROB-05).

    The loop is structured OUTER now so Phase 5 fills K Beta draws
    (``rng.beta(*beta_moment_fit(mean, v))`` per element) without a rewrite — burying the
    Beta draw in the inner per-sim loop would fold epistemic into aleatoric noise and make
    the Wilson band falsely tight at large N (Pitfall 4).
    """
    yield list(blend)


def beta_moment_fit(mean: float, var: float) -> tuple[float, float]:
    """Beta method-of-moments fit returning (alpha, beta), clamping var < mean*(1-mean).

    The maximum variance of a Beta with the given mean is ``mean*(1-mean)``; a supplied
    variance at or above that bound drives the Beta parameters non-negative and crashes on
    exactly the low-liquidity, high-disagreement matches that matter most (Pitfall 5).
    Clamp strictly below the bound before fitting (PROB-04).

    Unused until Phase 5 fills epistemic_draws, but present and structured now.
    """
    bound = mean * (1.0 - mean)
    # Clamp strictly below the bound; epsilon keeps alpha/beta finite and positive.
    eps = 1e-9
    v = min(var, bound - eps) if bound > eps else eps
    v = max(v, eps)
    common = mean * (1.0 - mean) / v - 1.0
    alpha = mean * common
    beta = (1.0 - mean) * common
    return alpha, beta
