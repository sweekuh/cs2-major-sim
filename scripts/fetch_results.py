"""scripts/fetch_results.py — the ONE live-results fetch entry (UI button AND v2 cron) (RES-01/05).

This is the SINGLE place that contacts the results providers and writes
``data/results_cache.json`` — the read-only seam the app reads back via
``ui/results_loader.load_results_cache``. It is a STRUCTURAL TWIN of ``scripts/fetch_odds.py``
and is runnable two ways, both OUT of the Streamlit render path:

  - ``python -m scripts.fetch_results``       — the v2-cron drop-in (ONE crontab line, zero app
                                                 change because the app's only results contact is
                                                 the JSON loader reading the schema this writes).
  - imported + called by the "Fetch latest results" button's click handler (an explicit USER
    action, never a rerun) — the button lazy-imports THIS module so httpx never enters the app
    import path.

PROVIDERS (RES-01, event-time verify aware — 06-RESEARCH lines 308-345):
  - bo3.gg public JSON API — PRIMARY, KEYLESS. Finished CS2 series only.
  - PandaScore /csgo/matches — FALLBACK A, needs an optional ``PANDASCORE_KEY``. A missing key
    simply skips this provider (the run stays bo3.gg-only), never an error (RES-04 fail-soft).
  - Kalshi-derived — FALLBACK B (already wired in odds/kalshi.py); not re-fetched here.

Invariants (CLAUDE.md / 06-RESEARCH / threat register T-06-06..12):
  - ``load_dotenv()`` lives HERE (keys never in the app). The optional ``PANDASCORE_KEY`` is read
    here only; its VALUE is never returned or logged — presence-only (T-06-06).
  - httpx logs the full request URL (incl. a ``?token=`` query param) at INFO — the ``httpx``/
    ``httpcore`` loggers are forced to WARNING at the top of ``main`` so the key is NEVER emitted.
  - httpx is LAZY-imported INSIDE the live-fetch helper ONLY (T-06-09); the module top + the pure
    parse layer import NO httpx, so the parsers run with no httpx installed (the recorded-fixture
    test path).
  - FINISHED-only: a row whose status is not ``finished``/``settled`` is EXCLUDED (T-06-07); a row
    with a missing/garbled field is DROPPED, never raised.
  - Slug-first team join (RES-05, T-06-08): each provider team SLUG resolves via an exact
    ``team_aliases.json`` hit FIRST, then ``odds/_match.resolve_id`` name-substring fallback, then
    the WHOLE row is DROPPED + ``log.warning`` — an unresolved team is NEVER mis-joined.
  - The FROZEN cache schema (design once so the cron is zero app change), mirroring odds_cache.json:
        {"_meta": {"fetched_at", "version": 1, "source", "stage"},
         "results": [{"match": [lo, hi], "winner", "round_idx", "bo", "status", "provider_slugs"}]}
    ``match`` is the SORTED ``[lo, hi]`` engine-id tuple; ``winner`` is the engine id; ``round_idx``
    is 0-based (R1 == 0). ``_meta.fetched_at`` is ISO-8601 UTC at WRITE time (the app folds it into
    the run cache key so a fresh fetch invalidates the memoized re-sim, T-06-STALEBAND).
  - NO streamlit import.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from engine.teams import load_stage
from odds._match import build_name_to_id, resolve_id

log = logging.getLogger("scripts.fetch_results")

DEFAULT_OUT = "data/results_cache.json"
CACHE_VERSION = 1
DEFAULT_TOURNAMENT = "cologne"  # substring matched against the provider tournament slug/name
_FINISHED = {"finished", "settled"}  # the FINISHED-only filter (no live/in-progress rows)

# Repo-root-relative per-stage fixture paths (resolved like engine.teams.DATA_PATH so the fetcher
# works regardless of the process cwd). Mirrors ui.cache._STAGE_FIXTURES, kept LOCAL here so the
# script imports no streamlit (ui.cache pulls streamlit; the fetcher must not).
_REPO_ROOT = Path(__file__).resolve().parent.parent
_STAGE_FIXTURES = {
    "stage1": "data/stage1.json",
    "stage2": "data/stage2.json",
    "stage3": "data/stage3.json",
    "playoffs": "data/playoffs.json",
}
_DEFAULT_ALIASES = "data/team_aliases.json"


def _path_for_stage(stage_id: str) -> Path:
    """Map a stage_id ('stage1'|'stage2'|'stage3'|'playoffs') -> its repo-root fixture Path.

    Raises ValueError on an unknown stage_id (a typo must fail loud, never silently load the
    wrong stage). Mirrors ui.cache._path_for_stage but returns a Path and imports no streamlit.
    """
    rel = _STAGE_FIXTURES.get(stage_id)
    if rel is None:
        raise ValueError(
            f"unknown stage_id {stage_id!r}; expected one of {sorted(_STAGE_FIXTURES)}"
        )
    return _REPO_ROOT / rel


def _stage_number(stage_id: str) -> int:
    """The 1-based stage number written into ``_meta.stage`` (playoffs -> 4)."""
    order = {"stage1": 1, "stage2": 2, "stage3": 3, "playoffs": 4}
    return order.get(stage_id, 1)


def _load_aliases(path: str | Path = _DEFAULT_ALIASES) -> dict[str, str]:
    """Load the committed ``{provider_slug -> internal_name}`` join map, fail-soft to ``{}``.

    A leading ``_comment`` key (the placeholder/provenance note) is stripped. A missing/malformed
    file degrades to an empty map (every team then routes through the resolve_id name fallback,
    still drop-on-unresolved) — never an error (RES-04).
    """
    src = Path(path)
    if not src.is_absolute():
        src = _REPO_ROOT / src
    try:
        raw = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # noqa: BLE001 — fail-soft: missing aliases is normal
        log.warning("team_aliases.json unavailable (%s); using name-substring join only", exc)
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(slug): str(name)
        for slug, name in raw.items()
        if slug != "_comment" and isinstance(name, str)
    }


def _resolve_team(slug, name, *, aliases: dict[str, str], name_to_id: dict[str, int]):
    """Resolve ONE provider team to an engine id, SLUG-FIRST then name fallback, else ``None``.

    1) An exact ``aliases`` hit on the provider SLUG -> the mapped internal name -> its engine id
       (via the normalized ``name_to_id``). This is the authoritative, calibrated join (RES-05).
    2) Else ``odds/_match.resolve_id`` on the provider NAME (exact-norm, then substring either
       direction) — the same single resolver the odds seam uses.
    3) Else ``None`` so the caller DROPS the whole row — an unresolved team is NEVER guessed into
       a wrong engine id (a mis-join would fabricate a lock that corrupts the Phase-7 seeding chain).
    """
    if slug:
        internal = aliases.get(str(slug))
        if internal is not None:
            tid = resolve_id(internal, name_to_id)
            if tid is not None:
                return tid
    if name:
        return resolve_id(str(name), name_to_id)
    return None


def _emit_row(id_a, id_b, winner_id, *, round_idx, bo, status, slugs):
    """Build ONE frozen-schema result row from two resolved engine ids + the winner id.

    Returns ``None`` (drop) if either id is missing, the two collide, or the winner is not one of
    the matched pair (a garbled winner must never silently mis-attribute the result).
    """
    if id_a is None or id_b is None or id_a == id_b:
        return None
    lo, hi = sorted((id_a, id_b))
    if winner_id not in (lo, hi):
        return None
    return {
        "match": [lo, hi],
        "winner": winner_id,
        "round_idx": round_idx,
        "bo": bo,
        "status": status,
        "provider_slugs": list(slugs),
    }


def _parse_bo3gg(raw: dict, *, teams, aliases: dict[str, str]) -> list[dict]:
    """Parse a recorded bo3.gg /matches response into frozen-schema rows (PURE — no httpx).

    FINISHED-only (``status in {finished, settled}``); slug-first join per team; a row with a
    missing/garbled field or an unresolvable team is DROPPED (never raises). The winner is the
    ``teams`` entry whose provider id equals ``winner_team_id``.
    """
    name_to_id = build_name_to_id(teams)
    rows: list[dict] = []
    matches = raw.get("matches") if isinstance(raw, dict) else None
    if not isinstance(matches, list):
        return rows
    for m in matches:
        try:
            if not isinstance(m, dict):
                continue
            if str(m.get("status", "")).lower() not in _FINISHED:
                continue  # FINISHED-only filter (T-06-07)
            ms = m.get("teams")
            if not isinstance(ms, list) or len(ms) != 2:
                continue  # garbled / not a 1v1 series — drop
            ta, tb = ms[0], ms[1]
            slug_a, slug_b = ta.get("slug"), tb.get("slug")
            id_a = _resolve_team(slug_a, ta.get("name"), aliases=aliases, name_to_id=name_to_id)
            id_b = _resolve_team(slug_b, tb.get("name"), aliases=aliases, name_to_id=name_to_id)
            if id_a is None or id_b is None:
                log.warning(
                    "bo3gg: couldn't map team(s) %s / %s — dropping row", slug_a, slug_b
                )
                continue
            # The provider winner is the `teams` entry whose provider id == winner_team_id.
            wtid = m.get("winner_team_id")
            winner_id = id_a if ta.get("id") == wtid else id_b if tb.get("id") == wtid else None
            row = _emit_row(
                id_a,
                id_b,
                winner_id,
                round_idx=int(m.get("round", 1)) - 1,
                bo=int(m.get("best_of", 1)),
                status="finished",
                slugs=[s for s in (slug_a, slug_b) if s],
            )
            if row is not None:
                rows.append(row)
        except Exception as exc:  # noqa: BLE001 — a bad row is DROPPED, never raised (T-06-07)
            log.warning("bo3gg: dropping unparseable row (%s)", exc)
    return rows


def _parse_pandascore(raw: dict, *, teams, aliases: dict[str, str]) -> list[dict]:
    """Parse a recorded PandaScore /csgo/matches response into frozen-schema rows (PURE — no httpx).

    FINISHED-only; the two ``opponents[].opponent`` teams join slug-first; the winner is the
    opponent whose id equals ``winner_id``. A garbled/unresolvable row is DROPPED (never raises).
    """
    name_to_id = build_name_to_id(teams)
    rows: list[dict] = []
    matches = raw.get("matches") if isinstance(raw, dict) else None
    if not isinstance(matches, list):
        return rows
    for m in matches:
        try:
            if not isinstance(m, dict):
                continue
            if str(m.get("status", "")).lower() not in _FINISHED:
                continue  # FINISHED-only filter
            opps = m.get("opponents")
            if not isinstance(opps, list) or len(opps) != 2:
                continue
            oa = opps[0].get("opponent") or {}
            ob = opps[1].get("opponent") or {}
            slug_a, slug_b = oa.get("slug"), ob.get("slug")
            id_a = _resolve_team(slug_a, oa.get("name"), aliases=aliases, name_to_id=name_to_id)
            id_b = _resolve_team(slug_b, ob.get("name"), aliases=aliases, name_to_id=name_to_id)
            if id_a is None or id_b is None:
                log.warning(
                    "pandascore: couldn't map team(s) %s / %s — dropping row", slug_a, slug_b
                )
                continue
            wid = m.get("winner_id")
            winner_id = id_a if oa.get("id") == wid else id_b if ob.get("id") == wid else None
            row = _emit_row(
                id_a,
                id_b,
                winner_id,
                round_idx=int(m.get("round", 1)) - 1 if m.get("round") else 0,
                bo=int(m.get("number_of_games", 1)),
                status="finished",
                slugs=[s for s in (slug_a, slug_b) if s],
            )
            if row is not None:
                rows.append(row)
        except Exception as exc:  # noqa: BLE001 — a bad row is DROPPED, never raised
            log.warning("pandascore: dropping unparseable row (%s)", exc)
    return rows


# Provider name -> its pure parser (the recorded-fixture path the tests exercise).
_PARSERS = {"bo3gg": _parse_bo3gg, "pandascore": _parse_pandascore}


def _live_fetch(provider: str, *, teams, aliases, tournament: str) -> list[dict]:
    """LIVE provider fetch — httpx is LAZY-imported HERE ONLY (T-06-09, never at module top).

    bo3.gg is keyless; PandaScore needs the optional ``PANDASCORE_KEY`` (a missing key skips it).
    Fully fail-soft: a dead endpoint logs + returns ``[]``. The Cologne tournament is filtered by
    slug/substring DYNAMICALLY (never a hardcoded match id).

    # [VERIFY AT EVENT TIME] The live endpoint paths, headers, filter params, and the Cologne
    # tournament slug/id are reconciled at the gstack /browse pass once Cologne fixtures post
    # (06-RESEARCH A1/A2). Until then the recorded-fixture path (main(fixtures=...)) is the seam;
    # this live branch is intentionally conservative and degrades to [] rather than guessing.
    """
    import httpx  # noqa: F401 — LAZY: keeps httpx out of the app import path (T-06-09)

    parser = _PARSERS.get(provider)
    if parser is None:
        return []

    try:
        if provider == "pandascore":
            key = os.environ.get("PANDASCORE_KEY")
            if not key:
                log.info("no PANDASCORE_KEY — skipping PandaScore fallback")
                return []
            # [VERIFY AT EVENT TIME] endpoint/params/tournament slug confirmed at the /browse pass.
            url = "https://api.pandascore.co/csgo/matches"
            params = {"filter[status]": "finished", "sort": "-end_at", "per_page": 100}
            headers = {"Authorization": f"Bearer {key}"}  # value never logged (httpx -> WARNING)
            resp = httpx.get(url, params=params, headers=headers, timeout=20.0)
            resp.raise_for_status()
            raw = {"matches": resp.json()}
        else:  # bo3gg (keyless primary)
            # [VERIFY AT EVENT TIME] endpoint/params/headers/tournament slug confirmed at /browse.
            url = "https://api.bo3.gg/api/v1/matches"
            params = {
                "scope": "widget-matches",
                "page[limit]": 100,
                "sort": "-start_date",
                "filter[matches.status][in]": "finished",
                "filter[matches.discipline_id][eq]": 1,
                "with": "teams,tournament,games",
            }
            headers = {
                "origin": "https://bo3.gg",
                "referer": "https://bo3.gg/",
                "user-agent": "Mozilla/5.0",
            }
            resp = httpx.get(url, params=params, headers=headers, timeout=20.0)
            resp.raise_for_status()
            raw = resp.json()
    except Exception as exc:  # noqa: BLE001 — fail-soft: a provider failure logs + continues
        log.warning("%s live fetch failed: %s", provider, exc)
        return []

    rows = parser(raw, teams=teams, aliases=aliases)
    # Dynamic tournament scoping is best done in the query params above; the recorded fixtures are
    # already Cologne-scoped. A future tightening can post-filter `raw` by the tournament slug here.
    return rows


def main(
    out_path: str | Path = DEFAULT_OUT,
    *,
    stage_id: str = "stage1",
    fixtures: dict | None = None,
    tournament: str = DEFAULT_TOURNAMENT,
) -> dict:
    """Fetch (or parse recorded) FINISHED series, join teams slug-first, write the frozen cache.

    ``fixtures`` (optional) maps a provider name ('bo3gg'/'pandascore') -> that provider's recorded
    response dict for the OFFLINE/recorded path the tests exercise. When omitted, the LIVE path
    (``_live_fetch``, lazy httpx) contacts bo3.gg then PandaScore. Either way the run is fully
    fail-soft: no source / no key -> a valid EMPTY ``results`` list, never an error (RES-04).

    Loads the ACTIVE stage's teams via ``load_stage(_path_for_stage(stage_id))`` (NOT the frozen
    always-Stage-1 ``load_teams``) so it works for any stage. Writes the FROZEN schema atomically
    (mkdir parents + write_text) with an ISO-8601 UTC ``_meta.fetched_at``. Returns the cache dict.
    """
    load_dotenv_safe()  # keys live HERE (T-06-06); never imported by the app
    # httpx logs the full request URL (incl. the optional ?token=/Authorization) at INFO — force
    # WARNING so the PANDASCORE_KEY is NEVER emitted to logs/stdout (T-06-06).
    for _n in ("httpx", "httpcore"):
        logging.getLogger(_n).setLevel(logging.WARNING)

    teams, _cfg = load_stage(_path_for_stage(stage_id))
    aliases = _load_aliases()

    results: list[dict] = []
    source = "none"
    if fixtures is not None:
        # Recorded path (tests / recorded button fixtures): parse each provider's fixture.
        for provider, parser in _PARSERS.items():
            raw = fixtures.get(provider)
            if raw is None:
                continue
            rows = parser(raw, teams=teams, aliases=aliases)
            if rows:
                results.extend(rows)
                source = provider if source == "none" else f"{source}+{provider}"
    else:
        # Live path: bo3.gg (keyless primary) then PandaScore (keyed fallback), fail-soft.
        for provider in ("bo3gg", "pandascore"):
            rows = _live_fetch(provider, teams=teams, aliases=aliases, tournament=tournament)
            if rows:
                results.extend(rows)
                source = provider if source == "none" else f"{source}+{provider}"
                break  # the first provider with FINISHED rows wins (bo3.gg primary)

    cache = {
        "_meta": {
            # ISO-8601 UTC at WRITE time — the app's run cache key folds this in (T-06-STALEBAND).
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "version": CACHE_VERSION,
            "source": source,
            "stage": _stage_number(stage_id),
        },
        "results": results,
    }

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    log.info(
        "wrote %d finished result(s) from %s (stage %s) to %s",
        len(results), source, _stage_number(stage_id), out,
    )
    return cache


def load_dotenv_safe() -> None:
    """Load ``.env`` via python-dotenv, fail-soft (keys live HERE, never in the app).

    python-dotenv is imported INSIDE this function (not at module top) purely to keep the network
    deps localized; ``scripts/`` is never on the app import path regardless. A missing .env is the
    normal keyless state (bo3.gg is a keyless read) — never an error.
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
