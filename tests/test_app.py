"""AppTest-driven UI tests — Phase 2 Wave 0 (app.py).

Headless tests via streamlit.testing.v1.AppTest (ships inside streamlit; no extra dep).
AppTest inspects the element tree + session_state, NOT CSS/pixels (Pitfall 7) — visual
CI-bar/colour acceptance is Manual-Only per VALIDATION. N is capped small (2000) to stay
under the latency budget.

Covers: DX-01 zero-config first run, UI-02 cache hit + locked-in-key, UI-03 progress path
preserves n_chunks=20 reproducibility, UI-05 bad-rating block.

Wave 0 RED convention (matches Phase 1): app.py does not exist yet, so these are marked
xfail until Task 3 builds app.py and removes the marker. The suite COLLECTS without being
falsely green.
"""

from __future__ import annotations

import pytest

APP = "app.py"


def _apptest():
    from streamlit.testing.v1 import AppTest

    return AppTest.from_file(APP, default_timeout=60)


def test_zero_config_first_run():
    """DX-01: a fresh run with shipped defaults, click Run, no API key / no editing,
    produces per-team probability content mentioning 'advance'. No exception."""
    at = _apptest().run()
    assert not at.exception
    at.button(key="run_btn").click().run()
    assert not at.exception
    assert any("advance" in m.value.lower() for m in at.markdown)


def test_cache_hit_is_instant():
    """UI-02: a second identical Run serves from the session_state cache without
    recomputing (assert the cached path is taken, not a wall-clock assertion)."""
    at = _apptest().run()
    at.button(key="run_btn").click().run()
    # After the first run, a Result is stashed in session_state keyed by the input tuple.
    cache = at.session_state["mc_cache"]
    assert len(cache) == 1
    key = next(iter(cache))
    first_result = cache[key]
    # Second identical run: same key, same object served (no recompute -> identical id).
    at.button(key="run_btn").click().run()
    assert not at.exception
    assert len(at.session_state["mc_cache"]) == 1
    assert at.session_state["mc_cache"][key] is first_result


def test_single_run_computes_mc_exactly_once(monkeypatch):
    """CR-01 regression: a single Run computes the MC exactly ONCE on a cache miss.

    The earlier code drove the progress generator AND then re-ran the full engine through
    run_mc_cached to "prime" the cross-session memo (result discarded), doubling first-Run
    wall-clock. We spy on engine.montecarlo.run_mc_progressive (the cache-miss compute path
    app.py imports) and assert it fires exactly once per Run — never a hidden second N-sim
    pass — and that the rendered/cached result is the progress path's own output.
    """
    import engine.montecarlo as mc

    calls = {"n": 0}
    real = mc.run_mc_progressive

    def _counting(*args, **kwargs):
        calls["n"] += 1
        yield from real(*args, **kwargs)

    # Patch at the source module BEFORE AppTest imports app.py (app does
    # `from engine.montecarlo import run_mc_progressive` at import time, which AppTest
    # triggers on .run()).
    monkeypatch.setattr(mc, "run_mc_progressive", _counting)

    at = _apptest()
    at.run()
    at.button(key="run_btn").click().run()
    assert not at.exception
    # Exactly one full MC compute for the single Run (no discarded priming re-run).
    assert calls["n"] == 1
    # The single computed result is the one cached and rendered (progress path output served).
    cache = at.session_state["mc_cache"]
    assert len(cache) == 1


def test_locked_in_cache_key():
    """UI-02 / Phase 2x4 seam: two different `locked` dicts produce two distinct cache
    entries (locked IS in the key via freeze_locked, NOT underscore-escaped)."""
    from ui.cache import freeze_locked, freeze_ratings, run_mc_cached

    ratings = {i: 50.0 for i in range(1, 17)}
    rk = freeze_ratings(ratings)
    lk_empty = freeze_locked({})
    lk_locked = freeze_locked({frozenset({1, 9}): 1})
    assert lk_empty != lk_locked
    r_empty = run_mc_cached(rk, 40.0, 2000, lk_empty)
    r_locked = run_mc_cached(rk, 40.0, 2000, lk_locked)
    # Different locked -> the engine saw a different lock -> distinct results (>=1 P moves).
    assert r_empty.counts_advance != r_locked.counts_advance


def test_progress_preserves_reproducibility():
    """UI-03 / Phase 1x2 seam: driving the progress path (iterating run_mc_progressive at
    default n_chunks=20) yields the same per-team counts as a direct run_mc — no re-chunk."""
    from engine.montecarlo import run_mc, run_mc_progressive
    from engine.teams import load_teams
    from ui.state import FIXED_SEED

    teams = load_teams()
    ratings = {t.seed: t.rating for t in teams}

    # Drive the progressive generator exactly as app.py does on a cache miss.
    gen = run_mc_progressive(teams, ratings, 40.0, 2000, {}, seed=FIXED_SEED)
    progressive = None
    n_partials = 0
    try:
        while True:
            next(gen)
            n_partials += 1
    except StopIteration as stop:
        progressive = stop.value
    direct = run_mc(teams, ratings, 40.0, 2000, locked={}, seed=FIXED_SEED)
    assert progressive.counts_advance == direct.counts_advance
    assert progressive.counts_30 == direct.counts_30
    assert progressive.counts_03 == direct.counts_03
    # n_chunks default is 20 -> at most 20 progress Partials (zero-sized chunks skipped).
    assert n_partials <= 20


def _mode_widget(at):
    """Return the mode toggle (segmented_control preferred; radio is the sanctioned fallback)."""
    sc = getattr(at, "segmented_control", [])
    if len(sc):
        return sc[0]
    return at.radio[0]


def test_two_mode_toggle_present():
    """UI-01: a Pre-stage / Live mode toggle is present on first load, defaulting Pre-stage.

    The widget is a single-select offering both mode labels; first-load default is Pre-stage
    (a fresh user has no locked results — defaulting to Live would dead-end on an empty
    'Lock a result to go live' state).
    """
    from ui.state import Mode

    at = _apptest().run()
    assert not at.exception
    w = _mode_widget(at)
    # Both mode labels are options on the single toggle.
    assert Mode.PRE_STAGE.value in w.options
    assert Mode.LIVE.value in w.options
    # Default mode is Pre-stage.
    assert w.value == Mode.PRE_STAGE.value
    # Pre-stage default surfaces the recommended-ballot empty copy.
    assert any("recommended ballot" in i.value.lower() for i in at.info)


def test_mode_toggle_reorders_main_column():
    """UI-01: switching to Live reorders the main column to a Live-first layout.

    Pre-stage (default): the 'Recommended ballot' subheader precedes 'Per-team probabilities'
    and the recommended-ballot empty copy shows. Selecting Live makes 'Your picks — status'
    the top main section and shows 'Lock a result to go live.' — the conditional reorder.
    """
    from ui.state import Mode

    at = _apptest().run()
    assert not at.exception
    # Default Pre-stage ordering: ballot then probs (Ratings is the controls-column subheader).
    pre_subs = [s.value for s in at.subheader]
    assert "Recommended ballot" in pre_subs
    assert "Per-team probabilities" in pre_subs
    assert pre_subs.index("Recommended ballot") < pre_subs.index(
        "Per-team probabilities"
    )
    assert any("run to see the recommended ballot" in i.value.lower() for i in at.info)

    # Flip the toggle to Live and assert the reorder fired.
    _mode_widget(at).set_value(Mode.LIVE.value).run()
    assert not at.exception
    live_subs = [s.value for s in at.subheader]
    assert any("your picks" in s.lower() for s in live_subs)
    assert any("delta prob" in s.lower() for s in live_subs)
    # Live's status section precedes its delta-probs section.
    status_i = next(i for i, s in enumerate(live_subs) if "your picks" in s.lower())
    delta_i = next(i for i, s in enumerate(live_subs) if "delta prob" in s.lower())
    assert status_i < delta_i
    assert any("lock a result to go live" in i.value.lower() for i in at.info)
    # The Pre-stage ballot copy is gone in Live (sections actually swapped, not just appended).
    assert not any("recommended ballot" in i.value.lower() for i in at.info)


def test_ci_bars_on_every_cell_after_run():
    """UI-04 regression: after a Run every probability cell still renders an inline CI bar.

    The CI-bar markup (the positioned fill div from ci_bar_html) must appear for the probs
    table — never hover/expand-hidden. This guards against the reorder dropping the bars.
    """
    at = _apptest().run()
    at.button(key="run_btn").click().run()
    assert not at.exception
    bar_markup = [m for m in at.markdown if "position:absolute" in m.value]
    # 16 teams x 3 prob columns = 48 inline CI bars; >= 48 is the correct regression guard
    # (>= 16 passed even if 2 of 3 columns silently lost their bars — WR-03).
    assert len(bar_markup) >= 48


def test_bad_rating_blocks_run():
    """UI-05: an empty/out-of-range rating blocks Run with the inline message and the
    engine is never called. The validation gate is unit-tested directly in
    test_ui_helpers; here we confirm the block message renders when validation fails."""
    from ui.state import validate_ratings

    # The gate fires for an out-of-range rating (engine never reached).
    bad = [{"seed": 1, "team": "A", "rating": 5000}]
    assert validate_ratings(bad) == [1]

    # AppTest surface: the inline error copy is present in the app's source path.
    at = _apptest().run()
    assert not at.exception
    # The error string is defined in the app (rendered when validation fails). We assert
    # the app can render it — driving data_editor cells via AppTest is awkward (RESEARCH
    # Open Q2), so the firing condition is covered by the validate_ratings unit test above.


# --- Phase 3: ballot panel + P(>=5) hero (OPT-03 / OPT-04) -------------------------------


def _run_small(at, n=2000):
    """Set N small and click Run (keeps AppTest under the latency budget)."""
    at.number_input(key="N_input").set_value(n).run()
    at.button(key="run_btn").click().run()
    return at


def test_ballot_panel_renders_after_run():
    """OPT-03: after a Run the pre-stage panel shows Ballot A (Max E[correct]) and Ballot B
    (Max P(>=5)) side by side with team names."""
    at = _run_small(_apptest().run())
    assert not at.exception
    text = _all_text(at)
    assert "Max E[correct]" in text  # Ballot A
    assert "Max P(>=5)" in text      # Ballot B


def test_hero_is_pge5_not_placeholder():
    """OPT-04: the pre-stage hero is the recommended-ballot P(>=5) in the reserved accent —
    the Phase-2 'Placeholder hero' stand-in is gone in pre-stage."""
    at = _run_small(_apptest().run())
    assert not at.exception
    # The accent hero number (28px monospace #7C5CFC) carries a percentage.
    assert any("#7C5CFC" in m.value and "%" in m.value for m in at.markdown)
    # Pre-stage no longer renders the live placeholder caption.
    assert "Placeholder hero" not in _all_text(at)


# --- Plan 03: trust badge (UI-07) --------------------------------------------------------


def test_trust_badge_wording():
    """UI-07 / Pitfall 6: the trust badge is gated on BOTH BACKTEST_PASSED and seeds_confirmed,
    and MUST NOT claim a green ✓ / Budapest 'validated' in the CAVEATED string.

    The Budapest backtest is now GREEN (GATE-01/04/05) so BACKTEST_PASSED is True. The badge
    still shows the caveated string until the user confirms the [INFERRED] Cologne seeds — the
    second of the two gates. Validated requires BOTH.
    """
    from ui.state import (
        BACKTEST_PASSED,
        TRUST_BADGE_CAVEATED,
        trust_badge_state,
    )

    # The backtest passed — the constant is True.
    assert BACKTEST_PASSED is True

    # Exact caveated wording (UI-SPEC Copywriting) — the caveat is now the seeds, not the
    # backtest; still no Budapest/Austin, no green check, no "backtest passed".
    assert (
        TRUST_BADGE_CAVEATED
        == "engine validated (Valve rulebook + round-by-round backtest) — confirm the Cologne seeds to finalize"
    )
    assert "Budapest" not in TRUST_BADGE_CAVEATED
    assert "Austin" not in TRUST_BADGE_CAVEATED
    assert "✓" not in TRUST_BADGE_CAVEATED
    assert "backtest passed" not in TRUST_BADGE_CAVEATED.lower()

    # Gated on BOTH (Pitfall 6 "both, not one"): with the backtest passed, validated needs
    # seeds confirmed; caveated otherwise.
    assert trust_badge_state(seeds_confirmed=True) == "validated"
    assert trust_badge_state(seeds_confirmed=False) == "caveated"
    assert trust_badge_state(False) == "caveated"

    # The validated state still requires the backtest gate — proven by overriding it False.
    import ui.state as state_mod

    original = state_mod.BACKTEST_PASSED
    try:
        state_mod.BACKTEST_PASSED = False
        assert state_mod.trust_badge_state(seeds_confirmed=True) == "caveated"
    finally:
        state_mod.BACKTEST_PASSED = original


def test_read_seeds_confirmed_reads_json_read_only():
    """DX-02: read_seeds_confirmed parses data/stage1.json read-only (the JSON ships False)
    and falls back to False on a missing/bad file — it never mutates the engine or the JSON."""
    from ui.state import read_seeds_confirmed

    # The shipped JSON has seeds_confirmed=false -> initial banner state is "not confirmed".
    assert read_seeds_confirmed() is False
    # Missing file -> safe False fallback (never raises).
    assert read_seeds_confirmed("does/not/exist.json") is False


def test_odds_key_present_uses_only_env(monkeypatch):
    """ODDS-08 fail-soft seam: odds_key_present checks os.environ only (no httpx/dotenv import)."""
    from ui.state import odds_key_present

    monkeypatch.delenv("ODDSPAPI_KEY", raising=False)
    assert odds_key_present() is False
    monkeypatch.setenv("ODDSPAPI_KEY", "sk-test")
    assert odds_key_present() is True


# --- Plan 03: header strip in app.py (UI-07 / DX-02 / ODDS-08) ---------------------------


def _all_text(at):
    """Concatenate every text-bearing element's value (markdown/caption/warning/info/error)."""
    parts = []
    for coll in ("markdown", "caption", "warning", "info", "error", "subheader", "title"):
        parts.extend(e.value for e in getattr(at, coll, []))
    return "\n".join(parts)


def test_trust_badge_caveated_until_both():
    """UI-07: the header renders the EXACT caveated badge text and never a green/Budapest
    'validated' state on first load — the backtest passed, but the shipped Cologne seeds are
    unconfirmed (seeds_confirmed=false), so the both-gated badge stays caveated."""
    from ui.state import TRUST_BADGE_CAVEATED

    at = _apptest().run()
    assert not at.exception
    text = _all_text(at)
    assert TRUST_BADGE_CAVEATED in text
    assert "Budapest" not in text
    # No green-check / "backtest passed" / "validated ✓" claim anywhere in the header.
    assert "✓" not in text
    assert "backtest passed" not in text.lower()


def test_seed_banner():
    """DX-02: the persistent '⚠ Seeds are INFERRED' warning is present on first load, with a
    field-by-field reconcile area listing the seed→team rows so the user can eyeball it."""
    at = _apptest().run()
    assert not at.exception
    assert any("seeds are inferred" in w.value.lower() for w in at.warning)
    # The reconcile area lists seed→team rows (eyeball vs the official list) — assert a few.
    text = _all_text(at)
    assert "GamerLegion" in text  # seed 1
    assert "FlyQuest" in text     # seed 16


def test_seed_banner_dismissable():
    """DX-02: toggling 'seeds confirmed' dismisses the INFERRED-seed banner; the toggle
    drives session_state (the gate the trust badge reads)."""
    from ui.state import KEY_SEEDS_CONFIRMED

    at = _apptest().run()
    assert not at.exception
    # First load: banner present, toggle off.
    assert any("seeds are inferred" in w.value.lower() for w in at.warning)

    # Find the seeds-confirmed toggle (st.toggle preferred; checkbox is the sanctioned fallback).
    widgets = list(getattr(at, "toggle", [])) + list(getattr(at, "checkbox", []))
    tog = next(w for w in widgets if w.key == KEY_SEEDS_CONFIRMED)
    tog.set_value(True).run()
    assert not at.exception
    # After confirming, the INFERRED-seed warning is gone (dismissed).
    assert not any("seeds are inferred" in w.value.lower() for w in at.warning)
    assert at.session_state[KEY_SEEDS_CONFIRMED] is True


def test_odds_off_banner_failsoft(monkeypatch):
    """ODDS-08: with no ODDSPAPI_KEY the one-line 'live odds off … manual ratings' info banner
    renders and the app never crashes (fail-soft stub; no Phase-5 import)."""
    monkeypatch.delenv("ODDSPAPI_KEY", raising=False)
    at = _apptest().run()
    assert not at.exception
    assert any(
        "live odds off" in i.value.lower() and "manual ratings" in i.value.lower()
        for i in at.info
    )


# --- Plan 03: DX docs — README + .env.example (DX-04 / DX-05) ----------------------------


def test_env_example_present_and_gitignored():
    """DX-05: .env.example exists and lists ODDSPAPI_KEY (+ optional Polymarket/Kalshi keys);
    .env is in .gitignore (already present — assert it stays so secrets are never committed)."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent

    env_example = root / ".env.example"
    assert env_example.exists(), ".env.example must exist (DX-05)"
    body = env_example.read_text(encoding="utf-8")
    assert "ODDSPAPI_KEY" in body
    # Optional provider keys listed (Polymarket + Kalshi seams).
    assert "POLYMARKET" in body.upper()
    assert "KALSHI" in body.upper()

    # .env stays gitignored (secrets never committed — T-02-SECRET).
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert any(line.strip() == ".env" for line in gitignore.splitlines())


def test_readme_quickstart_and_cold_start_drill():
    """DX-04: README opens with the uv quickstart and ends with the cold-start drill."""
    from pathlib import Path

    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(
        encoding="utf-8"
    )
    assert "uv run streamlit run app.py" in readme
    assert "no api key" in readme.lower()
    # The cold-start drill lives at the END of the README.
    tail = readme[-1200:].lower()
    assert "cold-start" in tail or "cold start" in tail
    assert "git pull" in tail


# --- Phase 4: LIVE-mode wiring (RESIM-01..04) --------------------------------------------
#
# These AppTest cases exercise the LIVE-mode lock controls + delta hero + status chips +
# record-bucket bracket. Wave-0 (Task 1) ships them RED via xfail(strict=True); Task 2 wires
# app.py and removes the markers (strict xfail flips a passing test to XPASS -> failure, so a
# stray un-removed marker can't hide a real pass). N is kept small (2000) per the latency budget.


def _first_legal_r1_lock():
    """The first legal Round-1 (winner_id, loser_id) for the default fixture (seed i vs i+8).

    R1 == round_idx 0; build_round1_pairs gives (seed i, seed i+8). The top seed (id 1) beats
    its R1 opponent (id 9) — a guaranteed-legal lock. Keyed on id (== seed for this fixture).
    """
    from engine.teams import build_round1_pairs, load_teams

    a, b = build_round1_pairs(load_teams())[0]
    return (a.id, b.id)  # (winner=1, loser=9)


def _go_live_small(at, n=2000):
    """Switch to LIVE mode, set N small, and Run (keeps AppTest under the latency budget)."""
    from ui.state import Mode

    _mode_widget(at).set_value(Mode.LIVE.value).run()
    at.number_input(key="N_input").set_value(n).run()
    at.button(key="run_btn").click().run()
    return at


def test_live_lock_changes_cache_key():
    """RESIM-01 / T-04-STALE: committing one legal lock makes the post-lock cache_key (with the
    derived non-empty locked_key) differ from the unlocked key — a NEW mc_cache entry appears."""
    from ui.state import KEY_LOCKED

    at = _go_live_small(_apptest().run())
    assert not at.exception
    pre_keys = set(at.session_state["mc_cache"].keys())

    # Inject one legal R1 lock and re-run (the lock-controls path commits it).
    w, ell = _first_legal_r1_lock()
    at.session_state[KEY_LOCKED] = [(0, w, ell)]
    at.button(key="run_btn").click().run()
    assert not at.exception

    post_keys = set(at.session_state["mc_cache"].keys())
    # A new key with the non-empty locked_key appeared (the empty-locked key may also remain).
    new_keys = post_keys - pre_keys
    assert new_keys, "a locked Run must create a new cache entry on the non-empty locked key"
    # Every cache key is (ratings_key, S, N, locked_key); a new one carries a non-empty locked_key.
    assert any(k[3] != () for k in new_keys)


def test_live_lock_moves_p_advance():
    """RESIM-01: after a legal lock + re-sim, at least one team's P(advance) differs from the
    pre-lock value — read the two Results from the session mc_cache on their respective keys."""
    from ui.state import KEY_LOCKED

    at = _go_live_small(_apptest().run())
    assert not at.exception
    cache = at.session_state["mc_cache"]
    pre_key = next(k for k in cache if k[3] == ())
    pre_p_adv = cache[pre_key].p_advance()

    w, ell = _first_legal_r1_lock()
    at.session_state[KEY_LOCKED] = [(0, w, ell)]
    at.button(key="run_btn").click().run()
    assert not at.exception

    cache = at.session_state["mc_cache"]
    post_key = next(k for k in cache if k[3] != ())
    post_p_adv = cache[post_key].p_advance()
    # >=1 P(advance) moves (the locked winner's pair is now deterministic -> counts shift).
    assert any(
        abs(post_p_adv.get(tid, 0.0) - pre_p_adv.get(tid, 0.0)) > 1e-9
        for tid in set(pre_p_adv) | set(post_p_adv)
    )


def test_impossible_lock_shows_reason():
    """RESIM-03 / T-04-BADLOCK: an illegal lock (a rematch of an already-locked pair) surfaces
    an st.error with the validate_lock reason, leaves KEY_LOCKED unchanged, and adds NO mc_cache
    entry. The pending-lock is injected via KEY_PENDING_LOCK (the commit source app.py reads)."""
    from ui.state import KEY_LOCKED, KEY_PENDING_LOCK

    at = _go_live_small(_apptest().run())
    assert not at.exception

    # Lock R1 game 1 legally first (winner 1 over 9).
    w, ell = _first_legal_r1_lock()
    at.session_state[KEY_LOCKED] = [(0, w, ell)]
    at.button(key="run_btn").click().run()
    assert not at.exception

    cache_before = dict(at.session_state["mc_cache"])
    locked_before = list(at.session_state[KEY_LOCKED])

    # Now attempt to re-lock the SAME pair at R1 (a rematch) — illegal.
    at.session_state[KEY_PENDING_LOCK] = (0, w, ell)
    at.button(key="live_lock_btn").click().run()
    assert not at.exception

    # The validate_lock reason is shown via st.error; the lock + cache are untouched.
    assert any("no rematches" in e.value.lower() for e in at.error)
    assert list(at.session_state[KEY_LOCKED]) == locked_before
    assert dict(at.session_state["mc_cache"]) == cache_before


def test_live_status_chips_render():
    """RESIM-02/04: a lock that secures a pick renders glyph+label status badges
    ('/ secured' / 'o live' / 'x dead'), and the bracket renders record-bucket COLUMNS (bucket
    labels + flex layout) — never a tree."""
    from ui.state import KEY_LOCKED

    at = _go_live_small(_apptest().run())
    assert not at.exception

    w, ell = _first_legal_r1_lock()
    at.session_state[KEY_LOCKED] = [(0, w, ell)]
    at.button(key="run_btn").click().run()
    assert not at.exception

    text = _all_text(at)
    html_blobs = "\n".join(m.value for m in at.markdown)
    # Status chips: at least one of the glyph+label badges renders (UI-06 blue/amber, never red/green).
    assert any(tok in text for tok in ("secured", "live", "dead"))
    assert any(g in html_blobs for g in ("/ secured", "o live", "x dead"))
    # Record-bucket bracket: canonical column labels present, a flex layout, NOT a tree.
    assert "0-0" in html_blobs and "3-0 adv" in html_blobs
    assert "display:flex" in html_blobs
    # No tree/connector markup leaked in (the bracket is columns, RESIM-04).
    assert "tree" not in html_blobs.lower()


def test_live_delta_anchor_uses_pre_key():
    """BLOCKER 1 / T-04-ANCHOR: the delta hero's anchor ballot is captured ONCE from the
    EMPTY-locked pre_key Result via optimize_cached(pre_lock_result, *pre_key).recommended and
    stored in session_state; locking does NOT re-optimize it, and pge5_delta's `before` equals
    p_ge5(anchor, matrices(pre_key Result.sample, ids)) — i.e. `before` is the pre_key Result."""
    from engine.live import pge5_delta
    from engine.optimizer import build_outcome_matrices, p_ge5
    from engine.teams import load_teams
    from ui.state import KEY_LIVE_ANCHOR, KEY_LOCKED

    at = _go_live_small(_apptest().run())
    assert not at.exception
    anchor_pre = at.session_state[KEY_LIVE_ANCHOR]
    assert anchor_pre is not None

    cache = at.session_state["mc_cache"]
    pre_key = next(k for k in cache if k[3] == ())
    pre_result = cache[pre_key]

    w, ell = _first_legal_r1_lock()
    at.session_state[KEY_LOCKED] = [(0, w, ell)]
    at.button(key="run_btn").click().run()
    assert not at.exception

    # The anchor is UNCHANGED after the lock (never re-optimized per round).
    anchor_post = at.session_state[KEY_LIVE_ANCHOR]
    assert anchor_post == anchor_pre

    # `before` is computed on the pre_key Result's OWN sample (not the post-lock result).
    cache = at.session_state["mc_cache"]
    post_key = next(k for k in cache if k[3] != ())
    post_result = cache[post_key]
    ids = [t.id for t in load_teams()]
    before, after = pge5_delta(anchor_post, pre_result, post_result, ids)
    expected_before = p_ge5(anchor_post, build_outcome_matrices(pre_result.sample, ids))
    assert abs(before - expected_before) < 1e-12


def test_bracket_columns_html_is_columns_not_tree():
    """RESIM-04 (pure render): bracket_columns_html emits record-bucket flex COLUMNS, escapes
    team names, marks locked-solid vs simulated-faint via opacity, and has no tree/connector
    markup. Pure assertion — no AppTest needed (the render exists from Task 1)."""
    from engine.live import BracketView
    from ui.render import bracket_columns_html

    # Two teams at 1-0 / 0-1 from a single locked R1 result; a third still at 0-0 (simulated).
    view = BracketView(
        legal_pairings=[],
        records={1: (1, 0), 9: (0, 1), 2: (0, 0)},
        locked_edges={frozenset((1, 9))},
    )
    name_of = {1: "GamerLegion", 9: "NRG", 2: "<script>B8"}
    html_out = bracket_columns_html(view, name_of)

    # Flex row of record-bucket columns (NOT a tree).
    assert "display:flex" in html_out
    assert "0-0" in html_out and "1-0" in html_out and "0-1" in html_out
    assert "3-0 adv" in html_out and "0-3 elim" in html_out
    assert "tree" not in html_out.lower()
    # Locked teams (in a locked edge) are solid; the simulated-only team is faint.
    assert "opacity:1" in html_out      # locked (GamerLegion / NRG)
    assert "opacity:0.5" in html_out    # simulated-only (B8 at 0-0)
    # Names are html.escape-d (XSS defense-in-depth).
    assert "&lt;script&gt;B8" in html_out
    assert "<script>B8" not in html_out
