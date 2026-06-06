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
# Number of epistemic OUTER draws when real cross-source variance is present (PROB-03/04).
# Small (like DEFAULT_N_CHUNKS) — total sims = K * N. The rating-only / zero-var path uses
# exactly ONE draw so its counts stay byte-identical to the pre-Phase-5 hot path.
DEFAULT_EPISTEMIC_DRAWS = 12


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
    # SAMPLING-only (aleatoric) bands: the Wilson interval of the AGGREGATE marginal over all
    # n=len(sample) sims (D2, /plan-eng-review). band_* above is the EPISTEMIC across-draw union;
    # these are the inner sampling band the two-tone CI bar draws solid (the union is the faint
    # extension). With one no-op draw (rating-only) band_*_sampling == band_* exactly (the union of
    # a single draw IS wilson(counts, n)), so the two-tone bar collapses to single-tone, GATE-safe.
    band_30_sampling: dict[int, tuple[float, float]] = field(default_factory=dict)
    band_advance_sampling: dict[int, tuple[float, float]] = field(default_factory=dict)
    band_03_sampling: dict[int, tuple[float, float]] = field(default_factory=dict)

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


def _epistemic_inputs(teams, market_blend):
    """Build the (blend, var, match_keys) vectors the OUTER loop draws over.

    ``market_blend`` (the Phase-5 odds seam) is ``dict[str, tuple[float, float]]`` keyed by
    the id-bucket ``"lo-hi"`` carrying ``(p, var)`` for the imminent round's KNOWN matchups
    — ``p`` = P(lower-id team wins the series), ``var`` = raw cross-source variance (clamped
    downstream by ``beta_moment_fit``). None / empty -> a zero-var single-element vector,
    which the no-op guard in ``epistemic_draws`` collapses to a single ``list(blend)`` draw
    (the rating-only path, byte-identical counts).

    Returns (blend, var, keys): parallel lists where ``keys[i]`` is the id-bucket string the
    drawn ``p_vec[i]`` overrides; an empty market_blend yields a 1-element placeholder vector
    with var 0.0 and key None (no override).
    """
    if not market_blend:
        # Single-source no-op placeholder (matches the pre-Phase-5 behavior).
        return [0.0], [0.0], [None]
    keys = sorted(market_blend.keys())
    blend = [float(market_blend[k][0]) for k in keys]
    var = [float(market_blend[k][1]) for k in keys]
    return blend, var, keys


def run_mc_progressive(
    teams: list[Team],
    ratings: dict[int, float] | None,
    S: float,
    N: int,
    locked: dict,
    *,
    seed: int,
    n_chunks: int = DEFAULT_N_CHUNKS,
    market_blend: dict[str, tuple[float, float]] | None = None,
    k_epistemic: int = DEFAULT_EPISTEMIC_DRAWS,
    all_bo3: bool = False,
) -> Iterator[Partial]:
    """Run N stage sims generator-first; yield a Partial per chunk, return the Result.

    ``teams`` is the seed->team template (each sim rebuilds fresh state from it; ENG-09's
    determinism comes from the RNG, not from reusing objects). ``ratings`` is the optional
    {id: rating} override (None -> each team's own rating; the Phase-5 seam). ``S`` is the
    logistic spread, ``N`` the sim count, ``locked`` the deterministic-winner dict (Phase-4
    seam), ``seed`` the only randomness source, ``n_chunks`` PINNED (default 20).

    ``market_blend`` (keyword-only, the Phase-5 odds seam — default None = unchanged):
    ``dict["lo-hi" -> (p, var)]`` of the imminent round's market-priced matchups, ``p`` =
    P(lower-id team wins the series), ``var`` = raw cross-source (epistemic) variance.

    ``all_bo3`` (keyword-only, default False = unchanged; BO-01): forwarded straight to
    ``simulate_stage`` so True runs the stage all-Bo3 (the Stage-3 mode); False is the exact
    rating-only path (GATE-01).

    Structure (RESEARCH Pattern 1/2/3 + D6):
      OUTER epistemic loop -> ``epistemic_draws`` yields K perturbed p-vectors when real
        var is present (each drawn p becomes that draw's per-match ``market_overrides``),
        and EXACTLY ONE no-op draw when var is all-zero / no market_blend (so the
        rating-only counts are byte-identical and GATE-01 stays green; PROB-03/04);
      INNER aleatoric loop -> per chunk, per sim, call simulate_stage with that chunk's rng
        AND that draw's market_overrides;
      tally per-team 3-0/advance/0-3 (MC-01) AND append the per-sim record vector (MC-04);
      yield Partial after each chunk (MC-05);
      the reported per-team band is the UNION of each draw's inner Wilson interval across
        the K draws — so it ⊇ a single Wilson band and does NOT shrink with N on a
        high-disagreement match (the across-draw spread is N-invariant; only each draw's
        Wilson half-width narrows with N). With one no-op draw it collapses to exactly the
        single Wilson interval (PROB-05).
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

    # OUTER epistemic loop (PROB-03/04/05). Build the (blend, var) the draws perturb from
    # the market disagreement (D6: draw at the blended-MATCH level). var all-zero -> the
    # no-op guard yields exactly ONE draw -> byte-identical rating-only counts.
    blend, var, match_keys = _epistemic_inputs(teams, market_blend)
    has_epistemic = any(v > 0.0 for v in var)
    k = k_epistemic if has_epistemic else 1
    # A DISTINCT child SeedSequence per outer draw so the Beta perturbations are reproducible
    # AND the inner chunk RNG differs per draw (reproducibility survives the K draws).
    draw_ss = np.random.SeedSequence(seed).spawn(k) if has_epistemic else [None]
    beta_rng = np.random.default_rng(np.random.SeedSequence(seed).spawn(1)[0]) if has_epistemic else None

    # Per-draw per-team counts so the final band is the across-draw union of Wilson intervals.
    per_draw_adv: list[dict[int, int]] = []
    per_draw_30: list[dict[int, int]] = []
    per_draw_03: list[dict[int, int]] = []

    draw_idx = 0
    for p_vec in epistemic_draws(blend, var, k=k, rng=beta_rng):
        # Translate this draw's p-vector into the per-match market_overrides dict
        # (id-bucket keyed, p = P(lower-id wins)); None keys (no market_blend) -> no override.
        overrides = None
        if has_epistemic:
            overrides = {
                key: float(p_vec[i])
                for i, key in enumerate(match_keys)
                if key is not None
            }

        # Per-DRAW counts (accumulate the global counts across draws for the live tally).
        d_30 = {i: 0 for i in ids}
        d_adv = {i: 0 for i in ids}
        d_03 = {i: 0 for i in ids}

        # INNER aleatoric loop: pinned chunks, one child Generator each (chunk-safe repro).
        # Each outer draw uses its own child SeedSequence so the K draws do not share a stream.
        base_ss = draw_ss[draw_idx] if has_epistemic else np.random.SeedSequence(seed)
        child_seeds = base_ss.spawn(n_chunks)
        done = 0
        for chunk_idx, chunk_n in enumerate(sizes):
            # When n_chunks > N, _chunk_sizes emits trailing zero-sized chunks. Skip them
            # so they neither emit a spurious no-progress Partial (which would mislead the
            # Phase-2 UI) nor risk a divide-by-zero in running_p_adv before any sim lands.
            if chunk_n == 0:
                continue
            rng = np.random.default_rng(child_seeds[chunk_idx])
            for _ in range(chunk_n):
                by_id = simulate_stage(
                    _fresh_teams(teams), ratings, S, rng, locked,
                    market_overrides=overrides, all_bo3=all_bo3,
                )
                rec: dict[int, tuple[int, int]] = {}
                for tid, t in by_id.items():
                    rec[tid] = (t.wins, t.losses)
                    if t.wins >= ADVANCE_AT_WINS:
                        counts_advance[tid] += 1
                        d_adv[tid] += 1
                        if t.losses == 0:
                            counts_30[tid] += 1
                            d_30[tid] += 1
                    if t.losses >= ELIMINATE_AT_LOSSES and t.wins == 0:
                        counts_03[tid] += 1
                        d_03[tid] += 1
                sample.append(rec)
                done += 1
            total_done = sum(sum(d.values()) for d in per_draw_adv) + done
            running_p_adv = {i: counts_advance[i] / max(1, total_done) for i in ids}
            yield Partial(done=total_done, total=N * k, running_p_adv=running_p_adv)

        per_draw_30.append(d_30)
        per_draw_adv.append(d_adv)
        per_draw_03.append(d_03)
        draw_idx += 1

    # Reported band = UNION of each draw's inner Wilson interval across the K draws. With one
    # no-op draw it is exactly the single Wilson interval (byte-identical band, PROB-05).
    band_30 = _union_band(per_draw_30, N, ids)
    band_advance = _union_band(per_draw_adv, N, ids)
    band_03 = _union_band(per_draw_03, N, ids)

    # SAMPLING-only band (D2): the aleatoric Wilson of the AGGREGATE marginal over all len(sample)
    # == K*N sims. It is the INNER (solid) band of the two-tone CI bar; band_* above is the OUTER
    # (faint) epistemic union. With one draw len(sample)==N and counts==that draw's counts, so
    # band_*_sampling == band_* exactly -> the two-tone bar renders single-tone (GATE guard).
    n_total = len(sample)
    band_30_sampling = {i: wilson(counts_30[i], n_total) for i in ids}
    band_advance_sampling = {i: wilson(counts_advance[i], n_total) for i in ids}
    band_03_sampling = {i: wilson(counts_03[i], n_total) for i in ids}

    # n MUST be the total sims behind the counts, NOT N. Under the epistemic OUTER loop the K
    # draws accumulate counts_* and sample over K*N sims, so the valid normalizer is len(sample)
    # (== K*N). With one no-op draw (rating-only / var<=0) len(sample) == N, so p_* and the bands
    # stay byte-identical and GATE-01 holds. (P0 fix, /plan-eng-review 2026-05-31: n=N inflated
    # every p_advance()/p_30()/p_03() by K ~= 12 the moment market odds fed var>0.)
    return Result(
        n=len(sample),
        counts_30=counts_30,
        counts_advance=counts_advance,
        counts_03=counts_03,
        sample=sample,
        band_30=band_30,
        band_advance=band_advance,
        band_03=band_03,
        band_30_sampling=band_30_sampling,
        band_advance_sampling=band_advance_sampling,
        band_03_sampling=band_03_sampling,
    )


def _union_band(per_draw_counts, N, ids):
    """Per-team band = union of each draw's inner Wilson interval (the epistemic band).

    For each team, lo = min over draws of that draw's Wilson lo, hi = max over draws of that
    draw's Wilson hi. With a single draw this is exactly ``wilson(count, N)`` (so the
    rating-only band is byte-identical). With K draws over a high-disagreement match the
    across-draw spread of the point estimates inflates the union beyond a single Wilson band
    and does NOT shrink with N (only each draw's Wilson half-width narrows; PROB-05).
    """
    band: dict[int, tuple[float, float]] = {}
    for i in ids:
        los, his = [], []
        for d in per_draw_counts:
            lo, hi = wilson(d[i], N)
            los.append(lo)
            his.append(hi)
        band[i] = (min(los), max(his))
    return band


def run_mc(
    teams: list[Team],
    ratings: dict[int, float] | None,
    S: float,
    N: int = DEFAULT_N,
    locked: dict | None = None,
    *,
    seed: int,
    n_chunks: int = DEFAULT_N_CHUNKS,
    market_blend: dict[str, tuple[float, float]] | None = None,
    k_epistemic: int = DEFAULT_EPISTEMIC_DRAWS,
    all_bo3: bool = False,
) -> Result:
    """Drain run_mc_progressive and return the final Result (the cache-wrapper seam).

    This is the function Phase 2 decorates with ``@st.cache_data`` (key includes ``locked``
    so re-sim does not serve stale numbers). It imports no streamlit — it only drains the
    generator, discarding the per-chunk Partials and capturing the generator's return value.

    ``market_blend`` (the Phase-5 odds seam — default None = unchanged rating-only path):
    ``dict["lo-hi" -> (p, var)]`` of the imminent round's market-priced matchups; var>0
    drives the K-Beta epistemic outer loop, var all-zero / None is the exact no-op (GATE-01).

    ``all_bo3`` (the Stage-3 seam — default False = unchanged; BO-01): forwarded to
    ``run_mc_progressive`` so True runs the stage all-Bo3; False is byte-identical (GATE-01).
    """
    gen = run_mc_progressive(
        teams, ratings, S, N, locked or {}, seed=seed, n_chunks=n_chunks,
        market_blend=market_blend, k_epistemic=k_epistemic, all_bo3=all_bo3,
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
