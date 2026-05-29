"""Monte Carlo runner tests — RED scaffold for Wave 3 (engine/montecarlo.py).

xfail(strict=False) until wave 3 implements the generator-first MC with
SeedSequence.spawn over a pinned chunk count, Wilson bands, and per-sim sample
retention. These guard the invariants (ΣP=2/8/2), reproducibility under chunking,
the retained record sample (Phase 3 Ballot B seam), and the epistemic-band-collapse
contract (single source -> band == inner Wilson).
"""

from __future__ import annotations

import pytest

WAVE3 = pytest.mark.xfail(reason="implemented in wave 3 (engine/montecarlo.py)", strict=False)


@WAVE3
def test_invariants():
    """MC-01/03, ENG-06/07: over a run, ΣP(3-0)≈2, ΣP(0-3)≈2, ΣP(advance)≈8 (±0.05 at
    N>=50k); exactly 8 advance / 8 eliminated; no rematches; Bo3 only at 2W or 2L."""
    from engine.montecarlo import run_mc_progressive  # noqa: F401

    raise AssertionError("wave 3: assert structural invariants over a large-N run")


@WAVE3
def test_reproducibility():
    """ENG-09/MC-05/Pitfall 10: same (seed, N, n_chunks) -> identical per-team counts,
    across runs and chunk layouts. SeedSequence.spawn over a pinned chunk count."""
    from engine.montecarlo import run_mc_progressive  # noqa: F401

    raise AssertionError("wave 3: assert deterministic counts under chunking")


@WAVE3
def test_record_sample_retained():
    """MC-04: the full per-sim record matrix is retained (not just marginals) so Phase 3
    Ballot B can hill-climb against the stored sample."""
    from engine.montecarlo import run_mc_progressive  # noqa: F401

    raise AssertionError("wave 3: assert per-sim record sample retained")


@WAVE3
def test_epistemic_band_collapses_to_wilson():
    """PROB-05: with one source the reported (epistemic) band collapses to the inner
    Wilson (aleatoric) band exactly. epistemic_draws yields one draw; spread == 0."""
    from engine.montecarlo import run_mc_progressive  # noqa: F401

    raise AssertionError("wave 3: assert single-source band == inner Wilson band")
