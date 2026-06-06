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

from pathlib import Path

import streamlit as st

from engine.montecarlo import Result, run_mc
from engine.optimizer import OptimizerOutput, optimize
from engine.teams import load_stage

from ui.state import FIXED_SEED

# Repo-root-relative per-stage fixture paths (resolved like engine.teams.DATA_PATH so the
# wrapper works regardless of the process cwd). stage_id is the SHORT id that scopes the whole
# cache key — adding stages later means adding a row here + the data/stageN.json fixture.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_STAGE_FIXTURES = {
    "stage1": "data/stage1.json",
    "stage2": "data/stage2.json",
    "stage3": "data/stage3.json",
    "playoffs": "data/playoffs.json",
}


def _path_for_stage(stage_id: str) -> str:
    """Map a stage_id ('stage1'|'stage2'|'stage3'|'playoffs') -> its repo-root fixture path.

    Raises ValueError on an unknown stage_id (a typo must fail loud, never silently load the
    wrong stage). The path is absolute (repo-root-relative) so load_stage reads it from any cwd.
    """
    rel = _STAGE_FIXTURES.get(stage_id)
    if rel is None:
        raise ValueError(f"unknown stage_id {stage_id!r}; expected one of {sorted(_STAGE_FIXTURES)}")
    return str(_REPO_ROOT / rel)


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
    stage_id: str, ratings_key: tuple, S: float, N: int, locked_key: tuple
) -> Result:
    """Cached final MC Result. Cache key = ``(stage_id, ratings_key, S, N, locked_key)`` — all hashable.

    ``stage_id`` is a REAL leading positional in the key (NEVER the leading-underscore escape)
    so each stage scopes its OWN cache entry: two stages can never collide on a shared key and
    one stage can never serve another's cached Result (STG-04 — the cross-stage stale-serve gate).
    It also picks the RIGHT fixture — the body loads ``load_stage(_path_for_stage(stage_id))``,
    NOT the old always-Stage-1 loader (which was the v3 bug: every stage served Stage 1).

    ``locked_key`` is likewise a REAL positional (NOT the underscore escape) so a changed
    ``locked`` yields a different cached output (UI-02 / Phase 2x4 seam, Pitfall 13).
    ``show_spinner=False`` because plan 01 drives its own progress bar over
    run_mc_progressive — the cached path should not also flash the default spinner.

    Reconstructs the dicts the frozen engine wants from the hashable keys, loads the selected
    stage's teams, and calls the FROZEN ``run_mc`` with ``seed=FIXED_SEED`` and the default
    ``n_chunks=20`` (DO NOT override — Phase 1x2 reproducibility).
    """
    teams, _cfg = load_stage(_path_for_stage(stage_id))
    ratings = dict(ratings_key)
    locked = {frozenset(pair): winner for pair, winner in locked_key}
    return run_mc(teams, ratings, S, N, locked=locked, seed=FIXED_SEED)


@st.cache_data(show_spinner=False)
def optimize_cached(
    _result: Result,
    stage_id: str,
    ratings_key: tuple,
    S: float,
    N: int,
    locked_key: tuple,
    fetched_at=None,
) -> OptimizerOutput:
    """Cached Pick'Em optimizer output (OPT-01..05), memoized on the MC cache tuple.

    Cache key = ``(stage_id, ratings_key, S, N, locked_key, fetched_at)`` — the SAME key shape as the
    app's run cache_key, so the recommendation recomputes only when the run does (when ``stage_id``
    changes in Phase 6, when ``locked`` changes in Phase 4, or when a fresh odds fetch moves
    ``_meta.fetched_at`` in Phase 5 — T-05-STALEBAND). ``stage_id`` is a REAL key arg scoping the
    WHOLE key (NEVER the underscore escape), and the body loads the SELECTED stage's teams via
    ``load_stage(_path_for_stage(stage_id))`` — never the old always-Stage-1 loader (the v3 bug).
    ``_result`` carries the leading underscore so it is EXCLUDED from the key: that is correct HERE
    (and the opposite of the ``stage_id``/``locked`` rule) because the Result is a pure function of
    the key, so the already-computed Result can be reused without re-running the N-sim MC — the
    optimizer only scores ``_result.sample`` (ROADMAP SC4, never re-sims). ``fetched_at`` defaults
    None so the pre-Phase-5 rating-only call sites are unchanged.

    Element order MUST match run_mc_cached's params (stage_id leading) AND _cache_key_for in app.py,
    because app.py splats ``optimize_cached(result, *cache_key)``.
    """
    teams, _cfg = load_stage(_path_for_stage(stage_id))
    return optimize(_result, teams)
