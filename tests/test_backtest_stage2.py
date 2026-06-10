"""Stage-2 round-by-round backtest — the SECOND real-data pairing gate (GATE-01 method).

The Budapest gate proved the pairing engine on a past Major; this one proves it on the
LIVE event: it feeds Cologne 2026 Stage 2's CONFIRMED seeds + actual results (as
``locked``) into the engine and asserts it GENERATES the real round-by-round pairings at
every round, then that the SHIPPED Stage-2 -> Stage-3 chain derives the OFFICIAL Stage-3
seeds 9-16 — the real-data 2->3 backtest TODOS deferred until the Stage-2 round list was
lockable (it became lockable 2026-06-09 when Stage 2 finished).

Seeding resolution (2026-06-09): the R1 pairings alone CANNOT pin absolute seed numbers
(any pair-preserving relabeling reproduces them — the trap that produced the two earlier
wrong inferred orders). The fixture's order is the UNIQUE survivor of a brute force over
all 8! invited orders requiring (a) the official R1 under seed-i-vs-i+8, (b) the engine
replay reproducing the official R2-R5 pairings exactly, (c) the shipped chain deriving the
official Stage-3 seeds 9-16, and it independently equals the ascending Valve Global
Standings order (invitation snapshot 2026_05_04) Liquipedia states as the seeding rule.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np

from engine.seeding import InvitedTeam, seed_next_stage
from engine.swiss import build_round1_pairs, simulate_stage
from engine.teams import Team, load_stage

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "cologne_2026_stage2.json"

ADVANCE_AT_WINS = 3


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _seeding(fx) -> dict[int, str]:
    return {int(s): name for s, name in fx["seeding"].items()}


def _build_teams(fx) -> list[Team]:
    """16 teams keyed id==seed; ratings are placeholders (every match locked -> the engine
    never samples; pairing generation is fully deterministic)."""
    return [Team(id=s, name=name, seed=s, rating=50.0) for s, name in _seeding(fx).items()]


def _locked_and_expected(fx, name_to_seed) -> tuple[dict, list[set]]:
    locked: dict[frozenset, int] = {}
    expected_rounds: list[set[frozenset]] = []
    for rnd in fx["rounds"]:
        round_pairs: set[frozenset] = set()
        for m in rnd["matches"]:
            w, ell = name_to_seed[m["winner"]], name_to_seed[m["loser"]]
            key = frozenset((w, ell))
            locked[key] = w
            round_pairs.add(key)
        expected_rounds.append(round_pairs)
    return locked, expected_rounds


def test_backtest_cologne_2026_stage2():
    """The engine reproduces Cologne 2026 Stage 2's actual round-by-round pairings EXACTLY
    under the confirmed seeds — every round, including the 6-team R4/R5 groups (the
    priority-table path), running the same simulate path the app ships."""
    fx = _load_fixture()
    name_to_seed = {name: s for s, name in _seeding(fx).items()}
    teams = _build_teams(fx)
    locked, expected_rounds = _locked_and_expected(fx, name_to_seed)

    pairings_out: list[list[frozenset]] = []
    simulate_stage(teams, None, 40.0, np.random.default_rng(0), locked,
                   pairings_out=pairings_out)

    assert len(pairings_out) == len(expected_rounds)
    for i, (generated, actual) in enumerate(zip(pairings_out, expected_rounds), start=1):
        gen = set(generated)
        assert gen == actual, (
            f"Round {i} pairings DIVERGE.\n"
            f"  generated: {sorted(tuple(sorted(p)) for p in gen)}\n"
            f"  actual:    {sorted(tuple(sorted(p)) for p in actual)}"
        )

    final = simulate_stage(_build_teams(fx), None, 40.0, np.random.default_rng(1), locked)
    advanced = {t.name for t in final.values() if t.wins == ADVANCE_AT_WINS}
    assert advanced == set(fx["advancers"])


def test_stage2_round1_is_kvsk8_under_confirmed_seeds():
    """The confirmed seeds reproduce all 8 actual R1 matches under seed k vs k+8 (ENG-01)."""
    fx = _load_fixture()
    name_to_seed = {name: s for s, name in _seeding(fx).items()}
    generated_r1 = {frozenset((a.id, b.id)) for a, b in build_round1_pairs(_build_teams(fx))}
    actual_r1 = {
        frozenset((name_to_seed[m["winner"]], name_to_seed[m["loser"]]))
        for m in next(r for r in fx["rounds"] if r["round"] == 1)["matches"]
    }
    assert generated_r1 == actual_r1


def test_real_stage2_derives_official_stage3_qualifier_seeding():
    """The real-data 2->3 backtest (was a TODOS item): the SHIPPED chain
    (simulate_stage locked replay -> seed_next_stage) run on the real Stage-2 result
    derives EXACTLY the official Stage-3 seeds 9-16 read from the Liquipedia bracket
    (FUT, Spirit, G2, BetBoom, 9z, Monte, B8, Legacy) — validating the losses-asc ->
    Buchholz-desc -> prior-seed merge against live Valve practice for a second stage."""
    fx = _load_fixture()
    name_to_seed = {name: s for s, name in _seeding(fx).items()}
    teams = _build_teams(fx)
    locked, _ = _locked_and_expected(fx, name_to_seed)
    finals = simulate_stage(teams, None, 40.0, np.random.default_rng(0), locked)

    s3, _cfg = load_stage("data/stage3.json")
    invited = [InvitedTeam(name=t.name, vrs_rank=t.seed, rating=t.rating)
               for t in s3 if t.seed <= 8]
    derived = seed_next_stage(finals, invited)

    # Fixture names match data/stage2.json's; stage-3 file uses the same provider-neutral
    # names for the 8 advancers, so a plain name comparison is exact.
    assert [t.name for t in derived[8:]] == fx["stage3_qualifier_seeding"]
    # And the committed stage-3 fixture's 9-16 ARE that derivation (one seeding path).
    assert [t.name for t in s3 if t.seed >= 9] == fx["stage3_qualifier_seeding"]


def test_stage2_fixture_shape_is_internally_legal():
    """The frozen fixture is internally legal: a 1..16 seeding over exactly the 16 teams,
    8 advancers all reaching exactly 3 wins, legal terminal records, no rematches."""
    fx = _load_fixture()
    seeding = _seeding(fx)
    assert set(seeding) == set(range(1, 17))
    assert len(set(seeding.values())) == 16

    wins: dict[str, int] = {}
    losses: dict[str, int] = {}
    seen_pairs: set[frozenset] = set()
    for rnd in fx["rounds"]:
        for m in rnd["matches"]:
            w, ell = m["winner"], m["loser"]
            pair = frozenset((w, ell))
            assert pair not in seen_pairs, f"rematch: {sorted(pair)}"
            seen_pairs.add(pair)
            wins[w] = wins.get(w, 0) + 1
            losses[ell] = losses.get(ell, 0) + 1
    for name in seeding.values():
        w, ell = wins.get(name, 0), losses.get(name, 0)
        assert (w == 3 and ell <= 2) or (ell == 3 and w <= 2), f"{name} ended {w}-{ell}"
    assert {n for n in seeding.values() if wins.get(n, 0) == 3} == set(fx["advancers"])