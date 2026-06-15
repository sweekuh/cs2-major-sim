"""On-demand World Cup cycle: ingest results -> update model -> predict upcoming + value bets.

One command for the operating loop's data->model->EV legs:
  1. ingest finished results (data/wc2026_results.json) and fold them into team Elo (apply_results);
  2. rebuild the goals model from the updated Elo (optionally market-calibrated via build_model);
  3. report the biggest strength movers from those results;
  4. predict the upcoming fixtures (data/wc2026_fixtures.json) with model vs de-vigged market + EV.

Read-only. Live odds/Kalshi are out of scope here (sandbox has no network); pass calibrate=True to
calibrate to whatever pre-match odds the fixtures file carries. Point the fixtures file at the rest
of the stage to predict it. Run: ``uv run python -m scripts.run_cycle``
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from engine.soccer.calibrate import build_model
from engine.soccer.elo_update import apply_results
from engine.soccer.teams import host_ids, load_teams
from monitor.match_edge import (
    decimal_ev,
    market_targets,
    match_prediction,
    results_to_tuples,
)
from odds._match import build_name_to_id, resolve_id

_DATA = Path(__file__).resolve().parents[1] / "data"


def _load(name: str) -> list:
    try:
        return json.loads((_DATA / name).read_text()).get("matches", [])
    except (OSError, ValueError):
        return []


def main(*, home_adv: float = 0.3, calibrate: bool = False, movers: int = 6) -> None:
    teams, _ = load_teams()
    n2i = build_name_to_id(teams)
    hosts = host_ids(teams)

    # 1. ingest results -> updated Elo
    results = _load("wc2026_results.json")
    res_tuples = results_to_tuples(results, n2i)
    base_elo = {t.id: t.elo for t in teams}
    new_elo = apply_results(base_elo, res_tuples, hosts=hosts)
    upd_teams = [dataclasses.replace(t, elo=new_elo[t.id]) for t in teams]
    name = {t.id: t.name for t in teams}

    print(f"\nWorld Cup cycle — ingested {len(res_tuples)} finished result(s)\n")
    movers_sorted = sorted(((tid, new_elo[tid] - base_elo[tid]) for tid in base_elo),
                           key=lambda kv: abs(kv[1]), reverse=True)
    print("Biggest Elo movers from results:")
    for tid, d in movers_sorted[:movers]:
        if abs(d) < 1e-9:
            break
        print(f"  {name[tid]:<16}{base_elo[tid]:>6.0f} -> {new_elo[tid]:>6.0f}  ({d:+.0f})")

    # 2. build model from updated Elo (optionally calibrated to the fixtures' market lines)
    fixtures = _load("wc2026_fixtures.json")
    targets = market_targets(fixtures, n2i) if calibrate else {}
    model = build_model(upd_teams, targets, home_adv=home_adv, shrinkage=0.2, neutral=True)

    # 3. predict the upcoming fixtures
    tag = "results-updated + market-calibrated" if (calibrate and targets) else "results-updated Elo"
    print(f"\nUpcoming fixtures ({len(fixtures)}) — {tag} model:")
    print(f"{'match':<26}{'P(home)':>8}{'P(draw)':>8}{'P(away)':>8}  pick  best +EV")
    print("-" * 74)
    for m in fixtures:
        hid, aid = resolve_id(m["home"], n2i), resolve_id(m["away"], n2i)
        if hid is None or aid is None:
            print(f"  [skip] {m['home']} v {m['away']}")
            continue
        neutral = True if (calibrate and targets) else m.get("neutral", hid not in hosts)
        p = match_prediction(model, hid, aid, neutral=neutral)
        pr = p["probs"]
        pick = m["home"] if p["pick"] == "home" else (m["away"] if p["pick"] == "away" else "Draw")
        best = ""
        odds = m.get("odds") or {}
        evs = [(decimal_ev(pr[k], odds[k]), k) for k in ("home", "draw", "away")
               if isinstance(odds.get(k), (int, float)) and odds.get(k) > 1.0]
        pos = [(ev, k) for ev, k in evs if ev > 0]
        if pos:
            ev, k = max(pos)
            who = m["home"] if k == "home" else (m["away"] if k == "away" else "Draw")
            best = f"{who} {ev:+.2f}"
        print(f"{m['home'] + ' v ' + m['away']:<26}{pr['home']:>8.1%}{pr['draw']:>8.1%}"
              f"{pr['away']:>8.1%}  {pick[:5]:<5} {best}")
    print("\n  Read-only, illustrative. +EV here uses raw book odds; calibrate=True removes the model's"
          " overconfidence so only genuine gaps remain. Compare to live Kalshi for real edge.\n")


if __name__ == "__main__":
    main()
