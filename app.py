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
from datetime import datetime, timezone

import streamlit as st

from engine.backsolve import fit_ratings, invert_series
from engine.live import (
    classify_pick,
    derive_bracket,
    legal_pairings_for_round,
    pge5_delta,
    validate_lock,
)
from engine.montecarlo import run_mc_progressive
from engine.optimizer import build_outcome_matrices
from engine.teams import load_stage
from ui.cache import _path_for_stage, freeze_locked, freeze_ratings, optimize_cached
from ui.odds_loader import load_odds_cache  # json-only read seam (NO httpx/dotenv — DX-01)
from ui.results_loader import load_results_cache  # json-only results read seam (NO httpx — RES-04)
from ui.render import (
    ballot_columns,
    bracket_columns_html,
    ci_bar_html,
    ci_bar_two_tone_html,
    correlated_pick_warning_text,
    delta_tag_html,
    fmt_age,
    fmt_pct,
    hero_number_html,
    is_stale,
    priced_ids,
    provider_labels,
    source_spread,
    status_badge_html,
)
from ui.render import PROVIDER_LABELS
from ui.state import (
    BAD_RATING_MSG,
    DEFAULT_MODE,
    FIXED_SEED,
    KEY_LIVE_ANCHOR,
    KEY_LOCK_PROVENANCE,
    KEY_LOCKED,
    KEY_MC_CACHE,
    KEY_MODE,
    KEY_N_INPUT,
    KEY_ODDS_OUTCOME,
    KEY_PENDING_LOCK,
    KEY_PENDING_RESULT_CONFLICT,
    KEY_RATINGS_EDITOR,
    KEY_RESULTS_OUTCOME,
    KEY_RUN_BUTTON,
    KEY_S_SLIDER,
    KEY_STAGE,
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
# Two-tone CI-bar legend (D2) — shown only on an odds-fed run (priced matches present). The faint
# flank is the across-draw epistemic spread; the solid core is the sampling band (UI-06: all blue).
TWO_TONE_LEGEND = "CI bars: solid = sampling band · faint = extra width from the books disagreeing."

st.set_page_config(page_title="Cologne 2026 Swiss MC", layout="wide")

# session_state init (Pattern 2 option B): a dict keyed on (ratings_key, S, N, locked_key)
# gives single-compute-per-unique-key AND a real progress bar, surviving reruns in-session.
# Bounded: each cached Result retains the full per-sim sample (MC-04, ~N records), so an
# unbounded dict would balloon RAM under repeated event-day re-runs / slider drags.
MAX_CACHE_ENTRIES = 8
if KEY_MC_CACHE not in st.session_state:
    st.session_state[KEY_MC_CACHE] = {}

# The active run's results-cache _meta.fetched_at, set by _prefill_results_into_locked() in the
# main block and folded into the run cache key via _combined_fetched_at (RES-02 re-sim re-fire). It
# is a module global (not session_state) because it is derived fresh every run from the read-only
# results cache — None until the pre-fill runs / when there is no results cache.
_RESULTS_FETCHED_AT = None

# Active stage (Phase 6, STG-04). The stage selector below WRITES KEY_STAGE; on first load it is
# not yet set, so default to "stage1" (the zero-config first-run stage — DX-01). On reruns the
# selected stage already lives in session_state, so the module globals below bind to it BEFORE the
# header/controls render. The globals are RE-BOUND once more right after the selector widget runs,
# so a same-run stage change takes effect for every downstream render path.
stage_id = st.session_state.get(KEY_STAGE, "stage1")
teams, _stage_cfg = load_stage(_path_for_stage(stage_id))  # DX-01 zero-config: Stage 1, no API key
by_seed = {t.seed: t for t in teams}

# --- Header strip + two-mode toggle (UI-01) ----------------------------------------------
# Hero (screenshot-facing): bold headline + one-line method, accent-tinted to the theme violet.
st.markdown(
    "<div style='font-size:2.0rem;font-weight:750;letter-spacing:-0.02em;line-height:1.15'>"
    "IEM&nbsp;Cologne&nbsp;2026 — Swiss&nbsp;Stage&nbsp;Predictions</div>"
    "<div style='color:#9aa4b2;font-size:0.98rem;margin:0.15rem 0 0.5rem'>"
    "Market-driven Monte&nbsp;Carlo · per-team P(advance)/P(3-0)/P(0-3) with confidence bands "
    "· optimal 2/6/2 Pick'Em ballot</div>",
    unsafe_allow_html=True,
)

# Friendly labels for the provider slugs the fetch job records in _meta.providers_present.
_PROVIDER_LABELS = {
    "oddspapi": "Pinnacle (OddsPapi)",
    "kalshi": "Kalshi",
    "polymarket": "Polymarket",
}


# Canonical stage_id (str) <-> stage number (int) mapping (Phase 6, RES-02 / T-06-12). The frozen
# results-cache schema stores _meta.stage as an INTEGER (1) while the app tracks stage_id as a STRING
# ("stage1"); a naive ``_meta.stage == stage_id`` is ``1 == "stage1"`` -> always False -> auto-prefill
# silently never fires. This ONE helper is the single source the filter uses on BOTH sides, and it
# matches scripts.fetch_results._stage_number EXACTLY (the fetcher writes _meta.stage via the same
# mapping) so the schema and the comparison can never drift into a second representation.
_STAGE_NUMBERS = {"stage1": 1, "stage2": 2, "stage3": 3, "playoffs": 4}


def _stage_int_for(stage_id: str) -> int:
    """Map a stage_id ('stage1'|'stage2'|'stage3'|'playoffs') -> its 1-based stage number (int).

    Raises ValueError on an unknown stage_id (a typo must fail loud, never silently mis-filter).
    Matches scripts.fetch_results._stage_number so the fetcher-written _meta.stage and this filter
    always agree — the ONE canonical reconciliation of the int-vs-str mismatch (T-06-12).
    """
    n = _STAGE_NUMBERS.get(stage_id)
    if n is None:
        raise ValueError(
            f"unknown stage_id {stage_id!r}; expected one of {sorted(_STAGE_NUMBERS)}"
        )
    return n


def _fmt_fetched(iso) -> str:
    """ISO-8601 UTC timestamp -> 'Jun 02, 04:49 UTC' (empty string on missing/malformed)."""
    if not iso:
        return ""
    try:
        from datetime import datetime

        return datetime.fromisoformat(iso).strftime("%b %d, %H:%M UTC")
    except (ValueError, TypeError):
        return ""


def _provider_label_list(meta: dict) -> str:
    present = meta.get("providers_present", []) or []
    return " + ".join(_PROVIDER_LABELS.get(p, p) for p in present) or "live markets"


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
    # PER-STAGE seed-confirm state (STG-05). The banner is scoped to the ACTIVE stage_id: each
    # stage carries its OWN seeds_confirmed flag in its committed fixture (stage1.json ships true;
    # stage2/3/playoffs ship false), so confirming one stage can never dismiss another's banner.
    # The session key is therefore per-stage (f"seeds_confirmed_{stage_id}"), seeded on first load
    # of THAT stage from its own fixture via read_seeds_confirmed(_path_for_stage(stage_id)) —
    # read-only, fail-safe to False (banner shows) on any error, never mutating the JSON/engine.
    seeds_key = f"seeds_confirmed_{stage_id}"
    # Seed from the read-only JSON flag on first load of this stage only; thereafter the in-session
    # toggle owns it. Setting the key BEFORE the widget is created makes it the toggle's initial
    # value (Streamlit binds the widget to the existing key).
    if seeds_key not in st.session_state:
        st.session_state[seeds_key] = read_seeds_confirmed(_path_for_stage(stage_id))

    seeds_confirmed = bool(st.session_state.get(seeds_key, False))

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
        key=seeds_key,
    )

    # 3. Live-odds status panel (D1) — reads the LOADED cache, NOT the env key (honest live/off).
    #    The sim feeds on data/odds_cache.json; Polymarket + Kalshi are KEYLESS, so a keyless fetch
    #    feeds the sim while the OLD banner ("off, no ODDSPAPI_KEY") lied. This reads the same cache
    #    the run uses (JSON-only loader — no httpx/dotenv import, DX-01 zero-config preserved). Every
    #    interpolated value is our own metadata / a fixed allowlist / a fixed badge — no user free-text.
    cache = load_odds_cache()
    blended = (cache or {}).get("blended") or {}
    if blended:
        meta = (cache or {}).get("_meta") or {}
        now = datetime.now(timezone.utc)
        fetched_at = meta.get("fetched_at")
        books = provider_labels(meta.get("providers_present", []))
        books_txt = f" ({', '.join(books)})" if books else ""
        st.markdown(
            f'{status_badge_html("live")} &nbsp; '
            f'<span style="font-family:ui-monospace,monospace">{len(blended)}</span> market(s) · '
            f'<span style="font-family:ui-monospace,monospace">{len(books)}</span> book(s){books_txt} · '
            f"fetched {html.escape(fmt_age(fetched_at, now))}",
            unsafe_allow_html=True,
        )
        if is_stale(fetched_at, now):
            st.warning("Live odds may be stale — click 'Fetch odds now' for current prices.")
    elif cache is not None:
        # A valid cache with an EMPTY blended map = a fetch ran, but no Cologne market posted yet.
        st.caption("odds off — no live markets posted yet, running manual ratings.")
    elif odds_key_present():
        st.caption("odds off — using manual ratings. Fetch to pull live market prices.")
    else:
        st.caption(
            "odds off — using manual ratings. Fetch to price the sim from live markets "
            "(Polymarket + Kalshi need no key; add ODDSPAPI_KEY for Pinnacle)."
        )


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

# Stage selector (Phase 6, STG-01/04). Options ARE the stage_ids so session_state[KEY_STAGE] always
# holds a stage_id (consumed by _path_for_stage); format_func renders the friendly label. Default
# (first option) is "stage1" — the zero-config first-run stage (DX-01). Writing KEY_STAGE re-keys the
# whole MC/optimizer cache so a stage switch can never serve the prior stage's numbers (STG-04).
_STAGE_LABELS = {"stage1": "Stage 1", "stage2": "Stage 2"}
stage_id = st.selectbox(
    "Stage",
    options=list(_STAGE_LABELS.keys()),
    format_func=lambda s: _STAGE_LABELS.get(s, s),
    key=KEY_STAGE,
    label_visibility="collapsed",
)
# Re-bind the module globals to the SELECTED stage so every downstream render path (header reconcile
# rows, ratings editor, bracket, run flow) uses this stage's teams — not the top-of-module Stage-1
# default. Stage 1 stays the zero-config first-run default (same teams as before).
teams, _stage_cfg = load_stage(_path_for_stage(stage_id))
by_seed = {t.seed: t for t in teams}

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

    # --- Live-odds fetch (ODDS-05/06/07, Pitfall 11) -------------------------------------
    # The ONE path that contacts the providers: an explicit USER action, OUT of the render
    # path. The handler LAZY-imports scripts.fetch_odds (which pulls httpx/dotenv) INSIDE the
    # click branch ONLY — so a plain rerun never imports the network deps (DX-01/T-05-APPIMPORT).
    # On a normal rerun this button is NOT clicked, so scripts.fetch_odds is never imported.
    st.divider()
    st.caption("Live odds (optional)")
    # Bug A fix: render the PERSISTED outcome from the previous run's fetch. A message drawn in the
    # click branch below is discarded by the st.rerun() that follows it (st.rerun halts + restarts
    # the run, dropping its output), so the outcome is stashed in session_state and rendered HERE on
    # the next run, then popped. Without this the user clicks Fetch and reliably sees nothing.
    _outcome = st.session_state.pop(KEY_ODDS_OUTCOME, None)
    if _outcome:
        {"success": st.success, "info": st.info, "error": st.error}.get(_outcome[0], st.info)(
            _outcome[1]
        )
    if st.button("Fetch odds now", key="fetch_odds_btn"):
        # Bug B fix: a real loading state for the multi-provider httpx call (never a dead button).
        with st.spinner("Contacting books — Pinnacle / Polymarket / Kalshi…"):
            try:
                from scripts.fetch_odds import main as _fetch_odds_main  # LAZY — click branch only

                cache = _fetch_odds_main()
                n_blended = len(cache.get("blended", {}))
                if n_blended:
                    books = provider_labels(cache.get("_meta", {}).get("providers_present", []))
                    st.session_state[KEY_ODDS_OUTCOME] = (
                        "success",
                        f"Fetched {n_blended} market(s) from {', '.join(books) or 'no providers'}.",
                    )
                else:
                    # A valid empty fetch (no Cologne market posted yet) is fail-soft, not an error.
                    st.session_state[KEY_ODDS_OUTCOME] = (
                        "info",
                        "No live markets found yet (Cologne markets may not have posted) — "
                        "still running rating-only.",
                    )
            except Exception as exc:  # noqa: BLE001 — the button NEVER crashes the app (fail-soft)
                st.session_state[KEY_ODDS_OUTCOME] = (
                    "error",
                    f"Odds fetch failed (running rating-only): {exc}",
                )
        st.rerun()

    # --- Live-results fetch (RES-01/02, Phase 6) -----------------------------------------
    # The ONE path that contacts the results providers — an explicit USER action OUT of the
    # render path. Mirrors the odds button EXACTLY: it LAZY-imports scripts.fetch_results (which
    # pulls httpx) INSIDE the click branch only, so a plain rerun never imports the network deps
    # (T-06-09b — test_no_network_on_rerun_with_results is the guard). The persisted-outcome stash
    # is load-bearing: a message drawn before st.rerun() is discarded — stash + render next run.
    st.caption("Live results (optional)")
    _r_outcome = st.session_state.pop(KEY_RESULTS_OUTCOME, None)
    if _r_outcome:
        {"success": st.success, "info": st.info, "error": st.error}.get(_r_outcome[0], st.info)(
            _r_outcome[1]
        )
    if st.button("Fetch latest results", key="fetch_results_btn"):
        with st.spinner("Fetching finished results…"):
            try:
                from scripts.fetch_results import main as _fetch_results_main  # LAZY — click only

                cache = _fetch_results_main(stage_id=stage_id)  # the ACTIVE stage
                n_rows = len(cache.get("results", []))
                if n_rows:
                    st.session_state[KEY_RESULTS_OUTCOME] = (
                        "success",
                        f"Fetched {n_rows} finished result(s) — auto-locking the current stage.",
                    )
                else:
                    # A valid empty fetch (no finished series posted yet) is fail-soft, not an error.
                    st.session_state[KEY_RESULTS_OUTCOME] = (
                        "info",
                        "No finished results yet (none posted for this stage) — manual entry still works.",
                    )
            except Exception as exc:  # noqa: BLE001 — the button NEVER crashes the app (fail-soft)
                st.session_state[KEY_RESULTS_OUTCOME] = (
                    "error",
                    f"Results fetch failed (manual entry still works): {exc}",
                )
        st.rerun()


def _drive_progress(ratings: dict, S: float, N: int, locked: dict, market_blend=None):
    """Cache-MISS path: iterate the FROZEN run_mc_progressive to drive st.progress.

    Each Partial(done, total, running_p_adv) advances the bar with a running sim counter
    (NEVER a blank spinner — UI-03). Do NOT override n_chunks (stays 20 — Phase 1x2
    reproducibility). Returns the final Result captured via StopIteration.value.

    ``market_blend`` (the Phase-5 odds seam — default None = unchanged rating-only path):
    ``dict["lo-hi" -> (p, var)]`` of the market-priced matchups; var>0 drives the K-Beta
    epistemic OUTER loop, var all-zero / None is the exact no-op (GATE-01 byte-identical).
    """
    bar = st.progress(0.0, text="Simulating…")
    gen = run_mc_progressive(
        teams, ratings, S, N, locked, seed=FIXED_SEED, market_blend=market_blend
    )
    result = None
    try:
        while True:
            p = next(gen)
            # Clamp into [0, 1]: under the Phase-5 epistemic OUTER loop (market_blend var>0) the
            # generator's running ``done`` tally can momentarily overshoot ``total`` across the K
            # draws, and st.progress raises on a fraction outside [0, 1]. The bar is cosmetic, so
            # clamp defensively rather than crash the run (Rule 1 — the engine tally is not ours
            # to change here; this keeps the odds-fed run from ever throwing on the progress bar).
            frac = p.done / p.total if p.total else 0.0
            frac = min(1.0, max(0.0, frac))
            bar.progress(frac, text=f"Simulating… {min(p.done, p.total):,} / {p.total:,}")
    except StopIteration as stop:
        result = stop.value
    bar.empty()
    return result


def _ci_cell_html(p: float, seed: int, band_epi: dict, band_samp: dict, two_tone: bool) -> str:
    """One probability cell's bar: two-tone (solid sampling over faint epistemic) on an odds-fed
    run, else the single-tone Wilson bar (rating-only — byte-identical to Phase 2). Shared by the
    pre-stage probs table and the live delta table so the bar rendering stays DRY (one code path)."""
    lo_o, hi_o = band_epi.get(seed, (0.0, 0.0))
    if two_tone:
        lo_i, hi_i = band_samp.get(seed, (lo_o, hi_o))
        return ci_bar_two_tone_html(p, lo_i, hi_i, lo_o, hi_o, HUE_ADVANCE)
    return ci_bar_html(p, lo_o, hi_o, HUE_ADVANCE)


def _render_probs_table(result, two_tone: bool = False) -> None:
    """SUCCESS state: per-team rows sorted by P(advance), each cell = number + inline CI bar.

    UI-04: EVERY probability cell renders the number PLUS an always-visible inline Wilson CI
    mini-bar via ci_bar_html — never hover/expand-hidden. Reused for the Pre-stage probs and
    the Live delta-probs section (delta content is Phase 4; the render is shared now).
    """
    p_adv = result.p_advance()
    p_30 = result.p_30()
    p_03 = result.p_03()
    order = sorted(by_seed, key=lambda s: p_adv.get(s, 0.0), reverse=True)
    if two_tone:
        st.caption(TWO_TONE_LEGEND)
    hdr = st.columns([3, 2, 2, 2])
    hdr[0].markdown("**Team**")
    hdr[1].markdown("**P(advance)**")
    hdr[2].markdown("**P(3-0)**")
    hdr[3].markdown("**P(0-3)**")
    for seed in order:
        t = by_seed[seed]
        c = st.columns([3, 2, 2, 2])
        c[0].markdown(f"{t.name}")
        c[1].markdown(
            _ci_cell_html(
                p_adv.get(seed, 0.0), seed,
                result.band_advance, result.band_advance_sampling, two_tone,
            ),
            unsafe_allow_html=True,
        )
        c[2].markdown(
            _ci_cell_html(
                p_30.get(seed, 0.0), seed,
                result.band_30, result.band_30_sampling, two_tone,
            ),
            unsafe_allow_html=True,
        )
        c[3].markdown(
            _ci_cell_html(
                p_03.get(seed, 0.0), seed,
                result.band_03, result.band_03_sampling, two_tone,
            ),
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


def _render_delta_table(pre_result, post_result, two_tone: bool = False) -> None:
    """LIVE 'Delta probabilities' (RESIM-02 — show the CHANGE, not a new static number).

    Each cell renders the post-lock value (CI bar) PLUS a signed percentage-point delta vs
    the pre-lock (empty-locked) baseline via delta_tag_html — so the user SEES what moved
    (ISSUE-1: the section was previously rendering absolute values under a 'Delta' header).
    Sorted by post-lock P(advance); the delta sign (+/-) is colorblind-safe (UI-06).
    """
    pre_adv, pre_30, pre_03 = pre_result.p_advance(), pre_result.p_30(), pre_result.p_03()
    post_adv, post_30, post_03 = (
        post_result.p_advance(),
        post_result.p_30(),
        post_result.p_03(),
    )
    order = sorted(by_seed, key=lambda s: post_adv.get(s, 0.0), reverse=True)
    st.caption("Post-lock odds with the change vs pre-lock (+/-pp) — blue up, amber down.")
    if two_tone:
        st.caption(TWO_TONE_LEGEND)
    hdr = st.columns([3, 2, 2, 2])
    hdr[0].markdown("**Team**")
    hdr[1].markdown("**P(advance)**")
    hdr[2].markdown("**P(3-0)**")
    hdr[3].markdown("**P(0-3)**")
    for seed in order:
        t = by_seed[seed]
        c = st.columns([3, 2, 2, 2])
        c[0].markdown(f"{t.name}")
        cells = (
            (c[1], post_adv, pre_adv, post_result.band_advance, post_result.band_advance_sampling),
            (c[2], post_30, pre_30, post_result.band_30, post_result.band_30_sampling),
            (c[3], post_03, pre_03, post_result.band_03, post_result.band_03_sampling),
        )
        for col, post_p, pre_p, band_epi, band_samp in cells:
            col.markdown(
                _ci_cell_html(post_p.get(seed, 0.0), seed, band_epi, band_samp, two_tone)
                + delta_tag_html(post_p.get(seed, 0.0), pre_p.get(seed, 0.0)),
                unsafe_allow_html=True,
            )


def _render_bracket() -> None:
    """Bracket as a COLLAPSED expander — seeded Round 1 `(seed, seed+8)` table only (UI-SPEC
    bracket empty state). Switch to Live mode for the full record-bucket bracket."""
    with st.expander("Bracket — seeded Round 1", expanded=False):
        st.caption("Round 1 pairings (seed vs seed+8). Switch to Live to see the record-bucket bracket.")
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


def _odds_from_cache(base_ratings: dict):
    """Derive (ratings, market_blend, fetched_at) from data/odds_cache.json — fail-soft (ODDS-04/05).

    Reads the read-only cache via the json-only loader (NO httpx/dotenv — DX-01). When a valid cache
    loads with a non-empty ``blended`` map:
      - back-solve per-team ratings from the market series probs (engine.backsolve.fit_ratings):
        each ``blended["lo-hi"] = {p, var, bo3}`` is INVERTED to a MAP-level prob via
        ``invert_series(p, bo3)`` (Pitfall 9 — invert series->map BEFORE fitting) and used as the
        target P(lower-id beats higher-id on a map); the top-seed team is the gauge anchor;
      - build ``market_blend = {"lo-hi": (p, var)}`` (SERIES p + raw var) for the epistemic OUTER
        loop (engine.probs.epistemic_draws clamps var via beta_moment_fit downstream, never here).
    Returns ``(base_ratings, None, None)`` unchanged when the cache is absent / invalid / empty —
    the rating-only path (no behavior change, the existing banner stays).

    ``fetched_at`` (``_meta.fetched_at``) is returned so the run cache key can fold it in: a fresh
    fetch that moves only ``var`` (not the back-solved ratings) still invalidates the memoized
    Result — no stale epistemic band (T-05-STALEBAND).
    """
    cache = load_odds_cache()
    if not cache:
        return base_ratings, None, None
    blended = cache.get("blended") or {}
    if not blended:
        # A valid EMPTY cache (no market posted) is fail-soft -> rating-only, but still fold its
        # fetched_at into the key so a later non-empty fetch re-runs (the var changes the band).
        return base_ratings, None, cache.get("_meta", {}).get("fetched_at")

    # Build MAP-level back-solve targets: invert each SERIES prob to a map prob (Pitfall 9).
    targets: dict[tuple[int, int], float] = {}
    market_blend: dict[str, tuple[float, float]] = {}
    for key, b in blended.items():
        try:
            lo_s, hi_s = key.split("-")
            lo, hi = int(lo_s), int(hi_s)
            p = float(b["p"])
            var = float(b.get("var", 0.0))
            bo3 = bool(b.get("bo3", False))
        except (ValueError, KeyError, TypeError):
            continue  # a malformed entry is skipped, never crashes the run (fail-soft)
        targets[(lo, hi)] = invert_series(p, bo3)  # P(lower-id beats higher-id on a MAP)
        market_blend[key] = (p, var)

    if not targets:
        return base_ratings, None, cache.get("_meta", {}).get("fetched_at")

    # Gauge anchor: the top seed (id == min seed) holds its rating fixed so the fit is identifiable.
    anchor_id = min(t.id for t in teams)
    ratings = fit_ratings(targets, teams, float(S), anchor_id)
    return ratings, market_blend, cache.get("_meta", {}).get("fetched_at")


def _cache_key_for(ratings: dict, locked: dict, stage_id: str, fetched_at=None):
    """The ``(stage_id, ratings_key, S, int(N), locked_key, fetched_at)`` cache tuple.

    ``stage_id`` LEADS the tuple (Phase 6, STG-04) so it scopes the WHOLE key — a stage switch can
    never serve the prior stage's memoized Result. The element order MUST match ``optimize_cached``'s
    params after ``_result`` (stage_id, ratings_key, S, N, locked_key, fetched_at) because the ballot
    panel splats ``optimize_cached(result, *cache_key)``; a reorder here silently corrupts that call.

    ``fetched_at`` (the cache's ``_meta.fetched_at``, or None when rating-only) is folded into the
    key so a FRESH fetch that moves only the epistemic ``var`` (not the back-solved ratings) still
    invalidates the memoized Result — no stale epistemic band is served (T-05-STALEBAND).
    """
    return (stage_id, freeze_ratings(ratings), S, int(N), freeze_locked(locked), fetched_at)


def _compute_or_serve(ratings: dict, locked: dict, stage_id: str, market_blend=None, fetched_at=None):
    """Get-or-compute the MC Result for the run key — returns (result, cache_key).

    Single source for BOTH the current Run and the LIVE empty-locked anchor compute. A cache
    HIT serves the stored Result (no recompute); a MISS drives the progress bar over
    run_mc_progressive ONCE and memoizes it. Each DISTINCT key computes at most once, so the
    CR-01 single-compute guard stays green even when LIVE mode also computes the empty-locked
    pre_key (a different key from the locked run).

    ``stage_id`` LEADS the cache key (Phase 6, STG-04) so a stage switch never serves the prior
    stage's Result. ``market_blend`` (the odds seam) feeds the epistemic OUTER loop; ``fetched_at``
    is folded into the cache key so a fresh fetch (moved var) invalidates the memoized Result
    (T-05-STALEBAND).
    """
    cache_key = _cache_key_for(ratings, locked, stage_id, fetched_at)
    cache = st.session_state[KEY_MC_CACHE]
    if cache_key in cache:
        return cache[cache_key], cache_key
    result = _drive_progress(ratings, S, int(N), locked, market_blend)
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
    # Phase 5 odds seam (ODDS-04/05): if a valid data/odds_cache.json is present, REPLACE the
    # manual ratings with the back-solved ones AND carry the market blend/var into the epistemic
    # outer loop; the cache's _meta.fetched_at folds into the cache key (T-05-STALEBAND). Absent /
    # invalid / empty cache -> (ratings, None, None) unchanged: the rating-only path, no behavior
    # change, the existing 'live odds off' banner stays (DX-01/ODDS-08).
    ratings, market_blend, fetched_at = _odds_from_cache(ratings)
    # Phase 6 (RES-02): fold the RESULTS cache's _meta.fetched_at into the SAME fetched_at slot as
    # the odds timestamp, so a fresh results fetch (new _meta.fetched_at) forces a cache MISS and the
    # conditional re-sim re-fires even when the auto-locked set is unchanged. The pre-fill already
    # ran in the main block (KEY_LOCKED carries the auto-locked results); here we only thread the ts.
    fetched_at = _combined_fetched_at(fetched_at)
    # Phase 4 fill point: the engine ``locked`` dict is DERIVED from KEY_LOCKED (the ordered
    # lock list) via the pure projection, then flows through the UNCHANGED freeze_locked ->
    # locked_key -> cache_key path so a non-empty lock changes the key and re-sims (RESIM-01).
    # In PRE_STAGE / first-run the list is empty -> locked == {} (no behavior change).
    locked = locked_dict(st.session_state.get(KEY_LOCKED, []))
    result, cache_key = _compute_or_serve(
        ratings, locked, stage_id, market_blend, fetched_at
    )
    return result, None, cache_key


def _live_anchor(ratings: dict, ids: list[int]):
    """The FIXED anchor ballot (Ballot B) for the LIVE delta + status chips (D5/BLOCKER 1).

    Captured ONCE, from the EMPTY-locked pre_key Result, and stored in KEY_LIVE_ANCHOR so it
    NEVER re-optimizes per round (the arrow would be meaningless otherwise). Returns
    ``(anchor_ballot, pre_lock_result)``:
      pre_key       = (stage_id, freeze_ratings(ratings), S, int(N), freeze_locked({}), fetched_at)
      pre_lock_result = mc_cache[pre_key] if present else ONE explicit compute on pre_key
                        (memoized — a DISTINCT key from the locked run, so CR-01 stays green)
      anchor        = optimize_cached(pre_lock_result, *pre_key).recommended  (Ballot B)

    The anchor is re-served from session_state on later reruns; only a first-ever capture runs
    the optimizer. ``pre_lock_result`` is returned so ``before`` is read off the pre_key sample.

    Phase 5: the pre_key uses the SAME odds-fed ratings + blend/var + fetched_at as the locked run
    (via _odds_from_cache) so the empty-locked baseline is consistent with the odds-fed numbers and
    the pre_key matches a real cache entry (no separate rating-only baseline under live odds).
    """
    ratings, market_blend, fetched_at = _odds_from_cache(ratings)
    fetched_at = _combined_fetched_at(fetched_at)  # fold the results ts too (RES-02 consistency)
    pre_lock_result, pre_key = _compute_or_serve(
        ratings, {}, stage_id, market_blend, fetched_at
    )  # empty-locked = pre_key (stage_id LEADS the key — Phase 6, STG-04)
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
        # A manually-committed lock is authoritative ground truth — tag provenance "manual" so a
        # later conflicting fetch cannot silently overwrite it (RES-03, T-06-11).
        prov = dict(st.session_state.get(KEY_LOCK_PROVENANCE, {}))
        prov[frozenset((winner_id, loser_id))] = "manual"
        st.session_state[KEY_LOCK_PROVENANCE] = prov


def _row_to_pending(row) -> tuple[int, int, int] | None:
    """Project ONE frozen-schema result row to a ``(round_idx, winner_id, loser_id)`` pending lock.

    Recovers the loser from the SORTED ``match`` [lo, hi] tuple: ``ell = lo if winner == hi else hi``.
    Returns ``None`` (drop) on a malformed row (bad shape / winner not in the pair) — a mis-shaped
    fetched row must never raise into the UI or fabricate a lock (T-06-10 fail-soft)."""
    try:
        lo, hi = row["match"]
        w = row["winner"]
    except (KeyError, TypeError, ValueError):
        return None
    if w == lo:
        ell = hi
    elif w == hi:
        ell = lo
    else:
        return None  # winner not one of the matched pair — drop (never mis-attribute)
    try:
        round_idx = int(row["round_idx"])
    except (KeyError, TypeError, ValueError):
        return None
    return (round_idx, w, ell)


def _prefill_results_into_locked() -> str | None:
    """Pre-fill the ACTIVE stage's KEY_LOCKED from fetched FINISHED results (RES-02). Returns the
    results cache's ``_meta.fetched_at`` (or ``None`` when there is no cache) so the run cache key
    can fold it in — a FRESH fetch then forces a MISS and the conditional re-sim re-fires.

    Every fetched row routes through the SAME guard a manual lock uses — ``legal_pairings_for_round``
    (prefix guard) -> ``validate_lock`` (the five illegal cases) -> ``add_lock`` — NO bypass, NO
    engine edit (T-06-10). The active-stage filter compares ``int(_meta.stage)`` to
    ``_stage_int_for(stage_id)`` through the ONE canonical helper (never a raw ``int == str`` that
    silently no-ops — T-06-12). A fetched row whose pair already has a MANUAL lock with a DIFFERENT
    winner is NOT auto-applied: it is stashed as a pending conflict for the explicit confirm control
    (RES-03, handled in _render_results_conflict) — never a silent overwrite.
    """
    results = load_results_cache()
    if not results:
        return None
    fetched_at = results.get("_meta", {}).get("fetched_at")
    try:
        active_stage_int = _stage_int_for(stage_id)
        cache_stage_int = int(results.get("_meta", {}).get("stage"))
    except (TypeError, ValueError):
        return fetched_at  # an unknown/garbled stage filters to nothing — fail-soft, still fold ts
    if cache_stage_int != active_stage_int:
        return fetched_at  # results are for another stage — do not prefill (canonical int compare)

    # Lock in ROUND ORDER so legal_pairings_for_round's "all prior rounds fully locked" precondition
    # is satisfied in ONE pass (HI-01). The live bo3.gg feed is reverse-chronological
    # (sort=-start_date), so an UNSORTED pass hits R5/R4/R3 rows first against a still-empty lock
    # list, the prefix guard raises, and every R2+ row is dropped until a later rerun. Sorting by
    # round_idx (here AND at WRITE time in scripts.fetch_results.main) makes the prefix build in
    # order so all rounds auto-lock in this single pass. round_idx is validated by _row_to_pending
    # (a malformed row -> None -> dropped before the sort key is read). Stable sort preserves the
    # within-round provider order.
    rows = results.get("results") or []
    pendings = [p for p in (_row_to_pending(row) for row in rows) if p is not None]
    pendings.sort(key=lambda p: p[0])  # p == (round_idx, winner_id, loser_id)
    for pending in pendings:
        round_idx, w, ell = pending
        locked_results = st.session_state.get(KEY_LOCKED, [])
        prov = st.session_state.get(KEY_LOCK_PROVENANCE, {})
        pair = frozenset((w, ell))

        # Already locked? Check for a CONFLICT with a manual lock (RES-03) before anything else.
        existing = next(
            (e for e in locked_results if frozenset((e[1], e[2])) == pair), None
        )
        if existing is not None:
            ex_w = existing[1]
            if ex_w != w and prov.get(pair, "manual") == "manual":
                # Conflicts with a MANUAL lock — stash a pending conflict, never silently overwrite.
                st.session_state[KEY_PENDING_RESULT_CONFLICT] = pending
            continue  # same pair already locked (agreeing, or auto, or conflict-stashed) — skip

        # Not yet locked — run the SAME validate path as a manual lock (no bypass).
        try:
            legal = legal_pairings_for_round(teams, locked_results, S, round_idx)
        except Exception:  # noqa: BLE001 — incomplete prefix: skip this row, never raise (RES-04)
            continue
        reason = validate_lock((w, ell), round_idx, locked_results, teams, legal)
        if reason is not None:
            continue  # illegal fetched lock — rejected (existing reason), KEY_LOCKED untouched
        st.session_state[KEY_LOCKED] = add_lock(locked_results, round_idx, w, ell)
        new_prov = dict(prov)
        new_prov[pair] = "auto"  # provenance: auto-fetched (RES-03)
        st.session_state[KEY_LOCK_PROVENANCE] = new_prov
    return fetched_at


def _combined_fetched_at(odds_fetched_at):
    """Fold BOTH the odds and the results cache timestamps into the SINGLE cache-key fetched_at slot.

    A fresh fetch from EITHER source must invalidate the memoized Result. Returns a tuple
    ``(odds_fetched_at, results_fetched_at)`` (or the lone odds value when there is no results
    cache) — any change in either element changes the run cache key (RES-02 re-sim re-fire +
    T-05-STALEBAND), so a new results _meta.fetched_at re-fires the re-sim even with an unchanged
    locked set. ``_RESULTS_FETCHED_AT`` is set by _prefill_results_into_locked earlier in the run."""
    results_fetched_at = _RESULTS_FETCHED_AT
    if results_fetched_at is None:
        return odds_fetched_at
    return (odds_fetched_at, results_fetched_at)


def _apply_fetched_conflict(pending: tuple[int, int, int]) -> None:
    """ATOMIC, VALIDATE-FIRST confirm of a fetched result that conflicts with a MANUAL lock (RES-03).

    The ordering is pinned (T-06-11 data integrity): (a) build the prospective lock list AS IF the
    conflicting manual entry were removed (on a COPY — session_state is not mutated yet); (b) run the
    EXISTING guard on that prospective-without-the-fetched state — legal_pairings_for_round then
    validate_lock; (c) ONLY on validate_lock == None commit the swap (remove the manual entry, add the
    fetched one, tag provenance 'auto', clear the pending); (d) on a reason DO NOT remove the manual
    entry and DO NOT add the fetched one — KEY_LOCKED stays exactly as it was (manual lock intact) and
    the reason is surfaced. The manual lock is NEVER removed before a successful validation."""
    round_idx, w_f, ell_f = pending
    pair = frozenset((w_f, ell_f))
    locked_results = list(st.session_state.get(KEY_LOCKED, []))

    # The conflicting MANUAL entry covering the same pair (if any).
    manual_entry = next(
        (e for e in locked_results if frozenset((e[1], e[2])) == pair), None
    )
    # Prospective state WITHOUT the conflicting manual entry and WITHOUT the fetched one yet — the
    # exact set validate_lock must judge the fetched lock against (mirrors _commit_lock's contract).
    prospective = [e for e in locked_results if e is not manual_entry]

    try:
        legal = legal_pairings_for_round(teams, prospective, S, round_idx)
    except Exception as exc:  # noqa: BLE001 — incomplete prefix: surface, mutate nothing (RES-04)
        st.error(str(exc))
        return
    reason = validate_lock((w_f, ell_f), round_idx, prospective, teams, legal)
    if reason is not None:
        # Engine-illegal fetched lock — DO NOT remove the manual entry, DO NOT add the fetched one.
        # KEY_LOCKED stays exactly as it was; surface the reason. (validate before remove — T-06-11.)
        st.error(reason)
        return
    # Legal — commit the swap atomically: manual entry dropped, fetched one added, provenance 'auto'.
    st.session_state[KEY_LOCKED] = add_lock(prospective, round_idx, w_f, ell_f)
    new_prov = dict(st.session_state.get(KEY_LOCK_PROVENANCE, {}))
    if manual_entry is not None:
        new_prov.pop(frozenset((manual_entry[1], manual_entry[2])), None)
    new_prov[pair] = "auto"
    st.session_state[KEY_LOCK_PROVENANCE] = new_prov
    st.session_state.pop(KEY_PENDING_RESULT_CONFLICT, None)


def _render_results_conflict(name_of: dict[int, str]) -> None:
    """Render the LOUD conflict notice + explicit confirm control for a stashed pending conflict.

    A fetched result that disagrees with a MANUAL lock for the same pair is NEVER silently applied
    (RES-03). Show the diff loudly (team names HTML-escaped at the boundary — T-06-13) plus an
    explicit 'Apply fetched result' button that routes through the atomic validate-first swap. The
    manual lock stays intact until the user confirms (and stays intact if the fetched lock is
    engine-illegal). Renders nothing when there is no pending conflict."""
    pending = st.session_state.get(KEY_PENDING_RESULT_CONFLICT)
    if not pending:
        return
    round_idx, w_f, ell_f = pending
    locked_results = st.session_state.get(KEY_LOCKED, [])
    pair = frozenset((w_f, ell_f))
    manual_entry = next(
        (e for e in locked_results if frozenset((e[1], e[2])) == pair), None
    )
    w_name = html.escape(str(name_of.get(w_f, w_f)))
    ell_name = html.escape(str(name_of.get(ell_f, ell_f)))
    if manual_entry is not None:
        m_w = html.escape(str(name_of.get(manual_entry[1], manual_entry[1])))
        m_ell = html.escape(str(name_of.get(manual_entry[2], manual_entry[2])))
        st.warning(
            f"Results conflict (Round {round_idx + 1}): the fetched result says {w_name} beat "
            f"{ell_name}, but you manually locked {m_w} beat {m_ell}. Confirm to overwrite your "
            f"manual lock with the fetched result — your manual lock is kept until you confirm."
        )
    else:
        st.warning(
            f"Results conflict (Round {round_idx + 1}): the fetched result says {w_name} beat "
            f"{ell_name}. Confirm to apply it."
        )
    if st.button("Apply fetched result", key="apply_fetched_result_btn"):
        _apply_fetched_conflict(pending)


def _render_results_provenance(name_of: dict[int, str]) -> None:
    """Surface fetched-results staleness + per-lock provenance (auto vs manual) (RES-03).

    Staleness: read the results cache's _meta.fetched_at and render its relative age via the EXISTING
    ui.render.fmt_age/is_stale (a stale cache shows an st.warning prompting a re-fetch — the same
    discipline the odds panel uses). Provenance: list each locked pair tagged 'auto' (fetched) or
    'manual' (user-entered) so the user can see which results came from the fetch. Names HTML-escaped
    (T-06-13). Renders nothing when there is no results cache and no locks."""
    from datetime import datetime, timezone

    results = load_results_cache()
    if results:
        fetched_at = results.get("_meta", {}).get("fetched_at")
        now = datetime.now(timezone.utc)
        age = fmt_age(fetched_at, now)
        if is_stale(fetched_at, now):
            st.warning(
                f"Fetched results may be stale (fetched {age}) — click "
                f"“Fetch latest results” to refresh."
            )
        else:
            st.caption(f"Fetched results: {age}.")

    locked_results = st.session_state.get(KEY_LOCKED, [])
    prov = st.session_state.get(KEY_LOCK_PROVENANCE, {})
    if not locked_results:
        return
    lines = []
    for (round_idx, w, ell) in locked_results:
        source = prov.get(frozenset((w, ell)), "manual")  # missing -> manual (pre-Phase-6 default)
        w_name = html.escape(str(name_of.get(w, w)))
        ell_name = html.escape(str(name_of.get(ell, ell)))
        badge = "auto (fetched)" if source == "auto" else "manual"
        lines.append(f"R{round_idx + 1}: {w_name} beat {ell_name} — <em>{badge}</em>")
    st.markdown(
        "<div style='font-size:0.85rem;color:#9aa4b2'>Locked results · "
        + " &nbsp;|&nbsp; ".join(lines)
        + "</div>",
        unsafe_allow_html=True,
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
    # Progress hint (ISSUE-2): the next round is gated on THIS round being fully locked, so tell
    # the user how many remain — otherwise the gating is correct but undiscoverable.
    total = len(legal)
    if total and open_pairs:
        st.caption(
            f"Round {round_idx + 1}: {len(already)} of {total} matches locked — "
            f"lock all {total} to open the next round."
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


def _render_odds_drilldown(blended) -> None:
    """D3 per-book drill-down: 'why the books disagree'. For each priced match with >=2 sources,
    list each book's series price next to the blended consensus, sorted by disagreement spread
    (widest first). Pure display read of the optional ``sources`` field — a match without it (a
    pre-D3 cache) is skipped. Team names + book labels are HTML-escaped; prices are numeric (T-XSS).
    """
    name_of = {t.id: t.name for t in teams}
    rows = []
    for key, b in blended.items():
        sources = b.get("sources") or []
        if len(sources) < 2:
            continue  # nothing to compare — one (or no) independent opinion
        try:
            lo, hi = (int(x) for x in str(key).split("-"))
        except (ValueError, AttributeError):
            continue
        rows.append((lo, hi, b, sources, source_spread(sources)))
    if not rows:
        return
    rows.sort(key=lambda r: r[4], reverse=True)  # widest disagreement first
    with st.expander("Why the books disagree", expanded=False):
        st.caption("Each book's series price vs the blended consensus — sorted by disagreement.")
        for lo, hi, b, sources, spread in rows:
            a = html.escape(str(name_of.get(lo, lo)))
            c = html.escape(str(name_of.get(hi, hi)))
            books_txt = " · ".join(
                f"{html.escape(PROVIDER_LABELS.get(str(s.get('book', '')).lower(), str(s.get('book', ''))))} "
                f"{float(s.get('p', 0.0)):.2f}"
                for s in sources
            )
            wide = " [wide]" if spread > 0.10 else ""  # ASCII tag — the label is the signal (UI-06)
            st.markdown(
                f"**{a} vs {c}** — {books_txt} → blended {float(b.get('p', 0.0)):.2f} "
                f"(spread {spread:.2f}){wide}"
            )


# --- Main column: mode-conditional ordering (UI-01) --------------------------------------
with main:
    # Phase 6 (RES-02): pre-fill the active stage's KEY_LOCKED from fetched FINISHED results BEFORE
    # anything consumes KEY_LOCKED (the run flow + the LIVE lock controls). Every fetched lock routes
    # through the existing validate path (no bypass, no engine edit); a conflict with a manual lock is
    # stashed for explicit confirm, never silently applied. The returned _meta.fetched_at is folded
    # into the run cache key (via _combined_fetched_at) so a fresh fetch re-fires the conditional re-sim.
    _RESULTS_FETCHED_AT = _prefill_results_into_locked()
    result, error_msg, cache_key = _run_or_serve()
    # Odds-fed view state (D2/D3): the loaded cache's priced matchups drive the two-tone CI bars
    # (solid sampling + faint epistemic) and the per-book drill-down. Empty / rating-only cache ->
    # priced empty -> two_tone False -> single-tone bars (the Phase-2 render, unchanged).
    odds_blended = (load_odds_cache() or {}).get("blended") or {}
    two_tone = bool(priced_ids(odds_blended))
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
            _render_probs_table(result, two_tone)

        _render_bracket()
    else:
        # LIVE order: (1) round-by-round lock controls, (2) locked-pick status + from-here
        # delta hero + status legend, (3) delta-probs area, (4) record-bucket bracket.
        # name_of / ids are built ONCE here (NOT reused from _render_ballot_panel's local).
        name_of = {t.id: t.name for t in teams}
        ids = [t.id for t in teams]

        st.subheader("Lock results")
        # RES-03: a fetched result that conflicts with a manual lock surfaces a LOUD notice + an
        # explicit confirm here (rendered BEFORE the lock controls so the conflict is unmissable);
        # the atomic validate-first swap keeps the manual lock intact on an engine-illegal fetched
        # lock. Then the provenance/staleness line surfaces auto-vs-manual + fetched_at freshness.
        _render_results_conflict(name_of)
        _render_results_provenance(name_of)
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
            # pre_lock_result (empty-locked baseline) was assigned above under the SAME
            # (result is not None and not error) condition — show the per-team change.
            _render_delta_table(pre_lock_result, result, two_tone)

        _render_bracket_live(name_of)

    # Per-book drill-down (D3) — shown in BOTH modes when the loaded cache carries per-source prices
    # (skipped on a rating-only / pre-D3 cache that has no `sources`). A pure display read.
    if odds_blended:
        _render_odds_drilldown(odds_blended)


# --- Honest methodology footer (full width, both modes) ----------------------------------
def _render_footer() -> None:
    """One-line provenance so a screenshot is self-explanatory and honest: data sources +
    freshness, the market-anchored-R1 / modeled-later-rounds split, reproducible sim params, and
    the engine-validation basis. Reads the JSON cache only (no httpx import)."""
    cache = load_odds_cache()
    meta = (cache or {}).get("_meta", {})
    blended = (cache or {}).get("blended") or {}
    st.divider()
    bits: list[str] = []
    if blended:
        fetched = _fmt_fetched(meta.get("fetched_at"))
        src = _provider_label_list(meta)
        bits.append(f"**Odds:** {src} · {len(blended)} R1 matches priced (de-vigged, log-opinion pooled)")
        if fetched:
            bits.append(f"fetched {fetched}")
        bits.append("R1 market-anchored; later rounds modeled from market-back-solved ratings")
    else:
        bits.append("**Mode:** rating-only (no live odds loaded)")
    bits.append(f"{int(N) // 1000}k sims · fixed seed {FIXED_SEED} (reproducible)")
    # Engine-provenance only (no event-name claim — keeps the UI off the Budapest overclaim the
    # trust-badge rule forbids; the badge above carries the validation state).
    bits.append("engine validated vs Valve rulebook + full round-by-round backtest")
    st.caption(" · ".join(bits))


_render_footer()
