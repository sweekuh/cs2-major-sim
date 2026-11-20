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

The optimizer hill-climbed the probability of at least five correct on 100,000 joint tournament draws. It considered substitutions and exchanges between buckets. On the same selection sample it scored all 60 legal one-team replacements for the final card. The best replacement was M80 for DENDELE. Both ballots were fixed before evaluating 200,000 fresh tournaments. The selected card has the same ten picks and assignments as the prior forecast.

| Frozen comparison | Result |
|---|---:|
| Current card passes | 88,253 / 200,000 (44.13%) |
| M80 replacement passes | 87,393 / 200,000 (43.70%) |
| Only the DENDELE card passes | 14,487 |
| Only the M80 card passes | 13,627 |
| DENDELE advantage, paired 95% Monte Carlo interval | +0.43 pp (+0.27 to +0.59) |

With the other seven markets fixed, raising M80’s opening win probability against NIP from 42.5% to 47.5% favored M80 by 0.84 pp (paired 95% interval +0.38 to +1.31). At 52.5%, M80 led by 1.64 pp. These are two tested prices. An exact crossover was not estimated. The full adjustment changes both the opener and later-round strength in these scenarios.

Under VRS alone the fixed card passed 40.63% of trials, under priced openers alone 42.12%, and under half carry 43.39%. The recent-map challenger put it at 14.98% and had the worst later-round scores on all three historical events. These scenarios expose model risk. The sampling intervals reflect repeat draws from a fixed model. Actual Singapore results will determine the card’s score. [Forecast and paired trial counts](../forecast.json)
