"""Offline checks for the live watcher and pricer (no network)."""

import json

import numpy as np
import pytest

from analysis.singapore_live import feed, markets as mk, price
from analysis.singapore_live.names import canon
from analysis.singapore_live.watch import diff


def fx(key="s1-20", status="upcoming", score=(0, 0), maps=(("", 0, 0), ("", 0, 0), ("", 0, 0)),
       a="Imperial", b="FlyQuest", bo=3):
    return feed.Fixture(key, 1, "round 3", 3, bo, "2026-11-25T08:00:00+00:00", status, a, b, score, maps)


def test_names_cover_every_venue_spelling():
    for raw, want in [("Ninjas in Pyjamas", "NIP"), ("PVISION (PARIVISION)", "PVISION"), ("GOSH (BC.Game)", "GOSH"),
                      ("DENDELE CS", "DENDELE"), ("9z Globant", "9z"), ("Lynn Vision Gaming", "Lynn Vision"),
                      ("Team Liquid", "Liquid"), ("FaZe Clan", "FaZe"), ("Imperial Esports", "Imperial")]:
        assert canon(raw) == want
    with pytest.raises(KeyError):
        canon("Vitality")
    assert canon("Vitality", strict=False) == "Vitality"


def test_first_poll_is_silent_and_bo3_lifecycle_emits_each_event_once():
    at = "2026-11-25T08:05:00+00:00"
    assert diff(None, {"s1-20": fx()}, at=at) == []
    steps = [
        fx(status="live", maps=(("de_nuke", 3, 2), ("de_inferno", 0, 0), ("", 0, 0))),
        fx(status="live", score=(1, 0), maps=(("de_nuke", 13, 9), ("de_inferno", 0, 0), ("de_ancient", 0, 0))),
        fx(status="live", score=(1, 1), maps=(("de_nuke", 13, 9), ("de_inferno", 10, 13), ("de_ancient", 0, 0))),
        fx(status="end", score=(2, 1), maps=(("de_nuke", 13, 9), ("de_inferno", 10, 13), ("de_ancient", 16, 13))),
    ]
    prev, seen = fx(), []
    for cur in steps:
        seen += diff({"s1-20": prev}, {"s1-20": cur}, at=at)
        prev = cur
    kinds = [e["type"] for e in seen if e["type"] != "round_update"]
    assert kinds.count("match_start") == 1 and kinds.count("match_finish") == 1
    ends = [e for e in seen if e["type"] == "map_end"]
    assert [(e["map_index"], e["map_winner"]) for e in ends] == [(1, "Imperial"), (2, "FlyQuest"), (3, "Imperial")]
    assert seen[-1]["type"] == "match_finish" and seen[-1]["winner"] == "Imperial"


def test_missed_polls_still_produce_ordered_events():
    at = "2026-11-25T09:30:00+00:00"
    done = fx(status="end", score=(0, 2), maps=(("de_nuke", 5, 13), ("de_mirage", 11, 13), ("", 0, 0)))
    kinds = [e["type"] for e in diff({"s1-20": fx()}, {"s1-20": done}, at=at) if e["type"] != "round_update"]
    assert kinds == ["maps_set", "match_start", "map_end", "map_end", "match_finish"]


def test_draw_of_a_later_round_is_a_fixture_event():
    empty = fx(key="s1-24", a=None, b=None)
    drawn = fx(key="s1-24", a="NIP", b="FlyQuest")
    events = diff({"s1-24": empty}, {"s1-24": drawn}, at="2026-11-25T13:00:00+00:00")
    assert [e["type"] for e in events] == ["fixture_set"]


def test_fees_and_book_walks():
    assert mk.poly_fee(0.5, 100) == pytest.approx(1.25)  # docs table: 100 shares at 50c, rate 0.05
    assert mk.poly_fee(0.3, 100) == pytest.approx(mk.poly_fee(0.7, 100))
    assert mk.walk_asks([(0.40, 5), (0.42, 10)], 10) == pytest.approx((5 * 0.40 + 5 * 0.42) / 10)
    assert mk.walk_asks([(0.40, 5)], 10) is None
    cost = price.taker_cost_poly({"asks": [(0.40, 5), (0.42, 10)]}, 10, 0.05)
    assert cost["unit"] == pytest.approx(cost["avg"] + (5 * 0.05 * 0.4 * 0.6 + 5 * 0.05 * 0.42 * 0.58) / 10)


def test_bo3_inversion_round_trips():
    for p in (0.1, 0.35, 0.5, 0.8, 0.97):
        q = price.bo3_to_map(p)
        assert q * q * (3 - 2 * q) == pytest.approx(p, abs=1e-9)


def test_strength_fit_reproduces_a_single_price_when_the_prior_is_weak():
    from engine.probs import p_map
    from engine.teams import load_stage

    teams, _ = load_stage(price.FIXTURE)
    a, b = teams[0], teams[8]
    fit = price.fit_strengths(teams, [(a.id, b.id, 0.70, 1)], scale=1.0, lam=1e-6)
    assert p_map(fit[a.id], fit[b.id], price.S) == pytest.approx(0.70, abs=1e-4)
    # A heavier prior pulls the gap back toward the Nov 19 points.
    sticky = price.fit_strengths(teams, [(a.id, b.id, 0.70, 1)], scale=1.0, lam=5.0)
    assert abs(sticky[a.id] - sticky[b.id] - (a.rating - b.rating)) < abs(fit[a.id] - fit[b.id] - (a.rating - b.rating))


def test_simulated_records_respect_stage_totals():
    from engine.montecarlo import run_mc
    from engine.teams import load_stage

    teams, _ = load_stage(price.FIXTURE)
    res = run_mc(teams, None, price.S, 4000, {}, seed=3)
    fair, arr = price.records(res.sample, [t.id for t in teams])
    totals = {fam: sum(fair[t.id][fam] for t in teams) for fam in price.RECORDS}
    assert totals == pytest.approx({"3-0": 2, "3-1": 3, "3-2": 3, "0-3": 2, "qualify": 8})
    assert arr.shape == (4000, 16, 2)
