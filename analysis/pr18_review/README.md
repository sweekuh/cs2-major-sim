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
| `forecast_pr18_spread600.json`, `forecast_spread1170.json` | The two forecasts frozen on 2026-11-20 |
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

## Kalshi entry rule (commit f76e48b)

`kalshi_rule_backtest.py` applies the entry rule in `analysis/singapore_kalshi/` to the 98 Cologne 2026
Swiss matches, with Polymarket closing prices (`cologne_joined.json`) standing in for an executable price.
Run from the repo root: `uv run python analysis/pr18_review/kalshi_rule_backtest.py analysis/pr18_review/cologne_joined.json`.

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
  analysis/pr18_review/forecast_pr18_spread600.json analysis/pr18_review/forecast_spread1170.json
```

`results.json` maps each team to its final record, for example `{"NIP": "3-1"}`.
