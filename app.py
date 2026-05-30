"""Cologne 2026 Swiss MC — Streamlit entry (Phase 2 plan 01: controls + Run + probs slice).

The thinnest runnable end-to-end UI: a fresh clone runs ``uv run streamlit run app.py``,
clicks Run with the shipped default ratings (no API key, no editing — DX-01/DX-03), watches
a real progress bar driven by the engine generator, and sees per-team
P(advance)/P(3-0)/P(0-3) with inline Wilson CI bars.

This slice owns the two correctness seams:
  - the ``locked``-keyed cache boundary (freeze_locked, Phase 2x4 — UI-02), and
  - the no-re-chunk progress loop over run_mc_progressive (Phase 1x2 — UI-03).
plus rating validation that blocks Run BEFORE the engine is ever called (UI-05).

The two-mode toggle / bracket / ballot panels are plan 02/03 — this stays the controls +
run + probs slice.

AppTest invariant (DX-03): the module body builds widgets (AppTest runs that), but performs
NO import-time work that breaks ``AppTest.from_file("app.py")`` — no network, no engine call
at import, no ``if __name__ == "__main__"`` side effects. The engine runs only on a Run click.
"""

from __future__ import annotations

import html

import streamlit as st

from engine.live import (
    classify_pick,
    derive_bracket,
    legal_pairings_for_round,
    pge5_delta,
    validate_lock,
)
from engine.montecarlo import run_mc_progressive
from engine.optimizer import build_outcome_matrices
from engine.teams import load_teams
from ui.cache import freeze_locked, freeze_ratings, optimize_cached
from ui.render import (
    ballot_columns,
    bracket_columns_html,
    ci_bar_html,
    correlated_pick_warning_text,
    fmt_pct,
    hero_number_html,
    status_badge_html,
)
from ui.state import (
    BAD_RATING_MSG,
    DEFAULT_MODE,
    FIXED_SEED,
    KEY_LIVE_ANCHOR,
    KEY_LOCKED,
    KEY_MC_CACHE,
    KEY_MODE,
    KEY_N_INPUT,
    KEY_PENDING_LOCK,
    KEY_RATINGS_EDITOR,
    KEY_RUN_BUTTON,
    KEY_S_SLIDER,
    KEY_SEEDS_CONFIRMED,
    MAX_N,
    Mode,
    TRUST_BADGE_CAVEATED,
    TRUST_BADGE_VALIDATED,
    add_lock,
    locked_dict,
    locks_for_round,
    odds_key_present,
    read_seeds_confirmed,
    remove_last_lock,
    trust_badge_state,
    validate_ratings,
)

# Status hues — colorblind-safe, NEVER red/green (UI-06). Used for the CI-bar fill.
HUE_ADVANCE = "#3B82F6"  # blue
EM_DASH = "—"  # — : empty-state placeholder for probs (never "0%")

st.set_page_config(page_title="Cologne 2026 Swiss MC", layout="wide")

# session_state init (Pattern 2 option B): a dict keyed on (ratings_key, S, N, locked_key)
# gives single-compute-per-unique-key AND a real progress bar, surviving reruns in-session.
# Bounded: each cached Result retains the full per-sim sample (MC-04, ~N records), so an
# unbounded dict would balloon RAM under repeated event-day re-runs / slider drags.
MAX_CACHE_ENTRIES = 8
if KEY_MC_CACHE not in st.session_state:
    st.session_state[KEY_MC_CACHE] = {}

teams = load_teams()  # DX-01 zero-config: data/stage1.json (or in-code default), no API key
by_seed = {t.seed: t for t in teams}

# --- Header strip + two-mode toggle (UI-01) ----------------------------------------------
st.title("Cologne 2026 Swiss Monte Carlo")


def _render_header_strip() -> None:
    """Persistent header strip rendered in BOTH modes, above the body (UI-SPEC Header strip).

    Three honest-by-construction pieces:
      1. Trust badge (UI-07): the EXACT caveated string while BACKTEST_PASSED is False — never
         a green ✓ / Budapest claim. Validated state needs BOTH the backtest AND seeds (Pitfall 6).
      2. INFERRED-seed banner (DX-02): a persistent ``st.warning`` + a field-by-field reconcile
         area (seed→team rows to eyeball vs the official list) + a ``seeds confirmed`` toggle that
         dismisses it. The toggle is the gate the badge reads; seeded from data/stage1.json read-only.
      3. Fail-soft odds banner (ODDS-08): a one-line ``st.info`` when no ODDSPAPI_KEY is set —
         never crashes, never imports httpx/python-dotenv.
    """
    # Seed the seeds_confirmed session_state from the read-only JSON flag on first load only;
    # thereafter the in-session toggle owns it. Setting the key BEFORE the widget is created
    # makes it the toggle's initial value (Streamlit binds the widget to the existing key).
    if KEY_SEEDS_CONFIRMED not in st.session_state:
        st.session_state[KEY_SEEDS_CONFIRMED] = read_seeds_confirmed()

    seeds_confirmed = bool(st.session_state.get(KEY_SEEDS_CONFIRMED, False))

    # 1. Trust badge — caveated while BACKTEST_PASSED is False (UI-07, Pitfall 6: both, not one).
    if trust_badge_state(seeds_confirmed) == "validated":
        # Green success box with its OWN consistent wording — never the caveated
        # "pending seed data" string (WR-02). Only reachable once GATE-01 lands AND seeds
        # are confirmed. No Budapest claim (CLAUDE.md trust-badge rule).
        st.success(TRUST_BADGE_VALIDATED)
    else:
        # Caveated: render the EXACT string as a neutral caption — no green ✓, no Budapest claim.
        st.caption(TRUST_BADGE_CAVEATED)

    # 2. INFERRED-seed banner + reconcile area + confirm toggle (persists until confirmed).
    if not seeds_confirmed:
        st.warning(
            "⚠ Seeds are INFERRED — verify vs the official seed list before trusting outputs."
        )
        with st.expander("Reconcile seeds vs the official list", expanded=False):
            st.caption(
                "Eyeball each seed→team against the official Cologne 2026 seed list, then "
                "flip 'seeds confirmed'. A wrong seed silently corrupts every probability."
            )
            rh = st.columns([1, 4])
            rh[0].markdown("**Seed**")
            rh[1].markdown("**Team**")
            for t in sorted(teams, key=lambda x: x.seed):
                rc = st.columns([1, 4])
                rc[0].markdown(f"{t.seed}")
                rc[1].markdown(t.name)
    # The confirm toggle is a positive confirmation (NOT destructive — no red; protects the
    # never-red/green rule). On True it dismisses the banner and is the gate the badge reads.
    st.toggle(
        "Seeds confirmed (dismiss the INFERRED-seed banner)",
        key=KEY_SEEDS_CONFIRMED,
    )

    # 3. Fail-soft odds-off info banner (ODDS-08 seam) — one line, never a crash, no Phase-5 import.
    if not odds_key_present():
        st.info("live odds off (no ODDSPAPI_KEY) — using manual ratings")


_render_header_strip()

# Pre-stage / Live mode toggle. segmented_control is the UI-SPEC default; the active segment
# is the reserved accent (Streamlit applies primaryColor automatically). Bound to ui.state.Mode.
# Default on first load = Pre-stage (a fresh user has no locks; Live would dead-end empty).
_mode_label = st.segmented_control(
    "Mode",
    options=[Mode.PRE_STAGE.value, Mode.LIVE.value],
    default=DEFAULT_MODE.value,
    key=KEY_MODE,
    label_visibility="collapsed",
)
mode = Mode(_mode_label) if _mode_label else DEFAULT_MODE

if mode is Mode.PRE_STAGE:
    st.caption(
        "Pre-stage — per-team P(advance) / P(3-0) / P(0-3) from the proven engine. "
        "First sim needs no API key."
    )
else:
    st.caption(
        "Live — lock results round-by-round and re-sim from here. "
        "Each pick shows live / dead / secured with a P(≥5)-from-here delta."
    )

controls, main = st.columns([1, 3], gap="medium")

# --- Controls column ---------------------------------------------------------------------
with controls:
    st.subheader("Ratings")
    rows = [{"seed": t.seed, "team": t.name, "rating": t.rating} for t in teams]
    edited = st.data_editor(
        rows,
        num_rows="fixed",  # cannot add/delete the 16 teams
        disabled=["seed", "team"],  # only rating is editable
        column_config={
            "seed": st.column_config.NumberColumn("Seed", disabled=True),
            "team": st.column_config.TextColumn("Team", disabled=True),
            "rating": st.column_config.NumberColumn(
                "Rating", min_value=1, max_value=999, step=1, format="%d"
            ),
        },
        hide_index=True,
        key=KEY_RATINGS_EDITOR,
    )
    S = st.slider("Spread (S)", min_value=10, max_value=100, value=40, key=KEY_S_SLIDER)
    N = st.number_input(
        "Sims (N)",
        min_value=1000,
        max_value=MAX_N,  # cap mirrors the engine — absurd N can't hang the app (T-DOS)
        value=100_000,
        step=1000,
        key=KEY_N_INPUT,
    )
    run_clicked = st.button("Run ▶", key=KEY_RUN_BUTTON, type="primary")
    st.caption("~15s for 100k sims, no API key needed")


def _drive_progress(ratings: dict, S: float, N: int, locked: dict):
    """Cache-MISS path: iterate the FROZEN run_mc_progressive to drive st.progress.

    Each Partial(done, total, running_p_adv) advances the bar with a running sim counter
    (NEVER a blank spinner — UI-03). Do NOT override n_chunks (stays 20 — Phase 1x2
    reproducibility). Returns the final Result captured via StopIteration.value.
    """
    bar = st.progress(0.0, text="Simulating…")
    gen = run_mc_progressive(teams, ratings, S, N, locked, seed=FIXED_SEED)
    result = None
    try:
        while True:
            p = next(gen)
            frac = p.done / p.total
            bar.progress(frac, text=f"Simulating… {p.done:,} / {p.total:,}")
    except StopIteration as stop:
        result = stop.value
    bar.empty()
    return result


def _render_probs_table(result) -> None:
    """SUCCESS state: per-team rows sorted by P(advance), each cell = number + inline CI bar.

    UI-04: EVERY probability cell renders the number PLUS an always-visible inline Wilson CI
    mini-bar via ci_bar_html — never hover/expand-hidden. Reused for the Pre-stage probs and
    the Live delta-probs section (delta content is Phase 4; the render is shared now).
    """
    p_adv = result.p_advance()
    p_30 = result.p_30()
    p_03 = result.p_03()
    order = sorted(by_seed, key=lambda s: p_adv.get(s, 0.0), reverse=True)
    hdr = st.columns([3, 2, 2, 2])
    hdr[0].markdown("**Team**")
    hdr[1].markdown("**P(advance)**")
    hdr[2].markdown("**P(3-0)**")
    hdr[3].markdown("**P(0-3)**")
    for seed in order:
        t = by_seed[seed]
        c = st.columns([3, 2, 2, 2])
        c[0].markdown(f"{t.name}")
        lo_a, hi_a = result.band_advance.get(seed, (0.0, 0.0))
        lo_3, hi_3 = result.band_30.get(seed, (0.0, 0.0))
        lo_0, hi_0 = result.band_03.get(seed, (0.0, 0.0))
        c[1].markdown(
            ci_bar_html(p_adv.get(seed, 0.0), lo_a, hi_a, HUE_ADVANCE),
            unsafe_allow_html=True,
        )
        c[2].markdown(
            ci_bar_html(p_30.get(seed, 0.0), lo_3, hi_3, HUE_ADVANCE),
            unsafe_allow_html=True,
        )
        c[3].markdown(
            ci_bar_html(p_03.get(seed, 0.0), lo_0, hi_0, HUE_ADVANCE),
            unsafe_allow_html=True,
        )


def _render_probs_empty() -> None:
    """EMPTY (pre-run) probs state (UI-05): never blank, never 0% — dashes under each team."""
    st.caption(
        f"First sim needs no API key — ~15s for 100k tournaments. "
        f"Per-team probs show {EM_DASH} until you Run."
    )
    hdr = st.columns([3, 2, 2, 2])
    hdr[0].markdown("**Team**")
    hdr[1].markdown("**P(advance)**")
    hdr[2].markdown("**P(3-0)**")
    hdr[3].markdown("**P(0-3)**")
    for t in teams:
        c = st.columns([3, 2, 2, 2])
        c[0].markdown(t.name)
        c[1].markdown(EM_DASH)
        c[2].markdown(EM_DASH)
        c[3].markdown(EM_DASH)


def _render_bracket() -> None:
    """Bracket as a COLLAPSED expander — seeded Round 1 `(seed, seed+8)` table only (UI-SPEC
    bracket empty state). Record-bucket columns + locked/simulated styling are Phase 4."""
    with st.expander("Bracket — seeded Round 1", expanded=False):
        st.caption("Round 1 pairings (seed vs seed+8). Record buckets fill in Phase 4.")
        bh = st.columns([1, 3, 3])
        bh[0].markdown("**Match**")
        bh[1].markdown("**Team A**")
        bh[2].markdown("**Team B**")
        for i in range(1, 9):
            a = by_seed.get(i)
            b = by_seed.get(i + 8)
            row = st.columns([1, 3, 3])
            row[0].markdown(f"R1-{i}")
            row[1].markdown(a.name if a else EM_DASH)
            row[2].markdown(b.name if b else EM_DASH)


def _cache_key_for(ratings: dict, locked: dict):
    """The ``(ratings_key, S, int(N), locked_key)`` cache tuple for a given ratings+locked."""
    return (freeze_ratings(ratings), S, int(N), freeze_locked(locked))


def _compute_or_serve(ratings: dict, locked: dict):
    """Get-or-compute the MC Result for ``(ratings, S, N, locked)`` — returns (result, cache_key).

    Single source for BOTH the current Run and the LIVE empty-locked anchor compute. A cache
    HIT serves the stored Result (no recompute); a MISS drives the progress bar over
    run_mc_progressive ONCE and memoizes it. Each DISTINCT key computes at most once, so the
    CR-01 single-compute guard stays green even when LIVE mode also computes the empty-locked
    pre_key (a different key from the locked run).
    """
    cache_key = _cache_key_for(ratings, locked)
    cache = st.session_state[KEY_MC_CACHE]
    if cache_key in cache:
        return cache[cache_key], cache_key
    result = _drive_progress(ratings, S, int(N), locked)
    cache[cache_key] = result
    # Evict oldest entries so the retained per-sim samples can't grow unbounded across
    # a long session of re-runs (insertion-ordered dict → pop oldest first).
    while len(cache) > MAX_CACHE_ENTRIES:
        cache.pop(next(iter(cache)))
    return result, cache_key


def _run_or_serve():
    """Validate + dispatch the engine (cache hit / miss). Returns (result, error_msg, cache_key).

    Shared by both modes' top section. On a bad rating returns (None, BAD_RATING_MSG, None)
    and the engine is NEVER called (UI-05). On no click returns (None, None, None) — the EMPTY
    state. ``cache_key`` is the ``(ratings_key, S, N, locked_key)`` tuple so the optimizer can
    memoize on the SAME key (Phase 3, OPT-04) without re-running the MC.
    """
    if not run_clicked:
        return None, None, None
    offenders = validate_ratings(edited)
    if offenders:
        # ERROR state (UI-05): block Run, engine NEVER called.
        return None, BAD_RATING_MSG, None
    ratings = {r["seed"]: float(r["rating"]) for r in edited}
    # Phase 4 fill point: the engine ``locked`` dict is DERIVED from KEY_LOCKED (the ordered
    # lock list) via the pure projection, then flows through the UNCHANGED freeze_locked ->
    # locked_key -> cache_key path so a non-empty lock changes the key and re-sims (RESIM-01).
    # In PRE_STAGE / first-run the list is empty -> locked == {} (no behavior change).
    locked = locked_dict(st.session_state.get(KEY_LOCKED, []))
    result, cache_key = _compute_or_serve(ratings, locked)
    return result, None, cache_key


def _live_anchor(ratings: dict, ids: list[int]):
    """The FIXED anchor ballot (Ballot B) for the LIVE delta + status chips (D5/BLOCKER 1).

    Captured ONCE, from the EMPTY-locked pre_key Result, and stored in KEY_LIVE_ANCHOR so it
    NEVER re-optimizes per round (the arrow would be meaningless otherwise). Returns
    ``(anchor_ballot, pre_lock_result)``:
      pre_key       = (freeze_ratings(ratings), S, int(N), freeze_locked({}))
      pre_lock_result = mc_cache[pre_key] if present else ONE explicit compute on pre_key
                        (memoized — a DISTINCT key from the locked run, so CR-01 stays green)
      anchor        = optimize_cached(pre_lock_result, *pre_key).recommended  (Ballot B)

    The anchor is re-served from session_state on later reruns; only a first-ever capture runs
    the optimizer. ``pre_lock_result`` is returned so ``before`` is read off the pre_key sample.
    """
    pre_lock_result, pre_key = _compute_or_serve(ratings, {})  # empty-locked = pre_key
    anchor = st.session_state.get(KEY_LIVE_ANCHOR)
    if anchor is None:
        anchor = optimize_cached(pre_lock_result, *pre_key).recommended
        st.session_state[KEY_LIVE_ANCHOR] = anchor
    return anchor, pre_lock_result


def _render_live_hero(post_lock_result, anchor, pre_lock_result, ids: list[int]) -> None:
    """LIVE 'P(>=5) from here' delta hero: ``before% -> after%`` on the FIXED anchor (RESIM-02).

    Two p_ge5 calls on the SAME anchor ballot against the pre-lock and post-lock samples
    (engine.live.pge5_delta). ``before`` reads the pre_key Result's OWN sample (not the
    post-lock result with a mismatched key — BLOCKER 1). Rendered as a hero arrow in the
    reserved accent; no placeholder caption.
    """
    before, after = pge5_delta(anchor, pre_lock_result, post_lock_result, ids)
    st.markdown("**P(>=5) from here**")
    st.markdown(
        f"{hero_number_html(before)}"
        '<span style="font-size:24px;margin:0 8px;opacity:0.6">&rarr;</span>'
        f"{hero_number_html(after)}",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Your locked-in ballot's coin odds, before -> after this stage's locks "
        f"({fmt_pct(before)} -> {fmt_pct(after)})."
    )


def _open_round_idx(locked_results: list[tuple[int, int, int]], name_of: dict[int, str]) -> int:
    """The lowest round index whose prior rounds are ALL fully entered — the only round whose
    controls may render (the live-mode invariant, BLOCKER 2 / T-04-PREFIX).

    Round R is "open" once round R-1 is fully locked: the count of locks at R-1 equals the
    number of legal pairings the engine generates for R-1. R1 (idx 0) is always open. We probe
    rounds upward via legal_pairings_for_round (which only succeeds on a fully-locked prefix),
    so legal_pairings_for_round is never CALLED on a partial prefix from the controls path.
    """
    r = 0
    while True:
        try:
            pairings = legal_pairings_for_round(teams, locked_results, S, r)
        except Exception:
            # The prefix for round r is not fully locked (or the stage has no round r) — the
            # previous round is the open one. Defensive: never raise into the UI.
            return r
        entered = len(locks_for_round(locked_results, r))
        if entered < len(pairings):
            return r  # round r itself is the open (partially/empty) round
        r += 1


def _commit_lock(pending: tuple[int, int, int]) -> None:
    """Validate ``(round_idx, winner_id, loser_id)`` and commit it, or show the reason (D3/RESIM-03).

    Runs engine.live.validate_lock against the round's legal pairings; on a reason -> st.error
    and DO NOT mutate KEY_LOCKED or the cache; else append via add_lock. Keyed on team id.
    """
    round_idx, winner_id, loser_id = pending
    locked_results = st.session_state.get(KEY_LOCKED, [])
    try:
        legal = legal_pairings_for_round(teams, locked_results, S, round_idx)
    except Exception as exc:  # incomplete prefix — should not happen from the gated controls
        st.error(str(exc))
        return
    reason = validate_lock(
        (winner_id, loser_id), round_idx, locked_results, teams, legal
    )
    if reason is not None:
        # Illegal lock — block it. KEY_LOCKED + mc_cache stay untouched (RESIM-03).
        st.error(reason)
    else:
        st.session_state[KEY_LOCKED] = add_lock(
            locked_results, round_idx, winner_id, loser_id
        )


def _render_lock_controls(name_of: dict[int, str]) -> None:
    """Round-by-round winner pickers writing KEY_LOCKED (D1/RESIM-01); round R gated on R-1.

    Renders the open round's legal pairings (each a winner radio) + a 'Lock result' button and
    an 'Undo last lock'. Round-R controls appear ONLY once R-1 is fully entered, so
    legal_pairings_for_round is never called on a partial prefix (BLOCKER 2). All keyed on id.

    Commit contract (testable): on a 'Lock result' click the handler commits KEY_PENDING_LOCK
    (the staged selection). The radio selection re-stages KEY_PENDING_LOCK on every render, so
    the normal UI path commits the user's pick; a test may inject KEY_PENDING_LOCK directly to
    exercise the validate_lock gate (the button click does NOT overwrite an out-of-round pick).
    """
    locked_results = st.session_state.get(KEY_LOCKED, [])
    round_idx = _open_round_idx(locked_results, name_of)
    try:
        legal = legal_pairings_for_round(teams, locked_results, S, round_idx)
    except Exception:
        legal = set()

    st.markdown(f"**Lock Round {round_idx + 1} results**")
    already = {frozenset((w, ell)) for (r, w, ell) in locked_results if r == round_idx}
    open_pairs = sorted(
        (p for p in legal if p not in already), key=lambda p: sorted(p)
    )
    if not open_pairs:
        st.caption("All matches this round are entered — the next round's pairings unlock.")
    for pair in open_pairs:
        a_id, b_id = sorted(pair)
        st.radio(
            f"{name_of.get(a_id, a_id)} vs {name_of.get(b_id, b_id)} — winner",
            options=[a_id, b_id],
            format_func=lambda tid: name_of.get(tid, str(tid)),
            key=f"live_winner_r{round_idx}_{a_id}_{b_id}",
            horizontal=True,
        )

    lock_clicked = st.button("Lock result", key="live_lock_btn")
    if lock_clicked:
        # Prefer an already-staged/injected pending lock (a test injects KEY_PENDING_LOCK to
        # exercise the validate_lock gate). Otherwise derive the pick from the FIRST open
        # pairing's radio (the normal UI path: one match locked per click).
        pending = st.session_state.get(KEY_PENDING_LOCK)
        if pending is None and open_pairs:
            a_id, b_id = sorted(open_pairs[0])
            winner = st.session_state.get(f"live_winner_r{round_idx}_{a_id}_{b_id}", a_id)
            loser = b_id if winner == a_id else a_id
            pending = (round_idx, winner, loser)
        if pending is not None:
            _commit_lock(pending)
        st.session_state[KEY_PENDING_LOCK] = None
    if locked_results:
        if st.button("Undo last lock", key="live_undo_btn"):
            st.session_state[KEY_LOCKED] = remove_last_lock(locked_results)


def _render_status_chips(anchor, post_lock_result, ids: list[int], name_of: dict[int, str]) -> None:
    """Per-pick live/dead/secured chips on the anchor ballot, by bucket (D4/RESIM-02/UI-06).

    Build the outcome matrices ONCE off the post-lock sample, then walk the anchor's picks WITH
    their bucket label and classify each (team, bucket) via engine.live.classify_pick -> a
    STATUS key -> the existing status_badge_html (blue/amber + glyph + label, never red/green).
    """
    matrices = build_outcome_matrices(post_lock_result.sample, ids)
    buckets = (
        (anchor.picks_30, "picks_30", "3-0"),
        (anchor.picks_adv, "picks_adv", "Advance"),
        (anchor.picks_03, "picks_03", "0-3"),
    )
    for picks, bucket_label, human in buckets:
        st.markdown(f"*{human}*")
        for team_id in picks:
            state = classify_pick(team_id, bucket_label, matrices)
            name = html.escape(str(name_of.get(team_id, team_id)))
            st.markdown(
                f"{name} &nbsp; {status_badge_html(state)}",
                unsafe_allow_html=True,
            )


def _render_bracket_live(name_of: dict[int, str]) -> None:
    """LIVE bracket: record-bucket COLUMNS from the engine replay (D6/RESIM-04), never a tree.

    Derives a BracketView by replaying simulate_stage with the current locks and renders it as
    solid-locked / faint-simulated record-bucket columns via bracket_columns_html.
    """
    locked = locked_dict(st.session_state.get(KEY_LOCKED, []))
    view = derive_bracket(teams, locked, S)
    with st.expander("Bracket — record buckets", expanded=True):
        st.markdown(bracket_columns_html(view, name_of), unsafe_allow_html=True)


def _render_ballot_panel(result, cache_key) -> None:
    """PRE-STAGE recommended-ballot panel (OPT-03/04/05): the P(>=5) hero + Ballot A vs B
    side by side with differing picks highlighted + the correlated-0-3-in-R1 warning.

    The optimizer is memoized on the SAME cache key as the MC (optimize_cached) and scores
    the stored sample — it never re-runs the MC (ROADMAP SC4).
    """
    opt = optimize_cached(result, *cache_key)

    # Hero = the recommended (Ballot B) P(>=5) — the true coin odds (OPT-04).
    st.markdown("**P(>=5) — recommended ballot (B)**")
    st.markdown(hero_number_html(opt.recommended_pge5), unsafe_allow_html=True)
    st.caption(
        f"P(>=5): A {fmt_pct(opt.pge5_a)} · B {fmt_pct(opt.pge5_b)}  |  "
        f"E[correct]: A {opt.e_correct_a:.2f} · B {opt.e_correct_b:.2f}"
    )

    # Ballot A vs B side by side, differing picks marked (OPT-03).
    name_of = {t.id: t.name for t in teams}

    # Correlated-pick warning (OPT-05) — st.warning is natively amber (colorblind-safe).
    # opt.warning carries team IDs (optimizer space), so look names up by id via name_of —
    # NOT the seed-keyed by_seed (id == seed only for the default fixture; don't couple to it).
    if opt.warning is not None:
        a_id, b_id = opt.warning
        st.warning(
            correlated_pick_warning_text(name_of[a_id], name_of[b_id])
        )

    st.markdown(
        ballot_columns(name_of, opt.ballot_a, opt.ballot_b, opt.diff),
        unsafe_allow_html=True,
    )
    if opt.diff:
        st.caption(
            "An asterisk (\\*) marks a pick where A and B disagree — "
            "that difference is the insight."
        )
    else:
        st.caption("Ballot A and Ballot B agree on all 10 picks.")


# --- Main column: mode-conditional ordering (UI-01) --------------------------------------
with main:
    result, error_msg, cache_key = _run_or_serve()
    if result is not None:
        st.caption(f"{int(N) // 1000}k sims · seed {FIXED_SEED}")

    if mode is Mode.PRE_STAGE:
        # PRE-STAGE order: (1) recommended ballot (hero P(>=5) + A vs B + warning),
        # (2) per-team probs, (3) collapsed bracket.
        st.subheader("Recommended ballot")
        if error_msg:
            st.error(error_msg)
        elif result is None:
            st.info("Run to see the recommended ballot.")
        else:
            _render_ballot_panel(result, cache_key)

        st.subheader("Per-team probabilities")
        if error_msg:
            pass  # error already shown above; probs stay empty
        elif result is None:
            st.info("Set ratings, then Run.")
            _render_probs_empty()
        else:
            _render_probs_table(result)

        _render_bracket()
    else:
        # LIVE order: (1) round-by-round lock controls, (2) locked-pick status + from-here
        # delta hero + status legend, (3) delta-probs area, (4) record-bucket bracket.
        # name_of / ids are built ONCE here (NOT reused from _render_ballot_panel's local).
        name_of = {t.id: t.name for t in teams}
        ids = [t.id for t in teams]

        st.subheader("Lock results")
        _render_lock_controls(name_of)

        st.subheader("Your picks — status")
        if error_msg:
            st.error(error_msg)
        elif result is None:
            st.info("Lock a result to go live.")
            # Status legend (UI-06): glyph + label + colorblind-safe hue, never red/green.
            legend = " &nbsp; ".join(
                status_badge_html(state) for state in ("live", "eliminated", "advanced")
            )
            st.markdown(legend, unsafe_allow_html=True)
        else:
            # The current run's ratings (same expression as _run_or_serve — keyed by seed==id).
            ratings = {r["seed"]: float(r["rating"]) for r in edited}
            anchor, pre_lock_result = _live_anchor(ratings, ids)
            _render_live_hero(result, anchor, pre_lock_result, ids)
            legend = " &nbsp; ".join(
                status_badge_html(state) for state in ("live", "eliminated", "advanced")
            )
            st.markdown(legend, unsafe_allow_html=True)
            _render_status_chips(anchor, result, ids, name_of)

        st.subheader("Delta probabilities")
        if error_msg:
            pass
        elif result is None:
            st.caption("Lock a result, then Run to see how each team's odds move.")
            _render_probs_empty()
        else:
            _render_probs_table(result)

        _render_bracket_live(name_of)
