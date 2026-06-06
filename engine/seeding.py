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
from engine.teams import ADVANCE_AT_WINS, Team


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
