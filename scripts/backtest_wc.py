"""Match-level backtest of the Dixon-Coles model against played 2026 World Cup results.

Loads the Elo-prior model (uncalibrated — the independent signal), prices each played match's 1X2,
and scores it against the actual result with proper scoring rules (log-loss, Brier, RPS), versus a
uniform (1/3) baseline and — where a pre-match line exists — the de-vigged market.

IMPORTANT: this is ~10 matches. Per the research, a handful of games is statistically
uninformative — it validates the *machinery* and gives a directional read, not a verdict on edge.
Run: ``uv run python -m scripts.backtest_wc``
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from engine.soccer.dixon_coles import match_1x2, strengths_from_elo
from engine.soccer.scoring import brier, log_loss, outcome_index, reliability_bins, rps
from engine.soccer.teams import load_teams
from odds._match import build_name_to_id, resolve_id
from odds.base import devig_three_way_shin

_RESULTS = Path(__file__).resolve().parents[1] / "data" / "wc2026_results.json"
_OUTCOME_LABEL = {0: "home", 1: "draw", 2: "away"}


def _mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def main() -> None:
    teams, _ = load_teams()
    name_to_id = build_name_to_id(teams)
    model = strengths_from_elo(teams)
    matches = json.loads(_RESULTS.read_text())["matches"]

    uniform = (1 / 3, 1 / 3, 1 / 3)
    preds, outs = [], []
    m_ll, m_br, m_rps = [], [], []
    u_ll = []
    mk_ll, mk_model_ll = [], []  # market vs model on the subset that has odds

    print(f"\nMatch-level backtest — Elo-prior Dixon-Coles model ({len(matches)} matches)\n")
    print(f"{'match':<34}{'score':>6}  {'actual':<5} {'model P(h/d/a)':<22}{'logloss':>8}{'rps':>7}")
    print("-" * 90)

    for m in matches:
        hid = resolve_id(m["home"], name_to_id)
        aid = resolve_id(m["away"], name_to_id)
        if hid is None or aid is None:
            print(f"  [skip] could not resolve {m['home']} vs {m['away']}")
            continue
        probs = match_1x2(model, hid, aid, neutral=True)
        actual = outcome_index(m["home_goals"], m["away_goals"])
        ll, br, rp = log_loss(probs, actual), brier(probs, actual), rps(probs, actual)
        m_ll.append(ll); m_br.append(br); m_rps.append(rp)
        u_ll.append(log_loss(uniform, actual))
        preds.append(probs); outs.append(actual)

        flag = "" if m.get("verified", True) else " *"
        label = f"{m['home']} v {m['away']}{flag}"
        score = f"{m['home_goals']}-{m['away_goals']}"
        pstr = f"{probs[0]:.0%}/{probs[1]:.0%}/{probs[2]:.0%}"
        print(f"{label:<34}{score:>6}  {_OUTCOME_LABEL[actual]:<5} {pstr:<22}{ll:>8.3f}{rp:>7.3f}")

        if m.get("odds"):
            o = m["odds"]
            mk = devig_three_way_shin(o["home"], o["draw"], o["away"])
            mk_ll.append(log_loss(mk, actual))
            mk_model_ll.append(ll)

    print("-" * 90)
    print(f"\nAggregate (lower is better):")
    print(f"  model    log-loss {_mean(m_ll):.3f}   Brier {_mean(m_br):.3f}   RPS {_mean(m_rps):.3f}")
    print(f"  uniform  log-loss {_mean(u_ll):.3f}   (1/3,1/3,1/3 baseline; ln3 = {math.log(3):.3f})")
    edge = _mean(u_ll) - _mean(m_ll)
    print(f"  model vs uniform: {'BEATS' if edge > 0 else 'WORSE THAN'} baseline by {edge:+.3f} log-loss")

    if mk_ll:
        print(f"\n  On {len(mk_ll)} match(es) with a pre-match line:")
        print(f"    market log-loss {_mean(mk_ll):.3f}   vs model {_mean(mk_model_ll):.3f}")

    print(f"\n  Reliability (predicted vs empirical over all outcome slots):")
    for b in reliability_bins(preds, outs, n_bins=5):
        print(f"    pred {b['lo']:.1f}-{b['hi']:.1f}: mean_pred {b['mean_pred']:.2f}  "
              f"empirical {b['empirical']:.2f}  (n={b['n']})")

    print("\n  * = unverified result (single-source). Caveat: ~10 matches is illustrative, not "
          "conclusive — it validates the pipeline and gives a directional read only.\n")


if __name__ == "__main__":
    main()
