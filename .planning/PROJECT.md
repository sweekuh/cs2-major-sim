# swiss-mc — Cologne 2026 Swiss Monte Carlo & Pick'Em Optimizer

## What This Is

An interactive Streamlit webapp (Python 3.12 · numpy) that simulates the IEM Cologne
Major 2026 Counter-Strike 2 Swiss stages via Monte Carlo, outputs per-team
P(3-0) / P(advance) / P(0-3) with confidence bands, recommends the optimal 2/6/2
Pick'Em ballot, reports the true P(≥5/10) coin odds, and supports round-by-round
result locking with conditional re-simulation. Win probabilities come from a
multi-provider market-odds ensemble pulled over APIs (Pinnacle anchor via OddsPapi,
blended with Polymarket and Kalshi), de-vigged, liquidity-weighted, and back-solved
into per-team ratings so the simulation can price unplayed Swiss branches. Single
local user (Zach) plus a few CS friends who clone the repo.

## Core Value

Honestly-calibrated probabilities for the exact quantities Pick'Em scores on —
P(3-0), P(advance), P(0-3) per team, plus P(≥5/10) for a ballot — including
conditional re-simulation that hand math cannot do past Round 3, without laundering
guessed inputs into false precision.

## Requirements

### Validated

- ✓ Headless Valve Stage-1 Swiss engine + Monte Carlo correctness core — Phase 1. Buchholz `Σ(w−l)`, difficulty-rank fold, verbatim 15-row priority table, `locked` support, generator-first MC with `SeedSequence.spawn` reproducibility, full per-sim sample, closed-form Bo3, Wilson bands, invariants Σ=2/8/2. Validated by Valve-rulebook unit tests (21 passed / 1 skipped).
- ✓ Two-mode Streamlit UI shell — Phase 2. Pre-stage/Live toggle, editable ratings + S/N controls, validated Run, generator-driven progress, per-team probs with always-visible inline CI bars (48 verified live), colorblind-safe blue/amber status, caveated trust badge (`BACKTEST_PASSED=False`), [INFERRED]-seed banner + confirm toggle, fail-soft odds banner, zero-config first run (no API key), `uv` bootstrap + README. Verified live via /browse (ΣP(advance)≈8.0 in-UI); 51 tests green. Outstanding: cross-OS (Mac/Linux) launch confirm.
- ✓ **Backtest gate GREEN (GATE-01/04/05) — 2026-05-29.** The engine reproduces StarLadder Budapest 2025 Stage 1's actual round-by-round pairings EXACTLY (R1-R5, including the 6-team priority-table rounds), validating the Buchholz ranking + high-low fold + verbatim priority table against real data. Seeds sourced from the authoritative Valve seeding VRS snapshot (`counter-strike_regional_standings` 2025_11_03, the "snapshot rule" — not live HLTV/VRS). `BACKTEST_PASSED=True`; trust badge can read "validated" once the user confirms the [INFERRED] Cologne seeds.

### Active

<!-- All hypotheses until shipped and validated. Detailed REQ-IDs live in REQUIREMENTS.md. -->

**Swiss engine & simulation (correctness core)**
- [ ] Faithful Valve Major Swiss engine: R1 seed N vs N+8; Rounds 2+ record-grouped, seeded by Difficulty Score (`Σ opp.wins − opp.losses`) then initial seed; fold pairing with rematch avoidance + priority-table fallback; Bo3 on advancement/elimination matches, Bo1 otherwise; no rematches; terminate at 3W/3L
- [ ] Round-by-round backtest against a completed past Major stage (Budapest 2025 / Austin 2025) reproduces actual pairings exactly — **hard gate before any sim output is trusted or UI is built**
- [ ] Monte Carlo runner (default 100k sims, reproducible via threaded seed) tallying per-team P(3-0)/P(advance)/P(0-3) with Wilson CI bands; emits incremental progress per chunk
- [ ] Probability invariants hold every run: Σ P(3-0)=2, Σ P(0-3)=2, Σ P(advance)=8

**Pick'Em optimizer (Valve binary scoring)**
- [ ] Ballot A: E[correct]-optimal via greedy (provably optimal — linear sum of independent slot probabilities)
- [ ] Ballot B: P(≥5)-optimal via hill-climb swap search against the stored sim sample
- [ ] Report both ballots and highlight differing picks; surface correlated-pick warnings (two 0-3 picks meeting in R1)

**Conditional re-simulation (killer feature)**
- [ ] Lock real results round by round; MC re-runs conditioned on standings/Buchholz/rematch history; locked winners are deterministic
- [ ] Live mode shows each locked pick as live / dead / secured with P(≥5)-from-here delta
- [ ] Record-bucket bracket view (HLTV/Liquipedia convention, not a tree); locked results solid, simulated branches faint

**Odds ensemble (all three providers live)**
- [ ] `OddsProvider` adapter interface + `pool()`; providers: OddsPapi (Pinnacle anchor), Polymarket, Kalshi — all live in v1
- [ ] Per-source normalization: de-vig fixed-odds two-way; treat prediction-market price as ~probability with thin-market downweighting
- [ ] Liquidity- and sharpness-weighted log-opinion pool → blended p + cross-source variance
- [ ] Epistemic variance fed to MC via outer-loop Beta draws (not inner per-sim), with `variance < p(1-p)` clamp; reported band ⊇ inner Wilson band
- [ ] Ratings back-solve: invert series probs to per-map p, fit per-team ratings via logistic least-squares; live odds override known imminent-round matchups
- [ ] Fetch cadence: manual "fetch now" + per-round triggers (not streaming); keys from env, never committed; missing key → rating-only mode with banner (fail soft)

**Full-Major scope (v3)**
- [ ] Stage 2 and Stage 3 Swiss
- [ ] Playoff single-elimination bracket
- [ ] Optional map-level Bo3 modeling (only if backtest demands it)

**Interface & DX**
- [ ] Streamlit two-mode UI (Pre-stage / Live) with `@st.cache_data`-keyed MC; rating `st.data_editor`, S slider, sim-count input
- [ ] Visible CI mini-bars on every probability; monospace numbers; colorblind-safe blue/amber status with glyph+label (never red/green)
- [ ] [INFERRED]-seed loud in-app banner until "seeds confirmed" toggle
- [ ] `uv run streamlit run app.py` one-command cross-platform bootstrap; zero-config first sim (no API key); README quickstart + event-day cold-start checklist; trust badge tied to backtest

### Out of Scope

- Account / auth / multi-user — single local user; adds nothing for the use case
- Map-veto / map-pool modeling — single win prob per matchup (map-level Bo3 only as v3 stretch if backtest demands)
- Scraping / browser automation — every source has a clean API; scraping is fragile, slow, ToS-risky, adds no signal
- Champion / Diamond-coin endgame prediction — out of scope for a Pick'Em-EV tool
- localStorage/sessionStorage (if an HTML variant is ever made) — keep state in Streamlit `session_state`
- Responsive / mobile / tablet, theming, branding — local single-user desktop tool
- Community/Discord/issue templates, SDK, telemetry — private tool

## Context

- **Event:** IEM Cologne Major 2026. Stage 1 = 16 teams, first to 3 wins advances /
  3 losses eliminated; advancement & elimination matches Bo3, all others Bo1.
- **Format mechanics are nailed down** in the PRD/handoff (R1 N-vs-N+8 pairing,
  Buchholz from R3, no rematches, top-most non-rematch pairing row). Pull the exact
  pairing/tiebreak table from Valve's `major-supplemental-rulebook.md` during build —
  do not approximate.
- **Seeds and default ratings are [INFERRED]** from announced R1 matchups (M80=6,
  NRG=9, Liquid=13 confirmed) and HLTV late-May 2026 order. Must be editable and
  reconciled against the official seed list at lock — a wrong seed silently corrupts
  every probability.
- **Prior planning:** the companion `files/HANDOFF_claude_code.md` is the executable
  spec (repo layout, build order, exact engine pseudocode, acceptance tests). It has
  already passed `/plan-eng-review` (11 issues, 1 P0 Buchholz fix), `/plan-design-review`
  (3/10 → 9/10, §10.5 UI contract), and `/plan-devex-review` (TTHW 8min → <2min, §10.6).
  `files/PRD_cologne2026_pickem_simulator.md` holds the rationale. `TODOS.md` captures
  deferred work (cron-fed odds cache, Numba acceleration, backtest-as-gate).
- **Why now:** Stage 1 Pick'Em locks once per stage; the tool must be ready and
  calibrated before lock, with conditional re-sim usable live during the event.

## Constraints

- **Tech stack**: Python 3.12, Streamlit, numpy, pure stdlib elsewhere — no other heavy deps. Engine ~300–500 LOC.
- **Bootstrap**: `uv` one command, cross-platform (author on Windows, friends on Mac/Linux); pip fallback. No bash-only `run.sh`.
- **Data sourcing**: APIs only, no scraping/browser automation. API keys from env (`.env` gitignored, `.env.example` shipped).
- **Correctness gate**: round-by-round backtest must pass before sim output is trusted or UI is built (slice-1 hard gate).
- **Honesty**: CI bands visible everywhere; epistemic vs aleatoric uncertainty kept distinct; manual-input outputs labeled low confidence.
- **Performance**: pure-Python 100k run ~10–30s with spinner is acceptable for v0–v2; Numba acceleration deferred (TODOS #2) unless live-event latency annoys.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Win-prob source = multi-provider market-odds ensemble over APIs | Markets price the exact series; guessed inputs launder priors into false precision | — Pending |
| Interface = Streamlit (not static HTML) | Same process as engine + odds layer; only option that can run keyed server-side odds calls (HTML blocked by CORS) | — Pending |
| Scope this cycle = full v3 (Stages 1–3 + playoffs + map-level) | User wants the whole-Major / Diamond-coin planning tool, not just Stage 1 | — Pending |
| Pick'Em scoring = official Valve binary (2/6/2, ≥5/10, exact-record 3-0/0-3) | Confirmed format; optimizer maximizes E[correct] and reports P(≥5) | — Pending |
| Odds v1 = all three providers live (Pinnacle + Polymarket + Kalshi) | User wants divergence signal up front, not Pinnacle-only minimal set | — Pending |
| Buchholz = `Σ(opp.wins − opp.losses)`, single seeding code path | Verified against rulebook worked example; `sum(o.wins)` passes invariants but corrupts all probs (eng-review P0) | ✓ Good |
| Bo3 = closed form `p²(3−2p)` as a single Bernoulli draw | Exact for iid maps; sampling 3 maps only adds cost + noise (eng review, supersedes F2) | ✓ Good |
| Epistemic variance via outer-loop Beta draws, not inner per-sim | Keeps source disagreement out of aleatoric MC noise so Wilson band isn't falsely tight at large N (G4) | ✓ Good |
| Backtest is a slice-1 hard gate, not post-hoc validation | Only check that proves greedy rematch resolution matches Valve's priority table | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-29 after Phase 2 (Streamlit UI shell) — engine + UI shell shipped; on branch phase-2-ui*
