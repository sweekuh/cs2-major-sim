"""Public market data for Singapore: Polymarket (Gamma + CLOB) and Kalshi. Read-only.

Nothing here places orders or touches an account. Prices are best bid/ask and the cost of
a fixed-size taker order walked through the displayed book, including the venue's taker fee.
"""

from __future__ import annotations

import json
import re
import time
from decimal import Decimal

from .names import canon

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
SINGAPORE_TAG = 106580
DERIVATIVES = {
    "pgl-major-singapore-2026-teams-to-go-3-0-in-stage-1": "3-0",
    "pgl-major-singapore-2026-teams-to-go-3-1-in-stage-1": "3-1",
    "pgl-major-singapore-2026-teams-to-go-3-2-in-stage-1": "3-2",
    "pgl-major-singapore-2026-teams-to-go-0-3-in-stage-1": "0-3",
    "pgl-major-singapore-2026-qualify-to-stage-2": "qualify",
}
KALSHI_S2 = "KXCS2QUALIFIERS-26PGLSGS2"
POLY_SPORTS_FEE = 0.05  # docs.polymarket.com/trading/fees: fee = C x feeRate x p x (1 - p), takers only


def _json(client, method, url, **kw):
    for attempt in range(5):
        r = client.request(method, url, **kw)
        if r.status_code not in (429, 502, 503) or attempt == 4:
            r.raise_for_status()
            return r.json()
        delay = r.headers.get("retry-after", "")
        time.sleep(float(delay) if delay.replace(".", "", 1).isdigit() else 1.5 * 2**attempt)


# ---------------------------------------------------------------- Polymarket
def poly_events(client) -> list[dict]:
    return _json(client, "GET", f"{GAMMA}/events", params={"tag_id": SINGAPORE_TAG, "limit": 200})


def poly_rate(market: dict) -> float:
    schedule = market.get("feeSchedule") or {}
    if not market.get("feesEnabled"):
        return 0.0
    if schedule.get("exponent", 1) != 1 or not schedule.get("takerOnly", True):
        raise ValueError(f"Review the fee schedule for {market.get('slug')}: {schedule}")
    return float(schedule.get("rate", POLY_SPORTS_FEE))


def poly_fee(price: float, shares: float, rate: float = POLY_SPORTS_FEE) -> float:
    return shares * rate * price * (1 - price)


def poly_matches(events: list[dict]) -> dict[tuple[int, frozenset], dict]:
    """Match-winner markets keyed by (stage, {team, team})."""
    out = {}
    for e in events:
        found = re.search(r"\(BO(\d)\) - PGL Major Singapore Stage (\d)", e.get("title", ""))
        if not found:
            continue
        bo, stage = int(found[1]), int(found[2])
        for m in e["markets"]:
            if m.get("sportsMarketType") != "moneyline" or m.get("slug") != e["slug"]:
                continue
            teams = [canon(t, strict=False) for t in json.loads(m["outcomes"])]
            out[(stage, frozenset(teams))] = {
                "slug": e["slug"], "stage": stage, "bo": bo, "outcomes": teams,
                "tokens": json.loads(m["clobTokenIds"]), "start": m.get("gameStartTime"),
                "closed": bool(m.get("closed")), "accepting": bool(m.get("acceptingOrders")),
                "volume": float(m.get("volumeNum") or 0), "fee_rate": poly_rate(m),
                "delay_s": m.get("secondsDelay"),
            }
    return out


def poly_derivatives(events: list[dict]) -> list[dict]:
    out = []
    for e in events:
        family = DERIVATIVES.get(e.get("slug"))
        if not family:
            continue
        for m in e["markets"]:
            outcomes = json.loads(m["outcomes"])
            if [o.casefold() for o in outcomes] != ["yes", "no"]:
                raise ValueError(f"Unexpected outcomes on {m.get('slug')}: {outcomes}")
            out.append({
                "venue": "polymarket", "family": family, "team": canon(m["groupItemTitle"]),
                "market": m["slug"], "question": m["question"], "tokens": json.loads(m["clobTokenIds"]),
                "closed": bool(m.get("closed")), "accepting": bool(m.get("acceptingOrders")),
                "fee_rate": poly_rate(m), "volume": float(m.get("volumeNum") or 0),
            })
    return out


def poly_books(client, tokens: list[str]) -> dict[str, dict]:
    books = {}
    for i in range(0, len(tokens), 40):
        chunk = tokens[i:i + 40]
        for b in _json(client, "POST", f"{CLOB}/books", json=[{"token_id": t} for t in chunk]):
            books[b["asset_id"]] = {
                "bids": sorted(((float(x["price"]), float(x["size"])) for x in b.get("bids", [])), reverse=True),
                "asks": sorted((float(x["price"]), float(x["size"])) for x in b.get("asks", [])),
                "ts": b.get("timestamp"),
            }
    return books


def poly_midpoints(client, tokens: list[str]) -> dict[str, float]:
    if not tokens:
        return {}
    raw = _json(client, "POST", f"{CLOB}/midpoints", json=[{"token_id": t} for t in tokens])
    return {t: float(v) for t, v in raw.items()}


_TOKEN_CACHE: dict = {"at": 0.0, "map": {}}


def poly_match_tokens(client, ttl: float = 600) -> dict[frozenset, dict]:
    """Open match markets keyed by team pair, cached. Used for per-poll price ticks."""
    if time.time() - _TOKEN_CACHE["at"] > ttl:
        matches = poly_matches(poly_events(client))
        _TOKEN_CACHE["map"] = {teams: info for (_, teams), info in matches.items() if not info["closed"]}
        _TOKEN_CACHE["at"] = time.time()
    return _TOKEN_CACHE["map"]


def walk_asks(asks: list[tuple[float, float]], shares: float):
    """Average price to buy ``shares`` from ascending asks, or None if the book is too thin."""
    left, cost = shares, 0.0
    for price, size in asks:
        take = min(size, left)
        cost += take * price
        left -= take
        if left <= 1e-9:
            return cost / shares
    return None


def poly_mid(book: dict | None) -> float | None:
    if not book or not book["bids"] or not book["asks"]:
        return None
    bid, ask = book["bids"][0][0], book["asks"][0][0]
    return (bid + ask) / 2 if ask - bid <= 0.10 else None


# ---------------------------------------------------------------- Kalshi
def kalshi_s2(client) -> tuple[list[dict], Decimal]:
    series = _json(client, "GET", f"{KALSHI}/series/{KALSHI_S2.split('-')[0]}")["series"]
    if series["fee_type"] not in ("quadratic", "quadratic_with_maker_fees"):
        raise ValueError(f"Review Kalshi fee type {series['fee_type']}")
    markets = []
    for m in _json(client, "GET", f"{KALSHI}/events/{KALSHI_S2}")["markets"]:
        markets.append({
            "venue": "kalshi", "family": "qualify", "team": canon(m["yes_sub_title"]),
            "market": m["ticker"], "status": m["status"], "rules": m.get("rules_primary", ""),
        })
    return markets, Decimal(str(series["fee_multiplier"]))


def kalshi_book(client, ticker: str) -> dict:
    return _json(client, "GET", f"{KALSHI}/markets/{ticker}/orderbook")["orderbook_fp"]


def kalshi_matches(client) -> dict[frozenset, dict]:
    """Open Kalshi CS2 match markets keyed by team pair, with each team's bid/ask."""
    out, cursor = {}, None
    for _ in range(10):
        params = {"series_ticker": "KXCS2GAME", "status": "open", "limit": 200, "with_nested_markets": "true"}
        if cursor:
            params["cursor"] = cursor
        page = _json(client, "GET", f"{KALSHI}/events", params=params)
        for e in page.get("events", []):
            ms = e.get("markets") or []
            try:
                teams = [canon(m["yes_sub_title"]) for m in ms]
            except KeyError:
                continue
            if len(teams) != 2:
                continue
            out[frozenset(teams)] = {
                "event": e["event_ticker"],
                "quotes": {canon(m["yes_sub_title"]): (float(m.get("yes_bid_dollars") or 0), float(m.get("yes_ask_dollars") or 1)) for m in ms},
                "tickers": {canon(m["yes_sub_title"]): m["ticker"] for m in ms},
            }
        cursor = page.get("cursor")
        if not cursor:
            break
    return out


def kalshi_bo3_markets(client) -> dict[frozenset, list[dict]]:
    """Open Kalshi total-maps and map-spread markets, keyed by team pair.

    Each row is a binary contract on the series' map score: "over" (three maps played) or
    "sweep" by a named team (a 2-0 win).
    """
    out: dict[frozenset, list[dict]] = {}
    for series, kind in (("KXCS2TOTALMAPS", "over"), ("KXCS2SPREAD", "sweep")):
        page = _json(client, "GET", f"{KALSHI}/events",
                     params={"series_ticker": series, "status": "open", "limit": 200, "with_nested_markets": "true"})
        for e in page.get("events", []):
            found = re.match(r"(.+?) vs\.? (.+?): ", e.get("title", ""))
            if not found:
                continue
            try:
                pair = frozenset((canon(found[1]), canon(found[2])))
            except KeyError:
                continue
            for m in e.get("markets") or []:
                label = m.get("yes_sub_title") or ""
                if kind == "over":
                    if not re.fullmatch(r"Over 2\.5 maps", label.strip(), re.IGNORECASE):
                        raise ValueError(f"Review total-maps contract {m['ticker']}: {label!r}")
                    team = None
                else:
                    won = re.fullmatch(r"(.+?) wins by over 1\.5 maps?", label.strip(), re.IGNORECASE)
                    if not won:
                        raise ValueError(f"Review spread contract {m['ticker']}: {label!r}")
                    team = canon(won[1])
                out.setdefault(pair, []).append({"venue": "kalshi", "family": "maps", "kind": kind, "team": team,
                                                 "market": m["ticker"], "status": m["status"], "label": label})
    return out


def kalshi_series_multiplier(client, series: str) -> Decimal:
    info = _json(client, "GET", f"{KALSHI}/series/{series}")["series"]
    if info["fee_type"] not in ("quadratic", "quadratic_with_maker_fees"):
        raise ValueError(f"Review Kalshi fee type {info['fee_type']} for {series}")
    return Decimal(str(info["fee_multiplier"]))
