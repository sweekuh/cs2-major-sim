"""KalshiProvider — KXCS2GAME match-winner yes-mid market-price normalize (keyless, ODDS-02/05).

Kalshi public market data is a KEYLESS read. The CS2 per-match series is ``KXCS2GAME``: each
match is ONE ``event_ticker`` with TWO complementary markets (one per competitor, "Will <team>
win …"). The ``yes_bid_dollars`` / ``yes_ask_dollars`` are price strings already in DOLLARS
(0-1), so the yes-mid ``(yes_bid + yes_ask)/2`` is ≈ a probability (vig_type=="market"), routed
through ``normalize_market_price`` and NEVER through the fixed-odds two-way de-vig (Pitfall 8).

REAL SHAPE (verified 2026-06-01 against live Kalshi /trade-api/v2/markets):
  - ``yes_sub_title`` — the competitor THIS market is YES for.
  - ``title`` — "Will <yes_team> win the <A> vs. <B> CS2 match?" (the matchup A vs. B).
  - ``rules_primary`` — carries the tournament ("IEM Cologne Major 2026: A vs. B …").
  - ``yes_bid_dollars`` / ``yes_ask_dollars`` — dollar strings.
The two markets per event are complementary (one fair two-sided price), so we DEDUPE per
``event_ticker`` to emit ONE opinion per match. Tournament filtering happens upstream in
``fetch`` (this parser is tournament-agnostic, so it is reusable for the next Major).

httpx INVARIANT (D1/DX-01): httpx is lazy-imported INSIDE ``fetch()`` only; ``get_quotes``
parses a recorded fixture with NO httpx import.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from odds._match import build_name_to_id, resolve_id
from odds.base import OddsQuote, normalize_market_price

# "<A> vs. <B> CS2 match" matchup extraction. The first team is anchored on "win the " (title)
# so the repeated yes-team prefix is not swallowed; the second is whatever sits between "vs." and
# "CS2 match".
_RE_FIRST = re.compile(r"win the\s+(.+?)\s+vs\.?\s", re.IGNORECASE)
_RE_SECOND = re.compile(r"\bvs\.?\s+(.+?)\s+CS2 match", re.IGNORECASE)
# Fallback for rules_primary: "<…>wins the <tournament>: <A> vs. <B> CS2 match".
_RE_FIRST_RULES = re.compile(r"wins the[^:]*:\s*(.+?)\s+vs\.?\s", re.IGNORECASE)


def _as_dict(fixtures) -> dict:
    if isinstance(fixtures, (str, Path)):
        return json.loads(Path(fixtures).read_text(encoding="utf-8"))
    return fixtures


def _matchup(mk: dict) -> tuple[str, str] | None:
    """Pull (teamA, teamB) from the market title (preferred) or rules_primary (fallback)."""
    title = str(mk.get("title") or "")
    rules = str(mk.get("rules_primary") or "")
    second = _RE_SECOND.search(title) or _RE_SECOND.search(rules)
    first = _RE_FIRST.search(title) or _RE_FIRST_RULES.search(rules)
    if not first or not second:
        return None
    a, b = first.group(1).strip(), second.group(1).strip()
    if not a or not b:
        return None
    return a, b


def _price_dollars(mk: dict, key: str) -> float | None:
    try:
        return float(mk[key])
    except (KeyError, TypeError, ValueError):
        return None


class KalshiProvider:
    """Parse a recorded Kalshi KXCS2GAME markets fixture into market-price OddsQuotes."""

    name = "kalshi"

    def get_quotes(self, fixtures, *, teams) -> list[OddsQuote]:
        """Parse the markets fixture -> list[OddsQuote] (vig_type=="market"), one per match.

        Dedupes the two complementary markets per ``event_ticker`` to ONE opinion. An empty
        ``markets: []`` (no market posted) yields ``[]`` (fail-soft, ODDS-05), as does an
        unresolvable/incomplete market — never raises.
        """
        try:
            raw = _as_dict(fixtures)
        except (OSError, ValueError):
            return []
        markets = raw.get("markets") if isinstance(raw, dict) else raw
        if not isinstance(markets, list):
            return []
        name_to_id = build_name_to_id(teams)
        by_event: dict[str, OddsQuote] = {}
        for mk in markets:
            q = self._parse_one(mk, name_to_id=name_to_id)
            if q is None:
                continue
            ev = str(mk.get("event_ticker") or id(mk))
            by_event.setdefault(ev, q)  # first complementary side wins; the other is redundant
        return list(by_event.values())

    def _parse_one(self, mk: dict, *, name_to_id) -> OddsQuote | None:
        if not isinstance(mk, dict):
            return None
        matchup = _matchup(mk)
        yes_team = mk.get("yes_sub_title")
        if matchup is None or not yes_team:
            return None
        ida = resolve_id(matchup[0], name_to_id)
        idb = resolve_id(matchup[1], name_to_id)
        id_yes = resolve_id(yes_team, name_to_id)
        if ida is None or idb is None or ida == idb or id_yes not in (ida, idb):
            return None
        yes_bid = _price_dollars(mk, "yes_bid_dollars")
        yes_ask = _price_dollars(mk, "yes_ask_dollars")
        if yes_bid is None or yes_ask is None:
            return None
        mid = (yes_bid + yes_ask) / 2.0  # already dollars (0-1)
        p_yes = normalize_market_price(mid)  # market price ≈ prob: NEVER two-way de-vig (Pitfall 8)
        lo = min(ida, idb)
        p_lower = p_yes if id_yes == lo else 1.0 - p_yes
        return OddsQuote(
            provider="kalshi",
            match=(lo, max(ida, idb)),
            p_a_raw=p_lower,
            vig_type="market",
            bo3=bool(mk.get("bo3", False)),  # Cologne Swiss opening rounds are Bo1
            # liquidity kept 0.0 so the cross-provider pool equal-weights Kalshi with the
            # liquidity-0 OddsPapi/Pinnacle quote rather than letting thin esports open-interest
            # zero out the sharp anchor (see odds/base.pool weighting). TODO: principled
            # cross-provider liquidity weighting.
            liquidity=0.0,
            originate=1.0,  # an independent market is a sharp originator
            ts=0.0,
        )

    def fetch(self, *, teams, tournament: str = "cologne") -> list[OddsQuote]:
        """Live Kalshi fetch (keyless, verified live 2026-06-01). httpx lazy-imported HERE.

        Pages the open KXCS2GAME match markets, keeps the ones whose ``rules_primary``/``title``
        contains ``tournament`` (case-insensitive), and hands them to ``get_quotes``. Network
        errors fail soft to whatever was gathered. Importing httpx inside the method keeps it OUT
        of the import path (D1/DX-01).
        """
        import httpx  # noqa: F401  — lazy: network branch only, NEVER at module top (D1/DX-01)

        base = "https://api.elections.kalshi.com/trade-api/v2"
        tkey = tournament.lower()
        kept: list[dict] = []
        cursor: str | None = None
        with httpx.Client(timeout=25.0) as client:
            for _ in range(12):  # bounded paging
                params = {"series_ticker": "KXCS2GAME", "status": "open", "limit": 200}
                if cursor:
                    params["cursor"] = cursor
                data = client.get(f"{base}/markets", params=params).json()
                markets = data.get("markets") or []
                for m in markets:
                    blob = (str(m.get("rules_primary", "")) + str(m.get("title", ""))).lower()
                    if tkey in blob:
                        kept.append(m)
                cursor = data.get("cursor")
                if not cursor or not markets:
                    break
        return self.get_quotes({"markets": kept}, teams=teams)


_KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"


@dataclass(frozen=True)
class KalshiMarketState:
    """A snapshot of one open Kalshi World Cup market: price, spread, and depth proxy.

    ``mid`` is the yes-mid in dollars (≈ P(yes)); ``spread`` the yes bid-ask width; ``depth`` an
    open-interest/volume proxy the ranker uses to down-weight thin books. ``market_type`` is the
    family the market belongs to (champion / group_winner / advance / match / exotic), resolved
    from its ``series_ticker`` so the pricing layer knows which model probability to compare.
    """

    series_ticker: str
    event_ticker: str
    ticker: str
    market_type: str
    title: str
    yes_sub_title: str
    yes_bid: float
    yes_ask: float
    mid: float
    spread: float
    depth: float
    status: str


# series_ticker -> market family. Extend via data/kalshi_wc_tickers.json as Kalshi posts more.
_SERIES_TYPE = {
    "KXMENWORLDCUP": "champion",
    "KXWCGROUPWIN": "group_winner",
    "KXWCGROUPQUAL": "advance",
}


def classify_series(series_ticker: str) -> str:
    """Map a Kalshi series ticker to a market family (default 'match' for per-game winner series)."""
    return _SERIES_TYPE.get(str(series_ticker).strip().upper(), "match")


def _f(mk: dict, key: str) -> float | None:
    try:
        return float(mk[key])
    except (KeyError, TypeError, ValueError):
        return None


class KalshiWCProvider:
    """Read open Kalshi World Cup markets into priced ``KalshiMarketState`` snapshots (keyless).

    Generalizes the KXCS2GAME reader to any WC series. Parsing is tournament/market-type agnostic
    — it extracts price/spread/depth and the descriptive fields; mapping a state to the model's
    fair value for the right outcome happens in the pricing/pipeline layer.
    """

    name = "kalshi_wc"

    def get_states(self, fixtures) -> list[KalshiMarketState]:
        """Parse a markets fixture (dict/list/path) -> list[KalshiMarketState]. Fail-soft to []."""
        try:
            raw = _as_dict(fixtures)
        except (OSError, ValueError):
            return []
        markets = raw.get("markets") if isinstance(raw, dict) else raw
        if not isinstance(markets, list):
            return []
        out: list[KalshiMarketState] = []
        for mk in markets:
            st = self._parse_one(mk)
            if st is not None:
                out.append(st)
        return out

    def _parse_one(self, mk: dict) -> KalshiMarketState | None:
        if not isinstance(mk, dict):
            return None
        ticker = str(mk.get("ticker") or "").strip()
        if not ticker:
            return None
        yes_bid = _f(mk, "yes_bid_dollars")
        yes_ask = _f(mk, "yes_ask_dollars")
        if yes_bid is None or yes_ask is None or yes_ask < yes_bid:
            return None
        mid = normalize_market_price((yes_bid + yes_ask) / 2.0)
        spread = yes_ask - yes_bid
        series = str(mk.get("series_ticker") or "").strip()
        depth = _f(mk, "open_interest") or _f(mk, "volume") or _f(mk, "liquidity") or 0.0
        return KalshiMarketState(
            series_ticker=series,
            event_ticker=str(mk.get("event_ticker") or ""),
            ticker=ticker,
            market_type=classify_series(series),
            title=str(mk.get("title") or ""),
            yes_sub_title=str(mk.get("yes_sub_title") or ""),
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            mid=mid,
            spread=spread,
            depth=depth,
            status=str(mk.get("status") or ""),
        )

    def fetch(self, *, series_tickers: list[str], status: str = "open") -> list[KalshiMarketState]:
        """Live keyless fetch of open WC markets across the given series. httpx lazy-imported HERE.

        Pages each series' markets (bounded), concatenates, and parses to states. Network errors
        fail soft to whatever was gathered (D1/DX-01: httpx imported inside this branch only).
        """
        import httpx

        kept: list[dict] = []
        with httpx.Client(timeout=25.0) as client:
            for series in series_tickers:
                cursor: str | None = None
                for _ in range(12):  # bounded paging per series
                    params = {"series_ticker": series, "status": status, "limit": 200}
                    if cursor:
                        params["cursor"] = cursor
                    try:
                        data = client.get(f"{_KALSHI_BASE}/markets", params=params).json()
                    except Exception:  # noqa: BLE001 — per-series fail-soft
                        break
                    markets = data.get("markets") or []
                    kept.extend(markets)
                    cursor = data.get("cursor")
                    if not cursor or not markets:
                        break
        return self.get_states({"markets": kept})
