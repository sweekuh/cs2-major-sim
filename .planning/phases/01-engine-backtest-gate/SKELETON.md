# Walking Skeleton — swiss-mc (Cologne 2026 Swiss MC & Pick'Em Optimizer)

**Phase:** 1
**Generated:** 2026-05-28

## Capability Proven End-to-End

`uv run python -m engine` simulates the full Valve Stage-1 Swiss format over N Monte Carlo runs and
prints per-team P(3-0)/P(advance)/P(0-3) with Wilson confidence bands — and `uv run pytest` proves the
engine reproduces a real past Major stage's (Budapest 2025 Stage 1) round-by-round pairings exactly.

This is a HEADLESS Walking Skeleton by design: the locked architecture makes Phase 1 a dependency-free
correctness core, so the thinnest runnable end-to-end stack is the pipeline `teams.py fixtures →
swiss.py engine → montecarlo.py MC → probs.py math → __main__ CLI output → backtest gate`. There is no
web UI, HTTP, routing, deployment target, or odds layer in this skeleton — those are Phase 2 (UI) and
Phase 5 (odds), and "no UI exists until the backtest gate passes" is a hard locked decision (GATE-05).
The Walking Skeleton's "one real interaction" is the `__main__` CLI smoke output; the "deploy" step is
satisfied by `uv run python -m engine` running locally.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language / runtime | Python >=3.12 (pinned in pyproject.toml) | Project constraint; frozenset/match/typing used freely |
| Numerics / RNG | numpy 2.4.x — `SeedSequence(seed).spawn(n_chunks)` over a PINNED chunk count | Only mechanism that keeps chunked execution reproducible across runs/machines (ENG-09, Pitfall 10); the backtest must run the same chunked path the app ships |
| Test runner / the gate | pytest 8.x; `uv run pytest` | The round-by-round backtest IS a pytest run; it is the hard blocking gate |
| Env / bootstrap | uv (`uv run ...`); pip+venv documented fallback | Cross-platform one-command bootstrap (Windows author) |
| Engine purity | `engine/` is a functional core — pure, deterministic, RNG injected, progress via generator yield; imports NO streamlit/httpx/requests | Makes the engine backtestable before any UI exists; the invariant that makes the gate possible |
| MC shape | Generator-first `run_mc_progressive` (yields per-chunk partials) + a separate cached-wrapper-shaped drain function | Phase 2's `@st.cache_data` split and progress bar ride on this; retrofitting yield is a hot-path rewrite |
| Conditional re-sim seam | `simulate_stage` accepts `locked: dict[frozenset({id,id}) -> winner_id]` from day one | Phase 4 re-sim rides entirely on this; skipping forces a swiss.py rewrite |
| Epistemic uncertainty | OUTER loop, stubbed as a single-draw no-op in Phase 1; Beta moment-fit with `var < p(1-p)` clamp present but unused | Phase 5 fills K Beta draws; if not structured outer now, Phase 5 is a rewrite (Pitfall 4) |
| Pairing oracle | Verbatim Valve 15-row priority table as the rematch-resolution oracle; greedy fold kept as fast path; literal-table fork on divergence (GATE-04) | Greedy can return a legal-but-wrong matching; only the verbatim table + backtest catch it |
| Difficulty / Buchholz | `Σ(opp.wins − opp.losses)` (NOT `Σ opp.wins`); fold sorts on `(−difficulty, seed)` | Load-bearing correctness facts; wrong → every probability silently corrupted (ENG-03/04) |
| Bo3 | Closed form `p²(3−2p)` as a single Bernoulli draw | Exact for iid maps; sampling 3 maps only adds noise (MC-06) |
| Directory layout | `engine/` (teams, swiss, probs, montecarlo, __main__), `tests/`, `data/`, `pyproject.toml` | HANDOFF §1 repo layout subset; app.py/odds/scripts are later phases |

## Stack Touched in Phase 1

- [x] Project scaffold (uv, pyproject.toml requires-python >=3.12, numpy + pytest, pytest config)
- [x] "Routing" → not applicable (headless); satisfied by the `python -m engine` entry point
- [x] "Database" → not applicable (no persistence); satisfied by the shipped `data/stage1.json` fixture (read) + retained per-sim sample (in-memory write)
- [x] "UI interaction" → the `__main__` CLI smoke run printing per-team probs + Wilson bands
- [x] "Deployment" → documented local full-stack run command `uv run python -m engine`; the backtest gate `uv run pytest`

## Out of Scope (Deferred to Later Slices)

> Be explicit — this prevents later phases from re-litigating Phase 1's minimalism.

- Streamlit / any web UI, routing, HTTP, deployment target (Phase 2)
- The Pick'Em optimizer / Ballot A & B / P(≥5) (Phase 3) — Phase 1 only RETAINS the sample it scores against
- Result-locking UI / live mode / bracket view (Phase 4) — Phase 1 only provides the `locked` seam in swiss.py
- Odds providers, log-opinion pool, de-vig, ratings back-solve, `odds_cache.json` (Phase 5) — Phase 1 only stubs the odds-override passthrough + epistemic outer loop + Beta clamp
- Stages 2/3 Swiss + playoff single-elim + map-level Bo3 (Phase 6)
- pandas / scipy / numba (forbidden / deferred); httpx / python-dotenv (Phase 5)

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering its architectural decisions:

- **Phase 2:** Streamlit two-mode UI over the proven engine — ratings editor, S/N controls, Run, results table with inline Wilson CI mini-bars, `@st.cache_data` keyed on `(ratings, S, N, locked)` draining `run_mc_progressive`, [INFERRED]-seed banner, trust badge.
- **Phase 3:** Pick'Em optimizer — Ballot A (E[correct]) + Ballot B (P(≥5)) scored against the retained per-sim sample, correlated-pick warning.
- **Phase 4:** Conditional re-sim + live mode — round-by-round locking via the `locked` cache key, live/dead/secured status with P(≥5)-from-here delta, record-bucket bracket.
- **Phase 5:** Odds ensemble — three-provider log-opinion pool fills the epistemic outer loop, ratings back-solve, read-only `data/odds_cache.json` seam; fails soft, never gates.
- **Phase 6:** Full-Major v3 — Stages 2/3 Swiss + playoff single-elim via the same engine; optional map-level Bo3 only if backtest evidence demands.
