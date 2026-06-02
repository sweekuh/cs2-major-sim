"""OddsPapiProvider — fixed-odds de-vig + soft-book bundle pre-pool (ODDS-03, Pitfall 7).

OddsPapi returns Pinnacle (the sharp originator) plus soft books (Thunderpick, GG.BET, Betway,
…) that COPY Pinnacle's line — heavily correlated, NOT independent sources. This provider:
  1. de-vigs EACH book's two-way fixed odds via ``devig_fixed_two_way`` (vig_type=="fixed"),
  2. PRE-POOLS the whole bundle into EXACTLY ONE Pinnacle-anchored OddsQuote (Pinnacle weighted
     originate=1.0, soft copies <1.0) via the same log-opinion ``pool()`` math, BEFORE the
     cross-provider pool ever sees it.
So the cross-provider ``pool()`` sees ONE OddsPapi opinion and never headcounts the soft books
(Pitfall 7, threat T-05-HEADCOUNT) — ``n_sources`` counts independent originators, not books.

REAL SHAPE (verified 2026-06-01 against live OddsPapi v4, IEM Cologne):
  - ``/v4/fixtures?sportId=17`` lists CS2 fixtures: ``participant1Name`` / ``participant2Name``,
    ``fixtureId``, ``tournamentName`` ("Intel Extreme Masters Cologne").
  - ``/v4/odds?fixtureId=…`` returns ``bookmakerOdds`` — a DICT keyed by book slug. Each book
    has ``markets["171"]`` (Match Winner) -> ``outcomes`` dict with keys ``"171"`` (participant1
    win) and ``"172"`` (participant2 win) -> ``players["0"].price`` (decimal odds).
  ``get_quotes`` parses the ENRICHED fixture (names joined to that fixture's ``bookmakerOdds``)
  the live ``fetch`` assembles; the recorded test fixture is one such enriched object.

httpx INVARIANT (D1/DX-01): httpx is lazy-imported INSIDE ``fetch()`` (the live-network branch)
ONLY. ``get_quotes`` parses a recorded fixture (parsed dict or path) with NO httpx import, so the
fixture tests collect and run with no httpx installed and nothing here leaks into the app path.
"""

from __future__ import annotations

import json
from pathlib import Path

from odds._match import resolve_match
from odds.base import OddsQuote, devig_fixed_two_way, pool

# Soft books copy Pinnacle's line; weight the sharp originator highest, copies lower, so the
# within-bundle pre-pool is Pinnacle-anchored (never an equal-weight headcount).
_PINNACLE_ORIGINATE = 1.0
_SOFT_ORIGINATE = 0.3

# OddsPapi market/outcome ids (verified live): market "171" = Match Winner; within it outcome
# "171" = participant1 wins, outcome "172" = participant2 wins.
_MARKET_MATCH_WINNER = "171"
_OUTCOME_P1 = "171"
_OUTCOME_P2 = "172"


def _as_dict(fixtures) -> dict:
    """Accept a parsed dict OR a path to a recorded fixture (no network)."""
    if isinstance(fixtures, (str, Path)):
        return json.loads(Path(fixtures).read_text(encoding="utf-8"))
    return fixtures


def _outcome_price(outcome) -> float | None:
    """Dig ``outcomes[id].players["0"].price`` (decimal odds), honouring the active flag.

    The live shape nests the price under a single ``players["0"]`` entry. Returns None for any
    missing/inactive/malformed branch so the caller drops just that book (fail-soft).
    """
    if not isinstance(outcome, dict):
        return None
    players = outcome.get("players") or {}
    leaf = players.get("0") if isinstance(players, dict) else None
    if not isinstance(leaf, dict) or leaf.get("active") is False:
        return None
    try:
        return float(leaf["price"])
    except (KeyError, TypeError, ValueError):
        return None


class OddsPapiProvider:
    """Parse a recorded OddsPapi enriched fixture into one Pinnacle-anchored OddsQuote per match."""

    name = "oddspapi"

    def get_quotes(self, fixtures, *, teams) -> list[OddsQuote]:
        """Parse the enriched fixture(s) -> list[OddsQuote], one per resolvable match.

        Each match's soft-book bundle is collapsed to ONE quote (Pitfall 7). Parses defensively:
        a missing/empty bundle or an unresolvable matchup yields no quote for that match (never
        raises) — the fail-soft empty path (ODDS-05).
        """
        try:
            raw = _as_dict(fixtures)
        except (OSError, ValueError):
            return []
        # An enriched fixture is a single match object; tolerate a list of them too.
        matches = raw if isinstance(raw, list) else [raw]
        out: list[OddsQuote] = []
        for m in matches:
            q = self._parse_one(m, teams=teams)
            if q is not None:
                out.append(q)
        return out

    def _parse_one(self, m: dict, *, teams) -> OddsQuote | None:
        if not isinstance(m, dict):
            return None
        name_a = m.get("participant1Name")
        name_b = m.get("participant2Name")
        books = m.get("bookmakerOdds") or {}
        if not name_a or not name_b or not isinstance(books, dict) or not books:
            return None
        resolved = resolve_match(name_a, name_b, teams)
        if resolved is None:
            return None
        match, a_is_lower = resolved  # a == participant1
        bo3 = bool(m.get("bo3", False))

        # De-vig each ACTIVE book's Match-Winner market to P(participant1), orient to P(lower-id).
        bundle: list[OddsQuote] = []
        for slug, bd in books.items():
            if not isinstance(bd, dict) or bd.get("suspended") or bd.get("bookmakerIsActive") is False:
                continue
            mkt = (bd.get("markets") or {}).get(_MARKET_MATCH_WINNER)
            if not isinstance(mkt, dict) or mkt.get("marketActive") is False:
                continue
            outcomes = mkt.get("outcomes") or {}
            o_a = _outcome_price(outcomes.get(_OUTCOME_P1))
            o_b = _outcome_price(outcomes.get(_OUTCOME_P2))
            if o_a is None or o_b is None or o_a <= 1.0 or o_b <= 1.0:
                continue
            p_a = devig_fixed_two_way(o_a, o_b)
            p_lower = p_a if a_is_lower else 1.0 - p_a
            is_pinnacle = str(slug).strip().lower() == "pinnacle"
            originate = _PINNACLE_ORIGINATE if is_pinnacle else _SOFT_ORIGINATE
            bundle.append(
                OddsQuote(
                    provider=f"oddspapi:{slug}",
                    match=match,
                    p_a_raw=p_lower,
                    vig_type="fixed",
                    bo3=bo3,
                    liquidity=0.0,
                    originate=originate,
                    ts=0.0,
                )
            )
        if not bundle:
            return None

        # PRE-POOL the bundle to ONE Pinnacle-anchored opinion (Pitfall 7). Reuse the log-opinion
        # pool over the books, then rewrap as a single vig_type=="fixed" quote carrying the
        # bundle's MAX originate (the sharp-originator weight) so the cross-provider pool counts
        # this as ONE independent opinion.
        blended = pool(bundle)
        return OddsQuote(
            provider="oddspapi:pinnacle",
            match=match,
            p_a_raw=blended.p,
            vig_type="fixed",
            bo3=bo3,
            liquidity=0.0,
            originate=max(q.originate for q in bundle),
            ts=0.0,
        )

    def fetch(self, *, teams, api_key: str, tournament: str = "cologne",
              date_from: str | None = None, date_to: str | None = None,
              throttle_s: float = 2.0) -> list[OddsQuote]:
        """Live OddsPapi fetch (verified live 2026-06-01). httpx is lazy-imported HERE only.

        Lists CS2 (`sportId=17`) fixtures in the date window, keeps the ones whose tournament
        name/slug contains ``tournament`` (case-insensitive), pulls each one's ``/odds`` (throttled
        + retried on 429 — the free tier rate-limits bursts), joins names to ``bookmakerOdds``, and
        hands the enriched fixtures to ``get_quotes``. Every network/parse error is swallowed
        per-fixture so a partial outage still yields the books that did answer (fail-soft, ODDS-05).

        httpx/httpcore loggers are forced to WARNING so the ``apiKey`` query param is NEVER emitted
        in request-line logs (T-05-SECRET). Importing httpx inside the method keeps it OUT of the
        import path (D1/DX-01).
        """
        import logging
        import time

        import httpx

        for _n in ("httpx", "httpcore"):
            logging.getLogger(_n).setLevel(logging.WARNING)  # never log the apiKey URL (T-05-SECRET)

        base = "https://api.oddspapi.io/v4"
        params = {"apiKey": api_key, "sportId": 17, "hasOdds": "true"}
        if date_from:
            params["from"] = date_from
        if date_to:
            params["to"] = date_to
        with httpx.Client(timeout=25.0) as client:
            fixtures = client.get(f"{base}/fixtures", params=params).json()
            items = fixtures if isinstance(fixtures, list) else (
                fixtures.get("data") or fixtures.get("fixtures") or []
            )
            tkey = tournament.lower()
            cologne = [
                fx for fx in items
                if tkey in (str(fx.get("tournamentName", "")) + str(fx.get("tournamentSlug", ""))).lower()
            ]
            enriched: list[dict] = []
            for i, fx in enumerate(cologne):
                fid = fx.get("fixtureId") or fx.get("id")
                if fid is None:
                    continue
                if i:
                    time.sleep(throttle_s)  # be polite to the free tier between /odds calls
                od = self._get_odds(client, base, api_key, fid, throttle_s=throttle_s)
                if od is None:
                    continue
                enriched.append({
                    "participant1Name": fx.get("participant1Name"),
                    "participant2Name": fx.get("participant2Name"),
                    "bo3": False,  # Cologne Swiss opening rounds are Bo1
                    "bookmakerOdds": od.get("bookmakerOdds", {}) if isinstance(od, dict) else {},
                })
        return self.get_quotes(enriched, teams=teams)

    @staticmethod
    def _get_odds(client, base, api_key, fid, *, throttle_s: float = 2.0, tries: int = 3):
        """GET /odds for one fixture, retrying on HTTP 429 with linear backoff. None on failure."""
        import time
        for attempt in range(tries):
            try:
                r = client.get(f"{base}/odds", params={"apiKey": api_key, "fixtureId": fid})
            except Exception:  # noqa: BLE001 — per-fixture fail-soft
                return None
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    return None
            if r.status_code == 429 and attempt < tries - 1:
                time.sleep(throttle_s * (attempt + 2))  # back off harder each retry
                continue
            return None
        return None
