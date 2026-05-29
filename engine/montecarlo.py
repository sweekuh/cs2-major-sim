"""Monte Carlo runner — the headless probability engine (MC-01..06, ENG-09, PROB-03/05).

Generator-first / functional-core: imports no streamlit/httpx/requests. RNG is injected
purely via the ``seed`` parameter. The hot path is structured so all three cross-phase
seams are correct now (retrofitting any is a rewrite of the hottest path):

  - RNG (ENG-09, Pitfall 10): ``SeedSequence(seed).spawn(n_chunks)`` over a PINNED chunk
    count (default 20). Reproducibility depends only on (seed, n_chunks), both controlled,
    so the backtest harness and the shipped app run the SAME chunked path and the same
    (seed, N) yields identical per-team counts across runs and machines.

  - Generator-first (MC-05): ``run_mc_progressive`` is a GENERATOR that yields a
    ``Partial(done, total, running_p_adv)`` after each chunk (the Phase-2 progress bar +
    live tally) and ``return``s the final ``Result``. ``run_mc`` is a separate thin wrapper
    that drains it — the function Phase 2 decorates with ``@st.cache_data`` (no streamlit
    import here; just the two-function split).

  - Sample retention (MC-04): the FULL per-sim record sample (one {id: (wins, losses)}
    map per sim) is retained on the Result, not just marginal tallies — Phase 3 Ballot B
    hill-climbs P(>=5) against it and Phase 4 re-sim scores against it.

  - Epistemic OUTER loop (PROB-03/05): the chunk loop is wrapped in
    ``for p_vec in epistemic_draws(...)``; in Phase 1 ``epistemic_draws`` yields exactly
    ONE point draw (single-source no-op), so the epistemic spread is zero and the reported
    per-team band collapses to the inner hand-coded Wilson band. Phase 5 fills K Beta draws
    here without a rewrite.

Wilson confidence bands are computed by hand (MC-02) — no scipy.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np

from engine.probs import epistemic_draws
from engine.swiss import simulate_stage
from engine.teams import ADVANCE_AT_WINS, ELIMINATE_AT_LOSSES, Team

DEFAULT_N = 100_000
DEFAULT_N_CHUNKS = 20


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for ``k`` successes in ``n`` trials (MC-02, no scipy).

    Closed form; ``z`` defaults to 1.96 (95%). Returns (lo, hi); (0.0, 0.0) when n == 0.
    This is the inner ALEATORIC band; with one probability source the reported epistemic
    band collapses to exactly this (PROB-05).
    """
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d
    return (centre - half, centre + half)


@dataclass(frozen=True)
class Partial:
    """Per-chunk progress payload yielded by run_mc_progressive (MC-05, the Phase-2 seam).

    ``done`` sims completed of ``total``; ``running_p_adv`` is the per-team running
    P(advance) so the UI can show a live tally as chunks land.
    """

    done: int
    total: int
    running_p_adv: dict[int, float]


@dataclass
class Result:
    """Final MC aggregate (MC-01/02/04).

    Marginal tallies (``counts_30``/``counts_advance``/``counts_03``) plus the FULL retained
    per-sim record ``sample`` (MC-04) and the per-team Wilson ``band_*`` intervals (MC-02).
    With a single source the bands are the reported epistemic bands (PROB-05).
    """

    n: int
    counts_30: dict[int, int]
    counts_advance: dict[int, int]
    counts_03: dict[int, int]
    sample: list[dict[int, tuple[int, int]]]
    band_30: dict[int, tuple[float, float]] = field(default_factory=dict)
    band_advance: dict[int, tuple[float, float]] = field(default_factory=dict)
    band_03: dict[int, tuple[float, float]] = field(default_factory=dict)

    def p_30(self) -> dict[int, float]:
        return {tid: c / self.n for tid, c in self.counts_30.items()} if self.n else {}

    def p_advance(self) -> dict[int, float]:
        return {tid: c / self.n for tid, c in self.counts_advance.items()} if self.n else {}

    def p_03(self) -> dict[int, float]:
        return {tid: c / self.n for tid, c in self.counts_03.items()} if self.n else {}


def _fresh_teams(template: list[Team]) -> list[Team]:
    """Rebuild a clean per-sim team set from the template's identity fields.

    ``simulate_stage`` mutates wins/losses/opps, so every sim needs its OWN Team objects
    (the Wave-2 handoff note). Only id/name/seed/rating carry over; counters/opps reset.
    """
    return [Team(id=t.id, name=t.name, seed=t.seed, rating=t.rating) for t in template]


def _chunk_sizes(n: int, n_chunks: int) -> list[int]:
    """Split N across a PINNED chunk count deterministically (ENG-09, Pitfall 10).

    base = N // n_chunks; the first (N % n_chunks) chunks take one extra. The split depends
    only on (N, n_chunks), so it is identical across runs and machines.
    """
    base, rem = divmod(n, n_chunks)
    return [base + (1 if i < rem else 0) for i in range(n_chunks)]


def run_mc_progressive(
    teams: list[Team],
    ratings: dict[int, float] | None,
    S: float,
    N: int,
    locked: dict,
    *,
    seed: int,
    n_chunks: int = DEFAULT_N_CHUNKS,
) -> Iterator[Partial]:
    """Run N stage sims generator-first; yield a Partial per chunk, return the Result.

    ``teams`` is the seed->team template (each sim rebuilds fresh state from it; ENG-09's
    determinism comes from the RNG, not from reusing objects). ``ratings`` is the optional
    {id: rating} override (None -> each team's own rating; the Phase-5 seam). ``S`` is the
    logistic spread, ``N`` the sim count, ``locked`` the deterministic-winner dict (Phase-4
    seam), ``seed`` the only randomness source, ``n_chunks`` PINNED (default 20).

    Structure (RESEARCH Pattern 1/2/3):
      OUTER epistemic loop -> single point draw in Phase 1 (PROB-03/05);
      INNER aleatoric loop -> per chunk, per sim, call simulate_stage with that chunk's rng;
      tally per-team 3-0/advance/0-3 (MC-01) AND append the per-sim record vector (MC-04);
      yield Partial(done, total, running_p_adv) after each chunk (MC-05);
      finally aggregate per-team P with hand-coded Wilson bands (MC-02) and ``return`` it.
    """
    if N <= 0:
        raise ValueError(f"N must be a positive integer, got {N!r}")
    if n_chunks <= 0:
        raise ValueError(f"n_chunks must be a positive integer, got {n_chunks!r}")

    ids = [t.id for t in teams]
    counts_30 = {i: 0 for i in ids}
    counts_advance = {i: 0 for i in ids}
    counts_03 = {i: 0 for i in ids}
    sample: list[dict[int, tuple[int, int]]] = []

    sizes = _chunk_sizes(N, n_chunks)

    # OUTER epistemic loop (PROB-03/05): Phase 1 yields exactly one point draw, so the
    # spread across draws is zero and the reported band collapses to the inner Wilson band.
    # blend/var are single-source placeholders; Phase 5 supplies real per-source values.
    blend = [t.rating for t in teams]
    var = [0.0] * len(teams)
    for _p_vec in epistemic_draws(blend, var):
        # INNER aleatoric loop: pinned chunks, one child Generator each (chunk-safe repro).
        ss = np.random.SeedSequence(seed)
        child_seeds = ss.spawn(n_chunks)
        done = 0
        for chunk_idx, chunk_n in enumerate(sizes):
            # When n_chunks > N, _chunk_sizes emits trailing zero-sized chunks. Skip them
            # so they neither emit a spurious no-progress Partial (which would mislead the
            # Phase-2 UI) nor risk a divide-by-zero in running_p_adv before any sim lands.
            # Skipping is reproducibility-safe: a zero-sized chunk consumes no RNG draws,
            # so leaving its pinned child seed unused does not shift any other chunk.
            if chunk_n == 0:
                continue
            rng = np.random.default_rng(child_seeds[chunk_idx])
            for _ in range(chunk_n):
                by_id = simulate_stage(_fresh_teams(teams), ratings, S, rng, locked)
                rec: dict[int, tuple[int, int]] = {}
                for tid, t in by_id.items():
                    rec[tid] = (t.wins, t.losses)
                    if t.wins >= ADVANCE_AT_WINS:
                        counts_advance[tid] += 1
                        if t.losses == 0:
                            counts_30[tid] += 1
                    if t.losses >= ELIMINATE_AT_LOSSES and t.wins == 0:
                        counts_03[tid] += 1
                sample.append(rec)
                done += 1
            running_p_adv = {i: counts_advance[i] / done for i in ids}
            yield Partial(done=done, total=N, running_p_adv=running_p_adv)

    band_30 = {i: wilson(counts_30[i], N) for i in ids}
    band_advance = {i: wilson(counts_advance[i], N) for i in ids}
    band_03 = {i: wilson(counts_03[i], N) for i in ids}

    return Result(
        n=N,
        counts_30=counts_30,
        counts_advance=counts_advance,
        counts_03=counts_03,
        sample=sample,
        band_30=band_30,
        band_advance=band_advance,
        band_03=band_03,
    )


def run_mc(
    teams: list[Team],
    ratings: dict[int, float] | None,
    S: float,
    N: int = DEFAULT_N,
    locked: dict | None = None,
    *,
    seed: int,
    n_chunks: int = DEFAULT_N_CHUNKS,
) -> Result:
    """Drain run_mc_progressive and return the final Result (the cache-wrapper seam).

    This is the function Phase 2 decorates with ``@st.cache_data`` (key includes ``locked``
    so re-sim does not serve stale numbers). It imports no streamlit — it only drains the
    generator, discarding the per-chunk Partials and capturing the generator's return value.
    """
    gen = run_mc_progressive(
        teams, ratings, S, N, locked or {}, seed=seed, n_chunks=n_chunks
    )
    result: Result | None = None
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        result = stop.value
    if result is None:
        raise RuntimeError(
            "run_mc_progressive exhausted without returning a Result — "
            "this is an internal engine bug"
        )
    return result
