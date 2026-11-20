import json

import pytest
from streamlit.testing.v1 import AppTest

from engine.montecarlo import run_mc_progressive
from engine.teams import build_round1_pairs, load_stage
from odds.singapore_openers import parse_book
from scripts.singapore_stage1 import FIXTURE, FORECAST, ROOT, market_inputs
from ui.singapore_report import render, static_page


def test_seeded_openers_and_prices():
    teams, cfg = load_stage(FIXTURE)
    assert cfg["seeds_confirmed"] and not cfg["all_bo3"]
    assert [(a.name, b.name) for a, b in build_round1_pairs(teams)] == [
        ("NIP", "M80"), ("PVISION", "DENDELE"), ("HEROIC", "Imperial"), ("FaZe", "Wildcard"),
        ("Liquid", "GOSH"), ("Eternal Fire", "FlyQuest"), ("100 Thieves", "Chinggis Warriors"),
        ("9z", "Lynn Vision"),
    ]
    openers = json.loads(FIXTURE.read_text())["openers"]
    ratings, prices = market_inputs(teams, openers, 0.5)
    assert prices["7-15"][0] == pytest.approx(0.825)
    assert ratings[7] + ratings[15] == pytest.approx(teams[6].rating + teams[14].rating)
    with pytest.raises(ValueError):
        market_inputs(teams, openers[:-1] + [openers[0]], 0.5)


def test_multi_draw_progress_counts_tournaments():
    teams, _ = load_stage(FIXTURE)
    updates = list(run_mc_progressive(teams, None, 60, 6, {}, seed=17, n_chunks=2,
                                      market_blend={"1-9": (0.6, 0.01)}, k_epistemic=2))
    assert [u.done for u in updates] == [3, 6, 9, 12]
    assert all(sum(u.running_p_adv.values()) == pytest.approx(8) for u in updates)


def test_refresh_orients_the_named_side_and_rejects_a_prop():
    opener = {"teams": ["PVISION", "DENDELE"], "slug": "match"}
    market = dict(slug="match", sportsMarketType="moneyline", outcomes='["DENDELE CS", "PVISION"]',
                  acceptingOrders=True, bestBid=0.35, bestAsk=0.38, updatedAt="2026-11-19T20:00:00Z")
    event = {"slug": "match", "markets": [market]}
    quote = parse_book(event, opener)
    assert (quote["bid"], quote["ask"]) == pytest.approx((0.62, 0.65))
    market["sportsMarketType"] = "map_handicap"
    with pytest.raises(ValueError):
        parse_book(event, opener)


def test_published_card_matches_simulation_and_site():
    data = json.loads(FORECAST.read_text())
    picks = list(data["card"].values())
    assert list(map(len, picks)) == [2, 6, 2]
    assert len({name for group in picks for name in group}) == 10
    for key, total in (("sweep", 2), ("advance_pick", 6), ("winless", 2), ("qualify", 8)):
        assert sum(t[key] for t in data["teams"]) == pytest.approx(total)
    report = render(data, json.loads(FIXTURE.read_text()))
    assert static_page(report) == (ROOT / "public/index.html").read_text(encoding="utf-8")


def test_app_opens_singapore_and_reruns_without_cologne_caches():
    at = AppTest.from_file("app.py", default_timeout=30).run()
    assert not at.exception
    assert at.radio(key="major_event").value == "Singapore 2026"
    assert "Stage 1 Pick’Em" in at.get("html")[0].proto.body
    at.number_input[0].set_value(1000)
    at.button[0].click().run()
    assert not at.exception
    assert at.session_state["singapore_card"]["evaluation"]["n"] == 1000
    at.radio(key="major_event").set_value("Cologne 2026").run()
    assert not at.exception
    assert at.button(key="run_btn")
