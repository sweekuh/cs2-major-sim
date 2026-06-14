"""Single-elimination knockout simulation (Phase 1).

Takes the 32 qualifiers in seed order (best first) and plays a standard single-elimination
bracket. Each tie is one sampled scoreline; a draw after 90'+ET is resolved as a ~50/50 shootout
(the well-supported "shootouts are ≈ coin flips" finding). Stage codes record how far each team got:

    1 = Round of 32 (eliminated there)   4 = Semi-final
    2 = Round of 16                       5 = Final (runner-up)
    3 = Quarter-final                     6 = Champion

NOTE: the real 2026 bracket uses a fixed slot table (and a specific best-third assignment); this
seeds purely by strength order, which keeps champion/deep-run odds sensible but is a documented
simplification of the exact bracket geometry.
"""

from __future__ import annotations

import numpy as np

from engine.soccer.dixon_coles import MatchModel, expected_goals, sample_score


def standard_seeding(n: int) -> list[int]:
    """Standard tournament seed order for a power-of-two ``n`` (so seed 1 meets seed 2 in the final)."""
    seeds = [1]
    while len(seeds) < n:
        m = len(seeds) * 2
        nxt: list[int] = []
        for s in seeds:
            nxt.append(s)
            nxt.append(m + 1 - s)
        seeds = nxt
    return seeds


def play_match(home: int, away: int, model: MatchModel, rng: np.random.Generator) -> int:
    """Play one knockout tie (neutral venue); return the winner id. Draws -> ~50/50 shootout."""
    lam_h, lam_a = expected_goals(model, home, away, neutral=True)
    hg, ag = sample_score(lam_h, lam_a, rng, rho=model.rho)
    if hg > ag:
        return home
    if ag > hg:
        return away
    return home if rng.random() < 0.5 else away


def simulate_knockout(seeded_ids: list[int], model: MatchModel,
                      rng: np.random.Generator) -> tuple[dict[int, int], int]:
    """Run the bracket from 32 seeded ids. Returns ({team_id: stage_reached}, champion_id).

    ``seeded_ids`` is best-first (index 0 = top seed); it is arranged into standard bracket order
    so the first-round pairs are adjacent and the two best seeds can only meet in the final.
    """
    order = standard_seeding(len(seeded_ids))
    current = [seeded_ids[s - 1] for s in order]
    stage = {tid: 1 for tid in seeded_ids}  # everyone reaches at least the first round they enter
    round_num = 1
    while len(current) > 1:
        winners: list[int] = []
        for i in range(0, len(current), 2):
            w = play_match(current[i], current[i + 1], model, rng)
            winners.append(w)
            stage[w] = round_num + 1  # survivor reached the next round
        current = winners
        round_num += 1
    return stage, current[0]
