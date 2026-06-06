"""STG-01: engine.teams.load_stage(path) sibling + the freeze-regression companion.

load_stage is a NEW SIBLING of the byte-frozen GATE-01 path (load_teams /
_DEFAULT_FIXTURE / _validate_fixture). It reads any per-stage fixture, validates it
against THAT fixture's declared ``stage.size`` (via the sibling _validate_fixture_for_size),
and returns ``(teams, cfg)``. It never calls — and must never perturb — the frozen path.

test_load_teams_unchanged is the FREEZE REGRESSION: after importing the new siblings,
``load_teams()`` must still return the byte-identical 16-team Stage-1 list. GATE-01
(tests/test_backtest_budapest_2025.py) is the companion proof that the pairing path is intact.
"""

from __future__ import annotations

import json

import pytest

from engine.teams import _DEFAULT_FIXTURE, Team, load_stage, load_teams

STAGE1_PATH = "data/stage1.json"


def _write(path, payload) -> str:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _fixture(size: int, teams: list[dict], *, seeds_confirmed: bool = False) -> dict:
    return {
        "stage": {"size": size, "advance_at_wins": 3, "eliminate_at_losses": 3},
        "seeds_confirmed": seeds_confirmed,
        "teams": teams,
    }


def _seeds(n: int, *, ratings: dict | None = None) -> list[dict]:
    ratings = ratings or {}
    return [
        {"seed": s, "name": f"Team {s}", "rating": ratings.get(s, 50.0)}
        for s in range(1, n + 1)
    ]


def test_load_stage_returns_teams_and_cfg():
    """load_stage('data/stage1.json') returns a 16-team seed-ordered list identical in
    id/name/seed/rating to load_teams(), plus cfg with size==16 and seeds_confirmed True."""
    teams, cfg = load_stage(STAGE1_PATH)
    ref = load_teams()

    assert isinstance(teams, list)
    assert len(teams) == 16
    assert all(isinstance(t, Team) for t in teams)
    # Seed-ordered and field-identical to the frozen load_teams() output.
    for t, r in zip(teams, ref):
        assert (t.id, t.name, t.seed, t.rating) == (r.id, r.name, r.seed, r.rating)

    assert cfg["size"] == 16
    assert cfg["seeds_confirmed"] is True


def test_load_stage_validates_against_declared_size(tmp_path):
    """A size-8 fixture with 8 valid seeds loads OK; a size-16 fixture with only 15 teams
    raises ValueError mentioning the size; a duplicate seed raises ValueError ('duplicate seed')."""
    # 8-team fixture validates against its OWN declared size (8), not STAGE_SIZE==16.
    ok8 = _write(tmp_path / "stage8.json", _fixture(8, _seeds(8)))
    teams8, cfg8 = load_stage(ok8)
    assert len(teams8) == 8
    assert cfg8["size"] == 8

    # 16-size fixture with only 15 teams -> ValueError mentioning the size.
    short = _write(tmp_path / "short.json", _fixture(16, _seeds(15)))
    with pytest.raises(ValueError, match="16"):
        load_stage(short)

    # Duplicate seed -> ValueError mentioning "duplicate seed" (the dup-seed guard).
    dup_rows = _seeds(16)
    dup_rows[1]["seed"] = 1  # two entries with seed 1
    dup = _write(tmp_path / "dup.json", _fixture(16, dup_rows))
    with pytest.raises(ValueError, match="duplicate seed"):
        load_stage(dup)


def test_load_stage_bad_rating_raises(tmp_path):
    """A non-numeric or out-of-range rating raises ValueError (mirrors _validate_fixture's loud fail)."""
    nonnum_rows = _seeds(16)
    nonnum_rows[0]["rating"] = "not-a-number"
    nonnum = _write(tmp_path / "nonnum.json", _fixture(16, nonnum_rows))
    with pytest.raises(ValueError):
        load_stage(nonnum)

    oor_rows = _seeds(16)
    oor_rows[0]["rating"] = 100000  # out of the 0<r<1000 range
    oor = _write(tmp_path / "oor.json", _fixture(16, oor_rows))
    with pytest.raises(ValueError):
        load_stage(oor)


def test_load_stage_malformed_fixture_raises_valueerror(tmp_path):
    """LO-03 (06-REVIEW): a malformed fixture raises a clean ``ValueError`` (the SAME error
    contract as the frozen ``load_teams``), never a bare ``KeyError``/``TypeError``. Mirrors
    load_teams's friendly ``raw.get('teams')`` + per-field presence guards so the twin loaders
    fail identically.

    Three malformed shapes: (a) NO ``teams`` key, (b) a non-list ``teams``, (c) a team entry
    missing a required field (``rating``). Each must raise ValueError, not a raw subscript error.
    """
    # (a) Missing the 'teams' key entirely (the old `raw["teams"]` raised a bare KeyError).
    no_teams = _write(tmp_path / "no_teams.json", {"stage": {"size": 16}})
    with pytest.raises(ValueError):
        load_stage(no_teams)

    # (b) 'teams' present but not a list -> ValueError (not a TypeError from iterating a dict).
    bad_teams = _write(
        tmp_path / "bad_teams.json", {"stage": {"size": 16}, "teams": {"not": "a list"}}
    )
    with pytest.raises(ValueError):
        load_stage(bad_teams)

    # (c) A team entry missing the required 'rating' field (the old `entry["rating"]` raised
    # a bare KeyError) -> ValueError naming the missing field, like load_teams.
    missing_field_rows = _seeds(16)
    del missing_field_rows[0]["rating"]
    missing_field = _write(
        tmp_path / "missing_field.json", _fixture(16, missing_field_rows)
    )
    with pytest.raises(ValueError, match="rating"):
        load_stage(missing_field)


def test_load_teams_unchanged():
    """FREEZE REGRESSION: after importing the new siblings, load_teams() still returns the
    byte-identical 16-team Stage-1 list — proving the frozen GATE-01 path was not perturbed.

    Asserts each (id, name, seed, rating) tuple against the known _DEFAULT_FIXTURE values
    (which data/stage1.json round-trips)."""
    teams = load_teams()
    assert len(teams) == 16
    expected = [
        (seed, name, seed, float(rating))
        for seed, (name, rating) in sorted(_DEFAULT_FIXTURE.items())
    ]
    actual = [(t.id, t.name, t.seed, t.rating) for t in teams]
    assert actual == expected
