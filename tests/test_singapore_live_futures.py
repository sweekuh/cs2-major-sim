import json
import sqlite3

import httpx
import pytest

from analysis.singapore_kalshi import live
from engine.teams import Team


def test_finished_and_partial_series_are_oriented_to_the_team():
    teams = [Team(1, "A", 1, 1400), Team(2, "B", 2, 1400)]
    g = live.Game(3, "B", "A", None, 3, 1, 0, "")
    locks, overrides = live.series_inputs(teams, [g], 1400)
    assert not locks
    assert overrides == {"1-2": 0.25}
    locks, overrides = live.series_inputs(teams, [g._replace(winner="B", left=2)], 1400)
    assert locks == {frozenset((1, 2)): 2}
    assert not overrides


def test_forecasts_reuse_identical_state_and_freeze_new_results(monkeypatch):
    monkeypatch.setattr(live, "RUNS", 12)
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE forecasts(id TEXT PRIMARY KEY, at, state, estimates, n)")
    g = live.Game(1, "HEROIC", "Imperial", None, 1, 0, 0, "")
    stages = [[g], [], [], []]
    model = {"fitted": 1410, "spread90": [980, 2040], "residual80": 0.56}
    key, forecasts, fresh = live.forecast(db, stages, "roster", model)
    assert fresh
    assert [
        sum(p[0] for p in forecasts[k].values()) for k in live.EVENTS
    ] == pytest.approx([8, 8, 8, 1])
    assert not live.forecast(db, stages, "roster", model)[2]
    stages[0] = [g._replace(winner="Imperial", right=1)]
    key2, _, fresh = live.forecast(db, stages, "roster", model)
    assert fresh and key != key2
    assert (
        json.loads(
            db.execute("SELECT state FROM forecasts WHERE id=?", (key,)).fetchone()[0]
        )["stages"][0][0][3]
        is None
    )
    assert live.forecast(db, stages, "new-roster", model)[2]


def test_futures_require_two_sided_depth_and_reviewed_inputs(monkeypatch):
    monkeypatch.setattr(live, "EVENTS", {"champion": "KXCS2-PGLSG26"})
    book = {"yes_dollars": [["0.08", "10"]], "no_dollars": [["0.90", "10"]]}
    market = {
        "status": "active",
        "event_ticker": "KXCS2-PGLSG26",
        "market_type": "binary",
        "notional_value_dollars": "1",
        "yes_sub_title": "HEROIC",
        "ticker": "example",
        "rules_primary": "If HEROIC is the 2026 PGL Major Singapore champion, then the market resolves to Yes.",
        "rules_secondary": "Terms",
    }

    def reply(request):
        path = request.url.path
        data = (
            {"markets": [market]}
            if "/events/" in path
            else {"orderbook_fp": book}
            if path.endswith("orderbook")
            else {"series": {"fee_type": "quadratic", "fee_multiplier": 1}}
        )
        return httpx.Response(200, json=data)

    estimate = {"champion": {"HEROIC": [0.35, 0.25, 0.5]}}
    with httpx.Client(transport=httpx.MockTransport(reply)) as client:

        def yes(live_teams=(), reviewed=True):
            return live.futures(client, estimate, live_teams, reviewed)[0]["sides"][0][
                "candidate"
            ]

        assert yes()
        assert not yes(["HEROIC"])
        assert not yes(reviewed=False)
        book["yes_dollars"] = []
        assert not yes()
