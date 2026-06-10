"""Stage-2 -> Stage-3 seeding-chain gate + the verified Stage-3 field (STG-06).

The stage2 -> stage3 derive reuses the EXACT chain the real Cologne Stage-1 -> Stage-2 backtest
validated (tests/test_stage2_seeding.py): ``final_standings_from_locked -> seed_next_stage`` with
the NEXT stage's fixture seeds 1-8 as the invited list. These tests lock two things:

  1. The CHAIN is stage-agnostic in fact, not just by intent — a complete Stage-2 replay derives
     a structurally-correct Stage-3 seed list (seeds 1..16, invited 1-8 from data/stage3.json in
     fixture/VRS order, qualifiers 9-16 == the 8 advancers, losses-ascending within 9-16).
     A deterministic full-lock replay (the Budapest lock pattern, name-independent) is the
     complete-Stage-2 source, so this is RNG-invariant like the SEED-02 gates.

  2. The DATA: data/stage3.json carries the real Cologne Stage-3 field (verified-by-source
     2026-06-09) — the invited 8 in VRS order and the 8 REAL Stage-2 advancers. The invited ORDER
     is asserted exactly (it is corroborated by three known R1 pairings under seed-i-vs-i+8:
     Vitality-FUT, NaVi-Spirit, PARIVISION-9z); the advancers are asserted as a SET because their
     within-loss-bucket order is [INFERRED] until reconciled vs the official bracket — when the
     official Stage-3 seed list posts, tighten this to an exact-order assert (a data
     reconciliation, not a code regression; the test_stage2_seeding NOTE discipline).

NOTE (event-time): once the user locks the COMPLETE real Stage-2 results in-app, add the
real-data analog of test_stage2_seeding.py (frozen Stage-2 results fixture -> expected Stage-3
seeds). The full per-round Stage-2 match list was not automatable on 2026-06-09 (Liquipedia/HLTV
403 automated fetch), so only the field + records are locked here, per LESSONS "don't build
against guessed shapes".
"""
from __future__ import annotations

import json
from pathlib import Path

from engine.seeding import (
    InvitedTeam,
    final_standings_from_locked,
    seed_next_stage,
    stage_is_complete,
)
from engine.teams import load_stage

S = 40.0

# The verified Stage-3 invited 8, in fixture (VRS) order — seeds 1-8 of data/stage3.json.
EXPECTED_INVITED_ORDER = [
    "Vitality", "Natus Vincere", "Falcons", "The MongolZ",
    "PARIVISION", "Aurora", "FURIA", "MOUZ",
]

# The 8 REAL Stage-2 advancers (Stage 2 finished 2026-06-09): Spirit & FUT 3-0; BetBoom, G2, 9z
# 3-1; Monte, Legacy, B8 3-2. A SET on purpose — within-bucket order stays [INFERRED] (see module
# docstring) and an over-frozen order would mistake a data reconciliation for a code regression.
EXPECTED_ADVANCERS = {"Spirit", "FUT Esports", "BetBoom", "G2", "9z", "Monte", "Legacy", "B8"}


def _budapest_locks() -> list[tuple[int, int, int]]:
    """The FULL verified Budapest lock pattern as (round_idx, winner_seed, loser_seed).

    The engine is name-independent and a fully-locked replay never samples, so this by-seed lock
    list replays any 16-seed Swiss fixture (here: Stage 2) to a deterministic complete finish —
    the same device tests/test_app.py uses for the app-level derive wiring.
    """
    fx = json.loads(
        (Path(__file__).resolve().parent / "fixtures" / "budapest_2025_stage1.json").read_text(
            encoding="utf-8"
        )
    )
    name_to_seed = {name: int(s) for s, name in fx["seeding"].items()}
    return [
        (int(rnd["round"]) - 1, name_to_seed[m["winner"]], name_to_seed[m["loser"]])
        for rnd in fx["rounds"]
        for m in rnd["matches"]
    ]


def _stage3_invited() -> list[InvitedTeam]:
    s3, _cfg = load_stage("data/stage3.json")
    return [InvitedTeam(name=t.name, vrs_rank=t.seed, rating=t.rating) for t in s3 if t.seed <= 8]


def test_stage3_fixture_carries_verified_field():
    """The committed Stage-3 fixture is the real Cologne field: all-Bo3 flag on, invited 1-8 in
    VRS order (exact), seeds 9-16 == the real Stage-2 advancers (set), and the two halves are
    disjoint. Fails on any silent fixture edit that drops a verified team or the Bo3 mode."""
    s3, cfg = load_stage("data/stage3.json")
    assert cfg.get("all_bo3") is True, "Stage 3 is ALL-Bo3 (BO-01) — the flag must survive edits"
    assert [t.name for t in s3 if t.seed <= 8] == EXPECTED_INVITED_ORDER
    advancers = {t.name for t in s3 if t.seed >= 9}
    assert advancers == EXPECTED_ADVANCERS
    assert advancers.isdisjoint(set(EXPECTED_INVITED_ORDER)), "no team enters Stage 3 twice"


def test_complete_stage2_replay_derives_structurally_correct_stage3():
    """The SHIPPED chain (final_standings_from_locked -> seed_next_stage) derives Stage-3 seeds
    from a complete Stage-2 replay with every structural invariant of the rulebook merge:
    seeds exactly 1..16; 1-8 = the Stage-3 invited (VRS order, never a prior-stage team);
    9-16 = exactly the 8 advancers of the replay; losses ascending within 9-16. This is the
    stage2 -> stage3 analog of the test_stage2_seeding gate, on the deterministic replay."""
    s2, _cfg = load_stage("data/stage2.json")
    locks = _budapest_locks()
    assert stage_is_complete(s2, locks, S), "the full Budapest pattern must complete Stage 2"

    final = final_standings_from_locked(s2, locks, S)
    invited = _stage3_invited()
    assert len(invited) == 8, "data/stage3.json must carry exactly 8 invited rows (seeds 1-8)"

    derived = seed_next_stage(final, invited)
    assert [t.seed for t in derived] == list(range(1, 17)), "derived seeds are exactly 1..16"
    assert [t.name for t in derived if t.seed <= 8] == EXPECTED_INVITED_ORDER, (
        "seeds 1-8 are the invited teams in VRS order — never interleaved with advancers"
    )

    # Seeds 9-16 are exactly the replay's 8 advancers (wins >= 3), losses-ascending (merge rule).
    advancers = {t.name for t in final.values() if t.wins >= 3}
    assert {t.name for t in derived if t.seed >= 9} == advancers
    rec = {t.name: t for t in final.values()}
    q_losses = [rec[t.name].losses for t in derived if t.seed >= 9]
    assert q_losses == sorted(q_losses), "qualifier seeds must be losses-ascending (rulebook merge)"


def test_stage3_derive_is_deterministic():
    """SEED-02 extended to the stage2 -> stage3 hop: two independent replays + derives yield
    byte-identical seed lists (no RNG, no iteration-order dependence anywhere in the chain)."""
    s2, _cfg = load_stage("data/stage2.json")
    locks = _budapest_locks()

    def _derive():
        final = final_standings_from_locked(s2, locks, S)
        return [(t.seed, t.name, t.rating) for t in seed_next_stage(final, _stage3_invited())]

    assert _derive() == _derive()
