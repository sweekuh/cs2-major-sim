---
phase: 06-multi-stage-scaffold-live-results-seam
reviewed: 2026-06-05T00:00:00Z
depth: deep
files_reviewed: 9
files_reviewed_list:
  - ui/cache.py
  - engine/teams.py
  - app.py
  - ui/results_loader.py
  - scripts/fetch_results.py
  - ui/state.py
  - data/stage2.json
  - data/stage3.json
  - data/playoffs.json
findings:
  blocker: 0
  high: 2
  medium: 2
  low: 3
  total: 7
status: resolved
resolved: 2026-06-05
---

> **RESOLUTION (2026-06-05):** All 7 findings fixed test-first (each regression test failed pre-fix, passed post-fix). Commits `76e2e4f`/`e94f62d`/`c3eedb5`/`1a969df`/`48bca75`/`a5d1414`. Suite 147 → 154 (+7 tests); GATE-01 green; freeze companion green; frozen bodies still 0-deletions. HI-01's multi-round reverse-order prefill test (`test_reverse_round_results_prefill_in_one_pass`) closes the untested path that would have silently fed Phase 7 incomplete seeds.

# Phase 6: Code Review Report — Multi-stage scaffold + live-results seam

**Reviewed:** 2026-06-05
**Depth:** deep (cross-file: app.py ↔ ui/cache.py ↔ scripts/fetch_results.py ↔ engine/live.py)
**Files Reviewed:** 9 (Python + the 3 new committed fixtures)
**Status:** issues_found
**Suite:** 147 passed (full run, 4m18s). GATE-01 (`test_backtest_budapest_2025`) GREEN.

## Summary

This was a deliberately adversarial pass over the Phase 6 diff (`a5fe9c0..HEAD`), weighted toward
correctness (a wrong lock silently corrupts every downstream probability AND the Phase-7 seeding
chain). The directed-hunt list was checked item by item.

**The good news — the load-bearing seams are correct:**

- **Cache-key correctness (STG-04): SOLID.** `stage_id` is a REAL leading positional in BOTH
  `run_mc_cached` and `optimize_cached`, and `_cache_key_for` produces
  `(stage_id, ratings_key, S, int(N), locked_key, fetched_at)` in the exact order `optimize_cached`'s
  params (after `_result`) expect for the `optimize_cached(result, *cache_key)` splat. No
  `_arg` underscore-escape on `stage_id`. A stage switch cannot serve the prior stage's Result.
- **Frozen-path / freeze regression: CLEAN.** Zero edits to `swiss.py`, `montecarlo.py`, `probs.py`,
  `live.py`, `optimizer.py`. The GATE-01 frozen functions in `teams.py`
  (`_validate_fixture` / `_teams_from_rows` / `load_teams` / `_DEFAULT_FIXTURE` / `STAGE_SIZE`) are
  byte-identical — the diff only ADDS the sibling block (lines 143-202). GATE-01 verified green.
- **validate_lock bypass: NONE.** Every fetched lock (prefill path AND conflict-confirm path) routes
  through `legal_pairings_for_round` → `validate_lock` → `add_lock`. No path adds a lock directly.
- **Conflict-confirm atomicity (the single-conflict case): CORRECT.** `_apply_fetched_conflict`
  builds `prospective` on a copy, validates BEFORE any mutation, and only reassigns
  `st.session_state[KEY_LOCKED]` on `validate_lock == None`. An engine-illegal fetched lock leaves
  the manual lock fully intact (verified by `test_conflict_confirm_validates_before_remove`).
- **int-vs-str (T-06-12): RECONCILED on both sides.** No residual raw `_meta.stage == stage_id`
  compare anywhere; the only comparison is `int(_meta.stage) != _stage_int_for(stage_id)` (both ints).
  The fetcher writes via `_stage_number`, the reader filters via `_stage_int_for` — they agree on all
  four stages.
- **Secret leakage (PANDASCORE_KEY): NONE found.** The key is read only in `_live_fetch`, placed in
  an `Authorization` header (never a `?token=` URL param), `httpx`/`httpcore` loggers are forced to
  WARNING at the top of `main` BEFORE any fetch, and the value never reaches the cache file
  (`_meta.source` is the provider name, not the key) nor the fail-soft `log.warning(... exc)` (the
  exception repr carries the URL/status, not headers). `.env.example` ships an empty `PANDASCORE_KEY=`.
- **Fail-soft loader: CORRECT.** `ui/results_loader.py` is json+pathlib only (no httpx — verified by
  AST test), four-branch fail-soft to `None` (missing / malformed / non-dict / wrong-version).

**The concerns** are all in the live-results *application* layer (the prefill loop and the
provenance UI), not the cache key or the engine. Two are HIGH because they will mis-handle the exact
real-world data Cologne produces (multi-round, reverse-chronological, occasionally provider-revised),
and every one of those is silent.

---

## High

### HI-01: Single-pass prefill silently drops later-round results when the cache is in reverse-round order

**File:** `app.py:885-918` (`_prefill_results_into_locked`), interacting with
`scripts/fetch_results.py:298-301` (bo3.gg `sort=-start_date`) and `engine/live.py:269-287`
(`legal_pairings_for_round` prefix precondition).

**Issue:** The prefill loop is a **single pass** over `results["results"]` in cache order, but
`legal_pairings_for_round` raises `LivePrefixIncomplete` unless **every** round `r < round_idx` is
already fully locked. The loop catches that and `continue`s (drops the row). The live bo3.gg fetch
sorts `-start_date` (newest first → **reverse round order**), and the fetcher appends rows in
provider order without sorting. So on the run that ingests a multi-round cache, the loop hits R5/R4/R3
rows *first* against a still-empty lock list, the prefix guard raises, and those rows are dropped;
only R1 (and whatever happens to be order-satisfiable) locks this pass. R2+ require a *subsequent
rerun* each (one round of progress per rerun), and there is no self-driving rerun loop after the
fetch's single `st.rerun()` — convergence depends on the user clicking around. The net effect: after
"Fetch latest results", the bracket can show only Round 1 locked even though the cache holds R1-R5,
with no error and no indication that rows were dropped.

Every existing test (`test_fetched_results_prefill_locked`, `test_fetch_conflict_*`,
`test_provenance_*`) uses **only single R1 rows**, so this is entirely untested and will first appear
against real Cologne data.

**Fix:** Sort the rows by `round_idx` before the loop so the prefix is always built in order
(belt-and-suspenders: do it at write time in the fetcher too). Minimal change at the read side:

```python
rows = results.get("results") or []
# Lock in ROUND ORDER so legal_pairings_for_round's "all prior rounds fully locked" precondition
# is satisfied in ONE pass — the live bo3.gg feed is reverse-chronological (sort=-start_date), so an
# unsorted pass drops every R2+ row until later reruns. round_idx is validated by _row_to_pending.
rows = sorted(
    (r for r in rows if _row_to_pending(r) is not None),
    key=lambda r: _row_to_pending(r)[0],
)
for row in rows:
    ...
```

(Alternatively, sort `results` by `round_idx` in `scripts.fetch_results.main` before writing the
cache — preferred, since it also makes the persisted artifact deterministic and human-readable.)

---

### HI-02: A provider-revised result for an already auto-locked pair is silently ignored (auto-lock never self-corrects)

**File:** `app.py:895-904` (`_prefill_results_into_locked`, the `existing is not None` branch).

**Issue:** The conflict gate only fires when the existing lock's provenance is `"manual"`
(`prov.get(pair, "manual") == "manual"`). When the existing lock is `"auto"` (from a prior fetch) and
a **later fetch returns the OPPOSITE winner for that pair** (a provider correction, or a bad first
fetch later fixed upstream), the branch falls through to `continue` (line 904) — no conflict stashed,
no overwrite. The stale auto-lock persists indefinitely (until a manual undo), and the corrected
fetched winner is dropped. Given "correctness is the product" and that a wrong lock corrupts every
probability plus the Phase-7 seeding chain, an auto seam that cannot self-correct an auto value is a
real data-integrity gap. There is no path anywhere that updates an existing `"auto"` lock to a new
fetched winner.

**Fix:** When the existing lock is `"auto"` and the fetched winner differs, re-apply the fetched
result through the same validate path (auto results are not user ground truth, so a fresh fetch should
win — no confirm needed). Sketch, replacing the `existing is not None` block:

```python
if existing is not None:
    ex_w = existing[1]
    if ex_w != w:
        source = prov.get(pair, "manual")
        if source == "manual":
            st.session_state[KEY_PENDING_RESULT_CONFLICT] = pending  # needs a human (unchanged)
        else:
            # Auto lock disagreeing with a FRESH fetch -> the provider revised it; re-apply through
            # the SAME validate path (drop the stale auto entry on a COPY, validate, then swap).
            prospective = [e for e in locked_results if e is not existing]
            try:
                legal = legal_pairings_for_round(teams, prospective, S, round_idx)
            except Exception:  # noqa: BLE001
                continue
            if validate_lock((w, ell), round_idx, prospective, teams, legal) is None:
                st.session_state[KEY_LOCKED] = add_lock(prospective, round_idx, w, ell)
                new_prov = dict(prov); new_prov[pair] = "auto"
                st.session_state[KEY_LOCK_PROVENANCE] = new_prov
    continue
```

(If the product decision is instead "auto-locks are sticky," that should be an explicit, documented
choice surfaced in the UI — currently it is an implicit silent drop.)

---

## Medium

### ME-01: Only ONE conflict can be pending at a time — earlier manual conflicts are silently lost

**File:** `app.py:899-904` (`_prefill_results_into_locked`) + `app.py:978-1011`
(`_render_results_conflict`). `KEY_PENDING_RESULT_CONFLICT` is a single scalar key.

**Issue:** The prefill loop overwrites `st.session_state[KEY_PENDING_RESULT_CONFLICT]` on every
conflicting pair. If the fetched cache disagrees with **two or more** manual locks, only the
**last-iterated** conflict survives to be rendered/confirmed; the earlier ones are neither stashed nor
applied — they vanish with no notice. The user confirms one conflict, and the others never resurface
unless a later fetch happens to re-encounter them after re-iteration order changes. With HI-01's
sort fix this becomes deterministic (last by round order) but still drops all-but-one. Multi-conflict
is plausible the moment a user hand-enters several rounds and then fetches.

**Fix:** Make the pending-conflict store a list/dict keyed by pair, and have
`_render_results_conflict` iterate and render one confirm control per pending conflict (each routing
through `_apply_fetched_conflict`). At minimum, if scope must stay single-conflict for this phase,
surface a visible "N more conflicts pending" note so the loss is not silent.

### ME-02: Staleness/provenance banner is NOT stage-scoped — shows "Fetched results: …" on a stage that has no applied results

**File:** `app.py:1024-1035` (`_render_results_provenance`).

**Issue:** `_prefill_results_into_locked` correctly refuses to apply a results cache whose
`_meta.stage` differs from the active stage (lines 882-883). But `_render_results_provenance` reads
the cache independently (`load_results_cache()`) and renders the freshness line ("Fetched results: X
ago" / "may be stale") **without** any stage check. So when a `stage2` results cache exists and the
user is viewing `stage1`, the banner asserts stage1 has fetched results that were in fact filtered
out. This is a misleading-UI / honesty issue (the project's whole thesis is "no false precision"); it
is not a probability corruption (the locks themselves are correct), hence Medium.

**Fix:** Gate the freshness block on the same canonical stage match the prefill uses:

```python
results = load_results_cache()
if results:
    try:
        same_stage = int(results.get("_meta", {}).get("stage")) == _stage_int_for(stage_id)
    except (TypeError, ValueError):
        same_stage = False
    if same_stage:
        fetched_at = results.get("_meta", {}).get("fetched_at")
        ...  # render the freshness line ONLY for the active stage's cache
```

---

## Low

### LO-01: Unused import `load_teams` in app.py

**File:** `app.py:38` — `from engine.teams import load_stage, load_teams`.

**Issue:** Phase 6 replaced the old `teams = load_teams()` with `load_stage(...)`. `load_teams` now
has zero references in app.py (confirmed: no `Name` load nodes, only the import token). Dead import.

**Fix:** Drop `load_teams` from the import: `from engine.teams import load_stage`.

### LO-02: Fetcher `_stage_number` silently defaults unknown stage_id → 1; app's `_stage_int_for` raises

**File:** `scripts/fetch_results.py:88-91` (`.get(stage_id, 1)`) vs `app.py:150-160` (`_stage_int_for`
raises `ValueError`).

**Issue:** The two sides agree for all four real stages, but they disagree on the *unknown* case. Via
the cron entry (`python -m scripts.fetch_results`), a typo'd stage_id would write `_meta.stage = 1`
instead of failing loudly, and the app would then prefill **stage1** with the wrong stage's results
(a fabricated-lock vector). The UI button can't hit this (selector is constrained), so Low — but the
asymmetry is a latent footgun for the documented v2-cron path.

**Fix:** Make `_stage_number` raise on unknown to mirror `_stage_int_for` (single fail-loud contract):

```python
def _stage_number(stage_id: str) -> int:
    order = {"stage1": 1, "stage2": 2, "stage3": 3, "playoffs": 4}
    if stage_id not in order:
        raise ValueError(f"unknown stage_id {stage_id!r}; expected one of {sorted(order)}")
    return order[stage_id]
```

### LO-03: `load_stage` lacks the friendly field-presence guards `load_teams` has (raw KeyError on a malformed fixture)

**File:** `engine/teams.py:185-193` (`load_stage`).

**Issue:** `load_stage` does `raw["teams"]` and `entry["seed"]` / `entry["name"]` / `entry["rating"]`
via direct subscript, so a malformed fixture raises a bare `KeyError`/`TypeError` rather than the
clean `ValueError("... missing required field ...")` the frozen `load_teams` raises (teams.py:122-135).
Today `load_stage` only ever loads committed fixtures via `_path_for_stage` (not user/fetched input),
and the app's top-level `load_stage` call (app.py:109) is unguarded — a corrupt committed fixture
crashes at startup. That fail-loud-on-corrupt-committed-data is defensible, so Low; but the
inconsistent error contract between the twin loaders is a maintainability snag and would bite if
`load_stage` is ever pointed at less-trusted input.

**Fix:** Mirror `load_teams`'s `raw.get("teams")` + per-field presence checks in `load_stage` (raise
`ValueError` with the same messages) so the two loaders fail identically.

---

## Directed-hunt checklist (explicit clean calls)

1. **Cache-key stale-serve on stage switch / fresh fetch:** CLEAN — `stage_id` leads both keys,
   order matches the splat, no underscore-escape, `fetched_at` folded into both run and optimizer
   keys (`test_fetched_at_refires_resim`, `test_stage_id_in_cache_key`).
2. **Conflict-confirm atomicity (single conflict):** CLEAN — validate-before-remove, manual lock
   preserved on engine-illegal fetched lock (`test_conflict_confirm_validates_before_remove`).
   (Multi-conflict loss → ME-01.)
3. **int-vs-str on both write+read sides, no raw `==`:** CLEAN — canonical helpers both sides; no
   residual `_meta.stage == stage_id`. (Unknown-case asymmetry → LO-02.)
4. **Fail-soft on bad/partial input:** CLEAN for the loader (4-branch → None), the fetch button
   (`except Exception` → stashed error, app never crashes), unresolved slug (drop+`log.warning`),
   empty fetch (info, not error), and per-row `_row_to_pending` (drop on malformed). (The latent
   gap is *silent drop of valid later-round rows* → HI-01, a logic bug not a crash.)
5. **PANDASCORE_KEY leakage to log / error / repr / cache:** CLEAN — header-only, loggers→WARNING
   before any fetch, never in cache `_meta`/`source`, never in the fail-soft exc string.
6. **Frozen-path / engine freeze regression:** CLEAN — GATE-01 functions byte-identical, zero edits
   to swiss/montecarlo/probs/live/optimizer, GATE-01 green.
7. **validate_lock bypass:** CLEAN — every fetched lock (prefill + confirm) routes through
   `legal_pairings_for_round` → `validate_lock` → `add_lock`; no direct lock insertion.

---

_Reviewed: 2026-06-05_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
