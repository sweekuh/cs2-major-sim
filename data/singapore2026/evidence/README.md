# Singapore Stage 1 validation

## What was known before play

PGL lists the 16 teams, opening matches and regular Swiss format. Valve’s November 2 invitation list gives the seeds. The simulator uses best-of-one matches until a team can qualify or be eliminated, when the series becomes best-of-three. Valve’s game files specify five correct predictions for Singapore Stage I and separate the undefeated and 3–1/3–2 buckets. The two sweep, six advance and two winless slots each score only their specified record. [PGL bracket and schedule](https://www.pglesports.com/cs2/pgl-major-singapore-2026/) · [Valve rules](https://github.com/ValveSoftware/counter-strike_rules_and_regs/blob/main/major-supplemental-rulebook.md) · [Valve invitation order](https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/invitation/2026/standings_global_2026_11_02.md) · [Singapore challenge](https://github.com/SteamTracking/GameTracking-CS2/blob/83fe83d4fbbd17614ff66e429309d2dacf230b81/game/csgo/pak01_dir/resource/csgo_english.txt#L32100) · [In-game record labels](https://github.com/SteamTracking/GameTracking-CS2/blob/83fe83d4fbbd17614ff66e429309d2dacf230b81/game/csgo/pak01_dir/resource/csgo_english.txt#L54572)

The frozen Singapore inputs include the November 19 Valve points, Polymarket bid and ask for all eight opening matches, and the five players PGL registered for each team. PGL confirmed history in place of meyern for 9z. GOSH is BC.Game in the results feed and PVISION is PARIVISION. Team IDs join those names to the map archive. [Opening prices and ratings](../stage1.json) · [Registered rosters](singapore-rosters.json) · [PGL roster sheet](https://news.pglesports.com/api/articles/1794219566606)

## Historical check

Replaying the recorded winners against the independently published matches reproduced rounds 1–5 in all three Majors, with 8, 8, 8, 6 and 3 pairings. All 99 published series lengths agreed with the record-based best-of-one and best-of-three rule. Each archived match has a source ID, participants, start time, winner and series length. The backtest predicts each actual matchup using only pre-stage strengths and opener prices. Later matchups are known when scoring the historical predictions. The Singapore forecast generates those matchups itself.

Austin and Budapest prices are two-sided decimal moneylines from the bookmaker’s morning editions, normalized by dividing each side’s implied probability by their sum. The Cologne prices are Kalshi bid/ask midpoints from the last available hourly candle ending at or before 10:00 UTC, before the first match at 10:30 UTC. All 24 historical openers have both prices. Singapore’s quotes were collected about four days before play. No comparable four-days-out archive was used for the historical comparison. Budapest’s available ranking snapshot is three weeks before the stage. [Austin bookmaker edition, p. 8](https://sansabet.com/content/Documents/%C5%A0ansabet%20-%202025-06-03T094312.205.pdf) · [Budapest edition, p. 11](https://sansabet.com/content/Documents/%C5%A0ansabet%20-%202025-11-24T091549.264.pdf) · [Kalshi historical market API](https://api.elections.kalshi.com/trade-api/v2/historical/markets) · [Match IDs, seed sources, ranking rosters and dated quotes](historical-stages.json)

Each cell gives **log loss / Brier score** on the same 25 post-opener match winners per event. Lower values are better. A 50/50 prediction scores 0.693 / 0.250. The two VRS baselines coincide here because their only difference is how they price round one.

| Later-round model | Austin 2025 | Budapest 2025 | Cologne 2026 |
|---|---:|---:|---:|
| VRS, with or without priced openers | .639 / .227 | .722 / .259 | .561 / .190 |
| Half of opener adjustment | .611 / .215 | .688 / .248 | .535 / .176 |
| Full opener adjustment | .612 / .214 | .667 / .238 | .524 / .170 |
| Recent opponent-adjusted map results | .650 / .229 | .869 / .332 | .618 / .215 |

Austin and Budapest selected the full adjustment by average later-round log loss. It improved on unadjusted VRS in each and improved both scores in Cologne. Half carry narrowly won Austin on log loss. Cologne provides a later check on the **carry decision**. The earlier forecast had already examined Cologne when setting the VRS spread of 600 raw points per tenfold change in map win odds. Three events and 75 later matches leave substantial uncertainty. The machine-readable scores also include each event’s complete 33-match comparison. [Validation results](validation.json)

The map challenger fits one Bradley–Terry log strength per organization, using all verified played maps in each 60-day window. Each result is weighted by its age with a 30-day half-life. An L2 penalty with coefficient 2 in the gradient shrinks sparsely observed teams toward average. The four archives contain 3,711, 5,651, 5,383 and 5,356 maps respectively. Each row preserves the match and map IDs, map, winner, loser and round score. A row’s time is its series finish time. Every included series finished before its cutoff. Singapore teams have 23–75 verified maps apiece. The map fit pools maps and uses team IDs across roster changes. The archived map rows lack player-level lineups and veto order. These limitations matter particularly for 9z. [Bo3 data query and coverage by window](map-sources.json) · [Per-team coverage](validation.json)

## Singapore decision

Three events and 75 later matches cannot pin down the rating spread. With the full adjustment, the best-fitting spread is near 1,000 Valve points per tenfold change in map odds, and the fit is nearly flat from 500 to beyond 3,000. The forecast therefore draws tournaments across twelve spreads from 400 to 3,000. Each spread is weighted by its likelihood on those 75 matches under a prior that is flat in log-spread. The 600 spread used earlier carries 7% of the weight. [Spread weights](validation.json)

The optimizer hill-climbed the probability of at least five correct on 100,000 joint tournament draws from that mix. It considered substitutions and exchanges between buckets. On the same selection sample it scored all 60 legal one-team replacements for the final card. The best replacement was M80 for 9z. Both ballots were fixed before evaluating 200,000 fresh tournaments. The selected card differs from the prior forecast in one slot: 9z replaces DENDELE among the 3–1 or 3–2 picks.

| Frozen comparison | Result |
|---|---:|
| Current card passes | 81,792 / 200,000 (40.90%) |
| M80 replacement passes | 80,567 / 200,000 (40.28%) |
| Only the 9z card passes | 13,999 |
| Only the M80 card passes | 12,774 |
| 9z advantage over M80, paired 95% Monte Carlo interval | +0.61 pp (+0.45 to +0.77) |
| Prior card (DENDELE) passes | 79,119 / 200,000 (39.56%) |
| 9z advantage over the prior card, paired 95% interval | +1.34 pp (+1.18 to +1.50) |

Scored at a single spread with 25,000 tournaments each, the card passed 41.9% at 400, 41.1% at 600, 40.6% at 1,000, 40.2% at 1,400, 40.1% at 2,000 and 39.7% at 3,000. DENDELE is the better sixth pick only at spreads of about 700 or below, because a wider spread turns each opener price into a larger strength gap and DENDELE opens as a 35.5% underdog. 9z opens as a 61.5% favorite. That price is a thin quote four days before play, and 9z fields a stand-in. A price well below about 58% near lock is a reason to re-run the forecast.

With the other seven markets fixed, raising M80’s opening win probability against NIP from 42.5% to 47.5% moved the comparison toward M80 by an amount inside simulation noise (M80 ahead by 0.41 pp, paired 95% interval −0.05 to +0.87). At 52.5%, M80 led by 1.46 pp (+1.00 to +1.92). These are two tested prices. An exact crossover was not estimated. The full adjustment changes both the opener and later-round strength in these scenarios.

Across the same spread mix, the fixed card passed 25.6% of trials under VRS alone, 29.7% under priced openers alone, and 35.6% under half carry. The recent-map challenger put it at 10.8% and had the worst later-round scores on all three historical events. The headline therefore depends on the full adjustment, which three events favored by margins inside noise. These scenarios expose model risk. The sampling intervals reflect repeat draws from a fixed model. Actual Singapore results will determine the card’s score. [Forecast and paired trial counts](../forecast.json)

# Singapore Stage 2 (written November 27, before play)

## Stage 1 scored

The rule fixed on November 20 scored the published card at **2 of 10, a miss**, against a stated
40.9% chance of five or more. Its per-team log loss over the four record buckets was 1.2925, worse
than the 1.2555 of base rates; the rule treats a gap under about 0.05 as noise, so Stage 1 shows no
skill without showing the forecast was worse than base rates. The correct picks were Liquid and
Eternal Fire at 3-1. [Stage 1 results](singapore-stage1-results.json) · [Scoring details](../../../analysis/pr18_review/README.md#stage-1-result-scored-november-27)

## What was known before play

Valve's rules seed the eight invited teams 1 to 8 by pre-event global VRS and the eight Stage 1
qualifiers 9 to 16 by final Stage 1 seed: record, then Buchholz difficulty, then initial seed.
Round one pairs seed k with seed k + 8. These seeds reproduce all eight PGL round-one pairings,
and every opener is best of one. The One fields the roster Valve listed as 1win on November 2
(nafany, ArtFr0st, Ax1Le, BELCHONOKK, fame), which places it fourth among the invited teams, as
PGL's pairing requires. Valve's game files give Stage II the same challenge as Stage I: ten picks,
five correct to pass. [Fixture](../stage2.json) · [Valve rules](https://github.com/ValveSoftware/counter-strike_rules_and_regs/blob/main/major-supplemental-rulebook.md) · [PGL roster sheet](https://news.pglesports.com/api/articles/1794219566606) · [Stage II challenge](https://github.com/SteamTracking/GameTracking-CS2/blob/master/game/csgo/pak01_dir/resource/csgo_english.txt)

All sixteen ratings are Valve's November 2 points. HLTV's November 19 page, used for Stage 1,
refuses automated requests. The Stage 1 teams' November 19 points sat on average 53 below their
November 2 points, a near-uniform shift, so one snapshot for every team keeps the gaps comparable.
The openers are Polymarket bid and ask at 17:30 UTC on November 27, about ten and a half hours
before the first match. [November 2 standings](https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/invitation/2026/standings_global_2026_11_02.md)

## Singapore Stage 1 as a fourth validation event

The engine replays PGL's Stage 1 draw exactly (8, 8, 8, 6 and 3 pairings). Re-scoring the three
historical events reproduces the stored Stage 1 validation to the last digit. Each cell gives
**log loss / Brier score** on that event's 25 later-round matches, at a spread of 600.

| Later-round model | Austin 2025 | Budapest 2025 | Cologne 2026 | Singapore 2026 | Pooled log loss |
|---|---:|---:|---:|---:|---:|
| VRS, with or without priced openers | .639 / .227 | .722 / .259 | .561 / .190 | .684 / .243 | .652 |
| Half of opener adjustment | .611 / .215 | .688 / .248 | .535 / .176 | .693 / .247 | .632 |
| Full opener adjustment | .612 / .214 | .667 / .238 | .524 / .170 | .706 / .253 | .627 |

The full adjustment, chosen for Stage 1, scored worst on Singapore and worse than a coin flip
(.693). Matched match by match, it beats priced openers alone by 0.024 nats per match over all 100
later matches, with a standard error of 0.027 (t = -0.9); on Singapore alone it lost by 0.022
(SE 0.033). Stage 1's rule required the challenger to beat the base on every event, so with Singapore
added it would fall back to priced openers. The evidence no longer separates the two. [Re-validation](stage2-validation.json)

Singapore's later matches favored wide spreads, where ratings matter less: its log loss fell
steadily from 400 to 3,000. With Singapore added, the likelihood weights move toward wide spreads.
Spreads of 1,000 to 3,000 now carry 79% of the weight, against 68% before; 600 carries 3.9%.

## Stage 2 card

The card was selected twice, independently: under the full adjustment (100,000 tournaments, seed
20261128) and under priced openers alone (seed 20261129). Both selections returned the same ten picks.

| Bucket | Picks |
|---|---|
| 3-0 | FUT Esports, The MongolZ |
| 3-1 or 3-2 | Nemiga, G2, Natus Vincere, The One, NIP, Astralis |
| 0-3 | Lynn Vision, FlyQuest |

| Model for later rounds | Card passes (five or more correct) |
|---|---:|
| Full opener adjustment | 61,089 / 200,000 (30.5%, 95% sampling interval 30.3% to 30.8%) |
| Half adjustment | 28.4% of 25,000 |
| Priced openers alone | 51,921 / 200,000 (26.0%) |
| VRS alone | 24.0% of 25,000 |

Under the full adjustment the expected number correct is 3.79, and at single spreads the card
passes 35.5% at 400 and 29.2% at 3,000. The pass rate is below Stage 1's stated 40.9% because the
Stage 2 field is closer: the widest opener is FUT Esports at 73.5% and three openers sit within
four points of even. After Stage 1, a 26% to 31% estimate is the model's view, not a measured rate.

The closest alternative replaces Astralis with 100 Thieves among the 3-1 or 3-2 picks. On the same
200,000 tournaments the card passed 13,248 times when the alternative failed and the alternative
passed 11,884 times when the card failed: the card leads by 0.68 points (paired 95% interval 0.53
to 0.84). Under priced openers alone the closest alternative was MIBR for Astralis (0.41 points). With
the other seven prices fixed, raising 100 Thieves' price against MIBR from the observed 51.5% to
56.5% left the two cards tied (-0.26 points, interval -0.70 to +0.18); at 61.5% the 100 Thieves
card led by 1.22 points. A 100 Thieves price above about 57% near lock is a reason to swap.

## Qualification odds next to the markets

Model qualification odds under the full adjustment, with Polymarket and Kalshi "reach Stage 3"
mids where the book was ten cents wide or less (17:33 UTC, November 27; read only).

| Team | Model | Polymarket | Kalshi |
|---|---:|---:|---:|
| FUT Esports | 79.8% | 78.5% | 78.0% |
| Natus Vincere | 73.1% | 81.5% | |
| The MongolZ | 62.9% | 62.5% | |
| G2 | 62.2% | 60.5% | 55.5% |
| Nemiga | 62.2% | | |
| The One | 57.7% | | |
| NIP | 54.2% | 54.0% | 52.0% |
| Astralis | 54.0% | 47.5% | 17.5% |
| 100 Thieves | 49.0% | 49.0% | 51.0% |
| MIBR | 47.3% | 47.5% | |
| Eternal Fire | 46.8% | 36.5% | 35.0% |
| Liquid | 46.0% | | |
| Imperial | 35.7% | 27.0% | 31.5% |
| PVISION | 33.9% | | |
| FlyQuest | 19.0% | | 47.5% |
| Lynn Vision | 16.3% | 17.5% | |

The model and Polymarket agree within two points for seven of the eleven teams both price. The
model is lower on Natus Vincere (8 points) and higher on Eternal Fire (10), Imperial (9) and
Astralis (6.5). Kalshi
and Polymarket disagree by 30 points on Astralis, and Kalshi's FlyQuest price sits 28 points above
the model; both look like thin or stale Kalshi books rather than information. None of these
differences is a bet: the full adjustment that produces them failed on Singapore Stage 1. [Forecast with market check](../forecast_stage2.json)

## Limits

- The recent-map challenger was not refit for Stage 2. It scored worst on all three historical
  events, and its Stage 2 map archive was not assembled.
- The spread weights and model comparison come from Stage 1s. Stage 2's field is stronger and
  closer, and no historical Stage 2 was replayed.
- November 2 points predate three weeks of results, including Stage 1 itself. The opener prices
  carry the market's view of those results into round one; the full adjustment carries them further.
- Four events, 100 later matches, cannot pin down the spread or the model. The interval for each
  pass rate covers simulation noise only.

