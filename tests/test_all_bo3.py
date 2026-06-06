"""BO-01 — the v3 milestone's single engine edit: a keyword-only ``all_bo3`` flag.

This suite proves the behavior of threading ``all_bo3: bool = False`` through the FROZEN
Monte Carlo engine — ``run_mc`` / ``run_mc_progressive`` (engine.montecarlo) ->
``simulate_stage`` -> ``_play`` (engine.swiss) — whose ONLY behavioral effect is at the
``_play`` call site: ``bo3=_is_bo3(a, b)`` becomes ``bo3=all_bo3 or _is_bo3(a, b)``. With
``all_bo3=True`` Stage 3 runs as an all-Bo3 stage on the rating-fallback branch.

Two correctness facts this file pins:

  * series-applied-ONCE: a rating-input match under ``all_bo3=True`` resolves through
    ``series(p_map(ra, rb, S), bo3=True) == p_map**2 * (3 - 2*p_map)`` exactly once — never
    p_map, never the square-of-the-square.

  * no-double-Bo3 (STRUCTURAL): ``engine.probs.series_prob`` returns ``market_series_prob``
    DIRECTLY when present and NEVER re-applies bo3 (PROB-02), so a market-priced match is
    never re-Bo3'd regardless of ``all_bo3``. This file PROVES that property under
    ``all_bo3=True``; it does NOT edit probs.py. The market-passthrough assertion below is
    GREEN against the unchanged probs.py with no engine edit at all.

The freeze (``all_bo3=False`` is byte-identical) is covered by GATE-01
(tests/test_backtest_budapest_2025.py) plus ``test_all_bo3_false_is_byte_identical`` here.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

import engine.montecarlo
import engine.swiss
from engine.probs import p_map, series, series_prob
from engine.swiss import _play
from engine.teams import load_teams


class _StubRng:
    """Minimal numpy-Generator stand-in exposing only ``.random()`` (the sole draw _play makes).

    ``_play`` resolves a non-locked match with a single ``rng.random() < p_a`` Bernoulli draw.
    Returning a FIXED value lets us drive the draw to either side of the resolved series prob
    and assert the winner flips exactly at that threshold.
    """

    def __init__(self, value: float):
        self._value = value

    def random(self) -> float:
        return self._value


def _fake_team(team_id: int, *, seed: int, wins: int = 0, losses: int = 0, rating: float = 0.0):
    """Duck-typed team for the _play unit assertions (id/seed/wins/losses/opps/rating).

    Mirrors engine.teams.Team's attribute surface that _play reads. A ``rating`` attr IS
    present because ``_play`` evaluates ``ratings.get(a.id, a.rating)`` — Python evaluates the
    ``.get`` default (``a.rating``) eagerly even when the id key is present, so the object must
    expose it. The explicit ``ratings`` dict passed in the tests still overrides this value;
    ``rating`` here is only the never-selected fallback. ``opps`` is a set (identity-hashable).
    """

    class _FT:
        __slots__ = ("id", "seed", "wins", "losses", "opps", "rating")

        def __init__(self):
            self.id = team_id
            self.seed = seed
            self.wins = wins
            self.losses = losses
            self.opps = set()
            self.rating = rating

    return _FT()


def test_all_bo3_applies_series_once():
    """A rating-input, NON-terminal match under all_bo3=True resolves at series(p_map, bo3=True).

    Two teams at (wins=0, losses=0) so ``_is_bo3`` is False — the Bo3 promotion comes ONLY
    from all_bo3. With ratings {1: 80.0, 9: 40.0} and S=40 the resolved P(a beats b) MUST be
    the Bo3 closed form applied EXACTLY ONCE: ``series(p_map(80, 40, 40), True)`` ==
    p_map**2 * (3 - 2*p_map). We drive the stub rng to either side of that threshold and
    assert the (winner, loser) flips precisely there (not at p_map, not at the double square).
    """
    a = _fake_team(1, seed=1, wins=0, losses=0)
    b = _fake_team(9, seed=9, wins=0, losses=0)
    ratings = {1: 80.0, 9: 40.0}

    # Sanity: these teams are NOT one step from termination, so any Bo3 is from all_bo3 alone.
    assert engine.swiss._is_bo3(a, b) is False

    pm = p_map(80.0, 40.0, 40.0)
    expected_p_a = series(pm, True)  # Bo3 closed form applied ONCE
    # Guard the test's own premise: Bo3-once differs from p_map and from the double square,
    # so a draw landing between them discriminates the three candidate formulas.
    assert expected_p_a != pytest.approx(pm)
    assert expected_p_a != pytest.approx(series(expected_p_a, True))

    # Draw strictly BELOW the Bo3-once threshold -> a (the favorite) wins.
    below = _StubRng(expected_p_a - 1e-6)
    winner, loser = _play(a, b, ratings, 40.0, below, {}, all_bo3=True)
    assert (winner.id, loser.id) == (1, 9)

    # Draw strictly ABOVE the Bo3-once threshold -> a loses, b wins.
    above = _StubRng(expected_p_a + 1e-6)
    winner, loser = _play(a, b, ratings, 40.0, above, {}, all_bo3=True)
    assert (winner.id, loser.id) == (9, 1)

    # And confirm the boundary is NOT p_map (Bo1) — a draw between p_map and the Bo3 value
    # (here p_map > the Bo3 value for a favorite? no: for p>0.5, series(p)>p, so Bo3 value is
    # ABOVE p_map). Pick a draw between p_map and expected_p_a: it must still let a win under
    # all_bo3 (threshold is the larger Bo3 value), proving the resolved prob is the Bo3 form.
    between = _StubRng((pm + expected_p_a) / 2.0)
    winner, loser = _play(a, b, ratings, 40.0, between, {}, all_bo3=True)
    assert (winner.id, loser.id) == (1, 9), (
        "draw between p_map and the Bo3 value must still favor a -> the resolved prob is the "
        "Bo3 closed form (the larger threshold), not the raw p_map"
    )


def test_market_override_not_re_bo3d_under_all_bo3():
    """A market-priced match returns the RAW market series number even with all_bo3=True.

    The no-double-Bo3 property is STRUCTURAL in series_prob (PROB-02): it returns
    ``market_series_prob`` directly and never re-applies bo3. We prove it two ways.

    (1) Direct: ``series_prob(..., bo3=True, market_series_prob=0.63) == 0.63`` exactly —
        this exercises the UNCHANGED probs.py and is GREEN with no engine edit.

    (2) End-to-end through _play with all_bo3=True: the id-bucket override "1-9" -> 0.63 is
        oriented to the FIRST arg via ``market_p_a = p if a.id < b.id else (1 - p)``. With
        a.id=1 < b.id=9, market_p_a == 0.63, so the draw is taken at 0.63 — NOT at
        0.63**2*(3 - 2*0.63). A stub rng of 0.0 (< 0.63) makes the lower-id team (id 1) win.
    """
    # (1) Structural pass-through — independent of all_bo3, against unchanged probs.py.
    assert series_prob(ra=80.0, rb=40.0, bo3=True, market_series_prob=0.63, S=40.0) == 0.63

    # (2) End-to-end: the override drives the draw at 0.63, not at the Bo3 of 0.63.
    a = _fake_team(1, seed=1, wins=0, losses=0)
    b = _fake_team(9, seed=9, wins=0, losses=0)
    ratings = {1: 80.0, 9: 40.0}  # present so the rating lookup never touches a missing .rating
    bo3_of_063 = series(0.63, True)  # the WRONG value if the market were re-Bo3'd

    # series(0.63, True) = 0.63^2 * (3 - 2*0.63) = 0.3969 * 1.74 = 0.690606 -> strictly ABOVE
    # 0.63. So a draw landing BETWEEN 0.63 and bo3_of_063 discriminates the two thresholds:
    # it is ABOVE the raw market 0.63 (so a loses) but BELOW the re-Bo3'd 0.69 (so a would win
    # if the market were wrongly squared). The market number is used directly -> a must LOSE.
    assert bo3_of_063 > 0.63  # the re-Bo3'd value is strictly above the raw market number
    lo, hi = sorted((0.63, bo3_of_063))
    mid = (lo + hi) / 2.0
    between = _StubRng(mid)
    winner, loser = _play(
        a, b, ratings, 40.0, between, {}, market_overrides={"1-9": 0.63}, all_bo3=True
    )
    # If the resolved prob were the Bo3 of 0.63 (~0.69) the draw at ~0.66 would be below it and
    # a would win; if it is the raw 0.63 the draw at ~0.66 is ABOVE it and a LOSES. The market
    # number is used directly, so a must LOSE here.
    assert (winner.id, loser.id) == (9, 1), (
        "the market override must drive the draw at the raw 0.63, NOT at series(0.63, True) — "
        "series_prob returns the market number directly (no double-Bo3)"
    )


def test_all_bo3_is_keyword_only():
    """``all_bo3`` is KEYWORD_ONLY with default False on all four threaded functions.

    Introspect signatures: _play, simulate_stage, run_mc, run_mc_progressive each expose
    ``all_bo3`` as inspect.Parameter.KEYWORD_ONLY with ``.default is False``. Passing it
    positionally to _play must raise TypeError — locking the keyword-only contract so a
    future caller cannot silently flip the stage to Bo3 via arg order.
    """
    targets = [
        engine.swiss._play,
        engine.swiss.simulate_stage,
        engine.montecarlo.run_mc,
        engine.montecarlo.run_mc_progressive,
    ]
    for fn in targets:
        params = inspect.signature(fn).parameters
        assert "all_bo3" in params, f"{fn.__qualname__} is missing the all_bo3 parameter"
        p = params["all_bo3"]
        assert p.kind == inspect.Parameter.KEYWORD_ONLY, (
            f"{fn.__qualname__}.all_bo3 must be KEYWORD_ONLY, got {p.kind}"
        )
        assert p.default is False, f"{fn.__qualname__}.all_bo3 default must be False"

    # Passing all_bo3 positionally must fail: _play(a, b, ratings, S, rng, locked) takes six
    # positional params; a seventh positional arg has nowhere to bind (the rest are kw-only).
    a = _fake_team(1, seed=1)
    b = _fake_team(9, seed=9)
    with pytest.raises(TypeError):
        _play(a, b, {1: 80.0, 9: 40.0}, 40.0, _StubRng(0.0), {}, True)  # all_bo3 positional


def test_all_bo3_false_is_byte_identical():
    """FREEZE (T-08-02): all_bo3=False is the SAME code path as omitting the flag.

    Run a small deterministic MC twice on the Stage-1 fixture — once with no all_bo3 argument
    at all, once with all_bo3=False explicitly — and assert IDENTICAL counts_30 /
    counts_advance / counts_03 / n. This is the in-suite companion to GATE-01 (the Budapest
    backtest); it does not replace GATE-01 but proves the explicit default does not perturb
    the frozen rating-only path.
    """
    teams = load_teams()
    base = engine.montecarlo.run_mc(teams, None, 40.0, N=2000, locked={}, seed=2024)
    explicit_false = engine.montecarlo.run_mc(
        teams, None, 40.0, N=2000, locked={}, seed=2024, all_bo3=False
    )

    assert explicit_false.n == base.n
    assert explicit_false.counts_30 == base.counts_30
    assert explicit_false.counts_advance == base.counts_advance
    assert explicit_false.counts_03 == base.counts_03
