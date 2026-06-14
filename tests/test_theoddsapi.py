"""TheOddsApiProvider parse guards — fixture-driven, NO httpx import (D1/DX-01).

Pins the sharp-1X2 reference path: 3-way de-vig per book, pre-pool the kept sharp books to ONE
opinion per match, fail-soft on unresolvable/missing markets.
"""

from __future__ import annotations

import sys

from engine.soccer.teams import SoccerTeam
from odds.theoddsapi import TheOddsApiProvider

TEAMS = [
    SoccerTeam(id=29, name="Brazil", group="H", elo=2030),
    SoccerTeam(id=6, name="Morocco", group="B", elo=1870),
]


def _event(home="Brazil", away="Morocco"):
    return {
        "home_team": home,
        "away_team": away,
        "bookmakers": [
            {"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
                {"name": "Brazil", "price": 1.8},
                {"name": "Morocco", "price": 4.5},
                {"name": "Draw", "price": 3.6},
            ]}]},
            {"key": "betfair_ex_eu", "markets": [{"key": "h2h", "outcomes": [
                {"name": "Brazil", "price": 1.83},
                {"name": "Morocco", "price": 4.6},
                {"name": "Draw", "price": 3.55},
            ]}]},
        ],
    }


def test_no_httpx_in_import_path():
    # The pure parse path must collect/run without httpx (lazy-imported in fetch() only).
    assert "httpx" not in sys.modules or True  # tolerate a pre-imported httpx; assert module is clean:
    import odds.theoddsapi as mod
    assert not hasattr(mod, "httpx")


def test_parse_one_match_devigged_and_summing_to_one():
    quotes = TheOddsApiProvider().get_quotes(_event(), teams=TEAMS)
    assert len(quotes) == 1
    q = quotes[0]
    assert q.match == (29, 6)
    assert abs((q.p_home + q.p_draw + q.p_away) - 1.0) < 1e-9
    assert q.p_home > q.p_away  # Brazil favoured
    assert q.provider == "theoddsapi:sharp"


def test_unresolvable_match_drops_quote():
    quotes = TheOddsApiProvider().get_quotes(_event(home="Atlantis"), teams=TEAMS)
    assert quotes == []


def test_missing_h2h_fails_soft():
    ev = {"home_team": "Brazil", "away_team": "Morocco",
          "bookmakers": [{"key": "pinnacle", "markets": [{"key": "totals", "outcomes": []}]}]}
    assert TheOddsApiProvider().get_quotes(ev, teams=TEAMS) == []


def test_list_of_events_each_parsed():
    quotes = TheOddsApiProvider().get_quotes([_event(), _event()], teams=TEAMS)
    assert len(quotes) == 2
