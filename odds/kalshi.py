"""KalshiProvider — trade-api/v2/markets yes-mid market-price normalize (keyless, ODDS-02/05).

Kalshi public market data is a KEYLESS read; ``yes_bid``/``yes_ask`` are cents (0-100). The
yes-mid ``(yes_bid + yes_ask)/2 / 100`` is ≈ a probability (vig_type=="market"), routed through
``normalize_market_price`` and NEVER through the fixed-odds two-way de-vig (Pitfall 8). Kalshi
esports coverage is sparse, so an empty ``markets: []`` (no Cologne market posted) is a
legitimate fail-soft path: ``get_quotes`` returns ``[]``, never raises (ODDS-05).

httpx INVARIANT (D1/DX-01): httpx is lazy-imported INSIDE ``fetch()`` only; ``get_quotes``
parses a recorded fixture with NO httpx import.
"""

from __future__ import annotations

import json
from pathlib import Path

from odds._match import resolve_match
from odds.base import OddsQuote, normalize_market_price


def _as_dict(fixtures) -> dict:
    if isinstance(fixtures, (str, Path)):
        return json.loads(Path(fixtures).read_text(encoding="utf-8"))
    return fixtures


class KalshiProvider:
    """Parse a recorded Kalshi trade-api/v2/markets fixture into market-price OddsQuotes."""

    name = "kalshi"

    def get_quotes(self, fixtures, *, teams) -> list[OddsQuote]:
        """Parse the recorded markets fixture -> list[OddsQuote] (vig_type=="market").

        An empty ``markets: []`` (no Cologne market yet) yields ``[]`` (fail-soft, ODDS-05),
        as does an unresolvable/incomplete market — never raises.
        """
        try:
            raw = _as_dict(fixtures)
        except (OSError, ValueError):
            return []
        markets = raw.get("markets") if isinstance(raw, dict) else raw
        if not isinstance(markets, list):
            return []
        out: list[OddsQuote] = []
        for mk in markets:
            q = self._parse_one(mk, teams=teams)
            if q is not None:
                out.append(q)
        return out

    def _parse_one(self, mk: dict, *, teams) -> OddsQuote | None:
        if not isinstance(mk, dict):
            return None
        name_a = mk.get("team_a")
        name_b = mk.get("team_b")
        if not name_a or not name_b:
            return None
        try:
            yes_bid = float(mk["yes_bid"])
            yes_ask = float(mk["yes_ask"])
        except (KeyError, TypeError, ValueError):
            return None
        resolved = resolve_match(name_a, name_b, teams)
        if resolved is None:
            return None
        match, a_is_lower = resolved
        # yes-mid in cents -> probability for team_a; normalize (market), NEVER two-way de-vig.
        mid = (yes_bid + yes_ask) / 2.0 / 100.0
        p_a = normalize_market_price(mid)
        p_lower = p_a if a_is_lower else 1.0 - p_a
        return OddsQuote(
            provider="kalshi",
            match=match,
            p_a_raw=p_lower,
            vig_type="market",
            bo3=bool(mk.get("bo3", False)),
            liquidity=float(mk.get("liquidity", 0.0) or 0.0),
            originate=1.0,  # an independent market is a sharp originator
            ts=0.0,
        )

    def fetch(self, fixtures, *, teams) -> list[OddsQuote]:
        """Live Kalshi fetch (keyless, DEFERRED-verified 05-03). httpx lazy-imported HERE."""
        import httpx  # noqa: F401  — lazy: network branch only, NEVER at module top (D1/DX-01)

        raise NotImplementedError(
            "Live Kalshi fetch is verified at the 05-03 live-slug checkpoint; "
            "05-01 parses recorded fixtures only."
        )
