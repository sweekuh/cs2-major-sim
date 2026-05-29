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
from ui.cache import freeze_locked, freeze_ratings, run_mc_cached
from ui.render import ci_bar_html
from ui.state import (
    BAD_RATING_MSG,
    DEFAULT_MODE,
    FIXED_SEED,
    KEY_MC_CACHE,
    KEY_RATINGS_EDITOR,
    KEY_RUN_BUTTON,
    KEY_S_SLIDER,
    MAX_N,
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

# --- Header strip (mode toggle is a plan-02 shell; Pre-stage is the default) -------------
st.title("Cologne 2026 Swiss Monte Carlo")
mode = DEFAULT_MODE  # Live toggle + reorder lands in plan 02; default Pre-stage on load.
st.caption(
    "Pre-stage — per-team P(advance) / P(3-0) / P(0-3) from the proven engine. "
    "First sim needs no API key."
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
        key="N_input",
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


# --- Main column: four interaction states (loading / empty / error / success) ------------
with main:
    st.subheader("Per-team probabilities")

    if run_clicked:
        offenders = validate_ratings(edited)
        if offenders:
            # ERROR state (UI-05): block Run, engine NEVER called.
            st.error(BAD_RATING_MSG)
        else:
            ratings = {r["seed"]: float(r["rating"]) for r in edited}
            locked: dict = {}  # Phase 4 fills this; the key shape is final now.
            ratings_key = freeze_ratings(ratings)
            locked_key = freeze_locked(locked)
            cache_key = (ratings_key, S, int(N), locked_key)
            cache = st.session_state[KEY_MC_CACHE]

            if cache_key in cache:
                # CACHE HIT: serve the stored Result, no recompute (single compute per key).
                result = cache[cache_key]
            else:
                # CACHE MISS: LOADING state — drive the bar over the generator, compute once.
                result = _drive_progress(ratings, S, int(N), locked)
                cache[cache_key] = result
                # Also prime the cross-session @st.cache_data memo so an identical input in a
                # later session is instant (it recomputes once here; in-session hits use the
                # session_state dict above — Pattern 2 option B, single in-session compute).
                run_mc_cached(ratings_key, S, int(N), locked_key)

            # SUCCESS state: per-team rows sorted by P(advance), number + inline CI bar.
            p_adv = result.p_advance()
            p_30 = result.p_30()
            p_03 = result.p_03()
            st.caption(f"{int(N) // 1000}k sims · seed {FIXED_SEED}")

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
    else:
        # EMPTY (pre-run) state (UI-05): never blank, never 0% — show dashes.
        st.info("Set ratings, then Run.")
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
