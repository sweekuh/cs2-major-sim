"""Live-mode pure core (Phase 4, 04-01) — the streamlit-free decision math LIVE mode wires in.

NON-NEGOTIABLES (CLAUDE.md / 04-01-PLAN.md):
  - NO ENGINE MUTATION. This module IMPORTS swiss/optimizer/teams and CALLS them; it never
    edits them. The GATE-01 Budapest backtest stays green. Its only files are this one and
    tests/test_live.py.
  - Pure + streamlit-free (functional-core invariant, like the optimizer).
  - Classification is computed against the CONDITIONAL ``Result.sample`` via the reused
    ``engine.optimizer.build_outcome_matrices`` — NEVER against the bracket render, and with
    EXACT ``== 1.0`` / ``== 0.0`` comparisons (no epsilon): the conditional sample is
    degenerate for locked-out teams.
  - Status keys map to the existing blue/amber STATUS palette ('advanced'|'live'|'eliminated')
    — never red/green, never a colour token here.
  - Key everything on team ``id``; never assume ``id == seed``.
  - The bracket / validator legal_pairings are DERIVED by replaying
    ``engine.swiss.simulate_stage(..., pairings_out=[])`` with the current locks — never
    re-derive pairings by hand (that re-opens the GATE-01 seed/Buchholz blind spot). Each
    replay is ONE stage sim (D7), so no cache.

This file owns four contracts the Plan-02 UI consumes:
  D1  locked_dict_from_results — lock-list <-> engine ``locked`` dict projection
  D3  validate_lock            — reject every impossible lock with the EXACT reason string
  D4  classify_pick            — secured/dead/live off the conditional sample
  D5  pge5_delta               — the from-here arrow as two p_ge5 calls on a FIXED ballot
  D6  derive_bracket / legal_pairings_for_round — replay the engine for pairings + standings
"""

from __future__ import annotations

from engine.optimizer import Matrices
from engine.teams import ADVANCE_AT_WINS, ELIMINATE_AT_LOSSES, Team

# ---------------------------------------------------------------------------
# Bucket -> outcome-matrix index (the build_outcome_matrices tuple order).
# ---------------------------------------------------------------------------
_BUCKET_INDEX = {"picks_30": 0, "picks_adv": 1, "picks_03": 2}


# ===========================================================================
# D1 — lock-list <-> engine ``locked`` dict projection
# ===========================================================================
def locked_dict_from_results(
    locked_results: list[tuple[int, int, int]],
) -> dict[frozenset, int]:
    """Project an ordered ``list[(round_idx, winner_id, loser_id)]`` into the engine
    ``locked`` dict ``{frozenset((winner, loser)): winner}`` (the EXACT shape
    ``_play`` / ``freeze_locked`` consume).

    Order-independent (frozenset key) and round-trippable: the winner is recoverable as the
    value, the pair as the key. The round index is dropped — the engine ``locked`` dict is
    keyed only on the pair (a stage never plays the same pair twice).
    """
    return {frozenset((w, ell)): w for (_round_idx, w, ell) in locked_results}


# ===========================================================================
# D3 — validate_lock (RESIM-03): reject every impossible lock with a reason string
# ===========================================================================
def _records_from_locked(
    locked_results: list[tuple[int, int, int]],
) -> dict[int, tuple[int, int]]:
    """Running (wins, losses) per team id from the locked results so far.

    Counts a win for each winner and a loss for each loser across every prior lock — exact
    enough for the terminated-team check (a team at ADVANCE_AT_WINS wins or
    ELIMINATE_AT_LOSSES losses is out).
    """
    wins: dict[int, int] = {}
    losses: dict[int, int] = {}
    for (_r, w, ell) in locked_results:
        wins[w] = wins.get(w, 0) + 1
        losses[ell] = losses.get(ell, 0) + 1
    ids = set(wins) | set(losses)
    return {tid: (wins.get(tid, 0), losses.get(tid, 0)) for tid in ids}


def validate_lock(
    new: tuple[int, int],
    round_idx: int,
    locked_results: list[tuple[int, int, int]],
    teams: list[Team],
    legal_pairings: set[frozenset],
) -> str | None:
    """Reject an impossible lock with a human reason string, else return None (RESIM-03).

    ``new`` is ``(winner_id, loser_id)`` the user is locking; keyed on ``id`` throughout
    (never assume ``id == seed``). The five enumerated illegal cases (D3) and their EXACT
    reason strings:

      - winner-not-in-pair (degenerate): the two ids are equal / malformed pair.
      - rematch:        ``frozenset(new)`` already appears in a prior locked pair.
      - terminated:     winner OR loser already at ADVANCE_AT_WINS wins or
                        ELIMINATE_AT_LOSSES losses (replayed from locked_results).
      - non-pairing:    ``frozenset(new)`` not in ``legal_pairings`` for ``round_idx``.
      - double-booking: winner or loser already in another lock at ``round_idx``.

    Reason strings are plain text (id->name lookup); the UI escapes them at its boundary.
    """
    winner_id, loser_id = new
    name = {t.id: t.name for t in teams}

    def nm(tid: int) -> str:
        return name.get(tid, str(tid))

    pair = frozenset((winner_id, loser_id))

    # Winner-not-in-pair (degenerate caller bug — mirrors swiss.py:219). A self-pair has a
    # single member, so the "pair" is not two distinct teams.
    if winner_id == loser_id or len(pair) != 2:
        return f"locked winner {nm(winner_id)} is not one of {nm(winner_id)}/{nm(loser_id)}."

    # Rematch — this exact pair already played this stage.
    prior_pairs = {frozenset((w, ell)) for (_r, w, ell) in locked_results}
    if pair in prior_pairs:
        return f"{nm(winner_id)} vs {nm(loser_id)} already played this stage — no rematches."

    # Terminated team — winner or loser already at 3W or 3L from the locked results so far.
    records = _records_from_locked(locked_results)
    for tid in (winner_id, loser_id):
        w, ell = records.get(tid, (0, 0))
        if w >= ADVANCE_AT_WINS or ell >= ELIMINATE_AT_LOSSES:
            return (
                f"{nm(tid)} is already out (3-0 advanced / 0-3 eliminated) — "
                f"cannot play another match."
            )

    # Not an actual pairing — the format does not pair these two this round.
    if pair not in legal_pairings:
        return (
            f"{nm(winner_id)} and {nm(loser_id)} are not paired this round — "
            f"the format pairs by record + Buchholz."
        )

    # Double-booking — either team already locked into ANOTHER match at this round_idx.
    for (r, w, ell) in locked_results:
        if r != round_idx:
            continue
        booked = {w, ell}
        for tid in (winner_id, loser_id):
            if tid in booked:
                return f"{nm(tid)} is already locked into another match this round."

    return None


# ===========================================================================
# D4 — classify_pick: secured/dead/live against the CONDITIONAL sample (RESIM-02)
# ===========================================================================
def classify_pick(team_id: int, bucket: str, matrices: Matrices) -> str:
    """Classify a (team, bucket) pick as a STATUS key against the conditional sample (D4).

    ``bucket`` in ``{"picks_30", "picks_adv", "picks_03"}`` selects the matching boolean
    array from ``build_outcome_matrices`` (the tuple ``(is_30, is_adv, is_03)``). Then:

      - p == 1.0 -> "advanced" (secured — the pick is already guaranteed by the locks)
      - p == 0.0 -> "eliminated" (dead — the pick is now impossible given the locks)
      - 0 < p < 1 -> "live" (still in play)

    EXACT 1.0 / 0.0 comparison, no epsilon: the conditional sample is degenerate for a
    locked-out team. Returns a STATUS key ('advanced'|'eliminated'|'live') — never red/green,
    never a colour.
    """
    arr = matrices[_BUCKET_INDEX[bucket]][team_id]
    p = float(arr.mean())
    if p >= 1.0:
        return "advanced"
    if p <= 0.0:
        return "eliminated"
    return "live"
