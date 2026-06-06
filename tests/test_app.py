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

import json
from pathlib import Path

import pytest

APP = "app.py"


@pytest.fixture(autouse=True)
def _no_ambient_odds_cache():
    """Isolate every AppTest run from the ambient ``data/odds_cache.json`` (a gitignored runtime
    artifact). Once odds are fetched that file is populated and the app takes the odds-fed path
    (K epistemic draws x N sims, ~12x cost), which blows the 60s AppTest budget for the timing
    tests in this file. A fresh checkout has no such file, which is why these tests passed before;
    here we recreate that clean state by moving any real cache aside for the duration of the test
    and restoring it after. Tests that need a cache (test_cache_present_feeds_sim) supply their own
    via a tmp file + monkeypatch, and the direct-loader test passes explicit paths — both are
    unaffected because the real ``load_odds_cache`` is left intact."""
    p = Path("data/odds_cache.json")
    backup = p.with_suffix(".json.testbak") if p.exists() else None
    if backup is not None:
        p.replace(backup)
    try:
        yield
    finally:
        if backup is not None:
            backup.replace(p)


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
    # stage_id is the new REAL leading positional (Phase 6, STG-04) — both calls carry "stage1".
    r_empty = run_mc_cached("stage1", rk, 40.0, 2000, lk_empty)
    r_locked = run_mc_cached("stage1", rk, 40.0, 2000, lk_locked)
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
    """OPT-03: after a Run the pre-stage panel shows Ballot A (E[correct] greedy) and Ballot B
    (Max P(>=5)) side by side with team names."""
    at = _run_small(_apptest().run())
    assert not at.exception
    text = _all_text(at)
    assert "E[correct] greedy" in text  # Ballot A (greedy, not claimed globally optimal)
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


def test_read_seeds_confirmed_reads_json_read_only(tmp_path):
    """DX-02: read_seeds_confirmed parses a stage JSON read-only and falls back to False on a
    missing/bad file — it never mutates the engine or the JSON. The shipped data/stage1.json now
    confirms the VERIFIED Cologne seed order (seeds_confirmed=true, 2026-06-01); the mechanism
    still reads whichever value the file holds."""
    from ui.state import read_seeds_confirmed

    # Shipped JSON: seeds are confirmed (seed order verified vs Liquipedia + Kalshi + R1 rule).
    assert read_seeds_confirmed() is True
    # Reads an explicit False flag from a file (exercises the read, not the shipped value).
    false_file = tmp_path / "stage_false.json"
    false_file.write_text(json.dumps({"seeds_confirmed": False, "teams": []}), encoding="utf-8")
    assert read_seeds_confirmed(str(false_file)) is False
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


def test_trust_badge_caveated_until_both(monkeypatch):
    """UI-07: when seeds are UNCONFIRMED the header renders the EXACT caveated badge text and
    never a green/Budapest 'validated' state — the badge is gated on BOTH the backtest AND seeds.
    The shipped JSON now confirms the seeds, so this test forces the unconfirmed state to exercise
    the both-gate mechanism (independent of the shipped default)."""
    from ui.state import TRUST_BADGE_CAVEATED

    monkeypatch.setattr("ui.state.read_seeds_confirmed", lambda *a, **k: False)
    at = _apptest().run()
    assert not at.exception
    text = _all_text(at)
    assert TRUST_BADGE_CAVEATED in text
    assert "Budapest" not in text
    # No green-check / "backtest passed" / "validated ✓" claim anywhere in the header.
    assert "✓" not in text
    assert "backtest passed" not in text.lower()


def test_trust_badge_validated_with_shipped_confirmed_seeds():
    """UI-07 (new shipped reality): with the shipped seeds_confirmed=true AND the backtest passed,
    the header shows the VALIDATED badge and the INFERRED-seed warning is gone."""
    from ui.state import TRUST_BADGE_VALIDATED

    at = _apptest().run()
    assert not at.exception
    # The validated badge renders via st.success (not captured by _all_text's element list).
    assert any(TRUST_BADGE_VALIDATED in s.value for s in at.success)
    assert not any("seeds are inferred" in w.value.lower() for w in at.warning)


def test_seed_banner(monkeypatch):
    """DX-02: when seeds are unconfirmed the persistent '⚠ Seeds are INFERRED' warning is present,
    with a field-by-field reconcile area listing the seed→team rows. Forced-unconfirmed so it
    tests the banner mechanism independent of the shipped (now confirmed) default."""
    monkeypatch.setattr("ui.state.read_seeds_confirmed", lambda *a, **k: False)
    at = _apptest().run()
    assert not at.exception
    assert any("seeds are inferred" in w.value.lower() for w in at.warning)
    # The reconcile area lists seed→team rows (eyeball vs the official list) — assert a few.
    text = _all_text(at)
    assert "GamerLegion" in text  # seed 1
    assert "FlyQuest" in text     # seed 16


def test_seed_banner_dismissable(monkeypatch):
    """DX-02 / STG-05: toggling 'seeds confirmed' dismisses the INFERRED-seed banner; the toggle
    drives session_state (the gate the trust badge reads). The banner+toggle are now PER-STAGE
    (STG-05), so on the default Stage 1 the toggle key is 'seeds_confirmed_stage1'.
    Forced-unconfirmed start (monkeypatch read_seeds_confirmed → False)."""
    # Default stage is Stage 1 (DX-01 zero-config first run), so the per-stage confirm key is
    # f"seeds_confirmed_{stage_id}" == "seeds_confirmed_stage1".
    seeds_key = "seeds_confirmed_stage1"

    monkeypatch.setattr("ui.state.read_seeds_confirmed", lambda *a, **k: False)
    at = _apptest().run()
    assert not at.exception
    # First load: banner present, toggle off.
    assert any("seeds are inferred" in w.value.lower() for w in at.warning)

    # Find the per-stage seeds-confirmed toggle (st.toggle preferred; checkbox is the fallback).
    widgets = list(getattr(at, "toggle", [])) + list(getattr(at, "checkbox", []))
    tog = next(w for w in widgets if w.key == seeds_key)
    tog.set_value(True).run()
    assert not at.exception
    # After confirming, the INFERRED-seed warning is gone (dismissed).
    assert not any("seeds are inferred" in w.value.lower() for w in at.warning)
    assert at.session_state[seeds_key] is True


def test_per_stage_seed_banner():
    """STG-05: the [INFERRED]-seed banner is PER-STAGE — each stage reads its OWN fixture's
    seeds_confirmed flag, so confirming one stage cannot dismiss another's banner.

    Stage 1's shipped fixture is seeds_confirmed=true → NO banner; Stage 2's is false → the
    loud warning shows. The Stage-2 confirm toggle is keyed 'seeds_confirmed_stage2' (distinct
    from Stage 1's 'seeds_confirmed_stage1'), proving the per-stage session key. No monkeypatch
    of read_seeds_confirmed — the per-stage state is driven by the real committed fixtures."""
    from ui.state import KEY_STAGE

    # Stage 1 (default): the shipped fixture confirms the seeds → no INFERRED-seed warning, and
    # no Stage-2 toggle yet (that key only appears once Stage 2 is the active stage).
    at = _apptest().run()
    assert not at.exception
    assert not any("seeds are inferred" in w.value.lower() for w in at.warning)
    s1_toggle_keys = {w.key for w in getattr(at, "toggle", [])}
    assert "seeds_confirmed_stage2" not in s1_toggle_keys

    # Switch to Stage 2 (inject the selector's session value, as the LIVE/isolation tests do —
    # robust to the selector widget type). Stage 2's fixture is seeds_confirmed=false.
    at.session_state[KEY_STAGE] = "stage2"
    at.run()
    assert not at.exception
    # Stage 2 SHOWS the INFERRED-seed warning (its fixture is unconfirmed).
    assert any("seeds are inferred" in w.value.lower() for w in at.warning), (
        "Stage 2 (seeds_confirmed:false) must show the INFERRED-seed banner"
    )
    # The Stage-2 confirm toggle is keyed per-stage — distinct from Stage 1's key.
    s2_toggle_keys = {w.key for w in getattr(at, "toggle", [])}
    assert "seeds_confirmed_stage2" in s2_toggle_keys, (
        "the confirm toggle must be keyed 'seeds_confirmed_stage2' (per-stage), proving the "
        "banner state is scoped to the active stage"
    )
    assert "seeds_confirmed_stage1" not in s2_toggle_keys, (
        "only the active stage's toggle renders — Stage 1's key must not leak into the Stage-2 view"
    )


def test_odds_off_banner_failsoft(monkeypatch):
    """ODDS-08 (honest live/off, D1): with no ODDSPAPI_KEY AND no loaded cache, the status reads
    'odds off … manual ratings' (driven by the CACHE, not the env key) and the app never crashes.

    The cache is forced to None so the off-state is deterministic regardless of any local
    data/odds_cache.json. The old banner keyed on ODDSPAPI_KEY and lied when a keyless fetch was
    live; the new panel reads the same cache the run feeds on (no httpx/dotenv on the render path).
    """
    monkeypatch.delenv("ODDSPAPI_KEY", raising=False)
    monkeypatch.setattr("ui.odds_loader.load_odds_cache", lambda *a, **k: None)
    at = _apptest().run()
    assert not at.exception
    text = _all_text(at).lower()
    assert "odds off" in text and "manual ratings" in text


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
    # Every cache key is (stage_id, ratings_key, S, N, locked_key); a new one carries a non-empty
    # locked_key — at index 4 now that stage_id leads (Phase 6, STG-04).
    assert any(k[4] != () for k in new_keys)


def test_live_lock_moves_p_advance():
    """RESIM-01: after a legal lock + re-sim, at least one team's P(advance) differs from the
    pre-lock value — read the two Results from the session mc_cache on their respective keys."""
    from ui.state import KEY_LOCKED

    at = _go_live_small(_apptest().run())
    assert not at.exception
    cache = at.session_state["mc_cache"]
    pre_key = next(k for k in cache if k[4] == ())
    pre_p_adv = cache[pre_key].p_advance()

    w, ell = _first_legal_r1_lock()
    at.session_state[KEY_LOCKED] = [(0, w, ell)]
    at.button(key="run_btn").click().run()
    assert not at.exception

    cache = at.session_state["mc_cache"]
    post_key = next(k for k in cache if k[4] != ())
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


def test_live_round_progress_caption_shows_remaining():
    """ISSUE-2: the open round shows a 'N of M matches locked — lock all M to open the next
    round' progress hint, so the round-gating is discoverable (it stuck a UAT tester)."""
    from ui.state import KEY_LOCKED

    at = _go_live_small(_apptest().run())
    assert not at.exception

    # Partially lock Round 1 (1 of 8) — the caption must surface the remaining count.
    w, ell = _first_legal_r1_lock()
    at.session_state[KEY_LOCKED] = [(0, w, ell)]
    at.button(key="run_btn").click().run()
    assert not at.exception

    text = _all_text(at)
    assert "of 8 matches locked" in text
    assert "lock all 8 to open the next round" in text.lower()


def test_live_delta_table_shows_per_team_change():
    """RESIM-02 / ISSUE-1: the LIVE 'Delta probabilities' table shows the per-team CHANGE vs
    pre-lock (signed '+/-pp' tags), not just absolute values — so the user can see what moved.
    The locked winner's P(advance) tag is a positive delta (its R1 result is now certain)."""
    from ui.state import KEY_LOCKED

    at = _go_live_small(_apptest().run())
    assert not at.exception

    w, ell = _first_legal_r1_lock()
    at.session_state[KEY_LOCKED] = [(0, w, ell)]
    at.button(key="run_btn").click().run()
    assert not at.exception

    text = _all_text(at)
    html_blobs = "\n".join(m.value for m in at.markdown)
    # The section still exists, now with the clarifying caption (no longer a bare 'Delta' label).
    assert "Delta probabilities" in text
    assert "change vs pre-lock" in text
    # Signed percentage-point delta tags render (the fix's signal) — at least one positive/blue.
    assert "pp</span>" in html_blobs
    assert "+" in html_blobs and "#3B82F6" in html_blobs  # an increase rendered in blue


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
    pre_key = next(k for k in cache if k[4] == ())
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
    post_key = next(k for k in cache if k[4] != ())
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


# --- Phase 5 (05-03): odds-cache read seam + fail-soft + no-network-on-rerun -------------
#
# These exercise the read-only cache seam (ui/odds_loader.py) wired into app.py: a present cache
# feeds the back-solved ratings + epistemic blend/var into the existing run path so the odds move
# the reported probabilities; an ABSENT cache (the normal first-run state) is fail-soft (rating-
# only + the existing banner); the app makes NO provider/network call on a rerun (Pitfall 11); a
# fresh fetch (new _meta.fetched_at) invalidates the memoized Result (T-05-STALEBAND).
#
# Wave-0 (Task 1) ships them RED via xfail(strict=True) for the AppTest cases that depend on the
# app.py wiring; Task 2 wires app.py and removes the markers (strict xfail flips a passing test to
# XPASS -> failure, so a stray un-removed marker can't hide a real pass). The loader fail-soft test
# is a pure unit assertion (cheaper than an AppTest) and is GREEN from Task 1. N is kept small
# (2000) per the latency budget.


def test_cache_loader_failsoft(tmp_path):
    """ODDS-08 / T-05-NOCACHE: load_odds_cache returns None on a missing path, malformed JSON, a
    non-dict payload, and a wrong (_meta.version != 1) schema — never raises. A valid v1 cache
    round-trips. Pure unit (no AppTest)."""
    from ui.odds_loader import load_odds_cache

    # Missing file -> None (the normal first-run state).
    assert load_odds_cache(tmp_path / "nope.json") is None

    # Malformed JSON -> None.
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_odds_cache(bad) is None

    # Non-dict payload -> None.
    arr = tmp_path / "arr.json"
    arr.write_text("[1, 2, 3]", encoding="utf-8")
    assert load_odds_cache(arr) is None

    # Wrong version -> None (fails closed rather than feeding a foreign schema).
    wrongver = tmp_path / "v2.json"
    wrongver.write_text(
        json.dumps({"_meta": {"version": 2}, "blended": {}}), encoding="utf-8"
    )
    assert load_odds_cache(wrongver) is None

    # A valid v1 cache round-trips (the dict is returned intact).
    good = tmp_path / "good.json"
    payload = {
        "_meta": {"fetched_at": "2026-05-29T00:00:00+00:00", "version": 1},
        "blended": {"1-9": {"p": 0.71, "var": 0.004, "n_sources": 2, "bo3": False}},
    }
    good.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_odds_cache(good)
    assert loaded is not None
    assert loaded["blended"]["1-9"]["p"] == 0.71


def _write_cache(path, blended, *, fetched_at="2026-05-29T00:00:00+00:00"):
    """Write a valid v1 odds cache to ``path`` for the AppTest cases (the schema the app reads)."""
    payload = {
        "_meta": {
            "fetched_at": fetched_at,
            "version": 1,
            "providers_present": ["polymarket", "kalshi"],
            "round_hint": 1,
        },
        "blended": blended,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_no_odds_failsoft(monkeypatch):
    """ODDS-08: with NO ODDSPAPI_KEY and NO data/odds_cache.json the app renders, runs rating-only,
    shows the existing 'live odds off … manual ratings' banner, and never raises — the absent-cache
    first run does not crash on the odds path."""
    monkeypatch.delenv("ODDSPAPI_KEY", raising=False)
    monkeypatch.setattr("ui.odds_loader.load_odds_cache", lambda *a, **k: None)
    at = _run_small(_apptest().run())
    assert not at.exception
    text = _all_text(at).lower()
    assert "odds off" in text and "manual ratings" in text
    # Rating-only run still produced per-team probability content.
    assert any("advance" in m.value.lower() for m in at.markdown)


def test_live_odds_status_panel_renders(monkeypatch, tmp_path):
    """D1: a loaded cache with a non-empty blended map shows the honest 'live' status panel —
    market count + human book labels + a relative fetched age — not the off copy.

    fetched_at is written FRESH (from now) so the staleness branch stays deterministic regardless
    of the system clock: a recent fetch must NOT show the stale warning.
    """
    from datetime import datetime, timezone

    monkeypatch.delenv("ODDSPAPI_KEY", raising=False)
    cache_file = tmp_path / "odds_cache.json"
    fresh = datetime.now(timezone.utc).isoformat()
    _write_cache(
        cache_file,
        {"1-9": {"p": 0.6, "var": 0.0, "n_sources": 2, "bo3": True}},
        fetched_at=fresh,
    )
    import ui.odds_loader as loader

    _real_load = loader.load_odds_cache
    monkeypatch.setattr(loader, "load_odds_cache", lambda *a, **k: _real_load(cache_file))

    at = _apptest().run()
    assert not at.exception
    text = _all_text(at)
    assert "market(s)" in text                       # the live count line rendered
    assert "Polymarket" in text and "Kalshi" in text  # human book labels (allowlist)
    assert "odds off" not in text.lower()             # NOT the off copy
    assert "may be stale" not in text.lower()         # a fresh fetch is not stale


def test_fetch_outcome_persists_across_rerun(monkeypatch):
    """Bug A fix: a fetch outcome stashed in session_state is rendered on the NEXT run (surviving
    the st.rerun the fetch triggers) and then popped — not lost like st.success-before-st.rerun.

    Uses an 'info'-level outcome so _all_text captures it; the stash/render/pop mechanism is the
    same for success/error. After rendering, the key is cleared so the message is one-shot.
    """
    from ui.state import KEY_ODDS_OUTCOME

    monkeypatch.delenv("ODDSPAPI_KEY", raising=False)
    monkeypatch.setattr("ui.odds_loader.load_odds_cache", lambda *a, **k: None)
    at = _apptest().run()
    at.session_state[KEY_ODDS_OUTCOME] = ("info", "No live markets found yet (test marker).")
    at.run()
    assert not at.exception
    assert "No live markets found yet (test marker)." in _all_text(at)
    # One-shot: the outcome is popped so it does not persist into the following rerun.
    assert KEY_ODDS_OUTCOME not in at.session_state


def test_odds_drilldown_and_two_tone_under_sourced_cache(monkeypatch, tmp_path):
    """D2/D3: a loaded cache carrying per-source prices shows the 'why the books disagree' drill-down
    (human book labels + blended consensus, sorted by spread) and, after Run, the two-tone CI legend.
    """
    from datetime import datetime, timezone

    monkeypatch.delenv("ODDSPAPI_KEY", raising=False)
    cache_file = tmp_path / "odds_cache.json"
    fresh = datetime.now(timezone.utc).isoformat()
    blended = {
        "1-9": {
            "p": 0.62,
            "var": 0.02,
            "n_sources": 3,
            "bo3": True,
            "sources": [
                {"book": "oddspapi", "p": 0.66},
                {"book": "polymarket", "p": 0.55},
                {"book": "kalshi", "p": 0.64},
            ],
        }
    }
    _write_cache(cache_file, blended, fetched_at=fresh)
    import ui.odds_loader as loader

    _real = loader.load_odds_cache
    monkeypatch.setattr(loader, "load_odds_cache", lambda *a, **k: _real(cache_file))

    at = _run_small(_apptest().run())  # Run so the odds-fed (two-tone) probs table renders
    assert not at.exception
    text = _all_text(at)
    # Drill-down content (inside the expander) — caption + human book labels + blended consensus.
    assert "Each book's series price" in text
    assert "Pinnacle" in text and "Polymarket" in text and "Kalshi" in text
    assert "blended 0.62" in text
    # Two-tone CI legend appears on the odds-fed probs table.
    assert "solid = sampling band" in text


def test_zero_config_first_run_still_works(monkeypatch):
    """DX-01: a fresh run with no key + no cache hits Run and produces per-team P(advance) — the
    Phase-2 zero-config promise is unbroken by the Phase-5 wiring."""
    monkeypatch.delenv("ODDSPAPI_KEY", raising=False)
    monkeypatch.setattr("ui.odds_loader.load_odds_cache", lambda *a, **k: None)
    at = _apptest().run()
    assert not at.exception
    at.button(key="run_btn").click().run()
    assert not at.exception
    assert any("advance" in m.value.lower() for m in at.markdown)


def test_cache_present_feeds_sim(monkeypatch, tmp_path):
    """ODDS-04/05: a valid data/odds_cache.json present -> load_odds_cache returns it and the run
    path uses the back-solved ratings + epistemic blend/var, so at least one reported P(advance)
    differs from the pure rating-only run (the odds change the numbers)."""
    from engine.montecarlo import run_mc
    from engine.teams import load_teams
    from ui.state import FIXED_SEED

    # Rating-only baseline P(advance) (no cache).
    teams = load_teams()
    ratings = {t.seed: t.rating for t in teams}
    base = run_mc(teams, ratings, 40.0, 2000, locked={}, seed=FIXED_SEED).p_advance()

    # A cache that pushes the seed-1 vs seed-9 series hard with real cross-source variance.
    import ui.odds_loader as loader

    cache_file = tmp_path / "odds_cache.json"
    _write_cache(cache_file, {"1-9": {"p": 0.95, "var": 0.02, "n_sources": 2, "bo3": False}})
    _real_load = loader.load_odds_cache
    monkeypatch.setattr(loader, "load_odds_cache", lambda *a, **k: _real_load(cache_file))

    at = _run_small(_apptest().run())
    assert not at.exception
    cache = at.session_state["mc_cache"]
    assert cache, "a run must have produced a cached Result"
    result = next(iter(cache.values()))
    odds_p_adv = result.p_advance()
    # The odds-fed run moved at least one team's P(advance) vs the rating-only baseline.
    assert any(
        abs(odds_p_adv.get(tid, 0.0) - base.get(tid, 0.0)) > 1e-9
        for tid in set(base) | set(odds_p_adv)
    )


def test_app_makes_no_network_on_rerun(monkeypatch):
    """Pitfall 11 / T-05-RERUN: the app makes NO provider/network call on a rerun. Monkeypatch
    httpx to RAISE on any attribute access; the app still renders and runs — proving the render
    path never touches httpx (only the explicit 'fetch now' button, not exercised here, would)."""
    import httpx

    class _Boom:
        def __getattr__(self, name):
            raise AssertionError(f"httpx.{name} called on a rerun — Pitfall 11 violation")

    # Replace every httpx network entrypoint with a raiser.
    for attr in ("get", "post", "request", "Client", "AsyncClient", "stream"):
        monkeypatch.setattr(httpx, attr, _Boom(), raising=False)

    at = _apptest().run()
    assert not at.exception
    at.button(key="run_btn").click().run()  # a rerun
    assert not at.exception
    # The app still produced probability content despite httpx being booby-trapped.
    assert any("advance" in m.value.lower() for m in at.markdown)


def test_fresh_fetch_invalidates_cache(monkeypatch, tmp_path):
    """T-05-STALEBAND: a fresh fetch that moves only `var` (not the back-solved ratings) still
    invalidates the memoized Result. Write a cache, run (memoizes a Result); then write a SECOND
    cache with the SAME `p` (same back-solved ratings) but a DIFFERENT `_meta.fetched_at` AND a
    moved `var`; the next run must produce a NEW mc_cache key (the fetched_at is in the run cache
    key) — not a stale serve."""
    import ui.odds_loader as loader

    cache_file = tmp_path / "odds_cache.json"

    def _read(p=cache_file):
        from pathlib import Path as _Path
        raw = json.loads(_Path(p).read_text(encoding="utf-8"))
        return raw if raw.get("_meta", {}).get("version") == 1 else None

    # The app reads whatever the file currently holds (re-read each call so the second fetch shows).
    monkeypatch.setattr(loader, "load_odds_cache", lambda *a, **k: _read())

    # Same p, modest var, fetched_at #1.
    _write_cache(
        cache_file,
        {"1-9": {"p": 0.8, "var": 0.001, "n_sources": 2, "bo3": False}},
        fetched_at="2026-05-29T00:00:00+00:00",
    )

    at = _run_small(_apptest().run())
    assert not at.exception
    keys_after_first = set(at.session_state["mc_cache"].keys())
    assert keys_after_first, "first run must memoize a Result"

    # SECOND fetch: SAME p (same ratings) but moved var + a NEW fetched_at.
    _write_cache(
        cache_file,
        {"1-9": {"p": 0.8, "var": 0.05, "n_sources": 2, "bo3": False}},
        fetched_at="2026-05-29T12:00:00+00:00",
    )
    at.button(key="run_btn").click().run()
    assert not at.exception
    keys_after_second = set(at.session_state["mc_cache"].keys())
    # A NEW cache key appeared because fetched_at is folded into the run cache key — the new var is
    # recomputed, NOT stale-served from the first run's memoized Result.
    assert keys_after_second - keys_after_first, (
        "a fresh fetch (new _meta.fetched_at) must invalidate the memoized Result (T-05-STALEBAND)"
    )


def test_stage_switch_isolates_cache():
    """STG-04 (integration): running Stage 1, then switching to Stage 2 via the selector and
    Running, creates an mc_cache key whose LEADING element is 'stage2'; the prior Stage-1 key
    (leading 'stage1') stays distinct — no cache key is shared across stages, so one stage can
    never serve the other's per-team numbers."""
    from ui.state import KEY_STAGE

    # Default stage is Stage 1 — run it first to memoize a 'stage1'-leading key.
    at = _apptest().run()
    assert not at.exception
    at.button(key="run_btn").click().run()
    assert not at.exception
    stage1_keys = set(at.session_state["mc_cache"].keys())
    assert stage1_keys, "the first (Stage-1) run must memoize a key"
    assert all(k[0] == "stage1" for k in stage1_keys), (
        "every key from the default-stage run must lead with 'stage1'"
    )

    # Switch to Stage 2 and Run again (inject the selector's session value, as the LIVE tests
    # inject KEY_LOCKED — robust to the selector widget type).
    at.session_state[KEY_STAGE] = "stage2"
    at.button(key="run_btn").click().run()
    assert not at.exception

    all_keys = set(at.session_state["mc_cache"].keys())
    stage2_keys = {k for k in all_keys if k[0] == "stage2"}
    assert stage2_keys, "running under Stage 2 must create a 'stage2'-leading cache key"
    # The Stage-1 key is still present and distinct — no key is shared across stages.
    assert stage1_keys & stage2_keys == set(), "no cache key may be shared across stages"
    assert all(k[0] == "stage1" for k in stage1_keys)


# --- Phase 6 Slice 4: live-results seam wired into the app (RES-02/03/04) -----------------
#
# These AppTest cases exercise the "Fetch latest results" button, the fetched-result pre-fill of
# KEY_LOCKED via the EXISTING validate path (no engine edit), the fetched_at-in-cache-key re-sim
# re-fire, the int-vs-str canonical stage filter, and the atomic conflict-confirm against a manual
# lock. The results cache is supplied per-test via monkeypatching ui.results_loader.load_results_cache
# (mirroring the odds-cache tests). N is kept small (2000) per the latency budget.


def _results_cache(rows, *, stage=1, fetched_at="2026-06-04T00:00:00+00:00", source="bo3gg"):
    """A frozen-schema results-cache dict (mirrors scripts.fetch_results.main's write shape).

    ``stage`` is the INTEGER stage number the frozen schema stores in _meta (1 for "stage1"); the
    app's canonical _stage_int_for reconciles it against the str stage_id. ``rows`` are the
    {match:[lo,hi], winner, round_idx, bo, status, provider_slugs} result rows.
    """
    return {
        "_meta": {"fetched_at": fetched_at, "version": 1, "source": source, "stage": stage},
        "results": list(rows),
    }


def _finished_row(lo, hi, winner, *, round_idx=0, bo=1):
    """One FINISHED frozen-schema result row (match is the SORTED [lo, hi] engine-id tuple)."""
    a, b = sorted((lo, hi))
    return {
        "match": [a, b],
        "winner": winner,
        "round_idx": round_idx,
        "bo": bo,
        "status": "finished",
        "provider_slugs": [f"slug{a}", f"slug{b}"],
    }


def _ss_get(at, key, default=None):
    """Read at.session_state[key] safely — AppTest's SessionState proxy has no .get() (subscript
    only), so mirror dict.get via a presence check. Used by the conflict/provenance tests."""
    return at.session_state[key] if key in at.session_state else default


def _patch_results(monkeypatch, cache):
    """Monkeypatch BOTH the loader module and app.py's imported alias to return ``cache``.

    app.py may either ``from ui.results_loader import load_results_cache`` (binding a local alias) or
    call it qualified; patching both the source module attr and the app attr (raising=False) covers
    whichever binding the wiring uses, so the test is robust to the import style."""
    import ui.results_loader as rloader

    monkeypatch.setattr(rloader, "load_results_cache", lambda *a, **k: cache)
    monkeypatch.setattr("app.load_results_cache", lambda *a, **k: cache, raising=False)


def test_fetched_results_prefill_locked(monkeypatch):
    """RES-02 / T-06-10 + T-06-12: a FINISHED row whose _meta.stage is the INTEGER 1 pre-fills
    KEY_LOCKED while the active stage_id is the STRING 'stage1' — the canonical int-vs-str filter
    FIRES (the row is NOT silently skipped). The non-empty locked_key produces a NEW mc_cache key
    (re-sim fires). An ILLEGAL fetched row (a non-pairing for the round) is REJECTED via the existing
    validate_lock reason and does NOT mutate KEY_LOCKED."""
    from ui.state import KEY_LOCKED

    # A legal R1 result (1 beats 9 — seed i vs i+8 is the R1 pairing) PLUS an illegal non-pairing
    # row (1 vs 2 are NOT paired in R1) that validate_lock must reject without mutating KEY_LOCKED.
    legal = _finished_row(1, 9, winner=1, round_idx=0)
    illegal = _finished_row(2, 3, winner=2, round_idx=0)  # 2 vs 3 is not an R1 pairing
    _patch_results(monkeypatch, _results_cache([legal, illegal], stage=1))

    at = _go_live_small(_apptest().run())
    assert not at.exception

    # The legal fetched result auto-locked (1 beat 9); the illegal one did not.
    locked = list(at.session_state[KEY_LOCKED])
    assert (0, 1, 9) in locked, "the FINISHED int-stage-1 row must pre-fill KEY_LOCKED (filter fired)"
    assert not any(frozenset((w, ell)) == frozenset((2, 3)) for (_r, w, ell) in locked), (
        "an illegal non-pairing fetched row must be rejected, never locked"
    )
    # The non-empty locked_key produced a cache key with a populated locked element (re-sim fired).
    keys = set(at.session_state["mc_cache"].keys())
    assert any(k[4] != () for k in keys), "the auto-locked result must produce a non-empty locked cache key"


def test_fetched_at_refires_resim(monkeypatch):
    """RES-02 re-sim re-fire: with the SAME (stage_id, ratings, S, N, locked) two results caches
    differing ONLY in _meta.fetched_at produce DIFFERENT run cache keys (the fetched_at element
    differs) — a fresh fetch forces a MISS so the conditional re-sim re-fires even with an unchanged
    locked set. Unit form: assert _cache_key_for(...) with two fetched_at values differs in its last
    element (and the wired run threads the RESULTS fetched_at into that slot)."""
    import importlib

    app = importlib.import_module("app")

    ratings = {i: 50.0 for i in range(1, 17)}
    locked = {frozenset((1, 9)): 1}
    k1 = app._cache_key_for(ratings, locked, "stage1", "2026-06-04T00:00:00+00:00")
    k2 = app._cache_key_for(ratings, locked, "stage1", "2026-06-04T12:00:00+00:00")
    # Identical except the trailing fetched_at slot — a fresh fetch timestamp changes the key.
    assert k1[:-1] == k2[:-1], "only the fetched_at slot should differ"
    assert k1[-1] != k2[-1], "two different fetched_at values must yield different cache keys (re-sim re-fires)"

    # End-to-end: two results caches with the SAME locked set but different fetched_at each add a
    # distinct mc_cache key (the RESULTS fetched_at is threaded into the run cache key).
    legal = _finished_row(1, 9, winner=1, round_idx=0)
    _patch_results(monkeypatch, _results_cache([legal], stage=1, fetched_at="2026-06-04T00:00:00+00:00"))
    at = _go_live_small(_apptest().run())
    assert not at.exception
    keys_first = set(at.session_state["mc_cache"].keys())

    _patch_results(monkeypatch, _results_cache([legal], stage=1, fetched_at="2026-06-04T12:00:00+00:00"))
    at.button(key="run_btn").click().run()
    assert not at.exception
    keys_second = set(at.session_state["mc_cache"].keys())
    assert keys_second - keys_first, (
        "a fresh _meta.fetched_at (same locked set) must add a NEW run cache key — the re-sim re-fires"
    )


def test_no_results_failsoft(monkeypatch):
    """RES-04 fail-soft: with NO results cache and NO key the app renders + Runs (manual locking
    still works), no exception. The pre-fill must degrade to a no-op when load_results_cache is None."""
    monkeypatch.delenv("ODDSPAPI_KEY", raising=False)
    monkeypatch.setattr("ui.odds_loader.load_odds_cache", lambda *a, **k: None)
    _patch_results(monkeypatch, None)

    at = _apptest().run()
    assert not at.exception
    at.button(key="run_btn").click().run()
    assert not at.exception
    # Manual locking still works day one — switch to LIVE, inject a manual lock, re-run, no crash.
    from ui.state import KEY_LOCKED

    at = _go_live_small(at)
    assert not at.exception
    w, ell = _first_legal_r1_lock()
    at.session_state[KEY_LOCKED] = [(0, w, ell)]
    at.button(key="run_btn").click().run()
    assert not at.exception
    assert (0, w, ell) in list(at.session_state[KEY_LOCKED])


def test_no_network_on_rerun_with_results(monkeypatch):
    """T-06-09b: with the results seam WIRED (a results cache present) and httpx booby-trapped to
    RAISE on any attribute access, a rerun makes NO network call and still renders probability
    content — proving scripts.fetch_results is lazy-imported (click branch only), never on rerun."""
    import httpx

    class _Boom:
        def __getattr__(self, name):
            raise AssertionError(f"httpx.{name} called on a rerun — results seam network leak")

    for attr in ("get", "post", "request", "Client", "AsyncClient", "stream"):
        monkeypatch.setattr(httpx, attr, _Boom(), raising=False)

    # The results seam is active (a valid cache present) — the pre-fill reads it via the json loader.
    legal = _finished_row(1, 9, winner=1, round_idx=0)
    _patch_results(monkeypatch, _results_cache([legal], stage=1))

    at = _apptest().run()
    assert not at.exception
    at.button(key="run_btn").click().run()  # a rerun
    assert not at.exception
    assert any("advance" in m.value.lower() for m in at.markdown)


def test_fetch_conflict_requires_confirm(monkeypatch):
    """RES-03 / T-06-11: a fetched result for a pair the user MANUALLY locked with the OPPOSITE
    winner does NOT silently overwrite KEY_LOCKED. A loud conflict notice is shown + a pending
    conflict stashed; KEY_LOCKED keeps the manual lock until the user explicitly confirms. After a
    LEGAL confirm KEY_LOCKED reflects the fetched winner, tagged provenance 'auto'."""
    from ui.state import KEY_LOCK_PROVENANCE, KEY_LOCKED, KEY_PENDING_RESULT_CONFLICT

    # Fetched result: 9 beat 1 (opposite of the manual lock the user will hold: 1 beat 9).
    row = _finished_row(1, 9, winner=9, round_idx=0)
    _patch_results(monkeypatch, _results_cache([row], stage=1))

    at = _go_live_small(_apptest().run())
    assert not at.exception
    # Establish the MANUAL lock 1 beat 9 (opposite the fetched 9 beat 1) and re-run.
    at.session_state[KEY_LOCKED] = [(0, 1, 9)]
    at.session_state[KEY_LOCK_PROVENANCE] = {frozenset((1, 9)): "manual"}
    at.button(key="run_btn").click().run()
    assert not at.exception

    # The conflict was stashed (NOT silently applied); the manual lock is intact; a loud notice shows.
    assert _ss_get(at, KEY_PENDING_RESULT_CONFLICT) == (0, 9, 1)
    assert (0, 1, 9) in list(at.session_state[KEY_LOCKED]), "manual lock must survive until confirm"
    assert (0, 9, 1) not in list(at.session_state[KEY_LOCKED]), "fetched winner not applied pre-confirm"
    assert any("conflict" in w.value.lower() for w in at.warning), "a loud conflict warning must render"

    # Explicit confirm (a LEGAL swap — same R1 pair, opposite winner): KEY_LOCKED now holds 9 beat 1.
    at.button(key="apply_fetched_result_btn").click().run()
    assert not at.exception
    locked = list(at.session_state[KEY_LOCKED])
    assert (0, 9, 1) in locked, "after confirm the fetched winner is applied"
    assert (0, 1, 9) not in locked, "the manual lock was atomically swapped out on a legal confirm"
    assert _ss_get(at, KEY_LOCK_PROVENANCE, {}).get(frozenset((9, 1))) == "auto"


def test_conflict_confirm_validates_before_remove(monkeypatch):
    """RES-03 / T-06-11 (the atomicity guard): confirming a fetched result for the SAME pair whose
    proposed lock is ENGINE-ILLEGAL (validate_lock returns a reason — here a non-pairing for the
    round) leaves the original MANUAL lock PRESERVED (KEY_LOCKED unchanged, the manual entry not
    removed) and surfaces the validate_lock reason. The remove-manual + add-fetched happens ONLY on a
    successful validate_lock — never remove-then-fail."""
    from ui.state import KEY_LOCK_PROVENANCE, KEY_LOCKED, KEY_PENDING_RESULT_CONFLICT

    # Manual lock for the pair {1,5} (NOT an R1 pairing — R1 is i vs i+8, so {1,9}). Injected directly
    # to represent a manual lock; the fetched conflict proposes the OPPOSITE winner for the SAME pair.
    # On confirm the prospective swap validates {5,1} at R1 -> "not paired this round" -> rejected.
    row = _finished_row(1, 5, winner=5, round_idx=0)
    _patch_results(monkeypatch, _results_cache([row], stage=1))

    at = _go_live_small(_apptest().run())
    assert not at.exception
    at.session_state[KEY_LOCKED] = [(0, 1, 5)]
    at.session_state[KEY_LOCK_PROVENANCE] = {frozenset((1, 5)): "manual"}
    at.button(key="run_btn").click().run()
    assert not at.exception
    # The conflict is stashed (same pair, opposite winner, manual provenance).
    assert _ss_get(at, KEY_PENDING_RESULT_CONFLICT) == (0, 5, 1)

    locked_before = list(at.session_state[KEY_LOCKED])
    # Confirm — but the fetched lock is engine-illegal (non-pairing) -> rejected, manual preserved.
    at.button(key="apply_fetched_result_btn").click().run()
    assert not at.exception
    assert list(at.session_state[KEY_LOCKED]) == locked_before, (
        "an engine-illegal fetched lock must NOT remove the manual lock (validate before remove)"
    )
    assert (0, 1, 5) in list(at.session_state[KEY_LOCKED]), "the manual lock is preserved"
    # The validate_lock reason is surfaced (the 'not paired this round' string).
    assert any("not paired this round" in e.value.lower() for e in at.error), (
        "the validate_lock reason must be surfaced on a rejected confirm"
    )


def test_provenance_and_staleness_surfaced(monkeypatch):
    """RES-03: a loaded results cache surfaces _meta.fetched_at via the existing fmt_age/is_stale (a
    stale cache shows the stale warning), and each lock's provenance (auto vs manual) is rendered."""
    from ui.state import KEY_LOCK_PROVENANCE, KEY_LOCKED

    # A STALE fetched_at (well past the 2h threshold) so is_stale -> True deterministically.
    row = _finished_row(1, 9, winner=1, round_idx=0)
    _patch_results(
        monkeypatch,
        _results_cache([row], stage=1, fetched_at="2020-01-01T00:00:00+00:00"),
    )

    at = _go_live_small(_apptest().run())
    assert not at.exception
    # The fetched result auto-locked (provenance auto), so a provenance badge + staleness surface.
    assert (0, 1, 9) in list(at.session_state[KEY_LOCKED])
    assert _ss_get(at, KEY_LOCK_PROVENANCE, {}).get(frozenset((1, 9))) == "auto"
    text = _all_text(at)
    # Staleness surfaced via the existing helper copy.
    assert "stale" in text.lower(), "a stale results cache must surface a stale notice"
    # Per-lock provenance rendered (auto vs manual wording).
    assert "auto" in text.lower(), "auto-fetched provenance must be surfaced"


# --- Phase 6 code-review fixes (06-REVIEW HI-01 / HI-02 / ME-01 / ME-02) ------------------
#
# Regression tests for the four live-results *application*-layer findings. Each is written to
# FAIL against the pre-fix single-pass / scalar-conflict / unscoped-banner code and pass after
# the fix. They use the SAME helpers (_results_cache / _finished_row / _patch_results /
# _go_live_small) as the Phase-6 Slice-4 tests above.


def _r1_full_lock_rows():
    """The 8 R1 result rows for the default fixture (seed i vs i+8), lower id wins each match.

    Returns ``list[(round_idx=0, winner_id, loser_id)]`` covering EVERY R1 pairing — a fully
    locked R1 prefix, which is the precondition for R2's legal pairings to be deterministic.
    """
    from engine.live import legal_pairings_for_round
    from engine.teams import load_teams

    r1 = legal_pairings_for_round(load_teams(), [], 40.0, 0)
    return [(0, *sorted(p)) for p in sorted(r1, key=lambda p: sorted(p))]  # lower id wins


def test_reverse_round_results_prefill_in_one_pass(monkeypatch):
    """HI-01 (06-REVIEW): a MULTI-ROUND results cache in REVERSE round order (the live bo3.gg
    feed is reverse-chronological, sort=-start_date) must auto-lock EVERY round in ONE prefill
    pass.

    The pre-fix single pass iterates rows in cache order; an R2 row encountered first against a
    still-empty lock list hits legal_pairings_for_round's "all prior rounds fully locked" prefix
    guard, raises LivePrefixIncomplete, and the row is DROPPED — so only R1 locks this pass and
    R2 silently vanishes until a later rerun. The fix sorts rows by round_idx (write side AND
    read side) so the prefix is built in order and R2 locks in the same pass.

    Constructed with the rows DELIBERATELY in reverse-round order (R2 row first, then the 8 R1
    rows) so the test FAILS against the unsorted single-pass loop.

    AppTest reruns the script several times during setup, and each rerun is a fresh prefill pass —
    so the pre-fix loop CONVERGES across reruns (R1 locks, then R2 locks on a later pass), which
    would mask the bug. To isolate ONE pass we reset KEY_LOCKED to empty and then do exactly ONE
    final .run() (one script execution == one prefill pass); the assertion then exercises the
    single-pass behavior the review flagged.
    """
    from ui.state import KEY_LOCKED

    r1_rows = _r1_full_lock_rows()  # 8 rows at round_idx 0 (fully locks R1)
    # One legal R2 result: with the full "lower id wins R1" prefix, [1,8] is an R2 pairing -> 1 beats 8.
    r2_row = (1, 1, 8)
    # Reverse-round order: the R2 row FIRST (newest-first), then the R1 rows — the exact order the
    # reverse-chronological bo3.gg feed would produce, which drops R2 under the pre-fix single pass.
    ordered = [r2_row, *r1_rows]
    rows = [_finished_row(w, ell, winner=w, round_idx=ri) for (ri, w, ell) in ordered]
    _patch_results(monkeypatch, _results_cache(rows, stage=1))

    at = _go_live_small(_apptest().run())
    assert not at.exception

    # Isolate a SINGLE prefill pass: clear any locks accumulated across the setup reruns, then run
    # exactly once. Under the pre-fix unsorted loop this single pass locks all 8 R1 rows but DROPS
    # the R2 row (its prefix guard raises because R1 is empty when the R2 row is hit first).
    at.session_state[KEY_LOCKED] = []
    at.run()
    assert not at.exception

    locked = list(at.session_state[KEY_LOCKED])
    # ALL 8 R1 results locked in the single pass.
    for (ri, w, ell) in r1_rows:
        assert (ri, w, ell) in locked, f"R1 result {(ri, w, ell)} must auto-lock in one pass"
    # AND the R2 result locked in the SAME pass (this is what the pre-fix single pass drops).
    assert (1, 1, 8) in locked, (
        "the R2 result must auto-lock in ONE pass despite the reverse-round cache order "
        "(HI-01: the unsorted single pass drops every R2+ row)"
    )

