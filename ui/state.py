"""Session/state constants + pure validation for the Phase 2 UI (UI-05, DX-01).

Imports NO streamlit — every name here (FIXED_SEED, Mode, the key constants, and the
validate_ratings gate) is a plain Python value/function so the UI-05 "bad rating cell"
gate is unit-tested directly (RESEARCH Open Question 2: do not drive the data_editor
through AppTest just to test validation).
"""

from __future__ import annotations

from enum import Enum

# Fixed RNG seed for every UI run — matches the engine __main__ smoke run so reruns are
# reproducible and the seed need NOT enter the cache key (RESEARCH A3). A deterministic
# tool wants reproducible numbers; per-session variety is explicitly out of scope.
FIXED_SEED = 20260528

# UI cap on N — mirrors the engine CLI's sane bound so an absurd N can't hang the app for
# hours (threat T-02-INPUT / DoS). 5,000,000 sims is already far beyond any useful run.
MAX_N = 5_000_000

# Rating bound mirrors engine.teams._validate_fixture (0 < r < 1000). The data_editor's
# NumberColumn min/max is the first line of defence; validate_ratings re-checks before the
# engine is ever called so a bad value never reaches it as an exception (defense in depth).
RATING_MIN_EXCLUSIVE = 0
RATING_MAX_EXCLUSIVE = 1000


class Mode(str, Enum):
    """The two top-level modes (UI-01). LIVE is a placeholder shell in Phase 2 (result
    locking is Phase 4); PRE_STAGE is the default on first load (a fresh user has no locks).
    """

    PRE_STAGE = "Pre-stage"
    LIVE = "Live"


# Default mode on first load — Pre-stage, NOT Live (a first run has no locked results, so
# defaulting to Live would land the user on the empty "Lock a result to go live" dead-end).
DEFAULT_MODE = Mode.PRE_STAGE

# session_state key constants (single source so app.py + tests agree on the names).
KEY_MODE = "mode"
KEY_MC_CACHE = "mc_cache"          # dict: (ratings_key, S, N, locked_key) -> Result
KEY_RATINGS_EDITOR = "ratings_editor"
KEY_S_SLIDER = "S_slider"
KEY_N_INPUT = "N_input"
KEY_RUN_BUTTON = "run_btn"

# UI-05 canonical inline error copy (UI-SPEC Copywriting Contract — do not drift).
BAD_RATING_MSG = "Ratings must be numbers. Fix the highlighted cell, then Run."


def validate_ratings(rows: list[dict]) -> list[int]:
    """Return the list of offending seeds for the UI-05 "bad rating cell" gate.

    A cell is bad when its rating is empty/None or out of range (NOT non-numeric text —
    the NumberColumn widget blocks that at the cell, Pitfall 5). Mirrors the engine bound
    ``0 < r < 1000`` (engine.teams._validate_fixture) so a bad value is blocked BEFORE the
    engine is called. Returns ``[]`` when every row is valid (Run is allowed).

    ``rows`` are the data_editor rows: ``[{"seed": int, "team": str, "rating": float|None}]``.
    """
    offenders: list[int] = []
    for row in rows:
        seed = row.get("seed")
        rating = row.get("rating")
        # Empty / missing cell.
        if rating is None:
            offenders.append(seed)
            continue
        # Non-numeric (defensive — the widget should prevent this, but never trust it).
        if isinstance(rating, bool) or not isinstance(rating, (int, float)):
            offenders.append(seed)
            continue
        # NaN (NaN != NaN) or out of the engine's accepted bound.
        if rating != rating or not (
            RATING_MIN_EXCLUSIVE < rating < RATING_MAX_EXCLUSIVE
        ):
            offenders.append(seed)
    return offenders
