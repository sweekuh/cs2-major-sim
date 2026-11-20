import gzip
import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from analysis.singapore_kalshi import paper
from analysis.singapore_kalshi.model import D, ceiling, fit, forecast, walk


def test_walk_price_and_fee_after_crossing_levels():
    result = walk([["0.60", "4"], ["0.58", "10"]], D(1))
    assert result["ask_c"] == pytest.approx(41.2)
    assert result["debit_usd"] == 4.29
    assert walk([["0.60", "9.99"]], D(1)) is None
    assert ceiling(0.41, D(1)) == 39


def test_future_spread_uses_prior_events_and_orients_all_formats():
    model = fit()
    assert model["fitted"] == 1410
    assert (
        model["walk"]["Cologne 2026"]["fit"]["brier"]
        < model["walk"]["Cologne 2026"]["repo600"]["brier"]
    )
    for bo in (1, 3, 5):
        a = forecast("Liquid", "BC.Game", bo, model)
        b = forecast("BC.Game", "Liquid", bo, model)
        assert a["low"] < a["p"] < a["high"]
        assert a["p"] + b["p"] == pytest.approx(1)
        assert a["low"] + b["high"] == pytest.approx(1)


def test_paper_entry_dedup_close_and_settlement(monkeypatch):
    at = datetime(2026, 11, 24, 3, 45, tzinfo=UTC)
    clock = [at]
    monkeypatch.setattr(paper, "now", lambda: clock[0])
    g = {
        "teams": ["HEROIC", "Imperial"],
        "start": (at + timedelta(minutes=15)).isoformat(),
        "bo": 1,
        "status": "upcoming",
        "score": [0, 0],
        "winner": None,
    }
    m = {
        "ticker": "KXCS2GAME-26NOV232300HERIMP-HER",
        "event_ticker": "KXCS2GAME-26NOV232300HERIMP",
        "status": "active",
        "market_type": "binary",
        "notional_value_dollars": "1",
        "yes_sub_title": "HEROIC",
        "rules_primary": "If HEROIC wins the PGL Singapore Major: HEROIC vs. Imperial CS2 match, then the market resolves to Yes.",
        "rules_secondary": "Full match",
    }
    assert paper.belongs(m, g)
    assert not paper.belongs(dict(m, yes_sub_title="Imperial"), g)
    assert not paper.belongs(m, dict(g, start=(at + timedelta(days=1)).isoformat()))
    books = {"orderbook_fp": {"yes_dollars": [["0.32", "20"]], "no_dollars": [["0.66", "20"]]}}
    meta = {"KXCS2GAME": {"fee_type": "quadratic", "fee_multiplier": 1}}
    monkeypatch.setattr(paper, "schedule", lambda client: {"1": g})
    monkeypatch.setattr(
        paper, "catalog", lambda client: ({"KXCS2GAME": [m["ticker"]]}, meta, [("KXCS2GAME", m)])
    )
    monkeypatch.setattr(
        paper, "fit", lambda: {"fitted": 1410, "spread90": [980, 2040], "residual80": 0.56}
    )
    monkeypatch.setattr(paper, "roster_check", lambda client: ("frozen", False))

    def api(client, url, **kwargs):
        if "articles" in url:
            return {"content": "registered"}
        if url.endswith("orderbook"):
            return books
        return {"market": dict(m, status="finalized", settlement_value_dollars="1", result="yes")}

    monkeypatch.setattr(paper, "get", api)
    with sqlite3.connect(":memory:") as db:
        paper.initialize(db)
        first = paper.scan(db, None)
        assert first["rows"]["1"]["decision"] == "TAKE"
        clock[0] += timedelta(minutes=1)
        assert paper.scan(db, None)["rows"]["1"]["decision"] == "HOLD"
        clock[0] += timedelta(hours=2)
        g.update(winner="HEROIC", status="finished", score=[1, 0])
        final = paper.scan(db, None)
        paper.grade(db, None)
        paper.grade(db, None)
        summary = paper.report(db, final)
        assert (
            summary["ever_taken"]
            == summary["settled_entries"]
            == summary["n_scored"]
            == summary["clv_n"]
            == 1
        )
        assert summary["realized_net_usd"] == pytest.approx(6.44)
        assert summary["avg_clv_net_c"] == pytest.approx(-2.6)


def test_published_decisions_reproduce_from_frozen_observation():
    publication = paper.HERE / "published"
    scan = json.loads(gzip.decompress((publication / "scan.json.gz").read_bytes()))
    stats = json.loads((publication / "performance.json").read_text(encoding="utf-8"))
    assert paper.sheet(scan, stats) == (publication / "decisions.md").read_text(encoding="utf-8")
    model = fit()
    for row in scan["rows"].values():
        a, b = row["teams"]
        fair = forecast(a, b, row["bo"], model)
        assert fair == pytest.approx(row["fair"][a])
        multiplier = D(str(scan["series"]["KXCS2GAME"]["fee_multiplier"]))
        assert row["limits_c"] == {
            a: ceiling(fair["low"], multiplier),
            b: ceiling(1 - fair["high"], multiplier),
        }
