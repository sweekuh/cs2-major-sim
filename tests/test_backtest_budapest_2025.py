"""THE GATE — round-by-round backtest against a real past Major stage (Wave 4).

GATE-01/05 (intended): reproduce StarLadder Budapest 2025 Stage 1 pairings EXACTLY —
the only check that proves the greedy rematch resolution matches Valve's 15-row
priority table.

STATUS (user decision 2026-05-29): GATE-01 is DEFERRED. The Budapest Stage 1 RESULTS
were fully reconciled and verified via /browse (both anchors confirmed: exactly 8 teams
at 1-1 entering R3; final eight = M80, FlyQuest, B8, Fnatic, NIP, PARIVISION, Imperial,
FaZe). BUT the authoritative Valve 1-16 SEED assignment could not be sourced (HLTV is
Cloudflare-walled; Liquipedia/Wikipedia do not publish seed integers), and the HLTV VRS
world-rank order does NOT reproduce the actual R1 pairings or the R2 pure-seed fold.
That divergence cannot be disentangled (wrong-seeds vs an engine within-group-pairing
nuance) without the authoritative seed bracket, so asserting a green full-reproduction
backtest would be a false pass/fail (threat T-04-01).

Per the user decision, the full pairing-reproduction backtest is SKIPPED (not xfail —
it is explicitly deferred pending data, not "expected to fail"), and Phase 1 is gated on
the already-green rulebook unit tests (test_swiss.py / test_mc.py) instead. The fixture
SHAPE is still validated below (threat T-04-02) without asserting pairing generation.

Resume path: obtain the authoritative Valve/HLTV seeded bracket image, freeze the 1-16
seeds into the fixture, remove the skip, and assert exact round-by-round pairings; apply
the planned GATE-04 priority-table fork on any divergence. Tracked in
.planning/todos/pending.
"""

from __future__ import annotations

import json
import pathlib

import pytest

FIXTURE = (
    pathlib.Path(__file__).resolve().parent
    / "fixtures"
    / "budapest_2025_stage1.json"
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


@pytest.mark.skip(
    reason="GATE-01 deferred — Budapest seed assignment unresolved; full "
    "pairing-reproduction backtest pending authoritative Valve seeds. "
    "See .planning/todos/pending. Engine gated on rulebook unit tests."
)
def test_backtest_budapest_2025():
    """Feed Budapest 2025 Stage 1 seeds + forced results (as `locked`); assert the
    engine GENERATES the actual round-by-round pairings at each round.

    DEFERRED: blocked on the authoritative Valve 1-16 seed integers (see module
    docstring). Do NOT assert this against a guessed seeding — it would be a false
    pass/fail (T-04-01).
    """
    from engine.swiss import simulate_stage  # noqa: F401

    raise AssertionError(
        "GATE-01 deferred: freeze authoritative Budapest seeds, then assert exact pairings"
    )


def test_budapest_fixture_shape_is_internally_legal():
    """T-04-02: validate the FROZEN Budapest fixture is internally legal WITHOUT
    needing the (unresolved) seeding or asserting engine pairing generation.

    Real-data assertions on the reconciled results only:
      - exactly 8 teams advance (reach 3 wins) and exactly 8 are eliminated (3 losses)
      - the advancing set is exactly the verified stable eight
      - across all locked matchups no team plays the same opponent twice (no rematch)
      - every team's final record is legal (3-W to advance, 3-L to eliminate; total 16)

    This validates the fixture's SHAPE (T-04-02) and freezes the verified results; it
    deliberately does NOT assert that the engine reproduces the pairings (GATE-01,
    deferred — seeds unresolved).
    """
    fx = _load_fixture()

    # Seeding is intentionally unresolved and must be recorded as such.
    assert fx["seeding"] is None
    assert "UNRESOLVED" in fx["seeding_note"]

    # 16 distinct teams.
    teams = fx["teams"]
    assert len(teams) == 16
    assert len(set(teams)) == 16

    # Advancers / eliminated partition the 16 cleanly.
    advancers = set(fx["advancers"])
    eliminated = set(fx["eliminated"])
    assert len(advancers) == 8
    assert len(eliminated) == 8
    assert advancers.isdisjoint(eliminated)
    assert advancers | eliminated == set(teams)

    # The advancing eight match the verified stable set (anchor).
    assert advancers == EXPECTED_ADVANCERS

    # Reconstruct each team's W/L and opponent history from the locked matchups,
    # then assert legality: no rematch, and a legal terminal record.
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

    # No rematch: every opponent appears at most once for each team.
    for t in teams:
        assert len(opponents[t]) == len(set(opponents[t])), (
            f"{t} has a rematch in the fixture: {opponents[t]}"
        )

    # Legal terminal record: each team ended at exactly 3 wins (advanced) OR
    # exactly 3 losses (eliminated), and the advance/eliminate sets agree with it.
    for t in teams:
        terminal_advance = wins[t] == ADVANCE_AT_WINS
        terminal_eliminate = losses[t] == ELIMINATE_AT_LOSSES
        assert terminal_advance or terminal_eliminate, (
            f"{t} did not terminate legally: {wins[t]}W-{losses[t]}L"
        )
        if terminal_advance:
            assert t in advancers, f"{t} reached 3 wins but is not in advancers"
        if terminal_eliminate:
            assert t in eliminated, f"{t} reached 3 losses but is not in eliminated"

    # Anchor: exactly 8 teams sit at 1-1 entering Round 3 (verified during reconcile).
    r2 = next(r for r in fx["rounds"] if r["round"] == 2)
    assert len(r2["anchor_8_at_1_1_entering_r3"]) == 8

    # Fixture must reference M80 (sanity that the right event was frozen).
    assert "M80" in teams
