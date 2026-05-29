---
phase: 02-streamlit-ui-shell
plan: 03
subsystem: ui
tags: [streamlit, ui, trust-badge, seed-banner, dx, readme]
requires:
  - "ui.state.Mode / KEY_* / read helpers (Phase 2 plan 01/02 — session keys + Streamlit-free core)"
  - "app.py header strip + two-mode shell (Phase 2 plan 02 — segmented_control + reorder)"
  - "data/stage1.json seeds_confirmed flag (Phase 1 — frozen fixture)"
  - "engine.teams.load_teams (Phase 1 — frozen; read-only consumer here)"
provides:
  - "ui.state.BACKTEST_PASSED — explicit False flag so the trust badge cannot drift to green validated"
  - "ui.state.TRUST_BADGE_CAVEATED — the EXACT caveated badge string (no Budapest/green-check)"
  - "ui.state.trust_badge_state — validated iff BOTH BACKTEST_PASSED AND seeds_confirmed (Pitfall 6)"
  - "ui.state.read_seeds_confirmed — read-only data/stage1.json seeds_confirmed parse (engine untouched)"
  - "ui.state.odds_key_present — os.environ-only presence check (no httpx/dotenv import)"
  - "app.py header strip — caveated badge + INFERRED-seed banner + reconcile area + confirm toggle + fail-soft odds banner"
  - "README.md — DX-04 quickstart + 30-second event-day cold-start drill"
  - ".env.example — optional provider keys (DX-05)"
affects:
  - "Phase 1 backtest landing (GATE-01) flips BACKTEST_PASSED True — then the badge can validate once seeds confirmed"
  - "Phase 5 (odds) replaces the fail-soft odds-off banner stub with the real OddsPapi/Polymarket/Kalshi path"
  - "Phase 4 (locking) inherits the seeds_confirmed session_state already wired here"
tech-stack:
  added: []
  patterns:
    - "Explicit BACKTEST_PASSED constant gate — badge claim cannot silently drift true while the backtest is deferred"
    - "trust_badge_state reads BACKTEST_PASSED off the module at call time (late ref) so a future flip / test override takes effect"
    - "read-only JSON flag parse in ui.state (not via the frozen engine) — load_teams does not surface seeds_confirmed"
    - "session_state seeded from read_seeds_confirmed() once, then the in-session toggle owns the key (set before widget creation = initial value)"
    - "Fail-soft env presence check via os.environ only — no Phase-5 network deps imported in Phase 2"
key-files:
  created:
    - "README.md"
    - ".env.example"
    - ".planning/phases/02-streamlit-ui-shell/02-03-SUMMARY.md"
  modified:
    - "ui/state.py"
    - "app.py"
    - "tests/test_app.py"
decisions:
  - "BACKTEST_PASSED=False is an explicit module constant (not implicit) so the trust badge can never drift to a green validated claim while GATE-01 is deferred; flipped only when the backtest actually runs"
  - "Trust badge ships as st.caption(TRUST_BADGE_CAVEATED) in the caveated state — neutral, no green ✓ and no Budapest claim (UI-07); the validated st.success path is dead code until BOTH gates clear"
  - "seeds_confirmed session_state seeded once from data/stage1.json read-only, then owned by the in-session st.toggle (positive confirmation, no red — protects never-red/green)"
  - "odds_key_present checks os.environ only and never returns/logs the key value (T-02-SECRET); no httpx/python-dotenv import preserves the zero-config first run (T-02-NOIMPORT)"
metrics:
  duration_min: 12
  tasks: 3
  files: 5
  completed: 2026-05-29
---

# Phase 2 Plan 03: Trust Badge + Seed-Safety Header + DX Docs Summary

Shipped the trust + seed-safety header strip and the DX docs that make Phase 2 honest and event-day-ready: a trust badge that reads the EXACT caveated wording and is gated on BOTH a `BACKTEST_PASSED=False` constant AND the seeds-confirmed toggle so it cannot claim more than is true; a persistent dismissable `⚠ Seeds are INFERRED` banner with a seed→team reconcile area; a fail-soft `live odds off` info banner that stubs the Phase-5 seam without any network import; and a README quickstart + cold-start drill plus `.env.example`.

## What Was Built

- **`ui/state.py`** — added `BACKTEST_PASSED = False` (explicit flag, flipped only when the deferred GATE-01 backtest runs), `TRUST_BADGE_CAVEATED` (the exact string `engine validated vs Valve rulebook unit tests — full backtest pending seed data` — no Budapest/Austin, no green ✓), `trust_badge_state(seeds_confirmed)` (returns `"validated"` iff BOTH `BACKTEST_PASSED` and `seeds_confirmed`, else `"caveated"`; reads the constant via a late module ref so a future flip / test override takes effect), `read_seeds_confirmed(path=None)` (parses `data/stage1.json` `seeds_confirmed` read-only, fail-safe `False` on any error — the frozen engine does not surface this field), and `odds_key_present()` (`os.environ` presence only, no httpx/dotenv import). Added `KEY_SEEDS_CONFIRMED` / `ODDS_KEY_ENV` constants.
- **`app.py`** — added `_render_header_strip()` rendered in BOTH modes above the body: (1) the trust badge — caveated `st.caption(TRUST_BADGE_CAVEATED)` while `BACKTEST_PASSED` is False (the green `st.success` validated path is dead code until both gates clear); (2) the `⚠ Seeds are INFERRED — verify vs the official seed list before trusting outputs.` `st.warning` with a "Reconcile seeds vs the official list" expander listing each seed→team row, shown until dismissed, plus an `st.toggle` (key `seeds_confirmed`, a positive confirmation — no red) that on True dismisses the banner and is the gate the badge reads; session_state seeded once from `read_seeds_confirmed()`; (3) a one-line fail-soft `st.info` `live odds off (no ODDSPAPI_KEY) — using manual ratings` when no key is set. No Phase-5 import.
- **`README.md`** (created) — DX-04-ordered quickstart at top: one-line what-it-is → `uv run streamlit run app.py` + pip fallback → "first sim needs no API key" + ~15s → what the numbers mean (P(3-0)/advance/0-3 + CI bands = honest uncertainty) → [INFERRED]-seed reconcile step → optional `.env.example`. Includes a trust-badge meaning paragraph (README and badge agree) and ends with the 30-second event-day cold-start drill (`git pull` → confirm seeds → flip "seeds confirmed" → Run).
- **`.env.example`** (created) — commented optional provider keys `ODDSPAPI_KEY=` / `POLYMARKET_API_KEY=` / `KALSHI_API_KEY=` with a rating-only fallback note. `.env` remains gitignored (asserted, not modified).
- **`tests/test_app.py`** (+9) — `test_trust_badge_wording` (exact string, both-gated logic, Budapest-free), `test_read_seeds_confirmed_reads_json_read_only`, `test_odds_key_present_uses_only_env`, `test_trust_badge_caveated_until_both`, `test_seed_banner`, `test_seed_banner_dismissable`, `test_odds_off_banner_failsoft`, `test_env_example_present_and_gitignored`, `test_readme_quickstart_and_cold_start_drill`.

## Verification Results

- `uv run pytest -q tests/test_app.py` — **24 passed** (15 plan-01/02 + 9 new).
- `uv run pytest -q` — **50 passed, 1 skipped** (the deferred Budapest GATE-01, expected). Up from 41 passed at plan start; no regression.
- Engine untouched: `git diff --stat HEAD -- engine/` is empty across all three commits.
- No network, no httpx/python-dotenv import added (`pyproject.toml` dependencies unchanged).

## TDD Gate Compliance

Task 1 was `tdd="true"`: the trust-badge/seeds/odds tests were added first and confirmed RED (3 `ImportError` failures against the not-yet-added `ui.state` names — not falsely green), then GREEN after implementing `ui/state.py` (commit `6155f23`). Tasks 2 and 3 are `auto` tasks (header-strip layout exercised via AppTest, docs verified by file-content asserts); their tests were added alongside the implementation and pass (commits `4545ca5`, `b5c0467`).

## Deviations from Plan

None affecting behavior. Two within-scope notes:

**1. [Within scope] The validated `st.success` badge path is dead code in Phase 2.**
`_render_header_strip` includes the `"validated"` branch (`st.success(f"/ {TRUST_BADGE_CAVEATED}")`) for when `trust_badge_state` returns `"validated"`, but with `BACKTEST_PASSED=False` it is unreachable now — by design (UI-07, Pitfall 6: the badge cannot reach green until BOTH the backtest lands AND seeds are confirmed). The both-gated logic is unit-tested via a local `BACKTEST_PASSED` override in `test_trust_badge_wording`.

**2. [Within scope] Reconcile area is an `st.expander` (collapsed) rather than always-open.**
DX-02 calls for a "field-by-field reconcile area"; it ships as a collapsed `st.expander` listing all 16 seed→team rows so it does not crowd the header strip but is one click from the eyeball check. The seed→team rows render in the element tree (asserted by `test_seed_banner`).

No authentication gates (local single-user app, no network). No package installs.

## Known Stubs

- **Fail-soft odds-off banner** — `st.info("live odds off (no ODDSPAPI_KEY) — using manual ratings")` is a real, shipped fail-soft banner, but the live-odds path it stubs (back-solving ratings from OddsPapi/Polymarket/Kalshi) is Phase 5. Intentional ODDS-08 seam, documented in the plan; the banner and the `.env.example` keys are the forward wiring. No httpx/dotenv import yet (preserves the zero-config first run).
- **`BACKTEST_PASSED = False`** — an intentional gate, not an unfinished stub: it flips to True only when the deferred GATE-01 backtest actually runs (tracked in `.planning/todos/pending`). Until then the badge is correctly caveated.

No stubs prevent this plan's goal (an honest trust + seed-safety header and event-day-ready DX docs). The badge wording/gate, the dismissable seed banner + reconcile area, the fail-soft odds banner, the README quickstart + cold-start drill, and `.env.example` are all real and tested.

## Threat Flags

None. The plan's `<threat_model>` is fully honored: the trust badge is gated on BOTH `BACKTEST_PASSED` AND `seeds_confirmed` and cannot drift to a green claim (T-02-BADGE mitigated); `.env.example` ships no real values and `.env` stays gitignored, and `odds_key_present` checks presence only without rendering/logging the key (T-02-SECRET mitigated); the odds-off banner uses only `os` — no httpx/python-dotenv import (T-02-NOIMPORT mitigated). No new network endpoint, auth path, or schema change was introduced.

## Self-Check: PASSED

- Files present on disk: `ui/state.py`, `app.py`, `README.md`, `.env.example`, `tests/test_app.py`, this SUMMARY.
- Task commits found in git history: `6155f23` (feat 02-03 state gate + helpers), `4545ca5` (feat 02-03 header strip), `b5c0467` (feat 02-03 README + .env.example).
- `BACKTEST_PASSED`/`TRUST_BADGE_CAVEATED`/`trust_badge_state`/`read_seeds_confirmed`/`odds_key_present` import and behave as asserted; full suite 50 passed / 1 skipped, engine `git diff --stat` empty.
