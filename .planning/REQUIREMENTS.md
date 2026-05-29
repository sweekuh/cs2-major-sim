# Requirements: swiss-mc — Cologne 2026 Swiss MC & Pick'Em Optimizer

**Defined:** 2026-05-28
**Core Value:** Honestly-calibrated probabilities for the exact quantities Pick'Em scores on — P(3-0)/P(advance)/P(0-3) per team and P(≥5/10) per ballot — including conditional re-sim, without laundering guesses into false precision.

> Scope this milestone = full **v3**. Pick'Em scoring = **official Valve binary** (2/6/2, ≥5/10, exact-record 3-0/0-3). Odds v1 = **all three providers live** (Pinnacle/OddsPapi + Polymarket + Kalshi).

## v1 Requirements

### Engine (Swiss correctness core)

- [ ] **ENG-01**: Engine builds Round 1 pairings as seed N vs seed N+8, derived from the single seed→team map (no second hardcoded copy)
- [ ] **ENG-02**: Rounds 2+ group active teams by (wins, losses) record and seed within group by Difficulty Score descending then initial seed ascending, via a single code path (no `if round == 2` special case)
- [ ] **ENG-03**: Difficulty Score is computed as `Σ(opp.wins − opp.losses)` over a team's played opponents (NOT `Σ opp.wins`)
- [ ] **ENG-04**: Within-group pairing uses rematch-avoiding high-vs-low fold; the fold sorts on the difficulty-ranked order, not raw seed
- [ ] **ENG-05**: When no rematch-free perfect matching exists, the engine pairs the least-disruptive rematch and logs a warning instead of crashing (no unhandled `None`)
- [ ] **ENG-06**: A match is Bo3 iff either team is at 2 wins (advancement) or 2 losses (elimination); otherwise Bo1
- [ ] **ENG-07**: No pair plays twice within a stage (no rematches); teams terminate at 3 wins (advance) or 3 losses (eliminated) with final record recorded
- [ ] **ENG-08**: Engine accepts `locked: dict[frozenset({id,id}) -> winner_id]` and uses locked winners deterministically (no sampling), respecting locked history in the no-rematch rule
- [ ] **ENG-09**: RNG is injected as a `seed` param threaded through the MC for reproducible runs/backtests, using `numpy.random.SeedSequence.spawn` so reproducibility survives chunked execution

### Backtest gate (HARD GATE — blocks UI and trusted output)

- [ ] **GATE-01**: Round-by-round backtest feeds a completed past Major stage (Budapest 2025 or Austin 2025) seeds + forced results and asserts the engine reproduces the actual round-by-round pairings exactly
- [ ] **GATE-02**: `test_difficulty_formula` asserts `difficulty()` on Valve's worked example (opponents 2-0 and 1-1) == 2
- [ ] **GATE-03**: `test_forced_rematch_pairing` (group whose ideal fold is a rematch matches Valve's priority table) and `test_no_valid_matching_fallback` (forced unmatchable group pairs without crashing) both pass
- [ ] **GATE-04**: The exact Valve rematch priority table is pulled verbatim from `major-supplemental-rulebook.md` during this phase; greedy fold is replaced by literal table lookup if any backtest pairing diverges
- [ ] **GATE-05**: No sim output is trusted and no UI is built until GATE-01 passes

### Monte Carlo runner

- [ ] **MC-01**: Runs N stage simulations (default 100k) tallying per-team count of 3-0, advance (any 3-W), and 0-3
- [ ] **MC-02**: Outputs per-team P(3-0)/P(advance)/P(0-3) with Wilson confidence bands
- [ ] **MC-03**: Probability invariants hold every run within tolerance (±0.05 at N≥50k): Σ P(3-0)≈2, Σ P(0-3)≈2, Σ P(advance)≈8
- [ ] **MC-04**: MC retains the full per-sim record sample (not just marginals) so the optimizer's P(≥5) and conditional re-sim can score against it
- [ ] **MC-05**: MC is structured generator-first — yields incremental tally aggregates per chunk (e.g. 20×5k) to drive a progress bar — with a separate cached wrapper for the final result
- [ ] **MC-06**: Series win prob uses closed-form Bo3 `p²(3−2p)` as a single Bernoulli draw (no 3-map sampling); Bo1 = `p_map`

### Probabilities & math

- [ ] **PROB-01**: Per-map win prob `p_map(a,b) = 1/(1 + 10^(-(rating_a − rating_b)/S))`, S default 40, exposed as a slider
- [ ] **PROB-02**: An odds-derived probability for an exact matchup is used directly as the series prob (Bo3 formula NOT re-applied — the market already prices the series)
- [ ] **PROB-03**: Epistemic uncertainty (source disagreement) is modeled as an OUTER loop — sample p-vector from Beta(blend, var) per epistemic draw, run an MC batch per draw, aggregate across draws — never folded into per-sim sampling
- [ ] **PROB-04**: Beta method-of-moments fit clamps `variance < p(1−p)` before fitting so low-liquidity high-disagreement matches do not crash
- [ ] **PROB-05**: Reported band = epistemic spread across draws (⊇ inner Wilson aleatoric band); a single source collapses the band to Wilson only

### Pick'Em optimizer (Valve binary)

- [ ] **OPT-01**: Ballot A (E[correct]-optimal) via greedy: top 2 by P(3-0), top 2 by P(0-3), top 6 by P(advance) excluding the four chosen
- [ ] **OPT-02**: Ballot B (P(≥5)-optimal) via hill-climb single-team swaps scored by P(≥5) against the stored per-sim sample (no brute-force enumeration)
- [ ] **OPT-03**: Both ballots are valid (exactly 2/6/2, no team in two buckets) and reported side by side with differing picks highlighted
- [ ] **OPT-04**: P(≥5/10) is computed for the chosen ballot by scoring each simulated stage against it
- [ ] **OPT-05**: Correlated-pick warning surfaces when the two 0-3 picks meet in Round 1 (caps correct picks); Ballot B avoids the trap automatically

### Conditional re-simulation & live mode (killer feature)

- [ ] **RESIM-01**: User locks actual results round by round; MC re-runs conditioned on current standings/Buchholz/rematch history; re-sim fires via the cache key including `locked`
- [ ] **RESIM-02**: Each locked pick is shown as live / dead / secured with a P(≥5)-from-here delta (e.g. `71% → 58%`)
- [ ] **RESIM-03**: An impossible locked pairing (e.g. a rematch or already-terminated team) is rejected with a reason, not silently accepted
- [ ] **RESIM-04**: Record-bucket bracket view (columns by W-L record, HLTV/Liquipedia convention — NOT a tree); locked/real results solid, simulated branches faint

### Odds ensemble (all three providers live)

- [ ] **ODDS-01**: `OddsProvider` adapter interface (`get_quotes(matches) -> [OddsQuote]`) + `pool()`; providers OddsPapi (Pinnacle anchor), Polymarket, Kalshi all implemented live
- [ ] **ODDS-02**: Per-source normalization — de-vig fixed-odds two-way `p_a = (1/o_a)/(1/o_a + 1/o_b)`; treat prediction-market price as ~probability adjusting only for spread/fees
- [ ] **ODDS-03**: Liquidity- and sharpness-weighted log-opinion pool outputs blended p + cross-source variance; weight by originate-vs-copy not headcount; downweight thin/low-`n_sources` markets and quotes near Polymarket UMA resolution
- [ ] **ODDS-04**: Ratings back-solve — invert each known-round series prob to per-map p (identity Bo1; invert `p²(3−2p)` for Bo3), fit per-team ratings via logistic least-squares at map level; live odds override the imminent round's known matchups
- [ ] **ODDS-05**: Adapters discover Cologne fixtures/market slugs dynamically (markets don't exist until the bracket posts); CS2 sportId/series filtering
- [ ] **ODDS-06**: Fetch is not streaming — manual "fetch now" button plus per-round triggers; keys read from env (`.env` gitignored, `.env.example` shipped)
- [ ] **ODDS-07**: Odds fetch writes a read-only `data/odds_cache.json` contract that the app only ever reads (seam preserved for the v2 cron job); the app never calls `get_quotes()` on rerun
- [ ] **ODDS-08**: Missing provider key → app runs rating-only with a one-line info banner; never crashes or hard-blocks (fail soft)

### Full-Major scope (v3)

- [ ] **V3-01**: Stage 2 Swiss simulated via the same engine
- [ ] **V3-02**: Stage 3 Swiss simulated via the same engine
- [ ] **V3-03**: Playoff single-elimination bracket simulated and optimized
- [ ] **V3-04**: Optional map-level Bo3 modeling — added only if backtest evidence demands it (otherwise single win prob per matchup)

### Interface & UX (Streamlit)

- [ ] **UI-01**: Explicit two-mode toggle (Pre-stage / Live); main column reorders by mode (Pre-stage: ballot hero → per-team probs → bracket; Live: locked-pick status + P(≥5)-from-here hero → delta probs → bracket)
- [ ] **UI-02**: Controls: rating `st.data_editor`, S slider, sim-count input, Run button; MC wrapped in `@st.cache_data` keyed on `(ratings, S, N, locked)`
- [ ] **UI-03**: Loading shows a progress bar + live running P(advance) tally fed by the MC generator (not a blank spinner)
- [ ] **UI-04**: Every probability cell renders the number + an always-visible inline CI mini-bar (never hover/expand-hidden)
- [ ] **UI-05**: All four interaction states built per feature (loading / empty-pre-run / error / success-partial), including inline cell errors that block the run on bad ratings
- [ ] **UI-06**: Visual tokens enforced — monospace for all numbers; one accent color for primary action/hero numbers; colorblind-safe status (advanced=blue, eliminated=amber, never red/green) always paired with text label + glyph (`o live` / `x dead` / `/ secured`); contrast ≥4.5:1
- [ ] **UI-07**: Persistent "engine validated vs [stage] backtest ✓" trust badge tied to the backtest gate

### Inputs, data & DX

- [ ] **DX-01**: Ship `data/stage1.json` with editable [INFERRED] seeds + default ratings so the first run needs no API key and no editing
- [ ] **DX-02**: Persistent dismissable in-app banner `⚠ Seeds are INFERRED — verify vs the official seed list before trusting outputs.` with a "seeds confirmed" toggle to dismiss
- [ ] **DX-03**: `uv run streamlit run app.py` one-command bootstrap, identical on Windows/Mac/Linux, Python pinned `>=3.12` in `pyproject.toml`; pip fallback documented; no bash-only `run.sh`
- [ ] **DX-04**: README quickstart at top in order: what-it-is → run command (+pip fallback) → "first sim needs no API key" + ~15s expectation → what the numbers mean → [INFERRED]-seed reconcile step → optional `.env.example` for live odds; ends with a 30-second event-day cold-start drill
- [ ] **DX-05**: `.env.example` lists optional provider keys; `.env` gitignored

## v2 Requirements

Deferred to future release. Tracked, not in current milestone phasing unless roadmapper pulls forward.

### Operations

- **OPS-01**: Standalone cron job (Ubuntu host) calls providers and writes `data/odds_cache.json`; app reads only — auto-fetch once per round after pairings post (TODOS #1; zero app change if ODDS-07 seam honored)
- **OPS-02**: Numba JIT acceleration of the Swiss hot loop to bring 100k-sim runs under ~2s — only if pure-Python latency annoys during live use (TODOS #2; requires array-of-structs refactor)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Account / auth / multi-user | Single local user; adds nothing for the use case |
| Map-veto / map-pool modeling | Single win prob per matchup; map-level Bo3 only as V3-04 stretch if backtest demands |
| Scraping / browser automation | Every source has a clean API; scraping is fragile, slow, ToS-risky, adds no signal |
| Champion / Diamond-coin endgame prediction | Out of scope for a Pick'Em-EV tool |
| Streaming / live-tick odds | Pick'Em locks once per stage; streaming buys nothing over per-round fetch |
| Third-party confidence-pool scoring | Confirmed format is Valve binary; weighted-points objective not needed |
| localStorage/sessionStorage | Keep state in Streamlit `session_state` |
| Responsive / mobile / tablet, theming, branding | Local single-user desktop tool |
| Community/Discord/issue templates, SDK, DX telemetry | Private tool |

## Traceability

Which phases cover which requirements. Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| (populated by roadmapper) | — | Pending |

**Coverage:**
- v1 requirements: 48 total
- Mapped to phases: 0 (pending roadmap)
- Unmapped: 48 ⚠️ (resolved at roadmap step)

---
*Requirements defined: 2026-05-28*
*Last updated: 2026-05-28 after initial definition*
