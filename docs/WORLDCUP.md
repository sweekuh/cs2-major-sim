# World Cup Edge Monitor — private fork

> This repository began as a CS2 Major Swiss Monte-Carlo simulator (see [README.md](../README.md),
> [ROADMAP.md](../ROADMAP.md), [STATUS.md](../STATUS.md) for that lineage). It is being privately
> forked into a **Kalshi 2026 FIFA World Cup edge monitor**. This file is the canonical, durable
> record of that effort — read it first.

**Owner:** Zach (Tachyon Engineering). **Framing:** a personal learning/fun project built with
Claude, **not** a serious capital deployment. Optimize for accuracy, pricing skill, and an honest
scoreboard — not for profit.

---

## 1. Goal and architecture (the "synthesis")

Find — and honestly score — value bets on the 2026 World Cup via Kalshi, using a goals-based
Monte-Carlo as the fair-value engine. The decided architecture:

- A **goals-based Monte Carlo** (Dixon-Coles) is the fair-value engine.
- It is **calibrated to de-vigged sharp 1X2 consensus** (Pinnacle/Betfair via The Odds API) on
  liquid matches, so it *agrees with the market where the market is sharp*.
- It is then **trusted to price the thin/exotic markets** where no clean sharp reference exists
  (exact group order, furthest stage, stage of elimination, Golden Boot) and to flag
  **cross-venue divergence** (Kalshi vs Polymarket). One MC run yields a joint distribution over
  whole tournaments, so it prices *every* derived/correlated market off one sample.
- **CLV vs the sharp close is the truth oracle.** Everything runs paper-only until mean CLV is
  positive and significant. Execution (placing orders) is out of scope and gated behind a legal
  check; v1 is a **read-only monitor + ranked alerts**.

### Decisions locked with the owner
- **Edge source:** independent ratings (Elo/xG prior), calibrated to sharp consensus.
- **Match model:** goals-based Dixon-Coles / bivariate Poisson (needed for draws AND goal
  difference for group tiebreakers).
- **Edge target:** thin/exotic + cross-venue; liquid markets are the calibration + CLV set.
- **Execution:** none in v1 (monitor first); human-in-loop later, automation last.
- **[Q-LEGAL]** California + Kalshi/Polymarket legality is a hard blocker before *any* execution
  — not before the read-only monitor. (See research findings: the liquid global Polymarket book
  is geoblocked for US persons; only Polymarket US / QCEX is lawful, and it is thinner.)

---

## 2. Research verdict (go/no-go) — 2026-06-14

**Build Phase 1 — but as a calibration + CLV learning exercise, not a profit engine.** A 5-angle
deep-research pass (Kalshi efficiency, cross-venue divergence, soccer modeling, calibration, and
competitor tools) reached a clear conclusion. Two load-bearing facts were verified directly (not
just from snippets).

**Why the *profit* thesis is weak:**
- **Liquid markets are efficient.** Prediction-market overround ~100.0–100.5% vs ~102% at
  Pinnacle; top-4 WC favorites price near-identically across venues. Even "tighter than Pinnacle"
  is contested net of fees.
- **Thin/exotic markets are a confirmed fee trap.** Kalshi rounds every fee **up to the cent per
  fill**, so on a contract priced ≤5¢ the fee is **12–50% of stake** (verified vs UCD/GWU working
  papers and a sharp bettor's documented 12.5%-avg fee on a thin longshot). Exotics *are* these
  cheap-longshot contracts. Headline "volume" overstates true money-at-risk ~20×; illiquid spreads
  run 5–10¢ and swamp typical edge.
- **The cross-venue arb is legally blocked for a US resident.** Verified: US persons (CA included)
  may only lawfully use Polymarket US / QCEX; the liquid global Polygon/USDC book is geoblocked
  since the 2022 CFTC settlement, VPN use risks fund seizure, and the two venues can resolve the
  same event on different terms.
- **You don't beat the soccer closing line.** State-of-the-art ML generally fails to outperform
  odds-based predictions; bookmaker odds beat the top Soccer Prediction Challenge entries.

**Why the *learning* thesis is strong:** the synthesis architecture is exactly what Opta's
supercomputer and FiveThirtyEight do (combine market odds with a ratings model, Monte-Carlo the
bracket). Building it teaches Dixon-Coles, calibration-to-market, de-vigging, Monte-Carlo, and CLV
— and the CLV scoreboard tells you the truth cleanly. Worst case, the tool proves there's no edge,
which is itself a correct and valuable result.

### Three research-driven tweaks to fold into Phase 1
1. **Add Shin / power de-vig** alongside the proportional `devig_three_way` — Štrumbelj (2014)
   shows Shin recovers truer probabilities, especially with a heavy favorite (i.e. 1X2).
2. **Sparse national-team fits:** weighted MLE with **exponential time-decay + match-importance
   weights** (down-weight friendlies hard) and **shrinkage toward confederation/global priors**.
   Seed from World Football Elo (beats the FIFA ranking).
3. **Keep CLV-vs-close the headline metric**; run paper-only until CLV is positive and significant.
   Validate the *match* model on a large historical international sample with Brier / log-loss /
   RPS and reliability diagrams (you cannot validate on one tournament). Use fractional Kelly and
   correlation-aware sizing — one tournament means many correlated bets.

Sources are catalogued in the deep-research report (see git history / PR description for the full
cited list). Methodology caveat: sub-agent full-text fetches were blocked (HTTP 403), so dollar
figures rest on search snippets; the two decision-critical facts above were verified directly and
the academic claims (Štrumbelj, Opta, "can't beat the close") are the most trustworthy.

---

## 3. Phase 0 — SHIPPED (truth oracle + match-1X2 monitor foundation)

Read-only, pure, fixture-tested. **37 new tests pass; existing `test_odds.py` and the wider suite
unaffected** (edits to `odds/base.py` and `odds/kalshi.py` are purely additive).

| Area | File(s) | What it does |
|------|---------|--------------|
| 3-way odds core | `odds/base.py` (extended) | `devig_three_way`, `Quote1X2`, `BlendedProb1X2`, `pool_1x2` — the soccer 1X2 analog of the 2-outcome ensemble (the existing `OddsQuote`/`pool` can't carry a draw). |
| Sharp reference | `odds/theoddsapi.py` (new) | `TheOddsApiProvider` — de-vig Pinnacle/Betfair h2h, pre-pool to one sharp opinion per match. Models the OddsPapi provider; httpx lazy-imported in `fetch()` only. |
| Kalshi WC read | `odds/kalshi.py` (extended) | `KalshiWCProvider` + `KalshiMarketState` + `classify_series` — keyless REST reader for WC series, extracts mid/spread/depth. |
| Fee engine | `monitor/fees.py` (new) | Exact Kalshi `ceil(0.07·C·P·(1-P))` taker / `0.0175` maker in integer cents; `net_edge = |fair-mid| - fee - spread/2`. |
| Truth oracle | `monitor/signal_log.py` (new) | sqlite signal store + `compute_clv` + post-settlement CLV backfill + `mean_clv`. |
| Soccer teams | `engine/soccer/teams.py` (new) | `SoccerTeam` (attack/defence/elo/group) + data-driven loader + group bucketing. |
| Data | `data/wc2026_teams.json`, `data/kalshi_wc_tickers.json` | **DRAFT** fixtures — group draw, Elo priors, and series tickers are PLACEHOLDERS to verify against the official FIFA draw and live Kalshi series. |
| Tests | `tests/test_odds_1x2.py`, `test_fees.py`, `test_clv.py`, `test_theoddsapi.py`, `test_kalshi_wc.py`, `test_soccer_teams.py` | Fixture-driven, no httpx in the import path. |

**Known Phase-0 gaps / caveats**
- `data/wc2026_teams.json` and `data/kalshi_wc_tickers.json` are **DRAFT placeholders** — verify
  the real 2026 group draw, Elo priors, and live Kalshi series tickers before trusting output.
- No live wiring yet: `fetch()` methods exist but haven't been run against live endpoints; the
  Kalshi WebSocket client and the pipeline orchestrator are not built.
- `devig_three_way` is proportional only (Shin/power is a Phase-1 tweak).

---

## 4. Phase 1 — NEXT (goals model + calibration + tournament sim)

Build the fair-value engine, with the three research tweaks baked in. Target package
`engine/soccer/`:

- `dixon_coles.py` — bivariate-Poisson match model: `expected_goals`, `scoreline_matrix`
  (with the Dixon-Coles low-score `τ`/`ρ` correction), `outcome_1x2` (closed form), `sample_score`
  (the per-match draw).
- `calibrate.py` — fit `(attack, defence, home_adv)` to de-vigged sharp 1X2. Reuse the
  Gauss-Newton + gauge-anchor + Levenberg pattern from `engine/backsolve.py:95-131`, but the
  residual is a 3-vector per match and there are two params/team. Add time-decay + match-importance
  weighting and shrinkage priors (tweak #2).
- `group_stage.py` — 12-group round-robin + FIFA tiebreakers (points → GD → GF → head-to-head
  mini-table → fair play → drawing of lots; the last consumes rng). Must simulate scorelines, not
  just W/D/L.
- `tournament.py` — reuse the `run_mc_progressive` harness shape (chunked `SeedSequence` RNG +
  epistemic outer loop from `engine/probs.py`'s `epistemic_draws`/`beta_moment_fit`), but define a
  soccer-shaped `Result.sample` per sim: `{group_rank, stage_reached, eliminated_in, champion,
  group_order, top_scorer}`.
- `markets.py` — price each Kalshi market type off the sample (`p_champion`, `p_group_winner`,
  `p_advance`, `p_exact_group_order`, `p_furthest_stage`, `p_stage_of_elimination`, `p_golden_boot`,
  and closed-form `p_match_1x2`).
- Add **Shin/power de-vig** to `odds/base.py` (tweak #1).
- Tests: `test_dixon_coles.py`, `test_calibrate_recovery.py` (build known model → recover
  gauge-invariant strength differences, mirror `test_backsolve.py::test_rating_roundtrip`),
  `test_group_tiebreakers.py`.

Later phases (P2: exotic pricing + Kalshi WebSocket + cross-venue + ranking/alerting; P3: knockout
bracket; execution gated behind [Q-LEGAL]) — see the architecture in §1 and the original plan.

---

## 5. Reuse map (existing repo assets)

- **Reuse/extend:** `odds/base.py` (ensemble core), `engine/backsolve.py` (calibration pattern),
  `engine/montecarlo.py` (chunked-RNG + epistemic harness + retained `sample`), `engine/probs.py`
  (`epistemic_draws` + `beta_moment_fit` only), `odds/kalshi.py` (REST paging skeleton),
  `odds/oddspapi.py` (provider template), `odds/_match.py` (name→id).
- **Replace (CS2-specific, fights soccer):** `engine/swiss.py`, `engine/probs.py` win/Bo3 math,
  `engine/teams.py` (16-seed Swiss), `engine/seeding.py`, `optimizer.py`, `live.py`, `qualifyfit.py`.
- **OSS to study:** [`ryanfrigo/kalshi-ai-trading-bot`](https://github.com/ryanfrigo/kalshi-ai-trading-bot)
  (RSA-PSS auth, Kelly/drawdown, paper-trade→SQLite loop), [`ImMike/polymarket-arbitrage`](https://github.com/ImMike/polymarket-arbitrage)
  (fee-aware edge math), [`ArshKA/kalshi-client`](https://github.com/aarora4/Awesome-Prediction-Market-Tools)
  (clean wrapper with local orderbook). Kalshi trading auth = RSA-PSS request signing.

---

## 6. Running / verifying

```bash
# Phase-0 tests (fast, pure, no network)
uv run python -m pytest tests/test_odds_1x2.py tests/test_fees.py tests/test_clv.py \
  tests/test_theoddsapi.py tests/test_kalshi_wc.py tests/test_soccer_teams.py -q

# Full suite (confirm no regression in the inherited CS2 engine)
uv run python -m pytest -q
```

Live reads (Phase-1+, once endpoints verified): `TheOddsApiProvider().fetch(...)` needs an
Odds API key; `KalshiWCProvider().fetch(series_tickers=[...])` is keyless. Confirm **[Q-FEES]**
(soccer taker coefficient = 0.07, no category override) against the live fee schedule before
trusting `net_edge` for any real-money decision.
