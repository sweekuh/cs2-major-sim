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

from dataclasses import dataclass, field

import numpy as np

from engine.optimizer import Ballot, Matrices, build_outcome_matrices, p_ge5
from engine.swiss import simulate_stage
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


# ===========================================================================
# D5 — pge5_delta: the from-here arrow as two p_ge5 calls on ONE fixed ballot (RESIM-02)
# ===========================================================================
def pge5_delta(
    anchor_ballot: Ballot,
    pre_lock_result,
    post_lock_result,
    ids: list[int],
) -> tuple[float, float]:
    """The P(>=5)-from-here delta as ``(before, after)`` (D5).

    Two ``engine.optimizer.p_ge5`` calls on the SAME fixed anchor ballot against TWO samples
    (pre-lock and post-lock), both matrices built with the SAME ``ids``:

      before = p_ge5(anchor_ballot, build_outcome_matrices(pre_lock_result.sample, ids))
      after  = p_ge5(anchor_ballot, build_outcome_matrices(post_lock_result.sample, ids))

    The ballot NEVER re-optimizes — the question is "how is *my* locked-in ballot doing as
    results come in," so the anchor is fixed and only the sample changes. Reads ``.sample``
    only; never re-runs the MC. ``pre_lock_result`` / ``post_lock_result`` may be a real
    ``engine.montecarlo.Result`` or any object exposing ``.sample``.
    """
    pre_matrices = build_outcome_matrices(pre_lock_result.sample, ids)
    post_matrices = build_outcome_matrices(post_lock_result.sample, ids)
    before = p_ge5(anchor_ballot, pre_matrices)
    after = p_ge5(anchor_ballot, post_matrices)
    return before, after


# ===========================================================================
# D6 — derive_bracket / legal_pairings_for_round: replay the engine (RESIM-04)
# ===========================================================================
class LivePrefixIncomplete(Exception):
    """Raised by ``legal_pairings_for_round`` when a prior round is not fully locked.

    The live-mode invariant forbids opening round R before round R-1 is fully entered, because
    ``simulate_stage`` computes round-R pairings from start-of-round standings — which depend
    on the SAMPLED winners of any unlocked prior game. With an incomplete prefix the round-R
    pairing set is a single-RNG-draw artifact, so the validator must never accept/reject a lock
    against it; we raise instead.
    """


@dataclass(frozen=True)
class BracketView:
    """The record-bucket bracket derived from one engine replay (D6).

    ``legal_pairings`` is one entry per round (R1 first), each a list of ``frozenset((a,b))``
    the engine GENERATED that round given the locks-so-far. ``records`` is ``{id: (wins,
    losses)}`` after the (partially locked) replay. ``locked_edges`` marks which pairings are
    LOCKED (solid edge) vs simulated-only (faint) — the UI renders solid/faint off this. No
    streamlit.
    """

    legal_pairings: list[list[frozenset]]
    records: dict[int, tuple[int, int]]
    locked_edges: set[frozenset] = field(default_factory=set)


def _fresh_teams(template: list[Team]) -> list[Team]:
    """Rebuild a clean per-replay team set from the template's identity fields.

    ``simulate_stage`` mutates wins/losses/opps, so the replay must own its Team objects and
    never leak state into the caller's ``teams``. Mirrors ``engine.montecarlo._fresh_teams``
    (re-implemented locally so we do not import a private helper). Only id/name/seed/rating
    carry over; counters/opps reset.
    """
    return [Team(id=t.id, name=t.name, seed=t.seed, rating=t.rating) for t in template]


def derive_bracket(teams: list[Team], locked: dict[frozenset, int], S: float) -> BracketView:
    """Replay ``simulate_stage`` once with the current ``locked`` to derive the bracket (D6).

    ONE ``simulate_stage`` call (not N) with a fixed throwaway rng — collect ``pairings_out``
    into per-round ``legal_pairings`` and the final standings into ``records``. Mark each
    pairing solid (locked) or faint (simulated-only). No cache (D7). Tolerates a PARTIAL
    prefix — this is the read-only render/standings path; the validator-feeding
    ``legal_pairings_for_round`` enforces the full-prefix precondition separately.
    """
    pairings_out: list[list[frozenset]] = []
    rng = np.random.default_rng(0)  # throwaway: pairings are format-determined; locked teams deterministic
    by_id = simulate_stage(_fresh_teams(teams), None, S, rng, dict(locked), pairings_out=pairings_out)

    records = {tid: (t.wins, t.losses) for tid, t in by_id.items()}
    locked_edges = set(locked.keys())
    return BracketView(
        legal_pairings=[list(round_pairs) for round_pairs in pairings_out],
        records=records,
        locked_edges=locked_edges,
    )


def legal_pairings_for_round(
    teams: list[Team],
    locked_results: list[tuple[int, int, int]],
    S: float,
    round_idx: int,
) -> set[frozenset]:
    """The validator's ``legal_pairings`` for round ``round_idx`` (0-based, R1 == 0) — D6/BLOCKER2.

    PRECONDITION: every round ``r < round_idx`` must be FULLY locked — the count of locked
    pairings at round r must equal the number of pairings the engine generated for round r in
    the replay, and every generated pairing must be present in the locks. Otherwise round
    ``round_idx``'s pairings are computed from start-of-round standings that depend on a
    sampled prior winner — a single-RNG-draw artifact — so we raise ``LivePrefixIncomplete``
    rather than return a draw the validator could (wrongly) accept/reject against.

    When the precondition holds the entire prefix takes ``_play``'s deterministic locked
    branch, so round ``round_idx``'s pairings are rng-invariant — exactly the set the
    validator needs. Returns ``set(pairings_out[round_idx])``.
    """
    locked = locked_dict_from_results(locked_results)
    pairings_out: list[list[frozenset]] = []
    rng = np.random.default_rng(0)  # throwaway: the full prefix makes the prefix deterministic
    simulate_stage(_fresh_teams(teams), None, S, rng, dict(locked), pairings_out=pairings_out)

    # Locks grouped by round index (the user-entered round each lock belongs to).
    locks_by_round: dict[int, set[frozenset]] = {}
    for (r, w, ell) in locked_results:
        locks_by_round.setdefault(r, set()).add(frozenset((w, ell)))

    for r in range(round_idx):
        if r >= len(pairings_out):
            raise LivePrefixIncomplete(
                f"round {r} has no pairings in the replay — cannot open round {round_idx}"
            )
        engine_round = set(pairings_out[r])
        locked_round = locks_by_round.get(r, set())
        if locked_round != engine_round:
            raise LivePrefixIncomplete(
                f"round {r} is not fully locked ({len(locked_round)} of "
                f"{len(engine_round)} pairings) — cannot open round {round_idx}"
            )

    if round_idx >= len(pairings_out):
        raise LivePrefixIncomplete(
            f"round {round_idx} does not exist in the replay (stage has "
            f"{len(pairings_out)} rounds)"
        )
    return set(pairings_out[round_idx])
