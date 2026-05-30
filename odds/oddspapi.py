"""OddsPapiProvider — fixed-odds de-vig + soft-book bundle pre-pool (ODDS-03, Pitfall 7).

OddsPapi returns Pinnacle (the sharp originator) plus soft books (Thunderpick, GG.BET, Betway,
…) that COPY Pinnacle's line — heavily correlated, NOT independent sources. This provider:
  1. de-vigs EACH book's two-way fixed odds via ``devig_fixed_two_way`` (vig_type=="fixed"),
  2. PRE-POOLS the whole bundle into EXACTLY ONE Pinnacle-anchored OddsQuote (Pinnacle weighted
     originate=1.0, soft copies <1.0) via the same log-opinion ``pool()`` math, BEFORE the
     cross-provider pool ever sees it.
So the cross-provider ``pool()`` sees ONE OddsPapi opinion and never headcounts the soft books
(Pitfall 7, threat T-05-HEADCOUNT) — ``n_sources`` counts independent originators, not books.

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


def _as_dict(fixtures) -> dict:
    """Accept a parsed dict OR a path to a recorded fixture (no network)."""
    if isinstance(fixtures, (str, Path)):
        return json.loads(Path(fixtures).read_text(encoding="utf-8"))
    return fixtures


class OddsPapiProvider:
    """Parse a recorded OddsPapi /odds fixture into one Pinnacle-anchored OddsQuote per match."""

    name = "oddspapi"

    def get_quotes(self, fixtures, *, teams) -> list[OddsQuote]:
        """Parse the recorded /odds fixture -> list[OddsQuote], one per resolvable match.

        Each match's soft-book bundle is collapsed to ONE quote (Pitfall 7). Parses defensively:
        a missing/empty bundle or an unresolvable matchup yields no quote for that match (never
        raises) — the fail-soft empty path (ODDS-05).
        """
        try:
            raw = _as_dict(fixtures)
        except (OSError, ValueError):
            return []
        # The recorded fixture is a single match object; tolerate a list of them too.
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
        name_a = m.get("participantAName")
        name_b = m.get("participantBName")
        books = m.get("bookmakerOdds") or []
        if not name_a or not name_b or not books:
            return None
        resolved = resolve_match(name_a, name_b, teams)
        if resolved is None:
            return None
        match, a_is_lower = resolved
        bo3 = bool(m.get("bo3", False))

        # De-vig each book to P(participant A wins), then orient to P(lower-id wins).
        bundle: list[OddsQuote] = []
        for b in books:
            try:
                o_a = float(b["oddsA"])
                o_b = float(b["oddsB"])
            except (KeyError, TypeError, ValueError):
                continue
            if o_a <= 1.0 or o_b <= 1.0:
                continue
            p_a = devig_fixed_two_way(o_a, o_b)
            p_lower = p_a if a_is_lower else 1.0 - p_a
            is_pinnacle = str(b.get("bookmaker", "")).strip().lower() == "pinnacle"
            originate = _PINNACLE_ORIGINATE if is_pinnacle else _SOFT_ORIGINATE
            bundle.append(
                OddsQuote(
                    provider=f"oddspapi:{b.get('bookmaker', '?')}",
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

    def fetch(self, fixtures, *, teams, api_key: str | None = None) -> list[OddsQuote]:
        """Live OddsPapi fetch (DEFERRED-verified in 05-03). httpx is lazy-imported HERE only.

        This is the network branch — never called by the fixture tests. Importing httpx inside
        the method body (not at module top) keeps it OUT of the import path so the parse path
        collects with no httpx installed (D1/DX-01).
        """
        import httpx  # noqa: F401  — lazy: network branch only, NEVER at module top (D1/DX-01)

        raise NotImplementedError(
            "Live OddsPapi fetch is built + verified at the 05-03 live-slug checkpoint; "
            "05-01 parses recorded fixtures only."
        )
