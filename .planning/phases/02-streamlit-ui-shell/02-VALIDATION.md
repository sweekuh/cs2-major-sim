---
phase: 2
slug: streamlit-ui-shell
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-29
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + `streamlit.testing.v1.AppTest` (ships inside streamlit — no extra dep) + pure-helper unit tests |
| **Config file** | existing `[tool.pytest.ini_options]` in pyproject.toml (from Phase 1) |
| **Quick run command** | `uv run pytest -q tests/test_app.py` |
| **Full suite command** | `uv run pytest` (Phase 1 engine tests + Phase 2 UI tests) |
| **Estimated runtime** | ~10–25s (AppTest runs the script headless; cap N small in tests, e.g. N=2000) |

**What AppTest CAN assert:** widget presence/values, mode toggle reorders layout, reruns, `session_state`, exceptions raised, that a bad-rating run is blocked, that `locked` in the cache key changes results. **What it CANNOT assert:** CSS/pixels, monospace rendering, CI-bar visual appearance, colorblind palette, ~15s wall-clock, cross-OS launch — those are Manual-Only.

---

## Sampling Rate

- **After every task commit:** `uv run pytest -q tests/test_app.py` (+ the pure-helper tests touched)
- **After every plan wave:** `uv run pytest` (full suite — UI tests must not regress the engine)
- **Before `/gsd-verify-work`:** full suite green
- **Max feedback latency:** ~25s

---

## Per-Task Verification Map

> Populated/refined by the planner. The load-bearing seams are pre-seeded so each gets a test.

| Task ID | Plan | Wave | Requirement | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | — | — | UI-02 / Phase2×4 | `locked` IS in the cache key — locking a result changes the cached output (NOT the underscore-arg bug) | unit | `uv run pytest tests/test_app.py::test_locked_in_cache_key` | ❌ W0 | ⬜ pending |
| TBD | — | — | UI-02 | `freeze_locked()` round-trips a dict→sorted-tuple→dict deterministically | unit (pure) | `uv run pytest tests/test_app.py::test_freeze_locked_roundtrip` | ❌ W0 | ⬜ pending |
| TBD | — | — | UI-03 / Phase1×2 | progress driven by `run_mc_progressive` does not re-chunk; `n_chunks=20` reproducibility preserved | unit | `uv run pytest tests/test_app.py::test_progress_preserves_reproducibility` | ❌ W0 | ⬜ pending |
| TBD | — | — | UI-05 | empty/out-of-range rating blocks Run with an inline message; engine not called | AppTest | `uv run pytest tests/test_app.py::test_bad_rating_blocks_run` | ❌ W0 | ⬜ pending |
| TBD | — | — | UI-01 | Pre-stage/Live toggle present; main column reorders by mode | AppTest | `uv run pytest tests/test_app.py::test_two_mode_toggle` | ❌ W0 | ⬜ pending |
| TBD | — | — | DX-01 | first run loads data/stage1.json with no API key, produces a result | AppTest | `uv run pytest tests/test_app.py::test_zero_config_first_run` | ❌ W0 | ⬜ pending |
| TBD | — | — | DX-02 | [INFERRED]-seed banner present until `seeds_confirmed` toggled | AppTest | `uv run pytest tests/test_app.py::test_seed_banner` | ❌ W0 | ⬜ pending |
| TBD | — | — | UI-07 | trust badge reads "validated vs Valve rulebook unit tests — full backtest pending seed data"; `BACKTEST_PASSED=False` constant | unit | `uv run pytest tests/test_app.py::test_trust_badge_wording` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `streamlit>=1.57,<1.58` added to pyproject `[project].dependencies` + `uv sync` (currently engine-only)
- [ ] `tests/test_app.py` — AppTest + pure-helper scaffolds for the rows above
- [ ] `app.py` importable headlessly by AppTest (no top-level side effects that break `AppTest.from_file`)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CI mini-bars render under every number, monospace-aligned | UI-04 / UI-06 | AppTest can't assert CSS/HTML rendering | `uv run streamlit run app.py`, Run, eyeball the prob table |
| Colorblind-safe blue/amber status + glyph+label (never red/green) | UI-06 | visual palette | eyeball live/dead/secured states |
| ~15s for 100k sims with a live-updating progress bar | UI-03 | wall-clock timing | run at default N=100k, observe the bar + running P(advance) |
| `uv run streamlit run app.py` launches on Windows/Mac/Linux | DX-03 | cross-OS | run on each OS (author Windows; friends Mac/Linux) |
| README quickstart + event-day cold-start drill readable | DX-04 | doc prose | read-through |

---

## Validation Sign-Off

- [ ] All tasks have an `<automated>` verify or a Manual-Only entry
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers streamlit dep + test scaffolds
- [ ] No watch-mode flags
- [ ] Feedback latency < 25s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
