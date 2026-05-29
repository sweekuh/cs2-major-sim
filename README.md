# swiss-mc — Cologne 2026 Swiss Monte Carlo & Pick'Em Optimizer

Monte-Carlo simulates the IEM Cologne Major 2026 CS2 Swiss stage and gives you honest per-team
odds + a recommended Pick'Em ballot. Single local user, no scraping — APIs only.

## Quickstart

```bash
uv run streamlit run app.py
```

`uv` auto-creates the env and installs everything from `pyproject.toml` (~45s cold), the same
command on Windows, Mac, and Linux. No `uv`? Use the pip fallback:

```bash
pip install streamlit numpy
streamlit run app.py
```

**The first sim needs no API key and no editing.** Click **Run ▶** with the shipped default
ratings and watch ~100k Swiss tournaments resolve in ~15 seconds.

### What the numbers mean

- **P(3-0) / P(advance) / P(0-3)** — each team's chance of going 3-0, of advancing (3 wins
  before 3 losses), and of crashing out 0-3. Per-team probabilities from the proven engine.
- **CI bands** — the thin bar under each number is the confidence interval: honest uncertainty,
  NOT false precision. A wide band means "we don't really know yet" — trust it as a warning.

### Seeds are [INFERRED] — reconcile before you trust the output

The shipped seeds and ratings are **inferred** from announced pairings and HLTV ordering, not
the official seed list. A wrong seed silently corrupts every probability, so the app shows a
persistent `⚠ Seeds are INFERRED` banner with a seed→team reconcile table. **At lock:** open the
reconcile panel, eyeball each seed→team against the official Cologne 2026 seed list, edit any
wrong rating in the controls table, then flip the **"seeds confirmed"** toggle to dismiss the
banner. Until you do, treat the numbers as a preview.

### Trust badge

The header badge reads `engine validated vs Valve rulebook unit tests — full backtest pending
seed data`. That is the honest claim: the engine is validated against the Valve rulebook unit
tests, but the full round-by-round pairing-reproduction backtest is deferred until authoritative
seed data is sourced. The badge only flips to a green "validated" state once **both** that
backtest passes **and** you confirm the seeds — never one without the other.

### Live odds (optional, v1+)

Live market odds are an optional enhancement. Copy `.env.example` to `.env` and add an
`ODDSPAPI_KEY` (and optionally Polymarket/Kalshi keys) to back-solve ratings from market odds.
Missing key → the app runs rating-only and shows a `live odds off … using manual ratings`
banner. `.env` is gitignored — never commit real keys.

## Event-day cold-start drill (30 seconds)

When the stage is locking and the clock is running, do NOT debug a missing dep. Run this:

1. `git pull` — get the latest engine + any rating tweaks.
2. Confirm the official seeds against the reconcile table (fix any rating in the controls).
3. Flip the **"seeds confirmed"** toggle to dismiss the INFERRED-seed banner.
4. Click **Run ▶** — first sim needs no API key, ~15s for 100k sims.
