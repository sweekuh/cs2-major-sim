# Project Research Summary

**Project:** swiss-mc - Cologne 2026 CS2 Major Swiss Monte Carlo + Pick'Em Optimizer
**Domain:** Local single-user scientific/simulation webapp (Monte Carlo + market-odds ensemble) in Python/Streamlit
**Researched:** 2026-05-28
**Confidence:** HIGH (engine, stack, features, pitfalls) / MEDIUM (odds-provider live access terms)

---

## Executive Summary

This is a correctness-critical local analytics tool: a Monte Carlo simulator of the CS2 Major Swiss stage that produces calibrated probabilities for a Pick'Em ballot optimizer. The entire product value rests on a faithful reimplementation of Valve's Swiss format (Buchholz seeding, fold pairing with rematch avoidance, Bo3 advancement/elimination matches) and on honest reporting of uncertainty through Wilson confidence intervals and, when odds are available, an outer epistemic loop over source disagreement. Every probability the tool emits is garbage if the pairing logic is wrong, and the only way to prove it is not wrong is a round-by-round backtest against a completed real Major (Budapest/Austin 2025). **The backtest is therefore the build's hard gate, not post-hoc validation.** No UI, optimizer, or odds layer should be built or trusted until the backtest passes exactly.

The recommended build order is strictly dependency-driven: engine + backtest gate (Phase 1) -> Streamlit UI with caching (Phase 2) -> Pick'Em optimizer with Ballot A/B (Phase 3) -> conditional re-simulation and live mode (Phase 4) -> odds ensemble with ratings back-solve (Phase 5) -> v3 extensions (Stages 2-3, playoffs, optional map-level Bo3). Each layer depends irreversibly on the layer below it: the optimizer needs the stored MC sim sample, re-sim needs the locking support built into the engine from day one, and the odds layer can only fail-soft once the rating-only path is proven. This order is not a preference; reversing any dependency pair forces a rewrite.

The primary risks are all silent-failure modes: a plausible-looking Buchholz formula that passes structural invariants while corrupting all probabilities, a `@st.cache_data` key that omits `locked` and returns stale distributions silently in live mode, a Beta uncertainty draw placed in the wrong loop that makes confidence bands shrink to false precision, and a monolithic MC runner that cannot be retrofitted with per-chunk progress yielding without a rewrite. These must each be addressed at their prevention phase, not discovered during event-day use.

---

## Key Findings

### Recommended Stack

The PRD/HANDOFF stack is sound and current for 2026. Build it as specified. Python 3.12, Streamlit 1.57.x (the 2026 ASGI release), numpy 2.4.x, and `uv` for environment management are all at their current stable releases and mutually compatible. The three odds providers (OddsPapi, Polymarket Gamma, Kalshi) are all live with CS2 markets and read-only-accessible in 2026: OddsPapi needs one API key, the other two require no authentication for read access. `httpx` is preferred over `requests` for the odds layer (forward-looking, free async path). Numba, pandas, and scipy should all be deferred.

**Core technologies:**
- **Python 3.12** (`>=3.12,<3.14`) - runtime, PRD-mandated, mature and fast
- **Streamlit 1.57.x** (`>=1.57,<1.58`) - UI + single-process host; only option that can hold API keys and make server-side odds calls; `@st.cache_data` semantics unchanged
- **numpy 2.4.x** (`>=2.4,<2.5`) - vectorized MC Bernoulli draws, record-vector tallying, Wilson CI bands, optimizer scoring
- **uv (>=0.9)** - env + lockfile + cross-platform bootstrap; `uv run streamlit run app.py` identical on Windows/Mac/Linux
- **httpx 0.28.x** - HTTP client for all three odds adapters; sync API is requests-compatible; free async path if needed
- **python-dotenv 1.x** - API keys from gitignored `.env`; fail-soft no-key-to-rating-only contract
- **pytest 8.x** (dev only) - engine acceptance tests + the hard-gate backtest

**Deferred (reversible, do not add yet):**
- numba >=0.65 - JIT only if pure-Python 100k latency annoys during the live event; 0.65.x supports py3.12-3.14 + numpy 2.4
- pandas, scipy - not justified by data scale; add scipy only if logistic back-solve fit proves fussy

### Expected Features

**Must have - table stakes (v0-v1 core):**

- **Faithful Valve Swiss engine** - N vs N+8 pairing, record-grouped Buchholz seeding (sum(opp.wins - opp.losses), NOT sum-of-wins), fold with 15-row rematch priority table, Bo3 on advancement/elimination/decider, 3W/3L terminate; 8 advance, 8 out
- **Round-by-round backtest gate** - reproduces Budapest/Austin 2025 exact pairings; BLOCKER for all downstream work
- **Monte Carlo P(3-0) / P(advance) / P(0-3)** - 100k default sims; invariants sum(3-0)=2, sum(0-3)=2, sum(adv)=8 every run; correct scoring requires P(exact 3-0), not P(advance)
- **Editable seeds/ratings + S spread slider + zero-config defaults** - first run ships with data/stage1.json; no API key required
- **Wilson CI bands visible inline** - always-visible mini-bars under every probability, never hidden behind hover
- **Pick'Em Ballot A (E[correct], greedy + exact-record scoring)** - table stakes for a pick'em tool
- **[INFERRED]-seed loud banner** - persistent until field-by-field reconcile against official list is confirmed
- **One-command cross-platform bootstrap** - `uv run streamlit run app.py`; pip fallback documented

**Should have - differentiators (v1-v2):**

- **P(>=5/10) headline number** - real coin-upgrade odds; nonlinear, correlation-sensitive; requires storing per-sim record sample, not just marginals
- **Ballot B (P(>=5) hill-climb) + dual-ballot diff** - the divergence between A and B is the insight: safe-EV ballot vs coin-clearing ballot
- **Correlated-pick warning** - two 0-3 picks sharing an R1 matchup is a pick cap trap Ballot A is blind to; falls out of Ballot B's joint sample for free
- **Conditional re-simulation (F6)** - the killer feature; lock real results round-by-round, MC re-runs conditioned on standings/Buchholz/rematch history; no public tool does this
- **Live pick status - live/dead/secured + P(>=5)-from-here delta** - shows the change (e.g. 71% to 58%), not a new static number
- **Record-bucket bracket view** - HLTV/Liquipedia column convention; locked results solid, simulated faint; never a bracket tree
- **Odds ensemble (Pinnacle via OddsPapi + Polymarket + Kalshi)** - de-vigged, log-opinion pooled, liquidity-weighted; fails soft to rating-only mode with banner
- **Ratings back-solve from odds** - invert series prob to map-level, then logistic least-squares; lets MC price unplayed branches the market never quotes
- **Backtest trust badge** - ties the UI credibility claim to the gate pass; displayed with seeds-confirmed state

**Defer to v3:**
- Stages 2-3 Swiss (same engine, different seeds; trivial reuse once Stage 1 validated live)
- Playoff single-elimination bracket (simpler than Swiss; add once stages done)
- Map-level Bo3 modeling (conditional: add ONLY if backtest shows single-series-prob modeling is insufficient)
- Epistemic CI bands via outer-loop Beta draws (requires multi-source odds; with one source, band correctly collapses to Wilson)

**Verified domain facts - lift directly into requirements as correctness assertions:**
- Buchholz / Difficulty Score = sum(opp.wins - opp.losses); can be negative; sum(o.wins) is WRONG (Valve worked example: opponents at 2-0 and 1-1 yields (2+1)-(0+1) = 2)
- Stage 1 ballot = 2 (3-0) + 6 (advance) + 2 (0-3) = 10 picks; need >=5 correct to upgrade coin; confirmed for IEM Cologne 2026
- 3-0 and 0-3 scored on EXACT final record; a 3-0 pick that finishes 3-1 scores zero
- Tiebreak chain: record first (constant within group, so implicit), then Difficulty Score, then initial seed
- All three odds providers live and read-only-accessible in 2026 with CS2 Major markets present

### Architecture Approach

The system is a three-layer single-process app (presentation -> domain -> odds) with one out-of-process satellite (the odds fetch job). The architectural spine is a strict one-directional dependency chain: `engine/` is a pure, deterministic, dependency-free core with no Streamlit imports and no network calls; `app.py` is the impure shell that owns all I/O, widget state, and cache keying; `odds/` is a decoupled acquisition layer whose providers are called only by a standalone fetch script, never on a Streamlit rerun. The MC runner must be written generator-first from day one (yielding per-chunk partial aggregates) so the progress bar and the `@st.cache_data` boundary can coexist via a two-function split.

**Major components:**

| Component | Responsibility | Critical constraint |
|-----------|----------------|---------------------|
| `engine/teams.py` | Seed-to-team map; derives R1 pairing as `[(i, i+8) for i in range(1,9)]` | Single source of truth for seeds; no hardcoded second copy |
| `engine/swiss.py` | Faithful Valve pairing + stage sim; accepts `locked: dict[frozenset->winner]` | RNG injected as seed param; locked support from day one even before UI |
| `engine/probs.py` | p_map, Bo3 closed form, de-vig, pool(), ratings back-solve | Pure functions; no Streamlit, no HTTP |
| `engine/montecarlo.py` | Epistemic outer loop + aleatoric inner loop; yields per-chunk partial aggregates | Generator-first from slice 1; stores per-sim record sample |
| `engine/optimizer.py` | Ballot A (greedy E[correct]) + Ballot B (hill-climb P(>=5) against stored sample) | Consumes stored sample; never re-runs the MC |
| `odds/base.py` + `odds/cache.py` | OddsProvider Protocol + cache read/write contract (data/odds_cache.json) | Cache contract between two processes; split so v2 cron is zero-app-change |
| `scripts/fetch_odds.py` | Standalone fetch satellite; sole get_quotes() caller; sole cache writer | Out-of-process; app.py never imports it; same script for manual button and v2 cron |
| `app.py` | Widget IA, cache keying (ratings, S, N, locked), progress bar, two-mode layout | Never calls get_quotes(); reads odds_cache.json only |

### Critical Pitfalls

**CORRECTNESS-FATAL - silent, pass invariants, corrupt all probs:**

1. **Buchholz as sum(opp.wins) instead of sum(opp.wins - opp.losses)** - most online explanations are wrong; Valve's formula can produce negative scores; invariant tests alone will NOT catch this; detection requires test_difficulty_formula with Valve's worked example AND backtest exact pairings

2. **Greedy fold diverging from Valve's 15-row priority table in Round 4/5** - passes no-rematch test but returns a valid-but-wrong matching; budget time for the literal priority-table-lookup fallback inside Phase 1 before building anything else on top

3. **Fold operating on raw initial seed instead of Difficulty-Score-then-seed ranking in R3+** - Buchholz formula can be correct but never used as the fold key; detection: unit test with a 4-team group where Buchholz order differs from seed order

4. **Beta draw inside the per-sim inner loop (epistemic collapsed into aleatoric)** - produces falsely tight bands that look MORE trustworthy at large N; outer-loop structure must be stubbed in Phase 1 even though odds don't arrive until Phase 5

5. **@st.cache_data key omitting `locked`** - live mode silently returns stale pre-lock distribution; the killer feature returns a lie; detection: lock a result, confirm at least one P(advance) value changes

**OPS-FATAL - works in dev, breaks on event day:**

6. **Odds fetch inside the Streamlit rerun path** - Streamlit reruns on every widget change; Community Cloud sleeps between requests; app reads odds_cache.json only; scripts/fetch_odds.py is the sole provider caller

7. **Missing API key hard-crashing instead of failing soft** - zero-config first run is a core promise; missing key must yield rating-only mode + info banner, never an exception

**Cross-phase silent-failure seams - flagged explicitly for the roadmapper:**

- **(Phase 1 x Phase 2) numpy RNG reproducibility vs chunked-progress yielding** - np.random.default_rng(seed) is reproducible single-threaded but not across varying chunk counts; use SeedSequence(seed).spawn(n_chunks) and pin n_chunks; design decision belongs in Phase 1, chunking arrives in Phase 2
- **(Phase 2 x Phase 4) @st.cache_data key must include `locked`** - must be in the cache key from Phase 2 even though the locking UI arrives in Phase 4; otherwise Phase 4 is a re-architecture, not a feature addition
- **(Phase 1 x Phase 3/4) MC must retain full per-sim record sample** - Ballot B P(>=5) and re-sim P(>=5)-from-here delta both score each simulated record vector against the ballot; storing only marginals requires a full MC rewrite when Phase 3 arrives
- **(Phase 5 x Phase 6/v2) odds read-only cache seam written in Phase 5 for v2 cron** - v1 manual button and v2 cron must call the same scripts/fetch_odds.py and write the same odds_cache.json; v2 is then a single crontab line with zero app changes

---

## Implications for Roadmap

The build order is forced by hard dependencies, not preference. Reversing any adjacent pair requires a partial or full rewrite of the affected components.

### Phase 1: Engine + Backtest Gate

**This is a HARD GATE. Nothing else starts until this passes.**

**Rationale:** Every downstream probability is garbage if the pairing logic is wrong. The gate proves greedy rematch resolution matches Valve's 15-row priority table on real historical data. Invariant tests (sum=2/8) are necessary but insufficient: a wrong Buchholz formula still produces invariant-passing outputs with wrong probabilities. This is a blocker, not validation.

**Delivers:** A pytest-runnable headless engine that reproduces Budapest/Austin 2025 round-by-round pairings exactly. Backtest trust badge earned.

**Implements:** engine/teams.py, engine/swiss.py, engine/probs.py, engine/montecarlo.py (generator-first, epistemic outer loop stub, per-sim record matrix retained), tests/test_swiss.py (backtest + test_difficulty_formula + test_forced_rematch_pairing + test_locked_results_honored), tests/test_probs.py

**Cross-phase seams to honor NOW - before the features that need them arrive:**
- RNG injected as seed param; use SeedSequence(seed).spawn(n_chunks) for reproducibility across chunk counts (Phase 1x2 seam)
- swiss.py accepts locked: dict[frozenset->winner] from day one - Phase 4 UI depends on this; skipping forces a swiss.py rewrite later
- MC written generator-first: run_mc_progressive yields per-chunk partials; run_mc_cached drains it - Phase 2 cache split depends on this; retrofitting is a rewrite of the hottest code path
- Outer epistemic loop structure stubbed as a single-draw no-op - Beta draw must live in the OUTER loop or Phase 5 is a rewrite
- Per-sim record matrix stored, not just marginals - Ballot B and P(>=5)-from-here delta both require it

**Avoids:** Pitfalls 1 (Buchholz formula), 2 (priority table), 3 (fold key), 4 (epistemic loop structure), 10 (numpy reproducibility)

**Research flag:** Fetch Valve's literal 15-row pairing priority table verbatim from github.com/ValveSoftware/counter-strike_rules_and_regs during this phase. Budget time for the priority-table-lookup fallback if greedy diverges on Round 4/5 groups - this is a planned fork, not a surprise.

---

### Phase 2: Streamlit UI (shell, caching, CI bands, zero-config UX)

**Rationale:** Engine proven correct. Build the presentation shell. The cache key must include locked from the start even though the re-sim UI lands in Phase 4. The progress bar requires the generator-first MC shape from Phase 1.

**Delivers:** app.py with editable data_editor, S/N sliders, Run button, results table with Wilson CI mini-bars, two-mode layout skeleton, [INFERRED]-seed banner with reconcile-diff before confirm, backtest trust badge, zero-config first run with no API key.

**Cross-phase seams to honor NOW:**
- Cache key is (ratings, S, N, locked) - locked included even though locking UI is Phase 4 (Phase 2x4 seam)
- Trust badge tied to BOTH backtest-passed AND seeds-confirmed, not just one
- Two-function MC split: run_mc_progressive uncached driver + @st.cache_data run_mc_cached; on cache miss drive bar from progressive; on cache hit serve instantly

**Avoids:** Pitfalls 6 (seed reconcile), 13 (cache key missing locked), 15 (Bo1 variance honesty)

**Research flag:** Standard Streamlit patterns; no additional research needed.

---

### Phase 3: Pick'Em Optimizer

**Rationale:** UI proven usable. Add the decision layer. Ballot B and P(>=5) both require the per-sim record sample built into the MC in Phase 1. Correlated-pick warnings fall out of Ballot B's joint sample for free.

**Delivers:** engine/optimizer.py with Ballot A (greedy E[correct], exact-record scoring), Ballot B (hill-climb P(>=5) vs stored sample), dual-ballot diff display, P(>=5) headline number, correlated-pick warning when two 0-3 picks share an R1 matchup.

**Critical dependency:** Optimizer reads the stored sample; never re-runs the MC. Exact-record scoring: P(exactly 3-0), not P(advance); a 3-0 pick that finishes 3-1 scores zero.

**Avoids:** Pitfall 14 (correlated 0-3 picks), Pitfall 15 (P(>=5) headlined)

**Research flag:** Standard Python scoring math; no additional research needed.

---

### Phase 4: Conditional Re-Simulation + Live Mode + Bracket View

**Rationale:** The killer feature. Depends on locked support in swiss.py (Phase 1), cache key including locked (Phase 2), and P(>=5) scoring from the stored sample (Phase 3). At this phase all three are already built - this phase is primarily UI additions and classification logic.

**Delivers:** Result-locking widgets, live/dead/secured pick classification, P(>=5)-from-here delta display (e.g. 71% to 58%, not a new static number), record-bucket bracket view (HLTV/Liquipedia column convention; locked solid, simulated faint; NOT a bracket tree).

**Key insight:** Re-sim fires automatically because locked is already in the cache key from Phase 2 - no architecture change needed. This phase is UI additions, not a re-architecture.

**Avoids:** Bracket tree anti-pattern, colorblind red/green status, swapping static P(>=5) without showing the delta

**Research flag:** Standard patterns; no additional research needed.

---

### Phase 5: Odds Ensemble + Ratings Back-Solve + Read-Only Cache Seam

**Rationale:** Engine, UI, optimizer, and re-sim all proven. Now add live-market inputs. This phase has the most external dependencies and the most correctness traps in a single phase, but it fails soft - a missing key or provider outage must never crash the app.

**Delivers:** OddsPapiProvider live (Pinnacle anchor), PolymarketProvider and KalshiProvider stubbed-then-live, pool() with liquidity-weighted log-opinion pooling (NOT headcount weighting), de-vig routing on vig_type, ratings back-solve (invert series to map-level, logistic least-squares on map probs), scripts/fetch_odds.py standalone satellite, odds/cache.py, odds_cache.json (gitignored), .env.example.

**Critical seams to honor:**
- App reads odds_cache.json only; never calls get_quotes() on a Streamlit rerun
- READ-ONLY CACHE SEAM WRITTEN HERE FOR V2 CRON: v1 manual button and v2 cron call the same scripts/fetch_odds.py and write the same cache; v2 adds a crontab line and nothing else
- Missing key yields rating-only mode + banner, never an exception
- Beta variance clamp: v = min(v, p*(1-p) - epsilon) BEFORE moment fit; crashes on exactly the thin-liquidity matches that matter most
- Epistemic outer loop wired here to Beta draws; loop structure was stubbed in Phase 1 - this phase fills in the content
- Weight by originate/liquidity, not headcount; soft books in OddsPapi bundle are approximately one sharp opinion, not independent sources
- Route de-vig on vig_type: fixed-odds overround removal for books; spread/fee adjustment only for prediction markets; never apply the same normalization to both
- Back-solve: invert Bo3 series to map-level first, THEN logistic least-squares on map probs; never fit ratings to series probs directly
- Verify provider market slugs dynamically (tournament/team filter), not hardcoded IDs

**Avoids:** Pitfalls 4 (epistemic outer loop wired), 5 (Beta clamp), 7 (ensemble independence illusion), 8 (vig routing), 9 (series/format conflation), 11 (Streamlit scheduler), 12 (fail-soft no key)

**Research flag:** Thin verification pass needed once IEM Cologne markets post. Confirm OddsPapi CS2 Major coverage, Polymarket event slugs, Kalshi series tickers. OddsPapi free tier ~250 req/month - budget historical-odds backtest pulls or cache them to data/.

---

### Phase 6 (v2): Auto-Fetch Cron

**Rationale:** Cache seam written in Phase 5; v2 is one crontab line on the always-on host calling scripts/fetch_odds.py.

**Delivers:** Automated per-round odds refresh without any app rewrite.

**Research flag:** Standard cron; no research needed.

---

### Phase 7 (v3): Stages 2-3 + Playoffs + Optional Map-Level Bo3

**Rationale:** Stage 1 fully validated live. Stages 2-3 reuse the engine with different seeds - trivial. Playoffs are single-elimination - simpler than Swiss. Map-level Bo3 is the only genuinely new modeling and is conditional on backtest evidence.

**Map-level Bo3 gate:** The iid closed form p^2(3-2p) is exact for identical independent maps. Sampling 3 separate map Bernoullis only adds MC noise without accuracy gain. Add map-level modeling ONLY if the backtest shows the single-series-prob assumption is the error source.

**Research flag:** No additional research needed for Stages 2-3 or playoffs. Map-level Bo3: if triggered by backtest evidence, research map-pool/veto modeling - the data burden is significant.

---

### Phase Ordering Rationale

1. **Backtest gate is the absolute pivot.** Nothing downstream produces trusted numbers until the engine reproduces real pairings exactly. Invariant tests alone hide the most dangerous failure modes.

2. **Optimizer before re-sim.** Ballot B P(>=5) scoring machinery is reused by the live-mode P(>=5)-from-here delta. Building re-sim first would require building that scoring logic twice.

3. **Odds last.** Rating-only mode is fully functional. The odds layer is an enhancement that fails soft - it must not gate any earlier slice. Putting it last keeps all network/key/cache complexity out of the correctness path.

4. **Three cross-slice seams must be honored in Phase 1:** swiss.py accepts locked (needed in Phase 4), MC is generator-first (needed in Phase 2), epistemic outer loop structure is stubbed (needed in Phase 5). Missing them forces rewrites.

---

### Research Flags

**Phase 5 (odds ensemble) - needs thin verification pass at event time:**
- Confirm OddsPapi CS2 Major coverage and fixture filter for IEM Cologne 2026
- Confirm Polymarket Gamma event slugs for Cologne (markets won't exist until bracket announced)
- Confirm Kalshi series ticker for Cologne (KXCS2GAME series confirmed, per-event IDs unverifiable until event)
- Budget OddsPapi 250 req/month quota against any historical-odds backtest pulls

**Phase 7 (v3 map-level Bo3) - conditional research:**
- Only if Phase 1 backtest reveals single-series-prob modeling is the error source
- Map-pool/veto modeling is a significant data burden; avoid unless evidence demands it

**Phases 1-4 - standard patterns, skip research-phase:**
- Engine math and Streamlit caching patterns are well-documented in the HANDOFF spec
- Optimizer scoring and hill-climb search are standard Python
- Re-sim and live mode are purely additive once the engine locked param exists

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified against PyPI current stable (May 2026); Streamlit 1.57 ASGI change confirmed transparent; numpy/numba compat confirmed |
| Features / domain facts | HIGH | Buchholz formula, 2/6/2 ballot, >=5/10 threshold, exact-record scoring, Bo3 conditions verified verbatim against Valve supplemental rulebook + IEM Cologne 2026 guides |
| Architecture | HIGH | Validating an eng-reviewed handoff spec; all patterns confirmed correct; seams and anti-patterns are architectural reasoning over that spec |
| Pitfalls | HIGH (engine/stats) / MEDIUM (odds-ensemble) | Engine pitfalls cross-checked vs HANDOFF math + Valve sources + numpy docs; odds-ensemble pitfalls WebSearch-verified but market-mechanics-dependent |
| Odds provider access | MEDIUM | All three live and read-only-accessible confirmed from current docs; not exercised with live keys against Cologne fixtures (won't post until event) |

**Overall confidence:** HIGH on the build order, correctness model, and all domain facts. MEDIUM on odds provider specifics - access works, but Cologne-specific market slugs and Kalshi/Polymarket CS2 liquidity are unverifiable until the event.

### Gaps to Address

- **Provider market slugs:** Cologne-specific event IDs/slugs don't exist yet. Adapters must discover fixtures dynamically (filter by tournament/team), never hardcode. Flag Phase 5 for a verification pass once markets post.
- **Kalshi/Polymarket thin-liquidity calibration:** Access confirmed; signal quality on tier-2/0-3 candidates is the real risk. Downweighting thresholds need calibration against real market data at event time.
- **OddsPapi 250 req/month quota:** Fits trivially for ~5 per-round polls, but historical-odds backtest calls should be batched and cached to data/ to preserve the quota budget.
- **Greedy vs priority-table fork:** The backtest will definitively resolve whether greedy fold matches Valve's table on real Round 4/5 data. Budget Phase 1 time for the priority-table-lookup fallback - it is a planned fork, not a surprise.

---

## Sources

### Primary (HIGH confidence)
- Valve major-supplemental-rulebook.md (ValveSoftware/counter-strike_rules_and_regs) - Difficulty Score formula, tiebreak chain, pairing/rematch rules, Bo3 conditions
- HANDOFF_claude_code.md (eng/design/DX-reviewed executable spec) - build order, component contracts, math layer, UI/DX contracts
- PRD_cologne2026_pickem_simulator.md - architecture, stack, risks
- PROJECT.md - key decisions, correctness core, constraints
- TODOS.md - cron-fed odds cache seam, Numba deferral, backtest-as-gate
- streamlit PyPI + Streamlit 2026 release notes - 1.57.0 ASGI release, cache_data semantics
- numpy PyPI - 2.4.6 current stable (May 18 2026)
- NumPy parallel RNG docs - SeedSequence.spawn for reproducible chunked execution
- uv projects guide - uv run, lockfile, pyproject
- numba PyPI / releases - 0.65.x py3.12-3.14 + numpy 2.4 compat (Apr 2026)

### Secondary (MEDIUM confidence)
- cs.money IEM Cologne 2026 Stage 1 Pick'Em guide - 2/6/2 ballot, >=5 coin threshold confirmed for Cologne 2026
- OddsPapi esports API guide + 2026 pricing - free tier ~250 req/month, CS2 Major coverage 10-14 books per fixture
- Polymarket Gamma API docs - public no-auth read-only confirmed
- Kalshi Quick Start: Market Data + CS2 events - public market data no-auth, live CS2 markets KXCS2GAME series confirmed
- HLTV: Buchholz seeding in PGL Major Swiss stages - confirms Difficulty Score = opponent strength, high vs low fold, seed tiebreak
- HLTV: Valve's Swiss System under the microscope - pairing controversies, group-by-record from R3
- Strafe IEM Cologne Major 2026 Stage 1 guide - advance = finish 3-1/3-2

### Tertiary (LOW confidence - community sources, corroborated by above)
- Steam Community: exact-record scoring discussion - corroborated by multiple pick'em guides
- HTTPX vs Requests 2026 - httpx as modern default

---

*Research completed: 2026-05-28*
*Ready for roadmap: yes*
