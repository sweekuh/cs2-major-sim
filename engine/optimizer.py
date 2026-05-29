"""Pick'Em optimizer (OPT-01..05) — the pure decision layer over the stored sim sample.

Reads a finished ``Result`` (the retained per-sim record ``sample`` — MC-04 — plus the
marginal tallies) and the team set, and produces BOTH recommended ballots, their P(>=5)
and E[correct], the differing picks, and the correlated-0-3-in-R1 warning. It **never
re-runs the MC** — the stored sample is the contract (ROADMAP Success Criterion 4;
``test_pge5_known_answer`` / ``test_greedy_is_e_correct_optimal``).

Imports no streamlit/httpx. R1-trap detection reuses ``engine.teams.build_round1_pairs``
(no seed re-derivation — sidesteps the GATE-01 seed blocker).

Format facts (HANDOFF §7 / PRD §"10 calls"): a ballot is 2 + 6 + 2 = 10 DISTINCT teams.
Scoring per simulated stage is exact-record: a 3-0 pick scores iff the record is exactly
(3, 0); an advance pick scores iff wins >= 3; a 0-3 pick scores iff the record is exactly
(0, 3). >=5 correct of 10 upgrades the coin, so P(>=5/10) is the "true coin odds".
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np

from engine.teams import ADVANCE_AT_WINS, ELIMINATE_AT_LOSSES, Team, build_round1_pairs

# Ballot shape (the 2/6/2 format) and the coin threshold.
N_PICK_30 = 2
N_PICK_ADV = 6
N_PICK_03 = 2
N_PICKS = N_PICK_30 + N_PICK_ADV + N_PICK_03  # 10
COIN_THRESHOLD = 5  # >=5 of 10 correct upgrades the coin (PRD)

# Strict-improvement epsilon for the hill-climb — guards float churn so equal-P(>=5) swaps
# do not loop forever (a swap must beat the incumbent by more than this to be accepted).
_EPS = 1e-12

# Bucket field names, in deterministic order (used by the hill-climb + diff).
_BUCKETS = ("picks_30", "picks_adv", "picks_03")
_BUCKET_LABEL = {"picks_30": "3-0", "picks_adv": "advance", "picks_03": "0-3"}
_BUCKET_SIZE = {"picks_30": N_PICK_30, "picks_adv": N_PICK_ADV, "picks_03": N_PICK_03}


@dataclass(frozen=True)
class Ballot:
    """A valid 2/6/2 Pick'Em ballot — exactly 2 exact-3-0 picks, 6 advance picks, 2 exact-0-3
    picks, all 10 team ids DISTINCT (OPT-03). Validated at construction; the engine never
    sees an invalid ballot. Pick fields are normalized to tuples so the ballot is hashable.
    """

    picks_30: tuple[int, ...]
    picks_adv: tuple[int, ...]
    picks_03: tuple[int, ...]

    def __post_init__(self) -> None:
        for field_name, size in _BUCKET_SIZE.items():
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
            got = len(getattr(self, field_name))
            if got != size:
                raise ValueError(
                    f"Ballot {field_name} must have exactly {size} picks, got {got}"
                )
        ids = self.all_ids
        if len(set(ids)) != len(ids):
            raise ValueError(f"a team appears in two ballot buckets: {ids}")

    @property
    def all_ids(self) -> tuple[int, ...]:
        return (*self.picks_30, *self.picks_adv, *self.picks_03)


def _top(prob: dict[int, float], k: int, exclude: set[int] | None = None) -> list[int]:
    """The ``k`` team ids with the highest ``prob``, excluding ``exclude``.

    Deterministic tie-break to the LOWER id so the same marginals always yield the same
    ballot (reproducibility across runs/machines).
    """
    excl = exclude or set()
    ranked = sorted((t for t in prob if t not in excl), key=lambda t: (-prob[t], t))
    return ranked[:k]


def ballot_a(
    p_30: dict[int, float],
    p_advance: dict[int, float],
    p_03: dict[int, float],
) -> Ballot:
    """Ballot A — the greedy per-bucket marginal baseline (OPT-01).

    Top 2 by P(3-0), top 2 by P(0-3) (excluding the 3-0 picks), top 6 by P(advance)
    (excluding all four already chosen); the advance bucket EXCLUDES the four already chosen
    so the ballot is valid 2/6/2 by construction (OPT-03).

    NOTE (Phase 3 V&V): this maximizes the sum of each bucket's marginals, but it is NOT the
    global E[correct] maximizer — the 3-0 and advance buckets compete for the same teams and
    Padv >= P30, so the true optimum spends the 3-0 slots on the smallest-(Padv-P30)-gap teams,
    not the highest-P(3-0). The two coincide for typical favorites (high P30 => also high Padv).
    Ballot A is kept as this transparent greedy baseline on purpose; the real recommendation is
    Ballot B, whose P(>=5) hill-climb includes re-bucketing moves and so can escape this gap.
    """
    picks_30 = _top(p_30, N_PICK_30)
    picks_03 = _top(p_03, N_PICK_03, exclude=set(picks_30))
    picks_adv = _top(p_advance, N_PICK_ADV, exclude=set(picks_30) | set(picks_03))
    return Ballot(tuple(picks_30), tuple(picks_adv), tuple(picks_03))


# Outcome matrices: dict[team_id -> np.ndarray[bool] of length N], one per pick criterion.
Matrices = tuple[dict[int, np.ndarray], dict[int, np.ndarray], dict[int, np.ndarray]]


def build_outcome_matrices(
    sample: list[dict[int, tuple[int, int]]], ids: list[int]
) -> Matrices:
    """Turn the stored per-sim ``sample`` into three boolean matrices (RESEARCH D3).

    ``is_30[tid]`` / ``is_adv[tid]`` / ``is_03[tid]`` are each a length-N boolean array:
    record exactly (3,0), wins >= 3, record exactly (0,3) respectively. One pass per team;
    every later P(>=5) eval is then a single vectorized reduce over N (so the hill-climb is
    cheap and the optimizer never touches the RNG).
    """
    is_30: dict[int, np.ndarray] = {}
    is_adv: dict[int, np.ndarray] = {}
    is_03: dict[int, np.ndarray] = {}
    for tid in ids:
        rec = np.array([s[tid] for s in sample], dtype=np.int16).reshape(-1, 2)
        wins, losses = rec[:, 0], rec[:, 1]
        is_30[tid] = (wins == ADVANCE_AT_WINS) & (losses == 0)
        is_adv[tid] = wins >= ADVANCE_AT_WINS
        is_03[tid] = (wins == 0) & (losses == ELIMINATE_AT_LOSSES)
    return is_30, is_adv, is_03


def marginals_from_matrices(
    matrices: Matrices,
) -> tuple[dict[int, float], dict[int, float], dict[int, float]]:
    """Per-team P(3-0)/P(advance)/P(0-3) straight off the sample matrices.

    Computed from the SAME sample the P(>=5) search scores against, so Ballot A's marginal
    ranking and Ballot B's P(>=5) are consistent (no divergence between counts and sample).
    """
    is_30, is_adv, is_03 = matrices
    p_30 = {tid: float(arr.mean()) for tid, arr in is_30.items()}
    p_adv = {tid: float(arr.mean()) for tid, arr in is_adv.items()}
    p_03 = {tid: float(arr.mean()) for tid, arr in is_03.items()}
    return p_30, p_adv, p_03


def p_ge5(ballot: Ballot, matrices: Matrices) -> float:
    """P(>=5/10) for ``ballot`` against the stored sample (OPT-04).

    Sum the 10 selected boolean rows per sim and return the fraction with >= COIN_THRESHOLD
    correct. Sample-only — never re-runs the MC.
    """
    is_30, is_adv, is_03 = matrices
    rows = (
        [is_30[t] for t in ballot.picks_30]
        + [is_adv[t] for t in ballot.picks_adv]
        + [is_03[t] for t in ballot.picks_03]
    )
    correct = np.sum(rows, axis=0)  # per-sim count of correct picks (0..10)
    return float(np.mean(correct >= COIN_THRESHOLD))


def e_correct(
    ballot: Ballot,
    p_30: dict[int, float],
    p_advance: dict[int, float],
    p_03: dict[int, float],
) -> float:
    """E[correct] — the linear sum of each slot's hit probability (the Ballot A objective)."""
    return (
        sum(p_30[t] for t in ballot.picks_30)
        + sum(p_advance[t] for t in ballot.picks_adv)
        + sum(p_03[t] for t in ballot.picks_03)
    )


def _swap(ballot: Ballot, bucket: str, out_id: int, in_id: int) -> Ballot:
    """Return a new Ballot with ``out_id`` replaced by ``in_id`` in ``bucket`` (size kept)."""
    new = {b: list(getattr(ballot, b)) for b in _BUCKETS}
    members = new[bucket]
    members[members.index(out_id)] = in_id
    return Ballot(new["picks_30"], new["picks_adv"], new["picks_03"])


def _rebucket(ballot: Ballot, b1: str, t1: int, b2: str, t2: int) -> Ballot:
    """Return a new Ballot with picked teams ``t1`` (in ``b1``) and ``t2`` (in ``b2``) swapping
    buckets. Same 10 teams, bucket sizes preserved — only the assignment changes."""
    new = {b: list(getattr(ballot, b)) for b in _BUCKETS}
    new[b1][new[b1].index(t1)] = t2
    new[b2][new[b2].index(t2)] = t1
    return Ballot(new["picks_30"], new["picks_adv"], new["picks_03"])


def _neighbors(ballot: Ballot, candidate_ids: list[int]) -> Iterator[Ballot]:
    """Deterministically yield the hill-climb neighborhood of ``ballot`` (OPT-02).

    Two move families, both size-preserving so every neighbor is a valid 2/6/2 ballot:
      (a) replace one PICKED team in a bucket with one UNPICKED team (changes which teams), and
      (b) exchange the buckets of two already-PICKED teams in different buckets (re-buckets the
          same 10 teams). Family (b) is what lets Ballot B escape Ballot A's marginal-greedy
          blind spot (Phase 3 V&V Finding 1/2) — e.g. demote a high-Padv advance pick that was
          forced into the 3-0 slot. Sorted iteration keeps the climb reproducible.
    """
    chosen = set(ballot.all_ids)
    cands = sorted(t for t in candidate_ids if t not in chosen)
    for bucket in _BUCKETS:  # (a) picked <-> unpicked, same bucket
        for out_id in sorted(getattr(ballot, bucket)):
            for in_id in cands:
                yield _swap(ballot, bucket, out_id, in_id)
    for i in range(len(_BUCKETS)):  # (b) re-bucket two picked teams
        for j in range(i + 1, len(_BUCKETS)):
            b1, b2 = _BUCKETS[i], _BUCKETS[j]
            for t1 in sorted(getattr(ballot, b1)):
                for t2 in sorted(getattr(ballot, b2)):
                    yield _rebucket(ballot, b1, t1, b2, t2)


def ballot_b(seed_ballot: Ballot, matrices: Matrices, candidate_ids: list[int]) -> Ballot:
    """Ballot B — P(>=5)-optimal via hill-climb (OPT-02).

    Seeded from Ballot A. Each pass evaluates the full ``_neighbors`` set — single picked<->
    unpicked swaps AND re-bucketing exchanges of two picked teams — and applies the single best
    STRICTLY-improving move; iterate to a local optimum. NO brute-force enumeration of the ~10M
    ballots (HANDOFF §7). Deterministic: neighbors are generated in sorted order and ties never
    displace the incumbent, so the same sample yields the same Ballot B every run. The
    correlated-0-3-in-R1 trap is avoided automatically — the joint sample makes P(both 0-3) ~ 0,
    so keeping both never maximizes P(>=5) (OPT-05). Including the re-bucketing moves lets B
    reach P(>=5) optima that re-assign Ballot A's own picks across buckets (V&V Finding 2).
    """
    best = seed_ballot
    best_score = p_ge5(best, matrices)
    improved = True
    while improved:
        improved = False
        move_best = best
        move_score = best_score
        for neighbor in _neighbors(best, candidate_ids):
            score = p_ge5(neighbor, matrices)
            if score > move_score + _EPS:
                move_best, move_score = neighbor, score
        if move_best is not best:
            best, best_score, improved = move_best, move_score, True
    return best


def correlated_03_in_r1(
    ballot: Ballot, teams: list[Team]
) -> tuple[int, int] | None:
    """Return the two 0-3 pick ids if they MEET in Round 1, else None (OPT-05).

    Two teams that meet in R1 cannot both go 0-3 (one wins), so picking both caps that
    bucket at 1 correct and drags P(>=5) down. R1 pairings are reused from
    ``engine.teams.build_round1_pairs`` (no seed re-derivation). Reported for Ballot A,
    which is correlation-blind and CAN fall into the trap; Ballot B avoids it for free.
    """
    r1 = {frozenset((a.id, b.id)) for a, b in build_round1_pairs(teams)}
    if frozenset(ballot.picks_03) in r1:
        return tuple(sorted(ballot.picks_03))  # type: ignore[return-value]
    return None


def _assign(ballot: Ballot) -> dict[int, str]:
    """team_id -> bucket label ('3-0' / 'advance' / '0-3') for diffing two ballots."""
    out: dict[int, str] = {}
    for bucket in _BUCKETS:
        for tid in getattr(ballot, bucket):
            out[tid] = _BUCKET_LABEL[bucket]
    return out


def ballot_diff(a: Ballot, b: Ballot) -> tuple[int, ...]:
    """Team ids whose bucket assignment differs between Ballot A and Ballot B (OPT-03).

    A team picked in one ballot but not the other, or moved to a different bucket, differs.
    Sorted for determinism — the UI highlights exactly these.
    """
    aa, ba = _assign(a), _assign(b)
    everyone = set(aa) | set(ba)
    return tuple(sorted(t for t in everyone if aa.get(t) != ba.get(t)))


@dataclass(frozen=True)
class OptimizerOutput:
    """Everything the UI needs from one Run (sample-only; no MC re-run)."""

    ballot_a: Ballot
    ballot_b: Ballot
    pge5_a: float
    pge5_b: float
    e_correct_a: float
    e_correct_b: float
    recommended: Ballot  # = ballot_b (the P(>=5)-optimal one)
    recommended_pge5: float  # the hero number (OPT-04)
    diff: tuple[int, ...]  # team ids that differ A vs B (OPT-03)
    warning: tuple[int, int] | None  # the Ballot-A correlated 0-3-in-R1 pair, or None (OPT-05)


def optimize(result, teams: list[Team]) -> OptimizerOutput:
    """Recommend both ballots + coin odds + warning from a finished ``Result`` (OPT-01..05).

    Pure function of (Result.sample, teams) — reads the stored sample only and NEVER calls
    the MC (ROADMAP SC4). Marginals are taken from the sample matrices so Ballot A's ranking
    and Ballot B's P(>=5) score the same distribution.
    """
    ids = [t.id for t in teams]
    matrices = build_outcome_matrices(result.sample, ids)
    p_30, p_adv, p_03 = marginals_from_matrices(matrices)

    a = ballot_a(p_30, p_adv, p_03)
    b = ballot_b(a, matrices, ids)
    pge5_b = p_ge5(b, matrices)
    return OptimizerOutput(
        ballot_a=a,
        ballot_b=b,
        pge5_a=p_ge5(a, matrices),
        pge5_b=pge5_b,
        e_correct_a=e_correct(a, p_30, p_adv, p_03),
        e_correct_b=e_correct(b, p_30, p_adv, p_03),
        recommended=b,
        recommended_pge5=pge5_b,
        diff=ballot_diff(a, b),
        warning=correlated_03_in_r1(a, teams),
    )
