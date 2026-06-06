"""Read-only results-cache loader for the app (RES-04, threats T-06-09 / T-06-12).

The app's ONLY contact with fetched live results is ``load_results_cache`` reading
``data/results_cache.json``. This module is JSON + pathlib ONLY — it imports NO httpx /
python-dotenv / provider / engine code, so the zero-config first run is preserved (RES-04):
importing the app never pulls the network deps. It is a structural TWIN of
``ui.odds_loader.load_odds_cache`` (same four-branch fail-soft read).

The cache is a FETCHED ARTIFACT (gitignored). Its ABSENCE is the normal first-run state —
handled as fail-soft ``None`` (the app then runs with manual result entry + a banner). The
loader NEVER raises into the UI.

Schema (the FROZEN contract written by ``scripts/fetch_results.py``):
    {"_meta": {"fetched_at", "version": 1, "source", "stage"},
     "results": [{"match": [lo, hi], "winner", "round_idx", "bo", "status",
                  "provider_slugs"}]}
``match`` is the SORTED ``[lo, hi]`` engine-id tuple (same orientation as ``OddsQuote.match``
and ``KEY_LOCKED``'s ``(round_idx, winner_id, loser_id)`` shape — the loser is recoverable as
``lo if winner == hi else hi``); ``winner`` is the engine id; ``round_idx`` is 0-based
(R1 == 0); ``status`` is the provider's settled status (``finished``/``settled``);
``provider_slugs`` are the raw provider team slugs (audit trail only — never re-resolved here).
``bo`` is the series format (1 for the Swiss Bo1, 3 for the Bo3 rounds). A version bump would
make this loader reject newer caches, so it fails closed to ``None`` on any other version.
"""

from __future__ import annotations

import json
from pathlib import Path

# Default cache path — mirrors scripts.fetch_results.DEFAULT_OUT but kept local (this module
# imports no scripts/ code, so httpx/dotenv stay out of the app import path).
_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "results_cache.json"

# The only schema version this loader accepts — a version bump must be a deliberate loader
# change, so a stale/foreign schema fails closed to None (manual entry) rather than feeding
# mis-shaped data into the lock pre-fill.
_SUPPORTED_VERSION = 1


def load_results_cache(path: str | Path | None = None) -> dict | None:
    """Read ``data/results_cache.json`` read-only; return the dict, or ``None`` on ANY error.

    Returns ``None`` for a missing file, malformed JSON, a non-dict payload, or a
    ``_meta.version`` that is not ``1`` — the app then runs with manual result entry. NEVER
    raises into the UI (RES-04 fail-soft). No httpx / dotenv / provider import (T-06-09).
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
