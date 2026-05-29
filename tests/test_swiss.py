"""Swiss-engine tests — RED scaffold for Wave 2 (engine/swiss.py).

These are xfail(strict=False) so the suite collects and is not falsely green while
swiss.py does not yet exist. When wave 2 implements engine/swiss.py, remove the
xfail marks (or they xpass) and assert the real behavior. The behaviors below are
the load-bearing correctness checks the structural invariants alone do NOT catch.
"""

from __future__ import annotations

import pytest

WAVE2 = pytest.mark.xfail(reason="implemented in wave 2 (engine/swiss.py)", strict=False)


@WAVE2
def test_fold_uses_difficulty_rank():
    """ENG-04: the list handed to the fold is sorted (-difficulty, seed) for R3+.

    A 4-team group where Buchholz order != seed order must pair on difficulty rank,
    not raw seed. Removing the difficulty sort MUST change the output (no dead code).
    """
    from engine.swiss import rank_group  # noqa: F401

    raise AssertionError("wave 2: assert ranked order uses (-difficulty, seed)")


@WAVE2
def test_forced_rematch_pairing():
    """GATE-03: a 6-team group whose Priority-1 row contains a rematch must select the
    first lower-priority rematch-free row from Valve's 15-row table."""
    from engine.swiss import pair_within_group  # noqa: F401

    raise AssertionError("wave 2: assert priority-table row selection on forced rematch")


@WAVE2
def test_no_valid_matching_fallback():
    """ENG-05/GATE-03: an unmatchable group falls back to least-disruptive rematch +
    warning, never an unhandled None / crash."""
    from engine.swiss import pair_within_group  # noqa: F401

    raise AssertionError("wave 2: assert fallback pairs without crashing")


@WAVE2
def test_locked_results_honored():
    """ENG-08: a locked winner is deterministic across sims, invariants still hold
    post-lock, and the no-rematch rule respects locked history (Phase 4 re-sim seam)."""
    from engine.swiss import simulate_stage  # noqa: F401

    raise AssertionError("wave 2: assert locked winners deterministic + no-rematch honored")
