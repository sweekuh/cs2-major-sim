# Roadmap: swiss-mc — Cologne 2026 Swiss MC & Pick'Em Optimizer

## Overview

The build is one strict dependency chain, not a menu. A faithful Valve Swiss engine
is worthless unless its pairing logic is provably correct, so the round-by-round
backtest is a **hard blocking gate** at the end of Phase 1 — no UI, optimizer, odds,
or trusted output exists until it reproduces a real past Major stage's pairings
exactly. From there each layer rides on the one below: the Streamlit shell (Phase 2)
needs the generator-first MC and a `locked`-keyed cache; the optimizer (Phase 3) needs
the stored per-sim record sample; conditional re-sim + live mode (Phase 4) needs the
engine's `locked` support and the optimizer's P(≥5) scoring; the odds ensemble
(Phase 5) is a fail-soft enhancement that fills the epistemic outer loop stubbed in
Phase 1 and is placed last because rating-only mode is fully functional and the first
run needs no API key; and v3 (Phase 6) reuses the validated engine for Stages 2–3,
playoffs, and optional map-level Bo3. Reversing any adjacent pair forces a rewrite.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Engine + Backtest Gate** - Headless Valve Swiss engine + generator-first MC; round-by-round backtest is a hard blocking gate
- [ ] **Phase 2: Streamlit UI Shell** - Two-mode app with `locked`-keyed cache, CI mini-bars, [INFERRED]-seed banner, zero-config first run
- [ ] **Phase 3: Pick'Em Optimizer** - Ballot A (E[correct]) + Ballot B (P(≥5)) against the stored sim sample, with correlated-pick warning
- [ ] **Phase 4: Conditional Re-Sim + Live Mode** - Round-by-round result locking, live/dead/secured status with P(≥5) delta, record-bucket bracket
- [ ] **Phase 5: Odds Ensemble** - Three-provider log-opinion pool, ratings back-solve, epistemic outer loop, read-only cache seam; fails soft, never gates
- [ ] **Phase 6: Full-Major v3** - Stages 2–3 Swiss + playoff single-elim via the same engine; optional map-level Bo3 only if backtest demands

## Phase Details

### Phase 1: Engine + Backtest Gate
**Goal**: A pytest-runnable, dependency-free correctness core that simulates the Valve Stage-1 Swiss format and reproduces a real past Major stage's pairings exactly — the hard gate that must pass before any output is trusted or any UI exists.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: ENG-01, ENG-02, ENG-03, ENG-04, ENG-05, ENG-06, ENG-07, ENG-08, ENG-09, MC-01, MC-02, MC-03, MC-04, MC-05, MC-06, PROB-01, PROB-02, PROB-03, PROB-04, PROB-05, GATE-01, GATE-02, GATE-03, GATE-04, GATE-05
**Success Criteria** (what must be TRUE):
  1. Running `pytest` reproduces a completed past Major stage (Budapest 2025 or Austin 2025) round-by-round pairings **exactly**, and `test_difficulty_formula` returns 2 on Valve's worked example — the BACKTEST GATE passes (GATE-01..05).
  2. A `__main__` smoke run of the engine prints per-team P(3-0)/P(advance)/P(0-3) with Wilson bands, and every run satisfies the invariants ΣP(3-0)≈2, ΣP(0-3)≈2, ΣP(advance)≈8 within ±0.05 at N≥50k.
  3. The same `(seed, N)` yields identical per-team counts across two runs and across machines (SeedSequence.spawn over a pinned chunk count), proving reproducibility survives chunked execution.
  4. The engine accepts `locked: dict[frozenset->winner]` and honors locked winners deterministically while respecting the no-rematch rule (verified by `test_locked_results_honored`).
  5. The MC yields per-chunk partial aggregates (generator-first) and retains the full per-sim record sample, with the epistemic outer loop present as a single-draw no-op.

**Plans**: 4 plans
- [x] 01-01-PLAN.md — Scaffold (uv, py>=3.12), full Wave 0 test harness, engine/probs.py math core, engine/teams.py seed→team fixtures + data/stage1.json (ENG-01/03, PROB-01..05, MC-06, GATE-02)
- [x] 01-02-PLAN.md — engine/swiss.py: difficulty-ranked fold + verbatim priority-table oracle + rematch fallback + Bo3 placement + locked support + simulate_stage (ENG-02..08, GATE-03)
- [x] 01-03-PLAN.md — engine/montecarlo.py generator-first MC (SeedSequence.spawn pinned chunks, Wilson bands, full sample retention, epistemic outer no-op) + `__main__` headless smoke run (ENG-09, MC-01..05, PROB-03/05)
- [x] 01-04-PLAN.md — Budapest 2025 Stage 1 fixture transcribed + reconciled (RESULTS verified, frozen); full backtest **DEFERRED** (GATE-01/04) — authoritative Valve seeds unsourceable (HLTV Cloudflare-walled), VRS order does not reproduce R1/R2 pairings. Phase 1 gated on green rulebook unit tests instead; Phase 2 unblocked WITH caveat. Tracked in .planning/todos/pending.

**BLOCKING GATE — `swiss-validated` (GATE-01..05):** This phase ends in a named hard gate. The round-by-round backtest is the **only** check that proves greedy rematch resolution matches Valve's 15-row priority table; invariant tests pass even when Buchholz (ENG-03), the fold key (ENG-04), or the priority table are wrong. **No sim output is trusted and Phase 2 does not begin until this gate passes.** Fetch Valve's literal priority table verbatim from `major-supplemental-rulebook.md` during this phase; budget a planned fork to replace the greedy fold with literal table lookup if any Round 4/5 pairing diverges (GATE-04).

**Correctness-fatal weight carried here:** Buchholz = `Σ(opp.wins − opp.losses)` not `Σ opp.wins` (ENG-03, Pitfall 1); fold sorts on difficulty-then-seed rank, not raw seed (ENG-04, Pitfall 3); `locked` support built from day one (ENG-08, needed by Phase 4); SeedSequence.spawn over pinned chunks (ENG-09, Pitfall 10); MC generator-first with full per-sim record sample retained (MC-04/MC-05, needed by Phases 2 and 3).

**Cross-phase seams to honor NOW:**
- **(Phase 1×2 seam) numpy RNG reproducibility vs chunked-progress yielding:** `np.random.default_rng(seed)` is reproducible single-threaded but NOT across varying chunk counts. Use `SeedSequence(seed).spawn(n_chunks)` and pin `n_chunks` here; chunked progress yielding arrives in Phase 2 and must not break this. The backtest must run the SAME chunked path the app ships, or it validates code that doesn't ship.
- swiss.py accepts `locked` from day one — Phase 4 depends on it; skipping forces a swiss.py rewrite.
- MC written generator-first (`run_mc_progressive` yields partials; a cached wrapper drains it) — Phase 2's cache split depends on it; retrofitting is a rewrite of the hottest path.
- Epistemic outer loop stubbed as a single-draw no-op (PROB-03) — Phase 5 fills the Beta-draw content; if the loop isn't structured outer here, Phase 5 is a rewrite (Pitfall 4).
- Odds-override math (PROB-02: market series prob used directly, Bo3 NOT re-applied) lives in probs.py from this phase even though odds arrive in Phase 5.

### Phase 2: Streamlit UI Shell
**Goal**: A usable two-mode Streamlit app over the proven engine — editable ratings, S/N controls, Run, results table with always-visible CI mini-bars, [INFERRED]-seed safety banner, trust badge, and a zero-config first run that needs no API key.
**Mode:** mvp
**Depends on**: Phase 1 (BACKTEST GATE must have passed)
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05, UI-06, UI-07, DX-01, DX-02, DX-03, DX-04, DX-05
**Success Criteria** (what must be TRUE):
  1. `uv run streamlit run app.py` launches identically on Windows/Mac/Linux, and a fresh clone can hit Run and watch 100k sims resolve to per-team P(advance) in ~15s with **no API key and no editing** (DX-01/DX-03/DX-04).
  2. The user toggles Pre-stage / Live mode and the main column reorders; every probability cell shows the number plus an always-visible inline Wilson CI mini-bar (never hover-hidden) in monospace, with colorblind-safe blue/amber status paired with text+glyph (UI-01/UI-04/UI-06).
  3. Editing a rating, S, or N and pressing Run recomputes via `@st.cache_data` keyed on `(ratings, S, N, locked)`; the cache miss drives a progress bar + live running P(advance) tally from the MC generator, and a repeat run serves instantly (UI-02/UI-03).
  4. A persistent dismissable `⚠ Seeds are INFERRED` banner shows a field-by-field reconcile diff before the "seeds confirmed" toggle can dismiss it, and the trust badge shows the validated state only when BOTH the backtest passed AND seeds are confirmed (DX-02/UI-07).
  5. All four interaction states (loading / empty-pre-run / error / success-partial) render per feature, including inline cell errors that block the run on bad ratings (UI-05).
**Plans**: 3 plans
- [x] 02-01-PLAN.md - Bootstrap + zero-config first run + per-team probs slice: streamlit dep/uv (DX-03), zero-config Run (DX-01), freeze_locked-keyed @st.cache_data (UI-02 / Phase 2x4 seam), no-re-chunk progress generator (UI-03 / Phase 1x2 seam), rating validation blocks Run + four states (UI-05), Wave 0 test scaffold
- [x] 02-02-PLAN.md - Two-mode shell + visual tokens: Pre-stage/Live toggle + main-column reorder (UI-01), number + always-visible inline CI mini-bar on every cell (UI-04), monospace/accent/colorblind-safe blue-amber status with ASCII glyph+label (UI-06), theming
- [ ] 02-03-PLAN.md - Trust + seed safety + DX docs: caveated trust badge gated on BOTH BACKTEST_PASSED=False AND seeds-confirmed (UI-07), dismissable INFERRED-seed banner + reconcile (DX-02), fail-soft odds-off banner, README quickstart + cold-start drill (DX-04), .env.example (DX-05)
**UI hint**: yes

**Cross-phase seams to honor NOW:**
- **(Phase 2×4 seam) `@st.cache_data` key must include `locked`:** `locked` must be in the cache key from THIS phase even though the locking UI lands in Phase 4. Omitting it makes Phase 4 a re-architecture and silently returns stale pre-lock distributions in live mode (Pitfall 13). Detection: locking a result must move at least one P(advance) value.
- Two-function MC split: uncached `run_mc_progressive` drives the bar on a miss; `@st.cache_data run_mc_cached` serves on a hit. Must not break the Phase 1 SeedSequence reproducibility scheme when chunking the progress loop.
- Trust badge tied to BOTH backtest-passed AND seeds-confirmed, not just one (Pitfall 6).
- Zero-config first run is the core promise that Phase 5's fail-soft odds path must preserve.

### Phase 3: Pick'Em Optimizer
**Goal**: A decision layer that recommends both the E[correct]-optimal and P(≥5)-optimal ballots side by side, headlines the true P(≥5/10) coin odds, and warns on the correlated 0-3 trap — all scored against the stored per-sim sample, never a fresh MC run.
**Mode:** mvp
**Depends on**: Phase 1 (stored per-sim record sample), Phase 2 (UI to display ballots)
**Requirements**: OPT-01, OPT-02, OPT-03, OPT-04, OPT-05
**Success Criteria** (what must be TRUE):
  1. The app shows Ballot A (greedy: top 2 by P(3-0), top 2 by P(0-3), top 6 by P(advance) excluding the four chosen) and Ballot B (hill-climb swaps scored by P(≥5) against the stored sample) side by side, both valid exactly 2/6/2 with no team in two buckets, differing picks highlighted (OPT-01/OPT-02/OPT-03).
  2. The chosen ballot's P(≥5/10) is computed by scoring each simulated stage's record vector against it (exact-record 3-0/0-3) and shown as the hero number (OPT-04).
  3. A correlated-pick warning fires when the two 0-3 picks meet in Round 1, and Ballot B automatically avoids the trap (OPT-05).
  4. The optimizer consumes the stored sample and never re-runs the MC (verified by `test_pge5_known_answer` and `test_greedy_is_e_correct_optimal`).
**Plans**: TBD
**UI hint**: yes

### Phase 4: Conditional Re-Sim + Live Mode
**Goal**: The killer feature — lock real results round by round, re-simulate conditioned on standings/Buchholz/rematch history, and show each locked pick as live/dead/secured with a P(≥5)-from-here delta, rendered over a record-bucket bracket.
**Mode:** mvp
**Depends on**: Phase 1 (engine `locked` support), Phase 2 (`locked` in cache key), Phase 3 (P(≥5) scoring reused for the from-here delta)
**Requirements**: RESIM-01, RESIM-02, RESIM-03, RESIM-04
**Success Criteria** (what must be TRUE):
  1. Locking a real round result fires a conditional re-sim automatically via the `locked` cache key; locked winners are deterministic and at least one P(advance) value moves (RESIM-01).
  2. Each locked pick displays as live / dead / secured with a P(≥5)-from-here delta arrow (e.g. `71% → 58%`), showing the change rather than a new static number (RESIM-02).
  3. An impossible locked pairing (a rematch or an already-terminated team) is rejected with a reason, not silently accepted (RESIM-03).
  4. The bracket renders as record-bucket columns (HLTV/Liquipedia convention, never a tree) with locked/real results solid and simulated branches faint (RESIM-04).
**Plans**: TBD
**UI hint**: yes

**Note:** This phase is primarily UI additions and classification logic — re-sim fires for free because `locked` is already in the cache key from Phase 2 and honored by swiss.py from Phase 1. If those Phase 1×2 seams were skipped, this becomes a re-architecture.

### Phase 5: Odds Ensemble
**Goal**: Live multi-provider market odds blended into honestly-banded probabilities and back-solved into per-team ratings — a fail-soft enhancement that never crashes, never gates, and writes a read-only cache the app only reads.
**Mode:** mvp
**Depends on**: Phases 1–4 (engine, UI, optimizer, re-sim all proven; epistemic outer loop stubbed in Phase 1)
**Requirements**: ODDS-01, ODDS-02, ODDS-03, ODDS-04, ODDS-05, ODDS-06, ODDS-07, ODDS-08
**Success Criteria** (what must be TRUE):
  1. With provider keys present, a "fetch now" button (and per-round triggers) pulls OddsPapi (Pinnacle anchor) + Polymarket + Kalshi, normalizes per source (de-vig fixed-odds, spread/fee-only for prediction markets), and log-opinion-pools them weighted by originate/liquidity — never headcount — into a blended p + cross-source variance (ODDS-01/ODDS-02/ODDS-03).
  2. With NO key, the app runs rating-only with a one-line info banner and never crashes or hard-blocks; the zero-config first run from Phase 2 still works (ODDS-08).
  3. Ratings back-solve inverts each known series prob to map-level (identity Bo1, invert `p²(3−2p)` for Bo3) then fits per-team ratings via logistic least-squares; live odds override the imminent round's known matchups (ODDS-04).
  4. The epistemic outer loop draws p ~ Beta(blend, clamped var) with `variance < p(1-p)` clamp before the moment fit; the reported band ⊇ the inner Wilson band and does NOT shrink with N on high-disagreement matches (wires PROB-03/PROB-04/PROB-05).
  5. Adapters discover Cologne fixtures/slugs dynamically; the fetch writes a read-only `data/odds_cache.json` the app only ever reads, and the app never calls `get_quotes()` on a rerun (ODDS-05/ODDS-06/ODDS-07).
**Plans**: TBD
**UI hint**: yes

**Cross-phase seam to honor NOW:**
- **(Phase 5×v2 read-only cache seam) ODDS-07:** The v1 manual "fetch now" button and the deferred v2 cron job must both call the SAME `scripts/fetch_odds.py` and write the SAME `data/odds_cache.json` that the app reads. Build the cache contract here so the v2 cron (OPS-01, deferred) is a single crontab line with **zero app changes** — a drop-in. The app never imports the fetch script and never calls providers on a Streamlit rerun (Pitfall 11).
- Beta variance clamp before the moment fit, or the fit crashes on exactly the thin-liquidity matches that matter most (Pitfall 5). Route de-vig on `vig_type`; never apply fixed-odds de-vig to a prediction-market price (Pitfall 8). Invert series→map before fitting; never fit ratings to series probs directly (Pitfall 9). Treat the OddsPapi soft-book bundle as ~one sharp opinion, not independent sources (Pitfall 7).

**Research flag:** Thin verification pass needed once IEM Cologne markets post — confirm OddsPapi CS2 coverage, Polymarket event slugs, Kalshi series tickers; budget OddsPapi's ~250 req/month quota against any historical backtest pulls.

### Phase 6: Full-Major v3
**Goal**: Extend the validated engine to the whole Major — Stages 2 and 3 Swiss plus the playoff single-elimination bracket — reusing the same correctness core, with optional map-level Bo3 modeling added only if backtest evidence demands it.
**Mode:** mvp
**Depends on**: Phases 1–5 (full v1 stack + passed backtest)
**Requirements**: V3-01, V3-02, V3-03, V3-04
**Success Criteria** (what must be TRUE):
  1. Stage 2 and Stage 3 Swiss simulate via the same engine with different seeds, producing per-team probs that pass the same invariants (V3-01/V3-02).
  2. The playoff single-elimination bracket simulates and is optimized end-to-end (V3-03).
  3. Map-level Bo3 modeling is added ONLY if Phase 1's backtest evidence shows the single-series-prob `p²(3−2p)` assumption is the error source; otherwise the single win prob per matchup stands and V3-04 is explicitly closed as not-needed (V3-04).
**Plans**: TBD
**UI hint**: yes

**Map-level Bo3 gate:** The iid closed form is exact for identical independent maps; sampling 3 map Bernoullis only adds MC noise without accuracy gain. Map-pool/veto modeling is a significant data burden — do not add it unless backtest evidence demands it.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Engine + Backtest Gate | 4/4 | Plans done (GATE-01/04 deferred) | 2026-05-29 |
| 2. Streamlit UI Shell | 2/3 | In progress | - |
| 3. Pick'Em Optimizer | 0/TBD | Not started | - |
| 4. Conditional Re-Sim + Live Mode | 0/TBD | Not started | - |
| 5. Odds Ensemble | 0/TBD | Not started | - |
| 6. Full-Major v3 | 0/TBD | Not started | - |
