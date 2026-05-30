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
