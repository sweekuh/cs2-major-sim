"""scripts/fetch_odds.py — the ONE odds-fetch entry (UI button AND v2 cron) (ODDS-05/06/07).

This is the SINGLE place that contacts the providers and writes ``data/odds_cache.json`` — the
read-only seam the app reads back via ``ui/odds_loader.load_odds_cache``. It is runnable two ways,
both OUT of the Streamlit render path (Pitfall 11):

  - ``python -m scripts.fetch_odds``          — the v2-cron drop-in (ONE crontab line, zero app
                                                 change because the app's only odds contact is the
                                                 JSON loader reading the schema this writes).
  - imported + called by the "fetch now" button's click handler (an explicit USER action, never a
    rerun) — the button lazy-imports THIS module so httpx/dotenv never enter the app import path.

Invariants (CLAUDE.md / 05-RESEARCH D7 / threat register):
  - ``load_dotenv()`` lives HERE (keys never in the app). ``ODDSPAPI_KEY`` is read here only; its
    VALUE is never returned or logged — presence-only (T-05-SECRET).
  - Per-provider ``try/except`` fail-soft: a provider failure logs + continues; a provider with no
    market yields ``[]`` -> a valid EMPTY ``blended`` map, NOT an error (ODDS-05, A7).
  - The FROZEN cache schema (design once so the cron is zero app change):
        {"_meta": {"fetched_at", "version": 1, "providers_present", "round_hint"},
         "blended": {"lo-hi": {"p", "var", "n_sources", "bo3"}}}
    Keys are sorted ``"loid-hiid"`` engine-id strings (``match_key``); ``p`` = P(lower-id wins the
    SERIES); ``var`` is stored RAW (clamped downstream by ``beta_moment_fit``, never here).
  - ``_meta.fetched_at`` is an ISO-8601 UTC timestamp set at WRITE time — the app folds it into the
    run cache key so a fresh fetch that moves only ``var`` still invalidates the memoized Result
    (T-05-STALEBAND).
  - NO streamlit import. ``discover_fixtures`` reuses ``engine.teams.load_teams`` /
    ``engine.swiss.build_round1_pairs`` — it NEVER re-derives seeds (the GATE-01 blocker).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from engine.swiss import build_round1_pairs
from engine.teams import load_teams
from odds.base import pool
from odds.kalshi import KalshiProvider
from odds.oddspapi import OddsPapiProvider
from odds.polymarket import PolymarketProvider

log = logging.getLogger("scripts.fetch_odds")

DEFAULT_OUT = "data/odds_cache.json"
CACHE_VERSION = 1

# The cross-provider provider set. OddsPapi is the only keyed provider (Pinnacle anchor); Polymarket
# + Kalshi are keyless public reads, so a no-key fetch still yields a 2-source pool (D3 new fact).
_PROVIDERS = (OddsPapiProvider, PolymarketProvider, KalshiProvider)


def match_key(match: tuple[int, int]) -> str:
    """The sorted ``"loid-hiid"`` engine-id string key for a match tuple (the FROZEN schema key).

    ``match`` is the sorted ``(lower_id, higher_id)`` tuple every ``OddsQuote`` already carries, so
    this just renders it — the app maps the key back to a matchup WITHOUT any provider strings.
    """
    lo, hi = sorted(match)
    return f"{lo}-{hi}"


def discover_fixtures(teams) -> dict:
    """Resolve each provider's Cologne market into the per-provider recorded-fixture inputs (ODDS-05).

    For the recorded-fixture path the providers parse a fixture dict/path directly; the live-URL
    discovery (alias-matching the known Round-1 matchups from ``build_round1_pairs`` to each
    provider's market) is a thin httpx-guarded branch.

    [DEFERRED — verify once Cologne markets post]: the live slug/ticker/field-name shapes
    (Assumptions A2-A5) cannot be confirmed until IEM Cologne 2026 markets exist. Until then this
    returns ``{}`` (no live fixtures) so ``main`` produces a valid EMPTY blended cache rather than
    contacting an endpoint that does not yet exist — the app stays fully fail-soft (rating-only +
    keyless). Reusing ``build_round1_pairs(teams)`` here pins the discovery to the PROVEN seed set
    (never re-derive seeds — the GATE-01 blocker).
    """
    # The known imminent-round matchups, pinned to the proven seed set (NEVER re-derived). Available
    # for the live-discovery branch to alias-match against each provider's posted market.
    _r1 = [(a.id, b.id) for (a, b) in build_round1_pairs(teams)]  # noqa: F841 — DEFERRED live branch
    # [DEFERRED] Live URL discovery + per-provider fetch() goes here once markets post. The recorded
    # -fixture path (tests + the offline build) supplies fixtures explicitly via main(fixtures=...).
    return {}


def _quotes_for_provider(Provider, fixtures_for_provider, *, teams) -> list:
    """Parse one provider's recorded fixture into quotes, fail-soft (never raises into ``main``)."""
    if fixtures_for_provider is None:
        return []
    try:
        return Provider().get_quotes(fixtures_for_provider, teams=teams)
    except Exception as exc:  # noqa: BLE001 — fail-soft: a provider failure logs + continues
        log.warning("provider %s failed: %s", getattr(Provider, "name", Provider), exc)
        return []


def main(out_path: str | Path = DEFAULT_OUT, *, fixtures: dict | None = None) -> dict:
    """Fetch (or parse recorded) provider odds, pool per match, write the frozen cache, return it.

    ``fixtures`` (optional) maps a provider ``name`` -> that provider's recorded fixture (dict or
    path) for the OFFLINE/recorded path the tests + button exercise. When omitted, ``discover_
    fixtures`` resolves the live markets (DEFERRED until Cologne markets post — currently ``{}``, so
    a no-fixtures run writes a valid EMPTY ``blended`` map, never an error).

    Per-provider fail-soft, per-match log-opinion ``pool()``, then the FROZEN schema is written with
    an ISO-8601 UTC ``_meta.fetched_at``. Returns the cache dict.
    """
    load_dotenv_safe()  # keys live HERE (T-05-SECRET); never imported by the app
    teams = load_teams()

    # The recorded-fixture map (button/tests) takes precedence; else discover live (DEFERRED -> {}).
    fixtures_map = fixtures if fixtures is not None else discover_fixtures(teams)

    # Gather quotes from every provider, each fail-soft and independent (ODDS-05).
    all_quotes: list = []
    providers_present: list[str] = []
    for Provider in _PROVIDERS:
        name = getattr(Provider, "name", Provider.__name__)
        provider_fixture = fixtures_map.get(name) if isinstance(fixtures_map, dict) else None
        quotes = _quotes_for_provider(Provider, provider_fixture, teams=teams)
        if quotes:
            providers_present.append(name)
            all_quotes.extend(quotes)

    # Group the independent opinions per match (sorted-id bucket) and pool each group (ODDS-03/D4).
    by_match: dict[tuple[int, int], list] = {}
    for q in all_quotes:
        by_match.setdefault(q.match, []).append(q)

    blended: dict[str, dict] = {}
    for match, group in by_match.items():
        bp = pool(group)  # var stored RAW — clamped downstream by beta_moment_fit, NEVER here
        blended[match_key(match)] = {
            "p": bp.p,
            "var": bp.var,
            "n_sources": bp.n_sources,
            "bo3": bp.bo3,
        }

    cache = {
        "_meta": {
            # ISO-8601 UTC at WRITE time — the app's run cache key folds this in (T-05-STALEBAND).
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "version": CACHE_VERSION,
            "providers_present": providers_present,
            "round_hint": 1,  # the imminent Swiss round these blended series price (R1 at stage open)
        },
        "blended": blended,
    }

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    log.info(
        "wrote %d blended match(es) from %d provider(s) to %s",
        len(blended), len(providers_present), out,
    )
    return cache


def load_dotenv_safe() -> None:
    """Load ``.env`` via python-dotenv, fail-soft (keys live HERE, never in the app).

    python-dotenv is imported INSIDE this function (not at module top) purely to keep the network
    deps localized; ``scripts/`` is never on the app import path regardless. A missing .env is the
    normal keyless state (Polymarket + Kalshi are keyless reads) — never an error.
    """
    try:
        from dotenv import load_dotenv
    except Exception as exc:  # noqa: BLE001 — dotenv missing is fail-soft (keyless run still works)
        log.warning("python-dotenv unavailable (%s); running with the ambient environment", exc)
        return
    load_dotenv()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
