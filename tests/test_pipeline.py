"""Monitor pipeline guards: map Kalshi markets to model probs, cost + rank, surface unmapped."""

from __future__ import annotations

import pytest

from engine.soccer.teams import SoccerTeam
from engine.soccer.tournament import TournamentResult
from monitor.pipeline import map_state_prob, model_prices, scan
from odds._match import build_name_to_id
from odds.kalshi import KalshiMarketState

TEAMS = [SoccerTeam(id=1, name="Brazil", group="C", elo=1991),
         SoccerTeam(id=2, name="Morocco", group="C", elo=1870)]

# Hand-built sample: Brazil champion 3/4, both always advance, Brazil always group winner.
_SIM = lambda champ: {  # noqa: E731
    "champion": champ,
    "group_rank": {1: 1, 2: 2},
    "stage_reached": {1: 6 if champ == 1 else 5, 2: 5 if champ == 2 else 1},
    "group_order": {"C": (1, 2)},
}
RESULT = TournamentResult(n=4, teams=[1, 2], sample=[_SIM(1), _SIM(1), _SIM(1), _SIM(2)])


def _state(market_type, yes_team, mid, ticker="T", spread=0.02, depth=5000.0):
    return KalshiMarketState(
        series_ticker="KX", event_ticker="E", ticker=ticker, market_type=market_type,
        title="", yes_sub_title=yes_team, yes_bid=mid - spread / 2, yes_ask=mid + spread / 2,
        mid=mid, spread=spread, depth=depth, status="open",
    )


def test_model_prices_tables_present():
    prices = model_prices(RESULT)
    assert prices["champion"][1] == pytest.approx(0.75)
    assert prices["group_winner"][1] == pytest.approx(1.0)
    assert prices["advance"][2] == pytest.approx(1.0)


def test_map_state_prob_resolves_team_and_type():
    prices = model_prices(RESULT)
    n2i = build_name_to_id(TEAMS)
    assert map_state_prob(_state("champion", "Brazil", 0.5), prices, n2i) == pytest.approx(0.75)
    # Unknown team and unpriceable type both map to None.
    assert map_state_prob(_state("champion", "Atlantis", 0.5), prices, n2i) is None
    assert map_state_prob(_state("match", "Brazil", 0.5), prices, n2i) is None


def test_scan_finds_edge_and_lists_unmapped():
    states = [
        _state("champion", "Brazil", 0.50, ticker="bra-champ"),   # model 0.75 -> strong YES edge
        _state("match", "Brazil", 0.50, ticker="bra-match"),       # per-match -> unmapped
    ]
    signals, unmapped = scan(states, RESULT, TEAMS, threshold=0.0)
    assert [s.ticker for s in signals] == ["bra-champ"]
    assert signals[0].side == "yes"
    assert [u.ticker for u in unmapped] == ["bra-match"]


def test_scan_threshold_drops_thin_edges():
    states = [_state("champion", "Brazil", 0.74, ticker="bra-champ")]  # model 0.75, ~0 net edge
    signals, _ = scan(states, RESULT, TEAMS, threshold=0.0)
    assert signals == []  # inside fee + spread
