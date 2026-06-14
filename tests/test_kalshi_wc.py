"""KalshiWCProvider parse guards — fixture-driven, NO httpx import (D1/DX-01).

Pins price/spread/depth extraction and series->market-type classification for the WC market reader.
"""

from __future__ import annotations

from odds.kalshi import KalshiWCProvider, classify_series


def _market(**kw):
    base = dict(
        ticker="KXMENWORLDCUP-26-BRA",
        event_ticker="KXMENWORLDCUP-26",
        series_ticker="KXMENWORLDCUP",
        title="Will Brazil win the 2026 World Cup?",
        yes_sub_title="Brazil",
        yes_bid_dollars="0.18",
        yes_ask_dollars="0.22",
        open_interest=1500,
        status="open",
    )
    base.update(kw)
    return base


def test_classify_series_known_and_default():
    assert classify_series("KXMENWORLDCUP") == "champion"
    assert classify_series("kxwcgroupwin") == "group_winner"
    assert classify_series("KXWCGROUPQUAL") == "advance"
    assert classify_series("KXSOMEMATCHSERIES") == "match"  # default


def test_parse_state_mid_spread_depth():
    states = KalshiWCProvider().get_states({"markets": [_market()]})
    assert len(states) == 1
    st = states[0]
    assert st.market_type == "champion"
    assert abs(st.mid - 0.20) < 1e-9
    assert abs(st.spread - 0.04) < 1e-9
    assert st.depth == 1500.0
    assert st.yes_sub_title == "Brazil"


def test_depth_falls_back_to_volume_then_liquidity():
    m = _market()
    del m["open_interest"]
    m["volume"] = 800
    assert KalshiWCProvider().get_states({"markets": [m]})[0].depth == 800.0


def test_missing_prices_drops_market():
    m = _market()
    del m["yes_bid_dollars"]
    assert KalshiWCProvider().get_states({"markets": [m]}) == []


def test_crossed_book_dropped():
    # ask < bid is a malformed/crossed book -> drop.
    assert KalshiWCProvider().get_states({"markets": [_market(yes_bid_dollars="0.6", yes_ask_dollars="0.4")]}) == []


def test_empty_markets_fail_soft():
    assert KalshiWCProvider().get_states({"markets": []}) == []
    assert KalshiWCProvider().get_states("not a path or dict that exists") == []
