# Phase 4 Research — Conditional Re-Sim + Live Mode

Phase: 04-conditional-re-sim-live-mode
Requirements: RESIM-01, RESIM-02, RESIM-03, RESIM-04
Depends on: Phase 1 (engine `locked` support + `pairings_out` observability seam) · Phase 2 (`locked` in the `@st.cache_data` key via `freeze_locked`, the `_hero_slot` placeholder, the LIVE-mode shell, the status palette) · Phase 3 (`engine.optimizer.p_ge5` + `build_outcome_matrices` reused for the from-here delta)
Sources: `files/HANDOFF_claude_code.md` §4 (locked results, line 142) · §10.5 (UI contract, lines 282-364: two-mode IA, interaction-state table line 320-322, dead/live/secured "emotional core" line 324, record-bucket bracket line 335) · `.planning/ROADMAP.md` Phase 4 · `engine/swiss.py` (`simulate_stage`, `_play`, `pairings_out`, `build_round1_pairs`) · `engine/montecarlo.py` (`run_mc_progressive`, `Result.sample`) · `engine/optimizer.py` (`p_ge5`, `build_outcome_matrices`, `OptimizerOutput`) · `ui/cache.py` (`freeze_locked`, `run_mc_cached`, `optimize_cached`) · `ui/state.py` · `ui/render.py` (`STATUS`, `status_badge_html`, `hero_number_html`) · `app.py` (`_run_or_serve`, `_hero_slot`, `_render_bracket`, mode block lines 386-443) · `tests/test_backtest_budapest_2025.py` (the deterministic-replay pattern Phase 4 reuses)

## What this phase is

A **UI + classification layer** on top of an engine that already does everything Phase 4
needs. The ROADMAP note is correct and verified against the code: re-sim "fires for free"
because `locked` is a REAL positional arg in the `@st.cache_data` key (`ui/cache.py:48-65`,
`run_mc_cached(ratings_key, S, N, locked_key)`) AND in the session-state cache tuple
(`app.py:308`, `cache_key = (ratings_key, S, int(N), locked_key)`), and `simulate_stage`
honors `locked` deterministically in `_play` (`engine/swiss.py:202-229`). **No engine
mutation is required** — the Phase 1×2 seams were honored, so this is additive: a new pure
module (`engine/live.py` — validator + classification + delta + bracket derivation) plus a
UI wiring slice that fills the LIVE-mode placeholders already stubbed in `app.py`.

The load-bearing discovery: `simulate_stage(teams, None, S, rng, FULL_locked, pairings_out=[])`
**deterministically reproduces the entire round-by-round pairing sequence** when `locked`
contains every played match — this is exactly what `test_backtest_budapest_2025` does
(`tests/test_backtest_budapest_2025.py:91-94`). Phase 4's two hardest UI questions — "which
pairings exist at round R given prior locks?" and "render the record-bucket bracket" — are
**both answered by replaying the engine with the current partial `locked` dict and reading
`pairings_out`**. We do not re-derive pairings in the UI; we ask the proven engine.

## The format facts (load-bearing — getting any wrong corrupts the live view)

- **`locked` key shape is FINAL and already wired:** `dict[frozenset({a.id, b.id}) -> winner_id]`
  (`engine/swiss.py:210`, `_play` reads `frozenset((a.id, b.id))`). `freeze_locked`
  (`ui/cache.py:26-35`) round-trips it order-independently into the cache key. A locked match
  is also recorded in `opps` so the no-rematch rule respects locked history
  (`engine/swiss.py:264-271`, `simulate_stage` docstring lines 240-241). **id == seed** for
  the Cologne fixture (`engine/teams.py:104-107`, `Team(id=seed, ...)`) — but classification
  and the validator must key on `id`, never assume `id == seed` (the optimizer already learned
  this: `app.py:367-371` looks names up by id via `name_of`, not `by_seed`).
- **A locked winner not in the pair already raises** in the engine (`engine/swiss.py:219-222`,
  `ValueError`). Phase 4's validator must catch the *same* class of errors BEFORE the engine is
  called, so the user sees a friendly reason (RESIM-03), not a stack trace.
- **Termination thresholds:** `ADVANCE_AT_WINS = 3`, `ELIMINATE_AT_LOSSES = 3`
  (`engine/teams.py:22-23`). A team is "out" of further matches once it reaches 3W or 3L.
- **Round structure:** R1 is fixed `seed i vs i+8` (`build_round1_pairs`, `engine/teams.py:143-150`).
  Rounds 2+ are record-grouped and Buchholz-seeded — **pairings past R1 depend on standings**, so
  the UI cannot enumerate "round R's matches" from seeds alone; it must replay (see D6).
- **The delta is a CHANGE, not a number** (HANDOFF §10.5 line 324-326): "`71% → 58%` … the
  *change* is the point, show it, don't just swap in a new static number." The hero shows
  pre-lock P(≥5) → post-lock P(≥5) for the same anchored ballot.

## Key decisions

### D1 — Lock data model: `st.session_state[KEY_LOCKED]` is a `list[(round, winner_id, loser_id)]`; `locked` dict is DERIVED from it
The user locks a **(match) winner** round by round. Store the source-of-truth as an
**ordered list of locked results** in a new session key (`KEY_LOCKED = "locked_results"`),
each entry `(round_idx, winner_id, loser_id)` — ordered so "undo last lock" and round grouping
are trivial. The engine-facing `locked` dict is a pure projection:
`{frozenset((w, l)): w for (_r, w, l) in locked_results}`. Feed that projection through the
EXISTING `freeze_locked` → `locked_key` → `cache_key` path in `_run_or_serve` (`app.py:305-308`),
which currently hardcodes `locked: dict = {}` (line 305 — the Phase-4 fill point). Keeping the
list as the UI truth and the dict as a derived projection means the cache key stays exactly the
proven `(ratings_key, S, N, locked_key)` tuple and **re-sim fires for free** (RESIM-01).

### D2 — Re-sim fires via the cache key — CONFIRMED already wired; "deterministic winners" proven by replay
`locked_key` is a genuine `@st.cache_data` key arg (`run_mc_cached`, `ui/cache.py:49`) and a
genuine session-cache-tuple member (`app.py:308`), NOT the `_locked` underscore-escape — the
Phase 2 SUMMARY and `ui/cache.py:1-13` docstring explicitly forbid the escape (Pitfall 13). So
the moment D1's derived dict is non-empty, the cache key changes, the session cache misses, and
`run_mc_progressive` re-runs conditioned on the locks. **"At least one P(advance) moves"
(RESIM-01)** is structurally guaranteed: a locked winner sets that pair's outcome to P=1, which
mechanically shifts both teams' advance counts vs the unlocked marginal. **"Locked winners
deterministic"** is proven by replaying `simulate_stage` with a full `locked` and asserting the
winner's record matches across sims — exactly the existing `test_locked_results_honored`
[CRITICAL] pattern (HANDOFF §6 line 199-201); Phase 4 adds an app-level assertion that two
identical locked Runs serve the same cached object (mirrors `test_cache_hit_is_instant`,
`tests/test_app.py:37-51`).

### D3 — A pure `validate_lock()` in `engine/live.py` rejects impossible pairings with a reason (RESIM-03)
Validation lives in the **engine** (pure, TDD-able, streamlit-free — same functional-core rule
the optimizer follows), called by the UI before any lock is committed. Signature:

```python
def validate_lock(
    new: tuple[int, int],          # (winner_id, loser_id) the user is locking
    round_idx: int,
    locked_results: list[tuple[int, int, int]],  # prior (round, winner, loser)
    teams: list[Team],
    legal_pairings: set[frozenset],  # the pairings the engine says exist at round_idx (D6)
) -> str | None:                   # None = OK; else a human reason string
```

Enumerated impossible cases and their reason strings (UI shows the returned string via
`st.error`, blocking the lock — never silently accepted):

| Case | Reason string |
|------|---------------|
| **Rematch** — `frozenset(new)` already in a prior locked pair | `"{A} vs {B} already played this stage — no rematches."` |
| **Terminated team** — winner or loser already at 3W or 3L (replay records to date) | `"{T} is already out (3-0 advanced / 0-3 eliminated) — cannot play another match."` |
| **Not an actual pairing** — `frozenset(new)` ∉ `legal_pairings` for `round_idx` | `"{A} and {B} are not paired this round — the format pairs by record + Buchholz."` |
| **Double-booked** — winner or loser already appears in another lock at `round_idx` | `"{T} is already locked into another match this round."` |
| **Winner not in pair** — degenerate caller bug | `"locked winner {W} is not one of {A}/{B}."` (mirrors engine ValueError msg, `swiss.py:219`) |

Reason strings are returned as **plain text by id→name lookup** (escaped at the UI boundary —
team names are interpolated, like `ballot_columns`, `render.py:128-151`). The engine's own
`ValueError` (`swiss.py:219-222`) stays as the last-line defense for a truly malformed dict, but
the UI never reaches it because `validate_lock` runs first.

### D4 — live / dead / secured classification is computed against the CONDITIONAL sample, not the bracket
Define each pick's state precisely against the **post-lock** `Result.sample` and the locked
standings (NOT against the bracket render). A "pick" is a team in the user's chosen ballot in a
specific bucket (3-0 / advance / 0-3), so classification is **per (team, bucket)** against the
matching outcome matrix from `build_outcome_matrices` (`engine/optimizer.py:111-130`, reuse it —
it already yields `is_30`/`is_adv`/`is_03` boolean arrays over the sample):

- **secured** (`/`, blue) — the pick's outcome is already GUARANTEED given the locks:
  `is_<bucket>[team].mean() == 1.0` (P=1). e.g. an advance pick whose team is already 3-0/3-1/3-2,
  or a 0-3 pick whose team is already 0-3.
- **dead** (`x`, amber) — the pick is now IMPOSSIBLE given the locks: `is_<bucket>[team].mean() == 0.0`
  (P=0). e.g. a 3-0 pick whose team already has a loss; a 0-3 pick whose team already has a win;
  an advance pick whose team is already 0-3.
- **live** (`o`, blue) — otherwise (0 < P < 1): the pick is still in play.

This **reuses the existing `STATUS` palette verbatim** (`render.py:33-37`): `STATUS["advanced"]`
= `("/", "secured", blue)`, `STATUS["live"]` = `("o", "live", blue)`, `STATUS["eliminated"]` =
`("x", "dead", amber)`. The classifier returns the STATUS key per pick; the UI passes it to the
existing `status_badge_html` (`render.py:82-99`). **No new palette, no red/green** (UI-06).

```python
def classify_pick(team_id: int, bucket: str, matrices: Matrices) -> str:
    # bucket in {"picks_30","picks_adv","picks_03"}; returns "advanced"|"eliminated"|"live"
    is_30, is_adv, is_03 = matrices
    arr = {"picks_30": is_30, "picks_adv": is_adv, "picks_03": is_03}[bucket][team_id]
    p = float(arr.mean())
    if p >= 1.0: return "advanced"   # secured
    if p <= 0.0: return "eliminated" # dead
    return "live"
```

Edge note: P=1/P=0 are EXACT here because the conditional sample is degenerate for a locked-out
team (every sim shares the locked prefix). Use exact `== 1.0` / `== 0.0`, not an epsilon — a team
not yet locked-out always has 0<P<1 at any reasonable N. (If a future fully-locked stage makes a
LIVE team coincidentally hit P=1.0 at finite N before being mathematically secured, that is still
correct: at that point it IS secured given the realized locks feeding the sample.)

### D5 — The P(≥5)-from-here delta REUSES `optimizer.p_ge5`, anchored on the user's CHOSEN ballot, computed as (pre-lock Result) vs (post-lock Result)
The delta arrow `71% → 58%` (RESIM-02, HANDOFF §10.5 line 324) is **two `p_ge5` calls on the
SAME ballot against TWO samples**:

- **before** = `p_ge5(anchor_ballot, build_outcome_matrices(pre_lock_result.sample, ids))`
- **after**  = `p_ge5(anchor_ballot, build_outcome_matrices(post_lock_result.sample, ids))`

**Which ballot anchors the delta:** the **recommended ballot (Ballot B)** computed at the
PRE-LOCK Run (`OptimizerOutput.recommended`, `engine/optimizer.py:293`). Rationale: the user
committed their real Pick'Em to one ballot before the stage; the live question is "how is *my
locked-in ballot* doing as results come in," so the anchor must NOT re-optimize per round (that
would change which 10 teams the % refers to and make the arrow meaningless). Lock the anchor at
the first Run; the delta tracks that fixed ballot. (Stretch, Claude's discretion: let the user
pick A vs B as the anchor via a radio — but default and ship B.)

Both Results come from the EXISTING cache: pre-lock is the `cache_key` with `locked_key == ()`;
post-lock is the current `cache_key`. The pre-lock Result is already in the session cache if the
user Ran pre-stage first (the natural flow); if not, compute it once on the empty-locked key.
This fills the `_hero_slot` placeholder (`app.py:328-341`) that Phase 2 explicitly reserved for
"the Phase-4 P(>=5) from here delta" and Phase 3 left for Phase 4 (`03-RESEARCH.md` D5).

### D6 — The record-bucket bracket is derived by REPLAYING the engine with the current `locked`, reading `pairings_out` + standings (RESIM-04)
This is the central reuse. To know **which pairings exist at round R** (the validator's
`legal_pairings`, D3) AND to render the **record-bucket columns**, call the proven engine:

```python
def derive_bracket(teams, locked, S) -> BracketView:
    pairings_out: list[list[frozenset]] = []
    by_id = simulate_stage(_fresh_teams(teams), None, S, _rng,
                           locked, pairings_out=pairings_out)
    # pairings_out[r] = the pairings the engine GENERATED in round r given locks-so-far
    # by_id[tid].(wins,losses,opps) = each team's standing after the (partially locked) stage
```

`pairings_out` is the existing observability seam (`engine/swiss.py:232,275-296` — keyword-only,
default `None` = no behavior change; the SAME path the GATE-01 backtest asserts on,
`test_backtest_budapest_2025.py:91-94`). Two replay modes:

- **Validator `legal_pairings` for round R:** replay with ONLY the locks for rounds `< R`, read
  `pairings_out[R]` → the set of `frozenset` pairs the format dictates this round. Unlocked
  matches in `pairings_out[R]` get a deterministic winner only if locked; otherwise the replay
  samples them — but we only READ the *pairings* (which are determined by start-of-round
  standings, independent of who wins the unlocked games at round R). For rounds whose inputs are
  fully locked, the pairings are exact; this is what the validator needs.
- **Bracket render:** lay out **columns by W-L record** — `0-0 → 1-0 / 0-1 → 2-0 / 1-1 / 0-2 →
  2-1 / 1-2 → … → 3-0 (adv) / 0-3 (elim)` (HANDOFF §10.5 line 336). Place each team in its
  current-record column from the replay standings; draw each locked result as a **solid** edge/row
  and each not-yet-locked (simulated-only) pairing **faint** (`opacity` ~0.5 in the inline HTML,
  reusing the `render.py` style idiom). **NOT a tree** (line 338-339: "Swiss teams reconverge by
  record, so a tree misrepresents the format").

Streamlit layout: one `st.columns(...)` per record bucket (the HLTV column convention maps
directly onto Streamlit columns), each column a vertical stack of team chips; or a single
`st.markdown(..., unsafe_allow_html=True)` flex row of bucket-`<div>`s (mirrors
`ballot_columns`, `render.py:154-168`) for tighter control of the solid/faint styling. Prefer the
HTML-flex approach so the solid-vs-faint distinction is a clean `opacity` swap and team names are
`html.escape`-d (XSS, like `_ballot_card_html`). Replace the Phase-2 placeholder
`_render_bracket` (`app.py:272-287`, currently "seeded Round 1 table only").

### D7 — `derive_bracket` and the validator replay are CHEAP (one stage sim, no N-loop) — call them per rerun, no cache needed
A single `simulate_stage` call is microseconds (it's the inner body the MC runs N times). The
bracket/validator replays are ONE call each, not N — so they need no `@st.cache_data` and can run
on every Streamlit rerun without latency concern. The expensive thing (the N-sim MC) is already
cached on `locked_key`. This keeps the bracket always-fresh against the live locks with zero cache
bookkeeping. (Use a fixed throwaway rng — `np.random.default_rng(0)` — since for the validator we
read pairings, not sampled winners; for the bracket render, standings of locked teams are
deterministic and unlocked teams aren't drawn in the bracket render path.)

## Engine seams already in place (NO engine change needed)

- `simulate_stage(teams, ratings, S, rng, locked, *, pairings_out=None)` — honors `locked`
  deterministically (`_play`, `swiss.py:202-229`); records locked matches in `opps` so no-rematch
  respects locked history; `pairings_out` reproduces the round-by-round pairing sequence
  (`swiss.py:275-296`). **This single function answers D2, D6, and the validator's `legal_pairings`.**
- `freeze_locked` + `locked_key` in `run_mc_cached` AND in `app.py`'s session cache tuple —
  re-sim fires for free (D1/D2). The Phase 2×4 seam is honored; verified `ui/cache.py:47-65`,
  `app.py:305-308`.
- `engine.optimizer.p_ge5(ballot, matrices)` + `build_outcome_matrices(sample, ids)` —
  reused verbatim for the delta (D5) and classification (D4). No optimizer change.
- `OptimizerOutput.recommended` / `.recommended_pge5` — the anchor ballot + pre-lock hero (D5).
- `ui.render.STATUS` / `status_badge_html` / `hero_number_html` — the LIVE status chips + delta
  hero reuse the existing colorblind-safe palette (D4); no new tokens.
- `app.py` LIVE-mode block (lines 413-442) — already stubs "Your picks — status" (line 416),
  `_hero_slot` (line 427), the status legend (line 428-431), "Delta probabilities" (line 433),
  and `_render_bracket` (line 442). Phase 4 fills these stubs; the shell exists.

**No change to `engine/montecarlo.py`, `engine/swiss.py`, `engine/probs.py`, or
`engine/optimizer.py`.** New file `engine/live.py` (validator + classifier + delta + bracket
derivation, all pure) + `tests/test_live.py`; UI wiring in `app.py` + small additions to
`ui/state.py` (the `KEY_LOCKED` constant + lock-list helpers) and `ui/render.py` (bracket HTML).

## Risks / pitfalls

| Risk | Mitigation |
|------|------------|
| **Stale pre-lock distributions in Live (Pitfall 13)** — the headline Phase 2×4 bug | `locked_key` is already a REAL cache-key arg (verified `ui/cache.py:49`, `app.py:308`); the derived dict (D1) flows through it. Detection test: locking a result moves ≥1 P(advance) (RESIM-01). |
| Re-deriving round-R pairings by hand in the UI (would re-introduce the GATE-01 seed/Buchholz blind spot) | NEVER re-derive — replay `simulate_stage` and read `pairings_out` (D6). The UI asks the proven engine. |
| Assuming `id == seed` in the validator/classifier | Key everything on `id`; look names up by id (like `app.py:367-371`). |
| Classifying against the bracket render instead of the conditional sample | Classify against `build_outcome_matrices(post_lock.sample)` P=1/P=0 (D4) — the sample is the contract, like Phase 3. |
| The delta re-optimizing the ballot per round (arrow becomes meaningless) | Anchor on a FIXED ballot (`recommended` at first Run); both arms call `p_ge5` on the SAME ballot, two samples (D5). |
| Drawing the bracket as a TREE | Record-bucket COLUMNS only (HANDOFF line 338-339); teams reconverge by record. |
| Impossible lock silently accepted (RESIM-03) | `validate_lock` runs in the engine BEFORE commit, returns a reason string the UI shows via `st.error` and blocks the lock; engine `ValueError` is the last-line defense (D3). |
| Locked winner not in the pair | Caught by `validate_lock` (D3) AND the engine raises (`swiss.py:219-222`). |
| Bracket/validator replay adding MC-scale latency | One `simulate_stage` call each, not N — no cache needed (D7). |
| Status colour drift to red/green | Reuse `STATUS` verbatim (`render.py:33-37`); blue/amber + glyph + label only (UI-06). |

## Test plan (TDD the pure logic; AppTest the UI)

Pure `engine/live.py` (`tests/test_live.py`, TDD — RED first like Phase 1/3):
- `test_locked_dict_derived_from_results` — `(round, w, l)` list → `{frozenset((w,l)): w}`; round-trips.
- `test_validate_lock_rejects_rematch` — a pair already locked → returns the rematch reason.
- `test_validate_lock_rejects_terminated_team` — a 3-0/0-3 team → returns the out reason.
- `test_validate_lock_rejects_non_pairing` — a pair the engine doesn't produce this round → reason.
- `test_validate_lock_rejects_double_booking` — a team in two locks one round → reason.
- `test_validate_lock_accepts_legal` — a real round-R pairing of two active teams → `None`.
- `test_classify_secured_dead_live` **[CRITICAL]** — crafted locks: a guaranteed-advance team →
  `"advanced"`, an already-lost-twice-for-3-0 team → `"eliminated"`, an in-play team → `"live"`
  (asserts P=1/P=0/0<p<1 against the conditional sample).
- `test_pge5_delta_uses_same_ballot` — before/after `p_ge5` on the SAME anchor ballot, two samples;
  the value MOVES after a lock (mirrors RESIM-01/02).
- `test_derive_bracket_pairings_match_engine` — `derive_bracket` round-R `legal_pairings` equal
  `simulate_stage(..., pairings_out=...)[R]` (the replay IS the source of truth).
- `test_locked_winner_deterministic` — reuse/extend `test_locked_results_honored` semantics: a
  locked winner's record is identical across sims at the app boundary.

UI (`tests/test_app.py`, AppTest — element tree + session_state, not pixels):
- `test_live_lock_changes_cache_key` — committing a lock changes the `mc_cache` key vs unlocked.
- `test_live_lock_moves_p_advance` — a locked P(advance) differs from the pre-lock value (RESIM-01).
- `test_impossible_lock_shows_reason` — an illegal lock surfaces an `st.error` with the reason and
  does NOT mutate `mc_cache` (RESIM-03).
- `test_live_status_chips_render` — locked-pick rows show `o live` / `x dead` / `/ secured`
  glyph+label (RESIM-02); bracket renders record-bucket columns, not a tree (RESIM-04).

## Plan split (2 plans, standard granularity — mirrors Phase 3's 03-01 core / 03-02 UI)

- **04-01** — `engine/live.py` pure core: lock-list↔`locked`-dict projection (D1), `validate_lock`
  with all five reject cases + reason strings (D3/RESIM-03), `classify_pick` secured/dead/live
  against the conditional sample (D4/RESIM-02), `pge5_delta` reusing `optimizer.p_ge5` on a fixed
  anchor ballot (D5/RESIM-02), `derive_bracket` replaying `simulate_stage`+`pairings_out` for
  `legal_pairings` + record-bucket standings (D6/RESIM-04) + `tests/test_live.py` (all pure tests
  above, TDD). **No UI, no engine mutation.** TDD-eligible — entirely pure functions over the
  frozen engine.
- **04-02** — UI wiring (LIVE mode): the round-by-round lock controls writing
  `st.session_state[KEY_LOCKED]` and deriving the `locked` dict into the EXISTING
  `cache_key`/`_run_or_serve` path (D1/D2/RESIM-01); the from-here delta filling `_hero_slot`
  (pre→post arrow via `hero_number_html`, D5); per-pick status chips via `status_badge_html`
  (D4); the record-bucket bracket replacing `_render_bracket` with solid-locked/faint-simulated
  columns (D6/RESIM-04); `validate_lock` gating each lock with an `st.error` reason
  (D3/RESIM-03); AppTest coverage. **Wave structure:** 04-01 is one wave (pure, parallel-safe
  tasks: validator, classifier, delta, bracket-derivation each independently TDD-able); 04-02
  depends on 04-01 and is one UI wave (the lock controls + status + delta + bracket are one
  coherent LIVE-mode slice). Dependency: 04-02 → 04-01 (UI consumes the pure core).

---

**Phase 4 key decisions (return value):**
- **D1:** Lock truth = `st.session_state["locked_results"]` ordered `list[(round, winner_id, loser_id)]`; the engine `locked` dict `{frozenset((w,l)): w}` is a DERIVED projection fed through the existing `freeze_locked`→`cache_key` path (`app.py:305-308`, the `locked={}` fill point).
- **D2:** Re-sim "fires for free" — CONFIRMED `locked_key` is a real `@st.cache_data` key arg (`ui/cache.py:49`) AND session-cache-tuple member (`app.py:308`); no engine change. RESIM-01 detection = a locked P(advance) moves; determinism via the `test_locked_results_honored` replay.
- **D3:** Pure `engine.live.validate_lock(...)` rejects rematch / terminated-team / non-pairing / double-booking / winner-not-in-pair with specific reason strings, called BEFORE commit; the UI shows the reason via `st.error` and blocks (RESIM-03). Engine `ValueError` (`swiss.py:219`) is last-line defense.
- **D4:** live/dead/secured = P=1/P=0/0<p<1 of the pick's outcome against the CONDITIONAL `Result.sample` via the reused `build_outcome_matrices` (`optimizer.py:111`); render with the existing blue/amber `STATUS` palette + `status_badge_html` — never red/green (UI-06).
- **D5:** P(≥5)-from-here delta = two `optimizer.p_ge5` calls on ONE FIXED anchor ballot (`OptimizerOutput.recommended`, Ballot B at first Run) — pre-lock sample vs post-lock sample — rendered `before% → after%` into the reserved `_hero_slot` (RESIM-02); the anchor never re-optimizes per round.
- **D6:** The record-bucket bracket AND the validator's per-round `legal_pairings` are DERIVED by replaying `simulate_stage(..., pairings_out=[])` with the current partial `locked` (the proven GATE-01 path) — record COLUMNS (`0-0→…→3-0/0-3`), locked solid / simulated faint, never a tree (RESIM-04). D7: these replays are one stage sim each (not N), so no cache needed.
- **Plan split:** 04-01 pure `engine/live.py` (validator + classifier + delta + bracket-derivation, TDD) → 04-02 LIVE-mode UI wiring (lock controls + status chips + delta hero + record-bucket bracket, AppTest). No engine mutation — all Phase 1×2×3 seams verified honored.
