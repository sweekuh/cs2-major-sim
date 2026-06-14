"""Edge detection + ranking (the monitor core): model fair value vs a live Kalshi price.

Given a model probability for a market's YES outcome and the live ``KalshiMarketState`` (mid,
spread, depth), compute the COSTED net edge with the exact Kalshi fee, choose the side, and rank
candidates by ``net_edge x log1p(depth)`` so thin books are down-weighted. This is where the
simulation's market probabilities (``engine.soccer.markets``) meet live prices.

Pairing each Kalshi ticker to the right model probability happens upstream (the ticker→outcome
map); this layer takes (model_prob, state) pairs and emits ranked, threshold-gated signals.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from monitor.fees import net_edge
from odds.kalshi import KalshiMarketState


@dataclass(frozen=True)
class EdgeSignal:
    """A costed edge candidate. ``side`` is the contract to buy (yes if the model thinks YES is
    underpriced, else no); ``net_edge`` already subtracts fee + half-spread; ``score`` ranks it."""

    ticker: str
    market_type: str
    side: str
    model_prob: float
    mid: float
    spread: float
    depth: float
    net_edge: float
    score: float


def evaluate(model_prob: float, state: KalshiMarketState, *, maker: bool = False) -> EdgeSignal:
    """Cost out one (model_prob, market) pair into an EdgeSignal (no threshold applied here)."""
    side = "yes" if model_prob > state.mid else "no"
    ne = net_edge(model_prob, state.mid, state.spread, maker=maker)
    score = ne * math.log1p(max(0.0, state.depth))
    return EdgeSignal(
        ticker=state.ticker, market_type=state.market_type, side=side,
        model_prob=model_prob, mid=state.mid, spread=state.spread, depth=state.depth,
        net_edge=ne, score=score,
    )


def find_edges(pairs, *, threshold: float = 0.0, maker: bool = False) -> list[EdgeSignal]:
    """Cost every (model_prob, KalshiMarketState) pair, keep those with net edge > ``threshold``,
    and return them ranked best-first by ``net_edge x log1p(depth)``."""
    signals = [evaluate(p, s, maker=maker) for p, s in pairs]
    kept = [s for s in signals if s.net_edge > threshold]
    return sorted(kept, key=lambda s: s.score, reverse=True)
