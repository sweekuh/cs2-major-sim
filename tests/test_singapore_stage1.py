import json
from datetime import datetime

import pytest
from streamlit.testing.v1 import AppTest

from engine.montecarlo import run_mc_progressive
from engine.teams import build_round1_pairs, load_stage
from odds.singapore_openers import parse_book
from scripts.singapore_stage1 import FIXTURE, FORECAST, ROOT, market_inputs
from scripts.validate_singapore import AUDIT, EVIDENCE, read, validate
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
    now = datetime.fromisoformat("2026-11-19T20:01:00Z")
    for changes in ({"bestBid": 0.01}, {"volumeNum": 20}, {"updatedAt": "2026-11-19T17:00:00Z"}):
        bad = {**market, "volumeNum": 150, **changes}
        with pytest.raises(ValueError):
            parse_book({**event, "markets": [bad]}, opener, observed_at=now)
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


def test_replay_and_time_ordered_model_selection():
    regenerated = validate()
    stored = read(AUDIT)
    assert regenerated["chosen"] == stored["chosen"]
    assert regenerated["development_candidate"] == stored["development_candidate"]
    assert regenerated["singapore_form"] == pytest.approx(stored["singapore_form"])
    for event, result in regenerated["events"].items():
        assert result["replayed"] == [8, 8, 8, 6, 3]
        for model, scores in result["scores"].items():
            for subset, metrics in scores.items():
                assert metrics == pytest.approx(stored["events"][event]["scores"][model][subset])
    rosters = read(EVIDENCE / "singapore-rosters.json")["registered_starting_five"]
    assert set(rosters) == {t.name for t in load_stage(FIXTURE)[0]}
    assert all(len(set(five)) == 5 for five in rosters.values())
    assert "history" in rosters["9z"] and "meyern" not in rosters["9z"]


def test_card_is_chosen_and_scored_across_weighted_spreads():
    from scripts.singapore_stage1 import SPREAD_GRID, allocate

    weights = read(AUDIT)["spread_weights"]
    assert [int(s) for s in weights] == [round(s * 10) for s in SPREAD_GRID]
    assert sum(weights.values()) == pytest.approx(1) and min(weights.values()) > 0
    counts = allocate(1000, {float(s) / 10: w for s, w in weights.items()})
    assert sum(counts.values()) == 1000
    assert max(counts, key=counts.get) * 10 == float(max(weights, key=weights.get))
    data = read(FORECAST)
    assert list(data["by_spread"]) == list(weights)
    mixed = sum(s["weight"] * s["p_ge5"] for s in data["by_spread"].values())
    # The pooled evaluation and the weighted single-spread runs are separate samples of one mixture.
    assert data["evaluation"]["p_ge5"] == pytest.approx(mixed, abs=0.01)


def test_paired_card_and_price_scenarios():
    data = read(FORECAST)
    swap = data["closest_swap"]
    assert swap["card_minus_alternative"] == pytest.approx(
        (swap["card_only"] - swap["alternative_only"]) / swap["n"])
    assert data["evaluation"]["p_ge5"] - swap["p_ge5"] == pytest.approx(swap["card_minus_alternative"])
    assert swap["out"] in data["card"][swap["bucket"]]
    assert swap["in"] not in [name for group in data["card"].values() for name in group]
    assert all(row["team"] == swap["in"] and row["current"] != row["tested"] for row in data["line_tests"])
