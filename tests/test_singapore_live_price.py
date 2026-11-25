"""Offline regression cases for live-state conditioning and prospective paper fills."""

import json
from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import numpy as np
import pytest

from analysis.singapore_live import feed, price, watch
from engine.swiss import simulate_stage
from engine.teams import Team, load_stage


@pytest.fixture(autouse=True)
def _no_kalshi_map_markets(monkeypatch):
    """Keep these cases offline: the map-score family is covered in test_singapore_live.py."""
    monkeypatch.setattr(price.mk, "kalshi_bo3_markets", lambda *_: {})
    monkeypatch.setattr(price.mk, "kalshi_series_multiplier", lambda *_: Decimal("1"))


def stage_at_round_three():
    teams, _ = load_stage(price.FIXTURE)
    by_id = {t.id: t for t in teams}
    fixtures, locks, wins = {}, {}, {t.id: 0 for t in teams}
    for rnd in (1, 2, 3):
        pairings = []
        fresh = [Team(t.id, t.name, t.seed, t.rating) for t in teams]
        simulate_stage(fresh, None, price.S, np.random.default_rng(0), locks, pairings_out=pairings)
        for pair in pairings[rnd - 1]:
            a, b = sorted(pair)
            key = f"r{rnd}-{a}-{b}"
            decider = wins[a] in (0, 2) and rnd == 3
            f = feed.Fixture(key, 1, f"round {rnd}", rnd, 3 if decider else 1,
                             "2026-11-25T00:00:00+00:00", "upcoming", by_id[a].name, by_id[b].name,
                             (0, 0), ())
            if rnd < 3:
                locks[pair] = a
                wins[a] += 1
                f = replace(f, status="end", score=(1, 0))
            elif wins[a] == 2:
                target = f
            fixtures[key] = f
    return fixtures, target


def poly_market(team):
    return {"venue": "polymarket", "market": "target-3-0", "family": "3-0", "team": team,
            "question": "Stage 1 record?", "rules": "Finishes Stage 1 at 3-0", "tokens": ["yes", "no"],
            "closed": False, "accepting": True, "volume": 100, "fee_rate": 0.05}


def book(ask, shares=100):
    return {"bids": [(ask / 2, shares)], "asks": [(ask, shares)]}


def test_snapshot_conditions_the_break_and_holds_mid_map(monkeypatch, tmp_path):
    fixtures, f = stage_at_round_three()
    # This case exercises map-break conditioning through a Polymarket market; the live default
    # records Kalshi entries only.
    monkeypatch.setattr(price, "PAPER_VENUES", {"kalshi", "polymarket"})
    monkeypatch.setattr(price, "STATE", tmp_path)
    monkeypatch.setattr(watch, "STATE", tmp_path)
    monkeypatch.setattr(price, "N_SIMS", 1600)
    monkeypatch.setattr(price, "SCENARIOS", {"base": (1.0, 0.3)})
    monkeypatch.setattr(feed, "fetch", lambda *_: (fixtures, {1: "test"}))
    monkeypatch.setattr(price.mk, "poly_events", lambda *_: [])
    monkeypatch.setattr(price.mk, "poly_matches", lambda *_: {})
    monkeypatch.setattr(price.mk, "poly_derivatives", lambda *_: [poly_market(f.a)])
    monkeypatch.setattr(price.mk, "kalshi_matches", lambda *_: {})
    monkeypatch.setattr(price.mk, "kalshi_s2", lambda *_: ([], Decimal("1")))
    monkeypatch.setattr(price.mk, "poly_books", lambda client, tokens: {t: book(.01) for t in tokens})
    probs = []
    for score, first in [((1, 0), (13, 8)), ((0, 1), (8, 13))]:
        fixtures[f.key] = replace(f, status="upcoming", score=score, underway=False,  # bo3.gg: between maps
                                  maps=(("nuke", *first), ("dust2", 0, 0), ("inferno", 0, 0)))
        snap = price.snapshot("map_end", quiet=True)
        probs.append(snap["quotes"][0]["fair"])
        row = next(row for row in snap["matches"] if row["key"] == f.key)
        assert row["source"] == "remaining maps" and row["score"] == list(score)
        assert row["p_a_low"] <= row["p_a"] <= row["p_a_high"]
        assert all(s["in_play"] for s in snap["signals"])
    assert probs[0] > probs[1] + .25
    entries = (tmp_path / "entries.jsonl").read_text()
    fixtures[f.key] = replace(fixtures[f.key], maps=(("nuke", 8, 13), ("dust2", 2, 4), ("inferno", 0, 0)))
    snap = price.snapshot("round_update", quiet=True)
    assert f.key in snap["entry_hold"]
    assert snap["signals"] == [] and snap["pickem"] is None
    assert (tmp_path / "entries.jsonl").read_text() == entries
    assert not price.at_map_break(replace(fixtures[f.key], maps=(("nuke", 8, 13),)))


def test_score_lag_keeps_in_play_price_out_of_prematch_strengths(monkeypatch, tmp_path):
    fixtures, f = stage_at_round_three()
    fixtures[f.key] = replace(f, status="upcoming", maps=(("nuke", 8, 1),))
    monkeypatch.setattr(price, "STATE", tmp_path)
    monkeypatch.setattr(watch, "STATE", tmp_path)
    monkeypatch.setattr(feed, "fetch", lambda *_: (fixtures, {}))
    monkeypatch.setattr(price.mk, "poly_events", lambda *_: [])
    moneyline = {"closed": False, "accepting": True, "outcomes": [f.a, f.b], "tokens": ["a", "b"],
                 "bo": 3, "start": f.start, "slug": "fixture"}
    monkeypatch.setattr(price.mk, "poly_matches", lambda *_: {(1, frozenset((f.a, f.b))): moneyline})
    monkeypatch.setattr(price.mk, "poly_derivatives", lambda *_: [])
    monkeypatch.setattr(price.mk, "poly_books", lambda *_: {"a": {"bids": [(.9, 10)], "asks": [(.92, 10)]}})
    monkeypatch.setattr(price.mk, "kalshi_matches", lambda *_: {})
    monkeypatch.setattr(price.mk, "kalshi_s2", lambda *_: ([], Decimal("1")))
    monkeypatch.setattr(price, "closing_price", lambda *_: .42)
    fit = price.fit_strengths
    def check_inputs(teams, observations, scale, lam):
        assert [o[2] for o in observations] == [.42]
        return fit(teams, observations, scale, lam)
    monkeypatch.setattr(price, "fit_strengths", check_inputs)
    monkeypatch.setattr(price, "N_SIMS", 20)
    snap = price.snapshot("tick", quiet=True)
    assert next(row for row in snap["matches"] if row["key"] == f.key)["p_a"] == pytest.approx(.91)


@pytest.mark.parametrize("venue", ["polymarket", "kalshi"])
@pytest.mark.parametrize("change", ["better", "worse", "thin", "closed", "terms", "score"])
def test_freeze_rechecks_size_price_terms_and_pgl(venue, change, monkeypatch):
    fixtures, f = stage_at_round_three()
    poly = poly_market(f.a)
    km = {"venue": "kalshi", "family": "qualify", "team": f.a, "market": "qual-K",
          "rules": "Advances to Stage 2", "status": "active"}
    original = poly if venue == "polymarket" else km
    fresh = dict(original)
    if change == "closed":
        fresh.update(closed=True, accepting=False, status="finalized")
    if change == "terms":
        fresh["rules"] = "Other settlement"
    signal = {"venue": venue, "market": original["market"], "side": "yes", "shares": 20 if venue == "polymarket" else 10,
              "worst_fair": .6, "unit_cost": .5, "avg": .49, "edge": .1}
    if venue == "polymarket":
        signal["token"] = "yes"
    ask = .90 if change == "worse" else .4
    qty = 1 if change == "thin" else 100
    monkeypatch.setattr(price.mk, "poly_events", lambda *_: [])
    monkeypatch.setattr(price.mk, "poly_derivatives", lambda *_: [fresh])
    monkeypatch.setattr(price.mk, "poly_books", lambda *_: {"yes": book(ask, qty)})
    monkeypatch.setattr(price.mk, "kalshi_s2", lambda *_: ([fresh], Decimal("1")))
    monkeypatch.setattr(price.mk, "kalshi_book", lambda *_: {"no_dollars": [[round(1-ask, 2), qty]]})
    checked = dict(fixtures)
    if change == "score":
        checked[f.key] = replace(f, status="live", maps=(("nuke", 4, 1),))
    monkeypatch.setattr(feed, "fetch", lambda *_: (checked, {}))
    entries, hold = price.confirm_signals(None, [signal], fixtures, {}, {(venue, original["market"]): original})
    if change == "better":
        assert len(entries) == 1 and hold is None
        entry = entries[0]
        assert entry["avg"] == .4
        assert entry["unit_cost"] == pytest.approx(.412 if venue == "polymarket" else .417)
        assert entry["edge"] == pytest.approx(.6 - entry["unit_cost"])
        assert datetime.fromisoformat(entry["quote_observed_at"]) <= datetime.fromisoformat(entry["state_observed_at"])
        assert entry["at"] == entry["state_observed_at"]
    else:
        assert entries == []


def test_live_input_moves_before_freeze(monkeypatch):
    fixtures, f = stage_at_round_three()
    poly = poly_market(f.a)
    signal = {"venue": "polymarket", "market": poly["market"], "token": "yes", "side": "yes", "shares": 20,
              "worst_fair": .9}
    monkeypatch.setattr(price.mk, "poly_events", lambda *_: [])
    monkeypatch.setattr(price.mk, "poly_derivatives", lambda *_: [poly])
    monkeypatch.setattr(price.mk, "poly_matches", lambda *_: {})
    monkeypatch.setattr(price.mk, "poly_books", lambda *_: {"yes": book(.1)})
    monkeypatch.setattr(price.mk, "kalshi_matches", lambda *_: {f.key: {"quotes": {f.a: (.43, .45)}}})
    entries, hold = price.confirm_signals(None, [signal], fixtures, {f.key: .8}, {("polymarket", poly["market"]): poly})
    assert not entries and "live match price changed" in hold


def test_fee_refresh_uses_full_precision_for_edge(monkeypatch):
    poly = poly_market("NIP")
    fresh = {**poly, "fee_rate": .05}
    original = {**poly, "fee_rate": 0.0}
    # 40-cent takes cost .412 after fees; rounding fair first would create a 2c signal.
    signal = {"venue": "polymarket", "market": poly["market"], "side": "yes", "shares": 20,
              "token": "yes", "worst_fair": .431999, "unit_cost": .4}
    monkeypatch.setattr(price.mk, "poly_events", lambda *_: [])
    monkeypatch.setattr(price.mk, "poly_derivatives", lambda *_: [fresh])
    monkeypatch.setattr(price.mk, "poly_books", lambda *_: {"yes": book(.4)})
    monkeypatch.setattr(feed, "fetch", lambda *_: ({}, {}))
    entries, _ = price.confirm_signals(None, [signal], {}, {}, {("polymarket", poly["market"]): original})
    assert entries == []


def test_grade_on_fresh_checkout(monkeypatch, tmp_path):
    state = tmp_path / "state"
    monkeypatch.setattr(price, "STATE", state)
    monkeypatch.setattr(feed, "fetch", lambda *_: ({}, {}))
    assert price.grade()["entries"] == 0
    assert json.loads((state / "graded.json").read_text())["settled"] == 0


def test_small_live_move_raises_the_bar_instead_of_blocking(monkeypatch):
    """In-play prices tick constantly; a move within tolerance only raises the required edge."""
    fixtures, f = stage_at_round_three()
    poly = poly_market(f.a)
    monkeypatch.setattr(price.mk, "poly_events", lambda *_: [])
    monkeypatch.setattr(price.mk, "poly_derivatives", lambda *_: [poly])
    monkeypatch.setattr(price.mk, "poly_matches", lambda *_: {})
    monkeypatch.setattr(price.mk, "poly_books", lambda *_: {"yes": book(.5)})
    monkeypatch.setattr(price.mk, "kalshi_matches", lambda *_: {f.key: {"quotes": {f.a: (.80, .82)}}})
    monkeypatch.setattr(feed, "fetch", lambda *_: (fixtures, {1: "test"}))
    terms = {("polymarket", poly["market"]): poly}
    cost = .5 + .05 * .5 * .5
    # The quote moved 1 cent (0.80 -> 0.81). An edge of 2.5 cents fails (needs 2 + 1); 3.5 passes.
    thin = {"venue": "polymarket", "market": poly["market"], "token": "yes", "side": "yes", "shares": 20,
            "worst_fair": cost + .025}
    assert price.confirm_signals(None, [thin], fixtures, {f.key: .80}, terms)[0] == []
    wide = {**thin, "worst_fair": cost + .035}
    entries, hold = price.confirm_signals(None, [wide], fixtures, {f.key: .80}, terms)
    assert hold is None and len(entries) == 1 and entries[0]["live_price_drift"] == pytest.approx(.01)
