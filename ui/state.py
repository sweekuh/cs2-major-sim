"""Session/state constants + pure validation for the Phase 2 UI (UI-05, DX-01).

Imports NO streamlit — every name here (FIXED_SEED, Mode, the key constants, and the
validate_ratings gate) is a plain Python value/function so the UI-05 "bad rating cell"
gate is unit-tested directly (RESEARCH Open Question 2: do not drive the data_editor
through AppTest just to test validation).
"""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path

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
KEY_STAGE = "active_stage"          # str: the selected stage_id ('stage1'|'stage2'|...) — Phase 6, STG-04
KEY_MC_CACHE = "mc_cache"          # dict: (stage_id, ratings_key, S, N, locked_key) -> Result
KEY_RATINGS_EDITOR = "ratings_editor"
KEY_S_SLIDER = "S_slider"
KEY_N_INPUT = "N_input"
KEY_RUN_BUTTON = "run_btn"
# Persisted "Fetch odds now" outcome: ("success"|"info"|"error", message). Stashed in the click
# handler and rendered on the NEXT run so the message survives the st.rerun() that the fetch
# triggers (a message drawn before st.rerun() is discarded — the toast-lost bug, fixed 2026-05-31).
KEY_ODDS_OUTCOME = "odds_fetch_outcome"
# Persisted "Fetch latest results" outcome: ("success"|"info"|"error", message). Same one-shot
# stash/render/pop discipline as KEY_ODDS_OUTCOME (Phase 6, RES-02) — the message is stashed in the
# fetch-results click handler and rendered on the NEXT run after the st.rerun() the fetch triggers.
KEY_RESULTS_OUTCOME = "results_fetch_outcome"
# Phase 6 (RES-03) conflict-confirm + provenance keys.
# KEY_PENDING_RESULT_CONFLICT stashes the ONE fetched (round_idx, winner_id, loser_id) lock that
# conflicts with an existing MANUAL lock for the same pair — set by the pre-fill loop, consumed by
# the explicit "Apply fetched result" confirm control. A conflicting fetch is NEVER silently applied
# (the manual lock is authoritative ground truth); the swap is validated BEFORE the manual lock is
# removed (atomic — manual lock preserved on an engine-illegal fetched lock).
KEY_PENDING_RESULT_CONFLICT = "pending_result_conflict"
# KEY_LOCK_PROVENANCE maps a lock pair frozenset((winner, loser)) -> "auto"|"manual": "manual" is
# tagged at the _commit_lock site (a user-entered lock); "auto" is tagged when a fetched result
# pre-fills a lock. A missing entry reads as "manual" (the pre-Phase-6 default — every prior lock
# was user-entered). The conflict gate keys off this so an auto-fetch never clobbers a manual lock.
KEY_LOCK_PROVENANCE = "lock_provenance"

# --- Phase 4 LIVE-mode keys (RESIM-01..04) -----------------------------------------------
# KEY_LOCKED holds the ordered source-of-truth list of locked results:
#   list[(round_idx, winner_id, loser_id)]  (0-based round; R1 == 0).
# The engine-facing ``locked`` dict {frozenset((w,l)): w} is a DERIVED projection (D1) fed
# through the EXISTING freeze_locked->locked_key->cache_key path so re-sim fires for free.
KEY_LOCKED = "locked_results"
# The fixed anchor ballot (OptimizerOutput.recommended / Ballot B) captured at the FIRST Run
# from the EMPTY-locked pre_key Result; stored once so the delta arrow never re-optimizes (D5).
KEY_LIVE_ANCHOR = "live_anchor_ballot"
# The pending (round_idx, winner_id, loser_id) the user selected in the lock controls, read by
# the "Lock result" button handler. It is validated via engine.live.validate_lock BEFORE being
# committed to KEY_LOCKED (D3/RESIM-03) — an illegal pending lock surfaces st.error and is dropped.
KEY_PENDING_LOCK = "pending_lock"

# UI-05 canonical inline error copy (UI-SPEC Copywriting Contract — do not drift).
BAD_RATING_MSG = "Ratings must be numbers. Fix the highlighted cell, then Run."

# --- Trust badge (UI-07) + seed-safety (DX-02) + fail-soft odds (ODDS-08) gates ----------
#
# BACKTEST_PASSED is an EXPLICIT flag. Flipped True 2026-05-29: the Budapest 2025 Stage-1
# round-by-round backtest is GREEN (GATE-01/04/05). The engine reproduces every actual
# pairing under the authoritative Valve VRS-snapshot seeds (test_backtest_budapest_2025).
# It gates the trust badge together with seeds_confirmed (Pitfall 6 "both, not one"): the
# engine is now backtest-validated, but the badge stays caveated until the user confirms the
# Cologne 2026 seeds (which are still [INFERRED]). Do NOT flip back as a side effect.
BACKTEST_PASSED = True

# UI-07 caveated badge text — the EXACT string (UI-SPEC Copywriting). Shown while the Cologne
# seeds are unconfirmed. The engine is validated (rulebook unit tests + full round-by-round
# backtest); what's pending now is confirming THIS event's [INFERRED] seeds — NOT the backtest.
# No green ✓, no "backtest passed", no Budapest/Austin in the caveat. test_trust_badge_wording
# asserts this string verbatim.
TRUST_BADGE_CAVEATED = (
    "engine validated (Valve rulebook + round-by-round backtest) — confirm the Cologne seeds to finalize"
)

# UI-07 VALIDATED badge text — used ONLY by the green st.success branch once BOTH
# BACKTEST_PASSED is flipped True AND seeds are confirmed (currently unreachable). It MUST
# NOT reuse the caveated "pending seed data" wording (a green box claiming "pending" is
# self-contradicting — WR-02) and MUST NOT mention Budapest/Austin (CLAUDE.md trust-badge
# rule): the round-by-round backtest is described generically.
TRUST_BADGE_VALIDATED = (
    "engine validated vs Valve rulebook unit tests + full round-by-round backtest"
)

# Legacy base name of the seeds-confirmed session key (the gate the trust badge reads). Phase 6
# (STG-05) made the banner PER-STAGE: app.py now binds the toggle to f"seeds_confirmed_{stage_id}"
# (e.g. "seeds_confirmed_stage1"), seeded from that stage's own fixture flag, so confirming one
# stage cannot dismiss another's banner. This constant is kept as the documented base name.
KEY_SEEDS_CONFIRMED = "seeds_confirmed"

# Optional odds-provider env var (Phase 5/ODDS-08). Presence is checked WITHOUT importing
# httpx/python-dotenv so the Phase 2 zero-config first-run promise is preserved.
ODDS_KEY_ENV = "ODDSPAPI_KEY"


def trust_badge_state(seeds_confirmed: bool) -> str:
    """Return ``"validated"`` ONLY when BOTH ``BACKTEST_PASSED`` AND ``seeds_confirmed`` are
    true; otherwise ``"caveated"`` (UI-07, Pitfall 6 — "both, not one").

    Reads ``BACKTEST_PASSED`` off the module at call time (not at def time) so a future flip
    of the constant takes effect — and so a test can prove the both-gated logic by overriding
    it. In Phase 2 the constant is False, so the badge is always caveated regardless of the
    seeds toggle: the deferred backtest means it cannot honestly claim "validated".
    """
    import ui.state as _self  # late ref so a runtime flip of BACKTEST_PASSED is honoured

    if _self.BACKTEST_PASSED and seeds_confirmed:
        return "validated"
    return "caveated"


def read_seeds_confirmed(path: str | Path | None = None) -> bool:
    """Read the ``seeds_confirmed`` flag from data/stage1.json READ-ONLY (DX-02).

    This seeds the INFERRED-seed banner's initial state (the shipped JSON ships ``false``).
    The frozen engine's ``load_teams`` does not surface this field, so we parse the raw JSON
    here — WITHOUT mutating the engine or the JSON. Any error (missing file, bad JSON, no
    field) falls back to ``False`` (banner shows) — fail safe, never raise into the UI.
    """
    src = Path(path) if path is not None else _DATA_PATH
    try:
        raw = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(raw.get("seeds_confirmed", False)) if isinstance(raw, dict) else False


def odds_key_present() -> bool:
    """Return True iff an odds-provider key is set in the environment (ODDS-08 fail-soft seam).

    Checks ``os.environ`` ONLY — it does NOT import httpx/python-dotenv (the fail-soft stub
    must not pull the Phase 5 network deps, preserving the zero-config first run). The key
    VALUE is never returned or logged — presence only (threat T-02-SECRET).
    """
    return bool(os.environ.get(ODDS_KEY_ENV))


# Path to the shipped fixture (mirrors engine.teams.DATA_PATH; kept local so this module
# imports no engine code for a simple read-only flag).
_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "stage1.json"


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


# --- Phase 4 pure lock-list helpers (D1) -------------------------------------------------
# list-in / list-out, NO session_state coupling, so they unit-test directly (mirroring
# validate_ratings). app.py holds st.session_state[KEY_LOCKED]; these operate on that list.

def add_lock(
    locked_results: list[tuple[int, int, int]],
    round_idx: int,
    winner_id: int,
    loser_id: int,
) -> list[tuple[int, int, int]]:
    """Return a NEW lock list with ``(round_idx, winner_id, loser_id)`` appended.

    Never mutates the input (reruns stay predictable). Validation is the caller's job
    (engine.live.validate_lock runs BEFORE this in app.py — D3/RESIM-03).
    """
    return [*locked_results, (round_idx, winner_id, loser_id)]


def remove_last_lock(
    locked_results: list[tuple[int, int, int]],
) -> list[tuple[int, int, int]]:
    """Return a NEW lock list with the LAST lock dropped ("undo last lock"). Empty -> empty."""
    return list(locked_results[:-1])


def locks_for_round(
    locked_results: list[tuple[int, int, int]], round_idx: int
) -> list[tuple[int, int, int]]:
    """Return the lock entries entered at ``round_idx`` (used to gate round-R controls on R-1)."""
    return [entry for entry in locked_results if entry[0] == round_idx]


def locked_dict(locked_results: list[tuple[int, int, int]]) -> dict:
    """Project the lock list into the engine ``locked`` dict — delegates to engine.live (D1).

    Imported lazily so ui.state stays cheap to import (and keeps no import-time engine cost);
    state.py is streamlit-free either way — engine.live imports no streamlit.
    """
    from engine.live import locked_dict_from_results

    return locked_dict_from_results(list(locked_results))
