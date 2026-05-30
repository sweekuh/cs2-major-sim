"""THE GATE — round-by-round backtest against a real past Major stage (GATE-01/04/05).

Feeds StarLadder Budapest 2025 Stage 1's authoritative seeds + actual results (as
``locked``) into the engine and asserts it GENERATES the real round-by-round pairings at
every round. This is the only check that proves the within-group pairing — the difficulty
(Buchholz) ranking, the high-low fold, and Valve's verbatim 15-row priority table (which
the 6-team R4/R5 groups exercise) — matches reality. The structural invariants Σ=2/2/8
pass even when this logic is silently wrong, so this backtest is the real proof.

Seeds (RESOLVED 2026-05-29): from the timestamped Valve VRS snapshot used for Major
seeding (ValveSoftware/counter-strike_regional_standings, 2025_11_03) — NOT live HLTV/VRS
(the original mistake; the "snapshot rule"). The 16 Opening-Stage teams sorted by their
global VRS rank in that snapshot give the 1-16 order in the fixture. Validated: under the
engine's own rules this order reproduces all 8 R1 pairings and all 4 R2-High pairings, the
pure-seed discriminator that failed under every live-ranking guess — confirming the engine
logic was correct and only the seed integers were wrong (Hypothesis B).
"""

from __future__ import annotations

import json
import pathlib

import numpy as np

from engine.swiss import build_round1_pairs, simulate_stage
from engine.teams import Team

FIXTURE = (
    pathlib.Path(__file__).resolve().parent / "fixtures" / "budapest_2025_stage1.json"
)

ADVANCE_AT_WINS = 3
ELIMINATE_AT_LOSSES = 3
EXPECTED_ADVANCERS = {
    "M80",
    "FlyQuest",
    "B8",
    "Fnatic",
    "NIP",
    "PARIVISION",
    "Imperial",
    "FaZe",
}


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _seeding(fx) -> dict[int, str]:
    """{seed: team_name} with int seeds (JSON keys are strings)."""
    return {int(s): name for s, name in fx["seeding"].items()}


def _build_teams(fx) -> list[Team]:
    """16 Budapest teams keyed id==seed; ratings are placeholders (every match is locked,
    so the engine never samples — pairing generation is fully deterministic)."""
    return [Team(id=s, name=name, seed=s, rating=50.0) for s, name in _seeding(fx).items()]


def test_backtest_budapest_2025():
    """GATE-01/04/05 (PASSING): the engine reproduces Budapest 2025 Stage 1's actual
    round-by-round pairings EXACTLY — every round, including the 6-team R4/R5 groups that
    exercise Valve's verbatim 15-row priority table (GATE-04) — running the same simulate
    path the app ships. This is the only check that proves the within-group difficulty
    (Buchholz) ranking, the high-low fold, and the priority table match reality; the
    structural invariants Σ=2/2/8 pass even when this logic is silently wrong.

    Seeds are the pure global-VRS-rank order from the authoritative Valve seeding snapshot
    (counter-strike_regional_standings 2025_11_03). An earlier by-hand disambiguation of
    four adjacent seeds (Fnatic/PARIVISION at 5/6, RED Canids/The Huns at 13/14) was wrong
    and this exact test caught it at Round 2 — the gate working as designed."""
    fx = _load_fixture()
    name_to_seed = {name: s for s, name in _seeding(fx).items()}
    teams = _build_teams(fx)

    # Build `locked` (every match's winner) and the expected pairing set per round, both
    # keyed on seed (== team id). Pairings are order-independent within a round → use sets.
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

    # Run the SHIPPED simulate path; capture the pairings it generates each round.
    pairings_out: list[list[frozenset]] = []
    rng = np.random.default_rng(0)  # unused: all matches locked → deterministic
    simulate_stage(teams, None, 40.0, rng, locked, pairings_out=pairings_out)

    assert len(pairings_out) == len(expected_rounds), (
        f"engine produced {len(pairings_out)} rounds, fixture has {len(expected_rounds)}"
    )

    # The gate: every round's GENERATED pairings equal the ACTUAL pairings. R4/R5 are
    # 6-team groups → this exercises the verbatim priority table against real data (GATE-04).
    for i, (generated, actual) in enumerate(zip(pairings_out, expected_rounds), start=1):
        gen = set(generated)
        assert gen == actual, (
            f"Round {i} pairings DIVERGE.\n"
            f"  generated: {sorted(tuple(sorted(p)) for p in gen)}\n"
            f"  actual:    {sorted(tuple(sorted(p)) for p in actual)}"
        )

    # And the engine reaches the verified final standings (8 advance / 8 eliminate).
    final = simulate_stage(_build_teams(fx), None, 40.0, np.random.default_rng(1), locked)
    advanced = {t.name for t in final.values() if t.wins == ADVANCE_AT_WINS}
    assert advanced == EXPECTED_ADVANCERS


def test_round1_is_kvsk8_under_resolved_seeds():
    """The resolved seeds reproduce all 8 actual R1 matches under seed k vs k+8 (ENG-01).
    This is the load-bearing seed check: a wrong seed order breaks R1 immediately."""
    fx = _load_fixture()
    name_to_seed = {name: s for s, name in _seeding(fx).items()}
    teams = _build_teams(fx)

    generated_r1 = {frozenset((a.id, b.id)) for a, b in build_round1_pairs(teams)}
    actual_r1 = {
        frozenset((name_to_seed[m["winner"]], name_to_seed[m["loser"]]))
        for m in next(r for r in fx["rounds"] if r["round"] == 1)["matches"]
    }
    assert generated_r1 == actual_r1


def test_budapest_fixture_shape_is_internally_legal():
    """T-04-02: the frozen Budapest fixture is internally legal — exactly 8 advance / 8
    eliminate, the verified advancing eight, no rematch, legal terminal records, the
    1-1-entering-R3 anchor, and a resolved 1-16 seeding consistent with the teams."""
    fx = _load_fixture()

    # Seeding is now RESOLVED: a 16-entry 1..16 map onto the team set.
    seeding = _seeding(fx)
    teams = fx["teams"]
    assert set(seeding) == set(range(1, 17))
    assert set(seeding.values()) == set(teams)
    assert "RESOLVED" in fx["seeding_note"]

    assert len(teams) == 16 and len(set(teams)) == 16

    advancers = set(fx["advancers"])
    eliminated = set(fx["eliminated"])
    assert len(advancers) == 8 and len(eliminated) == 8
    assert advancers.isdisjoint(eliminated)
    assert advancers | eliminated == set(teams)
    assert advancers == EXPECTED_ADVANCERS

    wins: dict[str, int] = {t: 0 for t in teams}
    losses: dict[str, int] = {t: 0 for t in teams}
    opponents: dict[str, list[str]] = {t: [] for t in teams}
    for rnd in fx["rounds"]:
        for match in rnd["matches"]:
            w, ell = match["winner"], match["loser"]
            assert w in wins and ell in wins, f"unknown team in match {match}"
            wins[w] += 1
            losses[ell] += 1
            opponents[w].append(ell)
            opponents[ell].append(w)

    for t in teams:
        assert len(opponents[t]) == len(set(opponents[t])), (
            f"{t} has a rematch in the fixture: {opponents[t]}"
        )

    for t in teams:
        terminal_advance = wins[t] == ADVANCE_AT_WINS
        terminal_eliminate = losses[t] == ELIMINATE_AT_LOSSES
        assert terminal_advance or terminal_eliminate, (
            f"{t} did not terminate legally: {wins[t]}W-{losses[t]}L"
        )
        if terminal_advance:
            assert t in advancers
        if terminal_eliminate:
            assert t in eliminated

    r2 = next(r for r in fx["rounds"] if r["round"] == 2)
    assert len(r2["anchor_8_at_1_1_entering_r3"]) == 8
    assert "M80" in teams
