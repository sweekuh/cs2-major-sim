"""Monitor pipeline: simulated market probabilities -> ranked edges vs live Kalshi prices.

The glue that makes this a monitor. Given a ``TournamentResult`` (one Monte-Carlo run prices every
futures market) and a list of live ``KalshiMarketState``, map each market to its model probability
by ``market_type`` + the team in ``yes_sub_title``, then cost and rank the edges via
``monitor.edge.find_edges``. Anything we can't map (unknown team, or a per-match 1X2 market that
needs the calibrated match model rather than the tournament sample) is returned in ``unmapped`` —
never silently dropped (PRD R3).
"""

from __future__ import annotations

from engine.soccer.markets import (
    p_advance,
    p_champion,
    p_eliminated_in_group,
    p_group_winner,
)
from engine.soccer.tournament import TournamentResult
from monitor.edge import EdgeSignal, find_edges
from odds._match import build_name_to_id, resolve_id
from odds.kalshi import KalshiMarketState

# Kalshi market_type (from classify_series) -> the model price table keyed by team id.
_PRICEABLE = {"champion", "group_winner", "advance", "eliminated_in_group"}


def model_prices(result: TournamentResult) -> dict[str, dict[int, float]]:
    """Precompute every futures price table off one tournament sample, keyed by market_type."""
    return {
        "champion": p_champion(result),
        "group_winner": p_group_winner(result),
        "advance": p_advance(result),
        "eliminated_in_group": p_eliminated_in_group(result),
    }


def map_state_prob(state: KalshiMarketState, prices: dict[str, dict[int, float]],
                   name_to_id: dict[str, int]) -> float | None:
    """Resolve one market's YES model probability, or None if it can't be priced from the sample."""
    table = prices.get(state.market_type)
    if table is None:
        return None
    team_id = resolve_id(state.yes_sub_title, name_to_id)
    if team_id is None:
        return None
    return table.get(team_id)


def scan(states, result: TournamentResult, teams, *, threshold: float = 0.0,
         maker: bool = False) -> tuple[list[EdgeSignal], list[KalshiMarketState]]:
    """Map + cost + rank every market against the model. Returns (ranked signals, unmapped states)."""
    prices = model_prices(result)
    name_to_id = build_name_to_id(teams)
    pairs: list[tuple[float, KalshiMarketState]] = []
    unmapped: list[KalshiMarketState] = []
    for s in states:
        mp = map_state_prob(s, prices, name_to_id)
        if mp is None:
            unmapped.append(s)
        else:
            pairs.append((mp, s))
    return find_edges(pairs, threshold=threshold, maker=maker), unmapped
