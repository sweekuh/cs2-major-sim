# Complete Budapest 2025 backtest gate (GATE-01) once authoritative seeds sourced

- **Captured:** 2026-05-29 (during 01-04 execution, at the Task 1 human-verify checkpoint)
- **Status:** DEFERRED (blocked on data)
- **resolves_phase:** (blank — cross-cutting; NOT auto-closed by Phase 1)
- **Related:** GATE-01, GATE-04, GATE-05; threats T-04-01 / T-04-02

## What

Finish the round-by-round backtest that proves the Swiss engine GENERATES Budapest
2025 Stage 1's actual pairings exactly (the hard gate, GATE-01/05), and exercise the
planned GATE-04 priority-table fork against real data. The reconciled RESULTS are
already frozen at `tests/fixtures/budapest_2025_stage1.json`; the missing piece is the
authoritative seeding.

## Why it's deferred (the blocker)

- The authoritative Valve **1-16 seed integers** for Budapest Stage 1 could not be
  sourced. **HLTV is Cloudflare-walled** (event page unreachable via /browse), and
  **Liquipedia/Wikipedia do not publish seed integers** — only the bracket results.
- The HLTV **VRS world-rank order** (recorded in the fixture under
  `vrs_world_rank_order_NOT_seeding`) is NOT a valid substitute: it does not reproduce
  the actual pairings (see the divergence finding below). Asserting a backtest on a
  guessed seeding would be a **false pass/fail** (threat T-04-01).

## The divergence finding (investigate — may be an engine nuance, not just a data gap)

This is the part worth root-causing before fully trusting the engine for Cologne:

- **R1 actual:** M80-B8, Imperial-RareAtom, FlyQuest-Legacy, PARIVISION-TheHuns,
  Fluxo-GamerLegion, NRG-NIP, FaZe-LynnVision, Fnatic-RED.
  Under the VRS world-rank order, the engine's **N-vs-N+8** R1 fold would produce
  Legacy-NIP, B8-LynnVision, FaZe-NRG, ... — completely different. So Budapest R1 is
  NOT a simple seed-offset under the VRS order.
- **R2 "High"** (the 8 R1-winners, no rematch possible, uniform Buchholz -> should be a
  pure seed fold): actual FlyQuest-Imperial, M80-PARIVISION, Fnatic-Fluxo, FaZe-NRG.
  Neither the world-rank order nor the per-card "orange" VRS order reproduces this fold
  (only Fnatic-Fluxo coincidentally lines up under one).

**Two hypotheses, not yet disentangled:**
(a) Budapest's published seed integers differ from both visible HLTV rankings, OR
(b) Valve's within-group pairing has a nuance the engine's difficulty-fold does not
capture (a real engine bug worth fixing before trusting Cologne output).

These cannot be separated without the authoritative seed bracket — hence the deferral.

## Resume path

1. Obtain the **authoritative Valve/HLTV seeded bracket** (the 1-16 seed image, or an
   HLTV fetch once the Cloudflare wall is passable, e.g. via the gstack real-browser
   `/browse` session). Confirm the integers against the announced R1 pairings.
2. Freeze the seeds into `tests/fixtures/budapest_2025_stage1.json` (`seeding` field;
   clear the `seeding_note`).
3. Remove the `@pytest.mark.skip` on `test_backtest_budapest_2025` and implement the
   real assertion: feed the 16 seeds + per-round `locked` winners and assert the engine
   reproduces every round's pairings exactly (the same pinned-chunk path the app ships).
4. **GATE-04 fork:** on any divergence, do NOT loosen the assertion — root-cause it
   (Buchholz formula, difficulty-rank fold key, or rematch resolution) and replace the
   greedy fold with the literal verbatim `PRIORITY_TABLE` lookup at the diverging group
   size (extend the table oracle to 8-team buckets if a divergence lands there).
5. Use the result to decide hypothesis (a) vs (b) above. If (b), the engine fold needs
   a fix BEFORE Cologne numbers are trusted — update the Phase 2 trust badge wording
   accordingly.

## Until then

Phase 1 is gated on the green rulebook unit tests (`tests/test_swiss.py`,
`tests/test_mc.py` — difficulty formula, difficulty-rank fold, verbatim priority-table
oracle, rematch fallback, locked determinism, MC invariants/reproducibility). Phase 2's
trust badge must read **"engine validated vs Valve rulebook unit tests — full Budapest
backtest pending seed data,"** NOT "validated vs Budapest backtest."
