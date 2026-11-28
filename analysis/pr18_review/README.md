# Evidence for the PR #18 review

Independent test of one claim: "this card has a 43.0% chance of five or more correct."

| File | What it is |
|---|---|
| `major_swiss_matches.json` | 297 series from 9 Major Swiss stages (Austin 2025, Budapest 2025, Cologne 2026), parsed from Valve's team detail files, with pre-event Valve points |
| `dl/cologne_market.json` | Polymarket closing prices for the 99 Cologne Swiss matches |
| `fit.py` | Maximum-likelihood spread, stage-cluster bootstrap, walk-forward, reliability |
| `market_join.py` | Market baseline and market-implied spread |
| `replay.py` | Engine pairing replay on all 9 stages |
| `enumerate.py` | Exhaustive search of all 10,090,080 ballots |
| `propagate.py` | Spread and rating-noise propagation, plus the 9-stage P(>=5) backtest |
| `forecast_published_spread_mix_9z.json`, `forecast_spread600_dendele.json` | The two forecasts frozen on 2026-11-20 for scoring: the published spread-mix forecast (9z card) and the earlier spread-600 forecast (DENDELE card) |
| `score_singapore.py` | Post-event scorer with the pre-registered reading rule |

## Correction after commit 254e0f9 (2026-11-20)

The first pass called the 600 spread a failure. That verdict came from a ratings-only fit on all nine
stages. On the evidence that matches the model as built (Stage 1, rounds 2 to 5, market-adjusted
strengths, 75 matches from `data/singapore2026/evidence/historical-stages.json`), 600 is not rejected:
the best-fit spread is about 975 and the 90% profile interval runs from 500 to beyond 4,000.

What still holds: the headline depends on the spread. Under full carry the published card scores
44% at 600, 40% at 1,000, and 38% at 1,400; weighted by that likelihood it is about 39% (35% to 46%).

| File | What it is |
|---|---|
| `joint_spread_carry.py` | Spread by carry grid on the PR's own historical evidence; Kalshi vs. Polymarket check |
| `card_by_spread.py` | Published and re-optimized card under full carry across spreads |
| `sixth_slot.py` | DENDELE vs. M80 vs. 9z in the sixth advance slot across spreads |

Run these three from the repo root with `uv run python analysis/pr18_review/<file>`; `joint_spread_carry.py`
takes `analysis/pr18_review/dl/cologne_market.json` as its argument.

## Kalshi entry rule

The backtest of the Kalshi entry rule moved with that analysis to its own pull request.

The first-pass scripts (`enumerate.py`, `propagate.py`, and the two frozen-forecast comparisons in
the correction note) describe earlier commits of #18. Their published numbers came from the half-carry,
spread-600 forecast at 8f72c94 and will differ if re-run against the current forecast.

## Reproduce

```bash
cd analysis/pr18_review
git clone --depth 1 https://github.com/ValveSoftware/counter-strike_regional_standings.git valve/repo
python stages.py && python fit.py && python market_join.py
cd ../..
uv run python analysis/pr18_review/replay.py
uv run python analysis/pr18_review/enumerate.py analysis/pr18_review/baselines.json
uv run python analysis/pr18_review/propagate.py
```

## Score after the stage

```bash
python analysis/pr18_review/score_singapore.py results.json \
  analysis/pr18_review/forecast_published_spread_mix_9z.json analysis/pr18_review/forecast_spread600_dendele.json
```

`results.json` maps each team to its final record, for example `{"NIP": "3-1"}`.

## Stage 1 result (scored November 27)

Final records come from PGL's results feed, frozen in
[`data/singapore2026/evidence/singapore-stage1-results.json`](../../data/singapore2026/evidence/singapore-stage1-results.json).
Scored with the rule fixed on November 20:

| Forecast | Card | Stated P(≥5) | Per-team log loss | Qualify Brier |
|---|---|---|---|---|
| Published spread mix (9z card) | 2/10, miss | 40.9% | 1.2925 | 0.2514 |
| Spread 600 (DENDELE card) | 2/10, miss | 44.1% | 1.3281 | 0.2607 |
| Base rates (2, 6, 2, 6 of 16) | | | 1.2555 | |

Both forecasts scored worse than base rates. The published forecast's gap to base rates (0.037) is
under the 0.05 the rule treats as noise, so one stage does not show the forecast was worse than
base rates, and it shows no skill either. The two correct picks were Liquid and Eternal Fire, both
3-1, in the advance bucket. Both 3-0 picks qualified without sweeping (100 Thieves 3-2, PVISION
3-1), NIP went 3-0 from the advance bucket, and neither 0-3 pick went winless (Chinggis Warriors
1-3, Lynn Vision 3-2). The teams that went 3-0 (NIP, FlyQuest) and 0-3 (DENDELE, GOSH) were all
off those buckets.

