"""Exact Kalshi trading fees + net-edge gate (PRD R4, goal G5: zero fee-math error).

The whole project's premise correction is that any apparent edge under ~2c at mid-price is
eaten by fees + spread, so "edge" MUST mean edge net of the EXACT Kalshi charge — not a
floating approximation. Kalshi's fee per fill is

    fee = ceil( coeff * C * P * (1 - P) )        rounded UP to the next whole cent

where ``C`` is the contract count, ``P`` is the trade price in dollars (0-1), and the product
``coeff * C * P * (1-P)`` is in DOLLARS. The taker coefficient is 0.07 (peaks ~1.75c per
contract at P=0.50); the maker coefficient is 0.0175. [Kalshi fee schedule]

We compute in INTEGER CENTS end to end so the result matches Kalshi's charge to the cent and
the tests assert exact equality (no float tolerance). The ceil is taken with a tiny negative
epsilon so a value that is mathematically an exact number of cents (e.g. 1.7500000001 from
float noise) does not spuriously round up a cent.

[Q-FEES, open] Confirm the soccer taker coefficient is 0.07 and not a sports-category override
against the live fee schedule / a real fill before trusting the net-edge gate for execution.
"""

from __future__ import annotations

import math

TAKER_COEFF = 0.07
MAKER_COEFF = 0.0175

# Guard against float noise pushing an exact-cent value up to the next cent.
_CENT_EPS = 1e-9


def _fee_cents(coeff: float, contracts: int, price: float) -> int:
    """``ceil(coeff * C * P * (1-P))`` rounded up to whole cents, returned as an int of cents."""
    if contracts <= 0:
        return 0
    dollars = coeff * contracts * price * (1.0 - price)
    return int(math.ceil(dollars * 100.0 - _CENT_EPS))


def taker_fee_cents(contracts: int, price: float) -> int:
    """Exact Kalshi TAKER fee in whole cents for ``contracts`` filled at ``price`` (dollars 0-1)."""
    return _fee_cents(TAKER_COEFF, contracts, price)


def maker_fee_cents(contracts: int, price: float) -> int:
    """Exact Kalshi MAKER fee in whole cents for ``contracts`` resting-then-filled at ``price``."""
    return _fee_cents(MAKER_COEFF, contracts, price)


def per_contract_fee(price: float, *, maker: bool = False) -> float:
    """Per-contract fee in DOLLARS at ``price`` (the unit ``net_edge`` subtracts).

    Computed as the exact whole-cent fee for ONE contract divided back to dollars, so it stays
    consistent with what Kalshi actually charges on a single contract at this price.
    """
    cents = maker_fee_cents(1, price) if maker else taker_fee_cents(1, price)
    return cents / 100.0


def net_edge(fair: float, mid: float, spread: float, *, maker: bool = False) -> float:
    """Edge net of cost, in probability/dollar units: ``|fair - mid| - fee - spread/2``.

    ``fair`` is the model (or sharp-consensus) fair value, ``mid`` the Kalshi mid price, both in
    dollars (0-1); ``spread`` the Kalshi bid-ask width. The fee is the exact per-contract Kalshi
    charge at ``mid``. A non-positive result means the apparent gap is inside cost -> no signal.
    """
    return abs(fair - mid) - per_contract_fee(mid, maker=maker) - spread / 2.0
