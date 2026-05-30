"""Cache-key translation + the @st.cache_data MC wrapper (UI-02 / Phase 2x4 seam).

THE correctness module of Phase 2. ``@st.cache_data`` hashes each argument to build the
cache key; a raw ``dict`` (and its ``frozenset`` keys) is unhashable and raises
``UnhashableParamError``. The leading-underscore escape (``_locked``) silences the error
but EXCLUDES the arg from the key — which silently serves stale pre-lock distributions in
Live mode (Pitfall 13, the exact bug this seam forbids). The correct fix: convert ``locked``
(and ``ratings``) to a deterministic hashable tuple at the UI boundary, key the cache on
that real arg, and reconstruct the dict inside the wrapper.

``freeze_locked`` / ``freeze_ratings`` are pure (streamlit-free) and importable on their
own. ``run_mc_cached`` carries the ``@st.cache_data`` decorator (the only streamlit use).
"""

from __future__ import annotations

import streamlit as st

from engine.montecarlo import Result, run_mc
from engine.optimizer import OptimizerOutput, optimize
from engine.teams import load_teams

from ui.state import FIXED_SEED


def freeze_locked(locked: dict) -> tuple:
    """``dict[frozenset({a,b}) -> winner_id]`` -> a deterministic hashable cache key.

    Sort each pair's members AND sort the pairs, so the key is order-independent:
    ``{frozenset({9,1}): 1}`` and ``{frozenset({1,9}): 1}`` produce the SAME tuple.
    Round-trips: ``{frozenset(pair): winner for pair, winner in freeze_locked(d)} == d``.
    """
    return tuple(
        sorted((tuple(sorted(pair)), winner) for pair, winner in locked.items())
    )


def freeze_ratings(ratings: dict) -> tuple:
    """``{id: rating}`` -> a sorted tuple of ``(id, rating)`` (order-independent, hashable).

    Same rationale as freeze_locked: a deterministic representation so equal rating maps
    produce equal cache keys regardless of insertion order.
    """
    return tuple(sorted(ratings.items()))


@st.cache_data(show_spinner=False)
def run_mc_cached(
    ratings_key: tuple, S: float, N: int, locked_key: tuple
) -> Result:
    """Cached final MC Result. Cache key = ``(ratings_key, S, N, locked_key)`` — all hashable.

    ``locked_key`` is a REAL positional arg in the key (NOT the underscore escape) so a
    changed ``locked`` yields a different cached output (UI-02 / Phase 2x4 seam, Pitfall 13).
    ``show_spinner=False`` because plan 01 drives its own progress bar over
    run_mc_progressive — the cached path should not also flash the default spinner.

    Reconstructs the dicts the frozen engine wants from the hashable keys, loads the team
    template, and calls the FROZEN ``run_mc`` with ``seed=FIXED_SEED`` and the default
    ``n_chunks=20`` (DO NOT override — Phase 1x2 reproducibility).
    """
    ratings = dict(ratings_key)
    locked = {frozenset(pair): winner for pair, winner in locked_key}
    teams = load_teams()
    return run_mc(teams, ratings, S, N, locked=locked, seed=FIXED_SEED)


@st.cache_data(show_spinner=False)
def optimize_cached(
    _result: Result,
    ratings_key: tuple,
    S: float,
    N: int,
    locked_key: tuple,
    fetched_at=None,
) -> OptimizerOutput:
    """Cached Pick'Em optimizer output (OPT-01..05), memoized on the MC cache tuple.

    Cache key = ``(ratings_key, S, N, locked_key, fetched_at)`` — the SAME key as the app's run
    cache_key, so the recommendation recomputes only when the run does (when ``locked`` changes in
    Phase 4, or when a fresh odds fetch moves ``_meta.fetched_at`` in Phase 5 — T-05-STALEBAND).
    ``_result`` carries the leading underscore so it is EXCLUDED from the key: that is correct HERE
    (and the opposite of the ``locked`` rule) because the Result is a pure function of the key, so
    the already-computed Result can be reused without re-running the N-sim MC — the optimizer only
    scores ``_result.sample`` (ROADMAP SC4, never re-sims). ``fetched_at`` defaults None so the
    pre-Phase-5 rating-only call sites are unchanged.
    """
    return optimize(_result, load_teams())
