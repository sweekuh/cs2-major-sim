# Feature Research

**Domain:** CS2 Major Swiss-stage Monte Carlo simulator + Pick'Em-EV optimizer (Streamlit/Python)
**Researched:** 2026-05-28
**Confidence:** HIGH (domain facts verified against Valve's official supplemental rulebook + multiple 2026 IEM Cologne guides)

---

## Domain Fact Verification (the rules that drive the feature set)

These are the load-bearing facts. Every probability the tool emits is meaningless if any of these is wrong, so they were verified against authoritative sources before categorizing features.

| Fact | PRD claim | Verified? | Source / confidence |
|------|-----------|-----------|---------------------|
| **Stage 1 ballot = 2× (3-0), 6× advance, 2× (0-3)** | Yes | ✅ CONFIRMED for IEM Cologne 2026 | cs.money, BLAST.tv pick'em hub, skin.club — HIGH |
| **Need ≥5 of 10 correct to upgrade coin** (Bronze→Silver→Gold→Diamond) | Yes | ✅ CONFIRMED, 2026 | cs.money ("make 10 predictions and get at least 5 correct") — HIGH |
| **3-0 and 0-3 scored on EXACT final record** | Yes | ✅ CONFIRMED — a 3-0 pick that finishes 3-1 scores **zero**; advancing is not enough | Steam Community CS2 discussion + multiple guides — HIGH |
| **Advance pick scored on reaching 3 wins (3-0/3-1/3-2)** | Yes | ✅ CONFIRMED — "finish 3-1 or 3-2" counts as advance | Strafe, cs.money — HIGH |
| **16 teams, first to 3 wins advances / 3 losses out (8 advance, 8 out)** | Yes | ✅ CONFIRMED | Valve supplemental rulebook, ESL — HIGH |
| **Bo3 on advancement (2-x) AND elimination (x-2) AND decider (2-2) matches; Bo1 otherwise** | Yes | ✅ CONFIRMED verbatim: "All elimination and advancement matches are to be best of three. All other matches are best of one." | Valve supplemental rulebook — HIGH |
| **R1 pairing: seed #N vs #N+8** | Yes | ✅ CONFIRMED | Valve rulebook, HLTV opening matchups — HIGH |
| **Buchholz / "Difficulty Score" = Σ(opp.wins − opp.losses)** | Yes (eng-review P0) | ✅ CONFIRMED verbatim: "sum of current wins minus the sum of current losses for every opponent." Worked example: opponents 2-0 and 1-1 → (2+1)−(0+1) = 2 | Valve supplemental rulebook — HIGH. **`sum(o.wins)` is wrong.** |
| **Tiebreak chain: W-L record → Difficulty Score → initial seed** | PRD says "difficulty, then seed" | ✅ CONFIRMED, with nuance | Valve rulebook lists **record first**, then difficulty, then seed. Within a record group record is constant so it collapses to PRD's chain — but the engine must group by record *before* sorting by difficulty. Spec already does this. — HIGH |
| **No rematches within a stage; pick top-most non-rematch row from a 15-row priority table** | Yes | ✅ CONFIRMED. Highest seed faces lowest available non-rematch seed; permute lowest pairs first | Valve rulebook — HIGH |
| **Buchholz applies from Round 3** (R1–2 use seed within pools) | Yes | ⚠️ PARTIAL — rulebook says difficulty applies "after initial matches" as the tiebreaker whenever records tie. In R2 every team's lone opponent sits at the mirror record so difficulty is uniform and the sort falls through to seed automatically (single code path, no `if round==2` — matches spec). Functionally identical to "Buchholz from R3." — HIGH |

**Net:** the PRD/HANDOFF format model is correct on every load-bearing point. The one item to watch is that the rulebook's literal tiebreak chain puts **record before difficulty** — the engine's record-grouping satisfies this, so no change needed, but document it so a future reader doesn't "fix" it.

---

## Feature Landscape

### Table Stakes (Users Expect These)

A CS2 Pick'Em/Swiss tool that lacks these does not clear the bar set by free public tools (HLTV's Swiss probability tables, BLAST.tv's pick'em tracker, community spreadsheets).

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Faithful Valve Swiss engine** (N vs N+8, record-grouped Buchholz seeding, fold pairing, no rematches, Bo3 deciders, 3W/3L terminate) | This is the *definition* of the event. Any pairing error silently corrupts every downstream number. HLTV/Liquipedia readers will instantly spot a wrong matchup. | HIGH | PRD F3. The hard part. Greedy rematch resolution must match Valve's 15-row priority table — the **backtest is the gate** that proves it. Maps to PROJECT.md correctness core. |
| **Per-team P(3-0) / P(advance) / P(0-3)** via Monte Carlo | These are *exactly the three quantities Pick'Em scores on*. The whole tool exists to produce them; hand math can't past R3 (Buchholz reseeding + branching). | MEDIUM | PRD F4/G1. 100k default sims. Invariants Σ(3-0)=2, Σ(0-3)=2, Σ(adv)=8 must hold every run. |
| **Editable team ratings + seeds** | Seeds/ratings are `[INFERRED]` until lock; a wrong seed corrupts everything. Users must be able to reconcile against the official list. | LOW | `st.data_editor` + `data/stage1.json`. Zero-config first run ships with defaults. |
| **`S` (spread) parameter** | Converts rating gaps → win probs; users need to tune favorite/coinflip aggressiveness and calibrate against history. | LOW | Logistic `p = 1/(1+10^(-(Ra−Rb)/S))`, default 40, exposed as slider. |
| **Pick'Em ballot recommendation (2/6/2)** | The headline ask. A pick'em tool that doesn't *recommend a ballot* is just a probability table. | MEDIUM | PRD F5. E[correct]-optimal greedy is provably optimal (linear independent slots) — no search needed for the baseline. |
| **Exact-record-aware 3-0 / 0-3 scoring** | A 3-0 pick scores **zero** if the team finishes 3-1. A tool that scores "advance" credit for a 3-0 slot gives wrong EV. This is the most common amateur mistake. | LOW | Score against the simulated *final record vector*, not a boolean "advanced." Already implicit in tallying P(exactly 3-0). |
| **Visible confidence/CI bands on every probability** | Core Value is "honestly calibrated, not falsely precise." Inputs are guessed; hiding uncertainty would be the product's central lie. | MEDIUM | Wilson bands (aleatoric). Inline mini-bars per §10.5. This is table stakes *for this tool's stated value*, even though most competitors omit it. |
| **One-command, cross-platform run + zero-config first sim** | The user is on Windows handing the repo to Mac/Linux friends; a broken bootstrap kills adoption before any feature lands. | LOW | `uv run streamlit run app.py`; ships defaults so first sim needs no API key. §10.6. |
| **Record-bucket bracket view** (HLTV/Liquipedia column convention, not a tree) | This is the only Swiss visualization CS viewers can read. A bracket *tree* misrepresents the format (teams reconverge by record). | MEDIUM | §10.5. Locked results solid, simulated branches faint. |

### Differentiators (Competitive Advantage)

Where this tool beats HLTV tables, BLAST.tv's tracker, and community spreadsheets. These align directly with PROJECT.md's Core Value.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Conditional re-simulation (result locking)** | THE killer feature. Lock real results round-by-round; MC re-runs conditioned on standings/Buchholz/rematch history. Hand math and static tables break down by R3 — nobody else updates *your specific ballot's* live odds mid-event. | HIGH | PRD F6. Depends on engine result-locking (`locked: dict[frozenset→winner]`, deterministic). `test_locked_results_honored` is CRITICAL. |
| **True P(≥5/10) for the ballot ("real coin odds")** | Users want to know "will my coin actually upgrade?" — a single nonlinear, correlation-sensitive number that *cannot* be read off per-team probs. No public tool reports it. | MEDIUM | PRD F5/G2. Score each stored sim's record vector against the ballot, count ≥5. Requires storing the sim sample, not just marginals. |
| **Dual ballots A (max E[correct]) + B (max P(≥5)) with diff highlight** | The *difference* between the two objectives is the insight: a safe-EV ballot vs a coin-clearing ballot diverge exactly on the marginal slots where money is made. | MEDIUM | HANDOFF §7. Ballot A = greedy (free). Ballot B = hill-climb swap search vs sim sample. Reporting both is cheap once both metrics exist. |
| **Live pick status: live / dead / secured + P(≥5)-from-here delta** | The emotional core of live mode. Shows *the change* (`71% → 58%`) as results land, not just a new static number. | MEDIUM | §10.5. Depends on conditional re-sim. Colorblind-safe blue/amber + glyph + label (never red/green). |
| **Epistemic CI bands (outer-loop Beta draws) ⊇ aleatoric Wilson band** | Honest two-layer uncertainty: source disagreement (epistemic, doesn't shrink with N) kept distinct from MC sampling noise (aleatoric). Prevents the falsely-tight band at large N that would defeat the whole calibration goal. | HIGH | HANDOFF §5, decision G4. Beta draws on the *outer* loop; clamp `var < p(1−p)`. This is the most sophisticated honesty feature and the hardest to get right. |
| **Multi-provider market-odds ensemble** (Pinnacle anchor via OddsPapi + Polymarket + Kalshi), de-vigged, log-opinion pooled | Markets price the exact series; this avoids "laundering guessed priors into false precision." Cross-source *divergence* is itself signal (thin tier-2 markets flagged). | HIGH | PRD F1. Adapter pattern. **Honest minimal set = Pinnacle + Polymarket (~90% of value); Kalshi/Thunderpick nice-to-have.** Fails soft to rating-only mode if no key. |
| **Ratings back-solve from odds** | Books only price the *next* round; R2+ branches don't exist yet. Inverting series probs → per-map p → fitted per-team ratings lets the MC price unplayed branches the market never quotes. | HIGH | PRD F1e. Fit at **map level** (invert Bo3 first) so one rating prices both unplayed Bo1 and Bo3 branches. Logistic least-squares. |
| **Correlated-pick warnings** (two 0-3 picks that meet in R1) | A subtle trap: two 0-3 picks meeting in R1 means one *must* win, capping that slot pair at 1 correct. Ballot A is correlation-blind; surfacing this is genuine edge. | LOW | Emerges for free from Ballot B's joint-sample search; surface explicitly anyway since Ballot A can fall into it. |
| **Backtest trust badge** ("validated vs Austin/Budapest 2025 ✓") | Does more for user trust than any styling when deciding whether to believe an "82% advance." Ties the UI to the correctness gate. | LOW | §10.5. Depends on the backtest gate passing. |
| **Full-Major scope: Stages 2–3 + playoff single-elim + optional map-level Bo3** | Turns a one-stage tool into a whole-Major / Diamond-coin planning instrument — the user's actual v3 ask. | MEDIUM (stages 2-3 reuse engine) / HIGH (map-level) | PRD v3. Stages 2-3 are the same Swiss engine with different seeds. Playoffs are trivial single-elim. Map-level Bo3 only if backtest demands it. |

### Anti-Features (Commonly Requested, Often Problematic)

Documented to prevent scope creep. Each is something a CS pick'em tool *could* add but shouldn't here.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Champion / Diamond-coin endgame prediction** (who wins the Major) | "I want to predict the whole event." | Out of scope for a *Pick'Em-EV* tool; playoff outcome is a different, much-higher-variance prediction with no Swiss-EV payoff. Pulls focus from the calibration core. | Stop at playoff bracket *structure*; don't model a single champion probability as a headline number. |
| **Map-veto / map-pool modeling** | "Team X is weak on Mirage; the model should know." | Huge state/data burden (veto order, per-map ratings, map removal logic) for marginal accuracy. Per-matchup odds already absorb most map-pool signal via the market. | Single win-prob per matchup; map-level Bo3 only as a v3 stretch *if the backtest shows series modeling is insufficient*. |
| **Scraping / browser automation for odds** | "Thunderpick/Kalshi have lines not in the API." | Fragile (DOM breakage), slow (seconds vs ms), ToS-risky, geo-restricted (Thunderpick). Every needed source has a clean API; Thunderpick arrives via OddsPapi anyway. | APIs only. Reserve scraping only for a hypothetical future source with no API *and* permissive ToS *and* unique signal — none qualify. |
| **Account / auth / multi-user / cloud sync** | "Share ballots with friends." | Adds backend, sessions, a database — enormous surface for a single-local-user tool. Friends clone the repo; that *is* the sharing model. | Single local user; Streamlit `session_state`. No localStorage even in an HTML variant. |
| **Streaming / always-live odds polling** | "Keep odds fresh in real time." | Pick'Em locks **once per stage**; streaming buys nothing and burns rate limits. | Two fetch triggers only: minutes before lock, and once per round after pairings post (~5 polls). Manual "fetch now" button. |
| **Sampling 3 separate map Bernoullis for Bo3** | "More realistic to simulate each map." | For iid maps the closed form `p²(3−2p)` is *exact*; sampling 3 maps only adds cost and MC noise. | Single Bernoulli draw on the closed-form series prob. (Eng-review decision, supersedes F2 wording.) |
| **Burying epistemic uncertainty inside per-sim sampling** | "Just add the source variance into the draw." | Folds epistemic disagreement into aleatoric noise → Wilson band looks falsely tight at large N → defeats the honesty goal (G4). | Outer-loop Beta draws; report spread across draws as the epistemic band. |
| **Responsive/mobile/tablet, theming, branding, animations** | "Make it look polished." | Local single-user desktop tool; styling effort returns ~nothing. Streamlit constrains styling anyway. | Pin minimal visual tokens (monospace numbers, one accent, colorblind-safe status). No DESIGN.md. |
| **Equal-weight `st.metric` card mosaic** | Streamlit default-pretty layout. | Flattens hierarchy — the ballot is the hero, probs are a dense table; symmetry hides what matters. | Explicit information hierarchy per §10.5 (ballot > probs > bracket pre-stage; flips live). |
| **Equal-weighting odds sources by headcount** | "More books = more confidence." | Soft books copy Pinnacle; arbitrageurs tie Polymarket/Kalshi to it — an "illusion of independence." Headcount overweights correlated copies. | Weight by liquidity/sharpness/originate-vs-copy in the log-opinion pool. |

---

## Feature Dependencies

```
Faithful Swiss engine (F3)
    └──gated by──> Round-by-round backtest (HARD GATE before any sim output trusted)
    └──requires──> Buchholz = Σ(opp.wins − opp.losses)   [P0 — wrong formula corrupts everything]

Monte Carlo runner (F4)
    └──requires──> Swiss engine (F3)
    └──provides per-team marginals──> Pick'Em optimizer Ballot A (E[correct], greedy)

Pick'Em optimizer Ballot B (P(>=5), search)
    └──requires──> MC that STORES the per-sim record sample (not just marginals)
    └──provides──> correlated-pick warnings (for free from joint sample)

Conditional re-sim (F6)  [KILLER FEATURE]
    └──requires──> engine result-locking (locked: dict[frozenset -> winner], deterministic)
    └──requires──> MC runner (F4)
    └──enables──> live pick status (live/dead/secured + P(>=5)-from-here delta)
    └──enables──> record-bucket bracket (locked solid / simulated faint)

Odds ensemble (F1)
    └──requires──> OddsProvider adapter + pool()
    └──feeds──> ratings back-solve ──> drives unplayed branches in MC
    └──feeds──> epistemic variance ──(outer-loop Beta)──> epistemic CI bands
    └──fails soft to──> rating-only mode (no key) — NOT a hard dependency for v0

Epistemic CI bands  ──widen/superset──>  Wilson (aleatoric) CI bands
    └──requires──> odds ensemble (multi-source variance); single source -> band collapses to Wilson

Full-Major scope (v3)
    Stages 2-3      ──reuse──> same Swiss engine (F3) with different seeds
    Playoff bracket ──is──>    trivial single-elim (NOT Swiss)
    Map-level Bo3   ──conditional on──> backtest showing series modeling insufficient
```

### Dependency Notes

- **Everything gates on the backtest.** No sim output is trustworthy and the UI shouldn't be built until the engine reproduces a past Major's pairings exactly. This is a slice-1 hard gate, not post-hoc validation — it's the only check that proves greedy rematch resolution matches Valve's priority table.
- **Ballot B (P≥5) needs the full sim sample, not marginals.** Ballot A only needs per-team probabilities; Ballot B and live P(≥5)-from-here both score *each simulated stage's record vector* against the ballot. Structure the MC to retain the sample (or stream it through the scorer) from the start — retrofitting is painful.
- **Conditional re-sim depends on engine result-locking.** The lock must be deterministic and respect no-rematch history. `test_locked_results_honored` guards the entire F6 feature.
- **Epistemic bands depend on the odds ensemble.** With one source (or rating-only mode), the epistemic band collapses to the Wilson band — that's correct, not a bug. The two-layer band is only meaningful when sources disagree.
- **Odds layer must fail soft.** A missing API key drops to rating-only mode with a banner — it is an enhancement, never a gate. So v0 (rating-only) is fully functional without F1.
- **Stages 2-3 reuse the engine; playoffs do not.** Stages 2-3 are the same 16→swiss machinery with new seeds. Playoffs are a separate, simpler single-elim path. Map-level Bo3 is the only genuinely new modeling in v3 and is conditional.

---

## MVP Definition

### Launch With (v0 — rating-only, headless then minimal UI)

- [ ] **Faithful Swiss engine + backtest gate** — without correct pairings every number is garbage; the gate proves it.
- [ ] **Monte Carlo per-team P(3-0)/P(advance)/P(0-3) + invariant checks** — the core deliverable; answers "what are my real odds per pick."
- [ ] **Editable seeds/ratings + `S` slider + zero-config defaults** — usable without odds, reconcilable at lock.
- [ ] **Wilson CI bands visible** — the honesty floor; cheap, and the product's stated value.
- [ ] **`uv` one-command bootstrap + `[INFERRED]`-seed banner** — adoption + correctness safety.

Bail-out: stop here if the per-team probabilities don't tell you anything the hand tier list didn't.

### Add After Validation (v1)

- [ ] **Pick'Em optimizer Ballot A (E[correct], greedy) + exact-record scoring** — turns a probability table into a decision tool.
- [ ] **P(≥5/10) + Ballot B (search) + dual-ballot diff** — trigger: v0 probs prove informative. Requires storing the sim sample.
- [ ] **Correlated-pick warnings** — falls out of Ballot B for free.
- [ ] **Odds ensemble: OddsPapi/Pinnacle anchor live + ratings back-solve** (Polymarket/Kalshi stubbed) — trigger: want self-updating inputs; fails soft.

### Add After v1 (v2)

- [ ] **Conditional re-sim (F6) + live mode status (live/dead/secured)** — trigger: want the tool usable *during* the event. The killer feature; deferred only because it depends on a stable locking engine.
- [ ] **Record-bucket bracket view** — companion UI to re-sim.
- [ ] **Polymarket + Kalshi adapters live + epistemic variance → MC + epistemic bands** — trigger: want divergence signal and the two-layer honesty band.

### Future Consideration (v3)

- [ ] **Stages 2-3 Swiss** — reuse engine; trigger: Stage 1 fully validated live.
- [ ] **Playoff single-elimination bracket** — trivial; trigger: stages done.
- [ ] **Optional map-level Bo3 modeling** — defer; add ONLY if the backtest shows single-series-prob modeling is insufficient. Otherwise it's an anti-feature (cost without accuracy).

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Faithful Swiss engine + backtest gate | HIGH | HIGH | P1 |
| MC per-team P(3-0)/adv/0-3 + invariants | HIGH | MEDIUM | P1 |
| Editable seeds/ratings + `S` + zero-config | HIGH | LOW | P1 |
| Wilson CI bands visible | HIGH | MEDIUM | P1 |
| `uv` bootstrap + `[INFERRED]`-seed banner | HIGH | LOW | P1 |
| Pick'Em Ballot A (E[correct], exact-record) | HIGH | MEDIUM | P1 |
| P(≥5) + Ballot B + dual-ballot diff | HIGH | MEDIUM | P2 |
| Correlated-pick warnings | MEDIUM | LOW | P2 |
| Odds ensemble (Pinnacle anchor) + back-solve | MEDIUM | HIGH | P2 |
| Conditional re-sim + live status | HIGH | HIGH | P2 |
| Record-bucket bracket view | MEDIUM | MEDIUM | P2 |
| Polymarket/Kalshi adapters + epistemic bands | MEDIUM | HIGH | P3 |
| Stages 2-3 Swiss | MEDIUM | MEDIUM | P3 |
| Playoff single-elim bracket | LOW | LOW | P3 |
| Map-level Bo3 modeling | LOW | HIGH | P3 (conditional) |

**Priority key:** P1 = must have for launch (v0–v1 core) · P2 = should have (v1–v2) · P3 = future/v3.

---

## Competitor Feature Analysis

| Feature | HLTV Swiss tables | BLAST.tv Pick'Em tracker | Community spreadsheets | Our Approach |
|---------|-------------------|--------------------------|------------------------|--------------|
| Per-team advance % | Yes (static, single estimate) | No | Sometimes | MC with CI bands + epistemic layer |
| P(exactly 3-0)/P(exactly 0-3) | Rarely / coarse | No | Rare | First-class outputs, exact-record |
| Ballot recommendation | No | Manual pick/track only | Occasionally ad-hoc | Dual optimized ballots (A + B) |
| True P(≥5/10) coin odds | No | No | No | Yes — headline number |
| Conditional live re-sim | No (manual refresh) | Tracks your picks, no re-sim | No | Yes — the killer feature |
| Honest uncertainty bands | No | No | No | Yes — Wilson + epistemic |
| Market-odds-derived inputs | No (own model) | No | No | Yes — de-vigged ensemble + back-solve |

The whitespace this tool occupies: **nobody combines a faithful conditional re-sim with optimized dual ballots and an honest P(≥5).** Public tools give you either a static table or a pick tracker, never your *specific ballot's live coin odds with calibrated uncertainty*.

---

## Confirms vs. Contradicts the PRD

- **CONFIRMS:** 2/6/2 ballot, ≥5/10 coin threshold, exact-record 3-0/0-3 scoring, advance = reach 3 wins — all verified for IEM Cologne 2026.
- **CONFIRMS:** Swiss mechanics (16 teams, 3W/3L, N vs N+8, Bo3 on advancement/elimination/decider, no rematches, 15-row priority table).
- **CONFIRMS (strongly):** Buchholz = Σ(opp.wins − opp.losses), verified verbatim against Valve's rulebook with the worked example. The eng-review P0 fix (`sum(o.wins)` is wrong) is correct.
- **CONFIRMS:** the killer-feature framing — conditional re-sim is genuinely the differentiating capability no public tool offers.
- **MINOR NUANCE (not a contradiction):** Valve's literal tiebreak chain is **record → Difficulty Score → initial seed**, i.e. record comes *first*. The PRD/HANDOFF phrase it as "difficulty, then seed" because the engine groups by record before sorting — functionally identical, but document it so it isn't "corrected" later. Also, "Buchholz from R3" is an emergent property (R2 difficulty is uniform within a group), not a special rule — the single-code-path design is right.
- **NO CONTRADICTIONS FOUND.** The domain model in PROJECT.md / PRD / HANDOFF is accurate on every load-bearing fact.

---

## Sources

- Valve official `major-supplemental-rulebook.md` (ValveSoftware/counter-strike_rules_and_regs) — Difficulty Score formula, tiebreak chain, pairing/rematch rules, Bo3 conditions. **HIGH (authoritative).**
- [cs.money — IEM Cologne 2026 Stage 1 Pick'Em guide](https://cs.money/blog/esports/iem-cologne-2026-major-pickem-guide-for-stage-1/) — 2/6/2 ballot, 10 picks / ≥5 correct, coin tiers. HIGH.
- [Strafe — IEM Cologne Major 2026 Stage 1 Pick'Ems guide](https://www.strafe.com/news/read/iem-cologne-major-2026-the-only-stage-1-pick-ems-guide-you-need/) — advance = finish 3-1/3-2. MEDIUM.
- [BLAST.tv Major Pick'Em hub](https://blast.tv/major/pickems) and [skin.club CS2 Pick'Em](https://cs2major.com/pickem) — ballot structure confirmation. MEDIUM.
- [Steam Community — "Do 3-0 picks count as advanced too?"](https://steamcommunity.com/app/730/discussions/0/6352962881243897519/) — exact-record scoring (3-0 pick finishing 3-1 scores zero). MEDIUM (community, corroborated by guides).
- [PGL — Buchholz tiebreaker announcement](https://news.pglesports.com/news/) — Buchholz adoption in Challengers/Legends stages. MEDIUM.
- [ESL Pro Tour — Live Ratings & matchup determination in Swiss](https://pro.eslgaming.com/tour/2025/03/esl-live-ratings/) and [esports.net Swiss explained](https://www.esports.net/news/counter-strike/swiss-system-explained/) — Swiss mechanics, Bo3 deciders, seeding. MEDIUM.

---
*Feature research for: CS2 Major Swiss MC + Pick'Em-EV optimizer*
*Researched: 2026-05-28*
