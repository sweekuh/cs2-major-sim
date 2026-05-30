# Complete Budapest 2025 backtest gate (GATE-01) — RESOLVED 2026-05-29

> **RESOLVED 2026-05-29.** GATE-01/04/05 are GREEN. The engine reproduces Budapest 2025
> Stage 1's actual pairings EXACTLY (R1-R5) under the authoritative Valve VRS-snapshot seeds
> (global-rank order from `counter-strike_regional_standings` 2025_11_03). The "8-team pairing
> gap" flagged below was NOT an engine bug — it was a by-hand seed-disambiguation error (Fnatic/
> PARIVISION 5/6, RED/The Huns 13/14) which the backtest caught at R2. Using the pure VRS-rank
> order, the engine's existing fold + priority table reproduce every round. `BACKTEST_PASSED=True`.
> History below kept for the record.

- **Captured:** 2026-05-29 (during 01-04 execution, at the Task 1 human-verify checkpoint)
- **Resolved:** 2026-05-29 (third pass — seeds corrected, full backtest green)
- **Status:** RESOLVED — GATE-01/04/05 complete; backtest green
- **resolves_phase:** (blank — cross-cutting; NOT auto-closed by Phase 1)
- **Priority:** P1

## Progress — SEEDS RESOLVED + authoritative

The original blocker (no authoritative seed source) is GONE. Valve open-sources the seeding VRS
snapshot: `ValveSoftware/counter-strike_regional_standings`, `invitation/2025/details/2025_11_03/`
(the post-final-RMR snapshot used for Major seeding). Each team is filed by global VRS rank; the
16 Budapest Stage-1 teams sorted by that rank give the 1-16 seed order, now frozen in
`tests/fixtures/budapest_2025_stage1.json` (`seeding`). The "snapshot rule" (timestamped VRS
SNAPSHOT, not live HLTV/VRS) was the original mistake — credit: user.

**Validated:** seed `k` vs `k+8` reproduces ALL 8 actual R1 matches (8/8) — green test
`test_round1_is_kvsk8_under_resolved_seeds`. Seeds are FORCED by both the VRS snapshot AND R1.

## The remaining gap (the real GATE-04 finding)

The full backtest (`test_backtest_budapest_2025`, now `xfail(strict=True)`) fails at **Round 2**.
With the correct seeds, the engine's within-group high-low fold does NOT reproduce the actual R2:

- Engine fold (rulebook's literal "highest faces lowest available non-rematch"), within-group
  positions: `(1,8),(2,7),(3,6),(4,5)`.
- Budapest ACTUAL R2 — BOTH the 1-0 "High" and 0-1 "Low" 8-team groups: `(1,8),(2,6),(3,7),(4,5)`.

Concretely (1-0 group): engine pairs PARIVISION-Fluxo & Fnatic-M80; actual was PARIVISION-M80 &
Fnatic-Fluxo. Same swap in the 0-1 group. Consistent across both groups → a real rule, not noise.
R2 difficulty is uniform (each 1-0 team beat a 0-1 team → −1), so within-group order is pure seed
and not in question. This is an engine-vs-reality pairing gap for groups LARGER than the verbatim
6-team priority table (R2 has two 8-team groups; R3 an 8-team group; R4/R5 are 6-team).

## Open question before closing GATE-01

Does Valve's actual within-group pairing for 8-team (and 4-team) groups follow a FIXED BRACKET
TEMPLATE (like the verbatim 15-row 6-team priority table) that the rulebook does not print, whose
row-1 (no-rematch) is `(1,8),(2,6),(3,7),(4,5)`? The rulebook's one-line "highest faces lowest
available" (R2/R3) does not match the observed bracket. Either:
  (a) engine should match the observed bracket (rulebook text is an oversimplification) →
      implement Valve's real n=8 / n=4 templates; OR
  (b) Cologne follows the literal rulebook rule and Budapest deviated → engine is already correct
      for Cologne and Budapest is a poor backtest fixture.

Do NOT hard-code the n=8 pattern from this single event (overfit / false confidence). Resolve via
the authoritative Valve pairing template, or cross-check with a second past 16-team stage
(BLAST Austin 2025 — same repo has its seeding snapshot).

## Resume path
1. Find/confirm Valve's within-group pairing template for n=8 and n=4 (rules repo / a second
   stage's bracket). The 6-team table is in `counter-strike_rules_and_regs/major-supplemental-rulebook.md`.
2. If a template reproduces Budapest R2-R5 AND a second stage, implement it in `engine/swiss.py`
   (`pair_within_group`) alongside the 6-team priority table.
3. The xfail flips to PASS (strict catches it) → flip `BACKTEST_PASSED=True` in `ui/state.py`,
   update the trust badge to "validated vs Budapest 2025 backtest", close this TODO.

## Already in place (this branch: phase-1-backtest-closeout)
- `tests/fixtures/budapest_2025_stage1.json` — frozen results + RESOLVED seeds + the finding.
- `tests/test_backtest_budapest_2025.py` — R1 8/8 (green), fixture-shape (green), full backtest (xfail strict).
- `engine/swiss.py` — `pairings_out` capture hook (default-off) + compute-pairings-before-playing
  (Buchholz integrity; all 67 other tests stay green).
- `BACKTEST_PASSED` stays `False`; trust badge stays caveated. No false green.

## Original capture (for the record)
Budapest Stage 1 RESULTS were reconciled + frozen during 01-04. The authoritative 1-16 Valve seed
integers were the original blocker (HLTV Cloudflare-walled; Liquipedia/Wikipedia publish no seed
integers; live VRS world-rank order did not reproduce R1/R2). That blocker is now resolved via the
Valve open-source standings repo (above).
