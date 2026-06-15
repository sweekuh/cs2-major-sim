"""Per-match prediction + EV (Phase 1 iteration): price a single fixture and value bets on it.

The tournament sample prices futures; this prices a single match's 1X2 directly off the match
model (the path the pipeline left ``unmapped``). EV helpers value a bet given either decimal
sportsbook odds or a Kalshi YES price (net of the exact Kalshi fee).
"""

from __future__ import annotations

from engine.soccer.dixon_coles import MatchModel, match_1x2
from monitor.fees import per_contract_fee

_OUTCOMES = ("home", "draw", "away")


def match_prediction(model: MatchModel, home_id: int, away_id: int, *, neutral: bool = True) -> dict:
    """Model 1X2 for a fixture + the most likely outcome. ``neutral=False`` applies home advantage."""
    probs = dict(zip(_OUTCOMES, match_1x2(model, home_id, away_id, neutral=neutral)))
    pick = max(probs, key=probs.get)
    return {"probs": probs, "pick": pick, "pick_prob": probs[pick]}


def decimal_ev(model_prob: float, decimal_odds: float) -> float:
    """EV per $1 staked at decimal odds: ``p * odds - 1`` (sportsbook). >0 means +EV."""
    return model_prob * decimal_odds - 1.0


def kalshi_ev(model_prob: float, yes_price: float, *, maker: bool = False) -> float:
    """Net EV per $1 Kalshi YES contract bought at ``yes_price``: ``p - price - fee``.

    A YES contract costs ``yes_price`` and pays $1 if the outcome happens, so gross EV is
    ``p - price``; subtract the exact per-contract Kalshi fee at that price.
    """
    return model_prob - yes_price - per_contract_fee(yes_price, maker=maker)
