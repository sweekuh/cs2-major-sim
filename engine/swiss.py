"""Valve Major Stage-1 Swiss engine — the correctness core (the hard part).

Groups active teams by record, ranks within a group by difficulty-then-seed (a SINGLE
code path for all rounds >= 2, no ``if round == 2`` special case), pairs via a
rematch-avoiding high-vs-low fold backed by Valve's verbatim 15-row priority table,
falls back gracefully on an unmatchable group, places Bo3 correctly, and honors a
``locked`` dict deterministically (the seam Phase 4 rides on).

Load-bearing facts (getting any wrong silently corrupts every probability while the
structural invariants Σ=2/2/8 still pass — the unit tests here + the wave-4 backtest are
the only proofs of correctness):

  - difficulty() is imported canonical from engine.probs (Buchholz = Σ(opp.wins−opp.losses),
    NOT Σ opp.wins; ENG-03). There is NO second copy here.
  - Within-group ranking key is (−difficulty(t), t.seed): difficulty descending then
    initial seed ascending. The difficulty sort actually FEEDS the fold (ENG-04, Pitfall 3)
    — it is not dead code. In R2 difficulty is uniform within a group and the sort falls
    through to seed automatically; one path, no `if round == 2` (ENG-02).
  - PRIORITY_TABLE is Valve's verbatim 15-row rematch-resolution oracle for 6-team groups
    (RESEARCH "VERIFIED: Valve Swiss Rules"). Positions 1..6 index the difficulty-ranked
    group. Select the top-most row with no rematch (Pitfall 2 — a greedy-legal-but-wrong
    matching silently corrupts the branch).
  - On no rematch-free perfect matching, pair the least-disruptive rematch and
    log.warning(...) — NEVER crash on an unhandled None (ENG-05).
  - ``opps`` holds opponent OBJECTS (engine.probs.difficulty iterates o.wins − o.losses),
    so each team's opponent collection exposes .wins/.losses; the no-rematch check compares
    opponent .id.

Imports no streamlit/httpx/requests (functional-core / gate-ability invariant).
"""

from __future__ import annotations

import logging
from collections import defaultdict

from engine.probs import (  # canonical Buchholz + math (ENG-03)
    difficulty,
    series_prob,
)
from engine.teams import (
    ADVANCE_AT_WINS,
    ELIMINATE_AT_LOSSES,
    build_round1_pairs,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valve rematch-avoidance priority table (15 rows, groups of 6) — VERIFIED verbatim
# Source: ValveSoftware/counter-strike_rules_and_regs/major-supplemental-rulebook.md
# Positions 1..6 are the difficulty-ranked positions WITHIN the 6-team record group
# (1 = highest seed in group). Organizers "select the top-most row that does not result
# in a rematch."
# ---------------------------------------------------------------------------
PRIORITY_TABLE: list[list[tuple[int, int]]] = [
    [(1, 6), (2, 5), (3, 4)],
    [(1, 6), (2, 4), (3, 5)],
    [(1, 5), (2, 6), (3, 4)],
    [(1, 5), (2, 4), (3, 6)],
    [(1, 4), (2, 6), (3, 5)],
    [(1, 4), (2, 5), (3, 6)],
    [(1, 6), (2, 3), (4, 5)],
    [(1, 5), (2, 3), (4, 6)],
    [(1, 3), (2, 6), (4, 5)],
    [(1, 3), (2, 5), (4, 6)],
    [(1, 4), (2, 3), (5, 6)],
    [(1, 3), (2, 4), (5, 6)],
    [(1, 2), (3, 6), (4, 5)],
    [(1, 2), (3, 5), (4, 6)],
    [(1, 2), (3, 4), (5, 6)],
]


def rank_group(group):
    """Order a record group by Valve's within-stage tiebreak chain (ENG-02/04).

    Key = (−difficulty(t), t.seed): Difficulty Score descending, then initial seed
    ascending. SINGLE code path for all rounds >= 2 — in R2 every team's lone opponent
    sits at the mirror record so difficulty is uniform and the sort falls through to
    seed automatically (no `if round == 2`). The returned order is what the fold pairs
    on; if the difficulty term is removed the fold output changes (Pitfall 3 — the sort
    is load-bearing, not dead code).
    """
    return sorted(group, key=lambda t: (-difficulty(t), t.seed))


def _is_rematch(a, b) -> bool:
    """True iff a and b have already met this stage (their ids are in each other's opps)."""
    return b.id in {o.id for o in a.opps} or a.id in {o.id for o in b.opps}


def _fold_match(ranked):
    """Rematch-avoiding high-vs-low fold (HANDOFF §4).

    ``ranked[0]`` is the best seed in the group. Pair it against the lowest-ranked
    available non-rematch opponent (try worst-ranked first — the fold), then recurse on
    the remainder. Returns a list of (high, low) pairs, or None when no rematch-free
    perfect matching exists (handled by the caller's fallback; ENG-05).
    """
    if not ranked:
        return []
    first, rest = ranked[0], ranked[1:]
    for j in range(len(rest) - 1, -1, -1):  # try worst-ranked candidate first (fold)
        cand = rest[j]
        if _is_rematch(first, cand):
            continue
        sub = _fold_match(rest[:j] + rest[j + 1 :])
        if sub is not None:
            return [(first, cand), *sub]
    return None


def _pair_via_priority_table(ranked):
    """Resolve a 6-team group via Valve's verbatim 15-row priority table (GATE-03/04).

    ``ranked`` is the difficulty-ranked group (index 0 == group seed 1). Select the
    top-most row whose three pairings contain no rematch. Returns the list of pairs, or
    None if every row contains a rematch (caller falls back; ENG-05).
    """
    for row in PRIORITY_TABLE:  # top-most row first
        pairs = [(ranked[a - 1], ranked[b - 1]) for a, b in row]
        if all(not _is_rematch(x, y) for x, y in pairs):
            return pairs
    return None


def _least_disruptive_rematch(ranked):
    """Fallback when no rematch-free perfect matching exists (ENG-05, Pitfall ENG-05).

    Pair the least-disruptive rematch: highest-ranked team vs the lowest-ranked available
    opponent (allowing the rematch), then recurse. Never returns None — the engine must be
    total on an unbounded input rather than crashing on an unhandled None. Logs a warning
    because an unavoidable rematch means the input group is degenerate.
    """
    if not ranked:
        return []
    first, rest = ranked[0], ranked[1:]
    # Prefer a non-rematch partner if one exists at this level; else take the lowest-ranked
    # (worst) available, accepting the rematch (least disruptive: keeps top seeds stable).
    chosen = None
    for j in range(len(rest) - 1, -1, -1):
        if not _is_rematch(first, rest[j]):
            chosen = j
            break
    if chosen is None:
        chosen = len(rest) - 1  # lowest-ranked available; forced rematch
        log.warning(
            "no rematch-free pairing for group seed %s; pairing forced rematch %s vs %s",
            getattr(first, "seed", "?"),
            getattr(first, "id", "?"),
            getattr(rest[chosen], "id", "?"),
        )
    cand = rest[chosen]
    return [(first, cand), *_least_disruptive_rematch(rest[:chosen] + rest[chosen + 1 :])]


def pair_within_group(group):
    """Pair a single record group, rematch-avoiding, with graceful fallback.

    1. Rank the group (−difficulty, seed) — the difficulty sort feeds the fold (ENG-04).
    2. For 6-team groups, use Valve's verbatim priority-table oracle (GATE-03/04); for
       other sizes use the high-vs-low fold (the table's generalizing principle).
    3. On no rematch-free perfect matching (None), pair the least-disruptive rematch and
       warn — never crash (ENG-05).

    ``group`` may be passed pre-ranked or unranked; it is (re)ranked here so callers and
    tests can hand it either way.
    """
    ranked = rank_group(group)

    pairs = None
    if len(ranked) == 6:
        pairs = _pair_via_priority_table(ranked)
    if pairs is None:
        pairs = _fold_match(ranked)
    if pairs is None:
        log.warning(
            "no rematch-free perfect matching for a %d-team group; using least-disruptive rematch",
            len(ranked),
        )
        pairs = _least_disruptive_rematch(ranked)
    return pairs


# ---------------------------------------------------------------------------
# Full single-stage Valve Swiss simulator (ENG-06/07/08, MC-06)
# ---------------------------------------------------------------------------


def _is_bo3(a, b) -> bool:
    """A match is Bo3 iff a team is at 2 wins (advancement) OR 2 losses (elimination).

    Both teams in a record group share (wins, losses), so testing either side suffices
    (ENG-06). One step from termination in EITHER direction promotes the match to Bo3.
    """
    return (
        a.wins == ADVANCE_AT_WINS - 1
        or a.losses == ELIMINATE_AT_LOSSES - 1
        or b.wins == ADVANCE_AT_WINS - 1
        or b.losses == ELIMINATE_AT_LOSSES - 1
    )


def _play(a, b, ratings, S, rng, locked, *, market_overrides=None, all_bo3=False):
    """Resolve one match, returning (winner, loser). Mutates nothing.

    If frozenset({a.id, b.id}) is in ``locked``, the locked winner is used
    deterministically (no sampling; ENG-08) — a locked result is a known FACT and takes
    precedence over any market override. Otherwise a SINGLE Bernoulli draw against the
    series win prob decides it — the Bo3 closed form p^2(3-2p) is one draw, never three
    map samples (MC-06).

    ``market_overrides`` (keyword-only, the Phase-5 odds seam — default None = unchanged):
    ``dict[str, float]`` keyed by the id-bucket ``f"{min(a.id, b.id)}-{max(a.id, b.id)}"``
    carrying ``p`` = P(LOWER-id team wins the SERIES). CRITICAL ORIENTATION (T-05-ORIENT):
    this ``_play`` receives ``(a, b)`` in DIFFICULTY-RANKED (high, low) order from
    ``pair_within_group`` (NOT id-sorted), while ``p`` is stored relative to the LOWER id.
    So we look the override up by the id-bucket (NOT an arg-order tuple) and orient it to
    the FIRST arg via ``p_a = p if a.id < b.id else (1 - p)`` BEFORE drawing — assuming the
    arg order matches id order would silently invert the favorite on every (high-id,
    low-id) pair. The override flows through ``series_prob(market_series_prob=p_a)`` which
    is used DIRECTLY: series()/Bo3 is NOT re-applied (the market already prices the series,
    PROB-02).

    ``all_bo3`` (keyword-only, default False = unchanged; BO-01) forces Bo3 on the
    rating-fallback branch only: ``bo3=all_bo3 or _is_bo3(a, b)`` runs the match as Bo3 even
    when neither team is one step from termination (the Stage-3 all-Bo3 mode). A market
    override still bypasses Bo3 — series_prob returns market_series_prob directly regardless
    of bo3 (PROB-02), so all_bo3 never re-Bo3's a priced match.
    """
    key = frozenset((a.id, b.id))
    if key in locked:
        winner_id = locked[key]
        if winner_id == a.id:
            return a, b
        if winner_id == b.id:
            return b, a
        # Defensive: a locked key whose winner is neither participant is malformed
        # (T-02-01). Do not silently mis-apply it.
        raise ValueError(
            f"locked winner {winner_id!r} for {key} is not one of the paired teams "
            f"({a.id}, {b.id})"
        )

    ra = ratings.get(a.id, a.rating) if ratings else a.rating
    rb = ratings.get(b.id, b.rating) if ratings else b.rating

    market_p_a = None
    if market_overrides:
        bucket = f"{min(a.id, b.id)}-{max(a.id, b.id)}"
        p = market_overrides.get(bucket)
        if p is not None:
            # `p` = P(lower-id wins); orient to the FIRST arg `a` (which may be the higher
            # id — pair arrives difficulty-ranked, NOT id-sorted). T-05-ORIENT.
            market_p_a = p if a.id < b.id else (1.0 - p)

    # series_prob honors a market override DIRECTLY (Bo3 NOT re-applied, PROB-02); with no
    # override it falls back to series(p_map(...), bo3) — byte-identical to the prior path.
    p_a = series_prob(
        ra=ra, rb=rb, bo3=all_bo3 or _is_bo3(a, b), market_series_prob=market_p_a, S=S
    )  # P(a beats b), single draw
    if rng.random() < p_a:
        return a, b
    return b, a


def simulate_stage(teams, ratings, S, rng, locked, *, pairings_out=None, market_overrides=None, all_bo3=False):
    """Simulate one complete Valve Stage-1 Swiss and return {id: final Team}.

    ``teams`` are the (mutable) per-stage team objects — pass a FRESH ``load_teams()``
    per sim so state does not leak between runs. ``ratings`` is an optional
    ``{id: rating}`` override (None -> use each team's own .rating; the Phase-5/MC seam).
    ``S`` is the logistic spread (PROB-01). ``rng`` is an injected numpy Generator (the
    only randomness source). ``locked`` is ``dict[frozenset({id, id}) -> winner_id]``;
    a locked matchup uses its winner deterministically (no sampling) and is still recorded
    in ``opps`` so the no-rematch rule respects locked history (ENG-08, the Phase-4 seam).

    Round 1 uses the derived seed table (build_round1_pairs, NOT a re-fold; ENG-01).
    Rounds 2+ run a SINGLE code path: group active teams by (wins, losses), rank each
    group by (-difficulty, seed), pair via the priority-table/fold oracle, play, and
    record opponents — until every team is at 3 wins or 3 losses (ENG-02/04/07). No pair
    plays twice within a stage (the fold + priority table avoid rematches; locked history
    counts).

    Buchholz integrity: each round's pairings are computed for ALL groups from the
    standings as of the previous round, THEN every match is played. Computing a later
    group's difficulty after an earlier group already played this round would read
    mid-round (post-this-round) opponent records and corrupt the Buchholz seeding
    (GATE-01 regression — caught by the Budapest backtest). So: rank+pair first, play after.

    ``pairings_out`` (keyword-only, observability — default None = no behavior change):
    when a list is passed, the engine appends one entry per round, each a list of
    ``frozenset({a.id, b.id})`` for the pairings it GENERATED that round (Round 1 first).
    This is the exact shipped pairing path the GATE-01 backtest asserts against — it does
    not alter simulation results.

    ``market_overrides`` (keyword-only, the Phase-5 odds seam — default None = no behavior
    change): ``dict[str, float]`` keyed by the id-bucket ``f"{min,max}"`` carrying P(lower-id
    team wins the series) for the imminent round's KNOWN matchups; threaded straight to
    ``_play`` which orients it to the lower-id team and uses it directly (Bo3 NOT re-applied,
    PROB-02). Default None reproduces the rating-only path byte-identically (GATE-01).

    ``all_bo3`` (keyword-only, default False = byte-identical; BO-01): True runs the WHOLE
    stage as Bo3 (the Stage-3 mode) by forwarding to ``_play(..., all_bo3=all_bo3)``; the
    default False leaves every existing pairing/draw untouched (GATE-01).
    """
    by_id = {t.id: t for t in teams}

    def _record_match(a, b):
        winner, loser = _play(
            a, b, ratings, S, rng, locked, market_overrides=market_overrides, all_bo3=all_bo3
        )
        winner.wins += 1
        loser.losses += 1
        # opps holds opponent OBJECTS (difficulty() reads o.wins/o.losses); the no-rematch
        # check compares .id. Record both directions, including locked results.
        a.opps.add(b)
        b.opps.add(a)

    # Round 1: fixed seed pairings (seed i vs i+8), not a fold.
    r1_pairs = build_round1_pairs(teams)
    if pairings_out is not None:
        pairings_out.append([frozenset((a.id, b.id)) for a, b in r1_pairs])
    for a, b in r1_pairs:
        _record_match(a, b)

    # Rounds 2+: single code path until everyone terminates at 3W or 3L.
    while True:
        active = [
            t for t in teams if t.wins < ADVANCE_AT_WINS and t.losses < ELIMINATE_AT_LOSSES
        ]
        if not active:
            break
        groups: dict[tuple[int, int], list] = defaultdict(list)
        for t in active:
            groups[(t.wins, t.losses)].append(t)
        # Compute every group's pairings from start-of-round standings BEFORE playing any
        # (Buchholz integrity — see docstring). Then play them all.
        round_pairs = []
        for record, group in groups.items():
            round_pairs.extend(pair_within_group(group))
        if pairings_out is not None:
            pairings_out.append([frozenset((a.id, b.id)) for a, b in round_pairs])
        for a, b in round_pairs:
            _record_match(a, b)

    return by_id
