"""Full-tournament Monte Carlo (Phase 1) — the joint distribution every market is priced from.

Reuses the CS2 runner's principle (deterministic per-sim RNG via ``SeedSequence(seed).spawn`` +
a RETAINED per-sim sample), but with a soccer-shaped record. One run yields a joint distribution
over whole tournaments, so ``engine.soccer.markets`` can price ANY derived/correlated market
(champion, group order, furthest stage, ...) off the single ``sample`` without re-simulating.

Each sim: play all 12 groups (scoreline-level, FIFA tiebreakers) -> 12 winners + 12 runners-up +
the 8 best third-placed = 32 qualifiers, seeded by strength -> single-elim knockout.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.soccer.dixon_coles import MatchModel
from engine.soccer.group_stage import GroupRow, simulate_group
from engine.soccer.knockout import simulate_knockout


@dataclass
class TournamentResult:
    """The retained Monte-Carlo sample. ``sample[i]`` is one simulated tournament:

    - ``champion``: team id
    - ``group_rank``: {team_id: 1..4 within its group}
    - ``stage_reached``: {team_id: 0 (didn't qualify) .. 6 (champion)} (see knockout stage codes)
    - ``group_order``: {group_letter: (ranked team ids,)}
    """

    n: int
    teams: list[int]
    sample: list[dict]


def _third_key(row: GroupRow) -> tuple[int, int, int]:
    return (row.points, row.gd, row.gf)


def _seed_qualifiers(winners, runners, thirds, standings) -> list[int]:
    """Order the 32 qualifiers best-first: winners, then runners-up, then best thirds; within each
    tier by overall (points, GD, GF). Strength seeding (a documented simplification of the real
    fixed-slot bracket)."""
    def by_strength(ids):
        return sorted(ids, key=lambda t: _third_key(standings[t]), reverse=True)
    return by_strength(winners) + by_strength(runners) + by_strength(thirds)


def simulate_one(groups: dict[str, list[int]], model: MatchModel,
                 rng: np.random.Generator, *, neutral: bool = True, hosts=frozenset()) -> dict:
    """Simulate a single full tournament and return its sample record.

    ``hosts`` (optional) get home advantage in their GROUP matches; the knockout is modelled as
    neutral (later-round venues aren't fixed by team — a documented simplification).
    """
    group_order: dict[str, tuple] = {}
    group_rank: dict[int, int] = {}
    standings: dict[int, GroupRow] = {}
    winners: list[int] = []
    runners: list[int] = []
    thirds: list[int] = []
    for g, ids in groups.items():
        order, st, _ = simulate_group(ids, model, rng, neutral=neutral, hosts=hosts)
        group_order[g] = tuple(order)
        for rank, tid in enumerate(order, start=1):
            group_rank[tid] = rank
        standings.update(st)
        winners.append(order[0])
        runners.append(order[1])
        thirds.append(order[2])

    best_thirds = sorted(thirds, key=lambda t: _third_key(standings[t]), reverse=True)[:8]
    seeded = _seed_qualifiers(winners, runners, best_thirds, standings)
    stage, champion = simulate_knockout(seeded, model, rng)

    stage_reached = {tid: stage.get(tid, 0) for tid in group_rank}
    return {
        "champion": champion,
        "group_rank": group_rank,
        "stage_reached": stage_reached,
        "group_order": group_order,
    }


def run_tournament(groups: dict[str, list[int]], model: MatchModel, n_sims: int,
                   *, seed: int, neutral: bool = True, hosts=frozenset()) -> TournamentResult:
    """Run ``n_sims`` full tournaments with deterministic per-sim RNG; retain every sample.

    Determinism depends only on ``seed`` (and ``n_sims``): each sim draws from its own child
    Generator, so results are reproducible across runs and machines. ``hosts`` (optional) get
    home advantage in their group matches.
    """
    if n_sims <= 0:
        raise ValueError(f"n_sims must be positive, got {n_sims!r}")
    child_seeds = np.random.SeedSequence(seed).spawn(n_sims)
    team_ids = [tid for ids in groups.values() for tid in ids]
    sample = [simulate_one(groups, model, np.random.default_rng(cs), neutral=neutral, hosts=hosts)
              for cs in child_seeds]
    return TournamentResult(n=n_sims, teams=team_ids, sample=sample)
