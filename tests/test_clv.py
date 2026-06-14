"""Signal log + CLV guards (PRD R6, the truth oracle).

CLV vs the sharp close is how we learn whether the fair value has alpha, so these pin the CLV
sign/magnitude and the round-trip through the sqlite store (in-memory).
"""

from __future__ import annotations

import pytest

from monitor.signal_log import Signal, SignalLog, compute_clv


def test_clv_positive_when_yes_entry_beats_close():
    # Bought YES at 0.50, line closed at 0.55 -> we were on the right side: +10%.
    assert compute_clv(0.50, 0.55, "yes") == pytest.approx(10.0)


def test_clv_negative_when_yes_entry_worse_than_close():
    assert compute_clv(0.50, 0.45, "yes") == pytest.approx(-10.0)


def test_clv_side_no_flips_orientation():
    # Bought NO at 0.50 (i.e. 0.50 on the no side); close drifts to 0.45 -> NO was right: +10%.
    assert compute_clv(0.50, 0.45, "no") == pytest.approx(10.0)


def test_clv_raises_on_nonpositive_entry():
    with pytest.raises(ValueError):
        compute_clv(0.0, 0.5, "yes")


def _sig(**kw):
    base = dict(
        ticker="KXMENWORLDCUP-26-BRA", market_type="champion", side="yes",
        fair_value=0.22, fair_source="theoddsapi:sharp", kalshi_mid=0.20,
        spread=0.02, depth=1000.0, net_edge=0.01, model_conf=0.8,
    )
    base.update(kw)
    return Signal(**base)


def test_record_and_settle_roundtrip():
    log = SignalLog(":memory:")
    try:
        sid = log.record(_sig(kalshi_mid=0.50, side="yes"))
        assert sid > 0
        clv = log.settle(sid, pinnacle_close=0.55)
        assert clv == pytest.approx(10.0)
        rows = log.all_signals()
        assert len(rows) == 1
        assert rows[0]["pinnacle_close"] == pytest.approx(0.55)
        assert rows[0]["clv"] == pytest.approx(10.0)
    finally:
        log.close()


def test_mean_clv_over_settled_only():
    log = SignalLog(":memory:")
    try:
        a = log.record(_sig(kalshi_mid=0.50))
        b = log.record(_sig(kalshi_mid=0.50))
        log.record(_sig(kalshi_mid=0.50))  # left unsettled
        log.settle(a, 0.55)   # +10
        log.settle(b, 0.45)   # -10
        mean, n = log.mean_clv()
        assert n == 2
        assert mean == pytest.approx(0.0)
    finally:
        log.close()


def test_settle_unknown_id_raises():
    log = SignalLog(":memory:")
    try:
        with pytest.raises(KeyError):
            log.settle(999, 0.5)
    finally:
        log.close()
