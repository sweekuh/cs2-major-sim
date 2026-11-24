"""Offline checks for the point-in-time Cologne qualification-market replay."""

import gzip
import json
from contextlib import nullcontext
from datetime import datetime

import pytest

from analysis.singapore_live import backtest_cologne as bt
from engine.teams import Team


def test_later_prices_and_unannounced_result_do_not_change_cutoff_state():
    teams = {n: Team(i, n, i, 100) for i, n in enumerate(("A", "B"), 1)}
    prefix = {"a": "A", "b": "B", "bo": 1, "created": 10, "start": 20, "end": 100,
              "series": bt.Series([(10, 0.44), (19, 0.46), (50, 0.99)])}
    # The prefix has no eventual winner. Both futures are possible at t=50.
    rec, locked, prices, obs = bt.state_at(50, [prefix], teams)
    assert rec == {"A": [0, 0], "B": [0, 0]}
    assert locked == {}
    assert prices == {"1-2": 0.99}
    assert obs == [(1, 2, 0.46, 1)]
    for later_price, winner in ((0.01, "B"), (1.0, "A")):
        full = {**prefix, "winner": winner,
                "series": bt.Series(list(zip(prefix["series"].t, prefix["series"].p)) + [(75, later_price)])}
        assert bt.state_at(50, [full], teams) == (rec, locked, prices, obs)
        assert bt.state_at(99, [full], teams)[1] == {}
        post, post_locks, post_prices, post_obs = bt.state_at(100, [full], teams)
        assert post[winner] == [1, 0]
        assert post_locks == {frozenset((1, 2)): teams[winner].id}
        assert post_prices == {} and post_obs == obs


def test_archive_result_clocks_cover_both_stages_and_agree_with_valve():
    data = json.loads(gzip.decompress(bt.DATA.read_bytes()))
    valve = json.loads(bt.VALVE.read_text())
    clocks = json.loads(bt.MATCH_TIMES.read_text())["matches"]
    assert len({m["match_id"] for m in clocks}) == len(clocks) == 66
    for stage in (1, 2):
        _, by, matches, _ = bt.stage_inputs(stage, data, valve, clocks)
        assert len(matches) == 33
    spirit_mibr = next(m for m in matches if {m["a"], m["b"]} == {"Spirit", "MIBR"})
    cutoff = int(datetime.fromisoformat("2026-06-06T20:00:00+00:00").timestamp())
    key = frozenset((by["Spirit"].id, by["MIBR"].id))
    assert spirit_mibr["start"] < cutoff < spirit_mibr["end"]
    assert key not in bt.state_at(cutoff, [spirit_mibr], by)[1]
    assert bt.state_at(spirit_mibr["end"], [spirit_mibr], by)[1] == {key: by["Spirit"].id}
    with pytest.raises(ValueError, match="Incomplete match clock"):
        bt.stage_inputs(clocks[0]["stage"], data, valve, clocks[1:])


def test_trade_error_resamples_opposing_sides_as_one_market():
    trades = [{"stage": 1, "team": team, "pnl": pnl}
              for team, pnls in (("A", (0.9, -0.9)), ("B", (0.4, -0.4))) for pnl in pnls]
    assert bt.clustered_trade_se(trades) == 0.0


@pytest.mark.parametrize("old_cache", [[], {"fingerprint": "old-inputs", "rows": []}])
def test_incompatible_cache_replays_with_prior_major_fit(tmp_path, monkeypatch, old_cache):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "cologne_bt_rows.json").write_text(json.dumps(old_cache))
    monkeypatch.setattr(bt, "HERE", tmp_path)
    monkeypatch.setattr(bt, "replay_key", lambda spread: "current-inputs")
    monkeypatch.setattr(bt.sys, "argv", ["backtest_cologne"])
    monkeypatch.setattr(bt, "ProcessPoolExecutor", lambda **kwargs: nullcontext())

    class ReplayStarted(Exception):
        pass

    def verify_replay(stage, data, valve, times, spread, pool):
        assert stage == 1 and len(times) == 66
        assert spread == 166.0  # Austin + Budapest, 198 matches, in engine units.
        raise ReplayStarted

    monkeypatch.setattr(bt, "replay", verify_replay)
    with pytest.raises(ReplayStarted):
        bt.main()
