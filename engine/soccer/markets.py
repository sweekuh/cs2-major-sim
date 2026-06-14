"""Market-pricing layer (Phase 1): model probabilities for each Kalshi market type.

Pure functions over a ``TournamentResult.sample`` (the retained joint distribution) — so every
market is priced off ONE Monte-Carlo run, and correlated markets stay mutually consistent. These
feed the monitor's net-edge comparison against live Kalshi prices.

Stage codes (from ``engine.soccer.knockout``): 0 group / 1 R32 / 2 R16 / 3 QF / 4 SF / 5 final /
6 champion. "Advance" = reach the knockout (stage >= 1).
"""

from __future__ import annotations

from collections import Counter

from engine.soccer.tournament import TournamentResult

ADVANCE_STAGE = 1


def _n(result: TournamentResult) -> int:
    return result.n


def p_champion(result: TournamentResult) -> dict[int, float]:
    """P(win the tournament) per team."""
    c = Counter(s["champion"] for s in result.sample)
    return {tid: c.get(tid, 0) / result.n for tid in result.teams}


def p_reach_stage(result: TournamentResult, stage: int) -> dict[int, float]:
    """P(reach at least ``stage``) per team (e.g. stage=3 -> reach the quarter-final)."""
    out = {tid: 0 for tid in result.teams}
    for s in result.sample:
        for tid, reached in s["stage_reached"].items():
            if reached >= stage:
                out[tid] += 1
    return {tid: c / result.n for tid, c in out.items()}


def p_advance(result: TournamentResult) -> dict[int, float]:
    """P(advance out of the group / reach the knockout) per team."""
    return p_reach_stage(result, ADVANCE_STAGE)


def p_group_winner(result: TournamentResult) -> dict[int, float]:
    """P(finish 1st in the group) per team."""
    out = {tid: 0 for tid in result.teams}
    for s in result.sample:
        for tid, rank in s["group_rank"].items():
            if rank == 1:
                out[tid] += 1
    return {tid: c / result.n for tid, c in out.items()}


def p_exact_group_order(result: TournamentResult, group: str) -> dict[tuple, float]:
    """Distribution over exact finishing orders for one group (the thin/exotic market)."""
    c = Counter(s["group_order"][group] for s in result.sample)
    return {order: cnt / result.n for order, cnt in c.most_common()}


def p_furthest_stage(result: TournamentResult, team_id: int) -> dict[int, float]:
    """Distribution over the deepest stage one team reaches (stage-of-elimination market)."""
    c = Counter(s["stage_reached"][team_id] for s in result.sample if team_id in s["stage_reached"])
    return {stage: cnt / result.n for stage, cnt in sorted(c.items())}
