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

import pytest  # noqa: F401  (kept for test_ci_bar_html_is_xss_safe_numeric_only)


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


def test_delta_tag_html_signs_and_palette():
    """delta_tag_html (RESIM-02 / ISSUE-1): signed pp change, blue up / amber down / grey flat.

    The +/- SIGN is the colorblind-safe signal (UI-06); hue only reinforces. ASCII only.
    """
    from ui.render import delta_tag_html

    up = delta_tag_html(0.999, 0.85)  # +14.9pp
    assert "+14.9pp" in up and "#3B82F6" in up  # increase -> blue, leading '+'
    down = delta_tag_html(0.40, 0.55)  # -15.0pp
    assert "-15.0pp" in down and "#F59E0B" in down  # decrease -> amber, leading '-'
    flat = delta_tag_html(0.500, 0.500)
    assert "+0.0pp" in flat and "#3B82F6" not in flat and "#F59E0B" not in flat  # muted
    # ASCII only — no Unicode arrows (cp1252 lesson).
    for tag in (up, down, flat):
        assert tag.isascii()


def test_delta_tag_html_is_xss_safe_numeric_only():
    """delta_tag_html must reject free-text args (T-02-XSS) — numbers only reach the markup."""
    from ui.render import delta_tag_html

    with pytest.raises(TypeError):
        delta_tag_html("<script>", 0.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        delta_tag_html(0.5, "<script>")  # type: ignore[arg-type]


def test_status_palette_never_red_green():
    """Every STATUS hue is colorblind-safe blue/amber — NEVER a red/green family (UI-06).

    The locked palette is exactly {#3B82F6 blue, #F59E0B amber}. A red or green hue would
    silently break the colorblind-safe contract (~8% of men) that the glyph/label backstop.
    """
    from ui.render import STATUS

    allowed = {"#3B82F6", "#F59E0B"}
    for state, (glyph, label, hue) in STATUS.items():
        assert hue in allowed, f"STATUS[{state!r}] hue {hue} is not blue/amber"
    # And the three locked states exist.
    assert {"advanced", "live", "eliminated"} <= set(STATUS)


def test_status_glyphs_are_ascii_only():
    """Glyphs are ASCII (`/`, `o`, `x`) — never Unicode bullets/checks (Phase 1 cp1252)."""
    from ui.render import STATUS

    for state, (glyph, label, hue) in STATUS.items():
        assert glyph.isascii(), f"STATUS[{state!r}] glyph {glyph!r} is not ASCII"
        assert label.isascii(), f"STATUS[{state!r}] label {label!r} is not ASCII"


def test_status_badge_html_pairs_glyph_and_label():
    """status_badge_html(state) renders BOTH the ASCII glyph AND the text label + hue.

    Colour is reinforcement, never the only signal (UI-06): glyph + label must both appear.
    """
    from ui.render import STATUS, status_badge_html

    html = status_badge_html("advanced")
    assert isinstance(html, str)
    # Assert the glyph appears in the SPAN's TEXT CONTENT (">glyph label<"), not anywhere in
    # the HTML: a bare `"/" in html` is vacuously true because the `</span>` close tag also
    # contains "/" (WR-04) — it would pass even if the glyph were changed to "X".
    glyph_a, label_a, _ = STATUS["advanced"]
    assert f">{glyph_a} {label_a}<" in html   # matches ">/ secured<" in the span text
    assert "#3B82F6" in html                   # blue hue, never red/green

    elim = status_badge_html("eliminated")
    glyph_e, label_e, _ = STATUS["eliminated"]
    assert f">{glyph_e} {label_e}<" in elim    # ">x dead<"
    assert "#F59E0B" in elim                   # amber

    live = status_badge_html("live")
    glyph_l, label_l, _ = STATUS["live"]
    assert f">{glyph_l} {label_l}<" in live    # ">o live<"
    assert "#3B82F6" in live


def test_status_badge_html_rejects_unknown_state():
    """An unknown state raises (no free-text reaches the unsafe_allow_html markup)."""
    from ui.render import status_badge_html

    with pytest.raises((KeyError, ValueError)):
        status_badge_html("<script>alert(1)</script>")  # type: ignore[arg-type]


def test_hero_number_html_is_monospace_accent():
    """hero_number_html(pct) renders a display-size monospace number in the accent colour.

    The one hero number per UI-SPEC Typography — accent #7C5CFC, 28px, monospace; never a
    status hue (blue/amber) and never red/green. Numeric input only (T-02-XSS).
    """
    from ui.render import hero_number_html

    html = hero_number_html(0.58)
    assert isinstance(html, str)
    assert "58.0%" in html
    assert "#7C5CFC" in html           # accent, reserved for the hero number
    assert "28px" in html              # display size
    assert "monospace" in html
    # Numeric only — a free-text payload must raise, not embed.
    with pytest.raises(TypeError):
        hero_number_html("<script>")  # type: ignore[arg-type]


# --- Plan 03: ballot panel render helpers (OPT-03 / OPT-05) ------------------------------


def test_ballot_columns_lists_names_and_marks_diff():
    """ballot_columns renders both ballots' 2/6/2 picks by name and marks the differing
    picks with the ASCII DIFF_MARK (OPT-03) — colour is never the only signal (UI-06)."""
    from engine.optimizer import Ballot
    from ui.render import DIFF_MARK, ballot_columns

    name_of = {i: f"T{i}" for i in range(1, 17)}
    a = Ballot((1, 2), (3, 4, 5, 6, 7, 8), (9, 10))
    b = Ballot((1, 2), (3, 4, 5, 6, 7, 11), (9, 10))  # differs only on 8 (A) vs 11 (B)
    html = ballot_columns(name_of, a, b, diff_ids=(8, 11))

    assert isinstance(html, str)
    assert "E[correct] greedy" in html  # Ballot A title (greedy, not claimed globally optimal)
    assert "Max P(>=5)" in html      # Ballot B title
    for i in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11):
        assert f"T{i}" in html
    # Differing picks carry the diff mark; an agreed pick does not.
    assert f"T8 {DIFF_MARK}" in html
    assert f"T11 {DIFF_MARK}" in html
    assert f"T1 {DIFF_MARK}" not in html


def test_ballot_columns_escapes_team_names():
    """Team names ARE interpolated into the ballot HTML, so they are HTML-escaped — a
    free-text payload can never reach the unsafe_allow_html markup (T-03-XSS)."""
    from engine.optimizer import Ballot
    from ui.render import ballot_columns

    name_of = {i: f"T{i}" for i in range(1, 17)}
    name_of[1] = "<script>alert(1)</script>"
    a = Ballot((1, 2), (3, 4, 5, 6, 7, 8), (9, 10))
    html = ballot_columns(name_of, a, a, diff_ids=())
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_correlated_pick_warning_text_format():
    """The correlated-pick warning copy names both teams, mentions Round 1, and leads with
    the ASCII '!' glyph — it relies on st.warning's amber + text, never red/green (OPT-05)."""
    from ui.render import correlated_pick_warning_text

    txt = correlated_pick_warning_text("GamerLegion", "NRG")
    assert "GamerLegion" in txt and "NRG" in txt
    assert "Round 1" in txt
    assert txt.startswith("!")


# --- Phase 5 display: two-tone CI bar + drill-down helpers (D2/D3) ------------------------


def test_ci_bar_two_tone_collapses_when_outer_equals_inner():
    """D2 GATE guard: when the epistemic (outer) band equals the sampling (inner) band — the
    rating-only case — the two-tone bar draws both segments at the same place (reads single-tone)
    and still carries the formatted percentage. Two positioned segments (faint outer + solid inner).
    """
    from ui.render import ci_bar_two_tone_html

    html = ci_bar_two_tone_html(0.62, 0.58, 0.66, 0.58, 0.66)
    assert "62.0%" in html
    assert "opacity:0.35" in html                      # the faint outer (epistemic) segment
    assert html.count("position:absolute") == 2        # outer + inner segments


def test_ci_bar_two_tone_is_xss_safe_numeric_only():
    """ci_bar_two_tone_html rejects free-text band values and non-hex hues (T-02-XSS), like ci_bar_html."""
    from ui.render import ci_bar_two_tone_html

    with pytest.raises(TypeError):
        ci_bar_two_tone_html("<script>", 0.0, 1.0, 0.0, 1.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ci_bar_two_tone_html(0.5, 0.4, 0.6, 0.4, 0.6, hue="blue;}<script>")


def test_source_spread_disagreement_width():
    """source_spread = max(p) - min(p) across a match's per-book prices; <2 prices or malformed -> 0."""
    from ui.render import source_spread

    assert source_spread(
        [{"book": "a", "p": 0.60}, {"book": "b", "p": 0.72}, {"book": "c", "p": 0.55}]
    ) == pytest.approx(0.17)
    assert source_spread([{"book": "a", "p": 0.6}]) == 0.0
    assert source_spread([]) == 0.0
    assert source_spread(None) == 0.0
    # Malformed entries are skipped; the remaining valid prices still compute.
    assert source_spread([{"book": "a"}, {"p": 0.5}, {"p": 0.7}]) == pytest.approx(0.2)


# --- Phase 5 display: live-odds status panel helpers (D1) --------------------------------


def test_fmt_age_boundaries():
    """fmt_age renders relative age across the just-now / minute / hour / day boundaries.

    ``now`` is passed in (no Date.now in tests). A bad/missing timestamp renders 'unknown',
    a future timestamp clamps to 'just now' — the header strip never raises on a weird value.
    """
    from datetime import datetime, timedelta, timezone

    from ui.render import fmt_age

    now = datetime(2026, 5, 31, 12, 0, 0, tzinfo=timezone.utc)

    def ago(**kw):
        return (now - timedelta(**kw)).isoformat()

    assert fmt_age(ago(seconds=10), now) == "just now"
    assert fmt_age(ago(minutes=4), now) == "4m ago"
    assert fmt_age(ago(hours=6), now) == "6h ago"
    assert fmt_age(ago(days=2), now) == "2d ago"
    # 59m -> still minutes; 23h -> still hours (boundary just below the next unit).
    assert fmt_age(ago(minutes=59), now) == "59m ago"
    assert fmt_age(ago(hours=23), now) == "23h ago"
    # Bad / missing / future.
    assert fmt_age("not-a-timestamp", now) == "unknown"
    assert fmt_age(None, now) == "unknown"
    assert fmt_age((now + timedelta(minutes=5)).isoformat(), now) == "just now"


def test_is_stale_boundary():
    """is_stale flips True past the 2h threshold; a bad/missing timestamp fails toward stale."""
    from datetime import datetime, timedelta, timezone

    from ui.render import is_stale

    now = datetime(2026, 5, 31, 12, 0, 0, tzinfo=timezone.utc)
    fresh = (now - timedelta(minutes=30)).isoformat()
    old = (now - timedelta(hours=3)).isoformat()

    assert is_stale(fresh, now) is False
    assert is_stale(old, now) is True
    # Custom threshold honoured.
    assert is_stale((now - timedelta(seconds=90)).isoformat(), now, threshold_s=60) is True
    # Fail toward stale on unparseable / missing.
    assert is_stale("garbage", now) is True
    assert is_stale(None, now) is True


def test_provider_labels_allowlist_dedupe_order():
    """provider_labels maps raw names to book labels via the allowlist, drops unknowns, dedupes.

    Unknown names are NEVER interpolated (the status line is rendered via unsafe_allow_html), and
    order is preserved so the display reads stably. None / non-list -> [].
    """
    from ui.render import provider_labels

    assert provider_labels(["oddspapi", "polymarket", "kalshi"]) == [
        "Pinnacle",
        "Polymarket",
        "Kalshi",
    ]
    # Case-insensitive, unknown dropped, dedup preserves first-seen order.
    assert provider_labels(["KALSHI", "mystery_book", "kalshi"]) == ["Kalshi"]
    assert provider_labels([]) == []
    assert provider_labels(None) == []


def test_priced_ids_union_and_failsoft():
    """priced_ids unions team ids across 'lo-hi' keys; empty/malformed yields an empty set."""
    from ui.render import priced_ids

    assert priced_ids({"1-9": {}, "3-11": {}}) == {1, 9, 3, 11}
    assert priced_ids({}) == set()
    assert priced_ids(None) == set()
    # A malformed key is skipped, the valid ones still resolve.
    assert priced_ids({"bad-key-x": {}, "2-7": {}}) == {2, 7}


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
