"""Monte Carlo runner tests — Wave 3 (engine/montecarlo.py).

These assert the generator-first MC contract: SeedSequence.spawn over a PINNED chunk
count (reproducibility under chunking, ENG-09/MC-05/Pitfall 10), the structural
invariants (ΣP=2/8/2, MC-01/03), the retained full per-sim record sample (Phase 3
Ballot B seam, MC-04), the hand-coded Wilson band (MC-02), and the epistemic-band
collapse to the inner Wilson band for a single source (PROB-03/05).
"""

from __future__ import annotations

import math

from engine.montecarlo import run_mc, run_mc_progressive, wilson
from engine.teams import STAGE_SIZE, load_teams


def test_wilson_closed_form():
    """MC-02: wilson(k, n, z) matches the closed-form Wilson score interval, no scipy."""
    k, n, z = 30, 100, 1.96
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d
    lo, hi = wilson(k, n, z)
    assert math.isclose(lo, centre - half, rel_tol=1e-12)
    assert math.isclose(hi, centre + half, rel_tol=1e-12)
    assert wilson(0, 0) == (0.0, 0.0)


def test_reproducibility():
    """ENG-09/MC-05/Pitfall 10: same (seed, N, n_chunks) -> identical per-team
    3-0/advance/0-3 counts across two independent runs (SeedSequence.spawn pinned)."""
    teams = load_teams()
    kwargs = dict(teams=teams, ratings=None, S=40.0, N=4000, locked={}, seed=12345)
    r1 = run_mc(**kwargs)
    r2 = run_mc(**kwargs)
    assert r1.n == r2.n == 4000
    assert r1.counts_30 == r2.counts_30
    assert r1.counts_advance == r2.counts_advance
    assert r1.counts_03 == r2.counts_03


def test_reproducibility_survives_n_chunks_default():
    """The pinned default n_chunks is what the app ships; an explicit equal n_chunks
    must reproduce the default exactly (the backtest runs the SAME chunked path)."""
    teams = load_teams()
    base = dict(teams=teams, ratings=None, S=40.0, N=4000, locked={}, seed=999)
    r_default = run_mc(**base)
    r_explicit = run_mc(**base, n_chunks=20)
    assert r_default.counts_advance == r_explicit.counts_advance


def test_record_sample_retained():
    """MC-04: the full per-sim record sample is retained (one (wins, losses) vector per
    team per sim), length == N — not just the marginal tallies."""
    teams = load_teams()
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


def test_invariants():
    """MC-01/03, ENG-06/07: at N>=50k, ΣP(3-0)≈2, ΣP(0-3)≈2, ΣP(advance)≈8 within ±0.05;
    every sim has exactly 2×3-0, 2×0-3, 8 advance."""
    teams = load_teams()
    N = 50000
    r = run_mc(teams=teams, ratings=None, S=40.0, N=N, locked={}, seed=2024)
    sum_30 = sum(c / N for c in r.counts_30.values())
    sum_03 = sum(c / N for c in r.counts_03.values())
    sum_adv = sum(c / N for c in r.counts_advance.values())
    assert abs(sum_30 - 2.0) <= 0.05
    assert abs(sum_03 - 2.0) <= 0.05
    assert abs(sum_adv - 8.0) <= 0.05


def test_progress_partials_yielded():
    """MC-05: run_mc_progressive yields one Partial(done, total, running_p_adv) per chunk;
    done climbs to N; running_p_adv is a finite per-team mapping."""
    teams = load_teams()
    partials = list(run_mc_progressive(
        teams=teams, ratings=None, S=40.0, N=4000, locked={}, seed=5, n_chunks=20
    ))
    assert len(partials) == 20  # one per pinned chunk
    assert partials[-1].done == 4000
    assert all(p.total == 4000 for p in partials)
    # running P(advance) is a per-team dict of finite probabilities in [0, 1].
    last = partials[-1].running_p_adv
    assert len(last) == STAGE_SIZE
    assert all(0.0 <= v <= 1.0 for v in last.values())


def test_epistemic_band_collapses_to_wilson():
    """PROB-03/05: with one source the epistemic spread is zero, so the reported band per
    team equals the inner Wilson band on its advance count exactly."""
    teams = load_teams()
    N = 4000
    r = run_mc(teams=teams, ratings=None, S=40.0, N=N, locked={}, seed=42)
    for tid, k in r.counts_advance.items():
        lo, hi = r.band_advance[tid]
        wlo, whi = wilson(k, N)
        assert math.isclose(lo, wlo, rel_tol=1e-12, abs_tol=1e-12)
        assert math.isclose(hi, whi, rel_tol=1e-12, abs_tol=1e-12)


def test_no_forbidden_imports():
    """engine.montecarlo must not import streamlit/httpx/requests (gate-ability)."""
    import engine.montecarlo as mc

    src = open(mc.__file__, encoding="utf-8").read()
    for forbidden in ("import streamlit", "import httpx", "import requests"):
        assert forbidden not in src
