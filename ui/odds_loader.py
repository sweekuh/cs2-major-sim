"""Read-only odds-cache loader for the app (ODDS-07/08, threat T-05-NOCACHE / T-05-APPIMPORT).

The app's ONLY contact with odds is ``load_odds_cache`` reading ``data/odds_cache.json``. This
module is JSON + pathlib ONLY — it imports NO httpx / python-dotenv / provider / engine code, so the
Phase-2 zero-config first run is preserved (DX-01): importing the app never pulls the Phase-5 network
deps. It mirrors ``ui.state.read_seeds_confirmed``'s fail-safe pattern exactly.

The cache is a FETCHED ARTIFACT (gitignored). Its ABSENCE is the normal first-run state — handled as
fail-soft ``None`` (the app then runs rating-only + the existing "live odds off" banner). The loader
NEVER raises into the UI.

Schema (the FROZEN contract written by ``scripts/fetch_odds.py``):
    {"_meta": {"fetched_at", "version": 1, "providers_present", "round_hint"},
     "blended": {"lo-hi": {"p", "var", "n_sources", "bo3"}}}
``p`` = P(lower-id team wins the SERIES); ``var`` is RAW (clamped downstream by ``beta_moment_fit``).
"""

from __future__ import annotations

import json
from pathlib import Path

# Default cache path — mirrors scripts.fetch_odds.DEFAULT_OUT but kept local (this module imports no
# scripts/ code, so httpx/dotenv stay out of the app import path).
_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "odds_cache.json"

# The only schema version this loader accepts — a version bump must be a deliberate loader change, so
# a stale/foreign schema fails closed to None (rating-only) rather than feeding mis-shaped data.
_SUPPORTED_VERSION = 1


def load_odds_cache(path: str | Path | None = None) -> dict | None:
    """Read ``data/odds_cache.json`` read-only; return the dict, or ``None`` on ANY error.

    Returns ``None`` for a missing file, malformed JSON, a non-dict payload, or a ``_meta.version``
    that is not ``1`` — the app then runs rating-only with the existing banner. NEVER raises into the
    UI (ODDS-08 fail-soft). No httpx / dotenv / provider import (T-05-APPIMPORT).
    """
    src = Path(path) if path is not None else _CACHE_PATH
    try:
        raw = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    meta = raw.get("_meta")
    if not isinstance(meta, dict) or meta.get("version") != _SUPPORTED_VERSION:
        return None
    return raw
