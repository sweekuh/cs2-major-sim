"""Live World Cup edge monitor — the full synthesis, run against live data.

In an environment with ``THE_ODDS_API_KEY`` set and a network policy that allows the providers, this
runs the whole pipeline end to end:
  1. ingest finished results (data/wc2026_results.json) -> update team Elo;
  2. fetch de-vigged sharp 1X2 from The Odds API -> per-team-calibrate the model (build_model);
  3. run the tournament Monte Carlo -> joint distribution / futures prices;
  4. fetch live (keyless) Kalshi WC markets -> price them off the model -> costed, side-chosen,
     depth-ranked, Kelly-sized edge signals (net of the exact Kalshi fee);
  5. log every signal for later CLV-vs-close measurement (the truth oracle).

Every leg is FAIL-SOFT: no key, no network, or no markets degrades to an empty result and a clear
status line rather than a crash — so it also runs harmlessly in a closed sandbox (printing what's
unavailable). Read-only: it identifies bets, it does not place them.

Run: ``uv run python -m scripts.monitor_wc_live``
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

from engine.soccer.calibrate import build_model
from engine.soccer.elo_update import apply_results
from engine.soccer.teams import groups as group_by_letter
from engine.soccer.teams import host_ids, load_teams
from engine.soccer.tournament import run_tournament
from monitor.edge import stake_row
from monitor.match_edge import results_to_tuples, targets_from_quotes
from monitor.pipeline import scan
from monitor.signal_log import Signal, SignalLog
from odds._match import build_name_to_id

_DATA = Path(__file__).resolve().parents[1] / "data"


def _load_matches(name: str) -> list:
    try:
        return json.loads((_DATA / name).read_text()).get("matches", [])
    except (OSError, ValueError):
        return []


def _series_tickers() -> list[str]:
    try:
        return list(json.loads((_DATA / "kalshi_wc_tickers.json").read_text())["series"].keys())
    except (OSError, ValueError, KeyError):
        return ["KXMENWORLDCUP", "KXWCGROUPWIN", "KXWCGROUPQUAL"]


def _fetch_odds(teams, *, regions: str) -> list:
    """Live sharp 1X2 (The Odds API). Returns [] with no key / network / on any error (fail-soft)."""
    key = os.environ.get("THE_ODDS_API_KEY")
    if not key:
        return []
    try:
        from odds.theoddsapi import TheOddsApiProvider
        return TheOddsApiProvider().fetch(teams=teams, api_key=key, regions=regions)
    except Exception:  # noqa: BLE001 — provider already fails soft; belt-and-suspenders here
        return []


def _fetch_kalshi(series) -> list:
    """Live (keyless) Kalshi WC market states. Returns [] on no network / error (fail-soft)."""
    try:
        from odds.kalshi import KalshiWCProvider
        return KalshiWCProvider().fetch(series_tickers=series)
    except Exception:  # noqa: BLE001
        return []


def main(*, n_sims: int = 20_000, seed: int = 0, threshold: float = 0.03, bankroll: float = 1000.0,
         home_adv: float = 0.3, regions: str = "eu,uk", db_path: str = "wc_signals.db",
         log: bool = True) -> None:
    teams, _ = load_teams()
    n2i = build_name_to_id(teams)
    hosts = host_ids(teams)

    # 1. results -> updated Elo
    res = results_to_tuples(_load_matches("wc2026_results.json"), n2i)
    new_elo = apply_results({t.id: t.elo for t in teams}, res, hosts=hosts)
    upd_teams = [dataclasses.replace(t, elo=new_elo[t.id]) for t in teams]

    # 2. live sharp odds -> per-team calibration targets
    quotes = _fetch_odds(teams, regions=regions)
    targets = targets_from_quotes(quotes)

    # 3. build the model (results-updated Elo + spread fit + per-team calibration of covered teams)
    model = build_model(upd_teams, targets, home_adv=home_adv, shrinkage=0.1, neutral=True)

    # 4. tournament -> joint distribution that prices every futures market
    groups = {g: [t.id for t in m] for g, m in group_by_letter(upd_teams).items()}
    result = run_tournament(groups, model, n_sims, seed=seed, hosts=hosts)

    # 5. live Kalshi markets -> costed, ranked edge signals
    states = _fetch_kalshi(_series_tickers())
    signals, unmapped = scan(states, result, upd_teams, threshold=threshold)

    key_on = bool(os.environ.get("THE_ODDS_API_KEY"))
    print("\nKalshi World Cup live edge monitor (read-only)")
    print(f"  results ingested : {len(res)}")
    print(f"  sharp odds (key {'set' if key_on else 'MISSING'}) : {len(targets)} matches calibrated")
    print(f"  kalshi markets   : {len(states)} live ({len(unmapped)} unmapped, e.g. per-match 1X2)")
    print(f"  edge signals     : {len(signals)} over {threshold:.0%} net\n")
    if not states:
        print("  No live Kalshi markets (no network / no open markets). Offline parts ran; set "
              "THE_ODDS_API_KEY + open the network policy to go live.\n")
        return

    hdr = f"{'ticker':<26}{'type':<13}{'side':<5}{'model':>7}{'mid':>6}{'net':>7}{'kelly':>7}{'stake$':>8}"
    print(hdr); print("-" * len(hdr))
    store = SignalLog(db_path) if log else None
    try:
        for s in signals:
            r = stake_row(s, bankroll=bankroll)
            print(f"{r['ticker']:<26}{r['type']:<13}{r['side']:<5}{r['model']:>7.3f}{r['mid']:>6.2f}"
                  f"{r['net_edge']:>7.3f}{r['kelly']:>7.3f}{r['stake']:>8.2f}")
            if store is not None:
                store.record(Signal(
                    ticker=s.ticker, market_type=s.market_type, side=s.side, fair_value=s.model_prob,
                    fair_source="model", kalshi_mid=s.mid, spread=s.spread, depth=s.depth,
                    net_edge=s.net_edge, model_conf=1.0, alerted=False))
    finally:
        if store is not None:
            store.close()
    print(f"\n  {len(signals)} signal(s) logged to {db_path} for CLV-vs-close. Read-only — place "
          "manually, and only after the [Q-LEGAL] check.\n")


if __name__ == "__main__":
    main()
