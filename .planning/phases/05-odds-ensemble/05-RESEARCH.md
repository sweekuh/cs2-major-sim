# Phase 5 Research — Odds Ensemble

Phase: 05-odds-ensemble
Researched: 2026-05-29
Domain: market-odds ingestion + de-vig/log-opinion pooling + logistic ratings back-solve + epistemic outer loop + read-only cache seam
Confidence: HIGH on the code seams (read verbatim) / HIGH on the math (in CLAUDE.md + probs.py stubs) / MEDIUM-LOW on live provider response shapes (single-source docs, no live markets) — those are explicitly [DEFERRED — verify once Cologne markets post]
Requirements: ODDS-01, ODDS-02, ODDS-03, ODDS-04, ODDS-05, ODDS-06, ODDS-07, ODDS-08
Depends on: Phase 1 (`engine/probs.py` `series_prob` odds-override + `epistemic_draws` outer-loop stub + `beta_moment_fit`; `engine/montecarlo.py` outer loop already wraps the chunk loop; `simulate_stage(teams, ratings, ...)` ratings-override seam) · Phase 2 (`ui/state.py` `odds_key_present()` + `ODDS_KEY_ENV`; `app.py:152` fail-soft banner; `data/stage1.json` read pattern; `freeze_ratings`→`run_mc_cached`) · Phases 3/4 proven (no change)
Sources: `files/HANDOFF_claude_code.md` §5 (math, lines 146-175), §8 (odds layer, lines 241-264), §1 (repo layout `odds/`, lines 24-28) · `.planning/ROADMAP.md` Phase 5 (lines 119-137) · `.planning/REQUIREMENTS.md` ODDS-01..08 (lines 93-100), OPS-01 (line 145) · `CLAUDE.md` non-negotiables · `TODOS.md` #1 (cron seam) · `engine/probs.py` (`series_prob:42`, `epistemic_draws:74`, `beta_moment_fit:92`, `difficulty:64`, `p_map:23`, `series:32`) · `engine/montecarlo.py` (`run_mc_progressive:123` OUTER loop lines 161-194, `blend/var:164-165`) · `engine/swiss.py` (`_play:202` ratings lines 224-226, `simulate_stage:232`) · `ui/state.py` (`odds_key_present:138`, `ODDS_KEY_ENV:103`) · `ui/cache.py` (`freeze_ratings:38`, `run_mc_cached:47`) · `app.py` (banner `:152`, `_run_or_serve:377`, `ratings` build `:391`) · OddsPapi/Polymarket/Kalshi public API docs (cited inline, MEDIUM)

---

## What this phase is

A **fail-soft enhancement layer** that bolts onto an engine whose every seam was already
cut for it in Phase 1. Phase 5 does NOT modify the engine's hot path — it **fills three
structured stubs** and adds two new packages (`odds/`, `scripts/`):

1. `engine/probs.py:epistemic_draws` (line 74) currently `yield list(blend)` — one no-op
   point draw. Phase 5 fills it with K Beta draws via the already-present
   `beta_moment_fit` (line 92, **the clamp is already correct** — verified below).
2. `engine/probs.py:series_prob` (line 42) already short-circuits on a `market_series_prob`
   override and does NOT re-apply Bo3 (PROB-02). Phase 5 supplies that value from the cache.
3. `simulate_stage(teams, ratings, ...)` (swiss.py:232) + `run_mc_progressive(..., ratings, ...)`
   (montecarlo.py:123) already accept a `ratings: {id: rating}` override. Phase 5's back-solve
   produces that dict.

**The headline discovery (verified by reading the code, not assumed):** the outer epistemic
loop is ALREADY wired in the shipped hot path. `run_mc_progressive` wraps the entire chunk
loop in `for _p_vec in epistemic_draws(blend, var):` (montecarlo.py:166), with `blend`/`var`
single-source placeholders at lines 164-165. Phase 1's note (ROADMAP line 61, "if the loop
isn't structured outer here, Phase 5 is a rewrite") is **honored** — Phase 5 is additive, not
a rewrite. The one architectural decision Phase 5 must make is **how `_p_vec` feeds the inner
sim** (it is currently discarded as `_p_vec`) — see D5/Risk "outer-loop wiring".

Everything else is **new, pure, TDD-able modules** (`odds/base.py`, `odds/oddspapi.py`,
`odds/polymarket.py`, `odds/kalshi.py`, `engine/backsolve.py`) plus **one I/O script**
(`scripts/fetch_odds.py`) and a **thin UI slice** (a "fetch now" button + a read-only cache
loader). The app NEVER imports `odds/` providers or `scripts/fetch_odds.py` — it only reads
`data/odds_cache.json` (ODDS-07, Pitfall 11).

**Why it's last and why it never gates:** rating-only mode is fully functional (Phases 1-4
shipped, 85 tests green). Odds are an enhancement. With no key — and even on any network/parse
failure — the app must behave EXACTLY as today: rating-only + the existing banner
(`app.py:152`). The `odds_cache.json` is **read-only and optional**; its absence is the normal
first-run state.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary | Rationale |
|------------|-------------|-----------|-----------|
| Provider HTTP fetch (httpx) | `scripts/fetch_odds.py` (offline job) | `odds/*.py` providers | NEVER in the Streamlit process (Pitfall 11); cron drop-in (ODDS-07/OPS-01) |
| Per-source de-vig / price normalize | `odds/base.py` + per-provider `odds/*.py` | — | pure, TDD-able, no I/O — same functional-core rule as `engine/probs.py` |
| Log-opinion pool + cross-source variance | `odds/base.py:pool()` | — | pure reduce over quotes; one opinion per originate-source |
| Ratings back-solve (series→map→logistic fit) | `engine/backsolve.py` (new, pure) | `engine/probs.py` (invert `series`) | numpy-only Gauss-Newton; no scipy (stack constraint) |
| Epistemic Beta outer loop | `engine/probs.py:epistemic_draws` (fill stub) + `engine/montecarlo.py` (wire `_p_vec`) | `beta_moment_fit` (exists) | OUTER loop already structured; fill content only |
| Odds → series-prob override into a sim | `engine/probs.py:series_prob` (exists) + `simulate_stage` plumbing | — | market series prob used directly, Bo3 NOT re-applied (PROB-02) |
| Read-only cache contract | `data/odds_cache.json` (written by script, read by app) | `ui/odds_loader.py` (new, read-only) | app only reads; cron + button write the same file (ODDS-07) |
| Fail-soft / banner | `ui/state.py:odds_key_present` (exists) + `app.py:152` (exists) | — | preserve verbatim; extend to "cache present?" not "key present?" |

---

## The format facts (load-bearing — getting any wrong silently corrupts the thin-liquidity matches that matter most)

- **De-vig ROUTES on `vig_type`** (Pitfall 8, CLAUDE.md). `OddsPapi` quotes are `vig_type="fixed"`
  → two-way overround de-vig `p_a = (1/o_a)/(1/o_a + 1/o_b)` (HANDOFF §5 line 154). `Polymarket`
  and `Kalshi` are `vig_type="market"` → the price already IS ≈ a probability; remove only the
  spread/fee and downweight thin markets. **Applying fixed-odds two-way de-vig to a market price
  is a silent corruption** — there is no second outcome's decimal odds to normalize against.
- **The OddsPapi bundle is ~ONE sharp opinion, not N sources** (Pitfall 7, CLAUDE.md). One
  `/odds` call returns Pinnacle + Thunderpick + GG.BET + Betway etc. They are soft books copying
  Pinnacle's line — heavily correlated. Pool them into a **single OddsPapi opinion (Pinnacle-anchored)**
  BEFORE the cross-provider pool, or headcount-weighting drowns the two genuinely-independent
  sources (Polymarket, Kalshi). Weight by **originate-vs-copy and liquidity, NEVER headcount**
  (ODDS-03).
- **Invert series→map BEFORE fitting ratings** (Pitfall 9, CLAUDE.md). A market series prob is for
  a SPECIFIC format (Bo1 or Bo3). Identity for Bo1; **invert `p²(3−2p)` for Bo3** to recover the
  per-map `p`, THEN logistic-least-squares fit ratings to the map-level probs. Fitting ratings to
  series probs conflates Bo1 and Bo3 so one rating can't price both unplayed branches.
- **Epistemic variance is an OUTER loop, NEVER folded into per-sim sampling** (PROB-03/04,
  CLAUDE.md, Pitfall 4). Source disagreement is *epistemic* — it does NOT shrink with N. The Beta
  draw lives in `epistemic_draws` (the OUTER loop), one draw per outer iteration; the inner MC
  runs aleatoric coin-flips against that drawn p-vector. Burying the Beta draw inside per-sim
  sampling makes the reported band falsely tight at large N (defeats G4).
- **Clamp `variance < p(1−p)` BEFORE the Beta moment fit** (Pitfall 5, CLAUDE.md). At/above the
  max-variance bound `mean·(1−mean)`, the method-of-moments Beta params go non-positive and
  `rng.beta` crashes — on exactly the low-liquidity, high-disagreement matches that matter most.
  **VERIFIED ALREADY DONE:** `beta_moment_fit` (probs.py:92-116) clamps `mean` into `(eps, 1-eps)`
  AND `v = min(var, bound*(1-eps))` with `v = max(v, eps*bound)`. Phase 5 must CALL it, not
  re-implement the clamp.
- **APIs only, no scraping; missing key → rating-only + banner, never a crash** (CLAUDE.md). First
  run needs no API key. **NEW verified fact (lowers risk):** Polymarket and Kalshi public market
  data require **NO authentication** ([CITED: docs.polymarket.com/market-data/overview],
  [CITED: docs.kalshi.com]); only OddsPapi needs a key. So "no key" disables only the OddsPapi
  anchor — the two prediction markets can still populate the cache. The fail-soft contract is
  about the **cache file's presence**, not the key's.
- **The app NEVER calls `get_quotes()` on a rerun** (Pitfall 11, ODDS-07). The button shells out
  to / imports-and-calls the SAME `scripts/fetch_odds.py` the cron will call; both write the SAME
  read-only `data/odds_cache.json`; the app's render path only ever READS that file.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why standard |
|---------|---------|---------|--------------|
| `httpx` | 0.28.x | provider REST calls in `scripts/fetch_odds.py` ONLY | CLAUDE.md-mandated odds client; sync API is enough for a batch job; already named in the stack |
| `python-dotenv` | 1.0.x | load `.env` in the FETCH SCRIPT ONLY (never in `ui/state.py`) | CLAUDE.md stack; keeps keys out of the app process (Pitfall 11) |
| `numpy` | 2.4.6 | back-solve Gauss-Newton/IRLS, Beta draws, vectorized pool | already pinned; no scipy (stack constraint) — hand-roll the fit |

**Verification (run before writing the install task):**
```bash
pip index versions httpx          # confirm 0.28.x current
pip index versions python-dotenv  # confirm 1.0.x current
```
[VERIFIED: numpy 2.4.6 already pinned per STATE.md line 77]. `httpx`/`python-dotenv` versions
are [ASSUMED] from training — the planner must `pip index versions` them in a Wave-0 task.

### NOT in scope (stack guardrails)
- **No scipy** — the logistic least-squares fit is hand-rolled Gauss-Newton (D4). scipy.optimize
  is the obvious tool and is explicitly forbidden by the stack constraint.
- **No pandas** — cache is plain JSON dicts; the app reads with `json.loads`.
- **httpx/dotenv must NOT be imported by `ui/state.py` or `app.py`** — `odds_key_present` already
  uses `os.environ` only (state.py:141, verified) to preserve the zero-config first run. Phase 5
  must NOT regress this (a stray `import httpx` at app top-level breaks DX-01).

---

## Package Legitimacy Audit

slopcheck unavailable in this web session (no pip network for it). All packages are
**well-known, already-named in CLAUDE.md's stack** — but per the package-provenance rule the
planner must still verify on PyPI before the install task.

| Package | Registry | Provenance | Disposition |
|---------|----------|-----------|-------------|
| `httpx` | PyPI | named in CLAUDE.md stack; verify `pip index versions httpx` | Approved — planner adds a Wave-0 `pip index versions` gate |
| `python-dotenv` | PyPI | named in CLAUDE.md stack; verify `pip index versions python-dotenv` | Approved — same gate |
| `numpy` | PyPI | already pinned 2.4.6 (STATE.md) | Approved (in tree) |

No new exotic packages. **Packages removed:** none. **Flagged suspicious:** none. The planner
should gate the two new installs behind a single Wave-0 `pip index versions` confirmation task
(they are mainstream, so a `checkpoint:human-verify` is not warranted — a version-confirm task is).

---

## Architecture Patterns

### System data flow

```
                        ┌─────────────────── OFFLINE (never in Streamlit) ──────────────────┐
  cron (v2, OPS-01) ───►│                                                                    │
       OR               │  scripts/fetch_odds.py                                             │
  "fetch now" button ──►│    ├─ load .env (python-dotenv)                                    │
                        │    ├─ discover_fixtures(teams)  ── dynamic slug/ticker match ──┐   │
                        │    ├─ OddsPapiProvider.get_quotes(fixtures)  (httpx, needs key)│   │
                        │    ├─ PolymarketProvider.get_quotes(...)     (httpx, NO key)   │   │
                        │    ├─ KalshiProvider.get_quotes(...)         (httpx, NO key)   │   │
                        │    │         └─ each → list[OddsQuote] (de-vig per vig_type)    │   │
                        │    ├─ pool(quotes) ─► {matchkey: BlendedProb(p, var, n_sources)}│   │
                        │    └─ json.dump(cache)  ──► data/odds_cache.json  (read-only)   │   │
                        └────────────────────────────────────────────────────────────────┘   │
                                                          │ FILE on disk (the seam)            │
  ┌──────────────────────────── STREAMLIT APP (read-only) ─────────────────────────────────┐  │
  │ ui/odds_loader.load_odds_cache()  ── json.loads, fail-soft → None on any error ──┐      │  │
  │                                                                                  ▼      │  │
  │ engine.backsolve.fit_ratings(blended_known_matches, teams)                              │  │
  │    series→map invert (probs.series inverse) → logistic Gauss-Newton → {id: rating}      │  │
  │                                                                                         │  │
  │ run_mc_progressive(teams, ratings=back_solved, S, N, locked,  blend, var FROM cache)    │  │
  │    OUTER: for p_vec in epistemic_draws(blend, var):   ◄── K Beta draws (was 1 no-op)    │  │
  │      INNER: chunks × sims  → simulate_stage(... market overrides for imminent round)     │  │
  │    aggregate ACROSS draws → epistemic band ⊇ Wilson, does NOT shrink with N             │  │
  └─────────────────────────────────────────────────────────────────────────────────────────┘
```

### Recommended new files
```
odds/
  __init__.py
  base.py          # OddsQuote, BlendedProb, OddsProvider Protocol, de-vig helpers, pool()
  oddspapi.py      # OddsPapiProvider (httpx, Pinnacle anchor; needs ODDSPAPI_KEY)
  polymarket.py    # PolymarketProvider (httpx, Gamma API, NO auth)
  kalshi.py        # KalshiProvider (httpx, trade-api v2 public, NO auth)
engine/
  backsolve.py     # series→map invert + logistic Gauss-Newton ratings fit (numpy, no scipy)
scripts/
  fetch_odds.py    # the ONE entry both the button AND the v2 cron call; writes the cache
ui/
  odds_loader.py   # read-only cache loader (json.loads, fail-soft); NO httpx/dotenv import
tests/
  test_odds.py     # de-vig, pool, provider parse (against recorded fixtures)
  test_backsolve.py# series→map invert + rating roundtrip (test_rating_roundtrip, HANDOFF §6)
  test_epistemic.py# test_epistemic_band_wider_than_wilson (HANDOFF §6)
data/
  odds_cache.json  # NOT shipped (gitignored or absent on first run); written by fetch_odds.py
  fixtures/        # recorded provider JSON samples for offline parse tests
```

### Pattern 1 — `OddsQuote` / `BlendedProb` / `OddsProvider` (ODDS-01)

The HANDOFF §8 (lines 244-256) gives the canonical shape. Refine it to carry what the pool
and back-solve need (a stable match key, both sides' de-vigged probs, originate-vs-copy, bo3):

```python
# odds/base.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class OddsQuote:
    provider: str                 # "oddspapi:pinnacle", "polymarket", "kalshi"
    match: tuple[int, int]        # (team_id_a, team_id_b) — resolved to ENGINE ids, sorted
    p_a_raw: float                # de-vigged P(a wins the SERIES), per this source
    vig_type: str                 # "fixed" | "market"
    bo3: bool                     # series format this quote prices (for the back-solve invert)
    liquidity: float              # volume/handle proxy; 0.0 if unknown
    originate: float              # 1.0 = sharp originator (Pinnacle/independent market), <1 = copy
    ts: float                     # unix fetch time

@dataclass(frozen=True)
class BlendedProb:
    p: float                      # pooled series P(a wins) in (0,1)
    var: float                    # cross-source variance (epistemic), CLAMPED < p(1-p) downstream
    n_sources: int                # count of INDEPENDENT opinions (OddsPapi bundle == 1)
    bo3: bool

class OddsProvider(Protocol):
    def get_quotes(self, fixtures: list[Fixture]) -> list[OddsQuote]: ...
```

`match` is keyed on **engine team ids** (not provider strings) — the providers map their team
strings to ids via a fuzzy/alias table in `discover_fixtures` (D6), so the pool and back-solve
never touch provider name spelling. The cache JSON stores `match` as a sorted `"a-b"` string key.

### Pattern 2 — de-vig routed on `vig_type` (ODDS-02)

```python
# odds/base.py  — PURE, no I/O
def devig_fixed_two_way(o_a: float, o_b: float) -> float:
    """OddsPapi fixed-odds: remove the two-way overround. HANDOFF §5 line 154.
    test_devig: o_a=1.5, o_b=2.5 -> 0.625."""
    ia, ib = 1.0 / o_a, 1.0 / o_b
    return ia / (ia + ib)

def normalize_market_price(price_a: float, *, spread: float = 0.0, fee: float = 0.0) -> float:
    """Polymarket/Kalshi: price ≈ probability. Remove only spread/fee; clamp to (eps, 1-eps).
    NEVER apply devig_fixed_two_way here (Pitfall 8) — there is no second decimal-odds side."""
    p = price_a - 0.5 * spread - fee
    return min(1.0 - 1e-6, max(1e-6, p))
```

### Pattern 3 — log-opinion pool, originate/liquidity-weighted, one opinion per source (ODDS-03)

A log-opinion pool is the **weighted geometric mean in logit space** — the standard for pooling
expert probability opinions (vs a linear pool, which is overconfident-averse and loses the
"sharp consensus" signal markets carry).

```python
# odds/base.py  — PURE
import numpy as np

def _logit(p): return np.log(p / (1.0 - p))
def _sigmoid(x): return 1.0 / (1.0 + np.exp(-x))

def pool(quotes: list[OddsQuote]) -> BlendedProb:
    """Weighted log-opinion pool of INDEPENDENT opinions for ONE match.

    Caller passes quotes ALREADY collapsed to one-per-originate-source (the OddsPapi
    soft-book bundle is pre-pooled into a single 'oddspapi:pinnacle' opinion — Pitfall 7).
    Weight = originate * log1p(liquidity); normalized. p = sigmoid(Σ w_i·logit(p_i)).
    var = cross-source WEIGHTED variance of the logits mapped back near p (the epistemic
    spread); n_sources = number of independent opinions. Single source -> var≈0 (band
    collapses to inner Wilson, PROB-05)."""
    ps = np.array([q.p_a_raw for q in quotes])
    w  = np.array([q.originate * np.log1p(q.liquidity) for q in quotes])
    w  = w / w.sum()
    z  = _logit(ps)
    zbar = float((w * z).sum())
    p = float(_sigmoid(zbar))
    # epistemic variance: weighted spread of logits, delta-method'd to p-space
    logit_var = float((w * (z - zbar) ** 2).sum())
    var = (p * (1 - p)) ** 2 * logit_var      # delta method: Var(p) ≈ (dp/dz)^2 Var(z)
    return BlendedProb(p=p, var=var, n_sources=len(quotes), bo3=quotes[0].bo3)
```

The OddsPapi bundle is collapsed to ONE opinion in `odds/oddspapi.py` (a within-provider pool
of its books, Pinnacle weighted highest), so `pool()` only ever sees independent opinions and
**never headcounts** the soft books.

### Pattern 4 — series→map invert + logistic least-squares ratings fit (ODDS-04)

Two stages, both pure, in `engine/backsolve.py`:

**(a) invert series→map.** The forward `series(p, bo3)` is `p²(3−2p)` (probs.py:32). For the
back-solve we need its inverse on `(0,1)→(0,1)`. `q = 3p² − 2p³` is strictly monotone on
`[0,1]`, so invert by **bisection** (numpy-only, ~40 iterations to 1e-9 — no scipy):

```python
# engine/backsolve.py
def invert_series(q: float, bo3: bool) -> float:
    """Recover per-map p from a SERIES prob q. Identity for Bo1; bisection-invert p²(3-2p) for Bo3.
    Verified inverse: invert_series(0.648, True) == 0.6 ; invert_series(0.5, True) == 0.5."""
    if not bo3:
        return q
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if mid * mid * (3 - 2 * mid) < q: lo = mid
        else: hi = mid
    return 0.5 * (lo + hi)
```

**(b) logistic least-squares ratings fit (hand-rolled Gauss-Newton, numpy only).** We have a
set of KNOWN-matchup map-level probs `p_map_target[(i,j)]` (from inverting the blended series
probs). The model is `p_map(r_i, r_j) = sigmoid(ln10·(r_i − r_j)/S)` (probs.py:23 rewritten in
nats: `1/(1+10^(-(ra-rb)/S))` ≡ `sigmoid((ra-rb)·ln10/S)`). Fit `r` (one free param per team,
fix one team's rating as the gauge / anchor to remove the additive degeneracy) by minimizing
`Σ (p_map(r_i,r_j) − target_ij)²`. Gauss-Newton update with the logistic Jacobian; ~10-20 iters.

```python
def fit_ratings(targets: dict[tuple[int,int], float], teams: list[Team], S: float,
                anchor_id: int, iters: int = 25) -> dict[int, float]:
    """Logistic least-squares per-team ratings from MAP-level target probs (already inverted).
    Anchor one team's rating (gauge fix) so the additive null space (r+c) is removed.
    numpy Gauss-Newton; NO scipy. test_rating_roundtrip: feed known map probs, recover ratings."""
    ...
```

**Where live odds OVERRIDE the imminent round** (ODDS-04, last clause): the back-solved ratings
re-price ALL unplayed branches. But for the **next round's KNOWN matchups** the market series
prob is more accurate than any rating model, so it is injected DIRECTLY as a per-match
`market_series_prob` override (probs.py:42 `series_prob` already honors it; Bo3 NOT re-applied,
PROB-02). The plumbing: `simulate_stage` needs an optional `market_overrides:
dict[frozenset->series_p_for_lower_id]` passed through to `_play` (swiss.py:202) — a small new
keyword-only arg mirroring how `locked` flows. See D7.

### Pattern 5 — fill `epistemic_draws` + wire `_p_vec` into the inner sim (PROB-03/04/05)

The OUTER loop is already in `run_mc_progressive` (montecarlo.py:166). Phase 5 changes TWO
things:

1. **`epistemic_draws` yields K Beta draws** instead of one no-op:
```python
# engine/probs.py  — fill the existing stub
def epistemic_draws(blend, var, *, k: int = 1, rng=None):
    """K epistemic draws of the per-element p-vector. k=1 (default) preserves the Phase-1
    single-point no-op for the rating-only path (var all-zero -> identical draws -> band
    collapses to Wilson). With real cross-source var (k>1), each element draws
    rng.beta(*beta_moment_fit(mean, v)) — the OUTER epistemic spread (PROB-03/04/05)."""
    if rng is None or all(v <= 0.0 for v in var):
        for _ in range(k): yield list(blend)
        return
    for _ in range(k):
        yield [float(rng.beta(*beta_moment_fit(m, v))) if v > 0 else m
               for m, v in zip(blend, var)]
```

2. **The inner sim consumes `_p_vec`.** Today `_p_vec` is discarded. The drawn vector is a
   per-MATCHUP series-prob perturbation for the KNOWN/market-priced matches, OR a per-team
   rating perturbation — **decision needed (D5)**: the cleaner design is to draw at the
   **blended-match level** (the market gives us per-match p + var directly), so `_p_vec` is a
   dict of `{frozenset(match): drawn_series_p}` that flows into `simulate_stage` as the
   `market_overrides` of Pattern 4 for THAT outer draw. Aggregate per-team counts across the K
   draws; the reported band = the across-draw spread (epistemic) which **does not shrink with N**
   because adding sims only tightens the inner aleatoric Wilson term, not the K-draw spread.

### Anti-patterns to avoid
- **Importing `httpx`/`dotenv` anywhere the app imports** (regresses zero-config DX-01). Keep
  them in `scripts/fetch_odds.py` and `odds/*.py` ONLY; the app touches `ui/odds_loader.py`
  (json only) and the frozen engine.
- **Headcounting the OddsPapi books** (Pitfall 7) — pre-pool them to one opinion in `oddspapi.py`.
- **Two-way de-vig on a market price** (Pitfall 8) — route on `vig_type`.
- **Fitting ratings to series probs** (Pitfall 9) — invert to map level first.
- **Beta draw inside the per-sim loop** (Pitfall 4) — it lives in `epistemic_draws` (OUTER).
- **Re-implementing the variance clamp** — call `beta_moment_fit` (probs.py:92), it's correct.
- **The app calling `get_quotes()` on rerun** (Pitfall 11) — only `scripts/fetch_odds.py` does.

---

## Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---------|-------------|-------------|-----|
| Beta method-of-moments + variance clamp | a new clamp | `engine.probs.beta_moment_fit` (line 92) | already correct, already tested-shaped; re-impl risks the negative-param crash |
| Odds-override-without-re-applying-Bo3 | a new branch | `engine.probs.series_prob(market_series_prob=...)` (line 42) | already short-circuits (PROB-02) |
| Outer/inner loop structure | a new MC loop | the existing `for _p_vec in epistemic_draws(...)` (montecarlo.py:166) | rewriting the hot path is the exact thing Phase 1 prevented |
| ratings override into the sim | a new sim path | `simulate_stage(teams, ratings, ...)` + `run_mc_progressive(..., ratings, ...)` | the `{id:rating}` seam exists (swiss.py:224, montecarlo.py:128) |
| Wilson band | recompute | `engine.montecarlo.wilson` (line 47) | the inner aleatoric band; epistemic wraps it |
| fail-soft key check | re-detect | `ui.state.odds_key_present` (line 138) | os.environ-only, preserves zero-config |
| R1 pairing for fixture discovery | re-derive seeds | `engine.swiss.build_round1_pairs` | the GATE-01 seed blocker again |

**Key insight:** Phase 5 is ~70% *calling existing seams correctly* and ~30% new pure code. The
risk is re-implementing a seam slightly differently (especially the Beta clamp) rather than the
new math being hard.

---

## Fetch + cache seam (ODDS-05/06/07) — the v2-cron drop-in contract

### `scripts/fetch_odds.py` — the ONE entry (button AND cron)
```python
# scripts/fetch_odds.py  — runnable as `python -m scripts.fetch_odds` (cron) OR imported+called
# by the "fetch now" button's handler (still OUT of the rerun path — it's an explicit user action).
def main(out_path="data/odds_cache.json") -> dict:
    load_dotenv()                                   # keys live HERE, not in the app
    teams = load_teams()
    fixtures = discover_fixtures(teams)             # dynamic slug/ticker match (ODDS-05)
    quotes = []
    for Provider in (OddsPapiProvider, PolymarketProvider, KalshiProvider):
        try: quotes += Provider().get_quotes(fixtures)   # each provider fails soft independently
        except Exception as e: log.warning("provider %s failed: %s", Provider, e)
    blended = {match_key(q.match): pool(group).__dict__ for ...}   # per-match pool
    cache = {"_meta": {"fetched_at": time.time(), "providers": [...], "version": 1}, "blended": blended}
    Path(out_path).write_text(json.dumps(cache, indent=2))
    return cache
```

### `data/odds_cache.json` schema (the FROZEN contract — design once so the cron is zero app change)
```json
{
  "_meta": {
    "fetched_at": 1733000000.0,
    "version": 1,
    "providers_present": ["oddspapi:pinnacle", "polymarket"],
    "round_hint": 2
  },
  "blended": {
    "1-9":  {"p": 0.71, "var": 0.0042, "n_sources": 3, "bo3": false},
    "2-10": {"p": 0.58, "var": 0.0110, "n_sources": 2, "bo3": false}
  }
}
```
- Keys are sorted `"loid-hiid"` engine-id pairs (`match_key`), so the app maps them to matchups
  WITHOUT provider strings. `p` is P(lower-id team wins the series).
- `var` is the cross-source epistemic variance (the app clamps via `beta_moment_fit` before
  drawing — do NOT pre-clamp in the file, keep it raw so the clamp is one place).
- **v2 cron = ONE crontab line:** `*/30 * * * * cd /app && python -m scripts.fetch_odds` — it
  writes the SAME file the app reads. Zero app change (ODDS-07/OPS-01) BECAUSE the app's only
  contact with odds is `ui/odds_loader.load_odds_cache()` reading this schema.

### `ui/odds_loader.py` — read-only, fail-soft
```python
# ui/odds_loader.py  — NO httpx, NO dotenv, NO provider import (preserves zero-config)
def load_odds_cache(path="data/odds_cache.json") -> dict | None:
    """Read-only. Returns None on ANY error (missing file, bad JSON, wrong version) — the app
    then runs rating-only with the existing banner. NEVER raises into the UI (ODDS-08 fail-soft)."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if raw.get("_meta", {}).get("version") != 1: return None
        return raw
    except (OSError, ValueError): return None
```
Mirrors the existing `read_seeds_confirmed` fail-safe pattern (state.py:122-135).

### Dynamic fixture discovery (ODDS-05) — and what's DEFERRED
`discover_fixtures(teams)` resolves each provider's market for a Cologne matchup by **alias
matching team names** (a small `{provider_string: engine_id}` table + case/space-insensitive
contains), because the markets do not exist until the bracket posts. Specifics:
- **OddsPapi:** `GET /fixtures?sportId=17&hasOdds=true&from=&to=`, filter by tournament name
  containing "Cologne"/"IEM", then `GET /odds?fixtureId=`. [CITED: oddspapi.io blog] — sportId 17,
  apiKey query param, base `https://api.oddspapi.io/v4`. **[DEFERRED — verify once Cologne markets
  post]:** exact `bookmakerOdds`/market-id field names, the tournament string, and that CS2
  Cologne has coverage. Budget the ~250 req/month free quota (one `/fixtures` + N `/odds` per
  fetch) — do NOT poll; the manual button + per-round trigger only.
- **Polymarket:** `GET https://gamma-api.polymarket.com/events?...` or `/public-search`, match the
  event slug, read `outcomes`/`outcomePrices` (1:1 implied probs). **NO auth**
  [CITED: docs.polymarket.com/market-data/overview]. **[DEFERRED]:** the exact Cologne event slug
  + whether a per-match market exists vs only tournament-winner.
- **Kalshi:** `GET https://external-api.kalshi.com/trade-api/v2/markets?series_ticker=...&status=open`,
  prices as `yes_bid`/`yes_ask` → mid = series prob. **NO auth for public market data**
  [CITED: docs.kalshi.com]. **[DEFERRED]:** the CS2/Cologne series ticker (Kalshi esports coverage
  is sparse — this provider may legitimately return `[]`, which is fine, it's fail-soft).

**Plan must NOT hard-depend on a live fixture existing today.** Build the adapters + parsers
against **recorded JSON fixtures** in `tests/fixtures/` (handcrafted to the documented shapes);
the live-slug verification is a `checkpoint:human-verify` the USER runs via gstack `/browse` once
markets post. A provider returning `[]` (no market yet) must produce a valid empty-blended cache,
not an error.

---

## Common Pitfalls

### Pitfall A — Epistemic variance folded into per-sim noise (PROB-03/04, the headline)
**What goes wrong:** the Beta draw ends up inside the per-sim loop; the reported band shrinks
with N and looks falsely tight on high-disagreement matches. **Avoid:** the draw lives ONLY in
`epistemic_draws` (OUTER, montecarlo.py:166); aggregate ACROSS draws. **Warning sign:**
`test_epistemic_band_wider_than_wilson` fails, or the band narrows as N grows on a 2-source
disagreeing match.

### Pitfall B — Beta params go negative on a thin-liquidity match (Pitfall 5)
**What goes wrong:** `var ≥ p(1−p)` → non-positive alpha/beta → `rng.beta` crashes on EXACTLY
the matches that matter. **Avoid:** call `beta_moment_fit` (probs.py:92, clamp already correct);
never pass raw var to `rng.beta`. **Warning sign:** a crash only on low-`n_sources`/high-`var`
matches.

### Pitfall C — Two-way de-vig applied to a Polymarket/Kalshi price (Pitfall 8)
**What goes wrong:** there's no second decimal-odds side; the "de-vig" silently mangles a price
that was already a probability. **Avoid:** route on `vig_type`; `normalize_market_price` for
market, `devig_fixed_two_way` for fixed. **Warning sign:** prediction-market probs that don't
match the raw price.

### Pitfall D — Soft books headcounted (Pitfall 7)
**What goes wrong:** OddsPapi's 4-5 books outvote the 2 independent markets; the blend just
echoes Pinnacle 5×. **Avoid:** pre-pool the OddsPapi bundle to ONE opinion in `oddspapi.py`
(Pinnacle-weighted) before `pool()`. **Warning sign:** `n_sources` > number of genuinely
independent originators.

### Pitfall E — Fitting ratings to series probs (Pitfall 9)
**What goes wrong:** a Bo3 series prob and a Bo1 series prob fed to the same fit produce a rating
that can't price both unplayed branches. **Avoid:** `invert_series` to map level FIRST, fit on
map probs. **Warning sign:** `test_rating_roundtrip` fails when the target set mixes Bo1/Bo3.

### Pitfall F — The app fetching on rerun / httpx in the app process (Pitfall 11)
**What goes wrong:** a provider call on every Streamlit rerun → slow, key-in-session, quota burn.
**Avoid:** app reads `data/odds_cache.json` only; fetch is `scripts/fetch_odds.py`. **Warning
sign:** `import httpx` reachable from `app.py`; a network call in the render path.

### Pitfall G — A missing/empty cache crashing the app (ODDS-08)
**What goes wrong:** odds path raises when the file is absent (the NORMAL first-run state).
**Avoid:** `load_odds_cache` returns `None` on any error; the app branches to rating-only + the
existing banner. **Warning sign:** any exception with no `odds_cache.json` present — the
zero-config first run (DX-01) is broken.

---

## Runtime State Inventory

Phase 5 is greenfield-additive (new packages + a JSON file), not a rename/refactor. The only
persisted runtime state it introduces:

| Category | Items | Action |
|----------|-------|--------|
| Stored data | `data/odds_cache.json` (NEW, read-only, written offline) | gitignore it (or ship absent); the app treats absence as normal |
| Secrets/env | `ODDSPAPI_KEY` (only one actually needed — Polymarket/Kalshi public reads need NO key) | read ONLY in `scripts/fetch_odds.py` via dotenv; `.env` gitignored; `.env.example` already shipped |
| Live service config | none — no provider-side state we register | None |
| OS-registered state | v2 cron line (DEFERRED, OPS-01) — not registered in v1 | None in this phase |
| Build artifacts | new `odds/`, `scripts/` packages → ensure `pyproject.toml` packages list includes them | add to packaging config so `python -m scripts.fetch_odds` resolves |

**Verified:** the `.gitignore` must include `data/odds_cache.json` (a fetched artifact, not
source) — confirm in a Wave-0 task. `.env` is already gitignored (DX-05, Phase 2).

---

## Environment Availability

| Dependency | Required by | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `httpx` | provider fetch | ✗ (not yet installed) | — | install in Wave 0 |
| `python-dotenv` | key load in fetch script | ✗ | — | install in Wave 0 |
| `numpy` | back-solve, Beta draws | ✓ | 2.4.6 | — |
| `ODDSPAPI_KEY` | OddsPapi anchor | ✗ (none in env) | — | rating-only OR Polymarket+Kalshi only (both keyless) |
| Live Cologne markets | live slug verification | ✗ (not posted 2026-05-29) | — | recorded JSON fixtures for tests; live verify DEFERRED to user via gstack |

**Blocking with no fallback:** none — every gap has a fail-soft path. **The phase is fully
plannable and testable today** against recorded fixtures; only the live-slug confirmation is
deferred.

---

## Validation Architecture

### Test framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.x (pinned, STATE.md line 77) |
| Quick run | `uv run pytest tests/test_odds.py tests/test_backsolve.py tests/test_epistemic.py -x` |
| Full suite | `uv run pytest` (must stay ≥85 green + new tests; GATE-01 backtest must stay green) |

### Phase requirements → test map
| Req | Behavior | Type | Command | Exists? |
|-----|----------|------|---------|---------|
| ODDS-02 | de-vig fixed two-way `1.5/2.5→0.625` | unit | `pytest tests/test_odds.py::test_devig_fixed` | ❌ Wave 0 |
| ODDS-02 | market price normalize (no two-way devig) | unit | `pytest tests/test_odds.py::test_market_price_not_devigged` | ❌ |
| ODDS-03 | log-opinion pool: agreeing sources → var≈0 | unit | `pytest tests/test_odds.py::test_pool_agreeing_low_var` | ❌ |
| ODDS-03 | OddsPapi bundle counts as ONE opinion | unit | `pytest tests/test_odds.py::test_softbook_bundle_one_opinion` | ❌ |
| ODDS-04 | `invert_series(0.648,True)==0.6` | unit | `pytest tests/test_backsolve.py::test_invert_series` | ❌ |
| ODDS-04 | `test_rating_roundtrip` (fit recovers known map probs) | unit | `pytest tests/test_backsolve.py::test_rating_roundtrip` | ❌ |
| ODDS-04 | market override used directly, Bo3 NOT re-applied | unit | `pytest tests/test_backsolve.py::test_override_no_bo3_reapply` | ❌ |
| PROB-04 | `test_epistemic_band_wider_than_wilson` **[CRITICAL]** | unit | `pytest tests/test_epistemic.py::test_band_wider_than_wilson` | ❌ |
| PROB-05 | epistemic band does NOT shrink with N on disagreement | unit | `pytest tests/test_epistemic.py::test_band_stable_in_N` | ❌ |
| ODDS-05 | provider parser maps recorded fixture → OddsQuote | unit | `pytest tests/test_odds.py::test_oddspapi_parse_fixture` | ❌ |
| ODDS-07 | cache schema round-trips; loader fail-soft on missing/bad | unit | `pytest tests/test_odds.py::test_cache_roundtrip_and_failsoft` | ❌ |
| ODDS-08 | no key + no cache → app rating-only, no crash | AppTest | `pytest tests/test_app.py::test_no_odds_failsoft` | ❌ |
| ODDS-06 | "fetch now" button calls the script, app never get_quotes on rerun | AppTest | `pytest tests/test_app.py::test_fetch_button_not_on_rerun` | ❌ |

### Wave 0 gaps
- [ ] `tests/test_odds.py` + `tests/fixtures/{oddspapi,polymarket,kalshi}_sample.json` (recorded shapes)
- [ ] `tests/test_backsolve.py`
- [ ] `tests/test_epistemic.py`
- [ ] `pip index versions httpx python-dotenv` + add to `pyproject.toml`; gitignore `data/odds_cache.json`

---

## Security Domain

| ASVS | Applies | Control |
|------|---------|---------|
| V5 Input validation | yes | parse provider JSON defensively; clamp probs to (eps,1-eps); cache `version` check; loader returns None not raise |
| V6 Cryptography | no | no crypto; keys are bearer tokens read from env, never logged (mirror `odds_key_present` value-never-returned rule, state.py:144) |
| V2/V3/V4 auth/session/access | no | single local user, no server-side auth |

| Threat | STRIDE | Mitigation |
|--------|--------|------------|
| API key leak into session/logs/UI | Information disclosure | keys read ONLY in `scripts/fetch_odds.py` via dotenv; never in `ui/`/`app.py`; presence-only check exists |
| Malicious/huge provider response → DoS or crash | DoS / Tampering | fail-soft per provider (`try/except` per `get_quotes`); loader returns None on bad JSON; cap response size in httpx |
| Cache file tampered to skew probs | Tampering | local single-user tool; `version` gate + clamp bound the blast radius; raw `var` clamped before Beta |

---

## State of the Art

| Old | Current | Impact |
|-----|---------|--------|
| Assume all three providers need API keys | Polymarket + Kalshi public market data need **NO auth** | "no key" still yields a 2-source pool; key only unlocks the OddsPapi/Pinnacle anchor — strictly better fail-soft |
| `the-odds-api.com` (common default) | OddsPapi (CLAUDE.md-chosen; Pinnacle anchor, 250 req/mo free) | locked by CLAUDE.md — research the chosen one, not alternatives |

---

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|-------|---------|---------------|
| A1 | `httpx` 0.28.x / `python-dotenv` 1.0.x current | Standard Stack | low — Wave-0 `pip index versions` confirms |
| A2 | OddsPapi base `api.oddspapi.io/v4`, sportId 17, `apiKey` query param, `/fixtures`+`/odds` | discovery | MEDIUM — single blog source; DEFERRED live verify |
| A3 | OddsPapi response field names (`bookmakerOdds`, market id "171", `participantNName`) | Pattern 1/discovery | MEDIUM-LOW — DEFERRED; parser built against a recorded fixture, adjusted at verify |
| A4 | Polymarket Gamma `/events`+`/public-search`, `outcomePrices`, no auth | discovery | LOW-MED — no-auth CITED; exact Cologne slug DEFERRED |
| A5 | Kalshi `trade-api/v2/markets?series_ticker=`, `yes_bid/ask`, no auth | discovery | LOW-MED — no-auth CITED; CS2 series ticker DEFERRED (may legitimately be `[]`) |
| A6 | delta-method var mapping in `pool()` is an acceptable epistemic proxy | Pattern 3 | LOW — any monotone var→band map satisfies "band ⊇ Wilson, no shrink in N"; tune in test |
| A7 | Cologne markets not yet posted (2026-05-29) | Environment | n/a — drives the DEFERRED fixtures-first strategy regardless |

**If markets are not live at plan time (expected):** every adapter is built + unit-tested against
recorded fixtures; live slug/ticker/coverage is a single user-run `checkpoint:human-verify` via
gstack `/browse`, NOT a build blocker.

## Open Questions

1. **Per-match vs tournament-only markets on Polymarket/Kalshi.**
   - Known: both expose markets keylessly; CS2 per-match coverage is uncertain this far out.
   - Unclear: whether per-series markets will exist or only outright-winner.
   - Recommendation: adapters target per-match; gracefully yield `[]` when only outright exists.
     The blend simply has fewer sources for that match (n_sources drops, var path handles it).

2. **Outer-draw granularity: per-match series-prob draw vs per-team rating draw (D5).**
   - Recommendation: draw at the **blended-match level** (market gives p+var per match directly),
     feeding `market_overrides` per outer draw. Simpler, matches where the variance actually lives
     (the market disagreement), and keeps the back-solved ratings as the deterministic backbone
     for unpriced branches. Flagged for the planner to lock in plan 05-02.

3. **K (number of epistemic draws) vs N split.** With N=100k and K outer draws, total sims = K·N.
   - Recommendation: K small (e.g. 8-16), reuse the existing pinned-chunk RNG per draw with a
     distinct child SeedSequence per draw so reproducibility survives. Make K a constant
     (`DEFAULT_EPISTEMIC_DRAWS`) like `DEFAULT_N_CHUNKS`; expose later if needed.

---

## Plan split (3 plans — math-dense, so split by purity boundary)

The phase is pitfall-dense; split so each plan is independently TDD-verifiable and the risky math
is isolated from the I/O.

- **05-01 — Pure odds core (TDD, no I/O, no UI).** `odds/base.py` (`OddsQuote`, `BlendedProb`,
  `OddsProvider` Protocol, `devig_fixed_two_way`, `normalize_market_price`, `pool()` log-opinion
  with originate/liquidity weight + cross-source var), the within-OddsPapi bundle pre-pool
  (one-opinion, Pitfall 7), and the provider PARSERS (`oddspapi/polymarket/kalshi.py`
  fixture-JSON → `list[OddsQuote]`, routed de-vig by `vig_type`) tested against recorded
  `tests/fixtures/*.json`. `tests/test_odds.py` (devig, market-not-devigged, pool agreeing→var≈0,
  bundle-one-opinion, parse). **Pure → fully TDD-eligible; no live network.** (ODDS-01/02/03/05-parse)

- **05-02 — Back-solve + epistemic outer loop (TDD, touches the frozen engine's stubs ONLY).**
  `engine/backsolve.py` (`invert_series` bisection, `fit_ratings` Gauss-Newton, market-override
  plumbing), FILL `engine/probs.py:epistemic_draws` with K Beta draws (call existing
  `beta_moment_fit`), wire `_p_vec` into `run_mc_progressive`'s inner sim + the `market_overrides`
  pass-through in `simulate_stage`/`_play`. `tests/test_backsolve.py` (`test_invert_series`,
  `test_rating_roundtrip`, `test_override_no_bo3_reapply`) + `tests/test_epistemic.py`
  (**`test_epistemic_band_wider_than_wilson` [CRITICAL]**, `test_band_stable_in_N`). **TDD; the
  only engine touch is filling the two pre-cut stubs + a small keyword-only arg — verify GATE-01
  backtest STAYS green (no behavior change on the rating-only path).** (ODDS-04, PROB-03/04/05)

- **05-03 — Fetch script + cache seam + UI (script is I/O; UI is AppTest).** `scripts/fetch_odds.py`
  (dotenv, `discover_fixtures` alias matching reusing `build_round1_pairs`/`load_teams`, per-provider
  try/except fail-soft, writes the `data/odds_cache.json` schema), `ui/odds_loader.py` (read-only,
  fail-soft → None), and the app slice: "fetch now" button calling the script (NOT on rerun),
  branch to back-solved ratings when a valid cache loads, PRESERVE the existing no-key banner
  (`app.py:152`) and zero-config first run. `tests/test_app.py` AppTests (`test_no_odds_failsoft`,
  `test_fetch_button_not_on_rerun`, cache round-trip/fail-soft). **AppTest/integration; the live
  slug/ticker confirmation is a deferred user `checkpoint:human-verify` via gstack /browse — NOT a
  build blocker.** (ODDS-05-discover/06/07/08, OPS-01 seam)

**Waves:** 05-01 (pure core) and 05-02 (back-solve/epistemic) are independent of each other —
both depend only on the frozen engine — so they are **parallel-safe** as two Wave-1 plans. 05-03
depends on BOTH (it imports the providers from 05-01 and the back-solve/epistemic from 05-02) →
Wave 2. Dependency: 05-03 → {05-01, 05-02}; 05-01 ∥ 05-02.

---

**Phase 5 key decisions (return value):**
- **D1 — Three new packages, app stays clean:** `odds/{base,oddspapi,polymarket,kalshi}.py`,
  `engine/backsolve.py`, `scripts/fetch_odds.py`, `ui/odds_loader.py`. `httpx`/`dotenv` live ONLY
  in `scripts/` + `odds/`; the app touches the frozen engine + a json-only read-only loader, so
  the zero-config first run (DX-01) and `odds_key_present` (os.environ-only, state.py:138) survive.
- **D2 — Verified seams, FILL don't rebuild:** the epistemic OUTER loop is ALREADY wired
  (`for _p_vec in epistemic_draws(...)`, montecarlo.py:166); `beta_moment_fit`'s `var<p(1-p)` clamp
  is ALREADY correct (probs.py:92-116 — CALL it, don't re-impl); `series_prob` ALREADY honors a
  market override without re-applying Bo3 (probs.py:42, PROB-02); `simulate_stage(teams, ratings,…)`
  ALREADY accepts the ratings override. Phase 5 is additive, not a hot-path rewrite.
- **D3 — De-vig routed on `vig_type`:** OddsPapi `"fixed"` → `(1/o_a)/(1/o_a+1/o_b)` (`0.625` test);
  Polymarket/Kalshi `"market"` → price≈prob, spread/fee-only, NEVER two-way de-vig (Pitfall 8).
  NEW FACT: both prediction markets are **keyless public reads**, so "no key" still yields a
  2-source pool; the key only unlocks the OddsPapi/Pinnacle anchor.
- **D4 — Pool = originate/liquidity-weighted log-opinion (geometric mean in logit):** the OddsPapi
  soft-book bundle is pre-pooled to ONE Pinnacle-anchored opinion in `oddspapi.py` so `pool()`
  never headcounts (Pitfall 7); output `BlendedProb(p, var, n_sources, bo3)` with cross-source
  (epistemic) variance via a delta-method map of the weighted logit spread.
- **D5 — Back-solve = invert-then-fit, numpy-only:** `invert_series` (identity Bo1, bisection-invert
  `p²(3−2p)` for Bo3 — `0.648→0.6`), then hand-rolled Gauss-Newton logistic least-squares
  `fit_ratings` with one anchored gauge team (no scipy). The imminent round's KNOWN matchups are
  injected as direct `market_overrides` (Bo3 NOT re-applied, PROB-02) via a new keyword-only arg
  threaded `simulate_stage`→`_play`.
- **D6 — Epistemic outer loop filled at the MATCH level:** `epistemic_draws` yields K
  `rng.beta(*beta_moment_fit(p, var))` per-match draws (k=1 + var=0 preserves the rating-only
  no-op so the band collapses to Wilson); each outer draw feeds `market_overrides`; aggregate per-team
  counts ACROSS draws so the band ⊇ Wilson and does NOT shrink with N (PROB-03/04/05;
  `test_epistemic_band_wider_than_wilson` [CRITICAL]).
- **D7 — Read-only cache seam = the v2-cron drop-in:** `scripts/fetch_odds.py` (button AND cron)
  writes `data/odds_cache.json` (`{_meta:{version,fetched_at,…}, blended:{"lo-hi":{p,var,n_sources,bo3}}}`);
  the app reads ONLY via `ui/odds_loader.load_odds_cache` (returns None on any error → rating-only +
  existing banner, ODDS-08). v2 cron = one crontab line, zero app change (ODDS-07/OPS-01). App never
  calls `get_quotes()` on rerun (Pitfall 11).
- **Plan split — 3 plans, 2 waves:** 05-01 pure odds core (de-vig/pool/parse, TDD) ∥ 05-02 back-solve
  + epistemic fill (TDD, frozen-engine stubs only, GATE-01 must stay green) → 05-03 fetch script +
  read-only cache + UI fetch button + fail-soft (AppTest); live slug/ticker confirmation is a deferred
  user `checkpoint:human-verify` via gstack /browse, NOT a build blocker. Markets-not-posted is the
  expected state → adapters are built + tested against recorded JSON fixtures today.
