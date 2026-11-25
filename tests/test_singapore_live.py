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


def test_map_score_probabilities_reconcile_the_series_price():
    r = 0.55
    s0 = price.bo3_to_map  # noqa: F841  (inverse used elsewhere)
    pre = r * r * (3 - 2 * r)
    p = price.map_score_probs(pre, r, (0, 0))
    assert p["sweep_a"] + p["sweep_b"] + p["over"] == pytest.approx(1)
    assert p["sweep_a"] == pytest.approx(r * r) and p["over"] == pytest.approx(2 * r * (1 - r))
    # Leading 1-0 while trailing badly on map 2: the live series price implies a low map-2 chance,
    # so three maps become likely even though fresh maps stay at r.
    q = 0.15
    live = q + (1 - q) * r
    p = price.map_score_probs(live, r, (1, 0))
    assert p["sweep_a"] == pytest.approx(q) and p["over"] == pytest.approx(1 - q) and p["sweep_b"] == 0
    p = price.map_score_probs(0.2, r, (0, 1))
    assert p["over"] == pytest.approx(0.2 / r) and p["sweep_b"] == pytest.approx(1 - 0.2 / r)
    assert price.map_score_probs(0.6, r, (1, 1))["over"] == 1.0
    assert price.map_score_probs(1.0, r, (2, 1)) == {"sweep_a": 0.0, "sweep_b": 0.0, "over": 1.0}


def test_push_text_is_one_short_line():
    from analysis.singapore_live.watch import push_text

    events = [{"type": "map_end", "a": "Imperial", "b": "FlyQuest", "bo": 3, "round": 3, "score": [1, 0],
               "map_index": 1, "map": "de_nuke", "rounds": [13, 9]},
              {"type": "match_start", "a": "NIP", "b": "Liquid", "bo": 3, "round": 3, "score": [0, 0]}]
    text = push_text(events, {"ok": True, "pickem_p_ge5": 0.098, "new": ["qualify FlyQuest YES @0.62 fair 0.70 in-play"]})
    assert "\n" not in text and len(text) <= 195
    assert text.startswith("Imperial 1-0 FlyQuest after map 1 Nuke 13-9") and "PickEm 10%" in text
    assert push_text([], None) is None


def test_map_markets_bind_to_the_fixture_and_skip_unknown_contracts(monkeypatch):
    pages = {
        "KXCS2TOTALMAPS": [
            {"event_ticker": "KXCS2TOTALMAPS-26NOV250530TLNIP", "title": "Liquid vs. NIP: Total Maps",
             "markets": [{"ticker": "T-3", "yes_sub_title": "Over 2.5 maps", "status": "active"}]},
            {"event_ticker": "KXCS2TOTALMAPS-26NOV290300TLNIP", "title": "Liquid vs. NIP: Total Maps",
             "markets": [{"ticker": "T-rematch", "yes_sub_title": "Over 2.5 maps", "status": "active"},
                         {"ticker": "T-odd", "yes_sub_title": "Over 3.5 maps", "status": "active"}]},
        ],
        "KXCS2SPREAD": [
            {"event_ticker": "KXCS2SPREAD-26NOV250530TLNIP", "title": "Liquid vs. NIP: Spread",
             "markets": [{"ticker": "S-TL", "yes_sub_title": "Liquid wins by over 1.5 maps", "status": "active"},
                         {"ticker": "S-odd", "yes_sub_title": "Someone else wins by over 1.5 maps", "status": "active"}]},
        ],
    }
    monkeypatch.setattr(mk, "_json", lambda client, method, url, params=None, **_: {"events": pages[params["series_ticker"]]})
    rows = mk.kalshi_bo3_markets(None)[frozenset(("Liquid", "NIP"))]
    assert {r["market"] for r in rows} == {"T-3", "T-rematch", "S-TL"}  # unknown wording skipped, no crash
    f = fx(key="s1-22", a="NIP", b="Liquid")
    km = {"s1-22": {"event": "KXCS2GAME-26NOV250530TLNIP"}}
    bound = price.fixture_map_markets(f, mk.kalshi_bo3_markets(None), km)
    assert {r["market"] for r in bound} == {"T-3", "S-TL"}  # the later rematch listing is excluded
    assert price.fixture_map_markets(f, mk.kalshi_bo3_markets(None), {}) == []


def test_series_score_after_each_map_when_two_maps_end_between_polls():
    from analysis.singapore_live.watch import push_text

    at = "2026-11-25T09:30:00+00:00"
    before = fx(status="live", maps=(("de_nuke", 3, 2), ("", 0, 0), ("", 0, 0)))
    after = fx(status="live", score=(1, 1), maps=(("de_nuke", 13, 9), ("de_inferno", 7, 13), ("", 0, 0)))
    ends = [e for e in diff({"s1-20": before}, {"s1-20": after}, at=at) if e["type"] == "map_end"]
    assert [e["series_after"] for e in ends] == [[1, 0], [1, 1]]
    assert push_text(ends[:1], None).startswith("Imperial 1-0 FlyQuest after map 1 Nuke 13-9")


def _bo3(status, games, t1="Imperial", t2="FlyQuest", s=(0, 0), bo=3, start="2026-11-25T08:00:00.000+00:00"):
    return {"status": status, "bo_type": bo, "start_date": start, "team1": {"name": t1}, "team2": {"name": t2},
            "team1_score": s[0], "team2_score": s[1], "games": games}


def test_bo3_overlay_drives_start_map_end_and_finish_while_pgl_lags():
    pgl = {"s1-20": fx()}  # PGL still shows the match as upcoming throughout
    at = "2026-11-25T08:40:00+00:00"
    live = feed.overlay(pgl, {1: [_bo3("current", [{"number": 1, "status": "current", "map_name": "de_nuke"}])]})
    assert live["s1-20"].status == "live" and live["s1-20"].maps[0] == ("de_nuke", 0, 0)
    first = feed.overlay(pgl, {1: [_bo3("current", [
        {"number": 1, "status": "finished", "map_name": "de_nuke", "winner_clan_name": "FlyQuest",
         "winner_clan_score": 13, "loser_clan_score": 9},
        {"number": 2, "status": "current", "map_name": "de_inferno"}], t1="FlyQuest", t2="Imperial Esports")]})
    assert first["s1-20"].score == (0, 1) and first["s1-20"].maps[0] == ("de_nuke", 9, 13)
    done = feed.overlay(pgl, {1: [_bo3("finished", [
        {"number": 1, "status": "finished", "map_name": "de_nuke", "winner_clan_name": "FlyQuest",
         "winner_clan_score": 13, "loser_clan_score": 9},
        {"number": 2, "status": "finished", "map_name": "de_inferno", "winner_clan_name": "FlyQuest",
         "winner_clan_score": 13, "loser_clan_score": 5}], t1="FlyQuest", t2="Imperial", s=(2, 0))]})
    assert done["s1-20"].status == "end" and done["s1-20"].score == (0, 2) and done["s1-20"].winner == "FlyQuest"
    kinds = []
    for prev, cur in ((pgl, live), (live, first), (first, done)):
        kinds += [e["type"] for e in diff(prev, cur, at=at) if e["type"] not in ("round_update", "maps_set")]
    assert kinds == ["match_start", "map_end", "map_end", "match_finish"]


def test_bo3_overlay_defers_to_pgl_and_ignores_mismatches():
    ended = fx(status="end", score=(2, 1), maps=(("de_nuke", 13, 9), ("de_inferno", 9, 13), ("de_ancient", 13, 7)))
    record = _bo3("finished", [], s=(0, 2))
    assert feed.overlay({"s1-20": ended}, {1: [record]})["s1-20"] == ended  # PGL's result stands
    upcoming = fx()
    assert feed.overlay({"s1-20": upcoming}, {1: [_bo3("current", [], t2="NIP")]})["s1-20"] == upcoming
    assert feed.overlay({"s1-20": upcoming}, {1: [_bo3("current", [], start="2026-11-29T08:00:00.000+00:00")]})["s1-20"] == upcoming
    assert feed.overlay({"s1-20": upcoming}, {1: [_bo3("current", [], bo=1)]})["s1-20"] == upcoming
    assert feed.overlay({"s1-20": upcoming}, {1: [_bo3("finished", [], s=(1, 1))]})["s1-20"] == upcoming
    twice = [_bo3("current", []), _bo3("current", [])]
    assert feed.overlay({"s1-20": upcoming}, {1: twice})["s1-20"] == upcoming  # ambiguous: no overlay


def test_a_flapping_start_is_reported_once(monkeypatch, tmp_path):
    from analysis.singapore_live import watch

    monkeypatch.setattr(watch, "STATE", tmp_path)
    upcoming, live = fx(key="s1-18", bo=1, maps=(("", 0, 0),)), fx(key="s1-18", bo=1, status="live", maps=(("de_nuke", 0, 0),))
    states = iter([upcoming, live, upcoming, live])
    monkeypatch.setattr(watch.feed, "fetch", lambda *_: ({"s1-18": next(states)}, {1: "t"}))
    for _ in range(4):
        watch.main(["--once", "--no-track-prices", "--price-on", "", "--price-every-live", "0"])
    starts = [json.loads(x) for x in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert [e["type"] for e in starts if e["type"] == "match_start"] == ["match_start"]
