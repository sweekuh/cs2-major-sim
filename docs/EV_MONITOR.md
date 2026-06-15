# Kalshi World Cup EV monitor — run guide

The "find EV" leg of the operating loop (docs/WORLDCUP.md §7), wired end-to-end and persistent.
It compares **your sim's fair value** to **current Kalshi prices** and writes a ranked, fee-netted,
Kelly-sized list of +EV signals. **Read-only — it never places orders** (execution gated behind
[Q-LEGAL]).

## What runs

```
engine.soccer (Elo-prior Dixon-Coles) ──run_tournament──▶ TournamentResult
                                                              │ (one MC run prices every market)
Kalshi /markets  ──KalshiWCProvider──▶ KalshiMarketState ─────┤
                                                              ▼
                                              monitor.pipeline.scan
                                   (map market → model prob, cost net of fee+spread, rank)
                                                              ▼
                              monitor.report → data/ev_report.json + data/ev_report.md
```

- `odds/kalshi_auth.py` — `KalshiClient`: keyless market reads + **RSA-PSS-signed** balance/positions
  reads when the API key is configured. No order endpoints by design.
- `scripts/ev_report.py` — the entry point (sim → fetch → scan → ranked table + saved artifact).
- `monitor/report.py` — the saved `ev_report.json` / `.md` (gitignored runtime artifact).

## Quickstart

```bash
# Offline (no network, no key) — against a recorded markets file:
uv run python -m scripts.ev_report --fixture tests/fixtures/kalshi_wc_sample.json

# Live, keyless (market data needs no key) — flat $1000 bankroll:
uv run python -m scripts.ev_report

# Live + your key: size stakes against your REAL Kalshi balance:
uv run python -m scripts.ev_report --use-balance --threshold 0.03
```

Useful flags: `--n-sims` (default 20000), `--threshold` (min net edge, default 3%),
`--bankroll` (flat, if not `--use-balance`), `--fraction` (Kelly fraction, default quarter),
`--maker` (cost with the maker fee), `--out` / `--md` (artifact paths).

## Credentials — what the key is (and isn't) for

Reading **current betting options is keyless** — the EV scan needs no key. The API key is only for
(a) `--use-balance` (your real bankroll) and (b) signed reads. Kalshi's auth is RSA request-signing
and needs **both** halves:

| Env var | What |
|---|---|
| `KALSHI_API_KEY_ID` (or the literal `Kalshi`) | API Key ID — the UUID, public half |
| `KALSHI_PRIVATE_KEY` *or* `KALSHI_PRIVATE_KEY_PATH` | RSA private key (PEM inline, or a file) |
| `KALSHI_PRIVATE_KEY_PASSWORD` | only if the PEM is passphrase-encrypted (usually not) |

See `.env.example`. Signature = `base64(RSA-PSS-SHA256(timestamp_ms + METHOD + path))`, salt =
digest length — the scheme `ryanfrigo/kalshi-ai-trading-bot` uses (WORLDCUP §5).

## Two things to flip it from "ready" to "live"

1. **Network egress.** Live reads hit `api.elections.kalshi.com`. If the run prints
   *"No live Kalshi markets returned … blocked egress host"*, add `api.elections.kalshi.com` to the
   environment's **network egress allowlist** (the network policy chosen when the env was created —
   see https://code.claude.com/docs/en/claude-code-on-the-web). This is the condition WORLDCUP §7-D
   calls out: *"Needs … a network policy allowing the provider host."*
2. **Env vars take effect on a NEW session.** A key added to the cloud env after a session started
   is not visible to that running session — start a fresh session so `KALSHI_API_KEY_ID` /
   `KALSHI_PRIVATE_KEY` load.

## Honesty (WORLDCUP §1–2)

`net_edge` is already net of the **exact** Kalshi fee + half-spread, but a positive number is *not*
proof of edge. Liquid favourites are efficient; thin/exotic longshots are a fee trap (a ≤5¢ contract
can pay 12–50% in fees). **CLV vs the sharp close is the only truth oracle** — log signals
(`monitor/signal_log.py`), run paper-only until mean CLV is positive and significant. Also confirm
[Q-FEES] (soccer taker coefficient = 0.07) against the live schedule before trusting sizing.

## Verify

```bash
uv run python -m pytest tests/test_kalshi_auth.py tests/test_report.py -q   # auth signing + report
uv run python -m pytest -q                                                  # full suite
```
