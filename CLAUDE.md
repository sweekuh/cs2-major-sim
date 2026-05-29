# swiss-mc — Cologne 2026 Swiss Monte Carlo & Pick'Em Optimizer

Interactive Streamlit webapp (Python 3.12 · numpy) that Monte Carlo-simulates the
IEM Cologne Major 2026 CS2 Swiss stages, outputs per-team P(3-0)/P(advance)/P(0-3)
with CI bands, recommends the optimal 2/6/2 Pick'Em ballot (E[correct]-optimal and
P(≥5)-optimal), reports true P(≥5/10) coin odds, and supports round-by-round result
locking with conditional re-simulation. Win probabilities come from a three-provider
market-odds ensemble (OddsPapi/Pinnacle + Polymarket + Kalshi), back-solved into
per-team ratings. Single local user. No scraping — APIs only.

## This project uses GSD (get-shit-done)

Planning lives in `.planning/`. Read these before working — they are the source of truth:

- `.planning/PROJECT.md` — what this is, core value, requirements state, key decisions, constraints
- `.planning/REQUIREMENTS.md` — 58 v1 requirements with REQ-IDs + traceability to phases
- `.planning/ROADMAP.md` — 6-phase MVP roadmap, dependencies, success criteria
- `.planning/STATE.md` — current project memory / where things stand
- `.planning/research/` — STACK / FEATURES / ARCHITECTURE / PITFALLS / SUMMARY
- `files/PRD_cologne2026_pickem_simulator.md` — rationale (the why)
- `files/HANDOFF_claude_code.md` — the executable spec (repo layout, engine pseudocode, acceptance tests, UI + DX contracts)
- `TODOS.md` — deferred work (cron-fed odds cache, Numba)

### Workflow

Phases execute in order 1 → 2 → 3 → 4 → 5 → 6. Per-phase loop:
`/gsd-plan-phase N` → `/gsd-execute-phase N` → `/gsd-verify-work N`.
Config: interactive mode, standard granularity, parallel execution, Quality models,
research + plan-check + verifier all on. Run `/gsd-progress` to see where things stand,
`/gsd-settings` to change preferences.

## Non-negotiable build rules (correctness is the product)

These are the load-bearing facts; getting any wrong silently corrupts every probability:

- **Buchholz / Difficulty Score = `Σ(opp.wins − opp.losses)`**, NOT `Σ opp.wins`. (ENG-03)
- **Within-group fold sorts on the difficulty-ranked order, not raw seed.** (ENG-04)
- **The Phase 1 round-by-round backtest is a HARD GATE** — it reproduces a real past
  Major stage's pairings exactly. No UI is built and no sim output is trusted until it
  passes. Invariant tests (Σ P=2/8/2) pass even when the engine is wrong, so the
  backtest is the only real check. Pull Valve's 15-row priority table verbatim from
  `major-supplemental-rulebook.md`; don't approximate. (GATE-01..05)
- **Bo3 = closed form `p²(3−2p)` as a single Bernoulli draw** — never sample 3 maps. (MC-06)
- **Epistemic (source-disagreement) variance is an OUTER loop**, never folded into
  per-sim sampling; clamp `variance < p(1−p)` before the Beta fit or it crashes on the
  thin-liquidity matches that matter most. (PROB-03/04)
- **Cross-phase seams to honor early:** `swiss.py` accepts `locked` from Phase 1; the
  `@st.cache_data` key includes `locked` from Phase 2 (or re-sim serves stale numbers);
  `SeedSequence.spawn` over a pinned chunk count so reproducibility survives chunked
  progress; the odds layer writes a read-only `data/odds_cache.json` the app only reads.
- **Seeds + default ratings are [INFERRED]** — keep editable, show the loud in-app banner,
  reconcile against the official seed list at lock.
- **APIs only, no scraping.** Keys from env (`.env` gitignored). Missing key → rating-only
  mode + banner, never a crash (fail soft). First run needs no API key.
- **Stack:** Python ≥3.12, Streamlit 1.57.* (pin it), numpy 2.4.x, `httpx` for odds,
  `python-dotenv`. Bootstrap with `uv run streamlit run app.py`. Avoid pandas/scipy.

---
*GSD project initialized 2026-05-28.*
