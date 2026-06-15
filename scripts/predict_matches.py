"""Predict specific World Cup fixtures and value the bets on them.

Reads a fixtures file (data/wc2026_fixtures.json), prices each match's 1X2 off the Elo-prior
model (host advantage when a host plays at home), prints the predicted outcome, and — where
pre-match decimal odds are supplied — the EV per $1 stake on each outcome, flagging +EV bets.

The model is the UNCALIBRATED Elo prior: the backtest showed it only marginally beats a coin and
is overconfident, so treat predictions and EV as illustrative, not advice.
Run: ``uv run python -m scripts.predict_matches``
"""

from __future__ import annotations

import json
from pathlib import Path

from engine.soccer.dixon_coles import strengths_from_elo
from engine.soccer.teams import host_ids, load_teams
from monitor.match_edge import decimal_ev, match_prediction
from odds._match import build_name_to_id, resolve_id
from odds.base import devig_three_way_shin

_FIXTURES = Path(__file__).resolve().parents[1] / "data" / "wc2026_fixtures.json"


def main(*, home_adv: float = 0.3) -> None:
    teams, _ = load_teams()
    model = strengths_from_elo(teams, home_adv=home_adv)
    hosts = host_ids(teams)
    n2i = build_name_to_id(teams)
    try:
        fixtures = json.loads(_FIXTURES.read_text()).get("matches", [])
    except (OSError, ValueError):
        fixtures = []

    if not fixtures:
        print("\nNo fixtures in data/wc2026_fixtures.json — populate it with the day's matches.\n")
        return

    print("\nWorld Cup match predictions — model vs de-vigged (Shin) market\n")
    print(f"{'match':<26}{'outcome':<10}{'model':>7}{'market':>8}{'gap':>7}{'odds':>7}{'EV/$1':>8}")
    print("-" * 73)
    plus_ev = []
    overconf = []  # (match, sum |model-market| over outcomes) to flag miscalibration
    for m in fixtures:
        hid, aid = resolve_id(m["home"], n2i), resolve_id(m["away"], n2i)
        if hid is None or aid is None:
            print(f"  [skip] unresolved: {m['home']} vs {m['away']}")
            continue
        neutral = m.get("neutral", hid not in hosts)
        p = match_prediction(model, hid, aid, neutral=neutral)["probs"]
        odds = m.get("odds") or {}
        market = None
        if all(odds.get(k) for k in ("home", "draw", "away")):
            market = dict(zip(("home", "draw", "away"),
                              devig_three_way_shin(odds["home"], odds["draw"], odds["away"])))
            overconf.append((m, sum(abs(p[k] - market[k]) for k in p)))
        label = f"{m['home'][:11]} v {m['away'][:10]}"
        for outcome, name in (("home", m["home"]), ("draw", "Draw"), ("away", m["away"])):
            o = odds.get(outcome)
            mk = market[outcome] if market else None
            gap = (p[outcome] - mk) if mk is not None else None
            ev = decimal_ev(p[outcome], o) if o else None
            print(f"{label if outcome == 'home' else '':<26}{outcome:<10}{p[outcome]:>7.1%}"
                  f"{(f'{mk:.1%}' if mk is not None else '—'):>8}"
                  f"{(f'{gap:+.1%}' if gap is not None else '—'):>7}"
                  f"{(f'{o:.2f}' if o else '—'):>7}"
                  f"{(f'{ev:+.2f}' if ev is not None else '—'):>8}")
            if ev and ev > 0:
                plus_ev.append((m, name, p[outcome], mk, o, ev))

    if plus_ev:
        print("\nApparent +EV bets (model prob x decimal odds - 1 > 0):")
        for m, name, prob, mk, odd, ev in sorted(plus_ev, key=lambda r: r[5], reverse=True):
            tag = ""
            if mk is not None and prob - mk > 0.10:
                tag = "  <- model >10pts over market: likely overconfidence, NOT edge"
            print(f"  {name + ' (' + m['home'] + ' v ' + m['away'] + ')':<42}"
                  f"model {prob:.0%} vs mkt {mk:.0%}  EV {ev:+.2f}{tag}")

    if overconf:
        worst = max(overconf, key=lambda r: r[1])
        print(f"\nCalibration check: mean |model - market| total per match = "
              f"{sum(c for _, c in overconf) / len(overconf):.2f} "
              f"(0 = agrees with the sharp line). Large gaps = the model is overconfident, so the "
              f"'EV' above is mostly a calibration artifact, not real edge.")
    print("\n  Caveat: UNCALIBRATED Elo model, shown overconfident on the backtest — illustrative, "
          "not betting advice. The de-vigged market is the better probability estimate.\n")


if __name__ == "__main__":
    main()
