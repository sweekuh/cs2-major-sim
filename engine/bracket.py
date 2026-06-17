"""Playoff single-elimination bracket simulator — the Champions-stage core (PLAY-01).

The Swiss engine (``engine.swiss``) is a record-bucket format; the playoffs are a fixed
8-team single-elimination BRACKET, a different shape (ROADMAP v4 — deliberately NOT another
Swiss ``_NEXT_STAGE`` entry). This module owns that shape as a PURE, streamlit-free /
httpx-free functional core, mirroring the discipline of ``engine.swiss`` / ``engine.montecarlo``:

  - The bracket TREE is DERIVED from the 8 seeds via the canonical Major seeding
    (1v8, 4v5, 2v7, 3v6, with seeds 1 and 2 in opposite halves so they meet only in the
    final). There is ONE structure table (``QF_SEEDS`` / ``SF_FEEDERS`` / ``GF_FEEDERS``) —
    no second hardcoded matchup list (the ENG-01 "single source" rule).
  - Series are resolved by ONE Bernoulli draw against the closed-form best-of-N win prob
    (``engine.probs.series_best_of``) — Bo3 quarters/semis, Bo5 grand final — never per-map
    sampling (MC-06). Ratings drive it; a ``locked`` matchup is deterministic (the live seam,
    mirroring ``engine.swiss._play``).
  - RNG is injected purely via the ``seed`` parameter over a PINNED chunk count, so the same
    (seed, N) yields identical per-team counts across runs and machines (ENG-09).

The retained per-sim ``sample`` (one ``{match_label: winner_id}`` map per sim) is the contract
the playoff Pick'Em optimizer scores against (``engine.playoff_optimizer``) — it never re-runs
the bracket MC (the OPT-04 sample-only rule, one stage up).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np

from engine.montecarlo import Partial, wilson
from engine.probs import p_map, series_best_of
from engine.teams import Team

# ---------------------------------------------------------------------------
# The canonical 8-team single-elim bracket structure — ONE source (ENG-01).
# QF matchups by SEED (1v8, 4v5, 2v7, 3v6): the standard Major seeding so the two top seeds
# are in opposite halves and can only meet in the grand final. SF/GF reference earlier labels.
# ---------------------------------------------------------------------------
QF_SEEDS: dict[str, tuple[int, int]] = {
    "QF1": (1, 8),
    "QF2": (4, 5),
    "QF3": (2, 7),
    "QF4": (3, 6),
}
# Top half (QF1, QF2) -> SF1; bottom half (QF3, QF4) -> SF2 (matches the official bracket render).
SF_FEEDERS: dict[str, tuple[str, str]] = {
    "SF1": ("QF1", "QF2"),
    "SF2": ("QF3", "QF4"),
}
GF_FEEDERS: tuple[str, str] = ("SF1", "SF2")

QF_LABELS: tuple[str, ...] = ("QF1", "QF2", "QF3", "QF4")
SF_LABELS: tuple[str, ...] = ("SF1", "SF2")
MATCH_ORDER: tuple[str, ...] = (*QF_LABELS, *SF_LABELS, "GF")

# Series length per round: Bo3 quarters/semis, Bo5 grand final (PLAY-01). Overridable per
# fixture via the stage config (data/playoffs.json: stage.qf_bo / sf_bo / gf_bo).
DEFAULT_BO: dict[str, int] = {"qf": 3, "sf": 3, "gf": 5}

DEFAULT_N = 100_000
DEFAULT_N_CHUNKS = 20


def bo_from_stage_cfg(cfg: dict | None) -> dict[str, int]:
    """Read the per-round series lengths from a stage config -> the ``{"qf","sf","gf"}`` bo dict.

    The fixture (data/playoffs.json) stores ``stage.qf_bo`` / ``sf_bo`` / ``gf_bo`` (the human-facing
    keys); the engine consumes the compact ``{"qf","sf","gf"}`` form. Any missing key falls back to
    ``DEFAULT_BO`` (Bo3 quarters/semis, Bo5 final), so an older fixture without the keys still runs.
    """
    cfg = cfg or {}
    return {
        "qf": int(cfg.get("qf_bo", DEFAULT_BO["qf"])),
        "sf": int(cfg.get("sf_bo", DEFAULT_BO["sf"])),
        "gf": int(cfg.get("gf_bo", DEFAULT_BO["gf"])),
    }


def overrides_from_named_lines(
    teams: list[Team], lines: dict[tuple[str, str], float]
) -> dict[str, float]:
    """Build the ``market_overrides`` dict from human-facing named series lines (fail-loud).

    ``lines`` maps a ``(team_a_name, team_b_name)`` tuple (a priced matchup) to ``p`` = P(the
    FIRST-named team wins the SERIES). Returns the id-bucket-keyed ``{"lo-hi": P(lower-id wins)}``
    dict that ``simulate_bracket`` / ``run_playoff_mc`` consume — the p is oriented to the lower id
    here so the engine seam stays orientation-agnostic. The series price is passed through verbatim
    (best-of NOT re-applied downstream, PROB-02).

    FAIL-LOUD (mirrors the fit-target validators): an unknown team name, a self-pair, a ``p`` not
    strictly in (0, 1), or the SAME matchup listed twice (even with the names swapped) raises
    ValueError rather than silently producing a half-specified or self-contradictory override set —
    a wrong line would quietly mis-price a whole half of the bracket.
    """
    id_of = {t.name: t.id for t in teams}
    out: dict[str, float] = {}
    for pair, raw_p in lines.items():
        a_name, b_name = pair
        for nm in (a_name, b_name):
            if nm not in id_of:
                raise ValueError(
                    f"unknown team name {nm!r} in market line; known teams: {sorted(id_of)}"
                )
        a_id, b_id = id_of[a_name], id_of[b_name]
        if a_id == b_id:
            raise ValueError(f"market line pairs a team with itself: {a_name!r}")
        p = float(raw_p)
        if not (0.0 < p < 1.0) or p != p:
            raise ValueError(
                f"series win prob for ({a_name} vs {b_name}) must be strictly in (0, 1), got {raw_p!r}"
            )
        bucket = f"{min(a_id, b_id)}-{max(a_id, b_id)}"
        if bucket in out:
            raise ValueError(f"matchup {a_name} vs {b_name} (bucket {bucket}) is listed twice")
        out[bucket] = p if a_id < b_id else (1.0 - p)  # orient to the LOWER id
    return out


def _n_maps(label: str, bo: dict[str, int]) -> int:
    """Series length (odd map count) for a match label, from the per-round bo config."""
    if label in QF_LABELS:
        return bo["qf"]
    if label in SF_LABELS:
        return bo["sf"]
    return bo["gf"]  # "GF"


def _play_match(
    a: Team, b: Team, ratings, S, rng, locked, n_maps: int, *, market_overrides=None
) -> Team:
    """Resolve one bracket match, returning the WINNING Team (reads ratings; mutates nothing).

    A ``locked`` entry (``frozenset({a.id, b.id}) -> winner_id``) is deterministic and takes
    precedence over EVERYTHING (the live seam, mirroring ``engine.swiss._play``). Otherwise a
    SINGLE Bernoulli decides it against the series win prob — never three/five map samples (MC-06).
    ``ratings`` is the optional ``{id: rating}`` override (None -> each team's own ``.rating``).

    ``market_overrides`` (keyword-only, the playoff odds seam — default None = unchanged; mirrors
    ``engine.swiss._play``'s PROB-02 seam): ``dict[str, float]`` keyed by the id-bucket
    ``f"{min(a.id, b.id)}-{max(a.id, b.id)}"`` carrying ``p`` = P(LOWER-id team wins the SERIES).
    CRITICAL ORIENTATION: a priced matchup is looked up by the id-bucket (NOT an arg-order tuple)
    and oriented to the FIRST arg via ``p_a = p if a.id < b.id else (1 - p)`` — the bracket can hand
    ``_play_match`` either seed order (QF1 is seed 1 vs seed 8, so the first arg is the LOWER id, but
    SF/GF feeders arrive in winner order), so assuming arg order matches id order would silently
    invert the favorite. The override prices the SERIES directly: the best-of closed form is NOT
    re-applied (PROB-02 — the market already prices the Bo3/Bo5), exactly like the Swiss seam.
    """
    key = frozenset((a.id, b.id))
    if key in locked:
        winner_id = locked[key]
        if winner_id == a.id:
            return a
        if winner_id == b.id:
            return b
        raise ValueError(
            f"locked winner {winner_id!r} for {key} is not one of the paired teams "
            f"({a.id}, {b.id})"
        )
    market_p_a = None
    if market_overrides:
        bucket = f"{min(a.id, b.id)}-{max(a.id, b.id)}"
        p = market_overrides.get(bucket)
        if p is not None:
            # `p` = P(lower-id wins the SERIES); orient to the FIRST arg `a` (which may be the
            # higher id — SF/GF feeders arrive in winner order, not id order).
            market_p_a = p if a.id < b.id else (1.0 - p)
    if market_p_a is not None:
        p_a = market_p_a  # market prices the series DIRECTLY; do NOT re-apply best-of (PROB-02)
    else:
        ra = ratings.get(a.id, a.rating) if ratings else a.rating
        rb = ratings.get(b.id, b.rating) if ratings else b.rating
        p_a = series_best_of(p_map(ra, rb, S=S), n_maps)  # P(a wins the series), single draw
    return a if rng.random() < p_a else b


def simulate_bracket(
    teams: list[Team],
    ratings: dict[int, float] | None,
    S: float,
    rng,
    locked: dict | None = None,
    *,
    bo: dict[str, int] | None = None,
    market_overrides: dict | None = None,
) -> dict[str, int]:
    """Simulate one full 8-team single-elim bracket -> ``{match_label: winner_id}``.

    ``teams`` is the seed-ordered 8-team list (each ``.seed`` in 1..8). The bracket tree is
    derived from ``QF_SEEDS`` / ``SF_FEEDERS`` / ``GF_FEEDERS`` (no second matchup table). Returns
    the winner id of every match (``QF1..QF4``, ``SF1``, ``SF2``, ``GF``); ``winners["GF"]`` is the
    champion. ``locked`` deterministically fixes any already-played matchup (the live seam).

    ``market_overrides`` (keyword-only, the playoff odds seam — default None = unchanged): the
    id-bucket-keyed ``{"lo-hi": P(lower-id wins the series)}`` dict ``_play_match`` consumes. A
    matchup present here is priced DIRECTLY from the market (best-of NOT re-applied, PROB-02), so
    market-calibrated QF/SF lines override the champion-fit ratings for the rounds the market prices
    while ratings still drive the unpriced later rounds — the same orthogonality the Swiss
    qualify-fit relies on. Mirrors ``engine.swiss.simulate_stage``'s seam.

    Unlike the Swiss sim, the bracket does NOT mutate team objects (no wins/losses/opps), so it
    needs no fresh per-sim Team set — ``_play_match`` only reads ``.rating``.
    """
    bo = bo or DEFAULT_BO
    locked = locked or {}
    by_seed = {t.seed: t for t in teams}
    if set(by_seed) != set(range(1, 9)):
        raise ValueError(f"playoff bracket needs exactly seeds 1..8, got {sorted(by_seed)}")

    win_obj: dict[str, Team] = {}
    for label, (sa, sb) in QF_SEEDS.items():
        win_obj[label] = _play_match(
            by_seed[sa], by_seed[sb], ratings, S, rng, locked, _n_maps(label, bo),
            market_overrides=market_overrides,
        )
    for label, (f1, f2) in SF_FEEDERS.items():
        win_obj[label] = _play_match(
            win_obj[f1], win_obj[f2], ratings, S, rng, locked, _n_maps(label, bo),
            market_overrides=market_overrides,
        )
    win_obj["GF"] = _play_match(
        win_obj[GF_FEEDERS[0]], win_obj[GF_FEEDERS[1]], ratings, S, rng, locked, _n_maps("GF", bo),
        market_overrides=market_overrides,
    )
    return {label: t.id for label, t in win_obj.items()}


@dataclass
class PlayoffResult:
    """Final playoff-MC aggregate — per-team reach/champion tallies + the retained sample.

    ``counts_sf`` = reached the semifinals (won the quarterfinal); ``counts_gf`` = reached the
    grand final (won the semifinal); ``counts_champ`` = won the title. ``sample`` is the full
    per-sim ``{match_label: winner_id}`` list the 7-pick optimizer scores against (it never
    re-runs the bracket MC). Wilson ``band_*`` intervals mirror ``montecarlo.Result``.
    """

    n: int
    ids: tuple[int, ...]
    counts_sf: dict[int, int]
    counts_gf: dict[int, int]
    counts_champ: dict[int, int]
    sample: list[dict[str, int]]
    band_sf: dict[int, tuple[float, float]] = field(default_factory=dict)
    band_gf: dict[int, tuple[float, float]] = field(default_factory=dict)
    band_champ: dict[int, tuple[float, float]] = field(default_factory=dict)

    def p_sf(self) -> dict[int, float]:
        return {i: c / self.n for i, c in self.counts_sf.items()} if self.n else {}

    def p_gf(self) -> dict[int, float]:
        return {i: c / self.n for i, c in self.counts_gf.items()} if self.n else {}

    def p_champ(self) -> dict[int, float]:
        return {i: c / self.n for i, c in self.counts_champ.items()} if self.n else {}


def _chunk_sizes(n: int, n_chunks: int) -> list[int]:
    """Split N across a PINNED chunk count deterministically (mirrors montecarlo._chunk_sizes)."""
    base, rem = divmod(n, n_chunks)
    return [base + (1 if i < rem else 0) for i in range(n_chunks)]


def run_playoff_mc_progressive(
    teams: list[Team],
    ratings: dict[int, float] | None,
    S: float,
    N: int,
    locked: dict | None = None,
    *,
    seed: int,
    n_chunks: int = DEFAULT_N_CHUNKS,
    bo: dict[str, int] | None = None,
    market_overrides: dict | None = None,
) -> Iterator[Partial]:
    """Run N bracket sims generator-first; yield a ``Partial`` per chunk, return ``PlayoffResult``.

    Same RNG discipline as ``montecarlo.run_mc_progressive`` (``SeedSequence(seed).spawn(n_chunks)``
    over a PINNED chunk count), so (seed, N) reproduces. The yielded ``Partial.running_p_adv`` carries
    the running P(reach grand final) so the app's progress bar can show a live tally; the returned
    ``PlayoffResult`` holds the marginals, the per-sim sample, and the Wilson bands.

    ``market_overrides`` (keyword-only, the playoff odds seam — default None = unchanged): forwarded
    to ``simulate_bracket`` so market-priced QF/SF lines override the champion-fit ratings for the
    rounds the market prices (PROB-02). None reproduces the rating-only path byte-identically.
    """
    if N <= 0:
        raise ValueError(f"N must be a positive integer, got {N!r}")
    if n_chunks <= 0:
        raise ValueError(f"n_chunks must be a positive integer, got {n_chunks!r}")

    ids = [t.id for t in teams]
    counts_sf = {i: 0 for i in ids}
    counts_gf = {i: 0 for i in ids}
    counts_champ = {i: 0 for i in ids}
    sample: list[dict[str, int]] = []

    sizes = _chunk_sizes(N, n_chunks)
    child_seeds = np.random.SeedSequence(seed).spawn(n_chunks)
    done = 0
    for chunk_idx, chunk_n in enumerate(sizes):
        if chunk_n == 0:
            continue
        rng = np.random.default_rng(child_seeds[chunk_idx])
        for _ in range(chunk_n):
            winners = simulate_bracket(
                teams, ratings, S, rng, locked, bo=bo, market_overrides=market_overrides
            )
            for label in QF_LABELS:
                counts_sf[winners[label]] += 1
            for label in SF_LABELS:
                counts_gf[winners[label]] += 1
            counts_champ[winners["GF"]] += 1
            sample.append(winners)
            done += 1
        running = {i: counts_gf[i] / max(1, done) for i in ids}
        yield Partial(done=done, total=N, running_p_adv=running)

    band_sf = {i: wilson(counts_sf[i], N) for i in ids}
    band_gf = {i: wilson(counts_gf[i], N) for i in ids}
    band_champ = {i: wilson(counts_champ[i], N) for i in ids}
    return PlayoffResult(
        n=len(sample),
        ids=tuple(ids),
        counts_sf=counts_sf,
        counts_gf=counts_gf,
        counts_champ=counts_champ,
        sample=sample,
        band_sf=band_sf,
        band_gf=band_gf,
        band_champ=band_champ,
    )


def run_playoff_mc(
    teams: list[Team],
    ratings: dict[int, float] | None,
    S: float,
    N: int = DEFAULT_N,
    locked: dict | None = None,
    *,
    seed: int,
    n_chunks: int = DEFAULT_N_CHUNKS,
    bo: dict[str, int] | None = None,
    market_overrides: dict | None = None,
) -> PlayoffResult:
    """Drain ``run_playoff_mc_progressive`` and return the final ``PlayoffResult`` (cache-wrapper seam).

    ``market_overrides`` (the playoff odds seam — default None = unchanged) is forwarded so
    market-priced QF/SF lines override the champion-fit ratings for the rounds the market prices
    (PROB-02); None is the byte-identical rating-only path.
    """
    gen = run_playoff_mc_progressive(
        teams, ratings, S, N, locked, seed=seed, n_chunks=n_chunks, bo=bo,
        market_overrides=market_overrides,
    )
    result: PlayoffResult | None = None
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        result = stop.value
    if result is None:
        raise RuntimeError(
            "run_playoff_mc_progressive exhausted without returning a PlayoffResult — "
            "this is an internal engine bug"
        )
    return result
