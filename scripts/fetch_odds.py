"""scripts/fetch_odds.py — the ONE odds-fetch entry (UI button AND v2 cron) (ODDS-05/06/07).

This is the SINGLE place that contacts the providers and writes ``data/odds_cache.json`` — the
read-only seam the app reads back via ``ui/odds_loader.load_odds_cache``. It is runnable two ways,
both OUT of the Streamlit render path (Pitfall 11):

  - ``python -m scripts.fetch_odds``          — the v2-cron drop-in (ONE crontab line, zero app
                                                 change because the app's only odds contact is the
                                                 JSON loader reading the schema this writes).
  - imported + called by the "fetch now" button's click handler (an explicit USER action, never a
    rerun) — the button lazy-imports THIS module so httpx/dotenv never enter the app import path.

LIVE PROVIDERS (verified live 2026-06-01 against IEM Cologne markets):
  - OddsPapi (Pinnacle anchor) — KEYED: needs ``ODDSPAPI_KEY``. Missing key -> skipped, the run
    degrades to Kalshi-only, never an error (ODDS-08 fail-soft).
  - Kalshi (KXCS2GAME match winners) — KEYLESS public read.
  - Polymarket is NOT fetched live: its CS2 coverage is novelty futures only (no per-match Cologne
    markets), confirmed at the live-verify probe. The parser stays for the recorded-fixture path.

Invariants (CLAUDE.md / 05-RESEARCH D7 / threat register):
  - ``load_dotenv()`` lives HERE (keys never in the app). ``ODDSPAPI_KEY`` is read here only; its
    VALUE is never returned or logged — presence-only (T-05-SECRET).
  - Per-provider ``try/except`` fail-soft: a provider failure logs + continues; a provider with no
    market yields ``[]`` -> a valid EMPTY ``blended`` map, NOT an error (ODDS-05, A7).
  - The FROZEN cache schema (design once so the cron is zero app change):
        {"_meta": {"fetched_at", "version": 1, "providers_present", "round_hint", "stage"},
         "blended": {"lo-hi": {"p", "var", "n_sources", "bo3",
                               "sources": [{"book", "p"}]}}}
    ``sources`` (D3) is ADDITIVE within v1 — per-source prices for the drill-down; an older
    sources-unaware reader ignores it (so a new cache still loads in an old app — no version bump).
    ``stage`` (v3 multi-stage) is likewise ADDITIVE within v1: the 1-based stage int (playoffs -> 4)
    the quotes were joined against, mirroring results_cache.json's ``_meta.stage``. The app refuses
    to feed a cache whose stage differs from the ACTIVE stage — blended keys are ENGINE-ID strings,
    and Stage-1 id 5 is a DIFFERENT TEAM from Stage-3 id 5, so a cross-stage feed would price the
    sim with another stage's teams (the same mis-join class as the n=N inflation: latent until live
    odds turn on, plausible-looking output). A legacy cache without ``stage`` reads as stage 1.
    Keys are sorted ``"loid-hiid"`` engine-id strings (``match_key``); ``p`` = P(lower-id wins the
    SERIES); ``var`` is stored RAW (clamped downstream by ``beta_moment_fit``, never here).
  - ``_meta.fetched_at`` is an ISO-8601 UTC timestamp set at WRITE time — the app folds it into the
    run cache key so a fresh fetch that moves only ``var`` still invalidates the memoized Result
    (T-05-STALEBAND).
  - NO streamlit import.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engine.teams import load_stage
from odds.base import pool
from odds.kalshi import KalshiProvider
from odds.oddspapi import OddsPapiProvider
from odds.polymarket import PolymarketProvider

log = logging.getLogger("scripts.fetch_odds")

DEFAULT_OUT = "data/odds_cache.json"
CACHE_VERSION = 1
DEFAULT_TOURNAMENT = "cologne"  # substring matched against provider tournament/rules text

# Repo-root-relative per-stage fixture paths — the STRUCTURAL TWIN of scripts.fetch_results'
# copies (kept local for the same reason: scripts/ never imports ui.cache, which pulls streamlit).
# The old module loaded the frozen always-Stage-1 ``load_teams``, so a Stage-2/3 fetch joined
# provider markets against STAGE-1 names/ids — the dropped-row/mis-join failure the results
# fetcher already guards against (RES-05). Per-stage loading closes the same hole here.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_STAGE_FIXTURES = {
    "stage1": "data/stage1.json",
    "stage2": "data/stage2.json",
    "stage3": "data/stage3.json",
    "playoffs": "data/playoffs.json",
}


def _path_for_stage(stage_id: str) -> Path:
    """Map a stage_id -> its repo-root fixture Path; ValueError on a typo (fail loud, never
    silently load the wrong stage). Mirrors scripts.fetch_results._path_for_stage."""
    rel = _STAGE_FIXTURES.get(stage_id)
    if rel is None:
        raise ValueError(
            f"unknown stage_id {stage_id!r}; expected one of {sorted(_STAGE_FIXTURES)}"
        )
    return _REPO_ROOT / rel


def _stage_number(stage_id: str) -> int:
    """The 1-based stage number written into ``_meta.stage`` (playoffs -> 4) — the SAME fail-loud
    contract as scripts.fetch_results._stage_number / app._stage_int_for, so the writer and the
    app's read-side stage filter can never disagree on what an int means."""
    order = {"stage1": 1, "stage2": 2, "stage3": 3, "playoffs": 4}
    if stage_id not in order:
        raise ValueError(f"unknown stage_id {stage_id!r}; expected one of {sorted(order)}")
    return order[stage_id]


# The recorded-fixture provider set (button-recorded / tests parse explicit fixtures via main(
# fixtures=...)). The LIVE path is handled by `_live_quotes` (OddsPapi + Kalshi only).
_PROVIDERS = (OddsPapiProvider, PolymarketProvider, KalshiProvider)


def match_key(match: tuple[int, int]) -> str:
    """The sorted ``"loid-hiid"`` engine-id string key for a match tuple (the FROZEN schema key)."""
    lo, hi = sorted(match)
    return f"{lo}-{hi}"


def _quotes_for_provider(Provider, fixtures_for_provider, *, teams) -> list:
    """Parse one provider's recorded fixture into quotes, fail-soft (never raises into ``main``)."""
    if fixtures_for_provider is None:
        return []
    try:
        return Provider().get_quotes(fixtures_for_provider, teams=teams)
    except Exception as exc:  # noqa: BLE001 — fail-soft: a provider failure logs + continues
        log.warning("provider %s failed: %s", getattr(Provider, "name", Provider), exc)
        return []


def _live_quotes(teams, *, tournament: str = DEFAULT_TOURNAMENT) -> tuple[list, list[str]]:
    """Gather LIVE quotes from OddsPapi (keyed) + Kalshi (keyless), each fully fail-soft.

    Returns ``(quotes, providers_present)``. A missing ``ODDSPAPI_KEY`` simply drops the Pinnacle
    anchor and the run continues Kalshi-only (ODDS-08). The key's VALUE is never logged.
    """
    quotes: list = []
    present: list[str] = []

    # OddsPapi (Pinnacle anchor) — KEYED. 9-day window (their cap is 10 days for sportId-only).
    key = os.environ.get("ODDSPAPI_KEY")
    if key:
        now = datetime.now(timezone.utc)
        d_from = now.strftime("%Y-%m-%dT00:00:00Z")
        d_to = (now + timedelta(days=9)).strftime("%Y-%m-%dT00:00:00Z")
        try:
            q = OddsPapiProvider().fetch(
                teams=teams, api_key=key, tournament=tournament, date_from=d_from, date_to=d_to
            )
            if q:
                quotes.extend(q)
                present.append("oddspapi")
        except Exception as exc:  # noqa: BLE001 — fail-soft
            log.warning("oddspapi live fetch failed: %s", exc)
    else:
        log.info("no ODDSPAPI_KEY — skipping OddsPapi/Pinnacle anchor (Kalshi-only run)")

    # Kalshi (KXCS2GAME) — KEYLESS.
    try:
        q = KalshiProvider().fetch(teams=teams, tournament=tournament)
        if q:
            quotes.extend(q)
            present.append("kalshi")
    except Exception as exc:  # noqa: BLE001 — fail-soft
        log.warning("kalshi live fetch failed: %s", exc)

    return quotes, present


def main(out_path: str | Path = DEFAULT_OUT, *, stage_id: str = "stage1",
         fixtures: dict | None = None, tournament: str = DEFAULT_TOURNAMENT) -> dict:
    """Fetch (or parse recorded) provider odds, pool per match, write the frozen cache, return it.

    ``fixtures`` (optional) maps a provider ``name`` -> that provider's recorded fixture (dict or
    path) for the OFFLINE/recorded path the tests exercise. When omitted, the LIVE path
    (``_live_quotes``) contacts OddsPapi + Kalshi. Either way the run is fully fail-soft: no
    market / no key -> a valid EMPTY ``blended`` map, never an error.

    Loads the ACTIVE stage's teams via ``load_stage(_path_for_stage(stage_id))`` (NOT the frozen
    always-Stage-1 ``load_teams``) so the provider-name join resolves against the stage actually
    being priced, and stamps ``_meta.stage`` so the app can refuse a cross-stage cache.

    Per-match log-opinion ``pool()``, then the FROZEN schema is written with an ISO-8601 UTC
    ``_meta.fetched_at``. Returns the cache dict.
    """
    load_dotenv_safe()  # keys live HERE (T-05-SECRET); never imported by the app
    # httpx logs the full request URL (incl. the ?apiKey=… query param) at INFO — force WARNING so
    # the OddsPapi key is NEVER emitted to logs/stdout (T-05-SECRET).
    for _n in ("httpx", "httpcore"):
        logging.getLogger(_n).setLevel(logging.WARNING)
    teams, _cfg = load_stage(_path_for_stage(stage_id))
    # On an all-Bo3 stage (Stage 3) every series a provider prices IS a Bo3 by rule, regardless
    # of the provider's per-market flag (Kalshi carries none and defaults False — correct for the
    # Bo1 opening rounds of Stage 1/2 only). Left False, the app's invert_series(p, bo3=False)
    # would take the SERIES price as a MAP prob and re-inflate it through p²(3−2p) in the sim —
    # systematically overrating every favorite (the same silent-corruption class as Pitfall 9).
    all_bo3 = bool((_cfg or {}).get("all_bo3", False))

    if fixtures is not None:
        # Recorded path (tests / recorded button fixtures): parse each provider's fixture.
        all_quotes: list = []
        providers_present: list[str] = []
        for Provider in _PROVIDERS:
            name = getattr(Provider, "name", Provider.__name__)
            quotes = _quotes_for_provider(Provider, fixtures.get(name), teams=teams)
            if quotes:
                providers_present.append(name)
                all_quotes.extend(quotes)
    else:
        # Live path: OddsPapi (keyed) + Kalshi (keyless), fail-soft.
        all_quotes, providers_present = _live_quotes(teams, tournament=tournament)

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
            "bo3": True if all_bo3 else bp.bo3,
            # Per-source prices for the "why the books disagree" drill-down (D3). ADDITIVE within
            # schema v1 (NOT a version bump): the loader returns the dict intact and an older,
            # sources-unaware app simply ignores this key — so a new cache still loads in an old app
            # (a v2 bump would make old loaders reject it). ``book`` is the raw provider name (the
            # app maps it to a display label); ``p`` is that source's P(lower-id wins the SERIES).
            "sources": [{"book": q.provider, "p": float(q.p_a_raw)} for q in group],
        }

    cache = {
        "_meta": {
            # ISO-8601 UTC at WRITE time — the app's run cache key folds this in (T-05-STALEBAND).
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "version": CACHE_VERSION,
            "providers_present": providers_present,
            "round_hint": 1,  # the imminent Swiss round these blended series price (R1 at stage open)
            # The stage these ENGINE-ID-keyed quotes belong to (ADDITIVE within v1, mirrors
            # results_cache.json). The app's read side refuses a stage mismatch — id 5 is a
            # different team each stage, so a cross-stage feed would price the wrong teams.
            "stage": _stage_number(stage_id),
        },
        "blended": blended,
    }

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    log.info(
        "wrote %d blended match(es) from %d provider(s) %s to %s",
        len(blended), len(providers_present), providers_present, out,
    )
    return cache


def load_dotenv_safe() -> None:
    """Load ``.env`` via python-dotenv, fail-soft (keys live HERE, never in the app).

    python-dotenv is imported INSIDE this function (not at module top) purely to keep the network
    deps localized; ``scripts/`` is never on the app import path regardless. A missing .env is the
    normal keyless state (Kalshi is a keyless read) — never an error.
    """
    try:
        from dotenv import load_dotenv
    except Exception as exc:  # noqa: BLE001 — dotenv missing is fail-soft (keyless run still works)
        log.warning("python-dotenv unavailable (%s); running with the ambient environment", exc)
        return
    load_dotenv()


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    _ap = argparse.ArgumentParser(description="Fetch live odds into data/odds_cache.json")
    _ap.add_argument(
        "--stage", default="stage1", choices=sorted(_STAGE_FIXTURES),
        help="stage whose teams the markets are joined against (stamps _meta.stage)",
    )
    _ap.add_argument("--out", default=DEFAULT_OUT, help="cache path to write")
    _ns = _ap.parse_args()
    main(_ns.out, stage_id=_ns.stage)
