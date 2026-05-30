---
phase: 04-conditional-re-sim-live-mode
verified: 2026-05-29T00:00:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification: null
gaps: []
human_verification: []
---

# Phase 4: Conditional Re-Sim + Live Mode — Verification Report

**Phase Goal:** Lock real results round by round, re-simulate conditioned on standings/Buchholz/rematch history, and show each locked pick as live/dead/secured with a P(>=5)-from-here delta, rendered over a record-bucket bracket.
**Verified:** 2026-05-29
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Test Suite Results

```
85 passed in 70.74s
```

**GATE-01 (Budapest 2025 backtest):**
```
3 passed in 0.10s   [tests/test_backtest_budapest_2025.py]
```
GATE-01 stayed green.

**No-engine-mutation check:**
```
git diff --stat master..HEAD -- engine/
engine/live.py | 316 +++++++++++++++++++++++++++++++++++++++++++++++++++++++++
1 file changed, 316 insertions(+)
```
`engine/swiss.py`, `montecarlo.py`, `optimizer.py`, `probs.py`, `teams.py` — zero diffs. The engine is frozen.

---

## Goal Achievement

### Observable Truths (RESIM Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | **RESIM-01** Locking a round result fires conditional re-sim via the `locked` cache key; locked winners are deterministic and at least one P(advance) moves | VERIFIED | `app.py:354` reads `locked_dict(st.session_state.get(KEY_LOCKED, []))` and passes it to `_compute_or_serve` which calls `_cache_key_for` -> `freeze_locked(locked)` as the 4th cache-key component. `tests/test_app.py::test_live_lock_changes_cache_key` (PASS) asserts a new mc_cache entry with non-empty `k[3]` appears; `test_live_lock_moves_p_advance` (PASS) asserts at least one P(advance) shifts. Both AppTests pass. |
| 2 | **RESIM-02** Each locked pick displays as live/dead/secured with a P(>=5)-from-here delta arrow (`71% -> 58%`), showing the CHANGE not a static number | VERIFIED | `engine/live.py:181-203` (`pge5_delta`) calls `p_ge5` twice on a FIXED anchor ballot against pre-lock and post-lock samples. `app.py:381-399` (`_render_live_hero`) renders `before -> after` via `hero_number_html`. Per-pick chips via `_render_status_chips` (app.py:506-527) call `classify_pick` -> `status_badge_html`. `tests/test_app.py::test_live_status_chips_render` (PASS) asserts `/ secured`, `o live`, `x dead` glyphs render. `test_live_delta_anchor_uses_pre_key` (PASS) proves anchor never re-optimizes and `before` equals `p_ge5(anchor, pre_result.sample)`. |
| 3 | **RESIM-03** An impossible locked pairing is rejected with a reason, not silently accepted | VERIFIED | `engine/live.py:82-148` (`validate_lock`) checks five rejection conditions: winner-not-in-pair, rematch, terminated-team (ADVANCE_AT_WINS / ELIMINATE_AT_LOSSES from engine.teams), non-pairing, double-booking. `app.py:426-449` (`_commit_lock`) calls `validate_lock` and on non-None reason calls `st.error(reason)` without mutating `KEY_LOCKED` or `mc_cache`. `tests/test_live.py` has four explicit rejection tests all PASSING. `tests/test_app.py::test_impossible_lock_shows_reason` (PASS) confirms `st.error` fires with "no rematches", KEY_LOCKED and mc_cache unchanged. |
| 4 | **RESIM-04** Bracket renders as record-bucket columns (never a tree) with locked results solid and simulated branches faint | VERIFIED | `ui/render.py:193-231` (`bracket_columns_html`) emits `display:flex` row of `<div data-bucket=...>` columns keyed on `_BRACKET_BUCKETS` (10 canonical record states). Locked team chips use `opacity:1`, simulated-only `opacity:0.5`. No tree/connector markup. `tests/test_app.py::test_live_status_chips_render` (PASS) asserts `0-0`, `3-0 adv`, `display:flex`, no `tree`. `test_bracket_columns_html_is_columns_not_tree` (PASS) asserts `opacity:1`, `opacity:0.5`, html-escaped names (`&lt;script&gt;B8`), `display:flex`, `3-0 adv`, `0-3 elim`. `app.py:530-539` (`_render_bracket_live`) derives `BracketView` via `derive_bracket` (engine replay) and calls `bracket_columns_html`. |

**Score: 4/4 truths verified**

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `engine/live.py` | D1/D3/D4/D5/D6 pure core, no engine mutation | VERIFIED | 316 lines. Exports: `locked_dict_from_results`, `validate_lock`, `classify_pick`, `pge5_delta`, `derive_bracket`, `BracketView`, `legal_pairings_for_round`, `LivePrefixIncomplete`. |
| `tests/test_live.py` | 11 pure-core tests covering all D contracts | VERIFIED | All 11 tests pass. Covers D1 (dict round-trip), D3 (4 rejection cases + accept), D4 (exact p==1.0/0.0), D5 (two p_ge5 on fixed anchor), D6 (bracket replay + prefix incomplete + locked determinism). |
| `ui/state.py` | KEY_LOCKED + lock-list helpers | VERIFIED | `KEY_LOCKED`, `KEY_LIVE_ANCHOR`, `KEY_PENDING_LOCK` constants. `add_lock`, `remove_last_lock`, `locks_for_round`, `locked_dict` helpers. All pure (no streamlit). |
| `ui/render.py` | `bracket_columns_html` record-bucket columns | VERIFIED | Lines 171-231. Solid (opacity:1) locked chips, faint (opacity:0.5) simulated chips, html-escaped names. |
| `app.py` | LIVE mode wiring: lock controls, delta hero, status chips, bracket | VERIFIED | All five wiring jobs from 04-02-PLAN complete: lock controls (lines 451-503), `_live_anchor` (359-378), `_render_live_hero` (381-399), `_render_status_chips` (506-527), `_render_bracket_live` (530-539). |
| `tests/test_app.py` | 6 Phase 4 AppTests + 1 pure bracket test | VERIFIED | `test_live_lock_changes_cache_key`, `test_live_lock_moves_p_advance`, `test_impossible_lock_shows_reason`, `test_live_status_chips_render`, `test_live_delta_anchor_uses_pre_key`, `test_bracket_columns_html_is_columns_not_tree` — all pass. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app.py LIVE controls` | `ui.cache.freeze_locked / cache_key` | `locked_dict(KEY_LOCKED)` -> `freeze_locked` in `_cache_key_for` | WIRED | `app.py:354` reads `KEY_LOCKED`, calls `locked_dict()` which delegates to `engine.live.locked_dict_from_results`. `app.py:310` calls `freeze_locked(locked)` as key component 4. |
| `engine.live.derive_bracket` | `engine.swiss.simulate_stage` | replay with partial locked + `pairings_out=[]` | WIRED | `live.py:258` calls `simulate_stage(_fresh_teams(teams), None, S, rng, dict(locked), pairings_out=pairings_out)`. |
| `engine.live.classify_pick / pge5_delta` | `engine.optimizer.build_outcome_matrices / p_ge5` | reuse Phase 3 scorers against `Result.sample` | WIRED | `live.py:34` imports both. `classify_pick` calls `matrices[_BUCKET_INDEX[bucket]][team_id].mean()`. `pge5_delta` calls `build_outcome_matrices` then `p_ge5` twice. |
| `engine.live.validate_lock` | `engine.teams (ADVANCE_AT_WINS / ELIMINATE_AT_LOSSES)` | terminated-team check | WIRED | `live.py:36` imports `ADVANCE_AT_WINS, ELIMINATE_AT_LOSSES`. Used at `live.py:126`. |
| `app.py _hero_slot (LIVE)` | `engine.live.pge5_delta` | `before/after` p_ge5 on fixed anchor -> `hero_number_html` arrow | WIRED | `app.py:389` calls `pge5_delta(anchor, pre_lock_result, post_lock_result, ids)`, result rendered via `hero_number_html` at `app.py:392-396`. |

---

### Blocker-2 Correctness Fix (LivePrefixIncomplete)

`legal_pairings_for_round` at `engine/live.py:269-316` enforces the full-locked-prefix precondition: it iterates prior rounds and raises `LivePrefixIncomplete` if any round `r < round_idx` is not fully locked (engine-generated pairings != locked pairings). `test_legal_pairings_requires_full_prefix` (PASS) asserts:

- Full R1 prefix -> R2 pairings returned, non-empty, RNG-invariant (same set across two differently-seeded calls), equal to actual Budapest R2 pairs.
- Incomplete prefix (one R1 entry dropped) -> `LivePrefixIncomplete` raised.

UI round-gating: `app.py:403-423` (`_open_round_idx`) probes rounds upward via `legal_pairings_for_round` — if it raises, it returns the previous round as "open". Lock controls only call `legal_pairings_for_round` on the open round, which by construction has a fully-locked prefix. The precondition is never violated in the normal UI path.

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `_render_live_hero` | `before, after` from `pge5_delta` | `pre_lock_result.sample` + `post_lock_result.sample` from mc_cache (real MC runs) | Yes — both samples come from `run_mc_progressive` or `run_mc`, not static | FLOWING |
| `_render_status_chips` | `matrices` from `build_outcome_matrices` | `post_lock_result.sample` from mc_cache (real MC run conditioned on locks) | Yes | FLOWING |
| `_render_bracket_live` | `BracketView` from `derive_bracket` | `engine.swiss.simulate_stage` replay with current locks | Yes — engine replay uses actual standings | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite passes | `uv run pytest -q` | 85 passed in 70.74s | PASS |
| GATE-01 Budapest backtest | `uv run pytest -q tests/test_backtest_budapest_2025.py` | 3 passed in 0.10s | PASS |
| Phase 4 pure-core tests | `uv run pytest -q tests/test_live.py -v` | 11 passed in 0.12s | PASS |
| Phase 4 AppTests (live filter) | `uv run pytest -q tests/test_app.py -k "live"` | 4 passed in 4.16s | PASS |
| Phase 4 AppTests (bracket/delta/lock/anchor) | `uv run pytest -q tests/test_app.py -k "bracket or delta or lock or anchor"` | 7 passed in 4.71s | PASS |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `app.py` | 175-178 | Stale caption: `"(Result locking lands in Phase 4.)"` — Phase 2's placeholder copy; locking IS implemented in the same branch | Info | Cosmetic only. The LIVE mode `else` branch at line 611+ fully implements locking. No functional impact. |

No TBD, FIXME, or XXX markers found in any `.py` file. No empty stubs, no hardcoded empty data in render paths.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| RESIM-01 | 04-02-PLAN | Locking fires conditional re-sim via `locked` cache key; P(advance) moves | SATISFIED | `app.py:354`, `freeze_locked` key path, `test_live_lock_changes_cache_key`, `test_live_lock_moves_p_advance` |
| RESIM-02 | 04-01-PLAN, 04-02-PLAN | live/dead/secured chips + P(>=5) delta arrow | SATISFIED | `classify_pick`, `pge5_delta`, `_render_live_hero`, `_render_status_chips`, five AppTests |
| RESIM-03 | 04-01-PLAN, 04-02-PLAN | Impossible locks rejected with reason | SATISFIED | `validate_lock` (5 rejection modes), `_commit_lock` st.error gate, `test_impossible_lock_shows_reason` |
| RESIM-04 | 04-01-PLAN, 04-02-PLAN | Record-bucket bracket columns, never tree | SATISFIED | `bracket_columns_html`, `derive_bracket`, `test_bracket_columns_html_is_columns_not_tree`, `test_live_status_chips_render` |

---

### Human Verification Required

None — all Phase 4 behaviors are verifiable programmatically via pytest and static code inspection.

---

### Gaps Summary

No gaps. All four RESIM criteria are verified with direct code evidence and passing tests.

---

_Verified: 2026-05-29_
_Verifier: Claude (gsd-verifier)_
