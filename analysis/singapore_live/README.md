# Singapore live watcher and derivative pricer

Paper only. Nothing here places orders or connects to an account.

## Event triggers

PGL publishes results through `news.pglesports.com/api/groupStageEndpoint` with no push
notifications, so `watch.py` polls it (15 s while a match is live or within 20 minutes of
starting, 60 s otherwise) and turns changes into events:

| Event | Fires when |
|---|---|
| `match_start` | PGL marks the match live or the first round score appears |
| `map_end` | the series score increases, once per finished map (a best-of-one's only map included) |
| `match_finish` | PGL marks the match ended |
| `fixture_set`, `maps_set`, `round_update` | a later round is drawn, the veto is published, a map's round score changes |

Hooks per event: append to `state/events.jsonl`; run the pricer (`--price-on`); POST the
event to an outbound URL (`--post`, off by default); and exit so a supervising loop can
react (`--wake-on`). While a match is live the watcher also records Polymarket's match
price every poll in `state/ticks.jsonl`. Comparing those ticks with PGL's event times shows
whether the feed trails the market.

```bash
uv run --frozen python -m analysis.singapore_live.watch            # run until an event, then exit
uv run --frozen python -m analysis.singapore_live.watch --once     # one poll, print state
uv run --frozen python -m analysis.singapore_live.price            # price now and print the table
uv run --frozen python -m analysis.singapore_live.price --grade    # settle paper entries from PGL
```

## Pricing

Liquid match-winner prices feed the Swiss simulator directly for every drawn match, including
matches in progress (Polymarket midpoint, Kalshi as fallback). Team strengths for rounds not
yet drawn are fitted to every observed match price: closing prices of finished matches and
current prices of upcoming ones. The fit is a ridge regression toward Nov 19 Valve points, run
under four prior settings; the spread between those settings is the reported range. The
simulator then values the thin markets that depend on several matches: Polymarket's 3-0, 3-1,
3-2, 0-3 and "qualify to Stage 2" lists and Kalshi's "reach Stage 2" futures. The engine's
pairings must reproduce every drawn PGL round, or the pricer stops.

A paper entry is frozen the first time buying one side of a market at the displayed book,
after the taker fee, beats the least favorable scenario's fair value (minus two simulation
standard errors) by at least 2 cents. Sizes: 20 Polymarket shares, 10 Kalshi contracts.

Fees: Polymarket sports takers pay `shares x 0.05 x p x (1 - p)` and makers pay nothing
([docs](https://docs.polymarket.com/trading/fees)). Kalshi charges `0.07 x p x (1 - p)` per
contract, rounded up, through the existing `analysis.singapore_kalshi.model.walk`.

## What this can and cannot show

- The liquid match markets are inputs, never bets. On the 98 Cologne Swiss matches the
  ratings-only model lost to Polymarket's closing price (log loss 0.642 against 0.581), so
  betting the match markets on our own ratings is not supported by evidence.
- The derivative prices are tested for consistency with the match markets. A gap is an edge
  only if the derivative later settles or moves toward the simulator's value more often than
  its price implies. One Swiss stage gives a few dozen markets: enough to catch a broken idea,
  not to prove a working one.
- Books on the derivative markets hold tens to a few hundred shares, so capacity per signal is
  small.
- Polymarket's markets carry `restricted: true` (not available to US persons); Kalshi is the
  US-regulated venue. Check eligibility before acting on anything here.
