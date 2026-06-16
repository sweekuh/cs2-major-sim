"""Pure inter-stage seed derivation — Stage N FINAL standings -> Stage N+1 seeds.

No state, no I/O, no streamlit/httpx/requests, no RNG. Every function here is referentially
transparent so the SEED-02 determinism gate can verify it in isolation.

Load-bearing facts (getting any wrong silently corrupts every downstream Stage-2 pairing):
  - Qualifier seeds derive from Stage N FINAL Buchholz via engine.probs.difficulty
    (the canonical Difficulty Score; ENG-03) — ONE Buchholz definition, NO second copy here.
  - The VERIFIED Valve merge rule (supplemental rulebook, [INFERRED] until reconciled against
    the official Stage-2 seed list): the directly-invited teams take seeds 1-8 by their
    pre-event (global VRS) rank; the 8 advancing qualifiers take seeds 9-16 by their final
    seed from the previous stage. NOT interleaved.
  - The qualifier final-standings tiebreak chain is the literal rulebook reading
    (losses ascending, then Difficulty Score descending, then prior initial seed ascending) —
    an explicit TOTAL key so identical inputs yield BYTE-IDENTICAL seeds across two runs
    (SEED-02). NO reliance on dict/set iteration order; NO numpy RNG call anywhere here.
  - This is a NEW sibling of the byte-frozen GATE-01 path: it imports difficulty + Team and
    edits no engine file, so the Budapest backtest stays green by construction.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.probs import difficulty  # canonical Buchholz (ENG-03) — no second copy
from engine.swiss import simulate_stage  # FROZEN replay path (SEED-03 full-lock standings)
from engine.teams import ADVANCE_AT_WINS, ELIMINATE_AT_LOSSES, Team


@dataclass(frozen=True)
class InvitedTeam:
    """A Stage-2 directly-invited team, seeded by its global Valve Regional Standing rank.

    ``vrs_rank`` is the global VRS rank (lower = better seed). ``rating`` is the [INFERRED]
    rating-only fallback prior (editable in the UI; market-calibrated once odds load). Frozen
    so an invited descriptor is a hashable, immutable input to the pure derivation.
    """

    name: str
    vrs_rank: int
    rating: float


def seed_next_stage(
    prior_finals: dict[int, Team],
    invited: list[InvitedTeam],
) -> list[Team]:
    """Derive the ordered seed-1..16 Stage N+1 ``Team`` list (VERIFIED Valve merge rule).

    Valve merge rule (supplemental rulebook — [INFERRED], editable until reconciled against
    the official Stage-2 seed list):
        "The teams directly invited to this stage will be seeds 1-8 and use their pre-event
         seed. The advancing 8 teams will be seeds 9-16 and use their final seed from the
         previous stage."  — NOT interleaved.

    Args:
      prior_finals: the ``{id: Team}`` map from a FULLY-LOCKED prior-stage replay
        (e.g. ``simulate_stage(..., locked, pairings_out=[])``). Each ``Team`` must carry
        final ``.wins/.losses`` AND a populated ``.opps`` set of opponent OBJECTS, because the
        canonical ``difficulty()`` reads each opponent's record over ``t.opps`` — a bare
        ``{id: (wins, losses)}`` record dict would lose the opponent graph Buchholz needs.
      invited: the 8 directly-invited teams (any object exposing ``.name/.vrs_rank/.rating``;
        ``InvitedTeam`` is the canonical shape).

    Qualifiers are the prior-stage teams with ``wins >= ADVANCE_AT_WINS`` (exactly 8 on a
    complete stage; a non-8 count raises rather than emitting a short list — Pitfall 5).

    Tiebreak chain for the 8 qualifiers — the LITERAL rulebook final-standings order, written
    as ONE sorted key with every level named (Open Question 1 resolution; mirrors
    engine.swiss.rank_group's documented single-path key):
        1. losses ASCENDING        -> a 3-0 advancer outseeds a 3-1 outseeds a 3-2
        2. Difficulty Score (Buchholz) DESCENDING within a loss bucket   -> ``-difficulty(t)``
        3. prior-stage INITIAL seed ASCENDING (final discriminator)       -> ``t.seed``

    id-vs-seed (the project rule "never assume id == seed"): the qualifier's ``t.seed`` used in
    the tiebreak key is its prior-stage INITIAL seed; the OUTPUT Team's ``.seed`` (== ``.id``)
    is its NEW Stage-2 list position (1..16). These are kept distinct.

    PURE: no RNG, no file I/O, no dict/set iteration-order dependence -> identical inputs yield
    byte-identical output (SEED-02). Returns a 16-element seed-ordered ``list[Team]``.
    """
    qualifiers = [t for t in prior_finals.values() if t.wins >= ADVANCE_AT_WINS]
    if len(qualifiers) != 8:
        raise ValueError(
            f"expected exactly 8 advancing qualifiers (wins >= {ADVANCE_AT_WINS}), "
            f"got {len(qualifiers)} — prior stage is not complete (SEED-03/Pitfall 5)"
        )

    # Qualifiers by the literal final-standings chain (losses asc, Difficulty desc, seed asc).
    qualifiers_ranked = sorted(qualifiers, key=lambda t: (t.losses, -difficulty(t), t.seed))

    # Invited by global VRS rank ASCENDING; name is a stable fallback so the key is a TOTAL
    # order even on a hand-entered duplicate rank (no iteration-order tie-break leaks in).
    invited_ranked = sorted(invited, key=lambda iv: (iv.vrs_rank, iv.name))

    seeds: list[Team] = []
    # Seeds 1-8 = invited, in VRS / pre-event order.
    for i, iv in enumerate(invited_ranked, start=1):
        seeds.append(Team(id=i, name=iv.name, seed=i, rating=iv.rating))
    # Seeds 9-16 = qualifiers, in final prior-stage order.
    for offset, t in enumerate(qualifiers_ranked):
        s = 9 + offset
        seeds.append(Team(id=s, name=t.name, seed=s, rating=t.rating))
    return seeds


def seed_playoffs(prior_finals: dict[int, Team]) -> list[Team]:
    """Derive the 8 playoff BRACKET seeds (1..8) from a FULLY-LOCKED final Swiss stage (PLAY-03).

    The playoffs are a single-elimination BRACKET, not another Swiss stage, so this is a SEPARATE
    derivation from ``seed_next_stage`` (ROADMAP v4 — deliberately NOT a ``_NEXT_STAGE`` merge:
    there is no directly-invited 8 to splice in; ALL eight bracket teams come from the prior
    stage's finish). The advancers (``wins >= ADVANCE_AT_WINS`` — exactly 8 on a complete stage;
    a non-8 count raises rather than emitting a short list, Pitfall 5) are seeded 1..8 by the SAME
    literal final-standings chain ``seed_next_stage`` uses for its qualifiers (ONE Buchholz
    definition, no second copy):
        1. losses ASCENDING        -> a 3-0 advancer outseeds a 3-1 outseeds a 3-2
        2. Difficulty Score (Buchholz) DESCENDING within a loss bucket   -> ``-difficulty(t)``
        3. prior-stage INITIAL seed ASCENDING (final discriminator)       -> ``t.seed``

    id-vs-seed (the project rule "never assume id == seed"): the ``t.seed`` in the tiebreak key is
    the team's prior-stage INITIAL seed; the OUTPUT Team's ``.seed`` (== ``.id``) is its NEW 1..8
    BRACKET position. The bracket matchups (1v8, 4v5, 2v7, 3v6) are derived from these seeds in
    ``engine.bracket`` — not stored here.

    PURE: no RNG, no file I/O, no dict/set iteration-order dependence -> byte-identical output for
    identical input (mirrors ``seed_next_stage``). Returns an 8-element seed-ordered ``list[Team]``.
    """
    advancers = [t for t in prior_finals.values() if t.wins >= ADVANCE_AT_WINS]
    if len(advancers) != 8:
        raise ValueError(
            f"expected exactly 8 playoff advancers (wins >= {ADVANCE_AT_WINS}), "
            f"got {len(advancers)} — prior stage is not complete (PLAY-03/Pitfall 5)"
        )
    ranked = sorted(advancers, key=lambda t: (t.losses, -difficulty(t), t.seed))
    return [
        Team(id=i, name=t.name, seed=i, rating=t.rating)
        for i, t in enumerate(ranked, start=1)
    ]


# ===========================================================================
# SEED-03 — completeness gate + full-lock replay standings (the auto-derive precondition).
# ===========================================================================
# These two helpers are the SEED-03 wiring side of the chain. Unlike seed_next_stage (which is
# RNG-free and accepts an already-replayed {id: Team}), they DO the replay — so numpy enters the
# module HERE and ONLY here. A fully-locked replay takes _play's deterministic locked branch and
# never samples, so the throwaway rng below does NOT affect output (mirrors engine.live.derive_bracket
# line 257 + the SEED-02 determinism claim on seed_next_stage is unaffected: the import is confined
# to this region, asserted by test_seeding_is_pure). Both helpers CALL the frozen engine + REUSE the
# engine.live full-lock precondition; they never mutate a frozen engine file (GATE-01 stays green).


def final_standings_from_locked(
    teams: list[Team],
    locked_results: list[tuple[int, int, int]],
    S: float,
) -> dict[int, Team]:
    """Replay a FULLY-LOCKED prior stage -> ``{id: Team}`` with ``.opps`` populated (RNG-invariant).

    Builds the engine ``locked`` dict from the ordered ``list[(round_idx, winner_id, loser_id)]``
    lock list via ``engine.live.locked_dict_from_results`` (the exact shape ``_play`` consumes),
    then runs the SHIPPED ``simulate_stage`` once with a FRESH per-replay team set and a throwaway
    rng. The returned Teams carry final ``.wins/.losses`` AND the opponent OBJECT set the canonical
    ``difficulty()`` needs — i.e. the ``{id: Team}`` ``seed_next_stage`` consumes.

    Determinism: a fully-locked prefix takes ``_play``'s deterministic locked branch for every match,
    so the standings are independent of the throwaway rng seed (T-07-10 / engine.live.derive_bracket).
    The numpy import is local to this helper to keep the SEED-02 purity claim on ``seed_next_stage``
    sharp (the module-level derivation path stays RNG-free).
    """
    import numpy as np

    from engine.live import locked_dict_from_results

    locked = locked_dict_from_results(locked_results)
    rng = np.random.default_rng(0)  # throwaway: a fully-locked stage is deterministic (no sampling)
    return simulate_stage(_replay_fresh(teams), None, S, rng, dict(locked), pairings_out=[])


def stage_is_complete(
    teams: list[Team],
    locked_results: list[tuple[int, int, int]],
    S: float,
) -> bool:
    """True iff the prior stage is COMPLETE + validated -> the chain may auto-derive (SEED-03).

    Complete means BOTH:
      1. every round is FULLY locked (no unlocked prior game whose winner would otherwise be
         sampled), AND
      2. every team has terminated (``wins >= ADVANCE_AT_WINS`` or ``losses >= ELIMINATE_AT_LOSSES``).

    Condition (1) REUSES the ``engine.live`` full-lock-prefix precondition rather than reinventing
    it (decisions #5): we ask ``legal_pairings_for_round`` for the round PAST the last replayed round
    inside a try/except — a partial prefix raises ``LivePrefixIncomplete`` (the EXACT exception SEED-03
    names), so we return False and the app emits NO seed list (never seeds off sampled winners,
    T-07-09 / Anti-Pattern 6). When the prefix is fully locked, that same call returns the next round's
    pairing set (or, if the stage truly ended, raises "round N does not exist" — also handled as the
    full-lock terminal case via the termination check below).

    A partial/incomplete stage therefore yields False (-> no derivation); only a fully-locked,
    fully-terminated stage yields True. This helper CALLS the frozen engine + reuses the live
    precondition; it edits no engine file.
    """
    from engine.live import (
        LivePrefixIncomplete,
        legal_pairings_for_round,
        locked_dict_from_results,
    )

    # Derive the standings (and round count) from the full-lock replay.
    import numpy as np

    pairings_out: list[list[frozenset]] = []
    rng = np.random.default_rng(0)  # throwaway: a fully-locked stage is deterministic
    by_id = simulate_stage(
        _replay_fresh(teams), None, S, rng, dict(locked_dict_from_results(locked_results)),
        pairings_out=pairings_out,
    )
    num_rounds = len(pairings_out)

    # (1) Full-lock-prefix check via the reused live precondition. Ask for the round PAST the last
    # the replay produced: an incomplete prefix raises LivePrefixIncomplete -> not complete. A
    # fully-locked stage raises "round N does not exist" (round_idx >= len(pairings_out)) instead,
    # which is NOT a partial-prefix failure — so we treat ONLY LivePrefixIncomplete-on-a-partial-prefix
    # as incomplete and lean on the termination check (2) for the all-locked terminal case.
    try:
        legal_pairings_for_round(teams, locked_results, S, num_rounds)
    except LivePrefixIncomplete as exc:
        # Distinguish "a prior round is not fully locked" (partial -> incomplete) from
        # "the stage has no round num_rounds" (fully locked, stage ended -> still possibly complete).
        if "not fully locked" in str(exc) or "has no pairings" in str(exc):
            return False
        # else: "round N does not exist" — the prefix is fully locked; fall through to (2).

    # (2) Every team terminated (3W or 3L). On a partial stage at least one team is still active.
    return all(
        t.wins >= ADVANCE_AT_WINS or t.losses >= ELIMINATE_AT_LOSSES for t in by_id.values()
    )


def _replay_fresh(template: list[Team]) -> list[Team]:
    """Clean per-replay team set (id/name/seed/rating only; counters/opps reset).

    Re-implemented locally (a one-line rebuild) so ``simulate_stage`` owns its Team objects and
    never leaks wins/losses/opps back into the caller's ``teams`` — mirrors
    ``engine.live._fresh_teams`` without importing a private helper at module scope.
    """
    return [Team(id=t.id, name=t.name, seed=t.seed, rating=t.rating) for t in template]
