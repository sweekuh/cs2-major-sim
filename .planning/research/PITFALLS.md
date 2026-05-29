# Pitfalls Research

**Domain:** CS2 Major Swiss-stage Monte Carlo simulator + Pick'Em optimizer (Python / Streamlit / numpy) driven by a multi-provider market-odds ensemble
**Researched:** 2026-05-28
**Confidence:** HIGH on engine/statistics pitfalls (cross-checked vs HANDOFF math + Valve/HLTV format sources + numpy docs); MEDIUM on odds-ensemble specifics (WebSearch-verified, market-mechanics-dependent)

> **How to read this file.** The PRD §10 risk table and the eng-reviewed HANDOFF already cover the headline failure modes well. This document is split into two jobs:
> 1. **CONFIRMS** — pitfalls the existing docs already name; restated only to tie them to a build phase and a detection test.
> 2. **EXTENDS** — pitfalls NOT in §10 or the HANDOFF that would still silently corrupt outputs or burn event-day time.
>
> Every correctness-fatal pitfall traces to one gate: **the round-by-round backtest against a real past Swiss stage (Austin/Budapest 2025).** Invariant tests (Σ P(3-0)=2, etc.) are necessary but **do not** catch the corruption-fatal class — a wrong probability still sums to 2. The backtest, the `test_difficulty_formula` unit, and the epistemic-band test are the only checks that catch silent corruption.

---

## Severity legend

- **CORRECTNESS-FATAL** — silently produces wrong probabilities that pass invariants and look plausible. The user makes real Pick'Em decisions on laundered numbers. No visible symptom.
- **OPS-FATAL** — works in dev, breaks or stalls on event day under live re-run pressure when the clock is running.
- **COSMETIC / DEGRADED** — wrong or annoying but visibly so; user notices and distrusts.

---

## Critical Pitfalls

### Pitfall 1: Buchholz computed as Σ(opp.wins) instead of Σ(opp.wins − opp.losses) — CORRECTNESS-FATAL

**Status:** CONFIRMS PRD §10 ("Buchholz small-sample distortion" / "Implement exactly per rulebook") and HANDOFF §4/§6 (eng-review P0). Restated here because it is the single highest-severity trap and must anchor the phase gate.

**What goes wrong:**
The "Difficulty Score" seeds teams within a record group from Round 3 on. Using `sum(o.wins)` instead of `sum(o.wins - o.losses)` produces a *different ordering* within the group, which produces *different pairings*, which produces *different downstream branches* — corrupting every P(3-0)/P(advance)/P(0-3). The simulation still terminates correctly: exactly 8 advance, 2 go 3-0, 2 go 0-3. All invariants pass.

**Why it happens:**
Most casual explanations of Buchholz online say "sum of opponents' wins" (the chess Buchholz heritage and even HLTV's summaries phrase it loosely as "combined score"). Valve's actual Difficulty Score is wins **minus** losses. A developer who Googles "CS2 Buchholz" and trusts the first explanation implements the wrong formula and it passes every structural test.

**How to avoid:**
- Single code path with `difficulty(t) = sum(o.wins - o.losses for o in t.opps)` (HANDOFF §4 — already correct in spec).
- `test_difficulty_formula` [CRITICAL]: Valve's worked example (opponents at 2-0 and 1-1 → score 2 = (2+1)−(0+1)). This is the ONLY unit test that distinguishes the two formulas.
- Backtest: the wrong formula will reorder a real past stage's Round 3+ groups and diverge from actual pairings.

**Warning signs:**
- Difficulty Score equals total opponent wins in any debug print (the bug). Correct scores can be negative.
- A team that beat only eliminated opponents is seeded ABOVE a team that beat advancing opponents within the same group (inverted — the losses term is missing).

**Phase to address:** **Phase 1 (engine + backtest gate), before any UI.** This is the gate, not a later hardening step.

---

### Pitfall 2: Rematch-avoidance fold approximates Valve's priority table instead of matching it — CORRECTNESS-FATAL

**Status:** CONFIRMS HANDOFF §4 (greedy `fold_match` "approximates that table … the backtest is the gate that proves it"). EXTENDS it with the specific divergence mode and which round it bites.

**What goes wrong:**
Valve resolves forced rematches with a literal 15-row priority table that keeps top-seed pairings stable and permutes the **lowest** pairs first (`1v6,2v5,3v4` → `1v6,2v4,3v5` → …). The greedy backtracking fold in the HANDOFF tries the worst-ranked candidate first and backtracks on conflict. In the common case these agree. They can **diverge** when multiple rematch conflicts force a non-obvious permutation — and greedy may pick a *valid* rematch-free matching that is not the one Valve's table mandates. The pairing is legal (no rematch) but wrong, so it corrupts that branch's downstream probabilities while passing the no-rematch invariant.

**Why it happens:**
The greedy is easier to write than transcribing a 15-row table, "feels right," and passes the no-rematch test. Divergence only shows up in specific group configurations that may not appear in a casual smoke test — but **do** appear in real Round 4/5 groups with dense rematch history.

**How to avoid:**
- Treat the backtest as the contract: feed a completed stage's seeds + forced results and assert **exact** round-by-round pairings (HANDOFF §6 determinism check).
- If ANY pairing diverges, do not patch the ratings — **replace greedy with the literal priority-table lookup** (HANDOFF §4 says exactly this; make it a planned fork, not a surprise).
- `test_forced_rematch_pairing`: construct a group where the ideal fold is a rematch; assert output matches the table.
- Pull the actual table verbatim from `ValveSoftware/counter-strike_rules_and_regs/major-supplemental-rulebook.md` during Phase 1; do not approximate from memory.

**Warning signs:**
- Backtest reproduces Rounds 1–3 but diverges in Round 4 or 5 (where rematch density peaks).
- Greedy returns a matching but a hand-check of Valve's table for the same group gives a different bottom pairing.

**Phase to address:** **Phase 1.** The backtest is the gate; budget time for the priority-table-lookup fallback inside Phase 1, not after.

---

### Pitfall 3: Fold is on seed instead of on Difficulty-Score rank within the group — CORRECTNESS-FATAL

**Status:** EXTENDS. Neither §10 nor the HANDOFF flags this as a *distinct* trap from Pitfall 1, but it is — you can have the difficulty formula correct yet fold on the wrong key.

**What goes wrong:**
Within a record group from Round 3 on, the fold (high vs low) must operate on the **Difficulty-Score-then-seed ordering**, i.e. highest-Buchholz plays lowest-Buchholz (HLTV: "high Buchholz plays low Buchholz"). A natural-but-wrong implementation folds on raw initial **seed** within the group even when Buchholz has reordered it. The difficulty formula is correct (Pitfall 1 passes) but it's never used as the fold key — so pairings are still wrong.

**Why it happens:**
Round 1 pairs by seed (N vs N+8) and Round 2 falls through to seed (difficulty is uniform). A developer generalizes "fold on seed" from R1/R2 and forgets that R3+ must fold on the difficulty-sorted `ranked` list. The HANDOFF's `fold_match(ranked)` takes the already-sorted list as input, which is correct — but only if the caller sorts by `(−difficulty, seed)` and passes THAT list. The bug lives in the caller, not `fold_match`.

**How to avoid:**
- Assert in code/test that the list handed to `fold_match` is sorted by `(−difficulty, seed)` for R3+.
- Backtest catches it: a stage where Buchholz reorders a group away from seed order will diverge if you folded on seed.
- Add a targeted unit test: a 4-team group where Buchholz order ≠ seed order; assert the pairing follows Buchholz order.

**Warning signs:**
- R3+ pairings within a group always pair `seed_min vs seed_max` even when Buchholz differs.
- Removing the difficulty sort from the caller changes nothing in output (means it was never used as the fold key — dead code = bug).

**Phase to address:** **Phase 1**, same gate as Pitfalls 1–2.

---

### Pitfall 4: Beta draw buried in the inner per-sim loop, collapsing the epistemic band — CORRECTNESS-FATAL

**Status:** CONFIRMS HANDOFF §5 / PROJECT key-decision G4 (epistemic via outer loop). Restated to tie to a *test* and a phase, and to make the failure visible (it produces falsely-tight bands that look MORE trustworthy).

**What goes wrong:**
Source disagreement (epistemic uncertainty) does not shrink as you add Monte Carlo sims; coin-flip variance (aleatoric) does. If the per-match Beta draw lives inside the per-sim loop, epistemic uncertainty gets averaged into the aleatoric noise and the reported Wilson band shrinks toward zero as N grows. The tool then displays its *tightest, most confident* bands on exactly the matches where sources disagree most — the opposite of honest calibration (defeats goal G4). This is worse than no bands: it actively misleads.

**Why it happens:**
It's the more natural code structure — one loop, sample everything per sim. The honest structure (outer loop over epistemic Beta draws, each running a full MC batch, aggregate across draws) is a deliberate two-level nesting that costs more compute and isn't obvious.

**How to avoid:**
- Outer-loop structure from HANDOFF §5: `for draw in epistemic_draws: p_vector ~ Beta(blend,var); run MC batch`; reported band = spread **across** draws; single source → band collapses to Wilson only.
- `test_epistemic_band_wider_than_wilson` [CRITICAL]: with disagreeing sources assert the reported band ⊇ inner Wilson band.
- Sanity probe: increase N 10×. The Wilson (aleatoric) band should shrink ~√10; the **epistemic** band should NOT. If the reported band keeps shrinking with N on a high-disagreement match, the draw is in the wrong loop.

**Warning signs:**
- Bands monotonically shrink with N on every match including high-disagreement ones.
- A match with one source and a match with three wildly-disagreeing sources show the same band width at the same N.

**Phase to address:** **Phase 5 (odds ensemble + variance→MC).** Until odds land, there is only one source and the band correctly is Wilson-only — but build the MC's loop structure in **Phase 1** to *accept* an outer epistemic loop so retrofitting in Phase 5 isn't a rewrite.

---

### Pitfall 5: Beta method-of-moments fit crashes (or silently clamps wrong) on low-liquidity, high-disagreement matches — CORRECTNESS-FATAL

**Status:** CONFIRMS HANDOFF §5 (`clamp variance < p(1-p)`). EXTENDS with the failure-correlation insight: it crashes on *exactly the matches that matter most*.

**What goes wrong:**
Beta method-of-moments back-solves `α,β` from mean `p` and variance `v`. If `v ≥ p(1−p)` (the variance ceiling of a [0,1] variable), the solved `α,β` go negative or zero and `Beta(α,β)` raises or returns garbage. The matches with the highest cross-source variance are the thin-liquidity tier-2 / 0-3 candidates — which are precisely the marginal Pick'Em slots the whole tool exists to price. So the crash/garbage lands on the highest-value decisions.

**Why it happens:**
The variance ceiling is non-obvious; developers test the fit on agreeing sharp markets (low variance, fits fine) and never hit the edge until a real thin market with two sources 30 points apart shows up — on event day.

**How to avoid:**
- Clamp `v = min(v, p*(1-p) - epsilon)` BEFORE the moment fit (HANDOFF §5 — already specified; make the epsilon explicit and tested).
- Decide and document the semantics of the clamp: a clamped match is *maximally uncertain*, so it should also be flagged low-confidence in the UI, not silently treated as a clean estimate.
- Test the boundary directly: `p=0.5, v=0.30` (above the 0.25 ceiling) must not raise and must produce a wide-but-valid Beta.

**Warning signs:**
- Any `ValueError`/`nan` from the Beta sampler appearing only on certain matches.
- A clamped match displays a narrow band (means the clamp silently substituted a small variance instead of capping at the ceiling).

**Phase to address:** **Phase 5.** Add the boundary unit test the moment the pooling code exists.

---

### Pitfall 6: Wrong / unreconciled seed silently corrupts every probability — CORRECTNESS-FATAL

**Status:** CONFIRMS PROJECT + HANDOFF §10.6 ([INFERRED]-seed loud banner). EXTENDS with the reconcile-at-lock mechanism and the specific reason a banner alone is insufficient.

**What goes wrong:**
Seeds drive R1 (N vs N+8), all R2 within-group ordering, and every Buchholz tiebreak. The current seed list is [INFERRED] from announced R1 matchups; only M80=6, NRG=9, Liquid=13 are confirmed. A single wrong seed reshuffles pairings throughout the bracket and corrupts every output — with no visible symptom (invariants still hold).

**Why it happens:**
The inferred seeds are good enough to *look* right pre-event. The official seed list lands shortly before lock — exactly when the user is rushed and most likely to skip verification. A README footnote gets forgotten at the moment it bites.

**How to avoid:**
- Loud, persistent, dismissable in-app banner until a "seeds confirmed" toggle is flipped (HANDOFF §10.6 — already specified).
- EXTEND: the cold-start checklist must require *reconciling the inferred list against the official seed list field-by-field*, not just toggling the banner off. Consider showing a diff ("you changed 3 seeds") before allowing confirmation, so blind-confirming is harder than actually checking.
- Tie the trust badge to BOTH backtest-passed AND seeds-confirmed; an "82% advance" with unconfirmed seeds should not show the green trust state.

**Warning signs:**
- Banner dismissed but seeds never edited (toggle-without-reconcile).
- R1 matchups in the app don't match HLTV's published opening matchups.

**Phase to address:** Banner + toggle in **Phase 2 (UI)**; reconcile-diff and trust-badge gating in **Phase 2**; the event-day checklist in the README at **Phase 2** (DX contract §10.6).

---

### Pitfall 7: Ensemble illusion of independence — soft books copy Pinnacle, prediction markets track it via arbitrage — CORRECTNESS-FATAL (subtle)

**Status:** CONFIRMS PRD §10 ("Ensemble illusion of independence" / "Weight by originate-vs-copy, not headcount"). EXTENDS with the concrete weighting failure and the prediction-market arbitrage tie.

**What goes wrong:**
A log-opinion pool that weights by source count treats 10 books as 10 independent experts. But soft books (Thunderpick, GG.BET, Betway — all arriving in one OddsPapi call) largely copy Pinnacle, and Polymarket/Kalshi prices are dragged toward the sharp line by arbitrageurs. Equal/headcount weighting double-counts Pinnacle's opinion ~8×, making the blend look like a tight consensus when it's really one source echoed. The *cross-source variance* — the thing that drives the epistemic band — is then falsely small, compounding Pitfall 4.

**Why it happens:**
"More sources = more confidence" is the intuitive pooling rule, and OddsPapi handing back 10 books per fixture makes headcount weighting trivially easy.

**How to avoid:**
- Weight by originate-vs-copy and liquidity/sharpness, not headcount (PRD §10). Practically: Pinnacle anchor gets dominant weight; soft books contribute little marginal weight; treat the OddsPapi book bundle as ~one sharp opinion plus minor independent noise.
- Treat Polymarket/Kalshi as semi-correlated with Pinnacle, not independent; do not let three near-identical numbers masquerade as agreement that collapses the epistemic band.
- Document the weighting rationale so it isn't silently "fixed" back to equal weight later.

**Warning signs:**
- Adding more soft books narrows the epistemic band (independence assumption — wrong).
- Polymarket/Kalshi/Pinnacle within 1–2 points → reported as high-confidence consensus rather than "they're all reading the same sharp line."

**Phase to address:** **Phase 5 (pooling / `pool()`).**

---

### Pitfall 8: Vig handling — applying fixed-odds de-vig to prediction-market prices (or skipping spread/fee adjustment) — CORRECTNESS-FATAL

**Status:** CONFIRMS PRD §10 ("Vig mishandling") and HANDOFF §5. Restated to pin per-source-type routing as a test.

**What goes wrong:**
Fixed-odds books carry a two-way overround removed by `p_a = (1/o_a)/(1/o_a+1/o_b)`. Prediction-market prices are already ~probabilities and need only spread/fee adjustment. Applying the fixed-odds de-vig to a Polymarket price (or vice versa) biases that source's probability, which biases the blend and the back-solved ratings.

**Why it happens:**
One normalization function applied uniformly is the simplest code. The `vig_type` field exists in `OddsQuote` precisely to route this, but it's easy to ignore on the first pass.

**How to avoid:**
- Route on `vig_type` ("fixed" vs "market") in normalization (HANDOFF §8 / §5 — specified).
- `test_devig` (fixed `o=1.5/2.5 → p≈0.625`) AND a market-price-passthrough test (market price 0.62 → ~0.62 after only spread/fee, NOT re-de-vigged).

**Warning signs:**
- All sources run through the same normalization branch.
- A Polymarket price visibly shifts after normalization in a way only de-vig would cause.

**Phase to address:** **Phase 5.**

---

### Pitfall 9: Series/format conflation in the ratings back-solve and odds override — CORRECTNESS-FATAL

**Status:** CONFIRMS HANDOFF §5 (fit ratings at map level; odds override = series prob, don't re-apply Bo3). EXTENDS by naming the two-way trap as one pitfall and tying both directions to a test.

**What goes wrong:**
Two symmetric errors:
1. **Fitting ratings to series probs.** Market odds are *series* probabilities for a specific format (Bo1 vs Bo3). A Bo3 favorite's series prob is more extreme than its map prob (`p²(3−2p)`). Fitting one rating to mixed Bo1/Bo3 series probs makes a rating that can't correctly price both unplayed Bo1 and Bo3 branches. Must invert each series prob to map-level first, then fit.
2. **Re-applying Bo3 to an odds-derived series prob.** If a market already prices the series, using it directly is correct; running it back through `p²(3−2p)` double-counts the format.

**Why it happens:**
The logistic model is naturally map-level, but the data arrives as series probs; the inversion step is an easy omission. And the Bo3 closed form is so central it's tempting to apply everywhere.

**How to avoid:**
- Back-solve: invert series→map (identity for Bo1, invert `p²(3−2p)` for Bo3), then logistic least-squares on map probs (HANDOFF §5).
- Override: if an odds series prob exists for the exact matchup, use it directly as the series prob — never re-apply Bo3 (HANDOFF §5).
- `test_rating_roundtrip` (fit to known map probs, recover them) + a test that a Bo3 odds override is NOT re-squared.

**Warning signs:**
- Back-solved ratings make Bo1 underdogs look weaker than their actual map odds (series→map inversion skipped).
- A team's modeled series prob differs from the market's series prob it was given (double Bo3 applied).

**Phase to address:** **Phase 5** (back-solve is slice 5; override math in `probs.py` from Phase 1).

---

### Pitfall 10: numpy reproducibility breaks when chunk/thread count changes — CORRECTNESS-ADJACENT / OPS

**Status:** EXTENDS — NOT in §10 or the HANDOFF. The HANDOFF asks for a "threaded seed for reproducible runs/backtests" AND chunked progress yielding (§10.5), and these two requirements quietly conflict.

**What goes wrong:**
numpy's reproducibility guarantee holds for the same seed **only if the number of streams/threads is fixed** (numpy docs; "if you're multi-threading, reproducibility goes bye-bye" unless you spawn child generators deterministically). The design wants (a) a reproducible seed for the backtest, and (b) chunked execution (20×5k) that yields progress for the live tally. If chunk count, chunk size, or thread count varies between runs — or differs between the backtest harness and the app — the "reproducible" backtest is not actually reproducible, and the gate that proves engine correctness becomes non-deterministic.

**Why it happens:**
`np.random.default_rng(seed)` *looks* deterministic and is, single-threaded. The non-reproducibility only appears once chunking/threading is added for the progress UI — a Phase 2 design decision that silently undermines a Phase 1 correctness gate.

**How to avoid:**
- Use `SeedSequence(seed).spawn(n_chunks)` to derive one child generator per chunk deterministically; reproducibility then depends only on `(seed, n_chunks)`, both of which you control and can pin.
- Pin `n_chunks` (or derive it deterministically from N) so the same `(seed, N)` always yields the same chunking and the same result.
- The backtest must run the SAME chunked path the app uses (not a separate single-threaded path), or it validates code that doesn't ship.
- Test: same `(seed, N)` → identical per-team counts across two runs; changing only `n_chunks` is allowed to change results but must be documented as not seed-stable across chunk counts.

**Warning signs:**
- Two runs with the same seed give slightly different P(advance).
- Backtest passes locally but a friend on a different machine/thread default sees different pairings or probs.

**Phase to address:** **Phase 1** decide the seeding/spawn scheme; **Phase 2** must not break it when adding chunked progress. Flag as a Phase 1×2 cross-impact.

---

### Pitfall 11: Streamlit-as-scheduler — auto-fetch inside the app + Community Cloud sleep — OPS-FATAL

**Status:** CONFIRMS TODOS #1 + PROJECT constraints. Restated as an event-day pitfall with the seam decision pulled forward.

**What goes wrong:**
Streamlit re-runs the whole script per widget interaction and has no background scheduler; Community Cloud sleeps between requests. A per-round auto-fetch loop placed inside the app either never fires (cloud asleep), blocks the UI on every rerun (inline keyed API calls), or leaks keys into the UI session. On event day this manifests as stale or missing odds at the exact moment of lock.

**Why it happens:**
"Just call the provider when the round changes" is the obvious in-app implementation, and it works in a always-open local dev session — then fails when deployed or when the tab is closed between rounds.

**How to avoid:**
- App only ever READS a cache (`data/odds_cache.json`); never calls `OddsProvider.get_quotes()` on rerun (TODOS #1).
- Build the cache-file seam in Phase 5 even though auto-fetch is later: the v1 manual "fetch now" button writes the SAME cache the app reads, so v2 only adds a cron trigger on the always-on host — no rewrite.
- Manual "fetch now" is the event-day fallback; never depend on cloud-side scheduling.

**Warning signs:**
- Odds calls appear in the Streamlit rerun path.
- Deployed app shows stale odds after being idle.

**Phase to address:** **Phase 5** (build the read-only cache seam); auto-fetch cron is post-v2 (TODOS #1).

---

### Pitfall 12: Missing API key hard-crashes instead of failing soft — OPS-FATAL

**Status:** CONFIRMS HANDOFF §10.6 (rating-only mode + banner). Restated as event-day pitfall.

**What goes wrong:**
A missing `ODDSPAPI_KEY` that raises on startup means a friend who clones the repo (or future-you on a fresh machine on event day) gets a blank crash instead of a working rating-only sim. The zero-config first-run promise is broken at the worst time.

**How to avoid:**
- Missing key → rating-only mode + one-line info banner (`live odds off (no ODDSPAPI_KEY) — using manual ratings`); never crash (HANDOFF §10.6).
- `data/stage1.json` ships so the first sim needs no key.
- Test the no-key path explicitly (import/run with env unset).

**Warning signs:**
- App raises on launch without `.env`.
- Any provider import at module top level that fails without a key.

**Phase to address:** **Phase 5** (key handling); the zero-config first-run guarantee belongs to **Phase 2**.

---

### Pitfall 13: @st.cache_data not keyed on `locked` (or on the full input set) — CORRECTNESS-ADJACENT / OPS

**Status:** CONFIRMS HANDOFF §2 (cache keyed on `(ratings,S,N,locked)`). EXTENDS by calling out `locked` as the easy-to-forget key — the live-mode killer-feature breaks if it's missing.

**What goes wrong:**
If the MC cache key omits `locked` (the round-by-round locked results), the conditional re-sim returns the STALE pre-lock distribution after the user locks a result. Live mode then shows wrong "live/dead/secured" states and a wrong P(≥5)-from-here — silently, because a cached number looks identical to a fresh one. This is the emotional core of live mode returning a lie.

**Why it happens:**
`ratings, S, N` are the obvious inputs; `locked` is a dict added later for F6 and easy to leave out of the cache key. Streamlit happily serves the stale cached value.

**How to avoid:**
- Key on `(ratings, S, N, locked)` with `locked` hashable/serialized (HANDOFF §2).
- `test_locked_results_honored` [CRITICAL] already asserts locked winners are deterministic and invariants hold post-lock — extend it / pair it with a UI-level check that locking changes the cached output.
- Manual event-day check: lock a known result, confirm at least one team's P(advance) moves.

**Warning signs:**
- Locking a result doesn't change any displayed probability.
- Re-sim is suspiciously instant after a lock (cache hit on stale key).

**Phase to address:** **Phase 2** (cache wiring) + **Phase 4** (re-sim feature).

---

### Pitfall 14: Pick'Em correlated-pick trap — two 0-3 picks that meet in R1 — DEGRADED (decision-corrupting)

**Status:** CONFIRMS PRD F5 / HANDOFF §7. Restated because Ballot A (E[correct]) is correlation-blind and *can* recommend the trap.

**What goes wrong:**
If your two 0-3 picks meet each other in Round 1, one must win → at most one can go 0-3 → you cap yourself at 1 correct in that bucket and hurt P(≥5). Ballot A maximizes E[correct] as a linear sum of independent slot probs and is structurally blind to this correlation; it can hand you the trap.

**How to avoid:**
- Ballot B (P(≥5) hill-climb against the joint sim sample) avoids it automatically — the sims encode that both can't go 0-3.
- Surface an explicit warning anyway, because Ballot A can fall into it (HANDOFF §7).
- Test: degenerate sim where the two highest-P(0-3) teams meet in R1; assert Ballot B avoids pairing them and the warning fires.

**Warning signs:**
- Two recommended 0-3 picks share an R1 matchup with no warning shown.

**Phase to address:** **Phase 3 (optimizer).**

---

### Pitfall 15: Bo1 variance mis-sold as precision — DEGRADED / UX

**Status:** CONFIRMS PRD §10 ("Bo1 variance — report P(≥5), not a single optimal"). UX framing.

**What goes wrong:**
Early Swiss rounds are near-coinflip Bo1s, so distributions are genuinely wide. Presenting a single "optimal ballot" with a confident headline understates how much is coin-flip. The user over-trusts a marginal edge.

**How to avoid:**
- Headline P(≥5) (the true coin odds), show both ballots A/B and the differing picks, and keep CI bands visible everywhere (PRD §10, HANDOFF §10.5). The honesty is the product.

**Phase to address:** **Phase 3** (P(≥5) reporting) + **Phase 2** (CI mini-bars).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Greedy fold instead of literal priority-table lookup | Faster to write; passes common cases | Diverges from Valve in dense-rematch Round 4/5 groups → silent corruption | Only if the backtest passes exactly; else replace (planned Phase-1 fork) |
| Single normalization fn for all sources | One code path | Biases prediction-market or fixed-odds probs | Never — route on `vig_type` from day one of Phase 5 |
| Beta draw in inner loop | One loop, simpler MC | Falsely tight bands at large N; defeats G4 | Never — structure outer loop in Phase 1 even before odds |
| Inline odds fetch in Streamlit | No cron needed | Breaks on Community Cloud sleep; UI blocks; key leak | Never for auto-fetch; manual "fetch now" → cache is fine |
| Hardcoding R1 table separately from seed list | Quick fixture | Two copies drift when official seeds land | Never (HANDOFF §3 DRY — derive R1 from seeds) |
| Pure-Python 100k (no Numba) | Ships v0–v2 fast | ~10–30s runs; annoying under live re-run pressure | Acceptable through v2; trigger Numba only if event-day latency bites (TODOS #2) |
| Equal-weight pooling | Trivial with OddsPapi's 10-book bundle | Double-counts Pinnacle; collapses epistemic band | Never — weight by originate/liquidity |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| OddsPapi (Pinnacle bundle) | Treat the ~10 returned books as 10 independent experts | One sharp anchor + minor noise; weight by originate, not headcount (Pitfall 7) |
| Polymarket / Kalshi | Treat price as independent of Pinnacle; de-vig it like a book | Semi-correlated via arbitrage; adjust for spread/fee only, downweight thin volume (Pitfalls 7–8) |
| Polymarket resolution | Assume the market price is a clean live probability near settlement | Markets near resolution can be distorted by the 2-hr challenge/dispute window and authoritative-source rules; downweight/skip near-settlement quotes |
| Kalshi CS2 markets | Assume liquidity exists for tier-2 / 0-3 candidates | Thin/zero volume on niche games — the exact marginal picks; flag low `n_sources`, widen variance |
| Streamlit Community Cloud | Expect a background fetch to run | Cloud sleeps; app reads cache only; fetch is external (Pitfall 11) |
| `.env` / keys | Import provider at module top, crash without key | Lazy-init; missing key → rating-only + banner (Pitfall 12) |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Full 100k MC on every widget change | Every slider nudge re-launches the sim | `@st.cache_data` keyed on all inputs incl. `locked` | Immediately, without caching (Pitfall 13) |
| Outer epistemic loop × inner MC = N×draws sims | Run time multiplies by #epistemic draws | Reduce inner N per draw; cache; consider Numba (TODOS #2) | When epistemic draws × N gets large on event day |
| Pure-Python branchy Swiss loop | ~10–30s per full run | Acceptable v0–v2; array-of-structs + Numba `@njit` if it annoys live | Under rapid live re-locks (TODOS #2 trigger) |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| API key committed or shown in UI session | Leaked paid/limited key | Keys from env only; `.env` gitignored; `.env.example` shipped; keys live in fetch job, not UI (TODOS #1) |
| Scraping geo-restricted/ToS-hostile sources (Thunderpick) | ToS breach, fragile, IP block | APIs only; Thunderpick lines arrive via OddsPapi — never scrape (guardrail) |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Red/green status for advance/eliminate | ~8% of men can't distinguish; misreads live picks | Blue/amber + glyph + text label (`o live`/`x dead`/`/ secured`) (§10.5) |
| Showing "0%" pre-run | Looks like a real result, not "not computed yet" | Dashes pre-run; skeleton on load (§10.5) |
| Hiding CI bands behind hover/expand | False precision — the core failure mode | Always-visible inline mini-bar under every prob (§10.5, G4) |
| Swapping in a new static P(≥5) after re-sim | User misses the change that is the whole point of live mode | Show the delta arrow `71% → 58%` (§10.5) |
| Drawing a bracket tree | Misrepresents Swiss (teams reconverge by record) | Record-bucket columns (HLTV/Liquipedia convention) (§10.5) |

## "Looks Done But Isn't" Checklist

- [ ] **Buchholz:** passes invariants but verify `test_difficulty_formula` (Valve worked example = 2) AND backtest pairings exact — invariants alone hide the bug (Pitfall 1).
- [ ] **Rematch fold:** no-rematch test passes but verify it matches Valve's priority table on a real Round 4/5 group, not just that it's rematch-free (Pitfall 2).
- [ ] **Fold key:** confirm the difficulty sort is actually USED as the fold key in R3+, not dead code (Pitfall 3).
- [ ] **Epistemic band:** bands DON'T shrink with N on high-disagreement matches; band ⊇ Wilson (Pitfall 4).
- [ ] **Beta clamp:** `p=0.5,v=0.30` doesn't crash and yields a wide valid band (Pitfall 5).
- [ ] **Reproducibility:** same `(seed,N)` → identical probs across machines/chunk counts (Pitfall 10).
- [ ] **Cache key:** locking a result actually moves a displayed probability (Pitfall 13).
- [ ] **Seeds:** banner cleared only after field-by-field reconcile vs official list (Pitfall 6).
- [ ] **No-key path:** app runs rating-only without `.env`, no crash (Pitfall 12).
- [ ] **Correlated picks:** Ballot A warned when two 0-3 picks meet in R1 (Pitfall 14).

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Buchholz / fold formula wrong (1,2,3) | LOW if caught at gate, HIGH if shipped | Backtest catches pre-UI; fix formula or swap to priority-table lookup; re-run gate |
| Epistemic band collapsed (4) | MEDIUM | Move Beta draw to outer loop; if MC loop wasn't built to accept it, partial rewrite — mitigate by structuring the loop in Phase 1 |
| Beta crash on thin market (5) | LOW | Add variance clamp + boundary test; flag clamped matches low-confidence |
| Wrong seed shipped (6) | LOW (re-run) but HIGH if a real ballot was locked on it | Reconcile, re-run, re-evaluate ballot; banner/badge gating prevents reaching lock |
| Streamlit auto-fetch fails on cloud (11) | LOW | Fall back to manual "fetch now"; cache seam means no rewrite |
| Stale cache after lock (13) | LOW | Add `locked` to cache key; clear cache |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1 Buchholz formula | Phase 1 (engine gate) | `test_difficulty_formula` + backtest exact pairings |
| 2 Rematch priority table | Phase 1 (engine gate) | Backtest exact Round 4/5 pairings; `test_forced_rematch_pairing` |
| 3 Fold key = difficulty rank | Phase 1 (engine gate) | Buchholz-reordered-group unit test + backtest |
| 4 Epistemic outer loop | Phase 1 (loop structure) → Phase 5 (wire) | `test_epistemic_band_wider_than_wilson`; band-vs-N probe |
| 5 Beta variance clamp | Phase 5 | `p=0.5,v=0.30` boundary test |
| 6 Seed reconcile | Phase 2 (banner/badge) + README | Reconcile diff before confirm; badge gated on confirm+backtest |
| 7 Ensemble independence | Phase 5 (`pool()`) | Adding soft books must not narrow epistemic band |
| 8 Per-source vig | Phase 5 | `test_devig` + market-passthrough test |
| 9 Series/format conflation | Phase 5 (back-solve) + Phase 1 (override math) | `test_rating_roundtrip` + no-double-Bo3 test |
| 10 numpy reproducibility | Phase 1 (seed scheme) × Phase 2 (chunking) | Same `(seed,N)` identical cross-machine |
| 11 Streamlit scheduler | Phase 5 (read-only cache seam) | App never calls `get_quotes()` on rerun |
| 12 Fail-soft no key | Phase 5 + Phase 2 (zero-config) | Run with env unset → rating-only + banner |
| 13 Cache key incl. locked | Phase 2 + Phase 4 | Locking moves a displayed prob |
| 14 Correlated 0-3 picks | Phase 3 (optimizer) | Ballot B avoids; warning fires on Ballot A |
| 15 Bo1 variance honesty | Phase 2 (CI) + Phase 3 (P≥5) | CI bars visible; P(≥5) headlined |

## Sources

- HANDOFF_claude_code.md §4 (engine), §5 (math), §6 (acceptance tests), §10.5/§10.6 (UI/DX contracts) — eng/design/DX-reviewed spec, primary authority (HIGH)
- PRD_cologne2026_pickem_simulator.md §9 (validation), §10 (risk table), §5 F1 (ensemble) — rationale (HIGH)
- PROJECT.md key-decisions table (Buchholz, epistemic outer loop, Bo3 closed form, backtest gate) (HIGH)
- TODOS.md #1 (cron-fed odds cache / Streamlit-is-not-a-scheduler), #2 (Numba), #3 (backtest gate) (HIGH)
- [Buchholz seeding to be used in PGL Major Swiss stages — HLTV](https://www.hltv.org/news/32621/buchholz-seeding-to-be-used-in-pgl-major-swiss-stages) (MEDIUM — confirms Difficulty Score = opponent strength, high-Buchholz vs low-Buchholz fold, seed tiebreak)
- [The Buchholz system will replace the tie-breaker system — PGL](https://press.pglesports.com/161255-the-buchholz-system-will-replace-the-tie-breaker-system-during-the-challengers-and-legends-stages) (MEDIUM)
- [Valve's Swiss System under the microscope — HLTV](https://www.hltv.org/news/36097/valves-swiss-system-under-the-microscope) (MEDIUM — pairing controversies, group-by-record from R3)
- [Confusing Seeding Just Made Heroic's BLAST Paris Major Run Harder — Waxpeer](https://waxpeer.com/blog/article/confusing-seeding-just-made-heroics-blast-paris-major-run-much-harder) (LOW — anecdote that seeding errors materially change a team's path; motivates Pitfall 6)
- [Parallel random number generation — NumPy Manual](https://numpy.org/doc/stable/reference/random/parallel.html) and [Multithreaded generation](https://numpy.org/doc/stable/reference/random/multithreading.html) (HIGH — SeedSequence.spawn for deterministic parallel streams; reproducibility tied to thread/stream count, Pitfall 10)
- [Best Practices for Using NumPy's Random Number Generators — scientific-python.org](https://blog.scientific-python.org/numpy/numpy-rng/) (MEDIUM)
- [Resolution — Polymarket Documentation](https://docs.polymarket.com/concepts/resolution) and [How Markets Resolve — Start Polymarket](https://startpolymarket.com/learn/how-markets-resolve/) (MEDIUM — UMA 2-hr challenge window, authoritative-source resolution; motivates downweighting near-settlement market quotes)
- Canonical engine source to fetch during Phase 1: `github.com/ValveSoftware/counter-strike_rules_and_regs` → `major-supplemental-rulebook.md` (the literal pairing/priority table — pull verbatim, do not approximate)

---
*Pitfalls research for: CS2 Major Swiss MC simulator + Pick'Em optimizer + odds ensemble*
*Researched: 2026-05-28*
