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
