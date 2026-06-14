"""SoccerTeam fixture model + loader for the 2026 World Cup (48 teams, 12 groups of 4).

Unlike the CS2 ``engine.teams.Team`` (Swiss state: wins/losses/opps, id==seed, 16-team stage),
a ``SoccerTeam`` carries an independent strength prior split into ``attack``/``defence`` (the
inputs to the Dixon-Coles model) plus a single ``elo`` the priors can be derived from, and the
``group`` letter it was drawn into. State accumulated during a simulation (points, GF, GA) lives
on per-sim row objects in ``group_stage.py``, NOT here — this is the immutable fixture template.

The loader is data-driven: ``data/wc2026_teams.json`` holds the confirmed draw + priors, so the
engine has no hardcoded team list. ``attack``/``defence`` default to a neutral 0.0 (log-space)
when only an ``elo`` is supplied; ``calibrate.py`` (Phase 1) refines them against sharp 1X2.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "wc2026_teams.json"

GROUP_SIZE = 4
N_GROUPS = 12
N_TEAMS = GROUP_SIZE * N_GROUPS  # 48


@dataclass(frozen=True)
class SoccerTeam:
    """One World Cup team: stable id, display name, group letter, and strength prior.

    ``attack``/``defence`` are LOG-space strengths (the Dixon-Coles model exponentiates
    differences); 0.0 is league-average. ``elo`` is the independent rating the priors derive
    from (World Football Elo / xG-based) and the calibration warm-start.
    """

    id: int
    name: str
    group: str
    elo: float
    attack: float = 0.0
    defence: float = 0.0


def load_teams(path: str | Path | None = None) -> tuple[list[SoccerTeam], dict]:
    """Load the WC fixture file -> (teams, meta). Validates ids are unique and groups well-formed.

    The file shape is ``{"meta": {...}, "teams": [{"id","name","group","elo",
    "attack"?,"defence"?}, ...]}``. Raises ValueError on duplicate ids or empty team names so a
    malformed fixture fails loudly rather than silently mis-resolving a market downstream.
    """
    p = Path(path) if path is not None else _DEFAULT_PATH
    raw = json.loads(Path(p).read_text(encoding="utf-8"))
    entries = raw.get("teams") if isinstance(raw, dict) else raw
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"fixture {p} has no teams")
    teams: list[SoccerTeam] = []
    seen: set[int] = set()
    for e in entries:
        tid = int(e["id"])
        name = str(e["name"]).strip()
        if not name:
            raise ValueError(f"team id {tid} has an empty name")
        if tid in seen:
            raise ValueError(f"duplicate team id {tid}")
        seen.add(tid)
        teams.append(
            SoccerTeam(
                id=tid,
                name=name,
                group=str(e.get("group", "")).strip().upper(),
                elo=float(e.get("elo", 1500.0)),
                attack=float(e.get("attack", 0.0)),
                defence=float(e.get("defence", 0.0)),
            )
        )
    meta = raw.get("meta", {}) if isinstance(raw, dict) else {}
    return teams, meta


def groups(teams: list[SoccerTeam]) -> dict[str, list[SoccerTeam]]:
    """Bucket teams by their drawn group letter, preserving load order within each group."""
    out: dict[str, list[SoccerTeam]] = {}
    for t in teams:
        out.setdefault(t.group, []).append(t)
    return out


# The 2026 World Cup is co-hosted by Mexico, the USA, and Canada (they play group matches at home).
HOST_NAMES = ("Mexico", "USA", "Canada")


def host_ids(teams: list[SoccerTeam], host_names=HOST_NAMES) -> frozenset[int]:
    """Resolve the host nations to a frozenset of team ids (for the tournament ``hosts`` arg)."""
    wanted = {n.lower() for n in host_names}
    return frozenset(t.id for t in teams if t.name.lower() in wanted)
