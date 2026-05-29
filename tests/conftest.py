"""Shared fixtures for the whole suite.

Provides the 16-team Cologne seed->team map and a minimal record-group builder
usable by the swiss / MC tests. The team fixture is imported from engine.teams
(the single source of truth); a lightweight local Team is also offered for the
math-guard tests so test_probs.py does not depend on the full fixture loading.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest


@dataclass(eq=False)
class FakeTeam:
    """Minimal duck-typed team for unit tests that only need wins/losses/opps.

    engine.swiss.difficulty() and the pairing fold operate on any object exposing
    .id, .seed, .wins, .losses, .opps — this stand-in keeps the math-guard tests
    independent of the full engine.teams fixture.

    ``opps`` is a ``set`` (matching the real ``engine.teams.Team.opps``) so that
    ``engine.swiss._record_match``'s ``a.opps.add(b)`` works on a FakeTeam too; the
    ``eq=False`` gives identity-based hashing so instances can live in that set
    (the default dataclass ``__eq__`` would make them unhashable).
    """

    id: int
    seed: int = 0
    wins: int = 0
    losses: int = 0
    opps: set = field(default_factory=set)


@pytest.fixture
def make_team():
    """Factory fixture returning FakeTeam instances."""

    def _make(id: int, *, seed: int = 0, wins: int = 0, losses: int = 0, opps=None):
        return FakeTeam(id=id, seed=seed, wins=wins, losses=losses, opps=set(opps or []))

    return _make


@pytest.fixture
def teams():
    """The 16-team Cologne seed->team map from the single source of truth.

    Imported lazily so collection still succeeds before engine.teams exists in
    early waves; the swiss/MC tests that use this are xfail until their wave.
    """
    from engine.teams import load_teams

    return load_teams()


@pytest.fixture
def seeds(teams):
    """seed -> team map derived from the loaded fixture."""
    return {t.seed: t for t in teams}
