# TODOS — swiss-mc

Deferred work captured during `/plan-eng-review` (2026-05-28). Each item has enough
context to pick up cold in 3 months.

---

## 1. Decouple odds fetch from the Streamlit app (cron-fed cache)

- **What:** Move the per-round odds fetch out of the Streamlit process. A small
  standalone job (cron on the Ubuntu host) calls the providers and writes a
  `data/odds_cache.json` (or sqlite); the app only ever *reads* that cache.
- **Why:** PRD F1f wants "auto-fetch once per round after pairings post." Streamlit
  is not a scheduler, and Community Cloud sleeps between requests, so a fetch loop
  cannot live inside the app. Inline keyed cross-origin calls also fight the UI rerun
  model.
- **Pros:** Auto-fetch works without a rewrite; app stays fast (no blocking API calls
  on rerun); keys live only in the fetch job's env, not the UI session.
- **Cons:** One more moving part (the cron job) + a cache file contract to keep stable.
- **Context:** Respect the seam from v1 even though auto-fetch is v2. The v1 manual
  "fetch now" button should write to the *same* cache the app reads, so the only thing
  v2 adds is the cron trigger. Do NOT let the app call `OddsProvider.get_quotes()`
  directly on rerun.
- **Depends on:** Odds layer (slice 5). Blocked by nothing for the seam itself.

## 2. Numba acceleration for the Swiss engine (deferred perf lever)

- **What:** JIT-compile the hot Swiss-stage loop (pairing + match sampling) with Numba
  to bring a full 100k-sim run under ~2s.
- **Why:** v0/v1 accept ~10-30s pure-Python runs with a spinner (correct call). But
  during the live event you may re-run constantly as results lock, and the latency
  could get annoying.
- **Pros:** ~10-50x on the branchy core; keeps the interactive loop snappy on event day.
- **Cons:** Numba doesn't love Python objects/dicts — the engine state (`opps: set`,
  team objects) would need restructuring into numeric arrays. Real refactor, spends
  an innovation token.
- **Context:** **Trigger condition:** only do this if full-run latency actually annoys
  you during live use. Pure Python is fine for pre-stage planning. If triggered, the
  refactor is to array-of-structs (team_id, wins, losses, seed, opp-bitmask) so Numba
  can `@njit` the loop. The closed-form Bo3 (no per-map sampling) helps here.
- **Depends on:** Engine complete + backtest passing (don't optimize an unverified sim).

## 3. (auto-captured from review) Backtest is a slice-1 GATE, not validation

- **What:** The round-by-round backtest against Austin/Budapest 2025 must pass before
  any sim output is trusted or the UI is built.
- **Why:** It's the only check that proves the greedy rematch-resolution matches Valve's
  literal priority table (review finding 1b).
- **Context:** Already in §6/§9, but reframed as a blocker. Not really deferrable —
  listed here so it isn't quietly downgraded.
