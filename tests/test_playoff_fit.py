"""Champion-futures calibration tests (PLAY-04) — determinism, convergence, gauge, fail-loud."""

from __future__ import annotations

import pytest

from engine.bracket import run_playoff_mc
from engine.playoff_fit import fit_champion_ratings
from engine.teams import Team


def _teams(ratings: dict[int, float] | None = None) -> list[Team]:
    ratings = ratings or {i: 50.0 for i in range(1, 9)}
    return [Team(id=i, name=f"T{i}", seed=i, rating=ratings[i]) for i in range(1, 9)]


def _target() -> dict[int, float]:
    # A valid champion distribution (sums to 1.0) with a clear favorite.
    return {1: 0.30, 2: 0.05, 3: 0.04, 4: 0.12, 5: 0.40, 6: 0.03, 7: 0.02, 8: 0.04}


def test_fit_is_deterministic():
    teams = _teams()
    a, da = fit_champion_ratings(teams, 40.0, _target(), n_per_iter=4000, max_iters=12, seed=3)
    b, db = fit_champion_ratings(teams, 40.0, _target(), n_per_iter=4000, max_iters=12, seed=3)
    assert a == b
    assert da == db


def test_fit_pins_the_gauge_anchor():
    # The top seed (min id == 1) keeps its base rating; only differences move.
    teams = _teams({i: 50.0 for i in range(1, 9)})
    fitted, _ = fit_champion_ratings(teams, 40.0, _target(), n_per_iter=4000, max_iters=10, seed=1)
    assert fitted[1] == pytest.approx(50.0)


def test_fit_reproduces_the_target_champion_distribution():
    teams = _teams()
    target = _target()
    fitted, diag = fit_champion_ratings(teams, 40.0, target, n_per_iter=20000, max_iters=40, seed=7)
    assert diag["converged"], diag
    # The bracket sim under the fitted ratings reproduces the target within a tolerance.
    res = run_playoff_mc(teams, fitted, 40.0, 60000, seed=11)
    pc = res.p_champ()
    for tid, t in target.items():
        assert pc[tid] == pytest.approx(t, abs=0.03)
    # The favorite (id 5, target 0.40) ends with the highest rating and highest title odds.
    assert max(fitted, key=fitted.get) == 5
    assert max(pc, key=pc.get) == 5


def test_fit_validates_targets_fail_loud():
    teams = _teams()
    # Missing an id -> raise.
    with pytest.raises(ValueError):
        fit_champion_ratings(teams, 40.0, {i: 0.125 for i in range(1, 8)}, n_per_iter=1000)
    # A probability out of (0,1) -> raise.
    bad = {**_target(), 1: 1.4, 5: -0.4}
    with pytest.raises(ValueError):
        fit_champion_ratings(teams, 40.0, bad, n_per_iter=1000)
    # A sum far from 1.0 (all 0.5 -> sum 4.0) -> raise (structurally garbage).
    with pytest.raises(ValueError):
        fit_champion_ratings(teams, 40.0, {i: 0.5 for i in range(1, 9)}, n_per_iter=1000)


def test_committed_playoff_ratings_reproduce_market_champion_view():
    """The shipped data/playoffs.json ratings are champion-futures-calibrated (PLAY-04): the bracket
    sim must put Vitality the clear favorite and Spirit a clear second, matching the market futures —
    a revert-proof guard that a ratings edit can't silently de-calibrate the title race."""
    from engine.bracket import bo_from_stage_cfg
    from engine.teams import load_stage

    teams, cfg = load_stage("data/playoffs.json")
    res = run_playoff_mc(teams, None, 40.0, 40000, seed=20260616, bo=bo_from_stage_cfg(cfg))
    pc = res.p_champ()
    by_name = {t.name: pc[t.id] for t in teams}
    # Vitality the favorite (~0.5), Spirit a clear second (~0.25), both well clear of the field.
    assert by_name["Vitality"] == max(by_name.values())
    assert by_name["Vitality"] > 0.40
    assert by_name["Spirit"] > 0.18
    assert by_name["Spirit"] == sorted(by_name.values())[-2]  # second-highest
    # The 3-2 seeds (G2/BetBoom/9z) are clear longshots.
    for name in ("G2", "BetBoom", "9z"):
        assert by_name[name] < 0.05
