# Claude Code Handoff — `swiss-mc`

Build brief for the Cologne 2026 Swiss Monte Carlo + Pick'Em optimizer. Companion to `PRD_cologne2026_pickem_simulator.md` (read it for rationale; this doc is the executable spec). Self-contained — you should not need to re-derive the format.

**Objective:** an interactive **Streamlit** webapp that simulates IEM Cologne Major 2026 **Stage 1** (16-team Swiss), outputs per-team P(3-0)/P(advance)/P(0-3), recommends the optimal 10-pick Pick'Em ballot, reports P(≥5/10), and supports round-by-round result locking with conditional re-simulation.

**Stack:** Python 3.12 · Streamlit · numpy. No other heavy deps. No scraping / browser automation (see Guardrails).

---

## 1. Repo layout

```
swiss-mc/
  app.py                 # Streamlit entry
  engine/
    __init__.py
    teams.py             # fixtures: 16 teams, seeds, R1 table, default ratings
    swiss.py             # pairing + stage simulation (the hard part)
    montecarlo.py        # MC runner -> per-team probs
    optimizer.py         # ballot search, E[correct], P(>=5)
    probs.py             # logistic map prob, Bo3 conversion, de-vig, pooling
  odds/
    base.py              # OddsProvider interface + pool()
    oddspapi.py          # Pinnacle anchor (live)
    polymarket.py        # stub
    kalshi.py            # stub
  tests/
    test_swiss.py        # invariants + no-rematch + backtest
    test_optimizer.py
  data/
    stage1.json          # editable seeds/ratings snapshot
  requirements.txt
  README.md
```

---

## 2. Build order (vertical slices; each must run before the next)

1. **Engine + MC, headless.** `swiss.py` + `montecarlo.py`; a `__main__` smoke test prints per-team probs. **HARD GATE: the round-by-round backtest (§6) must reproduce a real past stage's pairings exactly before any sim output is trusted or the UI is built.** This is the only check that proves the greedy rematch-resolution matches Valve's priority table. Thread a `seed` param through the MC for reproducible runs/backtests.
2. **Streamlit UI.** Rating `st.data_editor`, `S` slider, sim-count input, "Run" button, results table + bar charts. **Wrap the MC in `@st.cache_data` keyed on `(ratings, S, N, locked)`** — Streamlit re-runs the whole script on every widget change, so without caching every slider nudge silently re-launches the full sim. Show a spinner on cache miss (full 100k run is ~10-30s in pure Python; see §7-perf).
3. **Optimizer.** `optimizer.py`; show recommended ballot, E[correct], P(≥5), correlated-pick warnings.
4. **Result locking / conditional re-sim + bracket view.** Lock real winners round by round; re-run conditioned; render the deterministic bracket-so-far.
5. **Odds layer.** `OddsPapiProvider` live (Pinnacle anchor) + `pool()`; Polymarket/Kalshi stubbed. Wire the ratings back-solve (§5).

Stop after slice 1–3 if the probabilities don't beat the hand tier list (PRD bail-out).

---

## 3. Data fixtures (`engine/teams.py`)

16 Stage 1 teams. Seeds **[INFERRED]** from announced R1 pairings (#N vs #N+8); M80=6, NRG=9, Liquid=13 are confirmed. **Verify against the official seed list at lock and overwrite.** Default ratings are **[INFERRED]** starting strengths (HLTV late-May 2026 order) meant to be edited or replaced by the odds back-solve.

| Seed | Team | R1 opp (seed) | Default rating |
|---|---|---|---|
| 1 | GamerLegion | NRG (9) | 92 |
| 2 | B8 | TYLOO (10) | 78 |
| 3 | HEROIC | Sharks (11) | 58 |
| 4 | BetBoom | Gaimin Gladiators (12) | 72 |
| 5 | BIG | Liquid (13) | 55 |
| 6 | M80 | Lynn Vision (14) | 60 |
| 7 | MIBR | THUNDER dOWNUNDER (15) | 68 |
| 8 | SINNERS | FlyQuest (16) | 46 |
| 9 | NRG | GamerLegion (1) | 54 |
| 10 | TYLOO | B8 (2) | 50 |
| 11 | Sharks | HEROIC (3) | 49 |
| 12 | Gaimin Gladiators | BetBoom (4) | 47 |
| 13 | Liquid | BIG (5) | 57 |
| 14 | Lynn Vision | M80 (6) | 52 |
| 15 | THUNDER dOWNUNDER | MIBR (7) | 42 |
| 16 | FlyQuest | SINNERS (8) | 40 |

R1 pairing = `[(i, i + 8) for i in range(1, 9)]` -> `[(1,9),(2,10),...,(8,16)]`.
**Derive it from the seed list; do not hardcode a second copy.** The seed->team map is
the single source of truth. Two hand-maintained copies of the same fact will drift the
moment the official seeds land. (DRY.)
Stage config: 16 teams, advance at 3 wins, eliminate at 3 losses.

---

## 4. Swiss engine (`engine/swiss.py`) — implement exactly

This is the part that must be correct. Faithful to the Valve Major Swiss + Buchholz system.

**Per-team state:** `{id, name, seed, rating, wins, losses, opps:set[id]}`.

**Round pairing:**
- **Round 1:** use the fixed `(seed, seed+8)` table. Not fold.
- **Rounds 2+:** group active teams (`wins<3 and losses<3`) by record `(wins, losses)`. Seed within each group:
  - **All rounds (single code path):** sort by **Difficulty Score descending**, then initial seed ascending.

    ```python
    # Valve "Difficulty Score" (Buchholz). VERIFIED against the rulebook's worked
    # example: opponents 2-0 and 1-1 -> score 2  ==  (2+1) - (0+1).
    def difficulty(t):
        return sum(o.wins - o.losses for o in t.opps)   # NOT sum(o.wins)
    ```

    Do **not** special-case R2: in R2 every team's lone opponent is at the mirror
    record, so difficulty is uniform within a group and the sort falls through to
    seed automatically. One path, no `if round == 2`.
  - Rulebook tiebreak chain is difficulty, then initial seed (no head-to-head in the
    supplemental rulebook). If a backtest pairing diverges, reconcile against the
    rulebook before trusting outputs.
- **Pairing within a group:** high-vs-low **fold**, rematch-avoiding. VERIFIED against
the rulebook: within a record group the highest seed faces the lowest available
non-rematch seed (`1v6, 2v5, 3v4`). (R1's `N vs N+8` split is a special first-round
seeding, *not* this rule.) Valve resolves rematches via a 15-row **priority table**
that keeps the top-seed pairings stable and permutes the **lowest** pairs first
(`1v6,2v5,3v4` -> `1v6,2v4,3v5` -> ...). The greedy backtracking below approximates
that table and matches it in the common cases — **the round-by-round backtest (§6) is
the gate that proves it.** If a pairing diverges from a real past stage, replace the
greedy version with the literal priority-table lookup.

```python
def fold_match(ranked):           # ranked[0] = best seed in group (difficulty, then seed)
    if not ranked: return []
    first, rest = ranked[0], ranked[1:]
    for j in range(len(rest) - 1, -1, -1):     # try worst-ranked first (fold)
        cand = rest[j]
        if cand.id in first.opps:               # no rematch
            continue
        sub = fold_match(rest[:j] + rest[j+1:])
        if sub is not None:
            return [(first, cand), *sub]
    return None                                 # see fallback below
```

**`None` fallback (the rulebook is silent here, so the code must be total):** if no
rematch-free perfect matching exists, do NOT crash — pair the least-disruptive rematch
(highest seed vs lowest available, allowing the rematch) and `log.warning(...)`. In a
16-team Swiss this effectively never fires, but an unhandled `None` is a hard crash on
an unbounded input. Unit-test this path (§6).

**Best-of:** a match is **Bo3 iff** either team has `wins == 2` (advancement match) **or** `losses == 2` (elimination match); else **Bo1**. In record-grouped pairing both teams share a record, so test the group's `(w, l)`.

**Play a match:** see §5 for win prob. Sample winner, increment wins/losses, add each other to `opps`.

**Terminate:** loop rounds until every team has 3 wins or 3 losses. Return each team's final `(wins, losses)`.

**Locked results (for conditional re-sim):** the simulator accepts `locked: dict[frozenset({id,id}) -> winner_id]`. When a generated matchup is in `locked`, use the locked winner deterministically (no sampling). Keys are unordered pairs (safe: no rematches).

---

## 5. Math (`engine/probs.py`)

- **Per-map win prob:** `p_map(a,b) = 1 / (1 + 10 ** (-(a.rating - b.rating) / S))`, default `S = 40` (exposed as a slider; lower S = bigger favorites/blowouts, higher = more coinflips).
- **Series win prob:** `Bo1 = p_map`; `Bo3 = p_map**2 * (3 - 2*p_map)`. Use this
  **closed form as a single Bernoulli draw** in the MC — do NOT sample 3 separate map
  Bernoullis. For iid maps the closed form is exact, so sampling maps only adds cost
  and noise. (Supersedes F2's "3 Bernoullis" wording.)
- **Odds override:** if an odds-derived probability exists for *this exact matchup*, use it directly as the series win prob — do **not** re-apply the Bo3 formula (the market already prices the series).
- **De-vig (fixed-odds two-way):** `p_a = (1/o_a) / (1/o_a + 1/o_b)`.
- **Prediction-market price:** treat as ~probability; adjust only for spread/fees; downweight thin markets.
- **Pooling (`pool()`):** liquidity- and sharpness-weighted **log-opinion pool** across providers → blended `p` + cross-source variance.
- **Variance → MC (epistemic, OUTER loop):** source disagreement is *epistemic*
  uncertainty — it does NOT shrink as you add sims. Do **not** bury the Beta draw
  inside the per-match-per-sim sampling; that folds epistemic uncertainty into
  aleatoric coin-flip noise, so the reported Wilson band only reflects MC error and
  looks falsely tight at large N (defeats goal G4). Instead:
  `for draw in epistemic_draws: p_vector ~ Beta(blend, var); run an MC batch`; then
  aggregate per-team probs **across** draws. The reported band = spread across draws
  (epistemic) and is wider than the inner Wilson band (aleatoric). Single source ->
  point estimate, band collapses to Wilson only.
  Clamp `variance < p*(1-p)` before the Beta method-of-moments fit, or Beta params go
  negative and crash on exactly the low-liquidity, high-disagreement matches that
  matter most.
- **Ratings back-solve (slice 5):** market odds are *series* probs for a specific
  format (Bo1 or Bo3). First invert each known-round series prob to an implied
  **per-map** `p` (identity for Bo1; invert `p^2*(3-2p)` for Bo3), then fit per-team
  ratings to the **map-level** probs via logistic least-squares. Fitting directly to
  series probs conflates Bo1 and Bo3 matchups, so one rating can't price both unplayed
  Bo1 and Bo3 branches. Live odds override the imminent round's known matchups.

---

## 6. Acceptance tests (`tests/`) — engine must pass before UI

Per simulated stage (assert over many sims / large N):
- **Exactly 8 advance, 8 eliminated.** Every team ends at 3 wins or 3 losses.
- **Exactly 2 teams finish 3-0 and exactly 2 finish 0-3** every sim.
- **No rematches:** no pair plays twice within a stage.
- **Bo3 only** on matches where a team was at 2 wins or 2 losses.
- **Probability invariants** over a run: `Σ P(3-0) ≈ 2.0`, `Σ P(0-3) ≈ 2.0`, `Σ P(advance) ≈ 8.0` (tol ±0.05 at N≥50k).
- **Determinism check / backtest:** feed a completed past stage's seeds + forced results (StarLadder Budapest 2025 or BLAST Austin 2025 Swiss) and assert the engine reproduces the *actual* round-by-round pairings. If it diverges, the pairing tiebreaks are wrong — reconcile against the Valve rulebook before trusting outputs.
- **Sanity (eyeball):** with default ratings, GamerLegion has the highest P(3-0) and P(advance); THUNDER dOWNUNDER and FlyQuest have the highest P(0-3). Matches analyst consensus.

Critical unit tests (added by eng review — these guard the risk-bearing paths §6's
invariants alone do NOT catch):
- **`test_difficulty_formula` [CRITICAL]:** assert `difficulty()` on Valve's worked
  example (opponents 2-0 and 1-1) == 2. The §4 Buchholz bug (`sum(o.wins)` vs
  `sum(o.wins - o.losses)`) passes every invariant test while corrupting all probs —
  this is the only test that catches it.
- **`test_forced_rematch_pairing`:** construct a group where the ideal fold is a
  rematch; assert the produced pairing matches Valve's priority table.
- **`test_no_valid_matching_fallback`:** force a group with no rematch-free matching;
  assert the fallback pairs without crashing (no unhandled `None`).
- **`test_locked_results_honored` [CRITICAL]:** the entire F6 re-sim feature. Assert a
  locked winner is deterministic across sims, invariants still hold post-lock, and the
  no-rematch rule respects locked history.
- **`test_difficulty_unit` / `test_p_map` / `test_bo3`:** hand-computed points
  (`p=0.6 -> Bo3 0.648`; `p=0.5 -> 0.5`).
- **`test_epistemic_band_wider_than_wilson`:** with disagreeing sources, assert the
  outer-loop epistemic band ⊇ the inner Wilson band.
- **v1+: `test_devig` / `test_pool`** (de-vig `o=1.5/2.5 -> p≈0.625`; agreeing sources
  -> var≈0); **`test_rating_roundtrip`** (fit ratings to known map probs, recover them).

Optimizer:
- Returns valid ballots: exactly 2 / 6 / 2, no team in two buckets (both A and B).
- **`test_greedy_is_e_correct_optimal`:** on a degenerate deterministic sim, assert the
  greedy ballot maximizes E[correct] (no swap improves it).
- **`test_pge5_known_answer` [CRITICAL]:** degenerate sim with a hand-computed P(≥5).
- Flags when the two 0-3 picks meet in Round 1 (caps correct picks at 1; hurts P(≥5)),
  and asserts Ballot B avoids the trap.

---

## 7. Optimizer (`engine/optimizer.py`)

**Two objectives = two ballots. Report BOTH; when they differ, that difference is the
insight.**

- **Ballot A — E[correct]-optimal (greedy, provably optimal, no search):** 3-0 = top 2
  by P(3-0); 0-3 = top 2 by P(0-3); advance = top 6 by P(advance) excluding the four
  already chosen. E[correct] is a linear sum of independent slot-hit probabilities, so
  greedy is not a heuristic here — it is the exact maximizer. No enumeration needed.
- **Ballot B — P(≥5)-optimal (search):** P(≥5) is nonlinear and correlation-sensitive,
  so it needs search. Hill-climb single-team swaps, scoring each candidate by **P(≥5)**
  against the stored sim sample (vectorized: compare each simulated stage's record
  vector to the ballot, count ≥5). Full enumeration is ~10M ballots — do not
  brute-force; greedy seed + local swap converges.
- **Correlated-pick warnings emerge for free in Ballot B:** the "two 0-3 picks that
  meet in R1" trap (one must win, capping you at 1 correct) is automatically avoided by
  a P(≥5) search against the joint sim sample — the sims already encode that they can't
  both go 0-3. Surface it as an explicit warning anyway, because Ballot A (E[correct])
  is correlation-blind and *can* fall into it.

---

## 8. Odds layer (`odds/`) — slice 5

```python
# odds/base.py
@dataclass
class OddsQuote:
    provider: str; match: tuple[str,str]; p_raw: float
    vig_type: str  # "fixed" | "market"
    liquidity: float; ts: float

class OddsProvider(Protocol):
    def get_quotes(self, matches) -> list[OddsQuote]: ...

def pool(quotes: list[OddsQuote]) -> dict:  # -> {match: {"p":..,"variance":..,"n":..}}
    ...
```

- **OddsPapiProvider (live, anchor):** REST, free tier; CS2 `sportId`, filter fixtures by tournament; one call also returns Thunderpick / GG.BET / Betway. Pinnacle is the sharp anchor — weight it highest.
- **PolymarketProvider / KalshiProvider:** stubs returning `[]` for now; Kalshi uses its official API + public market data, Polymarket its public API. Prices are ~probabilities (`vig_type="market"`).
- **Thunderpick:** no direct provider — its lines arrive via OddsPapi. Never scrape it.
- **Keys:** read from env (`ODDSPAPI_KEY`, etc.); never commit. `.env` + `python-dotenv`, `.env` gitignored.
- **Fetch cadence:** not streaming. Two triggers: (a) minutes before stage lock, (b) once per round after next-round pairings post. A manual "fetch now" button is fine for v0.

---

## 9. Guardrails / non-goals

- **No scraping or browser automation.** APIs only. (Kalshi has an API; Thunderpick comes via OddsPapi.)
- **No localStorage/sessionStorage** if you also produce the HTML variant — keep state in memory / Streamlit `session_state`.
- **No map-veto modeling** in v0; single win prob per matchup.
- **Keep confidence intervals visible** everywhere (Wilson bands on probs). The biggest failure mode is false precision — surface uncertainty, don't hide it.
- **Seeds and default ratings are [INFERRED]** — make them editable and reconcile with official sources at lock.

---

## 10. Definition of done

- `streamlit run app.py` launches; edit ratings + `S`, run N sims, see per-team P(3-0)/advance/0-3 with CIs, a recommended ballot with E[correct] + P(≥5), and a lockable round-by-round bracket that re-simulates conditionally.
- All §6 tests pass, including the past-Major backtest.
- README documents the run command, the env vars, and the [INFERRED]-seed caveat.

## 10.5 UI/UX design contract (added by /plan-design-review)

The plan specified widgets, not design. This section is the buildable design spec.
Streamlit constrains styling, so these are layout/IA/state decisions, not pixels.

### Two modes (explicit toggle)
`st.radio`/`st.segmented_control` at the top: **Pre-stage** vs **Live**. Same data,
the main column reorders by what matters in each mode.

```
PRE-STAGE MODE                                    LIVE MODE (priority flips)
+- controls -+ +- MAIN ---------------+           +- controls -+ +- MAIN -----------------+
| ratings    | | (1) RECOMMENDED      |           | round  v   | | (1) YOUR PICKS-STATUS  |
|  (edit)    | |     BALLOT           |           | lock R2:   | |  3-0 GamerLegion o live|
| S  slider  | |   A: Max E[correct]  |           |  GL | NRG  | |  3-0 B8          x dead |
| N  input   | |   B: Max P(>=5)      |           |  ...       | |  ADV HEROIC      / secur|
| [RUN >]    | |   side by side       |           | [RE-SIM >] | |  -> 4 live / 1 dead     |
|            | | (2) PER-TEAM PROBS   |           |            | |  -> P(>=5 here) 58%     |
|            | |     16 rows + CI bars|           |            | |  (2) delta probs       |
|            | | (3) bracket (collapse)|          |            | |  (3) BRACKET           |
+------------+ +----------------------+           +------------+ +------------------------+
```

### Information hierarchy
- **Pre-stage:** ballot (hero) > per-team probs > bracket (collapsed).
- **Live:** locked-pick status + P(>=5)-from-here (hero) > delta probs > bracket.
- The ballot's headline is the **P(>=5) percentage** (big). Show both ballots A and B
  (eng review §7); when they differ, highlight the differing picks.

### Interaction states (build all of these)
```
FEATURE        | LOADING                  | EMPTY (pre-run)       | ERROR                | SUCCESS/PARTIAL
---------------|--------------------------|-----------------------|----------------------|-----------------
Run sim        | progress bar + live      | "Set ratings, hit Run.| bad rating cell ->   | fade in;
 (10-30s)      |  sim count + running     |  ~15s." (never blank) | inline cell error,   | "100k sims, 12.4s"
               |  P(advance) settling     |                       | do not run           |
Per-team probs | skeleton rows            | dashes, NOT "0%"      | -                    | number + CI bar
Ballot panel   | "computing..."           | "Run to see ballot"   | -                    | A vs B (+ diff)
Live status    | re-sim spinner           | "Lock a result to go  | impossible locked    | o live / x dead /
               |                          |  live"                | pair -> reject+reason| / secured + delta
Bracket        | -                        | seeded R1 only        | -                    | locked solid/sim faint
```
The **dead/live/secured** transition is the emotional core of live mode: status glyph
+ text label + the P(>=5) delta arrow (e.g. `71% -> 58%`). The *change* is the point,
show it, don't just swap in a new static number.

### Loading = progress bar + live tally (chosen)
The MC runs in chunks (e.g. 20 x 5k); after each chunk update a progress bar and a
rough running P(advance). **Eng-review cross-impact:** this requires the MC to yield
progress, so structure the runner to accumulate tallies incrementally (it already
stores per-sim records, so emit a partial aggregate every chunk). Final result still
cached via `@st.cache_data`.

### Swiss bracket = record-bucket columns (HLTV/Liquipedia convention)
Columns are W-L records (`0-0 -> 1-0 -> 2-1 -> ... -> 3-0 adv / 0-3 elim`); teams flow
rightward as they win/lose. Locked/real results solid; simulated branches faint. This
is the view every CS viewer already reads. Do NOT draw a bracket *tree* — Swiss teams
reconverge by record, so a tree misrepresents the format.

### Confidence intervals = inline mini-bar (chosen)
Every probability cell renders the number + a thin horizontal CI (Wilson/epistemic)
bar beneath it. Always visible, never hidden behind hover/expand — that is the whole
"don't be falsely precise" goal (G4) made visual.

### Trust badge
Small persistent "engine validated vs Austin 2025 backtest ✓" badge (tied to the
eng-review backtest gate). Does more for trust than any styling when the user is
deciding whether to believe an "82% advance."

### Visual tokens (no DESIGN.md; pin these so it isn't ad-hoc)
- **Monospace for ALL numbers** (probabilities/records align in columns; this is
  legibility, not taste).
- **One accent color** for the primary action / hero numbers.
- **Status palette = colorblind-safe:** advanced = blue, eliminated = amber/orange.
  **Never red/green.** Always pair color with a **text label + glyph** (`o live`,
  `x dead`, `/ secured`) — color alone fails for ~8% of men.
- Body/number contrast >= 4.5:1; CI bars must be visible against the table background.
- **No equal-weight `st.metric` card mosaic.** Ballot is the hero; probs are a dense
  table. Hierarchy over symmetry.

### Out of scope (design)
- Responsive/mobile/tablet: N/A — local single-user desktop tool.
- Theming/light-mode toggle, animations beyond state transitions, branding.

## 10.6 Developer experience / getting-started contract (added by /plan-devex-review)

Persona: you + a few CS friends you hand the repo to (you on Windows, them maybe
Mac/Linux). The DX that matters: **clone → first sim in under 2 minutes, cross-platform,
with zero API key**, and a cold-start that survives event-day time pressure.

### Bootstrap = uv (one command, cross-platform)
Primary path, identical on Windows/Mac/Linux:
```
uv run streamlit run app.py
```
`uv` auto-creates the env and installs from `pyproject.toml` (~45s cold). Provide a
pip fallback line too. Pin the Python version (`>=3.12`) in `pyproject.toml`. Do NOT
write a bash-only `run.sh` — it breaks the Windows author.

### Zero-config first sim (the magical moment)
Ship `data/stage1.json` with the default [INFERRED] ratings so the **first run needs
no API key and no editing**: clone → `uv run streamlit run app.py` → hit Run → watch
100k Swiss tournaments resolve → per-team P(advance) in ~15s. State this explicitly in
the README ("first sim requires no API key").

### Odds layer fails SOFT
Missing `ODDSPAPI_KEY` (or any provider key) → the app runs in **rating-only mode** and
shows a one-line info banner: `live odds off (no ODDSPAPI_KEY) — using manual ratings`.
NEVER crash or hard-block on a missing key. Live odds are an enhancement, not a gate.
Ship a `.env.example` listing the optional keys; `.env` gitignored.

### [INFERRED]-seed = loud in-app banner (correctness-critical)
Persistent dismissable banner until confirmed:
`⚠ Seeds are INFERRED — verify vs the official seed list before trusting outputs.`
A "seeds confirmed" toggle dismisses it. This is not cosmetic: a wrong seed silently
corrupts every probability (ties to the eng-review backtest gate). A README footnote is
not enough — it gets forgotten at exactly the moment it bites (event day).

### README contract (the only docs this needs)
Copy-paste quickstart at the very top, in this order:
1. One-line what-it-is.
2. `uv run streamlit run app.py` (+ pip fallback).
3. "First sim needs no API key" + the ~15s expectation.
4. "What the numbers mean" (2 lines: P(3-0)/advance/0-3, CI bands = honest uncertainty).
5. The [INFERRED]-seed reconcile step (verify at lock).
6. Optional: `.env.example` for live odds (v1+).
Reference docs / architecture prose: not needed for this persona. Skip them.

### Cold-start checklist (event day, clock running)
README ends with a 30-second pre-event drill: `git pull` → confirm official seeds →
flip "seeds confirmed" → run. So future-you isn't debugging a missing dep while the
stage locks.

### Out of scope (DX)
- Community/Discord/issue templates, SDK/multi-language, upgrade/migration/codemods,
  DX telemetry: N/A for a private single-user tool. (Add a LICENSE only if you ever
  publish it publicly.)

## 11. Canonical sources to fetch during build

- Swiss/Buchholz exact pairing + tiebreak chain: `github.com/ValveSoftware/counter-strike_rules_and_regs` → `major-supplemental-rulebook.md`.
- Stage 1 teams/seeds/matchups: HLTV "IEM Cologne Major Stage 1 opening matchups"; Liquipedia event page; Wikipedia "IEM Cologne Major 2026".
- Pick'Em rules (2/6/2, ≥5/10, 3-0 exact-record scoring): CS Money / Strafe / skin.land guides.
- Odds: OddsPapi esports API docs; Polymarket + Kalshi API docs.

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | not run |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | not run |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAN (PATCHED) | 11 issues, 1 P0 (Buchholz) fixed in spec |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | CLEAN | score 3/10 → 9/10, 5 decisions, §10.5 added |
| DX Review | `/plan-devex-review` | Developer experience gaps | 1 | CLEAN | TTHW ~8min → <2min, §10.6 added (uv, fail-soft, seed banner) |

- **UNRESOLVED:** 0 decisions (4 architecture forks + 4 design forks all resolved).
- **ENG — PATCHED INTO THIS DOC (2026-05-28):** Buchholz = `Σ(opp.wins − opp.losses)`
  (§4); fold direction confirmed + priority-table note + `None` fallback (§4); R1
  derived from seeds (§3); single seeding code path (§4); Bo3 closed-form single draw
  (§5); epistemic band via outer loop + Beta clamp (§5); ratings fit at map level (§5);
  dual ballots A/B (§7); Streamlit `@st.cache_data` + RNG seed (§2); backtest = slice-1
  hard gate (§2); 11 critical/unit tests added (§6).
- **DESIGN — ADDED (§10.5):** explicit two-mode IA (pre-stage/live); full interaction
  state table; progress-bar + live-tally loading (MC yields per-chunk — eng cross-impact);
  record-bucket bracket (HLTV convention, not a tree); inline CI mini-bars; colorblind-safe
  blue/amber status + glyph/label; trust badge tied to backtest; monospace numbers token.
- **DX — ADDED (§10.6):** uv one-command bootstrap (cross-platform); zero-config first
  sim via shipped `data/stage1.json` (no API key); odds layer fails soft to rating-only
  + banner; [INFERRED]-seed loud in-app banner until confirmed; README quickstart
  contract; event-day cold-start checklist. TTHW ~8min → <2min target.
- **VERDICT:** ENG + DESIGN + DX all CLEARED to build once the patched spec is accepted.
  Live risks during implementation: the backtest gate (eng), the progress-yielding MC
  the loading UX depends on (design×eng), and the seed-confirmation banner (dx×eng,
  correctness-critical).
