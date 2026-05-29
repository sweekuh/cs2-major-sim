"""THE GATE — round-by-round backtest against a real past Major stage (Wave 4).

GATE-01/05: reproduce StarLadder Budapest 2025 Stage 1 pairings EXACTLY. This is the
only check that proves the greedy rematch resolution matches Valve's 15-row priority
table; no UI is built and no sim output is trusted until this passes.

xfail(strict=False) until wave 4. The fixture data is intentionally NOT encoded here:
plan 01-04 Task 1 is an autonomous:false checkpoint that re-fetches and reconciles the
Budapest Stage 1 fixture match-by-match via gstack /browse (two research fetches
disagreed on the 1-1 bucket entering R3). Encoding it now would bake in an error. The
reconciliation IS the gate, not pre-work for it.
"""

from __future__ import annotations

import pytest

WAVE4 = pytest.mark.xfail(
    reason="implemented in wave 4 (the backtest gate); fixture reconciled in 01-04 Task 1",
    strict=False,
)


@WAVE4
def test_backtest_budapest_2025():
    """Feed Budapest 2025 Stage 1 seeds + forced results (as `locked`); assert the
    engine GENERATES the actual round-by-round pairings at each round.

    Required fixture (transcribed verbatim from Liquipedia at execution, reconciled
    before asserting — research data was internally inconsistent):
      - 16 initial seeds (Valve standings order)
      - each round's matchups grouped by record bucket, winner, Bo1/Bo3 status
      - the eight advancing and eight eliminated teams
    Sanity anchor (stable across fetches): advancers M80, FlyQuest, B8, Fnatic, NIP,
    PARIVISION, Imperial, FaZe.
    """
    from engine.swiss import simulate_stage  # noqa: F401

    raise AssertionError("wave 4: encode reconciled Budapest 2025 fixture and assert exact pairings")
