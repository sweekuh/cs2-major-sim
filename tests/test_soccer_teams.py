"""SoccerTeam loader guards: the WC fixture loads, validates, and buckets into groups.

The shipped data/wc2026_teams.json is a DRAFT (placeholder draw/priors), but its STRUCTURE must
be valid: 48 teams, 12 groups of 4, unique ids. Validation must reject malformed fixtures loudly.
"""

from __future__ import annotations

import json

import pytest

from engine.soccer.teams import GROUP_SIZE, N_GROUPS, N_TEAMS, groups, load_teams


def test_shipped_fixture_is_structurally_valid():
    teams, meta = load_teams()
    assert len(teams) == N_TEAMS == 48
    assert len({t.id for t in teams}) == 48  # unique ids
    g = groups(teams)
    assert len(g) == N_GROUPS == 12
    assert all(len(members) == GROUP_SIZE for members in g.values())


def test_loader_rejects_duplicate_ids(tmp_path):
    p = tmp_path / "dup.json"
    p.write_text(json.dumps({"teams": [
        {"id": 1, "name": "A", "group": "A", "elo": 1500},
        {"id": 1, "name": "B", "group": "A", "elo": 1500},
    ]}))
    with pytest.raises(ValueError):
        load_teams(p)


def test_loader_rejects_empty_name(tmp_path):
    p = tmp_path / "empty.json"
    p.write_text(json.dumps({"teams": [{"id": 1, "name": "  ", "group": "A", "elo": 1500}]}))
    with pytest.raises(ValueError):
        load_teams(p)


def test_attack_defence_default_to_neutral(tmp_path):
    p = tmp_path / "min.json"
    p.write_text(json.dumps({"teams": [{"id": 7, "name": "Test", "group": "C", "elo": 1700}]}))
    teams, _ = load_teams(p)
    assert teams[0].attack == 0.0 and teams[0].defence == 0.0
    assert teams[0].group == "C" and teams[0].elo == 1700.0
