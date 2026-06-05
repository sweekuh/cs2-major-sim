"""Single source of truth for the Cologne 2026 Stage-1 fixture.

Owns: the 16-team seed->team map, R1 pairing DERIVED from that map (ENG-01, no second
hardcoded copy), default [INFERRED] ratings, and the Stage config. Loads/validates the
shipped data/stage1.json (threat T-01-01: raise loudly on dup/short seed lists or bad
ratings). Imports no streamlit/httpx/requests (functional-core invariant).

Seeds + default ratings are [INFERRED] (HANDOFF §3) from announced R1 pairings and HLTV
late-May 2026 order; M80=6, NRG=9, Liquid=13 are confirmed. They MUST be editable and
reconciled against the official seed list at lock — a wrong seed silently corrupts every
probability. The Phase-2 editor and DX-01 zero-config run consume data/stage1.json.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Stage config (HANDOFF §3): 16 teams, advance at 3 wins, eliminate at 3 losses.
STAGE_SIZE = 16
ADVANCE_AT_WINS = 3
ELIMINATE_AT_LOSSES = 3

# Path to the shipped editable fixture.
DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "stage1.json"

# [INFERRED] Cologne Stage-1 seed -> (name, default rating). HANDOFF §3 table.
# This is the canonical in-code default; data/stage1.json round-trips the same values.
_DEFAULT_FIXTURE: dict[int, tuple[str, int]] = {
    1: ("GamerLegion", 92),
    2: ("B8", 78),
    3: ("HEROIC", 58),
    4: ("BetBoom", 72),
    5: ("BIG", 55),
    6: ("M80", 60),
    7: ("MIBR", 68),
    8: ("SINNERS", 46),
    9: ("NRG", 54),
    10: ("TYLOO", 50),
    11: ("Sharks", 49),
    12: ("Gaimin Gladiators", 47),
    13: ("Liquid", 57),
    14: ("Lynn Vision", 52),
    15: ("THUNDER dOWNUNDER", 42),
    16: ("FlyQuest", 40),
}


@dataclass(eq=False)
class Team:
    """Per-team Swiss state (HANDOFF §4).

    ``opps`` is the set of opponent TEAM OBJECTS faced this stage. It holds objects (not
    ids) because the canonical difficulty()/Buchholz reads ``o.wins - o.losses`` over the
    opponents; the no-rematch rule compares opponent ``.id``. ``id`` defaults to ``seed``
    for the Stage-1 fixture.

    ``eq=False`` gives identity-based equality + hashing so a Team can be stored in the
    ``opps`` set (the default dataclass ``__eq__`` makes instances unhashable, which would
    crash ``opps.add(team)``). Each Team is a distinct stage entity, so identity equality
    is correct here.
    """

    id: int
    name: str
    seed: int
    rating: float
    wins: int = 0
    losses: int = 0
    opps: set = field(default_factory=set)


def _validate_fixture(rows: dict[int, tuple[str, float]]) -> None:
    """Raise loudly on a malformed fixture (threat T-01-01, V5 input validation).

    Enforces exactly STAGE_SIZE unique seeds 1..STAGE_SIZE, unique team names, and finite
    in-range ratings. A wrong seed count or duplicate seed silently corrupts every pairing,
    so this fails hard rather than degrading.
    """
    seeds = list(rows.keys())
    if len(seeds) != STAGE_SIZE:
        raise ValueError(f"fixture must have exactly {STAGE_SIZE} teams, got {len(seeds)}")
    # NOTE: ``rows`` is a dict keyed by seed, so duplicate seeds are impossible here by
    # construction (dict keys are unique). Duplicate detection for the JSON load path
    # happens earlier in load_teams() (the ``if seed in rows`` guard); the in-code
    # _DEFAULT_FIXTURE path cannot have duplicates either. The exact-seed-set check below
    # subsumes any count/range mismatch.
    if set(seeds) != set(range(1, STAGE_SIZE + 1)):
        raise ValueError(f"seeds must be exactly 1..{STAGE_SIZE}, got {sorted(seeds)}")
    names = [name for name, _ in rows.values()]
    if len(set(names)) != len(names):
        raise ValueError("duplicate team name in fixture")
    for seed, (name, rating) in rows.items():
        if not isinstance(rating, (int, float)):
            raise ValueError(f"rating for seed {seed} ({name}) is not numeric: {rating!r}")
        # NaN check (NaN != NaN) and a sane bound for a 0..100-ish strength scale.
        if rating != rating or not (0 < rating < 1000):
            raise ValueError(f"rating for seed {seed} ({name}) out of range: {rating!r}")


def _teams_from_rows(rows: dict[int, tuple[str, float]]) -> list[Team]:
    _validate_fixture(rows)
    return [
        Team(id=seed, name=name, seed=seed, rating=float(rating))
        for seed, (name, rating) in sorted(rows.items())
    ]


def load_teams(path: Path | str | None = None) -> list[Team]:
    """Load the 16-team fixture, validated, as a seed-ordered list of Teams.

    ``path=None`` loads the shipped data/stage1.json if present, else falls back to the
    in-code [INFERRED] default (DX-01 zero-config: the first sim runs with no setup).
    Any JSON load path is validated (16 unique seeds / 16 teams); raises loudly on
    mismatch, duplicate seed, or bad rating (threat T-01-01).
    """
    if path is None and not DATA_PATH.exists():
        return _teams_from_rows(_DEFAULT_FIXTURE)
    src = Path(path) if path is not None else DATA_PATH
    raw = json.loads(src.read_text(encoding="utf-8"))
    teams_json = raw.get("teams") if isinstance(raw, dict) else raw
    if not isinstance(teams_json, list):
        raise ValueError("stage1.json must contain a 'teams' list")
    rows: dict[int, tuple[str, float]] = {}
    for entry in teams_json:
        if not isinstance(entry, dict):
            raise ValueError(
                f"each team entry must be a dict, got {type(entry).__name__!r}"
            )
        for field_name in ("seed", "name", "rating"):
            if field_name not in entry:
                raise ValueError(
                    f"team entry missing required field {field_name!r}: {entry!r}"
                )
        seed = entry["seed"]
        if seed in rows:
            raise ValueError(f"duplicate seed {seed} in {src}")
        rows[seed] = (entry["name"], entry["rating"])
    return _teams_from_rows(rows)


# --- Multi-stage siblings (Phase 6, STG-01) ----------------------------------------------
# NEW SIBLINGS of the byte-frozen GATE-01 path above (_validate_fixture / load_teams). They
# generalize the loader to ANY per-stage fixture (Stage 2/3 / playoffs) WITHOUT editing — or
# being reached by — the frozen Stage-1 functions. _validate_fixture stays literal STAGE_SIZE;
# this sibling parameterizes the same checks on the fixture's OWN declared stage.size.


def _validate_fixture_for_size(rows: dict[int, tuple[str, float]], size: int) -> None:
    """Size-parameterized twin of _validate_fixture (threat T-06-01, V5 input validation).

    Same loud-fail contract as the frozen _validate_fixture — exactly ``size`` unique seeds
    1..size, unique team names, finite in-range ratings — but checked against the ``size``
    parameter (read from the fixture's ``stage.size``) instead of the literal STAGE_SIZE, so
    a non-16 stage (e.g. the 8-team playoff bracket) validates against its OWN size. A bad
    fixture raises rather than silently corrupting every pairing.
    """
    seeds = list(rows.keys())
    if len(seeds) != size:
        raise ValueError(f"fixture must have exactly {size} teams, got {len(seeds)}")
    if set(seeds) != set(range(1, size + 1)):
        raise ValueError(f"seeds must be exactly 1..{size}, got {sorted(seeds)}")
    names = [name for name, _ in rows.values()]
    if len(set(names)) != len(names):
        raise ValueError("duplicate team name in fixture")
    for seed, (name, rating) in rows.items():
        if not isinstance(rating, (int, float)):
            raise ValueError(f"rating for seed {seed} ({name}) is not numeric: {rating!r}")
        # NaN check (NaN != NaN) and a sane bound for a 0..100-ish strength scale.
        if rating != rating or not (0 < rating < 1000):
            raise ValueError(f"rating for seed {seed} ({name}) out of range: {rating!r}")


def load_stage(path: str | Path) -> tuple[list[Team], dict]:
    """Load any per-stage fixture, validated against its OWN declared stage.size.

    Returns ``(teams, stage_config)`` where ``teams`` is the seed-ordered list[Team] (same
    ordering as _teams_from_rows) and ``stage_config`` carries at least ``size`` and
    ``seeds_confirmed`` (plus any other keys from the JSON ``stage`` block). load_teams /
    _DEFAULT_FIXTURE / _validate_fixture (the GATE-01 path) are NOT called and NOT edited —
    this is a pure sibling. Reuses load_teams's dup-seed guard (``if seed in rows``). Imports
    no streamlit/httpx (functional-core invariant).
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    stage = raw.get("stage") or {}
    size = int(stage.get("size", STAGE_SIZE))
    rows: dict[int, tuple[str, float]] = {}
    for entry in raw["teams"]:
        seed = entry["seed"]
        if seed in rows:
            raise ValueError(f"duplicate seed {seed} in {path}")
        rows[seed] = (entry["name"], entry["rating"])
    _validate_fixture_for_size(rows, size)
    teams = [
        Team(id=s, name=n, seed=s, rating=float(r)) for s, (n, r) in sorted(rows.items())
    ]
    return teams, {
        "size": size,
        "seeds_confirmed": bool(raw.get("seeds_confirmed", False)),
        **stage,
    }


def build_round1_pairs(teams: list[Team]) -> list[tuple[Team, Team]]:
    """Derive the Round-1 pairings from the single seed->team map (ENG-01).

    R1 pairing is ``[(i, i + 8) for i in range(1, 9)]`` -> seed i faces seed i+8. This is
    DERIVED from the seed map — there is no second hardcoded R1 table (Anti-Pattern 4).
    """
    by_seed = {t.seed: t for t in teams}
    return [(by_seed[i], by_seed[i + 8]) for i in range(1, 9)]
