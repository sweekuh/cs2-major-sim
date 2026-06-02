"""Epistemic OUTER-loop guards (PROB-03/04/05, Pitfall 4/5, T-05-GATE/CLAMP/EPI).

RED-first: these exercise the K-Beta-draw epistemic outer loop the MC must fill. They
prove the headline correctness facts:

  - test_band_wider_than_wilson [CRITICAL]: with cross-source disagreement injected
    DIRECTLY (hand-authored (p, var) with var > 0 — NOT routed through a 1-source pool,
    which yields var≈0 and degenerates to the no-op path), the reported per-team band is
    STRICTLY WIDER than the inner Wilson band (the across-draw epistemic spread).
  - test_band_stable_in_N: the SAME injected-var match has an epistemic band that does
    NOT meaningfully shrink from N=2000 to N=20000, while the pure Wilson term does
    (epistemic is N-invariant; only aleatoric Wilson narrows).
  - test_rating_only_noop_unchanged [GATE GUARD]: with NO var / NO market overrides the
    MC produces byte-identical per-team counts to a baseline (k=1 no-op path), proving the
    fill is additive and GATE-01 stays green.

The epistemic injection rides a keyword-only ``market_blend`` seam on the MC entry:
``{ "lo-hi": (p, var) }`` per imminent-round matchup (p = P(lower-id team wins the
series), var = raw cross-source variance, clamped downstream by beta_moment_fit).
``market_blend=None`` (default) is the unchanged rating-only path.
"""

from __future__ import annotations

import numpy as np
import pytest

from engine.montecarlo import run_mc, wilson
from engine.teams import load_teams


def _band_width(band: dict[int, tuple[float, float]], tid: int) -> float:
    lo, hi = band[tid]
    return hi - lo


def _r1_lower_id_match_key(teams):
    """An imminent-round (R1) matchup key 'lo-hi' for seed i vs seed i+8 (i < i+8)."""
    # Round 1 pairs seed i vs i+8; use seed 1 vs 9 -> key "1-9", id 1 is the lower id.
    return "1-9", 1, 9


def test_point_probs_valid_under_epistemic():
    """CRITICAL regression (P0, re-fix of the bug reverted by fde284a). Under the epistemic
    OUTER loop (K Beta draws when any market var>0), ``counts_*`` and ``sample`` accumulate over
    K*N sims, so ``Result.n`` MUST be ``len(sample)`` (=K*N). If it is the input N instead, every
    POINT probability is inflated by ~K: ``p_advance()`` sums to 8*K and individual values exceed
    1.0 ("1192%"). Rating-only (K=1) is unaffected, which is why GATE-01 and the band-width tests
    stayed green — they never assert ``p ∈ [0, 1]`` or the structural sums. This test closes that
    gap.

    Structural invariant of a 16-team 3-0/0-3 Swiss stage: EVERY sim has exactly 8 teams advance
    (reach 3 wins), exactly 2 go 3-0, exactly 2 go 0-3. Summed over teams -> P(advance)=8,
    P(3-0)=2, P(0-3)=2 (CLAUDE.md "Σ P = 8 / 2 / 2"), regardless of K.
    """
    teams = load_teams()
    key, _lo, _hi = _r1_lower_id_match_key(teams)
    N = 4000
    # Inject var>0 on one R1 matchup -> has_epistemic -> the K-draw outer loop runs.
    r = run_mc(teams, None, 40.0, N, {}, seed=7, market_blend={key: (0.5, 0.05)})

    # n reflects the TOTAL sims tallied (K*N) and matches the retained sample length.
    assert r.n == len(r.sample)
    assert r.n > N, "var>0 must run K>1 epistemic draws (n should be K*N, not N)"

    p_adv, p_30, p_03 = r.p_advance(), r.p_30(), r.p_03()
    # Every value is a valid probability (the K-inflation bug pushed these well above 1.0).
    assert all(0.0 <= v <= 1.0 for v in p_adv.values()), f"max p_adv={max(p_adv.values()):.3f}"
    assert all(0.0 <= v <= 1.0 for v in p_30.values())
    assert all(0.0 <= v <= 1.0 for v in p_03.values())
    # Structural sums hold exactly (integer counts / len(sample)); a K-inflated n breaks all three.
    assert sum(p_adv.values()) == pytest.approx(8.0, abs=1e-9)
    assert sum(p_30.values()) == pytest.approx(2.0, abs=1e-9)
    assert sum(p_03.values()) == pytest.approx(2.0, abs=1e-9)


def test_band_wider_than_wilson():
    """CRITICAL (PROB-04): a directly-injected high-disagreement matchup yields a reported
    band STRICTLY WIDER than the inner Wilson band.

    var is INJECTED, not pooled: we hand-author (p=0.5, var=0.05) for the seed1-vs-seed9
    R1 matchup. A 1-source pool() would give var≈0 (PROB-05) and the band would collapse
    to Wilson (trivially passing) — injecting var>0 exercises the genuine multi-source
    disagreement path. Across K Beta draws of p around 0.5±spread, seed-1's P(advance)
    varies, so the across-draw spread inflates the band beyond Wilson alone.
    """
    teams = load_teams()
    key, lo_id, _hi_id = _r1_lower_id_match_key(teams)
    N = 8000

    # Baseline: NO market_blend -> rating-only no-op -> band == inner Wilson.
    base = run_mc(teams, None, 40.0, N, {}, seed=42, market_blend=None)
    wilson_lo = wilson(base.counts_advance[lo_id], N)
    wilson_width = wilson_lo[1] - wilson_lo[0]

    # Epistemic: inject var=0.05 directly for the seed1-vs-seed9 matchup.
    market_blend = {key: (0.5, 0.05)}
    epi = run_mc(teams, None, 40.0, N, {}, seed=42, market_blend=market_blend)
    epi_width = _band_width(epi.band_advance, lo_id)

    assert epi_width > wilson_width * 1.2, (
        f"epistemic band width {epi_width:.4f} must STRICTLY exceed inner Wilson "
        f"{wilson_width:.4f}; the across-draw spread (var=0.05 injected) is missing"
    )


def test_band_stable_in_N():
    """PROB-05: the epistemic band on the injected-var matchup does NOT meaningfully shrink
    as N grows (across-draw spread is N-invariant), while pure Wilson does.

    Same directly-injected (p=0.5, var=0.05) matchup at N1=2000 and N2=20000 (N2 >> N1).
    Assert band_width(N2) is within a small factor of band_width(N1) (the epistemic floor
    persists), AND both clearly exceed the pure-Wilson width at N2 (which shrinks ~1/sqrt
    N). The injected var (not a 1-source pool) makes this a non-degenerate check.
    """
    teams = load_teams()
    key, lo_id, _hi_id = _r1_lower_id_match_key(teams)
    market_blend = {key: (0.5, 0.05)}

    N1, N2 = 2000, 20000
    epi1 = run_mc(teams, None, 40.0, N1, {}, seed=11, market_blend=market_blend)
    epi2 = run_mc(teams, None, 40.0, N2, {}, seed=11, market_blend=market_blend)
    w1 = _band_width(epi1.band_advance, lo_id)
    w2 = _band_width(epi2.band_advance, lo_id)

    # Pure Wilson at N2 (the aleatoric-only reference): a SINGLE-draw rating-only run at N2.
    # var=0 collapses epistemic_draws to one draw, so band_advance IS the inner Wilson band
    # at N2 (it shrinks ~1/sqrt(N)). This is the genuine no-epistemic comparison.
    wilson_ref = run_mc(teams, None, 40.0, N2, {}, seed=11, market_blend=None)
    wilson_n2_width = _band_width(wilson_ref.band_advance, lo_id)

    # Epistemic band is N-invariant: w2 is within a small factor of w1 (does not collapse).
    assert w2 > 0.5 * w1, (
        f"epistemic band shrank from {w1:.4f} (N={N1}) to {w2:.4f} (N={N2}); it must be "
        "~N-invariant (the across-draw spread does not shrink with N)"
    )
    # And the epistemic band at N2 clearly exceeds the pure-Wilson width at N2.
    assert w2 > wilson_n2_width * 1.5, (
        f"epistemic band {w2:.4f} at N={N2} should clearly exceed pure Wilson "
        f"{wilson_n2_width:.4f} (which shrank with N)"
    )


def test_point_probs_valid_under_epistemic():
    """CRITICAL REGRESSION (P0, /plan-eng-review 2026-05-31): point probabilities MUST stay valid
    under the K-draw epistemic OUTER loop.

    Under ``market_blend`` var>0 the MC runs K=12 outer draws, accumulating ``counts_*`` and
    ``sample`` over K*N sims. ``Result.n`` MUST therefore be ``len(sample)`` (== K*N), NOT ``N`` —
    else ``p_advance()/p_30()/p_03()`` are inflated by K (proven: sum=96.0, max=11.9 with n=N).

    The pre-existing band tests assert band WIDTH only and never caught this. This asserts the
    structural invariants of the marginals: every probability is in [0, 1], exactly 8 of 16 teams
    advance in expectation (sum P(advance)==8), and at most 8 can go 3-0 / at most 8 can go 0-3.
    """
    teams = load_teams()
    N = 3000
    epi = run_mc(teams, None, 40.0, N, {}, seed=42, market_blend={"1-9": (0.5, 0.05)})

    p_adv = epi.p_advance()
    p_30 = epi.p_30()
    p_03 = epi.p_03()

    # Every marginal is a valid probability.
    for label, probs in (("advance", p_adv), ("3-0", p_30), ("0-3", p_03)):
        worst = max(probs.values())
        assert worst <= 1.0, f"P({label}) exceeded 1.0 (got {worst:.3f}) — counts/n inflated by K"

    # Structural totals: 8 of 16 advance; 3-0 and 0-3 are 2-team slots each (<=8 in expectation).
    assert abs(sum(p_adv.values()) - 8.0) < 0.05, (
        f"sum P(advance) must be 8.0 (8 of 16 advance), got {sum(p_adv.values()):.2f} "
        "— Result.n is not len(sample) under epistemic draws"
    )
    assert sum(p_30.values()) <= 8.0 + 0.05
    assert sum(p_03.values()) <= 8.0 + 0.05

    # n must equal the retained sample size (the true sim count behind the counts).
    assert epi.n == len(epi.sample) == N * 12, (
        f"Result.n ({epi.n}) must equal len(sample) ({len(epi.sample)}) == K*N under epistemic draws"
    )


def test_sampling_band_nested_in_epistemic_and_equal_when_k1():
    """D2 (/plan-eng-review): band_*_sampling (the aleatoric Wilson of the aggregate marginal) is
    NESTED inside band_* (the epistemic across-draw union) under K>1, and EQUAL to it when K=1.

    The two-tone CI bar draws sampling solid + epistemic faint; the equal-when-K=1 fact is the GATE
    guard (the bar collapses to single-tone on the rating-only path). Nesting holds because the
    sampling band is a single tight Wilson over K*N sims while the union spans per-draw Wilson
    intervals each over N (wider) plus the across-draw spread.
    """
    teams = load_teams()
    N = 4000
    eps = 1e-9

    # K=1 (rating-only): sampling band == epistemic band exactly, for all three buckets.
    base = run_mc(teams, None, 40.0, N, {}, seed=7, market_blend=None)
    assert base.band_advance_sampling == base.band_advance
    assert base.band_30_sampling == base.band_30
    assert base.band_03_sampling == base.band_03

    # K>1 (injected var): sampling band is nested inside the epistemic union for EVERY team.
    epi = run_mc(teams, None, 40.0, N, {}, seed=7, market_blend={"1-9": (0.5, 0.05)})
    for tid in (t.id for t in teams):
        lo_o, hi_o = epi.band_advance[tid]
        lo_i, hi_i = epi.band_advance_sampling[tid]
        assert lo_o <= lo_i + eps and hi_i <= hi_o + eps, (
            f"team {tid}: sampling [{lo_i:.4f},{hi_i:.4f}] not nested in epistemic "
            f"[{lo_o:.4f},{hi_o:.4f}]"
        )
    # On the injected-var match (seed 1) the epistemic band is clearly WIDER than the sampling band.
    lo_o, hi_o = epi.band_advance[1]
    lo_i, hi_i = epi.band_advance_sampling[1]
    assert (hi_o - lo_o) > (hi_i - lo_i) * 1.1, (
        "the priced match's epistemic band must exceed its sampling band (the disagreement shows)"
    )


def test_rating_only_noop_unchanged():
    """GATE GUARD (T-05-GATE): with NO var / NO market overrides, run_mc produces IDENTICAL
    per-team counts to a baseline run for a fixed (seed, N, n_chunks).

    The rating-only path must be byte-identical to today's single-point no-op draw, proving
    the epistemic fill + market_blend seam are additive and GATE-01 stays green. We compare:
      (1) the default-arg run (no market_blend) to an explicit market_blend=None run, and
      (2) an all-zero-var market_blend (which must also collapse to the exact no-op draw).
    """
    teams = load_teams()
    N = 5000

    base = run_mc(teams, None, 40.0, N, {}, seed=2024, n_chunks=20)
    explicit_none = run_mc(teams, None, 40.0, N, {}, seed=2024, n_chunks=20, market_blend=None)

    assert base.counts_30 == explicit_none.counts_30
    assert base.counts_advance == explicit_none.counts_advance
    assert base.counts_03 == explicit_none.counts_03
    assert base.band_advance == explicit_none.band_advance

    # An all-zero-var market_blend must ALSO be the exact no-op (var<=0 -> single draw).
    zero_var = {"1-9": (0.5, 0.0)}
    zv = run_mc(teams, None, 40.0, N, {}, seed=2024, n_chunks=20, market_blend=zero_var)
    assert zv.counts_advance == base.counts_advance, (
        "all-zero-var market_blend must collapse to the exact rating-only no-op draw"
    )
