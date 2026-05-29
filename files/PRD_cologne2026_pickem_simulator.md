# PRD — Cologne 2026 Swiss Monte Carlo & Pick'Em Optimizer

**Status:** draft v0.3 · **Owner:** Zach · **Last updated:** 2026-05-28
**Codename:** `swiss-mc` (working)
**v0.3 changes:** interface resolved → interactive webapp (Streamlit primary; static HTML option for a probs-only v0); §7 + §11 updated. See companion `HANDOFF_claude_code.md` for the build brief.
**v0.2 changes:** win-prob source resolved → multi-provider market-odds ensemble over APIs (no computer use); F1 rewritten; ensemble/liquidity/ToS risks added.

---

## 0. TL;DR / build verdict

Build it, scoped tight. Win probabilities come from a **multi-provider market-odds ensemble pulled over APIs** (resolved, §5 F1): a sharp anchor (Pinnacle via OddsPapi) blended with prediction-market prices (Polymarket, Kalshi), de-vigged and liquidity-weighted, back-solved into per-team ratings so the Monte Carlo can price unplayed branches. With these inputs the tool produces the exact quantities Pick'Em scores on — P(3-0), P(advance), P(0-3) per team — which cannot be computed by hand because of Swiss branching + Buchholz reseeding. With guessed inputs it launders priors into false precision; skip it.

**No computer use / scraping.** Every source is reachable through a clean API; browser automation is slower, fragile, and ToS-risky, and adds nothing here (see §5 F1 decision note).

**Highest-value capability:** conditional re-simulation — lock each real result as it happens, re-run the MC over remaining games, and watch your live picks' P(advance) update. Hand math breaks down here by Round 3.

**Stop points are built into the milestones** so you can bail cheaply after v0 (~1–2 hrs) if it doesn't feel worth it.

---

## 1. Problem

Stage 1 Pick'Em requires 10 calls (2× 3-0, 6× advance, 2× 0-3) and you need ≥5 right to upgrade the coin. The hard part is not picking the obvious favorites; it's:
- Quantifying P(exactly 3-0) and P(exactly 0-3), which depend on full Swiss paths, not raw team strength.
- Choosing the **marginal** slots (2nd 3-0, 6th advance, 2nd 0-3) where edges are thin.
- Knowing the real probability the whole ballot clears ≥5/10 (i.e., your true coin odds).
- Updating all of the above after Rounds 1–4 actually resolve.

Source-of-truth format facts the engine must honor:
- 16 teams, first to 3 wins advances / 3 losses eliminated; advancement & elimination matches are Bo3, all others Bo1. (Wikipedia: IEM Cologne Major 2026; ESL/Insider-Gaming format pages.)
- R1 pairing: seed #N vs #(N+8) by pre-event VRS. (steamcommunity Major guide; HLTV opening-matchups.)
- Buchholz used from Round 3 onward; Rounds 1–2 use initial seed within record pools; no rematches; non-initial rounds pick the top-most pairing row avoiding a rematch. (Valve `major-supplemental-rulebook.md`; PGL Buchholz announcement.)

Known Stage 1 seeds (from announced R1 matchups; M80=6, NRG=9, Liquid=13 confirmed):
`1 GamerLegion · 2 B8 · 3 HEROIC · 4 BetBoom · 5 BIG · 6 M80 · 7 MIBR · 8 SINNERS · 9 NRG · 10 TYLOO · 11 Sharks · 12 Gaimin Gladiators · 13 Liquid · 14 Lynn Vision · 15 THUNDER dOWNUNDER · 16 FlyQuest` — [INFERRED] seed order from the R1 N-vs-N+8 pairing; verify against the official seed list at lock.

---

## 2. Goal & success criteria

Working backward from the decision the tool must improve:

| # | Success criterion | Measure |
|---|---|---|
| G1 | Output per-team P(3-0), P(advance), P(0-3) for a stage | Probabilities sum-consistent (Σ P(3-0)=2, Σ P(advance)=8, Σ P(0-3)=2) |
| G2 | Recommend the ballot maximizing E[correct] and report P(≥5/10) | Optimizer returns 2/6/2 + both metrics |
| G3 | Re-simulate from any mid-stage state in <2 s | Lock results → updated probs |
| G4 | Be honestly calibrated, not falsely precise | Backtest vs a past Major's actual Swiss (see §9) |

---

## 3. Non-goals (scope guardrails)

- **No map-veto / map-pool modeling** in v0–v1. Match win prob is a single number per matchup. (Add later only if backtest demands it.)
- **No scraping / browser automation, ever.** All odds come from APIs (§5 F1). v0 may paste a single round's probs manually; v1 adds the live API ensemble.
- **No account / auth / multi-user.** Single local user.
- **No playoff bracket** until Stages 1–2 work (playoffs are trivial single-elim by comparison).
- **No prediction of the eventual champion** (the Diamond-coin endgame); out of scope for a Pick'Em-EV tool.

---

## 4. Users & usage

Single user (you). Two modes:
1. **Pre-stage:** load 16 teams + win-prob source → run MC → read optimizer ballot.
2. **In-stage:** after each round, lock actual results → re-run → re-check live picks.

---

## 5. Functional requirements

### F1 — Win probabilities: multi-provider market-odds ensemble (the tool's value rides on this)

**Design:** an ensemble ("mixture of experts") of market sources, de-vigged, pooled, then back-solved into per-team ratings so the MC can price *any* matchup.

**F1a — Providers (each behind one adapter interface):**

| Provider | Access | Type | Role | Notes |
|---|---|---|---|---|
| Pinnacle (via **OddsPapi**) | REST API, free tier | Fixed-odds, sharp | **Anchor** | One OddsPapi call also returns Thunderpick, GG.BET, Betway; ~10–14 books per major CS2 fixture |
| Polymarket | Public API | Prediction market | Divergence signal | Price ≈ probability; minimal vig |
| Kalshi | Official API, public market data | Prediction market (US, CFTC) | Optional 3rd expert | Has CS2 + IEM Cologne markets; thin volume on niche games |

Honest minimal set: **Pinnacle anchor + Polymarket.** That captures ~90% of the value [INFERRED]; Kalshi/Thunderpick are nice-to-have, not load-bearing. Adapter pattern lets you add them later.

**F1b — Per-source normalization (vig handling differs by type):**
- Fixed-odds (Pinnacle, Thunderpick, GG.BET): de-vig two-way → `p_a = (1/o_a)/(1/o_a + 1/o_b)`.
- Prediction markets (Polymarket, Kalshi): price is already ~probability; adjust only for spread/fees; downweight thin markets.

**F1c — Pooling:** combine sources via a **liquidity- and sharpness-weighted log-opinion pool**. Pinnacle and high-volume markets get more weight; thin markets less. Output a blended `p` **and** the cross-source variance.

**F1d — Variance → MC:** feed cross-source disagreement into the sim as an uncertainty band (sample `p` from a Beta centered on the blend, widened by variance) rather than trusting the point estimate. Disagreement is signal, not noise to average away.

**F1e — Ratings back-solve (required; odds alone are insufficient):** books only price *known/next-round* matchups. Round 2+ pairings don't exist until prior rounds resolve, so no book prices the hypothetical "GamerLegion at 2-0 vs ???" branches the MC must traverse. Therefore: back-solve a **per-team rating** from each round's blended match probs (logistic: `p = 1/(1 + 10^(-(R_a − R_b)/s))`); ratings drive unplayed branches; live blended odds **override** the imminent round's known matchups.

**F1f — Fetch cadence (not "live"):** the Pick'Em locks once per stage, so streaming buys nothing. Fetch on two triggers only: (a) minutes before stage lock, (b) once per round after the next round's pairings post. ~5 polls × 8 matches over 4 days — well inside a free tier. Manual single-round paste remains the v0 fallback.

> **Decision note — computer use rejected.** Considered scraping Kalshi/Thunderpick via a browser agent. Rejected: Kalshi has an official API + public data (scraping strictly dominated); Thunderpick is geo-restricted and ToS-hostile to scraping, and its lines arrive through OddsPapi anyway. Browser automation is fragile (DOM breakage), slow (seconds vs ms), and ToS-risky. Reserve only for a future source with no API *and* permissive ToS *and* unique signal — none currently qualify.

### F2 — Match model
- `simulate_match(team_a, team_b, bo) -> winner`: Bernoulli for Bo1; best-of-3 as 3 correlated/independent Bernoullis (v1: independent maps using same p; v2: optional map-level).
- Flag whether a given pairing is a decider (3rd win or 3rd loss) → Bo3, else Bo1.

### F3 — Swiss engine (the core; must mirror Valve rulebook)
- R1: seed N vs N+8.
- Rounds 2+: group by W-L record; seed within group by Buchholz (sum of opponents' wins) from R3, by initial seed in R2; tiebreak initial seed.
- Pairing within group: replicate the rulebook's "top-most row that avoids a rematch" table. **Pull the exact table from Valve's `major-supplemental-rulebook.md` during build — do not approximate.**
- Hard constraint: no rematches.
- Terminate teams at 3W (advance) or 3L (eliminated); record final record (3-0 / 3-1 / 3-2 / 2-3 / 1-3 / 0-3).

### F4 — Monte Carlo runner
- Run N stage simulations (default 100k). Tally per team: count of 3-0, advance (any 3-W), 0-3.
- Return probabilities + Wilson/CI bands so precision is visible.

### F5 — Pick'Em optimizer
- Given per-team probs, search all valid 2/6/2 ballots (or greedy + local swap; full search is small enough at 16 teams) to maximize **E[correct]**.
- Also compute **P(≥5 correct)** for the chosen ballot via the same MC (score each sim against the ballot).
- Surface the two strategic constraints as hard filters: (a) don't pick two 0-3 teams that meet in R1; (b) warn on correlated advance pairs that meet early.

### F6 — Conditional re-sim (killer feature)
- Lock actual results for completed rounds; MC samples only remaining games conditioned on current standings/Buchholz/rematch history.
- Re-output updated probs + whether each of your locked picks is still live / dead / secured.

### F7 — Game-by-game interactive bracket
- Step the bracket forward; at each undetermined match either (a) force a winner, or (b) sample. Visualize the bracket state. (This is the "build it game by game" ask, implemented as F6's UI.)

---

## 6. Data model (sketch)

```python
Team     = {id, name, seed, rating, alive, wins, losses, opp_history[]}
Match    = {round, team_a, team_b, bo, winner|None, locked: bool}
Stage    = {teams[16], rounds[], advance_at=3, eliminate_at=3}
Result   = {team_id, final_record, advanced: bool}
Ballot   = {three_oh:[2], advance:[6], oh_three:[2]}
OddsQuote = {provider, match, p_raw, vig_type, liquidity, ts}   # one expert's read
BlendedP  = {match, p, variance, n_sources}                     # pooled output (F1c/d)
```

---

## 7. Architecture / stack

- **Core:** Python, pure stdlib + `numpy` for vectorized MC. ~300–500 LOC.
- **Odds layer:** `OddsProvider` interface — each source implements `get_quotes(matches) -> [OddsQuote]`; a `pool()` function applies F1b–F1d. Providers: `OddsPapiProvider` (Pinnacle anchor), `PolymarketProvider`, `KalshiProvider`. Swappable; no scraping component.
- **Interface (RESOLVED): interactive webapp.**
  - **Streamlit (primary target).** Python backend in the same process as the engine + odds layer, so it's the only option that can run the F1 live-odds ensemble (holds API keys, makes server-side calls, runs the per-round cron fetch). Near-zero UI code: rating table (`st.data_editor`), `S` slider, sim-count input, results tables/bar charts, round-by-round result locking via widgets. Host local, on your Ubuntu agent host, or Streamlit Community Cloud.
  - **Static HTML (alternative for a probs-only v0).** Single self-contained file (vanilla JS), engine + MC + optimizer + game-by-game bracket, all client-side with a manual/rating probability layer. Zero setup, but **cannot** run the odds ensemble — browser sandboxes block keyed cross-origin odds calls (CORS). Use only if you want a front-end-only artifact before wiring odds.
- **Decision:** build on **Streamlit** so the engine, optimizer, and odds ensemble live in one deployable app. The HTML path stays available as a throwaway v0 if you want something rendering in-chat first.

---

## 8. Milestones (with bail-out points)

| Ver | Scope | Effort [INFERRED] | Bail-out value |
|---|---|---|---|
| **v0** | Stage 1 only · manual/rating probs (single round pasted) · F3 engine · F4 MC · print per-team P(3-0/adv/0-3) | ~1–2 hrs | Already answers "what are my real odds per pick" |
| **v1** | F5 optimizer + P(≥5) · F1 ensemble live (OddsPapi/Pinnacle adapter; Polymarket+Kalshi stubbed) · ratings back-solve · correlated-pick warnings | +~3 hrs | Full Stage-1 decision tool, self-updating |
| **v2** | F6 conditional re-sim · F7 bracket UI · Polymarket/Kalshi adapters live · variance→MC | +~half day | Re-usable across all 3 stages + future Majors |
| **v3** | Stages 2–3, playoffs, map-level Bo3 | +~day | Whole-Major / Diamond-coin planning |

Stop after v0 if the per-team probabilities don't tell you anything the tier list didn't.

---

## 9. Validation (don't trust an uncalibrated sim)

- **Backtest:** load a completed Major Swiss stage (e.g., StarLadder Budapest 2025 or Austin 2025) with pre-stage ratings/odds; confirm simulated advance probabilities roughly match what happened and that the engine reproduces the *actual* pairings round-by-round (deterministic check of F3).
- **Calibrate `s`** in F1b so model win rates match realized rates on historical matchups.
- **Sanity invariants:** Σ P(3-0)=2, Σ P(0-3)=2, Σ P(advance)=8 every run.

---

## 10. Risks & how the tool can mislead

| Risk | Mitigation |
|---|---|
| **GIGO** — bad win probs → confident-looking garbage | Force F1 ensemble or rating; label manual outputs "low confidence"; show CI bands |
| **Ensemble illusion of independence** — soft books copy Pinnacle; arbitrageurs tie Polymarket/Kalshi to it | Weight by originate-vs-copy, not headcount; don't equal-weight |
| **Thin-liquidity noise** — tier-2 / 0-3 candidates get few books + low volume, exactly the picks that matter | Downweight low-liquidity quotes; widen MC variance; flag low-`n_sources` matches |
| **Vig mishandling** — one de-vig formula across fixed-odds + prediction markets is wrong | Per-source normalization (F1b) |
| **Stale / missing future-round prices** | Ratings back-solve (F1e) prices unplayed branches; odds override only known matchups |
| **Bo1 variance** — early rounds near-coinflips; distributions stay wide | Report P(≥5), not a single "optimal" — set expectations |
| **Buchholz small-sample distortion** | Implement exactly per rulebook; don't "improve" it |
| **Map veto unmodeled** — a team's map pool can swing a matchup | Per-matchup odds override (F1a) absorbs much of it |
| **Over-trust / false precision** | Backtest gate (§9); surface CIs everywhere |
| **Pairing-table errors** | Copy Valve's table verbatim from the GitHub rulebook; unit-test against a known past stage |
| **Provider ToS / geo** — Thunderpick geo-restricted; Kalshi US trading waitlisted | Use licensed aggregator (OddsPapi) for book lines; read-only public market data; no scraping |

---

## 11. Open questions

1. ~~Win-prob source~~ **RESOLVED (§5 F1):** market-odds ensemble over APIs (Pinnacle anchor + prediction markets), no computer use.
2. **Provider set for v1** [UNCLEAR] — ship with Pinnacle-only and add Polymarket/Kalshi in v2, or wire all three from the start? (Recommend Pinnacle-only v1; honest minimal set.)
3. ~~Interface~~ **RESOLVED (§7):** interactive webapp on Streamlit (primary); static HTML as a probs-only v0 alternative.
4. **Where it runs** [UNCLEAR] — local for dev; for the per-round auto-fetch, the always-on Ubuntu agent host or Streamlit Community Cloud. (Recommend local dev → Ubuntu host for the live event.)
5. **"Coin points"** [UNCLEAR] — official Valve binary Pick'Em (this PRD's assumption), or a third-party confidence-pool platform? The latter changes F5's objective from E[correct] to expected weighted points.

---

## 12. Sources

- IEM Cologne Major 2026 — Wikipedia; Liquipedia; Esports News UK; Insider Gaming (format, dates, teams).
- R1 matchups & seeds — HLTV "Stage 1 opening matchups"; Dust2.us.
- Swiss/Buchholz mechanics — Valve `counter-strike_rules_and_regs/major-supplemental-rulebook.md`; PGL Buchholz announcement; Steam Community Major guide; HLTV Swiss analysis.
- Current form/ratings — HLTV world ranking (via EGamersWorld, late May 2026).
- Pick'Em rules — CS Money, Strafe, skin.land guides (2/6/2, ≥5/10, 3-0 exact-record scoring, coin tiers).
- Odds APIs — OddsPapi (Pinnacle + Thunderpick + GG.BET + Betway, free REST tier, esports guide); The Odds API (500 free req/mo); PandaScore, OpticOdds, OddsMatrix (aggregators).
- Prediction markets — Kalshi (CS2 + IEM Cologne markets, official API, CFTC); Polymarket (CS2 live markets, public API); gameofskill.gg (Kalshi/Polymarket CS2 overview).
- Thunderpick — thunderpick.io (Curaçao license, geo-restricted, no public odds API).
