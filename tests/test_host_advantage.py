"""Host-advantage guards (Phase 1 iteration).

Pins the fixture orientation for host games and that host advantage measurably lifts a host's
advancement odds, while staying backward-compatible (no hosts = unchanged).
"""

from __future__ import annotations

import pytest

from engine.soccer.dixon_coles import strengths_from_elo
from engine.soccer.group_stage import orient_for_host
from engine.soccer.markets import p_advance
from engine.soccer.teams import groups as group_by_letter
from engine.soccer.teams import host_ids, load_teams
from engine.soccer.tournament import run_tournament

TEAMS, _ = load_teams()
GROUPS = {g: [t.id for t in members] for g, members in group_by_letter(TEAMS).items()}


def test_orient_puts_host_at_home():
    hosts = {7}
    assert orient_for_host(7, 9, hosts) == (7, 9, False)   # host already home
    assert orient_for_host(9, 7, hosts) == (7, 9, False)   # host moved to home, swapped
    assert orient_for_host(9, 11, hosts) == (9, 11, True)  # no host -> neutral
    assert orient_for_host(7, 8, {7, 8}) == (7, 8, True)   # both hosts -> neutral


def test_host_ids_resolves_the_three_hosts():
    hosts = host_ids(TEAMS)
    names = {t.name for t in TEAMS if t.id in hosts}
    assert names == {"Mexico", "USA", "Canada"}


def test_host_advantage_lifts_advancement():
    hosts = host_ids(TEAMS)
    model = strengths_from_elo(TEAMS, home_adv=0.7)  # strong advantage to make the effect clear
    base = p_advance(run_tournament(GROUPS, model, 500, seed=3, hosts=frozenset()))
    with_host = p_advance(run_tournament(GROUPS, model, 500, seed=3, hosts=hosts))
    # Every host should be at least as likely to advance with home advantage; on average, more.
    lift = [with_host[h] - base[h] for h in hosts]
    assert sum(lift) > 0.0
    assert all(with_host[h] >= base[h] - 0.02 for h in hosts)  # no host hurt by its own advantage


def test_no_hosts_is_unchanged():
    model = strengths_from_elo(TEAMS, home_adv=0.7)
    a = p_advance(run_tournament(GROUPS, model, 120, seed=9, hosts=frozenset()))
    b = p_advance(run_tournament(GROUPS, model, 120, seed=9))  # default hosts = empty
    assert a == b
