"""PolymarketProvider — Gamma /events market-price normalize (keyless, ODDS-02/08).

Polymarket Gamma market data is a KEYLESS public read; ``outcomePrices`` are already ≈ the
implied probabilities (vig_type=="market"), so each price is routed through
``normalize_market_price`` (spread/fee only) and NEVER through the fixed-odds two-way de-vig
(Pitfall 8, threat T-05-DEVIG). With no ODDSPAPI_KEY this provider still populates — the key
only unlocks the OddsPapi/Pinnacle anchor (D3 new fact).

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


class PolymarketProvider:
    """Parse a recorded Polymarket Gamma /events fixture into market-price OddsQuotes."""

    name = "polymarket"

    def get_quotes(self, fixtures, *, teams) -> list[OddsQuote]:
        """Parse the recorded /events fixture -> list[OddsQuote] (vig_type=="market").

        An absent/empty events list or an unresolvable event yields no quote for that match
        (fail-soft, ODDS-05) — never raises.
        """
        try:
            raw = _as_dict(fixtures)
        except (OSError, ValueError):
            return []
        events = raw.get("events") if isinstance(raw, dict) else raw
        if not isinstance(events, list):
            return []
        out: list[OddsQuote] = []
        for ev in events:
            q = self._parse_one(ev, teams=teams)
            if q is not None:
                out.append(q)
        return out

    def _parse_one(self, ev: dict, *, teams) -> OddsQuote | None:
        if not isinstance(ev, dict):
            return None
        outcomes = ev.get("outcomes") or []
        prices = ev.get("outcomePrices") or []
        if len(outcomes) != 2 or len(prices) != 2:
            return None
        resolved = resolve_match(outcomes[0], outcomes[1], teams)
        if resolved is None:
            return None
        match, a_is_lower = resolved
        try:
            price_a = float(prices[0])
        except (TypeError, ValueError):
            return None
        # Market price ≈ prob: normalize (spread/fee only), NEVER two-way de-vig (Pitfall 8).
        p_a = normalize_market_price(price_a)
        p_lower = p_a if a_is_lower else 1.0 - p_a
        return OddsQuote(
            provider="polymarket",
            match=match,
            p_a_raw=p_lower,
            vig_type="market",
            bo3=bool(ev.get("bo3", False)),
            liquidity=float(ev.get("liquidity", 0.0) or 0.0),
            originate=1.0,  # an independent market is a sharp originator
            ts=0.0,
        )

    def fetch(self, fixtures, *, teams) -> list[OddsQuote]:
        """Live Polymarket fetch (keyless, DEFERRED-verified 05-03). httpx lazy-imported HERE."""
        import httpx  # noqa: F401  — lazy: network branch only, NEVER at module top (D1/DX-01)

        raise NotImplementedError(
            "Live Polymarket fetch is verified at the 05-03 live-slug checkpoint; "
            "05-01 parses recorded fixtures only."
        )
