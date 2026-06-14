"""Group round-robin simulation + FIFA tiebreakers (Phase 1).

A World Cup group is 4 teams, each pair playing once (6 matches). We sample a SCORELINE per match
(not just W/D/L) because the official ordering is decided by goal difference and goals scored — a
win-probability model literally cannot rank a group. Ranking follows the FIFA 2026 sequence:

  1. points (3/1/0) over all group matches
  2. goal difference over all group matches
  3. goals scored over all group matches
  -- for teams STILL level on the above, a mini-table among only those teams:
  4. head-to-head points, 5. head-to-head goal difference, 6. head-to-head goals scored
  -- then fair-play points (not modellable here, treated equal) and finally drawing of lots (rng).

Pure: depends only on the model + injected rng.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.soccer.dixon_coles import MatchModel, expected_goals, sample_score


@dataclass(frozen=True)
class GroupRow:
    """A team's accumulated group record."""

    team_id: int
    played: int
    points: int
    gf: int
    ga: int

    @property
    def gd(self) -> int:
        return self.gf - self.ga


def _round_robin_pairs(team_ids: list[int]) -> list[tuple[int, int]]:
    """All unordered pairs in a group (6 for a group of 4), first listed team as nominal home."""
    return [(team_ids[i], team_ids[j])
            for i in range(len(team_ids)) for j in range(i + 1, len(team_ids))]


def play_group(team_ids: list[int], model: MatchModel, rng: np.random.Generator,
               *, neutral: bool = True) -> list[tuple[int, int, int, int]]:
    """Simulate every group match -> list of (home_id, away_id, home_goals, away_goals)."""
    results = []
    for home, away in _round_robin_pairs(team_ids):
        lam_h, lam_a = expected_goals(model, home, away, neutral=neutral)
        hg, ag = sample_score(lam_h, lam_a, rng, rho=model.rho)
        results.append((home, away, hg, ag))
    return results


def _standings(team_ids, results) -> dict[int, GroupRow]:
    """Aggregate match results into per-team GroupRows (points/gf/ga over the given matches)."""
    pts = {t: 0 for t in team_ids}
    gf = {t: 0 for t in team_ids}
    ga = {t: 0 for t in team_ids}
    played = {t: 0 for t in team_ids}
    for home, away, hg, ag in results:
        if home not in pts or away not in pts:
            continue
        gf[home] += hg; ga[home] += ag; played[home] += 1
        gf[away] += ag; ga[away] += hg; played[away] += 1
        if hg > ag:
            pts[home] += 3
        elif ag > hg:
            pts[away] += 3
        else:
            pts[home] += 1; pts[away] += 1
    return {t: GroupRow(t, played[t], pts[t], gf[t], ga[t]) for t in team_ids}


def _key(row: GroupRow) -> tuple[int, int, int]:
    """Primary FIFA sort key: (points, goal difference, goals for), all descending."""
    return (row.points, row.gd, row.gf)


def rank_group(team_ids: list[int], results: list[tuple[int, int, int, int]],
               rng: np.random.Generator) -> list[int]:
    """Order a group 1st..last by the FIFA 2026 tiebreaker chain. Returns team ids best-first."""
    st = _standings(team_ids, results)
    ordered = sorted(team_ids, key=lambda t: _key(st[t]), reverse=True)

    # Resolve blocks still level on (points, GD, GF) via the head-to-head mini-table, then lots.
    final: list[int] = []
    i = 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and _key(st[ordered[j]]) == _key(st[ordered[i]]):
            j += 1
        block = ordered[i:j]
        final.extend(block if len(block) == 1 else _break_tie(block, results, rng))
        i = j
    return final


def _break_tie(block: list[int], results, rng: np.random.Generator) -> list[int]:
    """Order a tied block by head-to-head mini-table, then random drawing of lots."""
    h2h = _standings(block, [r for r in results if r[0] in block and r[1] in block])
    ordered = sorted(block, key=lambda t: _key(h2h[t]), reverse=True)
    # Anything still identical on the h2h key goes to lots (deterministic given the rng).
    out: list[int] = []
    i = 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and _key(h2h[ordered[j]]) == _key(h2h[ordered[i]]):
            j += 1
        tied = ordered[i:j]
        if len(tied) > 1:
            tied = [tied[k] for k in rng.permutation(len(tied))]
        out.extend(tied)
        i = j
    return out


def simulate_group(team_ids: list[int], model: MatchModel, rng: np.random.Generator,
                   *, neutral: bool = True):
    """Play and rank one group. Returns (ranked_ids, standings_by_id, results)."""
    results = play_group(team_ids, model, rng, neutral=neutral)
    order = rank_group(team_ids, results, rng)
    return order, _standings(team_ids, results), results
