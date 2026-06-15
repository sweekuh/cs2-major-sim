"""Live World Cup edge monitor: model fair value vs live keyless Kalshi WC markets.

Builds the Elo-prior model (host advantage for Mexico/USA/Canada), runs the tournament Monte
Carlo, fetches open Kalshi WC markets (keyless REST), and prints fee-netted, Kelly-sized, ranked
edge signals. Read-only — it identifies bets, it does not place them. Network is fail-soft: no
markets (or an outage) prints an empty feed rather than raising.

Run: ``uv run python -m scripts.monitor_wc``
"""

from __future__ import annotations

import json
from pathlib import Path

from engine.soccer.dixon_coles import strengths_from_elo
from engine.soccer.teams import groups as group_by_letter
from engine.soccer.teams import host_ids, load_teams
from engine.soccer.tournament import run_tournament
from monitor.edge import stake_row
from monitor.pipeline import scan
from odds.kalshi import KalshiWCProvider

_TICKERS = Path(__file__).resolve().parents[1] / "data" / "kalshi_wc_tickers.json"


def _series_tickers() -> list[str]:
    try:
        return list(json.loads(_TICKERS.read_text())["series"].keys())
    except (OSError, ValueError, KeyError):
        return ["KXMENWORLDCUP", "KXWCGROUPWIN", "KXWCGROUPQUAL"]


def main(*, n_sims: int = 20_000, seed: int = 0, threshold: float = 0.03,
         bankroll: float = 1000.0, home_adv: float = 0.3) -> None:
    teams, _ = load_teams()
    groups = {g: [t.id for t in members] for g, members in group_by_letter(teams).items()}
    model = strengths_from_elo(teams, home_adv=home_adv)
    result = run_tournament(groups, model, n_sims, seed=seed, hosts=host_ids(teams))

    states = KalshiWCProvider().fetch(series_tickers=_series_tickers())  # keyless, fail-soft
    signals, unmapped = scan(states, result, teams, threshold=threshold)

    print(f"\nKalshi World Cup edge monitor — {len(states)} live markets, "
          f"{len(signals)} edges > {threshold:.0%} net (read-only)\n")
    if not states:
        print("  No live Kalshi markets returned (no open markets, or network unavailable).\n")
        return
    hdr = f"{'ticker':<26}{'type':<13}{'side':<5}{'model':>7}{'mid':>7}{'net':>7}{'kelly':>7}{'stake':>9}"
    print(hdr); print("-" * len(hdr))
    for s in signals:
        r = stake_row(s, bankroll=bankroll)
        print(f"{r['ticker']:<26}{r['type']:<13}{r['side']:<5}{r['model']:>7.3f}{r['mid']:>7.3f}"
              f"{r['net_edge']:>7.3f}{r['kelly']:>7.3f}{r['stake']:>9.2f}")
    print(f"\n  {len(unmapped)} market(s) unmapped (e.g. per-match 1X2 — need the match model).\n")


if __name__ == "__main__":
    main()
