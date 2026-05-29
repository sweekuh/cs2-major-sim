---
phase: 1
slug: engine-backtest-gate
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-28
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (latest 8.x) |
| **Config file** | none yet — Wave 0 installs (pyproject.toml `[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest -q` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~5–15 seconds (engine is pure Python; backtest is deterministic, no large MC) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd-verify-work`:** Full suite must be green, including the backtest gate
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

> Populated by the planner. The load-bearing rows — the correctness-fatal requirements that
> invariant tests do NOT catch — are pre-seeded here so the planner wires a test to each.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | — | — | GATE-01 | — | Engine reproduces Budapest 2025 Stage 1 round-by-round pairings exactly | backtest | `uv run pytest tests/test_backtest_budapest_2025.py` | ❌ W0 | ⬜ pending |
| TBD | — | — | ENG-03 / GATE-02 | — | `difficulty()` on opponents 2-0 & 1-1 returns 2 (not 3) | unit | `uv run pytest tests/test_swiss.py::test_difficulty_formula` | ❌ W0 | ⬜ pending |
| TBD | — | — | ENG-04 | — | Fold sorts on difficulty-ranked order, not raw seed | unit | `uv run pytest tests/test_swiss.py::test_fold_key` | ❌ W0 | ⬜ pending |
| TBD | — | — | ENG-05 | — | No rematch-free matching → least-disruptive rematch + warning, no crash | unit | `uv run pytest tests/test_swiss.py::test_no_valid_matching_fallback` | ❌ W0 | ⬜ pending |
| TBD | — | — | ENG-08 | — | Locked winner deterministic across sims; no-rematch respects locked history | unit | `uv run pytest tests/test_swiss.py::test_locked_results_honored` | ❌ W0 | ⬜ pending |
| TBD | — | — | ENG-09 | — | Same (seed, N) → identical counts across runs and chunk counts (SeedSequence.spawn) | unit | `uv run pytest tests/test_mc.py::test_reproducibility` | ❌ W0 | ⬜ pending |
| TBD | — | — | MC-03 | — | Σ P(3-0)≈2, Σ P(0-3)≈2, Σ P(advance)≈8 within ±0.05 at N≥50k | property | `uv run pytest tests/test_mc.py::test_invariants` | ❌ W0 | ⬜ pending |
| TBD | — | — | MC-06 / PROB-01 | — | Bo3 closed form: p=0.6 → 0.648; p=0.5 → 0.5 | unit | `uv run pytest tests/test_probs.py::test_bo3` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_swiss.py` — engine: difficulty, fold key, rematch fallback, locked results, no-rematch
- [ ] `tests/test_mc.py` — MC: invariants, reproducibility, full per-sim sample retained
- [ ] `tests/test_probs.py` — math: p_map, Bo3 closed form, epistemic-stub no-op
- [ ] `tests/test_backtest_budapest_2025.py` — the GATE: deterministic round-by-round pairing reproduction
- [ ] `tests/conftest.py` — shared fixtures (teams, seeds, a frozen Budapest fixture)
- [ ] pytest install via `uv` + `[tool.pytest.ini_options]` in pyproject.toml

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Budapest 2025 fixture transcription | GATE-01 | Liquipedia round-by-round data was inconsistent across fetches (research flag) — must be transcribed verbatim via `/browse` and reconciled before encoding | Re-fetch Budapest 2025 Stage 1 Swiss via `/browse`, reconcile match-by-match (8 teams at 1-1 entering R3), then freeze into the test fixture |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
