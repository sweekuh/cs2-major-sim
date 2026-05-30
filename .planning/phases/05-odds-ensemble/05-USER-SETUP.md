# Phase 5: User Setup Required

**Generated:** 2026-05-30
**Phase:** 05-odds-ensemble
**Status:** Incomplete

Complete these items to enable the **live market-odds ensemble**. Everything here is OPTIONAL —
the app runs fully **rating-only with NO key and NO setup** (the first sim needs nothing; a
`live odds off (no ODDSPAPI_KEY) — using manual ratings` banner shows). Claude automated all code;
these items require human access to an external account / a real browser once Cologne markets post.

## Environment Variables

| Status | Variable | Source | Add to |
|--------|----------|--------|--------|
| [ ] | `ODDSPAPI_KEY` | OddsPapi dashboard → API key (free tier ~250 req/month). Leave BLANK to run keyless (Polymarket+Kalshi only) or rating-only. | `.env` |

> Polymarket and Kalshi are **keyless public reads** — no key needed. The `ODDSPAPI_KEY` only
> unlocks the Pinnacle anchor (one of three sources). Missing key → keyless 2-source pool or
> rating-only, never a crash.

## Account Setup

- [ ] **Create an OddsPapi account** (optional — only for the Pinnacle anchor)
  - URL: https://oddspapi.io
  - Skip if: you are fine with the keyless Polymarket+Kalshi pool, or rating-only.

## Dashboard Configuration

- [ ] **Confirm IEM Cologne 2026 CS2 fixture coverage / event slugs / series tickers** (DEFERRED — markets not posted as of 2026-05-30)
  - Location: oddspapi.io / gamma-api.polymarket.com / kalshi.com
  - This is the **Task-3 deferred human-verify checkpoint**. Once Cologne markets post, verify the
    live slugs/tickers/field names via gstack `/browse` (NEVER the mcp chrome tools — CLAUDE.md):
    1. **OddsPapi** — CS2 IEM Cologne `/fixtures` + `/odds` field names (tournament string,
       `bookmakerOdds`/market-id, participant names); adjust `odds/oddspapi.py` + `discover_fixtures`
       if the recorded shapes differ. **Budget the ~250 req/month quota** — manual button + per-round
       trigger only, no polling.
    2. **Polymarket** — the Cologne event slug + whether per-match (vs only tournament-winner)
       markets exist; adjust `odds/polymarket.py` (keyless Gamma `/events`).
    3. **Kalshi** — the CS2/Cologne series ticker (esports coverage is sparse — `[]` is a valid
       fail-soft result); adjust `odds/kalshi.py` (keyless trade-api v2).
  - Notes: any adapter adjustment is a small parser tweak validated by re-recording the fixture and
    re-running `uv run pytest -q tests/test_odds.py` — the de-vig/pool/back-solve math does not change.

## Local Development

1. Copy the example env file and fill in any key you have (all optional):
   ```bash
   cp .env.example .env
   # edit .env — set ODDSPAPI_KEY if you have one; leave blank otherwise
   ```
2. Fetch odds (writes the read-only `data/odds_cache.json`):
   ```bash
   uv run python -m scripts.fetch_odds
   ```
   (Or click **"Fetch odds now"** in the app — same single entry, out of the render path.)
3. Run the app; with a valid cache present, the run path back-solves ratings + feeds the market
   blend/var so the reported probabilities reflect the odds:
   ```bash
   uv run streamlit run app.py
   ```

## Verification

```bash
# 1. Zero-config baseline (no key, no cache) — app runs rating-only + the banner, no crash.
uv run streamlit run app.py     # click Run -> per-team P(advance); banner shows "live odds off"

# 2. Fetch (keyless is fine) then confirm a cache file is written with the frozen schema.
uv run python -m scripts.fetch_odds
cat data/odds_cache.json        # expect {_meta:{fetched_at,version:1,...}, blended:{...}}

# 3. Optional: confirm the key is detected when set (presence-only, value never logged).
grep ODDSPAPI .env
```

Expected results:
- No key + no cache → app renders rating-only with the `live odds off … manual ratings` banner.
- `python -m scripts.fetch_odds` writes `data/odds_cache.json` (an EMPTY `blended:{}` until Cologne
  markets post — that is the expected fail-soft state, not an error).
- With a non-empty cache present, hitting Run moves ≥1 reported P vs the rating-only run.

---

**Once all items complete:** Mark status as "Complete" at top of file.
