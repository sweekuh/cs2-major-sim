"""Pure-function UI helper tests — Phase 2 Wave 0 (ui/cache.py, ui/state.py, ui/render.py).

These are AppTest-FREE unit tests for the two genuinely-new pieces of Phase 2 code plus
the rating-validation gate (RESEARCH "Key insight"): the freeze_locked / freeze_ratings
cache-key translation (UI-02 / Phase 2x4 seam, Pattern 1), validate_ratings (UI-05 bad
cell, Pitfall 5), and ci_bar_html (UI-04, the inline CI bar, XSS-safe T-02-XSS).

Wave 0 RED convention (matches Phase 1 — see test_probs.py xfail header): the ui/ package
does not exist yet, so each test imports lazily inside the body and is marked xfail until
Task 2 builds the helpers and removes the marker. The suite COLLECTS without being falsely
green. Tasks 2 flips these GREEN.
"""

from __future__ import annotations

import pytest

# Wave 0: ui/ not built yet. Remove this marker in Task 2 when the helpers land.
pytestmark = pytest.mark.xfail(
    strict=False, reason="Wave 0 RED — ui/ helpers not built until Task 2"
)


def test_freeze_locked_roundtrip():
    """freeze_locked output reconstructs to the original locked dict (Pattern 1)."""
    from ui.cache import freeze_locked

    original = {frozenset({9, 1}): 1, frozenset({3, 11}): 3}
    key = freeze_locked(original)
    # key must be hashable (this is the whole point — it goes into the cache key).
    hash(key)
    reconstructed = {frozenset(pair): winner for pair, winner in key}
    assert reconstructed == original


def test_freeze_locked_order_independent():
    """{frozenset({9,1}):1} and {frozenset({1,9}):1} produce the SAME key."""
    from ui.cache import freeze_locked

    assert freeze_locked({frozenset({9, 1}): 1}) == freeze_locked(
        {frozenset({1, 9}): 1}
    )
    # And pair-ordering in the dict must not matter either.
    a = freeze_locked({frozenset({9, 1}): 1, frozenset({3, 11}): 3})
    b = freeze_locked({frozenset({11, 3}): 3, frozenset({1, 9}): 1})
    assert a == b


def test_freeze_ratings_order_independent():
    """freeze_ratings({2:78,1:92}) == freeze_ratings({1:92,2:78}) — sorted, hashable."""
    from ui.cache import freeze_ratings

    a = freeze_ratings({2: 78, 1: 92})
    b = freeze_ratings({1: 92, 2: 78})
    assert a == b
    hash(a)
    assert dict(a) == {1: 92, 2: 78}


def test_validate_ratings_rejects_empty_and_out_of_range():
    """validate_ratings returns offending seeds for empty/None + out-of-range (UI-05).

    Mirrors engine.teams._validate_fixture bound 0 < r < 1000. Valid rows -> empty list.
    """
    from ui.state import validate_ratings

    good = [{"seed": 1, "team": "GamerLegion", "rating": 92}]
    assert validate_ratings(good) == []

    rows = [
        {"seed": 1, "team": "A", "rating": 92},      # ok
        {"seed": 2, "team": "B", "rating": None},     # empty/None -> bad
        {"seed": 3, "team": "C", "rating": 0},        # 0 not in (0, 1000) -> bad
        {"seed": 4, "team": "D", "rating": 1000},     # 1000 not in (0, 1000) -> bad
        {"seed": 5, "team": "E", "rating": 50},       # ok
    ]
    offenders = validate_ratings(rows)
    assert set(offenders) == {2, 3, 4}


def test_ci_bar_html_contains_bar_div():
    """ci_bar_html(p, lo, hi) -> a string with a track div + a positioned fill div.

    Numbers are formatted; NO non-numeric/free-text argument is interpolated (T-02-XSS).
    """
    from ui.render import ci_bar_html

    html = ci_bar_html(0.82, 0.80, 0.84)
    assert isinstance(html, str)
    assert "div" in html
    # the formatted percentage appears
    assert "82.0%" in html
    # a positioned fill div (absolute) over a track exists
    assert "position:absolute" in html
    assert "%" in html  # widths/lefts are percentages


def test_ci_bar_html_is_xss_safe_numeric_only():
    """ci_bar_html must never accept/interpolate a free-text team name (T-02-XSS).

    Passing a non-numeric value where a float is expected must raise, not silently embed
    a <script> payload into the unsafe_allow_html string.
    """
    from ui.render import ci_bar_html

    with pytest.raises((TypeError, ValueError)):
        ci_bar_html("<script>alert(1)</script>", 0.0, 1.0)  # type: ignore[arg-type]


def test_run_mc_cached_uses_frozen_seed_and_default_chunks():
    """run_mc_cached reconstructs dicts from frozen keys and calls the frozen run_mc
    with seed=FIXED_SEED and the default n_chunks=20, returning a Result (UI-02 seam)."""
    from engine.montecarlo import Result, run_mc
    from ui.cache import freeze_locked, freeze_ratings, run_mc_cached
    from ui.state import FIXED_SEED

    ratings = {i: 50.0 for i in range(1, 17)}
    ratings[1] = 92.0
    rk = freeze_ratings(ratings)
    lk = freeze_locked({})
    # Call through the cached wrapper (cache_data wraps but still computes on first call).
    result = run_mc_cached(rk, 40.0, 2000, lk)
    assert isinstance(result, Result)
    assert result.n == 2000

    # The cached wrapper must reproduce a direct frozen run_mc with FIXED_SEED, n_chunks=20.
    from engine.teams import load_teams

    direct = run_mc(load_teams(), ratings, 40.0, 2000, locked={}, seed=FIXED_SEED)
    assert result.counts_advance == direct.counts_advance
