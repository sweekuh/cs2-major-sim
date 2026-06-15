"""Tournament Monte-Carlo + market-pricing guards (Phase 1).

Pins the structural invariants of a 48-team / 12-group / 32-knockout run and that the market
layer prices coherently off the retained sample.
"""

from __future__ import annotations

import numpy as np
import pytest

from engine.soccer.dixon_coles import strengths_from_elo
from engine.soccer.markets import (
    p_advance,
    p_champion,
    p_eliminated_in_group,
    p_exact_group_order,
    p_group_position,
    p_group_winner,
    p_reach_stage,
    top_n,
)
from engine.soccer.teams import groups as group_by_letter
from engine.soccer.teams import load_teams
from engine.soccer.tournament import run_tournament

TEAMS, _ = load_teams()
GROUPS = {g: [t.id for t in members] for g, members in group_by_letter(TEAMS).items()}
MODEL = strengths_from_elo(TEAMS)


def _run(n=200, seed=7):
    return run_tournament(GROUPS, MODEL, n, seed=seed)


def test_sample_retained_and_sized():
    r = _run()
    assert r.n == 200
    assert len(r.sample) == 200
    assert len(r.teams) == 48


def test_exactly_one_group_winner_and_twelve_total():
    r = _run()
    gw = p_group_winner(r)
    assert sum(gw.values()) == pytest.approx(12.0)  # one winner per group, 12 groups


def test_exactly_32_advance_per_tournament():
    r = _run()
    assert sum(p_advance(r).values()) == pytest.approx(32.0)


def test_champion_distribution_sums_to_one():
    r = _run()
    pc = p_champion(r)
    assert sum(pc.values()) == pytest.approx(1.0)
    assert all(0.0 <= v <= 1.0 for v in pc.values())


def test_reach_stage_monotone():
    r = _run()
    adv = p_advance(r)               # stage >= 1
    qf = p_reach_stage(r, 3)         # stage >= 3
    # Reaching a later stage is never more likely than an earlier one.
    assert all(qf[t] <= adv[t] + 1e-12 for t in r.teams)


def test_exact_group_order_is_a_distribution():
    r = _run()
    dist = p_exact_group_order(r, "A")
    assert sum(dist.values()) == pytest.approx(1.0)
    assert all(len(order) == 4 for order in dist)


def test_group_position_distribution():
    r = _run()
    pos = p_group_position(r)
    # Each team's four position probabilities sum to 1.
    for tid in r.teams:
        assert sum(pos[tid].values()) == pytest.approx(1.0)
    # Exactly one team finishes 1st per group -> 12 firsts across the field.
    assert sum(pos[tid][1] for tid in r.teams) == pytest.approx(12.0)


def test_eliminated_in_group_complements_advance():
    r = _run()
    elim = p_eliminated_in_group(r)
    adv = p_advance(r)
    for tid in r.teams:
        assert elim[tid] + adv[tid] == pytest.approx(1.0)


def test_top_n_sorted_descending():
    out = top_n({1: 0.1, 2: 0.5, 3: 0.3, 4: 0.05}, 2)
    assert out == [(2, 0.5), (3, 0.3)]
    assert top_n({1: 0.1, 2: 0.5}, 0) == []
    assert top_n({1: 0.1, 2: 0.5}, -1) == []  # negative n -> empty, not a dropped element


def test_determinism_same_seed_same_result():
    a = p_champion(_run(seed=42))
    b = p_champion(_run(seed=42))
    assert a == b


def test_knockout_requires_power_of_two():
    import numpy as np

    from engine.soccer.knockout import simulate_knockout
    with pytest.raises(ValueError):
        simulate_knockout([1, 2, 3, 4, 5, 6], MODEL, np.random.default_rng(0))


def test_stronger_field_more_likely_to_win():
    # The strongest team by Elo should have a higher title chance than the weakest.
    r = _run(n=400, seed=1)
    pc = p_champion(r)
    strongest = max(TEAMS, key=lambda t: t.elo).id
    weakest = min(TEAMS, key=lambda t: t.elo).id
    assert pc[strongest] > pc[weakest]
