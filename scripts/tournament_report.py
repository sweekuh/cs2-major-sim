"""Full-tournament model book: the model's prices across every World Cup futures market.

Runs the tournament Monte Carlo (Elo prior + host advantage for Mexico/USA/Canada) once and
reports the joint-distribution prices the monitor would compare to Kalshi: title odds, group
winners, advancement, exact group order, and furthest-stage (stage-of-elimination) — the
thin/exotic markets where the research said edge could plausibly live.

This is the globally-UNCALIBRATED Elo model (only a handful of matches have sharp 1X2 targets so
far — too sparse to propagate across all 48 teams), so treat the numbers as illustrative of the
machinery, not as a bet list. Comparing them to live Kalshi exotic prices is the next (live) step.
Run: ``uv run python -m scripts.tournament_report``
"""

from __future__ import annotations

import json
from pathlib import Path

from engine.soccer.calibrate import fit_elo_scale
from engine.soccer.dixon_coles import strengths_from_elo
from engine.soccer.markets import (
    p_advance,
    p_champion,
    p_exact_group_order,
    p_furthest_stage,
    p_group_winner,
    top_n,
)
from engine.soccer.teams import groups as group_by_letter
from engine.soccer.teams import host_ids, load_teams
from engine.soccer.tournament import run_tournament
from monitor.match_edge import market_targets
from odds._match import build_name_to_id

_STAGE = {1: "R32", 2: "R16", 3: "QF", 4: "SF", 5: "Final", 6: "Champion"}
_FIXTURES = Path(__file__).resolve().parents[1] / "data" / "wc2026_fixtures.json"


def main(*, n_sims: int = 20_000, seed: int = 0, home_adv: float = 0.3,
         calibrate_scale: bool = False) -> None:
    teams, _ = load_teams()
    name = {t.id: t.name for t in teams}
    groups = {g: [t.id for t in members] for g, members in group_by_letter(teams).items()}

    elo_per_goal = 250.0
    calibrated = False  # whether the spread fit ACTUALLY ran (not just requested)
    if calibrate_scale:
        try:
            fixtures = json.loads(_FIXTURES.read_text()).get("matches", [])
        except (OSError, ValueError):
            fixtures = []
        targets = market_targets(fixtures, build_name_to_id(teams))
        if targets:
            elo_per_goal = fit_elo_scale(teams, targets, neutral=True)
            calibrated = True
            print(f"\n[fit Elo->goals spread to {len(targets)} market matches: "
                  f"elo_per_goal {elo_per_goal:.0f} (default 250; larger = less confident)]")
        else:
            print("\n[calibrate_scale requested but no de-viggable market odds found — "
                  "falling back to the UNCALIBRATED default spread]")

    model = strengths_from_elo(teams, elo_per_goal=elo_per_goal, home_adv=home_adv)
    result = run_tournament(groups, model, n_sims, seed=seed, hosts=host_ids(teams))

    tag = "spread-calibrated" if calibrated else "uncalibrated"
    print(f"\nWorld Cup model book — {n_sims:,} sims, Elo prior ({tag}), host advantage on\n")

    print("Title odds (top 12):")
    for tid, p in top_n(p_champion(result), 12):
        print(f"  {name[tid]:<16}{p:6.1%}")

    print("\nGroup winners (model favourite per group):")
    gw = p_group_winner(result)
    for g in sorted(groups):
        tid, p = max(((t, gw[t]) for t in groups[g]), key=lambda kv: kv[1])
        print(f"  Group {g}: {name[tid]:<16}{p:5.0%}")

    print("\nAdvance to knockout (top 10 + closest calls):")
    adv = p_advance(result)
    ranked = sorted(adv.items(), key=lambda kv: kv[1], reverse=True)
    for tid, p in ranked[:10]:
        print(f"  {name[tid]:<16}{p:6.1%}")
    print("  ... closest to the cut (P(advance) near 50%):")
    for tid, p in sorted(adv.items(), key=lambda kv: abs(kv[1] - 0.5))[:5]:
        print(f"  {name[tid]:<16}{p:6.1%}")

    print("\nExact group order — Group A (top 3 most likely orderings):")
    for order, p in list(p_exact_group_order(result, "A").items())[:3]:
        print(f"  {p:5.1%}  " + " > ".join(name[t] for t in order))

    print("\nFurthest stage — title favourite:")
    fav = top_n(p_champion(result), 1)[0][0]
    dist = p_furthest_stage(result, fav)
    print(f"  {name[fav]}: " + "  ".join(f"{_STAGE[s]} {p:.0%}" for s, p in dist.items() if s >= 1))
    if calibrated:
        print("\n  Spread calibrated to the day's market lines, so tournament confidence is realistic."
              " Still a GLOBAL spread + Elo team priors — per-team market calibration is needed"
              " before trusting any single exotic price for edge.\n")
    else:
        print("\n  NOTE: these title odds are far ABOVE the real market (model favourite ~49% vs"
              " market ~16%) — the uncalibrated Elo->goals spread is too strong, compounded over 7"
              " rounds. Run with calibrate_scale=True to fix the spread; illustrative only.\n")


if __name__ == "__main__":
    main()
