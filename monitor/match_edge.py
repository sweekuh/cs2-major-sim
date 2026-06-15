"""Per-match prediction + EV (Phase 1 iteration): price a single fixture and value bets on it.

The tournament sample prices futures; this prices a single match's 1X2 directly off the match
model (the path the pipeline left ``unmapped``). EV helpers value a bet given either decimal
sportsbook odds or a Kalshi YES price (net of the exact Kalshi fee).
"""

from __future__ import annotations

from engine.soccer.dixon_coles import MatchModel, match_1x2
from monitor.fees import per_contract_fee
from odds._match import resolve_id
from odds.base import devig_three_way_shin

_OUTCOMES = ("home", "draw", "away")


def market_targets(fixtures, name_to_id) -> dict[tuple[int, int], tuple[float, float, float]]:
    """De-vig each fixture's 1X2 odds (Shin) into calibration targets keyed by (home_id, away_id).

    Skips fixtures without a full home/draw/away price or with an unresolvable team. The result
    feeds ``engine.soccer.calibrate.calibrate_strengths`` so the model agrees with the sharp line.
    """
    out: dict[tuple[int, int], tuple[float, float, float]] = {}
    for m in fixtures:
        o = m.get("odds") or {}
        # Require a valid decimal price (> 1.0) on all three outcomes; anything else (missing,
        # zero, negative, or sub-1.0) is not de-viggable and is skipped (fail-soft, no crash).
        if not all(isinstance(o.get(k), (int, float)) and o.get(k) > 1.0 for k in _OUTCOMES):
            continue
        hid, aid = resolve_id(m["home"], name_to_id), resolve_id(m["away"], name_to_id)
        if hid is None or aid is None or hid == aid:
            continue
        out[(hid, aid)] = devig_three_way_shin(o["home"], o["draw"], o["away"])
    return out


def targets_from_quotes(quotes) -> dict[tuple[int, int], tuple[float, float, float]]:
    """Calibration targets keyed by (home_id, away_id) from already-de-vigged ``Quote1X2`` objects
    (the live ``TheOddsApiProvider`` output). Last quote per match wins on a duplicate."""
    return {q.match: (q.p_home, q.p_draw, q.p_away) for q in quotes}


def results_to_tuples(matches, name_to_id) -> list[tuple[int, int, int, int]]:
    """Resolve finished-match records into ``(home_id, away_id, home_goals, away_goals)`` tuples
    for ``engine.soccer.elo_update.apply_results``. Skips records missing a score or an
    unresolvable / same-id team (fail-soft, no crash)."""
    out: list[tuple[int, int, int, int]] = []
    for m in matches:
        if m.get("home_goals") is None or m.get("away_goals") is None:
            continue
        hid, aid = resolve_id(m.get("home", ""), name_to_id), resolve_id(m.get("away", ""), name_to_id)
        if hid is None or aid is None or hid == aid:
            continue
        try:
            out.append((hid, aid, int(m["home_goals"]), int(m["away_goals"])))
        except (TypeError, ValueError):
            continue
    return out


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
