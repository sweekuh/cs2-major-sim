"""resolve_id guards (M2): exact match wins; single substring resolves; ambiguity -> None.

Substring mis-resolution would price a Kalshi market against the WRONG team, so ambiguous names
must drop the quote rather than guess.
"""

from __future__ import annotations

from odds._match import resolve_id


def _n2i(*names):
    return {("".join(n.lower().split())): i for i, n in enumerate(names, start=1)}


def test_exact_match_wins_over_substring():
    n2i = _n2i("Korea", "Korea Republic")
    assert resolve_id("Korea Republic", n2i) == n2i["korearepublic"]
    assert resolve_id("Korea", n2i) == n2i["korea"]


def test_single_substring_resolves():
    n2i = _n2i("Team Liquid", "Vitality")
    assert resolve_id("Liquid", n2i) == n2i["teamliquid"]  # unambiguous substring


def test_ambiguous_substring_returns_none():
    n2i = _n2i("Equatorial Guinea", "Guinea-Bissau")
    assert resolve_id("Guinea", n2i) is None  # two candidates contain "guinea" -> drop


def test_no_match_returns_none():
    assert resolve_id("Atlantis", _n2i("Brazil", "Morocco")) is None
    assert resolve_id("", _n2i("Brazil")) is None
