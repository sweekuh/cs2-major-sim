"""Read the eight pre-match Singapore Stage 1 moneylines from Polymarket's public API."""

import json
from datetime import datetime, timezone


def parse_book(event, opener):
    slug = opener["slug"]
    if event.get("slug") != slug:
        raise ValueError(f"Wrong event returned for {slug}")
    matches = [m for m in event["markets"] if m.get("slug") == slug and m.get("sportsMarketType") == "moneyline"]
    if len(matches) != 1:
        raise ValueError(f"Missing or ambiguous match moneyline for {slug}")
    market = matches[0]
    if market.get("closed") or not market.get("acceptingOrders"):
        raise ValueError(f"Moneyline closed for {slug}")
    aliases = {"dendele cs": "dendele"}
    sides = [aliases.get(name.casefold(), name.casefold()) for name in json.loads(market["outcomes"])]
    expected = [name.casefold() for name in opener["teams"]]
    bid, ask = float(market["bestBid"]), float(market["bestAsk"])
    if not 0 < bid <= ask < 1:
        raise ValueError(f"No two-sided price for {slug}")
    if sides == expected[::-1]:
        bid, ask = 1 - ask, 1 - bid
    elif sides != expected:
        raise ValueError(f"Unexpected teams for {slug}")
    return {**opener, "bid": bid, "ask": ask, "updated_at": market["updatedAt"]}


def refresh(fixture):
    import httpx

    if datetime.now(timezone.utc) >= datetime.fromisoformat(fixture["starts_at"]):
        raise ValueError("Stage 1 has started. Use the frozen pre-match quotes for a replay.")
    quotes = []
    with httpx.Client(timeout=10) as client:
        for opener in fixture["openers"]:
            try:
                reply = client.get("https://gamma-api.polymarket.com/events", params={"slug": opener["slug"]})
                reply.raise_for_status()
                events = reply.json()
            except httpx.HTTPError as exc:
                raise ValueError(f"Could not fetch {opener['slug']} from Polymarket") from exc
            if len(events) != 1:
                raise ValueError(f"Expected one Singapore opener for {opener['slug']}")
            try:
                quotes.append(parse_book(events[0], opener))
            except (KeyError, TypeError, AttributeError) as exc:
                raise ValueError(f"Incomplete quote for {opener['slug']}") from exc
    return quotes, datetime.now(timezone.utc).isoformat(timespec="seconds")
