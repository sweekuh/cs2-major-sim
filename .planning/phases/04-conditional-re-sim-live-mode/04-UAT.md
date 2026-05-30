---
status: testing
phase: 04-conditional-re-sim-live-mode
source: [04-02-SUMMARY.md]
started: 2026-05-30T04:57:08Z
updated: 2026-05-30T04:57:08Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

number: 6
name: Impossible lock is blocked + round progression (RESIM-03)
expected: |
  Lock out the rest of Round 1 → Round 2 controls appear (round-gated), offering
  only legal record-grouped pairings. You cannot lock a rematch or a team already
  3-0/0-3; an illegal attempt surfaces a reason and changes nothing.
awaiting: user response

## Tests

### 1. Cold Start Smoke Test
expected: Launch from scratch — app boots without errors, Pre-stage Run resolves the sim to a per-team P(advance)/P(3-0)/P(0-3) table, zero config.
result: PASS — server booted clean on :8501 (no errors); user confirmed Pre-stage Run resolves.

### 2. Enter Live mode
expected: Toggle Pre-stage → Live. The main column reorders and shows the LIVE empty state ("Lock a result to go live.") before any lock — no crash, the fail-soft "live odds off" info banner is fine.
result: PASS — Live toggle active; layout reordered (Ratings left, Lock results right); empty state + correct caption + blue/amber legend render. Bonus: R1 pairings correctly N-vs-N+8 against confirmed Cologne seeds (M80=6, NRG=9, Liquid=13).

## Observations (non-blocking)

### OBS-1 — Toggling Pre-stage/Live mid-Run aborts the in-flight sim (severity: low, UX)
expected-ideal: A running sim survives or visibly resumes when the user flips the mode toggle.
actual: Switching mode mid-compute interrupts the in-flight `_drive_progress` run (Streamlit reruns top-to-bottom on any widget change). No data-correctness impact; a *completed* run is cached by `(ratings,S,N,locked)` and re-served instantly on toggle. Pre-existing since Phase 2 (mode toggle is not Phase-4 code), amplified by the user's N=1,000,000 (~2-3 min/run).
disposition: Logged as low-severity UX papercut, inherent to Streamlit. Candidate future polish (e.g. disable mode toggle while a compute is in flight, or a "run interrupted" note). NOT a Phase 4 blocker.

### ISSUE-1 — "Delta probabilities" table shows ABSOLUTE post-lock values, not deltas (severity: medium, UX/labeling)
found-during: Test 3 (lock GamerLegion over NRG)
expected: A section titled "Delta probabilities" should show how each team's odds CHANGED from pre-lock (before→after, or ↑/↓ vs the unlocked baseline).
actual: `app.py:642-649` — the "Delta probabilities" subheader renders `_render_probs_table(result)`, the SAME absolute-value table as Pre-stage, just re-simmed conditioned on the lock. No per-team delta is shown. The only true delta in the UI is the hero P(≥5) arrow (93.2% → 94.4%), which works. User reported "I can't really tell what changed" — the header promises a delta the content doesn't deliver.
diagnosis: The feature (conditional re-sim) is correct — numbers DID move (GamerLegion P(3-0) ~55% → 84.4%, P(advance) → 99.9% after winning R1). Only the per-team SECTION is mislabeled/under-delivers. RESIM-01/02 are technically satisfied (re-sim fires + hero delta arrow), so this is a UX gap, not a requirement failure.
fix-options:
  A. Rename the subheader to "Conditional probabilities (after locks)" — cheapest, removes the false promise (~1 line).
  B. Render a true per-team delta: pass the pre_lock_result into the table and show before→after or a signed ↑/↓ vs pre-lock per cell — fully delivers on the "Delta" label (small feature add).
disposition: RESOLVED (Fix B) — commit on phase-4-live-mode. Added `delta_tag_html` (signed +/-pp, blue-up/amber-down, ASCII, XSS-numeric-only) + `_render_delta_table` showing each post-lock cell PLUS its change vs the pre-lock baseline. +3 tests (2 render, 1 AppTest); full suite 88 passed; GATE-01 green. Awaiting user re-test in browser.

### ISSUE-2 — Round-gating is correct but undiscoverable; user got stuck (severity: medium, UX)
found-during: Test 6 (locked 2 of 8 R1 games, couldn't find Round 2)
expected: Clear signal that Round 2 opens only after ALL of Round 1 is locked, plus progress (e.g. "Round 1 — 2 of 8 locked").
actual: Round-R+1 controls are gated on round R being fully locked (CORRECT — legal_pairings_for_round needs a complete prefix or raises LivePrefixIncomplete). But the UI gives no progress indicator or "lock all of Round 1 to continue" hint, so the user locked 2 games, saw 6 remaining pairings, and assumed Round 2 was missing/broken (even re-ran the sim trying to "clear it"). The gating WORKS; it's just opaque.
diagnosis: Not a correctness bug — the engine/gating is right and the dead-state classification fired correctly (GamerLegion 3-0 pick → "x dead", hero 93.3%→80.2%). Pure discoverability gap in the lock-controls UX.
fix-options:
  A. Add a progress caption under "Lock Round N results": "Round N — {locked}/{total} locked. Lock all to open Round N+1." (~few lines, high value).
  B. Also show locked games as a struck-through/checked list so the user sees what's done vs remaining.
disposition: RESOLVED (Fix A) — added "Round N: X of M matches locked — lock all M to open the next round." caption under the lock controls + refreshed the stale Pre-stage bracket caption (verifier concern 3). +1 AppTest; full suite 89 passed; GATE-01 green.

## Tests

### 3. Lock a Round 1 result → re-sim fires
expected: In Live mode, lock a winner for a Round 1 pairing. The probabilities recompute conditioned on that lock — at least one team's P(advance) visibly moves vs the pre-lock numbers (the locked winner trends up, its opponent down).
result: PASS (Fix B applied) — re-sim fired (GamerLegion P(advance)→99.9%, P(3-0)→84.4%); hero delta 93.2%→94.4%; per-team change now legible via signed +/-pp tags (ISSUE-1 resolved).

### 4. From-here P(≥5) delta arrow
expected: After locking, the hero shows `before% → after%` for the fixed recommended ballot.
result: PASS — observed 93.2% → 94.4% in user screenshot.

### 5. live / dead / secured status chips
expected: Ballot picks show blue/amber glyph+label chips, never red/green.
result: PASS — chips grouped by 3-0/Advance/0-3, all 'o live' blue (correct with 1 lock); legend renders.

### 6. Impossible lock is blocked (RESIM-03)
expected: The lock controls only offer legal pairings for the round — you cannot lock a rematch or a team already 3-0/0-3. If an illegal lock is attempted it surfaces a plain-English reason and nothing changes.
result: [pending]

### 7. Record-bucket bracket (RESIM-04)
expected: The bracket renders as record COLUMNS (0-0 → 1-0 / 0-1 → … → 3-0 advanced / 0-3 eliminated), NOT a tree. Locked/real results are solid; simulated-only branches are faint.
result: [pending]
