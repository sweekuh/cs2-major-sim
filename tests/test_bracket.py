"""Playoff bracket engine tests (PLAY-01) — structure, MC invariants, determinism, locks."""

from __future__ import annotations

import numpy as np
import pytest

from engine.bracket import (
    DEFAULT_BO,
    GF_FEEDERS,
    QF_SEEDS,
    SF_FEEDERS,
    bo_from_stage_cfg,
    run_playoff_mc,
    simulate_bracket,
)
from engine.probs import series, series_best_of
from engine.teams import Team


def _teams(ratings: dict[int, float] | None = None) -> list[Team]:
    """8 seed-ordered playoff teams; default equal ratings (pure coinflips)."""
    ratings = ratings or {i: 50.0 for i in range(1, 9)}
    return [Team(id=i, name=f"T{i}", seed=i, rating=ratings[i]) for i in range(1, 9)]


# --- series_best_of (the Bo5 closed form, new sibling of the frozen series) ---------------
def test_series_best_of_matches_frozen_bo3():
    for p in (0.0, 0.3, 0.5, 0.6, 0.75, 1.0):
        assert series_best_of(p, 3) == pytest.approx(series(p, bo3=True))


def test_series_best_of_bo1_is_identity():
    for p in (0.1, 0.5, 0.9):
        assert series_best_of(p, 1) == pytest.approx(p)


def test_series_best_of_bo5_closed_form_and_monotonic():
    # p^3 (1 + 3q + 6q^2), q = 1-p — fair series at p=0.5, favorite amplified.
    assert series_best_of(0.5, 5) == pytest.approx(0.5)
    assert series_best_of(1.0, 5) == pytest.approx(1.0)
    assert series_best_of(0.0, 5) == pytest.approx(0.0)
    # A Bo5 is MORE favorite-amplifying than a Bo3 for p>0.5 (best-of-more favors the stronger side).
    assert series_best_of(0.6, 5) > series_best_of(0.6, 3) > 0.6


def test_series_best_of_rejects_even_or_nonpositive():
    for bad in (0, 2, 4, -1):
        with pytest.raises(ValueError):
            series_best_of(0.5, bad)


# --- bracket structure --------------------------------------------------------------------
def test_qf_seeds_are_the_canonical_major_pairing():
    # 1v8, 4v5, 2v7, 3v6 — the standard seeding so seeds 1 and 2 are in opposite halves.
    assert QF_SEEDS == {"QF1": (1, 8), "QF2": (4, 5), "QF3": (2, 7), "QF4": (3, 6)}
    # Top half (QF1, QF2) -> SF1; bottom half (QF3, QF4) -> SF2; final between the halves.
    assert SF_FEEDERS == {"SF1": ("QF1", "QF2"), "SF2": ("QF3", "QF4")}
    assert GF_FEEDERS == ("SF1", "SF2")


def test_bo_from_stage_cfg_reads_per_round_lengths():
    assert bo_from_stage_cfg({"qf_bo": 3, "sf_bo": 3, "gf_bo": 5}) == {"qf": 3, "sf": 3, "gf": 5}
    assert bo_from_stage_cfg(None) == DEFAULT_BO  # missing -> Bo3/Bo3/Bo5 default
    assert bo_from_stage_cfg({"gf_bo": 7})["gf"] == 7


def test_simulate_bracket_returns_all_match_winners():
    rng = np.random.default_rng(0)
    winners = simulate_bracket(_teams(), None, 40.0, rng)
    assert set(winners) == {"QF1", "QF2", "QF3", "QF4", "SF1", "SF2", "GF"}
    # The champion (GF winner) reached the final and a semifinal — bracket consistency.
    assert winners["GF"] in (winners["SF1"], winners["SF2"])
    assert winners["SF1"] in (winners["QF1"], winners["QF2"])
    assert winners["SF2"] in (winners["QF3"], winners["QF4"])


def test_simulate_bracket_rejects_wrong_seed_set():
    bad = [Team(id=i, name=f"T{i}", seed=i, rating=50.0) for i in range(1, 8)]  # only 7
    with pytest.raises(ValueError):
        simulate_bracket(bad, None, 40.0, np.random.default_rng(0))


# --- MC marginals + invariants ------------------------------------------------------------
def test_playoff_mc_marginals_sum_to_slot_counts():
    res = run_playoff_mc(_teams(), None, 40.0, 5000, seed=7)
    assert sum(res.p_sf().values()) == pytest.approx(4.0)  # 4 semifinal slots
    assert sum(res.p_gf().values()) == pytest.approx(2.0)  # 2 finalist slots
    assert sum(res.p_champ().values()) == pytest.approx(1.0)  # one champion


def test_playoff_mc_equal_ratings_is_symmetric():
    # All-50 ratings, Bo3 everywhere: every team's P(reach SF) is its single-match coinflip = 0.5.
    res = run_playoff_mc(_teams(), None, 40.0, 40000, seed=3, bo={"qf": 3, "sf": 3, "gf": 5})
    for tid in range(1, 9):
        assert res.p_sf()[tid] == pytest.approx(0.5, abs=0.02)
    # Champion is uniform-ish across 8 equal teams.
    for tid in range(1, 9):
        assert res.p_champ()[tid] == pytest.approx(0.125, abs=0.02)


def test_playoff_mc_is_deterministic():
    a = run_playoff_mc(_teams(), None, 40.0, 4000, seed=99)
    b = run_playoff_mc(_teams(), None, 40.0, 4000, seed=99)
    assert a.counts_champ == b.counts_champ
    assert a.counts_sf == b.counts_sf


def test_stronger_team_wins_more():
    # Seed 1 hugely overrated -> should reach the SF (beat its QF opp) far above 0.5.
    res = run_playoff_mc(_teams({**{i: 50.0 for i in range(1, 9)}, 1: 200.0}), None, 40.0, 4000, seed=1)
    assert res.p_sf()[1] > 0.95
    assert res.p_champ()[1] > res.p_champ()[2]


# --- locked (live) seam -------------------------------------------------------------------
def test_locked_quarterfinal_is_deterministic():
    # Lock seed 8 to beat seed 1 in QF1; every sim must then have id 8 win QF1.
    locked = {frozenset((1, 8)): 8}
    res = run_playoff_mc(_teams(), None, 40.0, 1000, seed=5, locked=locked)
    assert res.counts_sf[8] == res.n  # 8 reaches the SF in every sim
    assert res.counts_sf[1] == 0  # 1 never does


def test_locked_full_bracket_forces_champion():
    # A fully-locked bracket pins one champion deterministically.
    locked = {
        frozenset((1, 8)): 1,
        frozenset((4, 5)): 4,
        frozenset((2, 7)): 2,
        frozenset((3, 6)): 3,
        frozenset((1, 4)): 1,  # SF1
        frozenset((2, 3)): 2,  # SF2
        frozenset((1, 2)): 1,  # GF
    }
    res = run_playoff_mc(_teams(), None, 40.0, 500, seed=1, locked=locked)
    assert res.counts_champ[1] == res.n
