"""Read-only results-cache loader guard (Phase 6, plan 06-03) — RES-04 fail-soft.

A STRUCTURAL TWIN of ``tests/test_app.py::test_cache_loader_failsoft`` (the odds-cache
loader), copied 1:1 against ``ui.results_loader.load_results_cache`` with the ``results``
schema instead of ``blended``.

CRITICAL design constraint (CLAUDE.md threat T-06-09 / RES-04): ``ui/results_loader.py``
imports ONLY ``json`` + ``pathlib`` — NO httpx / python-dotenv / provider / engine import —
so the zero-config first run is preserved and httpx never enters the app import path. The
four fail-soft branches (missing / malformed / non-dict / wrong-version -> ``None``) are the
load-bearing contract: the loader NEVER raises into the UI; an absent cache is the normal
first-run state (manual entry + banner).
"""

from __future__ import annotations

import json

from ui.results_loader import load_results_cache


def test_results_cache_failsoft(tmp_path):
    """RES-04 / T-06-12: load_results_cache returns None on a missing path, malformed JSON, a
    non-dict payload, and a wrong (_meta.version != 1) schema — never raises. A valid v1 cache
    round-trips. Pure unit (no AppTest)."""
    # Missing file -> None (the normal first-run state).
    assert load_results_cache(tmp_path / "nope.json") is None

    # Malformed JSON -> None.
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_results_cache(bad) is None

    # Non-dict payload -> None.
    arr = tmp_path / "arr.json"
    arr.write_text("[1, 2, 3]", encoding="utf-8")
    assert load_results_cache(arr) is None

    # Wrong version -> None (fails closed rather than feeding a foreign schema).
    wrongver = tmp_path / "v2.json"
    wrongver.write_text(
        json.dumps({"_meta": {"version": 2}, "results": []}), encoding="utf-8"
    )
    assert load_results_cache(wrongver) is None

    # A valid v1 cache round-trips (the dict is returned intact).
    good = tmp_path / "good.json"
    payload = {
        "_meta": {
            "fetched_at": "2026-06-04T00:00:00+00:00",
            "version": 1,
            "source": "bo3gg",
            "stage": 1,
        },
        "results": [
            {
                "match": [1, 9],
                "winner": 1,
                "round_idx": 0,
                "bo": 1,
                "status": "finished",
                "provider_slugs": ["gamerlegion", "nrg"],
            }
        ],
    }
    good.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_results_cache(good)
    assert loaded is not None
    assert loaded["results"][0]["winner"] == 1
    assert loaded["_meta"]["stage"] == 1
