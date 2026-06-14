"""3-outcome (soccer 1X2) odds-core guards: devig_three_way + pool_1x2.

The 2-outcome ``OddsQuote``/``pool`` cannot carry a draw; these pin the 3-way analog so the
calibration targets and cross-venue divergence are computed on the full simplex (dropping the
draw silently corrupts every downstream fair value). Pure, no network.
"""

from __future__ import annotations

import pytest

from odds.base import BlendedProb1X2, Quote1X2, devig_three_way, pool_1x2


def _q(provider, p, originate=1.0, liquidity=0.0):
    h, d, a = p
    return Quote1X2(provider=provider, match=(1, 2), p_home=h, p_draw=d, p_away=a,
                    originate=originate, liquidity=liquidity, ts=0.0)


def test_devig_three_way_removes_overround():
    # implied 0.5 / 0.25 / 0.25 already sum to 1 -> unchanged.
    h, d, a = devig_three_way(2.0, 4.0, 4.0)
    assert (h, d, a) == pytest.approx((0.5, 0.25, 0.25))


def test_devig_three_way_normalizes_to_one():
    # A real book's implied probs sum to >1; de-vig renormalizes to exactly 1.
    h, d, a = devig_three_way(1.8, 3.6, 4.5)
    assert h + d + a == pytest.approx(1.0)
    assert h > d > a  # implied 0.556/0.278/0.222 -> home favoured, away least likely


def test_pool_single_source_zero_var():
    blend = pool_1x2([_q("a", (0.6, 0.25, 0.15))])
    assert isinstance(blend, BlendedProb1X2)
    assert blend.as_tuple() == pytest.approx((0.6, 0.25, 0.15))
    assert blend.var == pytest.approx((0.0, 0.0, 0.0))
    assert blend.n_sources == 1


def test_pool_agreeing_sources_var_near_zero():
    blend = pool_1x2([_q("a", (0.6, 0.25, 0.15)), _q("b", (0.6, 0.25, 0.15))])
    assert blend.as_tuple() == pytest.approx((0.6, 0.25, 0.15))
    assert max(blend.var) == pytest.approx(0.0, abs=1e-12)


def test_pool_disagreeing_sources_var_positive_and_sums_to_one():
    blend = pool_1x2([_q("a", (0.7, 0.2, 0.1)), _q("b", (0.4, 0.3, 0.3))])
    assert sum(blend.as_tuple()) == pytest.approx(1.0)
    assert all(v > 0.0 for v in blend.var)
    assert blend.n_sources == 2


def test_pool_originate_weight_pulls_toward_sharp():
    # The sharp source (originate 1.0, deep) should dominate the soft copy (originate 0.3, thin).
    sharp = _q("pinnacle", (0.7, 0.2, 0.1), originate=1.0, liquidity=1000.0)
    soft = _q("soft", (0.4, 0.3, 0.3), originate=0.3, liquidity=10.0)
    blend = pool_1x2([sharp, soft])
    assert blend.p_home > 0.6  # pulled toward the sharp 0.7, not the midpoint
    assert sum(blend.as_tuple()) == pytest.approx(1.0)
