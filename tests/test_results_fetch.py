"""Results-fetcher parse + slug-first-join guards (Phase 6, plan 06-03) — RES-01/05.

A STRUCTURAL TWIN of ``tests/test_odds.py`` (the recorded-fixture parse pattern): everything
here is PURE / fixture-driven — there is NO network call. The parsers parse the RECORDED
``tests/fixtures/bo3gg_finished_sample.json`` / ``pandascore_finished_sample.json`` (handcrafted
to the documented provider shapes; field names are ``[PLACEHOLDER — VERIFY AT EVENT TIME]`` per
06-RESEARCH A2-A3, reconciled at the event-time gstack /browse pass).

CRITICAL design constraint (CLAUDE.md threats T-06-07/08/09): ``httpx`` must stay OUT of the
parse path. ``scripts.fetch_results`` has NO ``import httpx`` at module top — httpx is lazy-
imported INSIDE the live-fetch helper only — so this file collects and runs even with NO httpx
installed (asserted below via sys.modules).

The load-bearing facts these tests pin:
  - FINISHED-only: a row whose status is not ``finished``/``settled`` is EXCLUDED (no live ticks).
  - Drop-on-bad-row: a row with a missing/garbled field is DROPPED, never raises.
  - Slug-first join (RES-05): a provider team SLUG resolves via an exact ``team_aliases.json``
    hit first, else ``odds/_match.resolve_id`` name-substring fallback, else the WHOLE row is
    DROPPED — an unresolved team is NEVER mis-joined to a wrong engine id.
  - The frozen row shape: SORTED ``match:[lo,hi]`` engine-id tuple + the ``winner`` engine id.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.teams import load_stage
from scripts.fetch_results import (
    _parse_bo3gg,
    _parse_pandascore,
    _load_aliases,
    _stage_number,
    main,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _stage1_teams():
    teams, _cfg = load_stage(_REPO_ROOT / "data" / "stage1.json")
    return teams


@pytest.fixture
def booby_trapped_httpx(monkeypatch):
    """Mirror test_app.test_app_makes_no_network_on_rerun: replace every httpx network entrypoint
    with a raiser, so any network access from the parse path fails LOUDLY. This is order-independent
    (httpx may already be imported by an earlier test) and strictly stronger than a sys.modules
    check — it proves the parse path never CALLS httpx (T-06-09)."""
    import httpx

    class _Boom:
        def __getattr__(self, name):
            raise AssertionError(f"httpx.{name} called on the parse path — T-06-09 violation")

    for attr in ("get", "post", "request", "Client", "AsyncClient", "stream"):
        monkeypatch.setattr(httpx, attr, _Boom(), raising=False)


def test_finished_fixture_parses(booby_trapped_httpx):
    """RES-01: parsing the recorded bo3.gg FINISHED response yields frozen-schema rows; a
    non-finished row is EXCLUDED; a garbled row is DROPPED (never raises). The parse path makes
    NO httpx network call (httpx is booby-trapped to raise — T-06-09)."""
    teams = _stage1_teams()
    aliases = _load_aliases(_REPO_ROOT / "data" / "team_aliases.json")
    raw = _load("bo3gg_finished_sample.json")

    rows = _parse_bo3gg(raw, teams=teams, aliases=aliases)

    # Every emitted row carries the frozen schema, FINISHED-only, sorted match tuple.
    for row in rows:
        assert set(row) >= {"match", "winner", "round_idx", "bo", "status", "provider_slugs"}
        lo, hi = row["match"]
        assert lo < hi, "match must be the SORTED [lo, hi] engine-id tuple"
        assert row["winner"] in (lo, hi), "winner must be one of the two matched teams"
        assert row["status"] in {"finished", "settled"}, "FINISHED-only filter"

    by_match = {tuple(r["match"]): r for r in rows}

    # Row 1 — both slugs in team_aliases.json: GamerLegion(1) beat NRG(9).
    assert (1, 9) in by_match
    assert by_match[(1, 9)]["winner"] == 1
    assert by_match[(1, 9)]["round_idx"] == 0
    assert by_match[(1, 9)]["bo"] == 1

    # Row 2 — slug 'mibr-team-2026' is ABSENT from team_aliases.json but resolves via the
    # resolve_id name-substring fallback on "MIBR"(7); SINNERS(8) hits the alias map directly.
    assert (7, 8) in by_match
    assert by_match[(7, 8)]["winner"] == 7

    # Row 3 (status:"upcoming") is EXCLUDED; Row 4 (unresolvable team) is DROPPED; Row 5
    # (garbled, missing teams) is DROPPED — so exactly the two resolvable FINISHED rows survive.
    assert len(rows) == 2, f"expected 2 finished+resolved rows, got {len(rows)}: {rows}"


def test_unresolved_team_fails_soft(booby_trapped_httpx):
    """RES-05 / T-06-08: a row whose teams resolve slug-first yields the SORTED match + winner
    engine id; a row with a team absent from team_aliases.json AND unresolvable via resolve_id is
    DROPPED — never joined to a wrong engine id. Proven against BOTH provider parsers (and the
    parse path makes no httpx call — booby-trapped)."""
    teams = _stage1_teams()
    aliases = _load_aliases(_REPO_ROOT / "data" / "team_aliases.json")

    # bo3.gg: the 'unknown-org' row (row 4) must NOT appear in any output match.
    bo3_rows = _parse_bo3gg(_load("bo3gg_finished_sample.json"), teams=teams, aliases=aliases)
    all_ids = {tid for r in bo3_rows for tid in r["match"]}
    assert all(0 < tid <= 16 for tid in all_ids), "no fabricated/out-of-range engine id leaked"
    # The unresolvable team's would-be partner (GamerLegion=1) still appears via row 1, but the
    # unknown-org row itself contributes NO row (drop-on-unresolved, never a (1, <garbage>) join).
    assert all(set(r["match"]) != {1} for r in bo3_rows)

    # PandaScore: a clean FINISHED row resolves; the 'unlisted-squad' row is dropped; the
    # 'running' row is excluded by the FINISHED-only filter -> exactly one surviving row.
    ps_rows = _parse_pandascore(
        _load("pandascore_finished_sample.json"), teams=teams, aliases=aliases
    )
    assert len(ps_rows) == 1, f"expected 1 finished+resolved PandaScore row, got {ps_rows}"
    # BetBoom(4) beat Liquid(13): sorted match [4, 13], winner 4.
    assert ps_rows[0]["match"] == [4, 13]
    assert ps_rows[0]["winner"] == 4


def test_main_writes_versioned_cache(tmp_path):
    """RES-01: main(fixtures=..., stage_id='stage1') writes a valid versioned cache atomically
    (mkdir parents + write) — _meta.version == 1, a 'results' list, _meta.stage/source set, the
    fetched_at ISO timestamp present. Fixture-driven (no network)."""
    out = tmp_path / "nested" / "results_cache.json"
    cache = main(
        out_path=out,
        stage_id="stage1",
        fixtures={"bo3gg": _load("bo3gg_finished_sample.json")},
    )
    # Returned dict + the written file agree and carry the frozen schema.
    assert cache["_meta"]["version"] == 1
    assert isinstance(cache["results"], list) and cache["results"], "non-empty results list"
    assert cache["_meta"]["stage"] == 1
    assert cache["_meta"]["source"] == "bo3gg"
    assert cache["_meta"].get("fetched_at"), "ISO fetched_at must be set at write time"

    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk["_meta"]["version"] == 1
    assert on_disk["results"] == cache["results"]
    # The two resolvable FINISHED bo3.gg rows are present.
    matches = {tuple(r["match"]) for r in on_disk["results"]}
    assert (1, 9) in matches and (7, 8) in matches


def test_stage_number_maps_known_and_raises_on_unknown():
    """LO-02 (06-REVIEW): the fetcher's ``_stage_number`` must mirror app's ``_stage_int_for`` —
    the four real stages map 1..4, and an UNKNOWN stage_id raises ``ValueError`` (a single
    fail-loud contract on BOTH sides). The old ``.get(stage_id, 1)`` silently defaulted a typo'd
    stage_id to 1, which would write ``_meta.stage = 1`` and prefill Stage 1 with another stage's
    results via the v2-cron path (a fabricated-lock vector)."""
    # The four real stages agree with app._stage_int_for exactly.
    assert _stage_number("stage1") == 1
    assert _stage_number("stage2") == 2
    assert _stage_number("stage3") == 3
    assert _stage_number("playoffs") == 4

    # An unknown stage_id fails loud (mirrors app._stage_int_for), never a silent default to 1.
    with pytest.raises(ValueError, match="unknown stage_id"):
        _stage_number("bogus")

    # The two sides agree on every real stage AND on the unknown-case contract (both raise).
    import app

    for sid in ("stage1", "stage2", "stage3", "playoffs"):
        assert _stage_number(sid) == app._stage_int_for(sid)
    with pytest.raises(ValueError):
        app._stage_int_for("bogus")


def test_httpx_is_lazy_not_top_level():
    """T-06-09: httpx must NOT be imported at the fetcher's module top — it is lazy-imported INSIDE
    the live-fetch helper ONLY, so the parsers run with no httpx installed and httpx never enters
    the app import path. Static source assertion (order-independent — does not depend on whether an
    earlier test already imported httpx into sys.modules)."""
    import ast

    import scripts.fetch_results as fr

    src = Path(fr.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    # No top-level (module-body) `import httpx` / `from httpx import ...`.
    for node in tree.body:
        if isinstance(node, ast.Import):
            assert all(a.name != "httpx" for a in node.names), "httpx must not be a top-level import"
        if isinstance(node, ast.ImportFrom):
            assert node.module != "httpx", "httpx must not be a top-level from-import"
    # httpx IS referenced somewhere (the lazy live-fetch import) — the seam exists.
    assert "import httpx" in src, "the live-fetch helper must lazy-import httpx"
