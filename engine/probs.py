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
from math import comb


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


def series_best_of(p: float, n_maps: int) -> float:
    """Win probability of a best-of-``n_maps`` series given a per-map win prob ``p``.

    Closed form for first-to-(n_maps // 2 + 1) maps with iid maps (NO per-map sampling) — one
    Bernoulli draw decides the series, exactly like ``series`` (MC-06). ``n_maps`` must be a
    positive ODD integer:
      - n_maps == 1 -> the identity ``p`` (a single map);
      - n_maps == 3 -> ``p^2 (3 - 2p)`` — byte-identical to ``series(p, bo3=True)``;
      - n_maps == 5 -> the Bo5 closed form ``p^3 (1 + 3q + 6q^2)``, q = 1 - p.

    This is a NEW SIBLING of the frozen ``series``: the Bo1/Bo3 GATE-01 path through ``series`` /
    ``series_prob`` is untouched. The playoff bracket (Bo3 quarter/semis, Bo5 grand final, PLAY-01)
    is the only consumer — it needs the Bo5 term ``series`` deliberately never grew.
    """
    if n_maps < 1 or n_maps % 2 == 0:
        raise ValueError(f"n_maps must be a positive odd integer, got {n_maps!r}")
    need = n_maps // 2 + 1  # maps to clinch the series
    q = 1.0 - p
    # P(win) = sum_{k=0}^{need-1} C(need-1+k, k) p^need q^k  (opponent takes k maps before we clinch).
    total = 0.0
    for k in range(need):
        total += comb(need - 1 + k, k) * (p**need) * (q**k)
    return total


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
    *,
    k: int = 1,
    rng=None,
) -> Iterator[Sequence[float]]:
    """Epistemic OUTER-loop generator (PROB-03/04/05).

    Yields ``k`` per-element draws of the p-vector. The draw lives ONLY here (the OUTER
    loop); burying it in the inner per-sim loop would fold epistemic spread into aleatoric
    noise and make the Wilson band falsely tight at large N (Pitfall 4).

    NO-OP PATH (GATE guard, T-05-GATE): if ``rng is None`` OR every ``var`` element is
    ``<= 0`` (the rating-only / single-source case), yield ``list(blend)`` EXACTLY ``k``
    times. With the defaults ``k=1, rng=None`` this is a single ``yield list(blend)`` —
    BYTE-IDENTICAL to the Phase-1 stub, so the rating-only counts are unchanged and GATE-01
    stays green.

    BETA PATH (real cross-source disagreement, ``var > 0`` with an ``rng``): each draw
    perturbs every element with ``var > 0`` via ``rng.beta(*beta_moment_fit(mean, v))`` —
    the OUTER epistemic spread (PROB-03/04). The variance clamp is the EXISTING
    ``beta_moment_fit`` (var < mean*(1-mean)); it is CALLED here, never re-implemented
    (Pitfall 5 / T-05-CLAMP) so a thin-liquidity high-var match never crashes ``rng.beta``.
    """
    if rng is None or all(v <= 0.0 for v in var):
        for _ in range(k):
            yield list(blend)
        return
    for _ in range(k):
        yield [
            float(rng.beta(*beta_moment_fit(m, v))) if v > 0.0 else m
            for m, v in zip(blend, var)
        ]


def beta_moment_fit(mean: float, var: float) -> tuple[float, float]:
    """Beta method-of-moments fit returning (alpha, beta), clamping var < mean*(1-mean).

    The maximum variance of a Beta with the given mean is ``mean*(1-mean)``; a supplied
    variance at or above that bound drives the Beta parameters non-negative and crashes on
    exactly the low-liquidity, high-disagreement matches that matter most (Pitfall 5).
    Clamp strictly below the bound before fitting (PROB-04).

    Unused until Phase 5 fills epistemic_draws, but present and structured now.
    """
    # Clamp the mean strictly inside (0, 1): a degenerate mean of 0.0 or 1.0 drives
    # bound to 0.0, which would yield non-positive alpha/beta and crash
    # numpy.random.Generator.beta (both params must be strictly > 0).
    eps = 1e-9
    mean = max(eps, min(1.0 - eps, mean))
    bound = mean * (1.0 - mean)
    # Keep the variance STRICTLY below the maximal bound so common = bound/v - 1 stays
    # strictly positive and both alpha/beta come out > 0. A multiplicative ceiling
    # (rather than bound - eps) is robust even when bound itself is tiny near mean 0/1.
    v = min(var, bound * (1.0 - eps))
    v = max(v, eps * bound)
    common = bound / v - 1.0
    alpha = mean * common
    beta = (1.0 - mean) * common
    return alpha, beta
