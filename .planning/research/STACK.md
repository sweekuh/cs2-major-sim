# Stack Research

**Domain:** Local single-user scientific/simulation webapp (Monte Carlo + market-odds ensemble) in Python
**Researched:** 2026-05-28
**Confidence:** HIGH (core stack), MEDIUM (odds-provider access terms — verified against current docs/marketing but not exercised with live keys)

## TL;DR — Verdict on the existing PRD/HANDOFF stack

**The PRD/HANDOFF stack is sound and current. Build it as specified.** Every core decision (Python 3.12, Streamlit primary, numpy, `uv` bootstrap, `OddsProvider` adapter pattern, `python-dotenv`, APIs-not-scraping) survives 2026 validation. Below are the four things that warrant a note:

1. **Streamlit shipped its "2026" release (1.57.0, Apr 28 2026) which swaps the web server from Tornado to Starlette (ASGI).** Transparent for this app's API usage, but pin a version so a future Starlette-era change can't surprise you. CONFIRMS PRD's Streamlit choice; UPDATES the version.
2. **OddsPapi's free REST tier is metered at ~250 requests/month**, not "unlimited free." The PRD's fetch budget (~5 polls × event) fits inside this with enormous headroom, so this is a non-issue — but it should be written down so nobody loops the fetch. CONFIRMS viability; ADDS a concrete number the PRD left generic.
3. **Use `httpx` (not `requests`) for the odds layer.** Marginal today, but it is the 2026-standard client and gives you a free async path if per-round multi-provider fetches ever need to parallelize. Either works; `httpx` is the forward-looking pick. (PRD/HANDOFF didn't pin an HTTP client.)
4. **Defer Numba, as the HANDOFF/TODOS already says — but the deferral is now cheaper to reverse.** Numba 0.65.x (Apr 2026) supports Python 3.12–3.14 and numpy 2.4, so adding it later is low-friction. Do NOT pin it now. CONFIRMS the PRD's "deferred perf lever" stance.

All three odds providers are **live and read-only-accessible in 2026** with CS2 markets present. Details and confidence per provider in the Odds Providers section.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Python** | `>=3.12,<3.14` | Runtime | PRD-mandated. 3.12 is mature and fast; cap below 3.14 only because Streamlit/numba wheel coverage for brand-new minors lags. `uv` pins this in `pyproject.toml`. |
| **Streamlit** | `1.57.*` (pin `>=1.57,<1.58`) | UI + single-process host for engine + keyed odds calls | PRD-resolved: the only option that can hold API keys and make server-side odds calls (HTML is CORS-blocked). 1.57.0 (Apr 28 2026) is the current "2026" release. `@st.cache_data` semantics unchanged from the PRD's assumption — still the correct cache for the MC keyed on `(ratings, S, N, locked)`. |
| **numpy** | `>=2.4,<2.5` (current `2.4.6`) | Vectorized Monte Carlo (Bernoulli draws, tallying, Wilson bands) | PRD-mandated. numpy 2.x is the established line; 2.4.6 (May 18 2026) is current stable. The MC's batched RNG (`np.random.default_rng(seed)`) and vectorized record-vector scoring for the optimizer live here. |
| **uv** | latest (`>=0.9`) | Bootstrap / env / lockfile | PRD-mandated, and it is the 2026 cross-platform default. `uv run streamlit run app.py` is identical on Windows (author) and Mac/Linux (friends). Auto-creates env, installs from `pyproject.toml`, verifies `uv.lock` on every run. No bash-only `run.sh`. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **httpx** | `>=0.28,<0.29` | HTTP client for all three odds adapters | Slice 5 (odds layer). Sync API is requests-compatible; gives a free async path if you ever parallelize the per-round multi-provider fetch. Built by Encode (same team as Starlette, which Streamlit now uses). |
| **python-dotenv** | `>=1.0,<2.0` | Load `ODDSPAPI_KEY` etc. from gitignored `.env` | PRD-mandated. Slice 5. Pairs with the fail-soft "no key → rating-only mode + banner" contract (HANDOFF §10.6). Ship `.env.example`. |
| **numba** | `>=0.65` (DEFER — do not add yet) | JIT the Swiss inner loop if pure-Python 100k is too slow live | Only if the ~10–30s pure-Python run annoys at event time (TODOS #2). 0.65.x supports py3.12–3.14 + numpy 2.4, so adding later is cheap. Adding now buys nothing and complicates the `uv` bootstrap (LLVM dep). |

**Notably NOT needed (keep the dep tree tiny, per the "no other heavy deps" constraint):**
- **pandas** — Streamlit's `st.data_editor` accepts a list-of-dicts / numpy array; the 16-team rating table does not justify pandas. (Streamlit 1.57 even added direct Polars→Arrow, but you need neither.)
- **scipy** — Wilson interval is a 3-line closed form; logistic least-squares for the ratings back-solve (HANDOFF §5) is a tiny problem you can solve with `numpy.linalg` / a hand-rolled Newton step. Add scipy only if the back-solve fit proves finicky.
- **pytest** is the one dev dep worth adding (acceptance tests, HANDOFF §6).

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| **uv** | Env + dependency + Python-version management | Single tool; `uv sync` / `uv run`. Commit `uv.lock` for reproducible friend clones. |
| **pytest** | Engine acceptance tests + the slice-1 backtest gate | `>=8.0`. Dev-only (`[dependency-groups] dev = ["pytest"]` in `pyproject.toml`). The backtest gate (HANDOFF §6) and `test_difficulty_formula` [CRITICAL] live here. |
| **ruff** (optional) | Lint + format | `>=0.10`. Nice-to-have for a multi-author clone; not load-bearing. One tool replaces black+flake8+isort. |

## Installation

```toml
# pyproject.toml (uv-managed)
[project]
name = "swiss-mc"
requires-python = ">=3.12,<3.14"
dependencies = [
    "streamlit>=1.57,<1.58",
    "numpy>=2.4,<2.5",
    "httpx>=0.28,<0.29",       # odds layer (slice 5)
    "python-dotenv>=1.0,<2.0", # env keys (slice 5)
]

[dependency-groups]
dev = ["pytest>=8.0", "ruff>=0.10"]
```

```bash
# Primary path (identical Windows / Mac / Linux):
uv run streamlit run app.py

# pip fallback (HANDOFF §10.6 requires one):
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install streamlit numpy httpx python-dotenv
streamlit run app.py
```

First sim needs **no** dependency beyond streamlit + numpy (odds libs only matter at slice 5). This preserves the HANDOFF §10.6 "zero-config first sim, no API key" magic moment.

## Odds Providers — 2026 access terms (the PRD's highest-risk assumption)

All three are **live, have CS2 markets, and expose read-only data without write/trading auth in 2026.** This validates the PRD's "all three live in v1" decision. Confidence is MEDIUM because terms were verified from current docs/marketing, not exercised with live keys against IEM Cologne fixtures (which post closer to the event).

| Provider | 2026 access | CS2 / Cologne markets | Read-only viable? | Confidence | Note vs PRD |
|----------|-------------|------------------------|-------------------|------------|-------------|
| **OddsPapi** (Pinnacle anchor + ~10–14 books incl. Thunderpick/GG.BET/Betway) | REST API, **free tier = ~250 req/month**, simple query-param key auth, JSON returning all books per call | Yes — "Major CS2 tournaments (BLAST, IEM, ESL Pro League, PGL Majors) have 10–14 bookmakers per fixture" | Yes — pre-match REST is exactly the use case | MEDIUM-HIGH | CONFIRMS PRD. ADDS concrete quota (250/mo) the PRD left as "free tier." Pinnacle's own API is closed; OddsPapi is the legitimate aggregation path — confirms the "no scraping" rationale. |
| **Polymarket** (Gamma API) | **Gamma market-data API is fully public, no auth, no key, no registration**; hosted `gamma-api.polymarket.com`. CLOB read endpoints also public; only trading needs HMAC keys. | CS2 markets exist on-platform; Gamma indexes every sports category incl. esports | Yes — read-only is the default, zero-auth | MEDIUM | CONFIRMS PRD ("public API"). UPDATES the specifics: use **Gamma** for read-only prices, skip CLOB auth entirely. Verify the exact Cologne event/market slugs at event time. |
| **Kalshi** (Trade API v2) | Public market-data endpoints (`GET /markets`, prices, order book, series) **require no auth**; only trading needs RSA-signed headers. Base: `external-api.kalshi.com/trade-api/v2`. ~30 req/s public cap. CFTC-regulated, US-accessible. | **Yes, live now** — ~22 CS2 markets (per-map winners, game winners, futures, total maps); series ticker `KXCS2GAME`; real per-match markets observed (e.g. NaVi vs GamerLegion) | Yes — read-only public market data, no key | MEDIUM-HIGH | CONFIRMS PRD ("official API + public market data, has CS2 + Cologne markets"). The earlier PRD risk note about "US trading waitlisted" is irrelevant to read-only data access — you never trade. Thin volume on niche games remains the real caveat (matches PRD risk §10 "thin-liquidity noise"). |

**Provider-set recommendation (resolves PRD Open Question #2):** the adapter pattern makes "all three live in v1" low-cost because read-only access for all three is auth-light (OddsPapi: one key; Polymarket: none; Kalshi: none for data). The PRD's "honest minimal = Pinnacle + Polymarket" remains a valid fallback if Kalshi liquidity is too thin to weight — but there is no *access* reason to defer any of them. Build the OddsPapi adapter live first (HANDOFF slice 5), stub the other two, then fill them in; that ordering is already correct.

**Scraping stays rejected — and is now even less defensible:** Polymarket and Kalshi both expose zero-auth read-only data; OddsPapi legitimately aggregates Pinnacle + Thunderpick. There is no source here that lacks an API. CONFIRMS the PRD/HANDOFF "APIs only, no scraping" guardrail.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Streamlit | Static HTML (vanilla JS) | Only for a throwaway probs-only v0 with manual inputs — it physically *cannot* run the keyed odds ensemble (CORS). PRD already documents this; do not pursue it as the real interface. |
| Streamlit | FastAPI + React/HTMX | If this ever became a multi-user hosted product. For a single local user it is massive overkill and violates the "near-zero UI code" goal. |
| httpx | requests | Fine and simpler; pick it if you want zero learning curve and will never parallelize fetches. Functionally equivalent for ~5 sequential polls. |
| numpy MC | Numba-JIT MC | Only if pure-Python 100k run latency annoys live (TODOS #2). Numba 0.65.x is ready when you need it. |
| numpy.linalg back-solve | scipy.optimize | If the logistic least-squares ratings fit (HANDOFF §5) is numerically fussy. Adds a heavy dep — try numpy first. |
| The Odds API | OddsPapi | The Odds API (500 free req/mo) is a viable second aggregator if OddsPapi's CS2 coverage disappoints. Keep as a backup adapter, not the primary. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **Browser automation / scraping** (Selenium, Playwright, computer-use agents) | Fragile (DOM breakage), slow (seconds vs ms), ToS-risky, geo-blocked (Thunderpick), and adds zero signal — every source has an API. PRD's core guardrail. | OddsPapi / Polymarket Gamma / Kalshi public endpoints |
| **pandas** | A 16-row rating table and per-sim record vectors do not justify a heavy dep; `st.data_editor` takes plain structures and numpy arrays | numpy arrays + list-of-dicts |
| **scipy** (by default) | Wilson CI and the ratings fit are small enough for closed-form / `numpy.linalg`; pulls in a large binary dep against the "no heavy deps" constraint | numpy, hand-rolled Wilson/Newton; add scipy only if fit misbehaves |
| **Pinnacle direct API** | Closed to the public in 2026 | OddsPapi aggregation (legitimate, free tier) |
| **Polymarket CLOB auth / Kalshi RSA auth** for data | Read-only prices need neither; auth is only for placing trades | Polymarket Gamma (no auth), Kalshi public market-data endpoints (no auth) |
| **Numba pinned now** | Premature optimization; LLVM dep complicates the `uv` cold-start and 100k pure-Python is acceptable per PRD perf budget | Defer (TODOS #2); add `numba>=0.65` only if live latency annoys |
| **conda / poetry / pipenv / raw pip-only** | `uv` is the PRD-mandated, faster, single-tool, cross-platform path with a lockfile; mixing managers breaks the one-command bootstrap | `uv` (with a documented pip fallback line) |
| **bash `run.sh`** | Breaks the Windows author (HANDOFF §10.6 explicitly forbids) | `uv run streamlit run app.py` |
| **localStorage/sessionStorage** (if an HTML variant is ever made) | Out of scope; state belongs in Streamlit `session_state` | `st.session_state` |

## Stack Patterns by Variant

**If you stay rating-only (v0, no keys):**
- streamlit + numpy only. `httpx`/`python-dotenv` not imported. Fail-soft banner shows "live odds off."
- This is the default first-run experience — keep it dependency-light.

**If live odds are wired (v1+):**
- Add `httpx` + `python-dotenv`. One adapter per provider behind `OddsProvider`.
- OddsPapi needs a key (env); Polymarket Gamma and Kalshi data need none. Missing OddsPapi key → degrade to the other two, then to rating-only — never crash (HANDOFF §10.6).

**If live-event latency annoys (v2+/v3):**
- Add `numba>=0.65`, JIT the Swiss pairing/sim inner loop. Keep the pure-Python path behind a flag so the backtest gate still runs un-JIT'd for clarity.

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| Python 3.12 | streamlit 1.57, numpy 2.4, numba 0.65, httpx 0.28 | All current; no conflicts. |
| Streamlit 1.57.0 | numpy 2.4 | 1.57 ("2026" release) moved to Starlette/ASGI server — transparent to this app's widget + cache usage. `@st.cache_data` semantics unchanged. |
| numpy 2.4.6 | numba 0.65.x | numba 0.65 explicitly added numpy 2.4 support (Apr 2026) — so deferring numba carries no future incompatibility risk. |
| httpx 0.28 | Python 3.12 | Sync API is requests-shaped; async available if needed. |

## Confidence Assessment

| Area | Confidence | Reason |
|------|------------|--------|
| Python / Streamlit / numpy / uv versions | HIGH | Verified against PyPI + official release notes (May 2026 dates); Context7 confirms Streamlit current major. |
| `@st.cache_data` still the right cache | HIGH | Semantics unchanged in 2026 release; matches HANDOFF §2 keying plan. |
| Numba defer is safe & reversible | HIGH | 0.65.x supports py3.12 + numpy 2.4 (Apr 2026). |
| httpx recommendation | HIGH | 2026-standard; either it or requests works. |
| OddsPapi free-tier terms | MEDIUM-HIGH | 250 req/mo + CS2 Major coverage from current OddsPapi docs/blog; not exercised with a live key against Cologne fixtures yet. |
| Polymarket Gamma read-only | MEDIUM | Public no-auth confirmed in current docs; exact Cologne market slugs unverifiable until markets post. |
| Kalshi public data + CS2 markets | MEDIUM-HIGH | Live CS2 series (`KXCS2GAME`) and zero-auth data endpoints confirmed now; Cologne-specific markets + liquidity unverifiable until event. |

## Open Items for the Roadmap

- **Verify provider market slugs at event time.** Cologne fixtures, Polymarket event slugs, and Kalshi event tickers won't exist until the bracket is announced — the adapters must discover fixtures dynamically (filter by tournament/team), not hardcode IDs. Flag slice 5 for a thin verification pass once markets post.
- **Confirm OddsPapi 250/mo is enough end-to-end.** PRD's ~5 polls fits trivially, but if you add historical-odds backtesting calls (HANDOFF §6 / §9 backtest), budget those against the same quota or pull history once and cache to `data/`.
- **Kalshi/Polymarket thin-liquidity downweighting is load-bearing** (PRD risk §10) — the access works; the *signal quality* on niche CS2 games is the real risk, already handled by the liquidity-weighted pool. No stack change needed, but it's where calibration effort goes.

## Sources

- Context7 `/streamlit/streamlit` (versions 1.54.0 listed), `/streamlit/docs` — Streamlit current line — HIGH
- [streamlit · PyPI](https://pypi.org/project/streamlit/) — 1.57.0 (Apr 28 2026) current stable — HIGH
- [Streamlit 2026 release notes](https://docs.streamlit.io/develop/quick-reference/release-notes/2026) — Starlette default server, cache_data exception chaining — HIGH
- [st.cache_data docs](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_data) — caching semantics — HIGH
- [numpy · PyPI](https://pypi.org/project/numpy/) / [NumPy release notes](https://numpy.org/doc/stable/release.html) — 2.4.6 (May 18 2026) — HIGH
- [uv projects guide](https://docs.astral.sh/uv/guides/projects/) — `uv run`, lockfile, pyproject — HIGH
- [numba · PyPI](https://pypi.org/project/numba/) / [numba releases](https://github.com/numba/numba/releases) — 0.65.x py3.12–3.14 + numpy 2.4 (Apr 2026) — HIGH
- [OddsPapi esports API guide](https://oddspapi.io/blog/esports-odds-api-guide-how-to-get-pinnacle-cs2-lol-data-for-free/) + [pricing 2026](https://oddspapi.io/blog/odds-api-pricing-2026-comparison/) — free REST tier (~250 req/mo), CS2 Major coverage 10–14 books, Pinnacle aggregation — MEDIUM-HIGH
- [Polymarket Gamma API docs](https://docs.polymarket.com/developers/gamma-markets-api/gamma-structure) + [Polymarket API guide 2026](https://pm.wiki/learn/polymarket-api) — Gamma public no-auth read-only — MEDIUM
- [Kalshi API help](https://help.kalshi.com/en/articles/13823854-kalshi-api) + [Quick Start: Market Data](https://docs.kalshi.com/getting_started/quick_start_market_data) + [CS2 events](https://kalshi.com/category/sports/esports/cs2/events) — public market data no-auth, live CS2 markets (KXCS2GAME) — MEDIUM-HIGH
- [HTTPX vs Requests 2026](https://medium.com/@lambert.watts.809/httpx-vs-requests-in-2026-1ff6079252f0) — httpx as modern default — HIGH

---
*Stack research for: local Python Monte Carlo + market-odds-ensemble webapp (Streamlit)*
*Researched: 2026-05-28*
