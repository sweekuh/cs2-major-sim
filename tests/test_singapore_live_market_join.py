from dataclasses import replace

import httpx
import pytest

from analysis.singapore_live import markets
from analysis.singapore_live.feed import Fixture


GAME = Fixture("s1-20", 1, "Round 3", 3, 3, "2026-11-25T08:00:00+00:00",
               "upcoming", "Imperial", "FlyQuest", (0, 0), ())


def listing(stamp, *, bid="0.54", tournament="PGL Major Singapore 2026"):
    event = "KXCS2GAME-" + stamp + "FLYIMP"
    sides = []
    for suffix, team in (("FLY", "FlyQuest"), ("IMP", "Imperial Esports")):
        sides.append({
            "event_ticker": event, "ticker": f"{event}-{suffix}", "market_type": "binary",
            "status": "active", "yes_sub_title": team, "yes_bid_dollars": bid, "yes_ask_dollars": "0.56",
            "rules_primary": f"If {team} wins the {tournament}: FlyQuest vs. Imperial CS2 match originally scheduled for this date, then the market resolves to Yes.",
        })
    return {"event_ticker": event, "markets": sides}


def join(fixtures, *pages):
    def respond(request):
        index = int(request.url.params.get("cursor", 0))
        return httpx.Response(200, json={"events": pages[index],
                                         "cursor": str(index + 1) if index + 1 < len(pages) else ""})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        return markets.kalshi_matches(client, fixtures)


def test_match_quote_uses_fixture_time_and_tournament_across_pages():
    nov, dec = listing("26NOV250300"), listing("26DEC120300", bid="0.12")
    unrelated = listing("26NOV250305", tournament="ESL Challenger Singapore")
    second = replace(GAME, key="s2-05", stage=2, start="2026-12-12T08:00:00+00:00")
    quotes = join([GAME, second], [nov], [unrelated, dec, nov])
    assert quotes[GAME.key]["event"] == nov["event_ticker"]
    assert quotes[GAME.key]["quotes"]["Imperial"] == (0.54, 0.56)
    assert quotes[second.key]["event"] == dec["event_ticker"]


def test_ambiguous_matches_are_excluded_in_either_direction():
    first, second = listing("26NOV250300"), listing("26NOV250330")
    assert join([GAME], [first], [second]) == {}
    assert join([GAME, replace(GAME, key="s2-01")], [first]) == {}


@pytest.mark.parametrize("overrides", [
    {"rules_primary": "If FlyQuest wins the PGL Major Singapore 2026: FlyQuest vs. M80 CS2 match"},
    {"status": "closed"},
    {"rules_primary": ""},
])
def test_both_contracts_must_describe_the_same_active_full_match(overrides):
    event = listing("26NOV250300")
    event["markets"][0].update(overrides)
    assert join([GAME], [event]) == {}
