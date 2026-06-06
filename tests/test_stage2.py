"""Stage-2 structural-invariant tests — STG-02.

STG-02: "Stage 2 Swiss simulates via the FROZEN engine with Stage-2 teams; per-team
probs pass the same structural invariants (Sigma = 2/8/2) as Stage 1, no engine edit
required." These are pure BLACK-BOX assertions against the unchanged
``simulate_stage``/``run_mc`` path — the ONLY difference from ``test_mc.py`` is that the
teams come from ``load_stage("data/stage2.json")`` instead of ``load_teams()``. The whole
point of STG-02 is "different teams only": no engine source is imported or edited here, so
GATE-01 (``test_backtest_budapest_2025``) and the freeze (``test_load_teams_unchanged``)
hold by construction. (See data/stage2.json for the [INFERRED] Stage-2 fixture.)
"""

from __future__ import annotations

from engine.montecarlo import run_mc
from engine.teams import STAGE_SIZE, load_stage

STAGE2_PATH = "data/stage2.json"


def test_stage2_invariants():
    """STG-02 (mirrors MC-01/03): at N>=50k on the Stage-2 fixture, ΣP(3-0)≈2,
    ΣP(0-3)≈2, ΣP(advance)≈8 within ±0.05 — the SAME marginal invariants Stage 1
    passes, proving the FROZEN run_mc runs Stage-2 teams unchanged."""
    teams, _cfg = load_stage(STAGE2_PATH)
    N = 50000
    r = run_mc(teams=teams, ratings=None, S=40.0, N=N, locked={}, seed=2024)
    sum_30 = sum(c / N for c in r.counts_30.values())
    sum_03 = sum(c / N for c in r.counts_03.values())
    sum_adv = sum(c / N for c in r.counts_advance.values())
    assert abs(sum_30 - 2.0) <= 0.05
    assert abs(sum_03 - 2.0) <= 0.05
    assert abs(sum_adv - 8.0) <= 0.05


def test_stage2_per_sim_degenerate():
    """STG-02 (mirrors MC-04): every individual sim on the Stage-2 fixture has exactly
    2 teams at 3-0, 2 teams at 0-3, and 8 teams reaching 3 wins (advance) — the per-sim
    degenerate guarantee of the frozen simulate_stage, on Stage-2 teams."""
    teams, _cfg = load_stage(STAGE2_PATH)
    r = run_mc(teams=teams, ratings=None, S=40.0, N=500, locked={}, seed=7)
    assert len(r.sample) == 500
    # Each sim record is a per-team final (wins, losses); 16 teams.
    sim0 = r.sample[0]
    assert len(sim0) == STAGE_SIZE
    # Per sim: exactly 2 go 3-0, 2 go 0-3, 8 reach 3 wins (advance).
    for sim in r.sample:
        recs = list(sim.values()) if isinstance(sim, dict) else list(sim)
        assert sum(1 for w, l in recs if w == 3 and l == 0) == 2
        assert sum(1 for w, l in recs if l == 3 and w == 0) == 2
        assert sum(1 for w, l in recs if w == 3) == 8
