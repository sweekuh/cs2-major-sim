"""Playoff Pick'Em optimizer (PLAY-02) — the 7-pick round-weighted ballot over the bracket sample.

This is the playoffs analog of ``engine.optimizer`` and MUST NOT reuse the Swiss 2/6/2 scheme
(TODOS #3 / ROADMAP v4): the playoff Pick'Em is a different scoring model. A ballot is a full
champion-path BRACKET prediction — the winners of all 7 matches:

    4 quarterfinal winners + 2 semifinal winners + 1 grand-final winner (the champion),

with the bracket-consistency constraint that each semifinal pick is one of that half's two
quarterfinal picks, and the champion is one of the two semifinal picks. That is exactly the
shape an in-game bracket Pick'Em submits (TODOS #3: "2 Quarterfinal + 1 Semifinal + 1 Grand
Final correct picks, per the in-game achievements").

Two scored quantities, mirroring the Swiss optimizer's E[correct] / P(>=5) pair:

  - **E[points]** — the round-weighted expected score: each correct QF pick is worth
    ``W_QF``, each correct SF pick ``W_SF``, the champion ``W_GF`` (later rounds weigh more).
    The ``ballot_points`` ballot maximizes this and is the RECOMMENDATION (the headline
    objective — chosen because it rewards every correct pick, not only an all-or-nothing coin).
  - **P(coin)** — the probability of unlocking the achievement tiers jointly: at least
    ``TIER_QF`` quarterfinal picks correct AND at least ``TIER_SF`` semifinal picks correct AND
    the champion correct. The ``ballot_coin`` ballot maximizes this; it is reported as the
    alternative (and the recommended ballot's own coin/tier odds are reported alongside).

The whole valid-ballot space is tiny — 2^4 QF choices x 2 SF x 2 SF x 2 champion = **128**
consistent brackets — so we ENUMERATE all of them and take the exact optimum for each objective
(no hill-climb needed, unlike the ~10M-ballot Swiss space). Sample-only: scores read the retained
``PlayoffResult.sample`` and NEVER re-run the bracket MC. Imports no streamlit/httpx.

The point weights and achievement tiers are [INFERRED] defaults (editable) — the exact in-game
values were not pinned in the rulebook; getting the relative ordering right (QF < SF < GF;
tiers 2/1/1) is what matters and matches the documented achievement description.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.bracket import QF_LABELS, QF_SEEDS, SF_LABELS
from engine.teams import Team

# Round weights (later rounds weigh more) — [INFERRED] editable defaults (PLAY-02).
W_QF = 1.0
W_SF = 2.0
W_GF = 3.0

# Achievement tiers — "2 Quarterfinal + 1 Semifinal + 1 Grand Final" (TODOS #3). The coin is
# unlocked when ALL THREE hold jointly in a sim.
TIER_QF = 2
TIER_SF = 1
TIER_GF = 1


@dataclass(frozen=True)
class PlayoffBallot:
    """A bracket-consistent 7-pick prediction (PLAY-02).

    ``qf`` are the predicted winners of QF1..QF4 (in ``engine.bracket.QF_LABELS`` order); ``sf``
    are the predicted winners of SF1, SF2; ``champion`` is the predicted title winner. Validated at
    construction: each SF pick is one of its half's two QF picks, the champion is one of the SF
    picks — so the engine never sees an inconsistent bracket.
    """

    qf: tuple[int, int, int, int]
    sf: tuple[int, int]
    champion: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "qf", tuple(self.qf))
        object.__setattr__(self, "sf", tuple(self.sf))
        if len(self.qf) != 4:
            raise ValueError(f"qf must have exactly 4 picks, got {len(self.qf)}")
        if len(self.sf) != 2:
            raise ValueError(f"sf must have exactly 2 picks, got {len(self.sf)}")
        # SF1 from QF1/QF2 picks, SF2 from QF3/QF4 picks (the bracket-consistency constraint).
        if self.sf[0] not in (self.qf[0], self.qf[1]):
            raise ValueError(f"SF1 pick {self.sf[0]} is not a QF1/QF2 pick {self.qf[:2]}")
        if self.sf[1] not in (self.qf[2], self.qf[3]):
            raise ValueError(f"SF2 pick {self.sf[1]} is not a QF3/QF4 pick {self.qf[2:]}")
        if self.champion not in self.sf:
            raise ValueError(f"champion {self.champion} is not an SF pick {self.sf}")

    def picks_by_label(self) -> dict[str, int]:
        """``{match_label: predicted_winner_id}`` for all 7 matches (QF1..GF)."""
        d = {label: self.qf[i] for i, label in enumerate(QF_LABELS)}
        d.update({label: self.sf[i] for i, label in enumerate(SF_LABELS)})
        d["GF"] = self.champion
        return d


def _qf_options(teams: list[Team]) -> dict[str, tuple[int, int]]:
    """Per-quarterfinal candidate winner ids ``(top_seed_id, bottom_seed_id)`` from the seeds.

    Top-seed id first so the enumeration explores favorites first and ties break toward the
    higher seed (deterministic). Raises if the fixture is not a clean seeds-1..8 bracket.
    """
    by_seed = {t.seed: t.id for t in teams}
    if set(by_seed) != set(range(1, 9)):
        raise ValueError(f"playoff bracket needs exactly seeds 1..8, got {sorted(by_seed)}")
    return {label: (by_seed[sa], by_seed[sb]) for label, (sa, sb) in QF_SEEDS.items()}


def enumerate_ballots(teams: list[Team]) -> list[PlayoffBallot]:
    """All 128 bracket-consistent ballots for the 8-seed fixture (deterministic order)."""
    opt = _qf_options(teams)
    o1, o2, o3, o4 = opt["QF1"], opt["QF2"], opt["QF3"], opt["QF4"]
    ballots: list[PlayoffBallot] = []
    for qf1 in o1:
        for qf2 in o2:
            for qf3 in o3:
                for qf4 in o4:
                    for sf1 in (qf1, qf2):  # SF1 winner ∈ top-half QF picks
                        for sf2 in (qf3, qf4):  # SF2 winner ∈ bottom-half QF picks
                            for champ in (sf1, sf2):
                                ballots.append(
                                    PlayoffBallot((qf1, qf2, qf3, qf4), (sf1, sf2), champ)
                                )
    return ballots


def build_win_matrices(
    sample: list[dict[str, int]], ids: list[int]
) -> dict[str, dict[int, np.ndarray]]:
    """Per (match_label, team_id) boolean array: did that team WIN that match in each sim.

    One pass over the sample; every later ballot score is then a vectorized reduce over N. Keyed
    by all 7 labels x all 8 ids so any of the 128 ballots scores against the same matrices.
    """
    labels = (*QF_LABELS, *SF_LABELS, "GF")
    arrays: dict[str, dict[int, np.ndarray]] = {}
    winners_by_label = {
        label: np.array([s[label] for s in sample], dtype=np.int64) for label in labels
    }
    for label in labels:
        col = winners_by_label[label]
        arrays[label] = {tid: (col == tid) for tid in ids}
    return arrays


def _marginals(matrices: dict[str, dict[int, np.ndarray]]) -> dict[str, dict[int, float]]:
    """P(team wins match) per (label, id) — the linear E[points] inputs."""
    return {
        label: {tid: float(arr.mean()) for tid, arr in by_id.items()}
        for label, by_id in matrices.items()
    }


def e_points(
    ballot: PlayoffBallot,
    marginals: dict[str, dict[int, float]],
    *,
    w_qf: float = W_QF,
    w_sf: float = W_SF,
    w_gf: float = W_GF,
) -> float:
    """Round-weighted expected score of ``ballot`` against the per-match marginals.

    ``sum_QF w_qf P(pick wins QF) + sum_SF w_sf P(pick wins SF) + w_gf P(champion wins GF)``. The
    SF/GF marginals already require the pick to have won the earlier rounds (the actual SF winner
    in a sim won its QF), so this is the true expected weighted points — no double counting.
    """
    picks = ballot.picks_by_label()
    total = 0.0
    for label in QF_LABELS:
        total += w_qf * marginals[label][picks[label]]
    for label in SF_LABELS:
        total += w_sf * marginals[label][picks[label]]
    total += w_gf * marginals["GF"][picks["GF"]]
    return total


def _per_sim_correct(
    ballot: PlayoffBallot, matrices: dict[str, dict[int, np.ndarray]]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-sim (qf_correct, sf_correct, gf_correct) counts for ``ballot`` (vectorized)."""
    picks = ballot.picks_by_label()
    qf_correct = sum(matrices[label][picks[label]] for label in QF_LABELS)
    sf_correct = sum(matrices[label][picks[label]] for label in SF_LABELS)
    gf_correct = matrices["GF"][picks["GF"]].astype(np.int64)
    return np.asarray(qf_correct, dtype=np.int64), np.asarray(sf_correct, dtype=np.int64), gf_correct


def p_coin(
    ballot: PlayoffBallot,
    matrices: dict[str, dict[int, np.ndarray]],
    *,
    tier_qf: int = TIER_QF,
    tier_sf: int = TIER_SF,
    tier_gf: int = TIER_GF,
) -> float:
    """P(achievement coin) — P(>= tier_qf QF AND >= tier_sf SF AND >= tier_gf GF correct), joint over sims."""
    qf_c, sf_c, gf_c = _per_sim_correct(ballot, matrices)
    coin = (qf_c >= tier_qf) & (sf_c >= tier_sf) & (gf_c >= tier_gf)
    return float(np.mean(coin)) if coin.size else 0.0


def _tier_probs(
    ballot: PlayoffBallot, matrices: dict[str, dict[int, np.ndarray]]
) -> tuple[float, float, float]:
    """Marginal P(>=2 QF correct), P(>=1 SF correct), P(champion correct) for the breakdown view."""
    qf_c, sf_c, gf_c = _per_sim_correct(ballot, matrices)
    n = qf_c.size or 1
    return (
        float(np.mean(qf_c >= TIER_QF)),
        float(np.mean(sf_c >= TIER_SF)),
        float(np.sum(gf_c) / n),
    )


@dataclass(frozen=True)
class PlayoffOptimizerOutput:
    """Everything the UI needs from one playoff Run (sample-only; no MC re-run).

    ``ballot_points`` (E[points]-optimal) is the RECOMMENDATION; ``ballot_coin`` (P(coin)-optimal)
    is the reported alternative. ``recommended`` aliases ``ballot_points`` and ``recommended_*``
    carry that ballot's stats (its expected score is the hero number; its coin/tier odds are the
    secondary line)."""

    ballot_points: PlayoffBallot  # E[points]-optimal — THE RECOMMENDATION
    ballot_coin: PlayoffBallot  # P(coin)-optimal — the alternative
    e_points_points: float  # E[points] of the points ballot (the maximum E[points])
    e_points_coin: float  # E[points] of the coin ballot
    pcoin_points: float  # P(coin) of the points ballot
    pcoin_coin: float  # P(coin) of the coin ballot (the maximum P(coin))
    max_points: float  # 4*w_qf + 2*w_sf + w_gf — the perfect-bracket score (for the % display)
    recommended: PlayoffBallot  # = ballot_points
    recommended_e_points: float  # = e_points_points (the hero number)
    recommended_pcoin: float  # = pcoin_points (the recommended ballot's coin odds, secondary)
    # Tier breakdown for the RECOMMENDED (points) ballot: P(>=2 QF), P(>=1 SF), P(champion).
    tier_qf: float
    tier_sf: float
    tier_gf: float
    champion: int  # the recommended champion id
    p_champion: float  # P(that champion wins the title)
    diff: tuple[str, ...]  # match labels where the two ballots disagree


def _ballot_diff(a: PlayoffBallot, b: PlayoffBallot) -> tuple[str, ...]:
    """Match labels whose predicted winner differs between the two ballots (sorted by MATCH_ORDER)."""
    pa, pb = a.picks_by_label(), b.picks_by_label()
    order = (*QF_LABELS, *SF_LABELS, "GF")
    return tuple(label for label in order if pa[label] != pb[label])


def optimize_playoffs(
    result,
    teams: list[Team],
    *,
    w_qf: float = W_QF,
    w_sf: float = W_SF,
    w_gf: float = W_GF,
) -> PlayoffOptimizerOutput:
    """Recommend the playoff ballots from a finished ``PlayoffResult``.

    Pure function of (result.sample, teams): enumerates the 128 consistent brackets, scores each for
    E[points] and P(coin), and returns the E[points]-optimal ballot as the RECOMMENDATION (with its
    own coin/tier breakdown + champion) plus the P(coin)-optimal ballot as the alternative. NEVER
    re-runs the bracket MC — it reads the retained sample only. Deterministic: ballots are enumerated
    in a fixed order and only a STRICT improvement displaces the incumbent, so ties break toward the
    favorites-first ballot.
    """
    ids = [t.id for t in teams]
    matrices = build_win_matrices(result.sample, ids)
    marginals = _marginals(matrices)
    ballots = enumerate_ballots(teams)

    best_points, best_points_val = None, float("-inf")
    best_coin, best_coin_val = None, float("-inf")
    for b in ballots:
        ep = e_points(b, marginals, w_qf=w_qf, w_sf=w_sf, w_gf=w_gf)
        if ep > best_points_val:
            best_points, best_points_val = b, ep
        pc = p_coin(b, matrices)
        if pc > best_coin_val:
            best_coin, best_coin_val = b, pc

    assert best_points is not None and best_coin is not None  # 128 ballots — always non-empty
    # The RECOMMENDED ballot is the E[points]-optimal one; report ITS coin/tier odds + champion.
    pcoin_points = p_coin(best_points, matrices)
    tier_qf, tier_sf, tier_gf = _tier_probs(best_points, matrices)
    max_points = 4 * w_qf + 2 * w_sf + w_gf  # perfect bracket: 4 QF + 2 SF + champion
    return PlayoffOptimizerOutput(
        ballot_points=best_points,
        ballot_coin=best_coin,
        e_points_points=best_points_val,
        e_points_coin=e_points(best_coin, marginals, w_qf=w_qf, w_sf=w_sf, w_gf=w_gf),
        pcoin_points=pcoin_points,
        pcoin_coin=best_coin_val,
        max_points=max_points,
        recommended=best_points,
        recommended_e_points=best_points_val,
        recommended_pcoin=pcoin_points,
        tier_qf=tier_qf,
        tier_sf=tier_sf,
        tier_gf=tier_gf,
        champion=best_points.champion,
        p_champion=marginals["GF"][best_points.champion],
        diff=_ballot_diff(best_points, best_coin),
    )
