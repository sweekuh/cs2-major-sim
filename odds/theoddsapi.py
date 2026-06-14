"""TheOddsApiProvider — de-vigged sharp 1X2 (Pinnacle/Betfair) for the World Cup (PRD R2).

The Odds API exposes the World Cup under sport key ``soccer_fifa_world_cup`` and returns many
bookmakers in one shape. We keep the SHARP references — Pinnacle (sharp originator) and the
Betfair Exchange (no-vig truth) — de-vig each book's three-way h2h (1X2) odds via
``devig_three_way``, and PRE-POOL the kept books into ONE sharp-anchored 1X2 opinion per match
via ``pool_1x2`` BEFORE the cross-venue pool ever sees it (same Pitfall-7 discipline as
``odds/oddspapi.py``: ``n_sources`` counts independent venues, not books).

This de-vigged sharp consensus is the calibration target for the goals model AND the reference
the monitor uses to validate CLV on liquid match-1X2 markets.

REAL SHAPE (The Odds API v4): ``GET /v4/sports/soccer_fifa_world_cup/odds`` -> list of events,
each ``{id, home_team, away_team, commence_time, bookmakers:[{key, markets:[{key:"h2h",
outcomes:[{name, price}, ...]}]}]}`` where the h2h outcomes are the two team names plus "Draw"
and ``price`` is decimal odds.

httpx INVARIANT (D1/DX-01): httpx is lazy-imported INSIDE ``fetch()`` (the live-network branch)
ONLY. ``get_quotes`` parses a recorded fixture with NO httpx import.
"""

from __future__ import annotations

import json
from pathlib import Path

from odds._match import build_name_to_id, resolve_id
from odds.base import Quote1X2, devig_three_way, pool_1x2

# Sharp originators / no-vig exchange weighted highest; any other book is a soft copy.
_SHARP_KEYS = {"pinnacle", "betfair_ex_eu", "betfair_ex_uk", "betfair"}
_SHARP_ORIGINATE = 1.0
_SOFT_ORIGINATE = 0.3

_DRAW_NAMES = {"draw", "tie"}


def _as_dict(fixtures):
    """Accept a parsed object OR a path to a recorded fixture (no network)."""
    if isinstance(fixtures, (str, Path)):
        return json.loads(Path(fixtures).read_text(encoding="utf-8"))
    return fixtures


def _h2h_prices(bookmaker: dict, home: str, away: str) -> tuple[float, float, float] | None:
    """Pull (o_home, o_draw, o_away) decimal odds from a bookmaker's h2h market. None if missing."""
    markets = bookmaker.get("markets") or []
    h2h = next((m for m in markets if m.get("key") == "h2h"), None)
    if not isinstance(h2h, dict):
        return None
    o_home = o_draw = o_away = None
    for oc in h2h.get("outcomes") or []:
        name = str(oc.get("name", "")).strip()
        try:
            price = float(oc["price"])
        except (KeyError, TypeError, ValueError):
            return None
        if name.lower() in _DRAW_NAMES:
            o_draw = price
        elif name == home:
            o_home = price
        elif name == away:
            o_away = price
    if o_home is None or o_draw is None or o_away is None:
        return None
    if min(o_home, o_draw, o_away) <= 1.0:
        return None
    return o_home, o_draw, o_away


class TheOddsApiProvider:
    """Parse a recorded The Odds API WC fixture into one sharp-anchored 1X2 opinion per match."""

    name = "theoddsapi"

    def get_quotes(self, fixtures, *, teams) -> list[Quote1X2]:
        """Parse event(s) -> list[Quote1X2], one pre-pooled sharp opinion per resolvable match.

        Parses defensively: an event with no sharp book, no h2h market, or an unresolvable
        matchup yields no quote for that match (fail-soft, never raises).
        """
        try:
            raw = _as_dict(fixtures)
        except (OSError, ValueError):
            return []
        events = raw if isinstance(raw, list) else [raw]
        name_to_id = build_name_to_id(teams)
        out: list[Quote1X2] = []
        for ev in events:
            q = self._parse_one(ev, name_to_id=name_to_id)
            if q is not None:
                out.append(q)
        return out

    def _parse_one(self, ev: dict, *, name_to_id) -> Quote1X2 | None:
        if not isinstance(ev, dict):
            return None
        home = str(ev.get("home_team", "")).strip()
        away = str(ev.get("away_team", "")).strip()
        if not home or not away:
            return None
        id_home = resolve_id(home, name_to_id)
        id_away = resolve_id(away, name_to_id)
        if id_home is None or id_away is None or id_home == id_away:
            return None

        bundle: list[Quote1X2] = []
        for bk in ev.get("bookmakers") or []:
            if not isinstance(bk, dict):
                continue
            prices = _h2h_prices(bk, home, away)
            if prices is None:
                continue
            p_home, p_draw, p_away = devig_three_way(*prices)
            key = str(bk.get("key", "")).strip().lower()
            originate = _SHARP_ORIGINATE if key in _SHARP_KEYS else _SOFT_ORIGINATE
            bundle.append(
                Quote1X2(
                    provider=f"theoddsapi:{key}",
                    match=(id_home, id_away),
                    p_home=p_home,
                    p_draw=p_draw,
                    p_away=p_away,
                    originate=originate,
                    liquidity=0.0,
                    ts=0.0,
                )
            )
        if not bundle:
            return None
        blended = pool_1x2(bundle)
        return Quote1X2(
            provider="theoddsapi:sharp",
            match=(id_home, id_away),
            p_home=blended.p_home,
            p_draw=blended.p_draw,
            p_away=blended.p_away,
            originate=max(q.originate for q in bundle),
            liquidity=0.0,
            ts=0.0,
        )

    def fetch(self, *, teams, api_key: str, regions: str = "eu,uk",
              sport_key: str = "soccer_fifa_world_cup") -> list[Quote1X2]:
        """Live The Odds API fetch. httpx is lazy-imported HERE only (D1/DX-01).

        Pulls h2h (1X2) odds in decimal format for the World Cup sport key, then hands the events
        to ``get_quotes``. Network/parse errors fail soft to whatever was gathered. The httpx/
        httpcore loggers are forced to WARNING so the ``apiKey`` query param is never logged.
        """
        import logging

        import httpx

        for _n in ("httpx", "httpcore"):
            logging.getLogger(_n).setLevel(logging.WARNING)

        base = "https://api.the-odds-api.com/v4"
        params = {
            "apiKey": api_key,
            "regions": regions,
            "markets": "h2h",
            "oddsFormat": "decimal",
        }
        with httpx.Client(timeout=25.0) as client:
            try:
                events = client.get(f"{base}/sports/{sport_key}/odds", params=params).json()
            except Exception:  # noqa: BLE001 — fail-soft to empty on any network/parse error
                return []
        return self.get_quotes(events, teams=teams)
