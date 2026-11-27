# Singapore live watcher and derivative pricer

Paper only. Nothing here places orders or connects to an account.

## Event triggers

PGL publishes results through `news.pglesports.com/api/groupStageEndpoint` with no push
notifications, so `watch.py` polls it (15 s while a match is live or within 20 minutes of
starting, 60 s otherwise) and turns changes into events.

PGL's feed can trail live play: on November 24 its update time stayed fixed while matches were
played. The watcher therefore layers bo3.gg's match API over every match PGL has not finished.
A bo3.gg record counts only if it is the one listing of the same two teams within 12 hours of
PGL's start time and uses the same format. A map winner it cannot name stops the record there,
and PGL's result stands once PGL has one. bo3.gg marks a match current around the veto and can
flip it back, so a match counts as live only once a map is underway, and each start is reported
once.

| Event | Fires when |
|---|---|
| `match_start` | PGL marks the match live, bo3.gg shows a map underway, or the first round score appears. Once per match. |
| `map_end` | the series score increases, once per finished map (a best-of-one's only map included) |
| `match_finish` | PGL marks the match ended, or bo3.gg marks it finished with a decisive score |
| `result_corrected` | PGL changes the winner of a finished match. The event carries the old and new winners and series scores. |
| `fixture_set`, `maps_set`, `round_update` | a later round is drawn, the veto is published, a map's round score changes |

The watcher appends events to `state/events.jsonl`. Use `--price-on` to reprice and
`--wake-on` to wake a supervisor. Both include winner corrections by default.
With `--post URL`, the watcher saves pending notifications in the feed checkpoint and
retries them in order, including after a restart. A successful HTTP response acknowledges
one event. Receivers can use its stable `Idempotency-Key` header to deduplicate a retry.
Round-score updates stay in the local log.
While a match is live the watcher also records Polymarket's match
price every poll in `state/ticks.jsonl`. Comparing those ticks with PGL's event times shows
whether the feed trails the market.

```bash
uv run --frozen python -m analysis.singapore_live.watch            # run until an event, then exit
uv run --frozen python -m analysis.singapore_live.watch --once     # one poll, print state
uv run --frozen python -m analysis.singapore_live.price            # price now and print the table
uv run --frozen python -m analysis.singapore_live.price --grade    # settle paper entries from PGL
```

## Pricing

The Swiss simulator uses available match-winner prices for drawn matches, including
matches in progress. The Kalshi fallback requires a unique listing whose Singapore
settlement terms, teams and scheduled kickoff match the PGL fixture. For undrawn rounds,
the model fits team strengths to available pre-match prices under four prior settings.
It uses these simulations to value Polymarket's 3-0, 3-1, 3-2, 0-3 and qualification
markets and Kalshi's Stage 2 qualification futures. The engine checks its draw against PGL.

If both match quotes disappear between confirmed maps of a best-of-three, the simulator
prices only the remaining maps. Neither feed reports live round scores, so a break counts
only when bo3.gg shows the last map finished and none in progress; otherwise the pricer
treats the map as underway. For equally matched teams, a 1–0 lead implies a 75%
series win probability and a 0–1 deficit implies 25%. If a map is underway and neither
venue provides a usable match quote, the pricer holds the stage forecast and paper entries
until it can price that match again. One result can change other teams' Swiss pairings.

The pricer screens 20 Polymarket shares or 10 Kalshi contracts against the least favorable
fair value, allowing two simulation standard errors. Before recording a paper entry, it
rechecks the market terms, executable depth, costs, live match prices and PGL state.
It records the refreshed price and both observation times if the edge still clears two
cents per share after fees. A live match price may move by up to 5 cents during the recheck,
and the required edge rises by the move: by the sum of the live matches' moves for stage
markets, and for map-score contracts by the move in their own match scaled by how strongly the
contract depends on that price. A larger move blocks the entry until the next pass.

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

## Cologne backtest

`backtest_cologne.py` compares both models with Polymarket's qualification markets
every 15 minutes. The sample covers 19 team markets and 4,085 observations across rounds
4–5 of Cologne Stage 1 and all of Stage 2. The replay uses Bo3.gg's first-map start and
match finish timestamps for 66 matches and checks each winner against Valve's record.
A result enters the simulation at recorded finish. Historical feed publication latency
is unknown. The ratings benchmark fits a spread of 1,660 Valve points using the 198
Austin and Budapest matches preceding Cologne. [Match timestamps and source](data/cologne_match_times.json)

| Check | Market-fed simulator | Ratings only |
|---|---|---|
| Log loss minus the qualification market's, mean ± SE | +0.0157 ± 0.0259 | +0.0546 ± 0.0223 |
| Next-hour move per unit of gap, team's own match live (90% CI) | 0.419 (0.131 to 0.703) | 0.105 (−0.143 to 0.433) |
| Same, between the team's matches (90% CI) | 0.107 (0.060 to 0.158) | 0.096 (0.042 to 0.169) |
| Paper trades held to settlement, 5¢ edge after a 2¢ half-spread and fees | 34 trades, +1.8¢/share (SE 2.9¢) | 31 trades, −5.3¢/share (SE 4.2¢) |

In the 342 in-play observations used in the regression, a 10¢ gap between the market-fed
model and the qualification price corresponded to a 4.2¢ move toward the model over the
next hour. The regression accounts for the ratings gap and the preceding 15-minute price
move. The other 3,724 observations were between the team's matches. The paper profit of
1.8¢ per share was smaller than its 2.9¢ standard error, estimated by resampling whole
team markets so that both sides of a contract stay together. Historical execution costs
use an assumed spread because the archive contains prices without order-book depth.

Registered before Singapore round 3 (November 24): entries tagged `in_play` (the team's own
match was live) are the hypothesis, other entries the control, and `--grade` reports them
separately. While a match is live the watcher reprices every 3 minutes so in-play gaps get
observed.

## Singapore Stage 1 paper results (November 24 to 27)

All 24 paper entries settled against PGL's final records (`ledger/graded.json`). Each entry is 10
Kalshi contracts or 20 Polymarket shares, costed at the executable price including fees.

| Group | Entries | P&L | Mean per share (SE) |
|---|---|---|---|
| Kalshi qualify, team's match live (pre-registered hypothesis) | 4 | +$10.62 | +26.6¢ (14.8¢) |
| Kalshi qualify, otherwise (control) | 9 | +$4.57 | +5.1¢ (15.0¢) |
| Kalshi map score (exploratory) | 8 | +$0.18 | +0.2¢ (14.2¢) |
| Polymarket (reference, logged before the Kalshi-only decision) | 3 | +$21.90 | +36.5¢ (2.9¢) |

The in-play group beat the control by 21.5¢ per share with a standard error of about 21¢, so
Stage 1 does not separate them. The standard errors treat entries as independent, but several
settled on the same match: the control HEROIC YES and the in-play HEROIC NO offset each other,
and Lynn Vision NO and HEROIC YES both lost when Lynn Vision beat HEROIC in round 5. The
effective sample is smaller than the counts. Four of the map entries came from a pricing bug
fixed during the stage, and the entry rules changed during the stage (PR #22). Once every Stage 1
match has ended the pricer records no more entries: Kalshi keeps trading decided contracts until
settlement, and an entry then is not a forecast.

## Live configuration (November 24)

- **Kalshi only.** Paper entries come only from Kalshi markets (`PAPER_VENUES` in `price.py`).
  Polymarket prices still feed the simulator as a read-only input; its derivative quotes stay in
  each snapshot for reference. Polymarket entries logged before this change are graded apart.
- **Map-score markets (exploratory).** Kalshi's best-of-three "Total Maps" and map "Spread"
  contracts are priced from the live series price: the map in progress takes whatever chance
  reconciles that price with fresh maps at the pre-match per-map strength. Entries need a
  5-cent edge and are graded as their own group, outside the pre-registered test. They also
  need a price between 3 and 97 cents and an edge of at most 25 cents, measured at the least
  favorable fresh-map strength within 5 points of the pre-match value (map picks and in-play
  re-rating move it). Near the end of a map the
  market knows the round score and the model does not: on November 25 four 1-cent map entries
  came from stale inputs.
- **Durable runs.** `--ledger` restores the compact state from the committed `ledger/`
  directory when `state/` is empty (a fresh container) and copies it back after every event and
  pricer run. The supervising session commits `ledger/` so the paper ledger survives a container
  replacement.
- **Notifications.** Each wake's JSON includes `push`, one line under 200 characters with the
  game events, new Kalshi paper entries and the Pick'Em chance, for a phone notification.
  A pricer run that records entries wakes the supervisor even without a game event
  (`"exit": "entries"`).
