"""Playoff bracket-seed derivation tests (PLAY-03) — seed_playoffs from a locked Stage-3 finish.

Mirrors tests/test_stage3_seeding.py's deterministic-chain discipline: it proves the STRUCTURE
(8 advancers -> bracket seeds 1..8 by losses asc, Buchholz desc, prior seed asc) and that the
derive reproduces the committed, official-bracket-confirmed data/playoffs.json seeding from a
synthetic Stage-3 finish whose within-record order matches the real one.
"""

from __future__ import annotations

import pytest

from engine.seeding import seed_playoffs
from engine.teams import Team, load_stage


def _finish(records: dict[int, tuple[int, int]], buchholz: dict[int, int]) -> dict[int, Team]:
    """Build a {id: Team} finish where difficulty(t) returns the given Buchholz per team.

    difficulty(t) = sum(o.wins - o.losses for o in t.opps); we fake it by giving each team a
    single dummy opponent whose (wins-losses) equals the desired Buchholz value.
    """
    teams: dict[int, Team] = {}
    for tid, (w, ell) in records.items():
        t = Team(id=tid, name=f"S3-{tid}", seed=tid, rating=50.0, wins=w, losses=ell)
        opp = Team(id=1000 + tid, name="opp", seed=0, rating=50.0, wins=buchholz[tid], losses=0)
        t.opps.add(opp)
        teams[tid] = t
    return teams


def test_seed_playoffs_orders_by_losses_then_buchholz_then_seed():
    # 8 advancers: two 3-0, three 3-1, three 3-2 (the Cologne shape).
    records = {
        10: (3, 0), 20: (3, 0),               # 3-0
        30: (3, 1), 40: (3, 1), 50: (3, 1),   # 3-1
        60: (3, 2), 70: (3, 2), 80: (3, 2),   # 3-2
    }
    # Within each loss bucket, higher Buchholz seeds higher.
    buchholz = {10: 5, 20: 3, 30: 6, 40: 4, 50: 2, 60: 7, 70: 5, 80: 1}
    seeds = seed_playoffs(_finish(records, buchholz))
    assert [t.seed for t in seeds] == list(range(1, 9))
    # Output Team.id/.seed are the NEW bracket position (1..8); the original team rides in .name.
    assert [t.id for t in seeds] == list(range(1, 9))
    # 3-0 first (by Buchholz), then 3-1, then 3-2 — identified by carried-forward name.
    assert [t.name for t in seeds] == [f"S3-{i}" for i in (10, 20, 30, 40, 50, 60, 70, 80)]
    assert seeds[0].name == "S3-10" and seeds[0].seed == 1


def test_seed_playoffs_buchholz_tiebreak_within_bucket():
    records = {i: (3, 1) for i in (10, 20, 30)}
    records.update({i: (3, 0) for i in (40, 50)})
    records.update({i: (3, 2) for i in (60, 70, 80)})
    buchholz = {40: 1, 50: 9, 10: 2, 20: 8, 30: 5, 60: 0, 70: 0, 80: 0}
    seeds = seed_playoffs(_finish(records, buchholz))
    # 3-0 bucket: 50 (Buchholz 9) outseeds 40 (Buchholz 1).
    assert [t.name for t in seeds[:2]] == ["S3-50", "S3-40"]
    # 3-1 bucket: 20 (8) > 30 (5) > 10 (2).
    assert [t.name for t in seeds[2:5]] == ["S3-20", "S3-30", "S3-10"]


def test_seed_playoffs_rejects_non_eight_advancers():
    records = {i: (3, 0) for i in range(1, 8)}  # only 7 advancers
    buchholz = {i: 0 for i in range(1, 8)}
    with pytest.raises(ValueError):
        seed_playoffs(_finish(records, buchholz))


def test_committed_playoffs_fixture_is_the_confirmed_bracket():
    # The shipped data/playoffs.json must encode the official Cologne 2026 bracket seeding
    # (verified vs the posted bracket 2026-06-16). This is the revert-proof guard on the real data.
    teams, cfg = load_stage("data/playoffs.json")
    assert cfg["size"] == 8 and cfg["seeds_confirmed"] is True
    assert (cfg["qf_bo"], cfg["sf_bo"], cfg["gf_bo"]) == (3, 3, 5)
    by_seed = {t.seed: t.name for t in teams}
    assert by_seed == {
        1: "Spirit", 2: "FURIA", 3: "Aurora", 4: "Falcons",
        5: "Vitality", 6: "BetBoom", 7: "9z", 8: "G2",
    }
