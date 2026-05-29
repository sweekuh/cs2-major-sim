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

import streamlit as st

from engine.montecarlo import run_mc_progressive
from engine.teams import load_teams
from ui.cache import freeze_locked, freeze_ratings
from ui.render import ci_bar_html, hero_number_html, status_badge_html
from ui.state import (
    BAD_RATING_MSG,
    DEFAULT_MODE,
    FIXED_SEED,
    KEY_MC_CACHE,
    KEY_MODE,
    KEY_N_INPUT,
    KEY_RATINGS_EDITOR,
    KEY_RUN_BUTTON,
    KEY_S_SLIDER,
    KEY_SEEDS_CONFIRMED,
    MAX_N,
    Mode,
    TRUST_BADGE_CAVEATED,
    TRUST_BADGE_VALIDATED,
    odds_key_present,
    read_seeds_confirmed,
    trust_badge_state,
    validate_ratings,
)

# Status hues — colorblind-safe, NEVER red/green (UI-06). Used for the CI-bar fill.
HUE_ADVANCE = "#3B82F6"  # blue
EM_DASH = "—"  # — : empty-state placeholder for probs (never "0%")

st.set_page_config(page_title="Cologne 2026 Swiss MC", layout="wide")

# session_state init (Pattern 2 option B): a dict keyed on (ratings_key, S, N, locked_key)
# gives single-compute-per-unique-key AND a real progress bar, surviving reruns in-session.
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
        "(Result locking lands in Phase 4.)"
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


def _run_or_serve():
    """Validate + dispatch the engine (cache hit / miss). Returns (result, error_msg).

    Shared by both modes' top section. On a bad rating returns (None, BAD_RATING_MSG) and the
    engine is NEVER called (UI-05). On no click returns (None, None) — the EMPTY state.
    """
    if not run_clicked:
        return None, None
    offenders = validate_ratings(edited)
    if offenders:
        return None, BAD_RATING_MSG  # ERROR state (UI-05): block Run, engine NEVER called.
    ratings = {r["seed"]: float(r["rating"]) for r in edited}
    locked: dict = {}  # Phase 4 fills this; the key shape is final now.
    ratings_key = freeze_ratings(ratings)
    locked_key = freeze_locked(locked)
    cache_key = (ratings_key, S, int(N), locked_key)
    cache = st.session_state[KEY_MC_CACHE]
    if cache_key in cache:
        # CACHE HIT: serve the stored Result, no recompute (single compute per key).
        return cache[cache_key], None
    # CACHE MISS: LOADING state — drive the bar over the generator, compute ONCE.
    # In-session deduplication via the session_state cache (above) is sufficient for Phase 2:
    # a unique input tuple computes the MC exactly once. The earlier cross-session
    # @st.cache_data priming call was removed because it re-ran the full N-sim engine a
    # second time (result discarded), doubling first-Run wall-clock with no user feedback
    # (CR-01). Cross-session reuse can be wired correctly in a later phase if needed.
    result = _drive_progress(ratings, S, int(N), locked)
    cache[cache_key] = result
    return result, None


def _hero_slot(result, label: str) -> None:
    """Render the one display-size hero number (UI-SPEC Typography/Color — accent reserved).

    Phase 3 (Pre-stage P(>=5)) / Phase 4 (Live P(>=5)-from-here) fill the real ballot content;
    this plan owns the hero SLOT + renderer. With a result we show a placeholder hero number
    (top-team P(advance) stand-in) so the 28px monospace accent slot is real now.
    """
    if result is None:
        return
    p_adv = result.p_advance()
    top = max(p_adv.values()) if p_adv else 0.0
    st.markdown(f"**{label}**")
    st.markdown(hero_number_html(top), unsafe_allow_html=True)
    st.caption("Placeholder hero — Phase 3/4 fills the optimal-ballot P(>=5).")


# --- Main column: mode-conditional ordering (UI-01) --------------------------------------
with main:
    result, error_msg = _run_or_serve()
    if result is not None:
        st.caption(f"{int(N) // 1000}k sims · seed {FIXED_SEED}")

    if mode is Mode.PRE_STAGE:
        # PRE-STAGE order: (1) recommended-ballot placeholder + hero, (2) per-team probs,
        # (3) collapsed bracket.
        st.subheader("Recommended ballot")
        if error_msg:
            st.error(error_msg)
        elif result is None:
            st.info("Run to see the recommended ballot.")
        else:
            _hero_slot(result, "P(>=5) — recommended ballot")

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
        # LIVE order: (1) locked-pick status placeholder + hero + status legend,
        # (2) delta-probs area, (3) collapsed bracket.
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
            _hero_slot(result, "P(>=5) from here")
            legend = " &nbsp; ".join(
                status_badge_html(state) for state in ("live", "eliminated", "advanced")
            )
            st.markdown(legend, unsafe_allow_html=True)

        st.subheader("Delta probabilities")
        if error_msg:
            pass
        elif result is None:
            st.caption("Lock a result to see how each team's odds move (Phase 4).")
            _render_probs_empty()
        else:
            _render_probs_table(result)

        _render_bracket()
