"""Shared team-name -> engine-id resolution for the provider parsers.

This module (NOT base.py) is where ``engine.teams`` is imported, so ``odds/base.py`` and
``pool()`` stay engine-free and pure. The providers map their fixture team STRINGS to engine
ids here so the pool/back-solve never touch provider name spelling — a name typo drops the
quote (returns None) rather than silently corrupting a DIFFERENT match (trust-boundary
"provider team strings -> engine ids", threat register row 2).

NO httpx/dotenv/streamlit import here either.
"""

from __future__ import annotations


def build_name_to_id(teams) -> dict[str, int]:
    """Map normalized team name -> engine id from a loaded team list (engine.teams.load_teams)."""
    return {_norm(t.name): t.id for t in teams}


def _norm(s: str) -> str:
    """Case/space-insensitive normalization for alias matching."""
    return "".join(s.lower().split())


def resolve_id(name: str, name_to_id: dict[str, int]) -> int | None:
    """Resolve a provider team string to an engine id (case/space-insensitive contains).

    Exact normalized match first; otherwise a substring match either direction (handles
    "Team Liquid" vs "Liquid"). Returns None when nothing matches — the caller then DROPS the
    quote rather than guessing a wrong team.
    """
    key = _norm(name)
    if key in name_to_id:
        return name_to_id[key]
    for cand, tid in name_to_id.items():
        if key and (key in cand or cand in key):
            return tid
    return None


def resolve_match(name_a: str, name_b: str, teams) -> tuple[tuple[int, int], bool] | None:
    """Resolve two team strings to a SORTED engine-id match tuple.

    Returns ``(match, a_is_lower)`` where ``match == (lower_id, higher_id)`` and ``a_is_lower``
    says whether ``name_a`` is the lower-id team — the caller uses it to orient ``p_a_raw`` to
    P(lower-id wins). Returns None if either team can't be resolved (drop the quote, fail-soft).
    """
    name_to_id = build_name_to_id(teams)
    ida = resolve_id(name_a, name_to_id)
    idb = resolve_id(name_b, name_to_id)
    if ida is None or idb is None or ida == idb:
        return None
    if ida < idb:
        return (ida, idb), True
    return (idb, ida), False
