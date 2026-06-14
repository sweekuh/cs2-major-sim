"""Pure odds-ensemble core: dataclasses, de-vig routing, and the log-opinion pool.

NON-NEGOTIABLES (CLAUDE.md + 05-RESEARCH D3/D4):
  - PURE numpy. NO httpx / python-dotenv import here (those live in the provider modules'
    live-fetch branch only, and in scripts/ in 05-03) and NO engine/app/ui import — so this
    module is unreachable from the app import path and collects with no httpx installed
    (D1/DX-01, threat T-05-APPIMPORT).
  - De-vig ROUTES on ``vig_type`` AT THE CALL SITE (Pitfall 8): the OddsPapi fixed-odds path
    calls ``devig_fixed_two_way`` (two-way overround removal); the prediction-market path
    calls ``normalize_market_price`` (price ≈ prob, spread/fee only). A market price is NEVER
    run through the two-way de-vig — there is no second decimal-odds side to normalize against
    (threat T-05-DEVIG).
  - ``pool()`` emits ``var`` RAW. The ``var < p(1-p)`` clamp lives in ONE place only —
    ``engine.probs.beta_moment_fit`` downstream (05-02). Do NOT pre-clamp ``var`` here, or the
    clamp logic forks (05-RESEARCH "do NOT pre-clamp in the file").
  - ``pool()`` sees only INDEPENDENT opinions. The OddsPapi soft-book bundle is pre-pooled to
    ONE Pinnacle-anchored opinion inside ``odds/oddspapi.py`` BEFORE pool() ever sees it, so
    pool() never headcounts the soft books (Pitfall 7, threat T-05-HEADCOUNT) — ``n_sources``
    counts independent originators, not books.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np

# Clamp epsilon keeping de-vigged/normalized probabilities strictly inside (0, 1) so the
# logit/Beta math downstream never hits ±inf or non-positive Beta params.
_EPS = 1e-6


@dataclass(frozen=True)
class OddsQuote:
    """One INDEPENDENT-source opinion on one Swiss series, keyed on engine team ids.

    ``match`` is the SORTED ``(lower_id, higher_id)`` engine-id tuple (never provider name
    spelling); ``p_a_raw`` is the de-vigged/normalized P(the LOWER-id team wins the SERIES)
    per this source. ``vig_type`` records which de-vig produced ``p_a_raw`` ("fixed" two-way
    overround for OddsPapi, "market" price-normalize for Polymarket/Kalshi). ``originate`` is
    1.0 for a sharp originator (Pinnacle / an independent market) and <1.0 for a soft copy;
    ``liquidity`` is a volume/handle proxy (0.0 if unknown). The OddsPapi soft-book bundle is
    collapsed to ONE such quote (Pinnacle-anchored) before pool() — pool() never sees the books.
    """

    provider: str
    match: tuple[int, int]
    p_a_raw: float
    vig_type: str
    bo3: bool
    liquidity: float
    originate: float
    ts: float


@dataclass(frozen=True)
class BlendedProb:
    """The cross-provider pooled opinion for one series.

    ``p`` is the pooled P(lower-id team wins the series) in (0, 1); ``var`` is the RAW
    cross-source (epistemic) variance — clamped downstream by ``beta_moment_fit``, NEVER here;
    ``n_sources`` is the number of INDEPENDENT opinions pooled (the OddsPapi bundle counts as 1).
    """

    p: float
    var: float
    n_sources: int
    bo3: bool


@runtime_checkable
class OddsProvider(Protocol):
    """Provider contract: parse a recorded fixture (dict or path) into independent opinions.

    Implementations parse defensively and yield ``[]`` for a missing/empty market (fail-soft,
    ODDS-05) rather than raising into the caller.
    """

    def get_quotes(self, fixtures, *, teams) -> list[OddsQuote]: ...


def devig_fixed_two_way(o_a: float, o_b: float) -> float:
    """OddsPapi fixed-odds: remove the two-way overround. HANDOFF §5 line 154, ODDS-02.

    ``ia, ib = 1/o_a, 1/o_b ; return ia / (ia + ib)``. The implied probabilities of a two-way
    market sum to >1 (the bookmaker's vig); renormalizing them to sum to 1 recovers the fair
    P(A wins). Verified: ``devig_fixed_two_way(1.5, 2.5) == 0.625``.

    This is the ONLY de-vig applied to a ``vig_type=="fixed"`` price and is NEVER applied to a
    market price (Pitfall 8).
    """
    ia, ib = 1.0 / o_a, 1.0 / o_b
    return ia / (ia + ib)


def normalize_market_price(price_a: float, *, spread: float = 0.0, fee: float = 0.0) -> float:
    """Polymarket/Kalshi: the price already IS ≈ a probability — remove only spread/fee.

    ``p = price_a - 0.5*spread - fee``, clamped strictly into ``(_EPS, 1-_EPS)``. There is NO
    second decimal-odds side here, so the fixed-odds two-way de-vig is NEVER applied to a market
    price — doing so silently mangles a value that was already a probability (Pitfall 8).
    """
    p = price_a - 0.5 * spread - fee
    return min(1.0 - _EPS, max(_EPS, p))


@dataclass(frozen=True)
class Quote1X2:
    """One INDEPENDENT-source opinion on one soccer 1X2 (home/draw/away) match.

    Soccer match markets are THREE-outcome, so the 2-outcome ``OddsQuote`` cannot carry them
    without silently dropping the draw (which corrupts every calibration target). ``match`` is
    an opaque ordered key for the fixture (e.g. ``(home_id, away_id)`` engine-id tuple). The
    three de-vigged probabilities sum to 1.0 per this source. ``originate``/``liquidity`` weight
    the source in ``pool_1x2`` exactly as in the 2-outcome ``pool``.
    """

    provider: str
    match: tuple[int, int]
    p_home: float
    p_draw: float
    p_away: float
    originate: float
    liquidity: float
    ts: float


@dataclass(frozen=True)
class BlendedProb1X2:
    """The cross-source pooled 1X2 opinion for one soccer match.

    ``p_home``/``p_draw``/``p_away`` sum to 1.0; ``var`` is the per-outcome RAW cross-source
    (epistemic) variance triple — clamped downstream, never here; ``n_sources`` counts
    independent opinions pooled. This is both the calibration target for the goals model and
    the reference for cross-venue (Kalshi vs Polymarket) divergence on match markets.
    """

    p_home: float
    p_draw: float
    p_away: float
    var: tuple[float, float, float]
    n_sources: int

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.p_home, self.p_draw, self.p_away)


def devig_three_way(o_h: float, o_d: float, o_a: float) -> tuple[float, float, float]:
    """Fixed-odds 1X2: remove the three-way overround. The soccer analog of ``devig_fixed_two_way``.

    Implied probabilities ``1/o`` for home/draw/away sum to >1 (the book's vig); renormalizing
    them to sum to 1 recovers the fair ``(P(home), P(draw), P(away))``. Verified:
    ``devig_three_way(2.0, 4.0, 4.0)`` (implied 0.5/0.25/0.25, sum 1.0) ``== (0.5, 0.25, 0.25)``.

    This is the ONLY de-vig applied to fixed 1X2 odds and is NEVER applied to a market price
    (the prediction-market path uses ``normalize_market_price`` per outcome; Pitfall 8).
    """
    ih, id_, ia = 1.0 / o_h, 1.0 / o_d, 1.0 / o_a
    s = ih + id_ + ia
    return (ih / s, id_ / s, ia / s)


def devig_shin(inverse_odds: list[float]) -> list[float]:
    """Shin's-method de-vig of raw inverse odds (1/o per outcome) — the favorite-longshot-aware
    alternative to proportional normalization (Štrumbelj 2014: more accurate true probabilities).

    Shin (1992) models the overround as protection against a proportion ``z`` of insider trading;
    the true probabilities satisfy
        p_i = (sqrt(z² + 4(1-z)·r_i²/B) - z) / (2(1-z)),   B = Σ r_i,
    with ``z`` chosen so Σ p_i = 1 (``Σ p_i`` is strictly decreasing in z, so a bisection finds it).
    Loading the vig onto longshots gives the favourite a slightly HIGHER true prob than proportional
    de-vig. With no overround (B ≤ 1) there is nothing to Shin-correct, so it falls back to plain
    normalization. Returns probabilities summing to 1.
    """
    r = [float(x) for x in inverse_odds]
    B = sum(r)
    if B <= 1.0:  # no overround (or an arb) — Shin's z would be non-positive; just normalize.
        return [x / B for x in r]

    def p_of(z: float) -> list[float]:
        return [(math.sqrt(z * z + 4.0 * (1.0 - z) * ri * ri / B) - z) / (2.0 * (1.0 - z)) for ri in r]

    lo, hi = 0.0, 0.9999
    for _ in range(100):  # bisection on z; Σp(z) decreases from sqrt(B)>1 toward <1
        mid = 0.5 * (lo + hi)
        if sum(p_of(mid)) > 1.0:
            lo = mid
        else:
            hi = mid
    p = p_of(0.5 * (lo + hi))
    s = sum(p)
    return [x / s for x in p]  # renormalize away any residual bisection error


def devig_three_way_shin(o_h: float, o_d: float, o_a: float) -> tuple[float, float, float]:
    """Shin's-method de-vig of fixed 1X2 odds -> (P(home), P(draw), P(away)). See ``devig_shin``."""
    p = devig_shin([1.0 / o_h, 1.0 / o_d, 1.0 / o_a])
    return (p[0], p[1], p[2])


def devig_power(inverse_odds: list[float]) -> list[float]:
    """Power-method de-vig: fair p_i = (1/o_i)**k with k chosen so Σ p_i = 1.

    Raising the raw inverse odds (each < 1 when there's an overround) to a power k > 1 shrinks them
    to sum to 1 while amplifying the favourite/longshot ratio — a favorite-longshot correction in
    the same spirit as Shin, but multiplicative and without an insider model (a cheaper alternative
    to A/B against Shin on CLV). With no overround (B ≤ 1) it falls back to plain normalization.
    """
    r = [float(x) for x in inverse_odds]
    B = sum(r)
    if B <= 1.0:
        return [x / B for x in r]
    lo, hi = 1.0, 50.0  # Σ r_i^k decreases from B>1 (k=1) toward 0; a root k>1 with Σ=1 exists
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if sum(x ** mid for x in r) > 1.0:
            lo = mid
        else:
            hi = mid
    k = 0.5 * (lo + hi)
    p = [x ** k for x in r]
    s = sum(p)
    return [x / s for x in p]


def devig_three_way_power(o_h: float, o_d: float, o_a: float) -> tuple[float, float, float]:
    """Power-method de-vig of fixed 1X2 odds -> (P(home), P(draw), P(away)). See ``devig_power``."""
    p = devig_power([1.0 / o_h, 1.0 / o_d, 1.0 / o_a])
    return (p[0], p[1], p[2])


def devig_1x2(o_h: float, o_d: float, o_a: float, *, method: str = "shin") -> tuple[float, float, float]:
    """Dispatch 1X2 de-vig by ``method``: 'shin' (default), 'power', or 'proportional'."""
    if method == "shin":
        return devig_three_way_shin(o_h, o_d, o_a)
    if method == "power":
        return devig_three_way_power(o_h, o_d, o_a)
    if method == "proportional":
        return devig_three_way(o_h, o_d, o_a)
    raise ValueError(f"unknown de-vig method {method!r} (use 'shin', 'power', or 'proportional')")


def pool_1x2(quotes: list["Quote1X2"]) -> "BlendedProb1X2":
    """Weighted log-opinion pool of INDEPENDENT 1X2 opinions for ONE match (the 3-outcome ``pool``).

    A log-opinion pool over a categorical distribution is the normalized weighted GEOMETRIC mean:
    ``log p_k_bar = Σ w_i log p_ik``, ``p_k = exp(log p_k_bar)`` renormalized to sum 1. Weighting
    matches ``pool``: ``w_i = originate_i * log1p(liquidity_i)`` (normalized; equal-weight fallback
    when all weights degenerate). Per-outcome epistemic variance is the weighted spread of the
    log-probabilities mapped to p-space by the delta method ``var_k ≈ p_k^2 * Σ w_i (log p_ik -
    log p_k_bar)^2`` — agreeing sources -> var≈0; a single source -> var==0. ``var`` is RAW.
    """
    n = len(quotes)
    logs = np.array([[q.p_home, q.p_draw, q.p_away] for q in quotes], dtype=float)
    logs = np.log(np.clip(logs, _EPS, 1.0))
    w = np.array([q.originate * np.log1p(q.liquidity) for q in quotes], dtype=float)
    total = w.sum()
    if total <= 0.0:
        w = np.ones(n, dtype=float)
        total = w.sum()
    w = w / total
    logbar = (w[:, None] * logs).sum(axis=0)  # per-outcome weighted mean log-prob
    p = np.exp(logbar)
    p = p / p.sum()
    logit_var = (w[:, None] * (logs - logbar) ** 2).sum(axis=0)
    var = (p ** 2) * logit_var  # delta method for the exp transform
    return BlendedProb1X2(
        p_home=float(p[0]),
        p_draw=float(p[1]),
        p_away=float(p[2]),
        var=(float(var[0]), float(var[1]), float(var[2])),
        n_sources=n,
    )


def _logit(p):
    """Log-odds. Operates elementwise on a numpy array of probabilities in (0, 1)."""
    return np.log(p / (1.0 - p))


def _sigmoid(x):
    """Inverse-logit. Maps a (weighted) mean log-odds back to a probability."""
    return 1.0 / (1.0 + np.exp(-x))


def pool(quotes: list[OddsQuote]) -> BlendedProb:
    """Weighted log-opinion pool of INDEPENDENT opinions for ONE match (ODDS-03, D4).

    A log-opinion pool is the weighted GEOMETRIC mean in logit space — the standard for pooling
    sharp market/expert probability opinions (a linear pool blurs the consensus signal markets
    carry). The caller passes quotes ALREADY collapsed to one-per-originate-source: the OddsPapi
    soft-book bundle is pre-pooled to a single Pinnacle-anchored opinion in ``odds/oddspapi.py``,
    so pool() never headcounts the soft books (Pitfall 7).

    Weighting:  ``w_i = originate_i * log1p(liquidity_i)`` (normalized) — sharp originators and
    deeper markets pull harder; copies and thin markets pull less.
    Point:      ``z = logit(p_a_raw); zbar = Σ w_i z_i; p = sigmoid(zbar)``.
    Variance:   ``logit_var = Σ w_i (z_i - zbar)^2`` (the weighted spread of opinions in logit
                space — the EPISTEMIC, source-disagreement spread), mapped to p-space by the
                delta method ``var = (p(1-p))^2 * logit_var`` (``dp/dz = p(1-p)``). Agreeing
                sources -> logit_var≈0 -> var≈0 (the band collapses to the inner Wilson, PROB-05);
                a single source -> logit_var==0 -> var==0. ``var`` is RAW — the ``var<p(1-p)``
                clamp is applied ONCE downstream in ``beta_moment_fit``, never here.

    ``n_sources`` = number of independent opinions pooled; ``bo3`` carried from the first quote
    (all quotes for one match share a series format).
    """
    ps = np.array([q.p_a_raw for q in quotes], dtype=float)
    w = np.array([q.originate * np.log1p(q.liquidity) for q in quotes], dtype=float)
    total = w.sum()
    # Degenerate weights (e.g. all-zero liquidity -> log1p(0)==0): fall back to equal weight so
    # a thin-but-real set of opinions still pools rather than dividing by zero.
    if total <= 0.0:
        w = np.ones_like(w)
        total = w.sum()
    w = w / total
    z = _logit(ps)
    zbar = float((w * z).sum())
    p = float(_sigmoid(zbar))
    logit_var = float((w * (z - zbar) ** 2).sum())
    var = (p * (1.0 - p)) ** 2 * logit_var  # delta method: Var(p) ≈ (dp/dz)^2 Var(z)
    return BlendedProb(p=p, var=var, n_sources=len(quotes), bo3=quotes[0].bo3)
