# Live-Odds Display & Fetching — Design Plan

> Output of `/plan-design-review` (2026-05-31). Improves how live odds are *shown* and *fetched*.
> Calibrated against the LOCKED design contract in `.planning/phases/02-streamlit-ui-shell/02-UI-SPEC.md`.
> Scope decision: **full** (10/10). Visual reference: **Streamlit-faithful spec** (no web mockups —
> the medium is Streamlit, and the UI-SPEC is explicit that these are layout/IA/token decisions).
>
> Initial display rating **3/10**. Target after this plan **9/10**.
>
> **Implementation status (2026-05-31):**
> - ✅ **P0 fix** — `Result.n = len(sample)` (montecarlo.py:281) + critical regression
>   `test_point_probs_valid_under_epistemic`. Full suite green (114), GATE-01 + rating-only byte-identical.
> - ✅ **D1 + bug fixes A/B** — honest cache-driven status panel (header strip), real fetch spinner,
>   persisted fetch outcome. New helpers `fmt_age`/`is_stale`/`provider_labels`/`priced_ids` + unit tests;
>   2 stale banner tests updated, 2 new AppTests. test_ui_helpers (21) + test_app (36) green.
> - ⏳ **D2 (two-tone band)** + **D3 (per-book drill-down)** — next lane (engine `band_*_sampling` + schema v2).

---

## The problem in one line

The live-odds feature is wired end-to-end and fail-soft, but as a *display* it is nearly invisible,
the off-banner can contradict reality, and the Fetch button has two real interaction bugs.

## Load-bearing constraints (do not break)

- **Never red/green.** Status = blue `#3B82F6` / amber `#F59E0B`, always with an ASCII glyph + text label (UI-06).
- **Accent `#7C5CFC` stays reserved** for the Run CTA, the hero number, and the active mode segment. The odds panel must NOT use it.
- **ASCII glyphs only** (`o`/`x`/`/`, no `●`/`✓` — the cp1252 console lesson).
- **Monospace for every number** (counts, timestamps).
- **Fail-soft, zero-config first run.** The app's only odds contact stays the JSON loader (`ui/odds_loader.load_odds_cache`); no httpx/dotenv on the import or render path. A missing cache is the normal first-run state, never an error.
- **GATE-01 / reproducibility:** all changes are pure *display* — they never touch the engine, the sim seed, `n_chunks=20`, or the cache key math. A rating-only run renders byte-identical to today (no markers, no legend, no panel content).

---

## Prerequisite — P0 engine fix (BLOCKS all display work)

`/plan-eng-review` (2026-05-31) found a correctness bug that the display work would otherwise expose.

Under epistemic draws (the exact path live odds creates: `market_blend` with `var > 0` → K=12), the MC
accumulates `counts_*` and `sample` over K×N sims (montecarlo.py:256, 264) but sets `Result.n = N`
(montecarlo.py:282). So `p_advance()/p_30()/p_03()` are inflated by K. **Proven empirically:** with a
`var>0` blend, `sum(p_advance) = 96.0` (must be 8.0) and `max(p_advance) = 11.923` (the UI would render
"1192%"). Rating-only (K=1) is correct, which is why GATE-01 and every existing test stayed green —
`test_epistemic.py` asserts band *width* only, never that `p_advance ∈ [0,1]`.

- **Fix:** `Result(n=len(sample), ...)` instead of `n=N` in `run_mc_progressive`. `len(sample) == N*k`,
  so it is correct under epistemic draws AND byte-identical for rating-only (K=1 → `len == N`). One line.
- **Regression test (CRITICAL):** `tests/test_epistemic.py::test_point_probs_valid_under_epistemic` —
  with `market_blend={"1-9": (0.5, 0.05)}`, assert `max(p_advance().values()) <= 1.0` and
  `abs(sum(p_advance().values()) - 8.0) < 0.05`. The exact assertion the suite was missing.
- **Blast radius:** isolated to `Result.p_*()` (the probs table this plan surfaces). The optimizer
  (optimizer.py:307) and live hero (live.py:199-200) read `result.sample` directly, so they're already
  consistent over the K×N sample and need no change. Verify they still pass post-fix.
- **Sequencing (user decision 2026-05-31): fix this FIRST, before any display work.** D1's whole job is
  to announce "odds are live", which would make the 12x-wrong numbers visible. Correctness is the product.

---

## Decision 1 — Status lives in the header strip (both modes)

The odds state back-solves all 16 ratings and drives the epistemic band, so it changes every number on
the page. It belongs with the other cross-cutting honest-status elements (trust badge, seed banner), not
buried in a sidebar. The **Fetch action stays in the controls column** (co-located with the thing it changes).

### Honest live/off — read the CACHE, not the env key

Today's banner keys on `odds_key_present()` (the env key). That is wrong: Polymarket + Kalshi are **keyless**,
so a no-key user can have a fetched cache actively feeding the sim while the banner says "off, using manual
ratings." The status must read the **loaded cache**, not the key.

```
STATE  | CONDITION                                   | HEADER COPY
-------|---------------------------------------------|------------------------------------------------------------
live   | cache present AND blended non-empty         | [o live]  8 markets · 3 books (Pinnacle, Polymarket, Kalshi)
       |                                             |           · fetched 4m ago
stale  | live AND age > STALE_AFTER (default 2h)     | …as live, then amber: "· may be stale — re-fetch"
off    | no cache, OR cache present but blended empty| odds off — using manual ratings.
       |                                             | Fetch to price the sim from live markets (Polymarket
       |                                             | + Kalshi need no key).
```

- `[o live]` uses `status_badge_html("live")` (blue `o live`) — already in `ui/render.py`.
- "off" is **neutral** (`st.caption`/`st.info`), never amber-alarm — off is a valid resting state, not a warning.
- The stale suffix is the **only** amber here, via the existing warn token.
- The empty-cache case ("fetched, but no Cologne market posted yet") is **off**, with a one-line reason so the
  feature never reads as broken pre-event: "no live markets posted yet — running manual ratings."

### Header strip ASCII (Streamlit-faithful)

```
+----------------------------------------------------------------------------------+
| engine validated vs Valve rulebook unit tests — full backtest pending seed data  |  (trust badge, unchanged)
| ⚠ Seeds are INFERRED — verify vs the official seed list ...                       |  (seed banner, unchanged)
| [o live]  8 markets · 3 books (Pinnacle, Polymarket, Kalshi) · fetched 4m ago    |  <-- NEW: replaces the
|                                                                                  |       one-line off-banner
+----------------------------------------------------------------------------------+
```

## Decision 2 — Epistemic band: two-tone CI bar  ⚠ crosses into the engine

A 3-provider ensemble's signature output is source-disagreement variance widening the CI band on
thin-liquidity matches. Today a market-disagreement band looks identical to a sampling band.

**Two-tone bar:** draw the **sampling (Wilson) band as the solid segment** and the **epistemic widening
as a faint extension** flanking it, so the eye reads "the market is adding this much uncertainty."

- All one hue (blue `#3B82F6`) — never red/green, no new semantic color. The distinction is **opacity**:
  solid (1.0) = sampling, faint (~0.4) = market-disagreement extension. Plus a one-line legend:
  `solid = sampling band · faint = extra width from books disagreeing.`
- New render helper `ci_bar_two_tone_html(p, lo_in, hi_in, lo_out, hi_out, hue)`; the existing
  `ci_bar_html` stays for the rating-only path.

**⚠ Architectural implication (NOT pure display) — seam is in `montecarlo.py`, not `probs.py`:**
the existing `Result.band_*` is the **epistemic** band (the across-draw union of per-draw Wilson intervals,
`_union_band`, montecarlo.py:277-279). The two-tone bar's *solid* segment needs the **sampling-only** band:
the aleatoric Wilson interval of the aggregate marginal, `wilson(counts, n)` over the full K×N sample. Add
sibling fields `Result.band_*_sampling` populated by `wilson(counts_*[i], n)` next to the existing union
bands. `probs.py` does NOT change (it's pure point-math, never sees the band). **GATE-01 guard:** with
`market_blend` None/empty (K=1), the union band already equals the single Wilson band, and
`band_*_sampling == band_*`, so the bar renders single-tone exactly as today, byte-identical.
**Depends on the P0 fix** — until `n = len(sample)`, both the point `p` and `wilson(counts, n)` are inflated.

## Decision 3 — Per-book drill-down  ⚠ crosses into the cache schema

The panel shows counts (8 markets, 3 books). The drill-down shows *why the books disagree*: an
`st.expander("Why the books disagree", expanded=False)` listing, for each priced match, each book's
series price next to the blended value.

```
Why the books disagree ▾
  Vitality vs paiN          Pinnacle 0.71 · Polymarket 0.68 · Kalshi 0.74   → blended 0.71  (spread 0.06)
  MOUZ vs Wildcard          Pinnacle 0.63 · Polymarket 0.55 · Kalshi 0.66   → blended 0.61  (spread 0.11) [wide]
```

- Sorted by disagreement spread (widest first — that's the interesting row). `[wide]` ASCII tag on
  high-spread matches (amber via the warn token, never red).
- Team names HTML-escaped (`html.escape`, like `_ballot_card_html`); prices are monospace numbers.

**⚠ Architectural implication (NOT pure display):** `scripts/fetch_odds.py` pools quotes via `pool(group)`
and writes **only the blended** `{p, var, n_sources, bo3}` per match. The individual book prices are
discarded, so the drill-down needs **per-provider quote retention** — a cache **schema v2**:

```
"blended": {"lo-hi": {"p", "var", "n_sources", "bo3",
                      "sources": [{"book": "Pinnacle", "p": 0.71}, ...]}}   # NEW optional field
```

This touches the FROZEN schema and the loader's `_SUPPORTED_VERSION` (currently fails closed on
`version != 1`). Plan: bump to v2, **accept both v1 and v2** (a v1 cache with no `sources` → counts only,
no drill-down — back-compat, fail-soft). Like Decision 2, this should go through `/plan-eng-review`.

---

## Architectural implications (read before building)

The **P0 fix lands first** (blocks everything — it corrects the numbers the display surfaces). Then D1 +
bug fixes A/B are pure display. D2 + D3 cross frozen contracts:

| Change | Layer touched | Frozen contract | Guard |
|--------|---------------|-----------------|-------|
| **P0 normalization** | `engine/montecarlo.py` (`Result.n`) | GATE-01 reproducibility | `n = len(sample)`; K=1 → `len == N`, byte-identical |
| Two-tone band (D2) | `engine/montecarlo.py` (`Result.band_*_sampling`) | GATE-01 reproducibility | K=1 → `sampling == union`, single-tone, byte-identical. Depends on P0. |
| Per-book drill-down (D3) | `scripts/fetch_odds.py` + `ui/odds_loader.py` | cache schema v1 (`_SUPPORTED_VERSION`) | v2 superset; v1 still loads (counts-only) |

**Build order:** P0 fix (+ regression test) → D1 + bug fixes A/B (pure display) → D2 + D3 (engine/schema).

---

## Interaction-state matrix (UI-05 — build all of these)

```
FEATURE      | LOADING                         | EMPTY (no cache)         | ERROR                  | SUCCESS
-------------|---------------------------------|--------------------------|------------------------|---------------------------
Fetch action | st.spinner: "Contacting books — | "Fetch odds now" CTA +   | persisted st.error,    | persisted st.success,
             |  Pinnacle / Polymarket / Kalshi"|  one-line what-it-does   | survives the rerun     | survives the rerun;
             |  (NEVER a dead button)          |                          | (fail-soft copy)       | header panel refreshes
Odds status  | —                               | "odds off — manual       | —                      | "[o live] N mkts · K books
panel        |                                 |  ratings. Fetch to ..."  |                        |  · fetched <age>"  (+stale)
Per-team band| (existing sim progress bar)     | dashes (existing)        | —                      | two-tone CI bar (solid
             |                                 |                          |                        | sampling + faint epistemic)
             |                                 |                          |                        | + legend; per-book expander
```

### Bug fix A — the fetch outcome must survive `st.rerun()`

`app.py:229-241` draws `st.success`/`st.info`/`st.error` then immediately calls `st.rerun()`, which discards
the current run's output, so the user reliably sees nothing. Fix: stash the outcome, render it after the rerun.

```python
# in the click handler, replace the inline st.success/.info/.error + st.rerun() with:
st.session_state[KEY_ODDS_OUTCOME] = (level, message)   # ("success"|"info"|"error", str)
st.rerun()

# near the top of the controls column (after the rerun lands), render once and clear:
outcome = st.session_state.pop(KEY_ODDS_OUTCOME, None)
if outcome:
    {"success": st.success, "info": st.info, "error": st.error}[outcome[0]](outcome[1])
```

(Stash-and-render, not `st.toast`, because the AppTest suite can assert on it deterministically.)

### Bug fix B — real loading state during the httpx fetch

Wrap the lazy-imported fetch in a spinner so the multi-provider network call is never a dead button:

```python
with st.spinner("Contacting books — Pinnacle / Polymarket / Kalshi…"):
    from scripts.fetch_odds import main as _fetch_odds_main   # LAZY — click branch only
    cache = _fetch_odds_main()
```

---

## New pure helpers (ui/render.py — no streamlit, unit-tested in tests/test_ui_helpers.py)

```python
PROVIDER_LABELS = {"oddspapi": "Pinnacle", "polymarket": "Polymarket", "kalshi": "Kalshi"}

def fmt_age(fetched_at_iso: str, now: datetime) -> str:
    """'just now' / '4m ago' / '6h ago' / '2d ago'. now is PASSED IN (no Date.now in tests)."""

def is_stale(fetched_at_iso: str, now: datetime, threshold_s: int = 7200) -> bool:
    """True once the cache age exceeds threshold (default 2h). Bad/missing timestamp -> True (fail toward 're-fetch')."""

def provider_labels(names: list[str]) -> list[str]:
    """Map raw provider .name values to display labels, preserving order, dropping unknowns gracefully."""

def priced_ids(blended: dict) -> set[int]:
    """Union of team ids across the 'lo-hi' keys of a blended map. Empty/malformed -> empty set."""

def ci_bar_two_tone_html(p, lo_in, hi_in, lo_out, hi_out, hue=_DEFAULT_HUE) -> str:
    """Solid inner (sampling) band + faint outer (epistemic) extension. lo_out<=lo_in<=hi_in<=hi_out.
    When outer == inner (rating-only), renders identical to ci_bar_html (single-tone). XSS guards as today."""

def source_spread(sources: list[dict]) -> float:
    """max(p) - min(p) across a match's per-book prices, for sorting the drill-down by disagreement."""
```

- `now` is injected so tests are deterministic and the GSD no-`Date.now` discipline holds.
- These are numeric/own-data only (no user free-text), but the age + counts render through `st.caption`/`st.write`
  (which escape) — only the `[o live]` badge uses `unsafe_allow_html`, and it comes from the fixed `status_badge_html`.

## Data thread (display-only, no engine change)

- `_odds_from_cache` already returns `market_blend`. Derive `priced = priced_ids(blended)` from the loaded cache
  and pass it into `_render_probs_table` / `_render_delta_table` for the `[mkt]` markers.
- The header panel reads the cache directly via `load_odds_cache()` (already imported), pulling `_meta.fetched_at`,
  `_meta.providers_present`, and `len(blended)`. Rating-only / absent cache → the "off" copy.
- Add `KEY_ODDS_OUTCOME` to `ui/state.py` alongside the other session keys.

---

## What already exists (reuse, do not rebuild)

- `status_badge_html`, `fmt_pct`, `ci_bar_html`, `delta_tag_html`, `hero_number_html` — `ui/render.py`.
- `load_odds_cache` (read-only JSON seam, no network) — `ui/odds_loader.py`.
- The amber warn token + banner pattern — already used by the seed banner in `_render_header_strip`.
- The cache schema already carries `fetched_at`, `providers_present`, `round_hint`, per-match `n_sources` + `var`.

## NOT in scope (deferred, with reason)

- **Auto-refresh / background re-fetch on staleness** — belongs to TODO #1 (cron-fed cache); this plan only
  *surfaces* staleness, it does not schedule fetches.
- **Responsive / mobile** — out of scope per UI-SPEC (local single-user desktop).
- **Accent on the odds panel** — deliberately excluded (accent is reserved).

(Two-tone band and per-book drill-down were *promoted into scope* — see Decisions 2 and 3.)

## Verification

- Unit (tests/test_ui_helpers.py): `fmt_age`, `is_stale`, `provider_labels`, `priced_ids`, `source_spread`,
  `ci_bar_two_tone_html` — age boundaries (just-now / minutes / hours / days), bad timestamp → stale=True,
  empty blended → off, and `outer == inner` → two-tone output equals `ci_bar_html` (single-tone).
- Engine band (tests/test_epistemic.py): `band_*_sampling ⊆ band_*` (sampling nested in the epistemic union)
  under K>1; and `band_*_sampling == band_*` when K=1 (the D2 GATE guard — two-tone collapses to single-tone).
- Schema (tests/test_odds.py): `fetch_odds` writes the v2 `sources` list; the loader accepts both v1 (counts-only)
  and v2 (`_SUPPORTED_VERSION` regression — a v1 fixture still loads, a malformed `sources` is dropped fail-soft).
- Fixture: add `tests/fixtures/odds_cache_live_v2.json` (a non-empty `blended` with `var>0` + `sources`) so the
  AppTest drives the live header panel, the two-tone band, and the drill-down end-to-end.
- AppTest (tests/test_app.py): fetch click shows a persisted outcome after rerun (Bug A); off-state copy when no
  cache; live-state copy with a recorded cache fixture; two-tone bars + legend + drill-down present only under a
  non-empty cache; the drill-down sorts by spread.
- Reproducibility: a rating-only run renders identically to today (single-tone bar, no panel content, no
  drill-down) — **GATE-01 stays green** (the engine-seam change must keep `market_blend=None` byte-identical).

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | issues_open | 1 P0 (12x prob inflation under epistemic K), 2 plan corrections, 1 critical regression test |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | issues_open | score 3/10 → 9/10, 4 decisions, 2 bug fixes |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **P0 FOUND:** `Result.n = N` while counts/sample span K×N under epistemic draws → `p_advance` inflated ~12x (proven: sum=96.0, must be 8.0). Fix `n = len(sample)` + critical regression test. Sequenced FIRST (user decision).
- **PLAN CORRECTIONS:** D2 seam is `montecarlo.py` (`band_*_sampling`), not `probs.py`. D3 schema v2 confirmed clean (per-source quotes already at the fetch call site).
- **UNRESOLVED:** 0. Build order locked: P0 fix → D1 + bug fixes A/B → D2 + D3.
- **VERDICT:** ENG + DESIGN reviewed. 1 critical gap (the P0) now has a mandated regression test, so it closes on implementation. Ready to implement in the locked order.
