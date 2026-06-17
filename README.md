# swiss-mc — IEM Cologne 2026 Swiss Monte Carlo & Pick'Em Optimizer

Monte-Carlo simulates the IEM Cologne Major 2026 CS2 Swiss stage and gives you honest per-team
odds, market-anchored ratings, and the math-optimal Pick'Em ballot. The point isn't a pretty
dashboard, it's a **correct** one: every probability is validated against the Valve rulebook and
a real past-Major backtest, and the uncertainty is shown, not hidden.

No scraping. APIs only. Single local user. Python + numpy + Streamlit.

![Recommended Pick'Em ballot](docs/assets/ballot.png)
![Per-team probabilities with two-tone CI bands](docs/assets/table.png)

## Quickstart

```bash
uv run streamlit run app.py
```

`uv` auto-creates the env and installs everything from `pyproject.toml` (~45s cold), same command
on Windows, Mac, and Linux. No `uv`? `pip install streamlit numpy && streamlit run app.py`.

**The first sim needs no API key and no editing.** Click **Run ▶** with the shipped defaults and
watch ~100k Swiss tournaments resolve in ~15 seconds (rating-only). Add odds (below) to make it
market-driven.

## What the numbers mean

- **P(3-0) / P(advance) / P(0-3)** — each team's chance of going 3-0, of qualifying (3 wins
  before 3 losses), and of crashing out 0-3. The per-team "P(advance)" column is the genuine
  "does this team make it through" stat.
- **Two-tone CI bars** — under each number. The **solid** inner band is sampling noise (Wilson
  interval); the **faint** outer band is *extra* width from the odds sources disagreeing
  (epistemic uncertainty). A wide faint band means the books don't agree yet. It is honest
  uncertainty, not false precision.
- **The Pick'Em coin (2/6/2)** — you pick 2 teams to go 3-0, 6 to advance, 2 to go 0-3; **≥5 of
  10 correct** upgrades the coin, so the headline number is **P(≥5/10)**, the true coin odds.
  - Subtle but load-bearing: an **advance** pick scores only on an exact **3-1 or 3-2** finish.
    A 3-0 satisfies the 3-0 bucket, never the advance bucket. Getting this wrong inflates the
    coin odds by ~30 points (it's why a naive model reads ~90% when the honest number is ~59%).
- **Two ballots** — **A** maximizes E[correct] (greedy); **B** maximizes P(≥5) (a hill-climb that
  re-buckets to dodge correlated picks, e.g. two 0-3 picks that meet in Round 1 and can't both
  hit). On a clear field they agree; they diverge when there's correlation to exploit.

## How it works

```
seeds + ratings ──► Swiss engine ──► Monte Carlo ──► optimizer ──► ballot + P(≥5)
   (data/            (pairing,        (N sims,         (2/6/2,
    stage1.json)      Buchholz,        Wilson CI,       3-1/3-2 scoring,
                      rematch table)   epistemic loop)  P(≥5) hill-climb)
        ▲
        │  back-solved from market odds
        │
   odds ensemble ◄── OddsPapi (Pinnacle, de-vigged) + Kalshi (KXCS2GAME)
   (log-opinion pool, per-source variance → the faint band)
```

- **Engine:** round-by-round Swiss pairing with Buchholz difficulty (`Σ opp.wins − opp.losses`),
  the Valve 15-row rematch-avoidance table, and Bo3 as a closed-form `p²(3−2p)` draw.
- **Odds ensemble:** OddsPapi gives Pinnacle (the sharp book) de-vigged two-way; Kalshi gives a
  keyless prediction-market price. Both are pooled with a weighted **log-opinion pool**; their
  disagreement becomes the epistemic variance that widens the faint CI band. Market series
  probabilities are **back-solved into per-team ratings** so the whole bracket is market-anchored.
- **APIs only, fail-soft:** missing key → it degrades (OddsPapi needs a key; Kalshi is keyless)
  down to rating-only with an honest banner, never a crash. Keys live in a gitignored `.env`,
  never in the app process, and are never logged.
- **Full Major (v3):** the stage selector runs Stages 1–3 through the same validated engine —
  Stage 3 is all-Bo3 — and a fully-locked, complete stage auto-derives the next stage's seeds
  (invited 1-8 by VRS, advancers 9-16 by final Buchholz) as an editable [INFERRED] overlay.
  Odds/results caches are stage-stamped, and the app refuses a cache fetched for another stage
  (the same engine id names a different team on each stage).

## Correctness is the product

- **Backtest gate:** the engine reproduces StarLadder Budapest 2025 Stage 1's actual R1–R5
  pairings exactly (`tests/test_backtest_budapest_2025.py`). If that ever goes red, the pairing
  logic is broken. Seeds for the backtest come from the authoritative Valve VRS snapshot.
- **268 passing tests**, including regression guards that *distinguish the right rule from the
  wrong one* (a test that still passes when you revert the fix is theater, not a guard).
- **Cologne seeds confirmed:** the seed order is verified against Liquipedia + the live Kalshi
  bracket + the R1 pairing rule, so the trust badge reads *validated*, not *inferred*.

Two real probability bugs were caught and fixed during the live-odds work (a 12× normalization
inflation and the advance-pick scoring rule above). The full story is in
**[docs/LESSONS.md](docs/LESSONS.md)** — worth reading if you care about how subtle simulation
math goes wrong.

## Predictions & results — per stage

Predictions for **all four stages**, graded against what actually happened. These are a model's
odds, not a guarantee — and we grade ourselves honestly (an honest dashboard is the whole point).

**How to read these.** The Stage-1/2 tables are the engine on the committed fixture priors
(rating-only, 200k sims, `seed=20260617` — reproducible: `uv run python -m engine ...`), so the
"prediction" is exactly what the shipped priors imply. The Stage-3 block keeps the **live-market
call-my-shot** that was actually published *ahead* of the stage (its provenance is in the caption).
**✓** = the team actually advanced; the model's "pick" is its top-8 by P(advance). Calibration is
cited per stage from `python -m scripts.score_stage` and the Budapest 2025 backtest gate.

### Stage 1 — 16→8, settled · model top-8 **6/8**

The eight predicted advancers (top-8 by P(advance)) and whether they made it:

| # | Predicted to advance | P(advance) | Result |
|--:|---|---:|:--:|
| 1 | GamerLegion | 99.8% | ✓ |
| 2 | B8 | 97.2% | ✓ |
| 3 | BetBoom | 92.4% | ✓ |
| 4 | MIBR | 86.8% | ✓ |
| 5 | M80 | 66.2% | ✓ |
| 6 | HEROIC | 62.0% | — |
| 7 | Liquid | 53.0% | — |
| 8 | BIG | 50.1% | ✓ |

Missed: HEROIC, Liquid. Bubble surprises that advanced: **TYLOO** (model 27.7%), **FlyQuest**
(8.4%). History: the live 2/6/2 Pick'Em scored **5/10** (coin hit; predicted P(≥5)≈59%), with the
one instructive miss being the **B8 *advance* pick failing because B8 went 3-0** — an advance pick
scores only on a 3-1/3-2 finish (the rule above). Match-level calibration over the 33 real matches:
**log-loss 0.5785 vs 0.6931 coinflip, 24/33 (73%) favorites, S=40 the sweep argmin**. Pairing logic
is backtest-gated exact vs StarLadder Budapest 2025.

### Stage 2 — 16→8, settled · model top-8 **6/8**

| # | Predicted to advance | P(advance) | Result |
|--:|---|---:|:--:|
| 1 | GamerLegion | 95.4% | — |
| 2 | Spirit | 95.2% | ✓ |
| 3 | Legacy | 87.9% | ✓ |
| 4 | Astralis | 78.3% | — |
| 5 | B8 | 74.0% | ✓ |
| 6 | FUT Esports | 73.5% | ✓ |
| 7 | G2 | 59.6% | ✓ |
| 8 | BetBoom | 51.8% | ✓ |

Missed: GamerLegion, Astralis. Bubble surprises that advanced: **9z** (model 38.2%), **Monte**
(23.0%). The two misses are the classic Swiss bubble: both were >75% to advance and both lost the
3-2 / 2-3 coinflips.

### Stage 3 — 16→8 (playoff qualifiers), all-Bo3, settled · live-market call **5/8**

Snapshot 2026-06-10 02:07 UTC, published *ahead* of Stage 3 (June 11–15, every match Bo3), from
**live Kalshi markets**: the eight KXCS2GAME R1 series prices (priced directly in-sim) plus the
sixteen KXCS2QUALIFIERS playoff-qualify mids — back-solved into rounds-2-5 ratings by the qualify
fit (converged, max err 0.7%) — over 200k sims. Single-provider, so no epistemic band. **✓** = the
team actually reached the playoffs.

| Team | P(advance) | P(3-0) | P(0-3) | Result |
|---|---:|---:|---:|:--:|
| Vitality | 94.7% | 51.5% | 0.4% | ✓ |
| Falcons | 89.8% | 36.2% | 0.8% | ✓ |
| Spirit | 82.4% | 20.9% | 2.3% | ✓ |
| Natus Vincere | 81.3% | 21.9% | 2.3% | — |
| FURIA | 65.9% | 15.4% | 3.4% | ✓ |
| Aurora | 59.3% | 13.2% | 4.4% | ✓ |
| MOUZ | 54.8% | 9.1% | 6.4% | — |
| PARIVISION | 43.0% | 7.2% | 8.8% | — |
| The MongolZ | 42.0% | 6.7% | 9.0% | — |
| G2 | 41.8% | 4.4% | 13.9% | ✓ |
| FUT Esports | 38.7% | 3.6% | 14.6% | — |
| BetBoom | 31.9% | 3.7% | 14.9% | ✓ |
| Legacy | 31.2% | 2.7% | 19.9% | — |
| 9z | 23.5% | 2.2% | 20.5% | ✓ |
| B8 | 10.1% | 0.6% | 40.1% | — |
| Monte | 9.8% | 0.6% | 38.3% | — |

The chalk held at the top (all five of the model's favorites — Vitality, Falcons, Spirit, FURIA,
Aurora — went through), but the **3-2 bubble was chaos**: G2 (41.8%), BetBoom (31.9%) and 9z
(23.5%) all squeaked in over NaVi, MOUZ and PARIVISION. Rating-only priors land the same **5/8**.
That bubble noise is exactly why the playoff title race is anchored to the market, not to priors.

### Playoffs — 8-team single-elim bracket, **live (pending)**

Champion odds, **live-market-anchored** (Polymarket ~$21M + Kalshi `KXCS2-IEMCOL26`, read
2026-06-16; the bracket sim is fit so P(champion) reproduces this book through the real draw —
`scripts/fit_champion.py`), 200k sims:

| Team | P(champion) | P(reach SF) | Quarterfinal |
|---|---:|---:|---|
| Vitality | 44.8% | 74.8% | vs Falcons |
| Spirit | 29.6% | 78.6% | vs G2 |
| FURIA | 9.4% | 69.8% | vs 9z |
| Falcons | 7.2% | 25.2% | vs Vitality |
| Aurora | 3.9% | 56.6% | vs BetBoom |
| G2 | 2.0% | 21.4% | vs Spirit |
| BetBoom | 2.0% | 43.4% | vs Aurora |
| 9z | 1.1% | 30.2% | vs FURIA |

**Path beats raw strength here:** FURIA's title odds (9.4%) outrank Falcons' (7.2%) despite a
*lower* rating (70.0 vs 73.9) — FURIA draws 9z in its quarterfinal while Falcons must beat Vitality.
Quarterfinals are June 18–19 (Bo3), the grand final June 21 (Bo5) — **result pending.** Now that
playoff per-match odds are wired (below), fetching `--stage playoffs` anchors the bracket's known
QF/SF lines to the live series markets too, on top of the champion-futures fit.

## Live odds setup (optional)

```bash
cp .env.example .env        # then add ODDSPAPI_KEY (Kalshi needs no key)
```

In the app, click **Fetch odds now**. It pulls OddsPapi + Kalshi, writes a read-only
`data/odds_cache.json`, and the next Run is market-driven (two-tone bands light up). Missing key →
rating-only, no crash. Note: odds-fed runs do K=12 epistemic draws, so they take ~12× longer than
rating-only at the same N.

## Honest caveats

- It's a **model, not an oracle.** R1 is anchored to live market prices; rounds 2–5 are projected
  from back-solved ratings, so deeper-round numbers are softer than R1.
- Practical N is ~100k–200k: the engine retains the full per-sim sample for the optimizer, so
  memory grows with K·N (a 1M odds-fed run needs ~11 GB). Probabilities are converged well before
  that, so this is a non-issue in practice, just don't crank N to 1M.
- The **playoffs** are built (v4): the 8-team single-elim bracket is simulated end-to-end on the
  real Stage-3 finish, with a 7-pick round-weighted Pick'Em optimizer (4 QF + 2 SF + 1 champion).
  The bracket ratings are **live-champion-market-calibrated** (`scripts/fit_champion.py` fits them so
  P(champion) reproduces the tournament-winner book), and **playoff per-match odds are now wired**: a
  `--stage playoffs` odds cache prices the known QF/SF series lines directly while the champion-fit
  ratings drive the unpriced later rounds (the same orthogonality as the Swiss qualify-fit). With no
  line posted it falls back to the champion-fit ratings, byte-identical. The Pick'Em point weights /
  achievement tiers are [INFERRED] editable defaults. See `STATUS.md`.

## Project layout

```
app.py              Streamlit UI (controls, run, two-tone bars, ballot, live mode)
engine/             pure compute core (no streamlit/httpx)
  swiss.py            round-by-round pairing + Buchholz + rematch table
  montecarlo.py       MC runner, Wilson CI, epistemic outer loop
  probs.py            Bo3/Bo5 closed-form, epistemic Beta draws, variance clamp
  optimizer.py        2/6/2 ballot, 3-1/3-2 scoring, P(≥5) hill-climb
  bracket.py          playoff single-elim sim + bracket MC (Bo3 QF/SF, Bo5 final)
  playoff_optimizer.py  7-pick round-weighted ballot (4 QF + 2 SF + 1 champion)
  seeding.py          inter-stage seed chain + seed_playoffs (bracket seeds)
  backsolve.py        market series probs → per-team ratings
  live.py             conditional re-sim + pick status (live/dead/secured)
odds/               OddsPapi + Kalshi parsers, de-vig, log-opinion pool (pure numpy)
scripts/            fetch_odds + fetch_results — the ONLY provider contact; both take --stage
                    and stamp _meta.stage so a cache can never feed the wrong stage's run
  fit_qualify.py      offline qualify-market calibration → fitted_ratings in the odds cache
  score_stage.py      post-stage calibration audit (log-loss/Brier/fav-acc + S-sweep)
tests/              268 tests incl. the Budapest backtest gate + real-data seeding gates
                    + playoff bracket / 7-pick optimizer / seed_playoffs / market-overrides gates
docs/LESSONS.md     what we learned and would do differently
ROADMAP.md          shipped vs next   ·   STATUS.md  current state
CHANGELOG.md        release history (v1.0 → v4.0), per the git tags
```

## Stack

Python ≥3.12 · numpy 2.4 · Streamlit 1.57 · httpx (odds only) · python-dotenv · `uv`. No pandas,
no scipy. Planned and built with a phased, test-gated workflow (see `ROADMAP.md` / `STATUS.md`).

## Event-day cold-start drill (30 seconds)

1. `git pull` — latest engine + rating tweaks.
2. **Fetch odds now** (if markets are posted) to price the sim from live markets.
3. Confirm the seeds against the reconcile table; flip **"seeds confirmed."**
4. Click **Run ▶**. First sim needs no API key.
