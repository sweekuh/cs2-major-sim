"""Real-data seeding backtest — the ACTUAL Cologne 2026 Stage-1 result -> Stage-2 seeds.

This is the seeding-chain analog of the GATE-01 Budapest pairing backtest: it feeds the
AUTHORITATIVE Cologne Stage-1 final result (the user-entered, engine-recovered, Buchholz-
verified standings, frozen in tests/fixtures/cologne_2026_stage1_results.json) through the
SHIPPED chain (final_standings_from_locked -> seed_next_stage) and asserts the derived
Stage-2 seed order. It locks in the merge rule + the Buchholz tiebreak on real data so a
future change to either is caught.

RECONCILED 2026-06-09 against the OFFICIAL bracket: the invited 1-8 order below is the
ascending Valve Global Standings rank from the 2026_05_04 invitation snapshot (FUT #4,
Spirit #5, Astralis #6, G2 #12, Legacy #14, paiN #17, Monte #18, 9z #19), confirmed by all
8 official R1 pairings AND the engine replay reproducing the official R2-R5 pairings (the
full-pairing gate lives in tests/test_backtest_stage2.py). The earlier inferred order
(Spirit/Legacy/Astralis/FUT/...) reproduced R1 only — rounds 2-5 falsified it. The
qualifier 9-16 order was already correct (the rulebook Stage-1-placement merge).
"""
from __future__ import annotations

import json
from pathlib import Path

from engine.teams import load_teams, load_stage
from engine.seeding import (
    InvitedTeam,
    final_standings_from_locked,
    seed_next_stage,
    stage_is_complete,
)

S = 40.0
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cologne_2026_stage1_results.json"

# Expected Stage-1 final records (HIGH-confidence, cross-checked) — the gate's ground truth.
EXPECTED_RECORDS = {
    "B8": (3, 0), "BetBoom": (3, 0),
    "GamerLegion": (3, 1), "M80": (3, 1), "MIBR": (3, 1),
    "TYLOO": (3, 2), "BIG": (3, 2), "FlyQuest": (3, 2),
    "NRG": (2, 3), "Liquid": (2, 3), "Lynn Vision": (2, 3),
    "HEROIC": (1, 3), "Sharks": (1, 3), "THUNDER dOWNUNDER": (1, 3),
    "SINNERS": (0, 3), "Gaimin Gladiators": (0, 3),
}

# Expected derived Stage-2 seed order (seeds 1-16). Invited 1-8 = the CONFIRMED official order
# (ascending VRS in the 2026_05_04 invitation snapshot, from data/stage2.json); qualifiers 9-16
# by the rulebook merge (losses asc -> -Buchholz -> prior Stage-1 seed) — confirmed official.
EXPECTED_SEED_ORDER = [
    "FUT Esports", "Spirit", "Astralis", "G2", "Legacy", "paiN", "Monte", "9z",
    "B8", "BetBoom", "GamerLegion", "M80", "MIBR", "TYLOO", "BIG", "FlyQuest",
]


def _locks_from_fixture() -> list[tuple[int, int, int]]:
    """Project the frozen results fixture into the engine lock list (round_idx, winner, loser)."""
    fx = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    locks = []
    for r in fx["results"]:
        lo, hi = r["match"]
        w = r["winner"]
        ell = lo if w == hi else hi
        locks.append((r["round_idx"], w, ell))
    return locks


def test_real_stage1_is_complete_with_correct_records():
    """The authoritative Stage-1 result replays to a COMPLETE stage with the known 2/3/3-3/3/2 split."""
    teams = load_teams()
    locks = _locks_from_fixture()
    assert stage_is_complete(teams, locks, S), "the real Stage-1 result must be a complete stage"

    final = final_standings_from_locked(teams, locks, S)
    by_name = {t.name: t for t in final.values()}
    got = {nm: (by_name[nm].wins, by_name[nm].losses) for nm in EXPECTED_RECORDS}
    assert got == EXPECTED_RECORDS


def test_real_stage1_derives_expected_stage2_seeding():
    """The shipped chain derives the expected Stage-2 seed-1..16 order from the real Stage-1 result.

    Invited 1-8 from data/stage2.json (VERIFIED names); qualifiers 9-16 by the merge rule. This is
    the regression gate on the inter-stage seeding chain run against real Cologne data.
    """
    teams = load_teams()
    locks = _locks_from_fixture()
    final = final_standings_from_locked(teams, locks, S)

    s2, _ = load_stage("data/stage2.json")
    invited = [InvitedTeam(name=t.name, vrs_rank=t.seed, rating=t.rating) for t in s2 if t.seed <= 8]
    assert len(invited) == 8, "data/stage2.json must carry exactly 8 invited rows (seeds 1-8)"

    derived = seed_next_stage(final, invited)
    assert [t.seed for t in derived] == list(range(1, 17)), "derived seeds are exactly 1..16"
    assert [t.name for t in derived] == EXPECTED_SEED_ORDER

    # The 8 qualifiers (seeds 9-16) are exactly the Stage-1 advancers, never an invited team.
    qualifiers = {t.name for t in derived if t.seed >= 9}
    assert qualifiers == {n for n, r in EXPECTED_RECORDS.items() if r[0] >= 3}

    # Loss-bucket monotonicity: a qualifier with fewer losses never seeds below one with more.
    rec = {t.name: t for t in final.values()}
    q_losses = [rec[t.name].losses for t in derived if t.seed >= 9]
    assert q_losses == sorted(q_losses), "qualifier seeds must be losses-ascending (rulebook merge)"
