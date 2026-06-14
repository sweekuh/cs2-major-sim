"""Exact Kalshi fee + net-edge guards (goal G5: zero fee-math error).

Fees are asserted as EXACT integer cents (no float tolerance) — the net-edge gate is only
trustworthy if "edge" already subtracts what Kalshi actually charges to the cent.
"""

from __future__ import annotations

import math

import pytest

from monitor.fees import (
    maker_fee_cents,
    net_edge,
    per_contract_fee,
    taker_fee_cents,
)


def test_taker_fee_rounds_up_to_cent():
    # 0.07 * 1 * 0.5 * 0.5 = 0.0175 dollars = 1.75c -> rounds UP to 2c.
    assert taker_fee_cents(1, 0.50) == 2


def test_taker_fee_exact_whole_cents_no_spurious_roundup():
    # 0.07 * 100 * 0.5 * 0.5 = 1.75 dollars = exactly 175c -> NOT 176.
    assert taker_fee_cents(100, 0.50) == 175


def test_maker_fee_coefficient():
    # 0.0175 * 100 * 0.5 * 0.5 = 0.4375 dollars = 43.75c -> 44c.
    assert maker_fee_cents(100, 0.50) == 44


def test_taker_fee_small_price_rounds_up():
    # 0.07 * 1 * 0.1 * 0.9 = 0.0063 dollars = 0.63c -> 1c.
    assert taker_fee_cents(1, 0.10) == 1


def test_fee_zero_at_extreme_prices_and_nonpositive_contracts():
    assert taker_fee_cents(10, 0.0) == 0
    assert taker_fee_cents(10, 1.0) == 0
    assert taker_fee_cents(0, 0.5) == 0
    assert taker_fee_cents(-5, 0.5) == 0


def test_fee_matches_general_formula_across_grid():
    for c in (1, 3, 17, 100):
        for p in (0.05, 0.2, 0.37, 0.5, 0.83, 0.99):
            assert taker_fee_cents(c, p) == math.ceil(0.07 * c * p * (1 - p) * 100 - 1e-9)


def test_per_contract_fee_in_dollars():
    assert per_contract_fee(0.50) == 0.02  # 2c
    assert per_contract_fee(0.50, maker=True) == 0.01  # 1c (0.0175*0.25=0.4375c -> 1c)


def test_net_edge_subtracts_fee_and_half_spread():
    # |0.60 - 0.50| - fee(0.02) - spread/2(0.01) = 0.07
    assert net_edge(0.60, 0.50, 0.02) == pytest.approx(0.07)


def test_net_edge_negative_when_gap_inside_cost():
    # A 1c gap at mid 0.50 is inside the 2c fee -> no edge.
    assert net_edge(0.51, 0.50, 0.02) < 0
