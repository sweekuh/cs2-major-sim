"""One spelling per Stage 1 team, matching data/singapore2026/stage1.json.

PGL, Polymarket and Kalshi each spell teams differently. Unknown names fail loudly in the
pricer so a renamed team can never be matched to the wrong market.
"""

from __future__ import annotations

ALIASES = {
    "nip": "NIP",
    "ninjas in pyjamas": "NIP",
    "pvision": "PVISION",
    "parivision": "PVISION",
    "pvision (parivision)": "PVISION",
    "heroic": "HEROIC",
    "faze": "FaZe",
    "faze clan": "FaZe",
    "liquid": "Liquid",
    "team liquid": "Liquid",
    "eternal fire": "Eternal Fire",
    "eternal fire esports": "Eternal Fire",
    "100 thieves": "100 Thieves",
    "9z": "9z",
    "9z globant": "9z",
    "9z team": "9z",
    "m80": "M80",
    "dendele": "DENDELE",
    "dendele cs": "DENDELE",
    "imperial": "Imperial",
    "imperial esports": "Imperial",
    "wildcard": "Wildcard",
    "wildcard gaming": "Wildcard",
    "gosh": "GOSH",
    "gosh (bc.game)": "GOSH",
    "bc.game": "GOSH",
    "bc game": "GOSH",
    "flyquest": "FlyQuest",
    "chinggis warriors": "Chinggis Warriors",
    "lynn vision": "Lynn Vision",
    "lynn vision gaming": "Lynn Vision",
}


def canon(raw: str | None, *, strict: bool = True) -> str | None:
    """Return the Stage 1 spelling, or raise (strict) / pass through (lenient) if unknown."""
    if raw is None or not raw.strip():
        return None
    key = raw.strip().casefold()
    if key in ALIASES:
        return ALIASES[key]
    if strict:
        raise KeyError(f"Unknown team name: {raw!r}")
    return raw.strip()
