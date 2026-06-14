"""Edge-detection + ranking guards (monitor core)."""

from __future__ import annotations

import pytest

from monitor.edge import evaluate, find_edges
from odds.kalshi import KalshiMarketState


def _state(ticker="T", mid=0.20, spread=0.02, depth=1000.0):
    return KalshiMarketState(
        series_ticker="KX", event_ticker="E", ticker=ticker, market_type="champion",
        title="", yes_sub_title="", yes_bid=mid - spread / 2, yes_ask=mid + spread / 2,
        mid=mid, spread=spread, depth=depth, status="open",
    )


def test_buy_yes_when_model_above_mid():
    sig = evaluate(0.30, _state(mid=0.20, spread=0.02))
    assert sig.side == "yes"
    # |0.30 - 0.20| - fee(2c at 0.20) - spread/2(0.01) = 0.10 - 0.02 - 0.01 = 0.07
    assert sig.net_edge == pytest.approx(0.07)


def test_buy_no_when_model_below_mid():
    sig = evaluate(0.10, _state(mid=0.20, spread=0.02))
    assert sig.side == "no"
    assert sig.net_edge == pytest.approx(0.07)


def test_find_edges_filters_below_threshold():
    pairs = [
        (0.205, _state(ticker="tiny", mid=0.20)),   # ~0 gross edge, inside cost -> dropped
        (0.30, _state(ticker="real", mid=0.20)),     # clear edge -> kept
    ]
    out = find_edges(pairs, threshold=0.0)
    assert [s.ticker for s in out] == ["real"]


def test_find_edges_ranks_deeper_book_higher_when_edge_equal():
    pairs = [
        (0.30, _state(ticker="thin", mid=0.20, depth=10.0)),
        (0.30, _state(ticker="deep", mid=0.20, depth=100000.0)),
    ]
    out = find_edges(pairs, threshold=0.0)
    assert out[0].ticker == "deep"  # same net edge, deeper book ranks first
